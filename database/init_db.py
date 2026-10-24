"""Create the smart_iot schema and apply pending upgrades. Safe to re-run.

Run from the repo root:  python -m database.init_db
"""

import logging
import sys

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .migrations import upgrade
from .models import Base
from .session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("init_db")


def init_db() -> list[str]:
    """Create any missing tables, apply pending migrations, and return the table names now present."""
    Base.metadata.create_all(engine)
    upgrade(engine)
    return sorted(inspect(engine).get_table_names())


def main():
    # Log host/db only -- never the password.
    logger.info("Connecting to MySQL at %s:%s/%s", engine.url.host, engine.url.port, engine.url.database)
    try:
        tables = init_db()
    except OperationalError as exc:
        logger.error("Could not initialise database: %s", exc.orig)
        sys.exit(1)
    logger.info("Schema ready, tables: %s", ", ".join(tables))


if __name__ == "__main__":
    main()
