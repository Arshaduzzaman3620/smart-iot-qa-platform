"""Create the smart_iot schema and apply pending upgrades. Safe to re-run.

Run from the repo root:  python -m database.init_db
Set INIT_DB_WAIT=<seconds> to keep retrying while MySQL is still starting (compose.yaml does).
"""

import logging
import os
import sys
import time

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .migrations import upgrade
from .models import Base
from .session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("init_db")

# MySQL error codes meaning "server not reachable (yet)": can't connect / lost connection.
# Anything else (wrong password, unknown database) won't fix itself, so it fails at once.
NOT_READY_CODES = {2003, 2013}
RETRY_INTERVAL = 2


def init_db() -> list[str]:
    """Create any missing tables, apply pending migrations, and return the table names now present."""
    Base.metadata.create_all(engine)
    upgrade(engine)
    return sorted(inspect(engine).get_table_names())


def init_db_when_ready(wait: float, sleep=time.sleep, clock=time.monotonic) -> list[str]:
    """init_db(), retrying for up to `wait` seconds while MySQL is not accepting connections yet."""
    deadline = clock() + wait
    while True:
        try:
            return init_db()
        except OperationalError as exc:
            code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
            if code not in NOT_READY_CODES or clock() + RETRY_INTERVAL > deadline:
                raise
            logger.info("MySQL not ready yet (%s), retrying in %ss", code, RETRY_INTERVAL)
            sleep(RETRY_INTERVAL)


def main():
    # Log host/db only -- never the password.
    logger.info("Connecting to MySQL at %s:%s/%s", engine.url.host, engine.url.port, engine.url.database)
    try:
        tables = init_db_when_ready(float(os.getenv("INIT_DB_WAIT", "0")))
    except OperationalError as exc:
        logger.error("Could not initialise database: %s", exc.orig)
        sys.exit(1)
    logger.info("Schema ready, tables: %s", ", ".join(tables))


if __name__ == "__main__":
    main()
