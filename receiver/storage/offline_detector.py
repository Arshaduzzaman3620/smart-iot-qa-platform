from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update

from alerts.alert_service import OFFLINE, WARNING
from database.models import Alert, Sensor
from database.session import SessionLocal
from storage.telemetry_repository import utc_now


def format_duration(seconds: float) -> str:
    """35842 -> '9 h 57 min': readable in an alert message, where raw seconds are not."""
    seconds = int(seconds)
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7200:
        return f"{seconds // 60} min"
    if seconds < 172800:
        return f"{seconds // 3600} h {seconds % 3600 // 60} min"
    return f"{seconds // 86400} days"


@dataclass
class OfflineSensor:
    sensor_id: str
    silent_seconds: float


class OfflineDetector:
    """Marks ONLINE sensors that have gone quiet as OFFLINE and raises one OFFLINE alert for each.

    Recovery is the other half: the next stored reading sets the sensor ONLINE again and resolves
    the alert (TelemetryRepository.save).
    """

    def __init__(self, timeout_seconds: float, session_factory=SessionLocal):
        self.timeout_seconds = timeout_seconds
        self._session_factory = session_factory

    def sweep(self) -> list[OfflineSensor]:
        now = utc_now()
        cutoff = now - timedelta(seconds=self.timeout_seconds)

        is_stale = (Sensor.status == "ONLINE", Sensor.last_seen < cutoff)
        with self._session_factory() as session, session.begin():
            # Plain (non-locking) read first. A locking read here would scan the whole table and, under
            # REPEATABLE READ, next-key-lock every row and gap -- stalling every receiver write behind
            # it every few seconds (measured: max latency 1 s -> 39 s at 100 sensors). Usually nothing
            # is stale, and then nothing is locked at all.
            candidates = session.scalars(select(Sensor.sensor_id).where(*is_stale)).all()
            if not candidates:
                return []

            # Lock only the candidates, by unique key, and re-check: a reading arriving right now
            # either waits for this transaction (and then sets the sensor ONLINE again) or commits
            # first and drops out of the re-check, so a live sensor is never left OFFLINE.
            stale = session.execute(
                select(Sensor.sensor_id, Sensor.last_seen)
                .where(Sensor.sensor_id.in_(candidates), *is_stale)
                .with_for_update()
            ).all()
            if not stale:
                return []

            ids = [sensor_id for sensor_id, _ in stale]
            session.execute(update(Sensor).where(Sensor.sensor_id.in_(ids)).values(status="OFFLINE"))
            already = set(session.scalars(
                select(Alert.sensor_id).where(
                    Alert.sensor_id.in_(ids), Alert.alert_type == OFFLINE, Alert.status == "ACTIVE"
                )
            ))

            offline = []
            for sensor_id, last_seen in stale:
                silent = (now - last_seen).total_seconds()
                offline.append(OfflineSensor(sensor_id, silent))
                if sensor_id not in already:
                    session.add(Alert(
                        sensor_id=sensor_id, alert_type=OFFLINE, severity=WARNING, value=round(silent),
                        message=f"No telemetry for {format_duration(silent)} (timeout {self.timeout_seconds:g} s)",
                    ))
            return offline
