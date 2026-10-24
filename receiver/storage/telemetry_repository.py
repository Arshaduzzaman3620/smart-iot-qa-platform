from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert

from database.models import Sensor, Telemetry
from database.session import SessionLocal


def _to_utc_naive(timestamp: str) -> datetime:
    """ISO 8601 string -> naive UTC datetime (MySQL DATETIME has no timezone). Naive input is taken as UTC."""
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class TelemetryRepository:
    """Persists validated telemetry. DB logic only -- expects data already parsed and validated."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def save(self, data: dict) -> int:
        """Upsert the sensor's latest state and append one telemetry row, atomically. Returns the telemetry id."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # INSERT ... ON DUPLICATE KEY UPDATE: a first-seen sensor is registered automatically,
        # and concurrent receivers can't race each other into a duplicate-key error.
        upsert = insert(Sensor).values(
            sensor_id=data["sensor_id"], status="ONLINE", battery=data["battery"], last_seen=now
        )
        upsert = upsert.on_duplicate_key_update(
            status=upsert.inserted.status,
            battery=upsert.inserted.battery,
            last_seen=upsert.inserted.last_seen,
            # Core upserts bypass the model's onupdate hook, so bump it explicitly.
            updated_at=func.now(),
        )

        telemetry = Telemetry(
            sensor_id=data["sensor_id"],
            timestamp=_to_utc_naive(data["timestamp"]),
            temperature=data["temperature"],
            humidity=data["humidity"],
            pressure=data["pressure"],
            light=data["light"],
            battery=data["battery"],
        )

        with self._session_factory() as session, session.begin():
            session.execute(upsert)
            session.add(telemetry)
            session.flush()
            return telemetry.id
