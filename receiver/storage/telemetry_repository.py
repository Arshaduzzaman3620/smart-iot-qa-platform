from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.mysql import insert

from alerts.alert_service import OFFLINE, AlertChange, AlertService
from database.models import Alert, Sensor, Telemetry
from database.session import SessionLocal


# MySQL DATETIME has whole seconds and *rounds* any fraction it is given (12:00:00.6 -> 12:00:01),
# which can put a stored time up to 0.5 s in the future. Truncate before writing instead.


def utc_now() -> datetime:
    """Current UTC time, naive, whole seconds -- what a DATETIME column stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _to_utc_naive(timestamp: str) -> datetime:
    """ISO 8601 string -> naive UTC datetime, whole seconds (MySQL DATETIME has no timezone). Naive input is taken as UTC."""
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


@dataclass
class SaveResult:
    telemetry_id: int
    alert_changes: list[AlertChange] = field(default_factory=list)


class TelemetryRepository:
    """Persists validated telemetry. DB logic only -- expects data already parsed and validated."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def save(self, data: dict) -> SaveResult:
        return self.save_batch([data])[0]

    def save_batch(self, batch: list[dict]) -> list[SaveResult]:
        """Store several messages in one transaction: all or nothing, results in input order.

        The commit (with its disk flushes) is most of the cost of a save, so sharing one commit
        across a batch is what lets the receiver keep up under load. Messages are applied in order,
        so a sensor's readings and alerts end up exactly as if they had been saved one by one.
        """
        with self._session_factory() as session, session.begin():
            return [self._save_one(session, data) for data in batch]

    def _save_one(self, session, data: dict) -> SaveResult:
        """Upsert the sensor's state, append one telemetry row, advance the sensor's latest-reading
        pointer, and raise / escalate / resolve its alerts."""
        now = utc_now()

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

        session.execute(upsert)
        session.add(telemetry)
        session.flush()
        # Move the sensor's latest-reading pointer forward -- never back, so a delayed
        # (out-of-order) message can't replace a newer reading on the dashboard.
        advanced = session.execute(
            update(Sensor)
            .where(Sensor.sensor_id == data["sensor_id"])
            .where(or_(Sensor.latest_reading_at.is_(None), Sensor.latest_reading_at <= telemetry.timestamp))
            .values(latest_telemetry_id=telemetry.id, latest_reading_at=telemetry.timestamp)
        ).rowcount == 1
        changes = self._update_alerts(session, data, advanced, now)
        return SaveResult(telemetry.id, changes)

    @staticmethod
    def _update_alerts(session, data: dict, advanced: bool, now: datetime) -> list[AlertChange]:
        # The upsert above holds this sensor's row lock until commit, so concurrent saves for the
        # same sensor are serialized here and can't both raise the same alert. Within a batch, this
        # query autoflushes earlier messages' alert changes first, so it sees them too.
        active = {
            alert.alert_type: alert
            for alert in session.scalars(
                select(Alert).where(Alert.sensor_id == data["sensor_id"], Alert.status == "ACTIVE")
            )
        }

        # Any message, even a late one, proves the sensor is back.
        changes = [AlertChange("RESOLVE", OFFLINE)] if OFFLINE in active else []
        # Thresholds are judged on the newest reading only; a delayed older reading must not
        # raise or resolve anything.
        if advanced:
            changes += AlertService.evaluate(
                data, {alert_type: a.severity for alert_type, a in active.items() if alert_type != OFFLINE}
            )

        for change in changes:
            if change.action == "RAISE":
                session.add(Alert(sensor_id=data["sensor_id"], alert_type=change.alert_type,
                                  severity=change.severity, value=change.value, message=change.message))
            elif change.action == "ESCALATE":
                alert = active[change.alert_type]
                alert.severity, alert.value, alert.message = change.severity, change.value, change.message
            else:
                alert = active[change.alert_type]
                alert.status, alert.resolved_at = "RESOLVED", now
        return changes
