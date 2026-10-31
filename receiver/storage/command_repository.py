from datetime import timedelta

from sqlalchemy import func, update
from sqlalchemy.dialects.mysql import insert

from database.models import Command, Sensor
from database.session import SessionLocal
from storage.telemetry_repository import utc_now
from validator.device_message_validator import MESSAGE_MAX_LENGTH


class CommandRepository:
    """Records command outcomes and sensor self-descriptions. DB logic only -- input already validated."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def complete(self, sensor_id: str, command_id: int, status: str, message: str | None) -> bool:
        """Apply a sensor's response. False if there is no such SENT command *for this sensor*:
        unknown, already finished (a duplicate or a late answer after TIMED_OUT), or another sensor's."""
        with self._session_factory() as session, session.begin():
            return session.execute(
                update(Command)
                .where(Command.id == command_id, Command.sensor_id == sensor_id, Command.status == "SENT")
                .values(status=status, message=message[:MESSAGE_MAX_LENGTH] if message else None,
                        completed_at=utc_now())
            ).rowcount == 1

    def expire(self, timeout_seconds: float) -> int:
        """Mark commands still SENT after `timeout_seconds` as TIMED_OUT. Returns how many."""
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        with self._session_factory() as session, session.begin():
            return session.execute(
                update(Command)
                .where(Command.status == "SENT", Command.created_at < cutoff)
                .values(status="TIMED_OUT", message=f"No response within {timeout_seconds:g} s",
                        completed_at=utc_now())
            ).rowcount

    def save_status(self, sensor_id: str, data: dict):
        """Store what the sensor reports about itself. Firmware and type always follow the device;
        name and location only fill empty fields, so an operator's edit (PATCH /sensors) is kept."""
        firmware, sensor_type = data.get("firmware_version"), data.get("sensor_type")
        values = {"sensor_id": sensor_id, "name": data.get("name"), "location": data.get("location"),
                  "firmware_version": firmware}
        if sensor_type:
            values["sensor_type"] = sensor_type
        upsert = insert(Sensor).values(**values)
        changes = {
            "name": func.coalesce(Sensor.name, upsert.inserted.name),
            "location": func.coalesce(Sensor.location, upsert.inserted.location),
        }
        if firmware is not None:
            changes["firmware_version"] = upsert.inserted.firmware_version
        if sensor_type:
            changes["sensor_type"] = upsert.inserted.sensor_type
        with self._session_factory() as session, session.begin():
            # A sensor that has announced itself but not yet sent a reading stays OFFLINE (the default).
            session.execute(upsert.on_duplicate_key_update(**changes))

