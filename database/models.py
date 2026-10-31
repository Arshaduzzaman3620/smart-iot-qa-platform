from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, Index, Integer, LargeBinary, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Schema per docs/architecture/database.md. Tables arrive with their features: sensors, telemetry,
# alerts (Phase 8), users (15c), commands (15d), firmware / firmware_updates (15e).


class Base(DeclarativeBase):
    pass


class Sensor(Base):
    """One row per physical (simulated) sensor, holding its latest known state."""

    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="ENVIRONMENT")
    name: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(100))
    # ONLINE / OFFLINE / ERROR (later CONNECTING / UPDATING) -- see sensor-behavior.md.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OFFLINE")
    firmware_version: Mapped[str | None] = mapped_column(String(20))
    battery: Mapped[float | None] = mapped_column(Double)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    # Pointer to the newest reading (by sensor timestamp), maintained by the receiver. Lets the
    # sensor list fetch every sensor's latest reading by primary key instead of scanning telemetry,
    # which grows by ~1.7M rows/day at 100 sensors. No FK: telemetry already references sensors,
    # and a constraint in both directions would fight the ON DELETE CASCADE.
    latest_telemetry_id: Mapped[int | None] = mapped_column(BigInteger)
    latest_reading_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    telemetry: Mapped[list["Telemetry"]] = relationship(back_populates="sensor")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="sensor")


class Telemetry(Base):
    """One row per accepted (validated) telemetry message. Append-only."""

    __tablename__ = "telemetry"
    __table_args__ = (Index("ix_telemetry_sensor_timestamp", "sensor_id", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sensors.sensor_id", ondelete="CASCADE"), nullable=False
    )
    # When the sensor says it took the reading.
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    temperature: Mapped[float] = mapped_column(Double, nullable=False)
    humidity: Mapped[float] = mapped_column(Double, nullable=False)
    pressure: Mapped[float] = mapped_column(Double, nullable=False)
    light: Mapped[float] = mapped_column(Double, nullable=False)
    battery: Mapped[float] = mapped_column(Double, nullable=False)
    # When the receiver stored it -- the gap to `timestamp` is end-to-end latency.
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    sensor: Mapped[Sensor] = relationship(back_populates="telemetry")


class Alert(Base):
    """A threshold breach or fault raised for a sensor."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_sensor_status", "sensor_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sensors.sensor_id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float | None] = mapped_column(Double)
    message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")

    sensor: Mapped[Sensor] = relationship(back_populates="alerts")


class User(Base):
    """A dashboard / API user. Passwords are stored only as a salted scrypt hash (backend/app/security.py)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # VIEWER < OPERATOR < ADMIN, see docs/api/auth.md.
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="VIEWER")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Phase 19 (docs/api/auth.md): for "forgot username or password". Optional for accounts made earlier.
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    # ACTIVE, or PENDING: signed up and waiting for an admin's approval (cannot sign in yet).
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ACTIVE")
    # Tokens issued before this moment stop working (set when the password is reset or changed).
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PasswordReset(Base):
    """A one-time password reset link (Phase 19). Only the SHA-256 of the token is stored, so a copy of
    the database can't be used to reset anyone's password."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class Command(Base):
    """A command sent to a sensor over MQTT and what became of it.

    SENT (published) -> SUCCEEDED / FAILED (the sensor's response) or TIMED_OUT (no response in
    time). FAILED is also used when the API could not publish it at all.
    """

    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_sensor_created", "sensor_id", "created_at"),
                      Index("ix_commands_status_created", "status", "created_at"))

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sensors.sensor_id", ondelete="CASCADE"), nullable=False
    )
    command: Mapped[str] = mapped_column(String(30), nullable=False)  # RESTART / REQUEST_TELEMETRY / SET_INTERVAL
    params: Mapped[str | None] = mapped_column(String(255))  # JSON, e.g. {"interval": 10}
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SENT")
    message: Mapped[str | None] = mapped_column(String(255))  # the sensor's response, or why it failed
    requested_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Firmware(Base):
    """An uploaded firmware image (simulated). Small, so the bytes live in MySQL; sensors download
    them from the API with a short-lived token (docs/architecture/fota.md)."""

    __tablename__ = "firmware"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(100), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256, hex
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    # MEDIUMBLOB (up to 16 MiB) on MySQL; uploads are capped far below that.
    content: Mapped[bytes] = mapped_column(LargeBinary(length=2**24 - 1), nullable=False, deferred=True)
    uploaded_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class FirmwareUpdate(Base):
    """One firmware update of one sensor: REQUESTED -> DOWNLOADING -> VERIFYING -> INSTALLING ->
    SUCCEEDED, or FAILED / TIMED_OUT at any point."""

    __tablename__ = "firmware_updates"
    __table_args__ = (Index("ix_fw_updates_sensor_started", "sensor_id", "started_at"),
                      Index("ix_fw_updates_status_started", "status", "started_at"))

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sensor_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sensors.sensor_id", ondelete="CASCADE"), nullable=False
    )
    firmware_id: Mapped[int] = mapped_column(ForeignKey("firmware.id", ondelete="RESTRICT"), nullable=False)
    from_version: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="REQUESTED")
    error_message: Mapped[str | None] = mapped_column(String(255))
    requested_by: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(),
                                                 onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    firmware: Mapped[Firmware] = relationship()
