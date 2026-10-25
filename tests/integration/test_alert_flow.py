"""Alerts raised by the real receiver process: threshold rules, de-duplication, recovery, offline detection."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from database.models import Alert, Sensor, Telemetry
from database.session import SessionLocal
from helpers import valid_telemetry, wait_until

pytestmark = pytest.mark.usefixtures("receiver_process")


def alerts(sensor_id: str) -> list[Alert]:
    with SessionLocal() as session:
        return session.scalars(select(Alert).where(Alert.sensor_id == sensor_id).order_by(Alert.id)).all()


def sensor_status(sensor_id: str) -> str | None:
    with SessionLocal() as session:
        return session.scalar(select(Sensor.status).where(Sensor.sensor_id == sensor_id))


def telemetry_count(sensor_id: str) -> int:
    with SessionLocal() as session:
        return len(session.scalars(select(Telemetry.id).where(Telemetry.sensor_id == sensor_id)).all())


def publish_series(mqtt_publisher, sensor_id: str, *readings: dict):
    """Publish readings one second apart (sensor time) and wait until all are stored."""
    start = telemetry_count(sensor_id)
    for i, reading in enumerate(readings):
        mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp=f"2026-10-24T12:00:{i:02d}Z", **reading))
    wait_until(lambda: telemetry_count(sensor_id) == start + len(readings))


def test_low_battery_raises_one_active_alert(receiver_process, mqtt_publisher, sensor_id):
    publish_series(mqtt_publisher, sensor_id, {"battery": 15.5})

    [alert] = alerts(sensor_id)
    assert (alert.alert_type, alert.severity, alert.status, alert.value) == ("LOW_BATTERY", "WARNING", "ACTIVE", 15.5)
    assert alert.message == "Battery low: 15.5 % (below 20 %)"
    assert alert.resolved_at is None
    wait_until(lambda: f"Alert raised for {sensor_id}: LOW_BATTERY WARNING" in receiver_process())


def test_continuing_breach_keeps_a_single_alert(mqtt_publisher, sensor_id):
    publish_series(mqtt_publisher, sensor_id, {"battery": 19}, {"battery": 18}, {"battery": 17})
    assert len(alerts(sensor_id)) == 1


def test_escalation_updates_the_same_alert(mqtt_publisher, sensor_id):
    publish_series(mqtt_publisher, sensor_id, {"battery": 15}, {"battery": 8})

    [alert] = alerts(sensor_id)
    assert (alert.severity, alert.value) == ("CRITICAL", 8)
    assert alert.message == "Battery low: 8 % (below 10 %)"


def test_recovery_resolves_and_a_new_breach_raises_a_new_alert(receiver_process, mqtt_publisher, sensor_id):
    publish_series(mqtt_publisher, sensor_id, {"temperature": 55}, {"temperature": 49}, {"temperature": 47},
                   {"temperature": 60})

    first, second = alerts(sensor_id)
    # 49 is inside the hysteresis band (clears at 48), 47 resolves it, 60 is a new incident.
    assert (first.status, first.alert_type) == ("RESOLVED", "HIGH_TEMPERATURE")
    assert first.resolved_at is not None
    assert (second.status, second.value) == ("ACTIVE", 60)
    assert f"Alert resolved for {sensor_id}: HIGH_TEMPERATURE" in receiver_process()


def test_late_reading_does_not_raise_or_resolve(mqtt_publisher, sensor_id):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:10Z", battery=50))
    # Taken earlier, delivered later: history keeps it, but it is not the sensor's current state.
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:05Z", battery=5))
    wait_until(lambda: telemetry_count(sensor_id) == 2)
    assert alerts(sensor_id) == []


def seed_sensor(sensor_id: str, last_seen_ago: timedelta, status: str = "ONLINE"):
    # Whole seconds, like the receiver writes: MySQL would round a fraction up.
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    with SessionLocal() as session, session.begin():
        session.add(Sensor(sensor_id=sensor_id, status=status, battery=80.0, last_seen=now - last_seen_ago))


def test_silent_sensor_is_marked_offline_with_one_alert(receiver_process, sensor_id):
    seed_sensor(sensor_id, timedelta(minutes=5))

    wait_until(lambda: sensor_status(sensor_id) == "OFFLINE", timeout=10)
    [alert] = wait_until(lambda: alerts(sensor_id))
    assert (alert.alert_type, alert.severity, alert.status) == ("OFFLINE", "WARNING", "ACTIVE")
    assert 295 <= alert.value <= 320
    assert alert.message == "No telemetry for 5 min (timeout 30 s)"
    assert f"Sensor {sensor_id} marked OFFLINE" in receiver_process()

    time.sleep(2.5)  # two more sweeps (1 s interval in tests): still exactly one alert
    assert len(alerts(sensor_id)) == 1


def test_recently_seen_sensor_stays_online(sensor_id):
    seed_sensor(sensor_id, timedelta(seconds=5))
    time.sleep(2.5)  # two sweeps; the timeout is 30 s
    assert sensor_status(sensor_id) == "ONLINE"
    assert alerts(sensor_id) == []


def test_sensor_that_reports_again_comes_back_online_and_resolves_offline(mqtt_publisher, sensor_id):
    seed_sensor(sensor_id, timedelta(minutes=5))
    wait_until(lambda: sensor_status(sensor_id) == "OFFLINE", timeout=10)

    publish_series(mqtt_publisher, sensor_id, {})

    assert sensor_status(sensor_id) == "ONLINE"
    [alert] = alerts(sensor_id)
    assert (alert.alert_type, alert.status) == ("OFFLINE", "RESOLVED")
    assert alert.resolved_at is not None
