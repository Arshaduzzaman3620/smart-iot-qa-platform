from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Schema per docs/architecture/database.md. Tables arrive with their features: sensors, telemetry,
# alerts (Phase 8), users (15c).


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
