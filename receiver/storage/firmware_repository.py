from datetime import timedelta

from sqlalchemy import select, update

from database.models import Firmware, FirmwareUpdate, Sensor
from database.session import SessionLocal
from storage.telemetry_repository import utc_now
from validator.device_message_validator import MESSAGE_MAX_LENGTH

FINAL = ("SUCCEEDED", "FAILED", "TIMED_OUT")
# A report may only move an update forward; a late or replayed "DOWNLOADING" can't undo "INSTALLING".
ORDER = {"REQUESTED": 0, "DOWNLOADING": 1, "VERIFYING": 2, "INSTALLING": 3, "SUCCEEDED": 4, "FAILED": 4}


class FirmwareRepository:
    """Applies firmware progress reported by sensors (Phase 15e). DB logic only -- input already validated."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def progress(self, sensor_id: str, update_id: int, status: str, message: str | None) -> str | None:
        """Apply one report. Returns None if applied, otherwise why it was ignored."""
        with self._session_factory() as session, session.begin():
            row = session.scalar(select(FirmwareUpdate).where(FirmwareUpdate.id == update_id).with_for_update())
            if row is None or row.sensor_id != sensor_id:
                return "no such update for this sensor"
            if row.status in FINAL:
                return f"update already {row.status}"
            if ORDER[status] < ORDER[row.status]:
                return f"would go back from {row.status} to {status}"
            row.status = status
            if status in ("SUCCEEDED", "FAILED"):
                row.completed_at = utc_now()
            if status == "FAILED":
                row.error_message = message[:MESSAGE_MAX_LENGTH] if message else "failed"
            if status == "SUCCEEDED":
                # The retained status after the reboot says the same; this makes it immediate.
                version = session.scalar(select(Firmware.version).where(Firmware.id == row.firmware_id))
                session.execute(update(Sensor).where(Sensor.sensor_id == sensor_id).values(firmware_version=version))
            return None

    def expire(self, timeout_seconds: float) -> int:
        """Updates with no progress for `timeout_seconds` become TIMED_OUT. Returns how many."""
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        with self._session_factory() as session, session.begin():
            return session.execute(
                update(FirmwareUpdate)
                .where(FirmwareUpdate.status.not_in(FINAL), FirmwareUpdate.updated_at < cutoff)
                .values(status="TIMED_OUT", error_message=f"No progress for {timeout_seconds:g} s",
                        completed_at=utc_now())
            ).rowcount
