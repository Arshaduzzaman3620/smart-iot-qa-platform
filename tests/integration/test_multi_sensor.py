"""Many sensors publishing at once through the real receiver."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from database.models import Sensor, Telemetry
from database.session import SessionLocal
from helpers import valid_telemetry, wait_until

pytestmark = pytest.mark.usefixtures("receiver_process")

SENSORS = 20
READINGS_EACH = 5


def counts(prefix: str):
    with SessionLocal() as session:
        sensors = session.scalar(select(func.count()).select_from(Sensor).where(Sensor.sensor_id.like(f"{prefix}%")))
        rows = session.execute(
            select(Telemetry.sensor_id, func.count()).where(Telemetry.sensor_id.like(f"{prefix}%"))
            .group_by(Telemetry.sensor_id)
        ).all()
    return sensors, dict(rows)


def test_concurrent_sensors_are_all_stored_without_loss(mqtt_publisher):
    prefix = f"TEST-M{uuid.uuid4().hex[:4].upper()}-"
    ids = [f"{prefix}{i:02d}" for i in range(SENSORS)]

    def publish_all(sensor_id):
        for second in range(READINGS_EACH):
            mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp=f"2026-10-24T12:00:0{second}Z"))

    with ThreadPoolExecutor(max_workers=SENSORS) as pool:
        list(pool.map(publish_all, ids))

    wait_until(lambda: sum(counts(prefix)[1].values()) == SENSORS * READINGS_EACH, timeout=30)
    sensors, per_sensor = counts(prefix)
    assert sensors == SENSORS
    assert per_sensor == {sensor_id: READINGS_EACH for sensor_id in ids}


def test_every_sensor_points_at_its_own_latest_reading(mqtt_publisher):
    prefix = f"TEST-P{uuid.uuid4().hex[:4].upper()}-"
    ids = [f"{prefix}{i:02d}" for i in range(5)]
    for sensor_id in ids:
        mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:00Z"))
        mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:05Z"))
    wait_until(lambda: sum(counts(prefix)[1].values()) == 10)

    with SessionLocal() as session:
        pairs = session.execute(
            select(Sensor.sensor_id, Telemetry.sensor_id, Telemetry.timestamp)
            .join(Telemetry, Telemetry.id == Sensor.latest_telemetry_id)
            .where(Sensor.sensor_id.like(f"{prefix}%"))
        ).all()
    assert len(pairs) == 5
    for sensor_id, telemetry_sensor_id, timestamp in pairs:
        assert telemetry_sensor_id == sensor_id
        assert timestamp.second == 5
