"""Small, idempotent schema upgrades for databases created by an earlier phase.

`create_all` creates missing tables but never alters existing ones, so columns added later are
applied here. Each step checks whether it is needed, so running it again is a no-op.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("migrations")


def _add_latest_reading_pointer(engine: Engine) -> bool:
    """Phase 14: sensors.latest_telemetry_id / latest_reading_at, backfilled from telemetry."""
    columns = {c["name"] for c in inspect(engine).get_columns("sensors")}
    if "latest_telemetry_id" in columns:
        return False
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE sensors ADD COLUMN latest_telemetry_id BIGINT NULL, "
            "ADD COLUMN latest_reading_at DATETIME NULL"
        ))
        # One-off full scan to backfill existing sensors; ties on timestamp go to the highest id.
        conn.execute(text("""
            UPDATE sensors s
            JOIN (
                SELECT t.sensor_id, MAX(t.id) AS id, t.timestamp
                FROM telemetry t
                JOIN (SELECT sensor_id, MAX(timestamp) AS ts FROM telemetry GROUP BY sensor_id) m
                  ON m.sensor_id = t.sensor_id AND m.ts = t.timestamp
                GROUP BY t.sensor_id, t.timestamp
            ) latest ON latest.sensor_id = s.sensor_id
            SET s.latest_telemetry_id = latest.id, s.latest_reading_at = latest.timestamp
        """))
    return True


MIGRATIONS = [_add_latest_reading_pointer]


def upgrade(engine: Engine) -> list[str]:
    """Apply every pending migration; return the names of the ones that ran."""
    applied = []
    for migration in MIGRATIONS:
        if migration(engine):
            logger.info("Applied migration: %s", migration.__doc__.strip().splitlines()[0])
            applied.append(migration.__name__)
    return applied
