from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["VIEWER", "OPERATOR", "ADMIN"]


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
    active_alerts: int = 0


class AlertOut(_UTCModel):
    id: int
    sensor_id: str
    # LOW_BATTERY / HIGH_TEMPERATURE / LOW_TEMPERATURE / HIGH_HUMIDITY / OFFLINE
    alert_type: str
    severity: str  # WARNING / CRITICAL
    value: float | None
    message: str | None
    status: str  # ACTIVE / RESOLVED
    created_at: datetime
    resolved_at: datetime | None


class HealthOut(BaseModel):
    status: str
    database: str


# ---- auth and users (Phase 15c) -------------------------------------------------------------

class _StrictIn(BaseModel):
    # Unknown fields are an error, not silently ignored (a typo like "rol" must not pass).
    model_config = ConfigDict(extra="forbid")


class LoginIn(_StrictIn):
    # Loose on purpose: login must not reveal the password policy.
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserOut(_UTCModel):
    username: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut


class UserCreateIn(_StrictIn):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Role = "VIEWER"


def _clean_text(value: str | None) -> str | None:
    """Trim; empty means "clear it"; control characters are rejected."""
    if value is None:
        return None
    value = value.strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("must not contain control characters")
    return value or None


class SensorUpdateIn(_StrictIn):
    """PATCH /sensors/{id}: only the fields that are sent are changed."""

    name: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)

    @field_validator("name", "location")
    @classmethod
    def _clean(cls, value):
        return _clean_text(value)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.model_fields_set:
            raise ValueError("send at least one of: name, location")
        return self
