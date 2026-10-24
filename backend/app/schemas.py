from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

# Response models only -- the API is read-only at this phase.


class _UTCModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def _mark_utc(cls, value):
        # MySQL DATETIMEs come back naive but are stored as UTC; label them so JSON ends in "Z".
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class SensorOut(_UTCModel):
    sensor_id: str
    sensor_type: str
    name: str | None
    location: str | None
    status: str
    firmware_version: str | None
    battery: float | None
    last_seen: datetime | None
    created_at: datetime
    updated_at: datetime


class TelemetryOut(_UTCModel):
    id: int
    sensor_id: str
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float
    light: float
    battery: float
    received_at: datetime


class SensorWithLatestOut(SensorOut):
    """List view for the dashboard: sensor state plus its most recent reading (None if it has none yet)."""

    latest_telemetry: TelemetryOut | None = None


class HealthOut(BaseModel):
    status: str
    database: str
