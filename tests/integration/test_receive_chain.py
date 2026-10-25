"""Broker -> real receiver process -> MySQL. Every test uses its own TEST-* sensor ID."""

from datetime import datetime

import pytest
from sqlalchemy import func, select

from database.models import Sensor, Telemetry
from database.session import SessionLocal
from helpers import valid_telemetry, wait_until

pytestmark = pytest.mark.usefixtures("receiver_process")

READING_FIELDS = ("temperature", "humidity", "pressure", "light", "battery")


def telemetry_rows(sensor_id: str) -> list[Telemetry]:
    with SessionLocal() as session:
        return session.scalars(select(Telemetry).where(Telemetry.sensor_id == sensor_id).order_by(Telemetry.id)).all()


def get_sensor(sensor_id: str) -> Sensor | None:
    with SessionLocal() as session:
        return session.scalar(select(Sensor).where(Sensor.sensor_id == sensor_id))


def wait_for_log(receiver_process, text: str, timeout: float = 10):
    wait_until(lambda: text in receiver_process(), timeout=timeout)


def test_valid_message_is_stored_with_exact_values(mqtt_publisher, sensor_id):
    message = valid_telemetry(sensor_id, temperature=-12.34, humidity=99.99, pressure=300.01,
                              light=99999.99, battery=0.01, timestamp="2026-10-24T21:15:30+09:00")
    mqtt_publisher(sensor_id, message)

    rows = wait_until(lambda: telemetry_rows(sensor_id))
    assert len(rows) == 1
    row = rows[0]
    for field in READING_FIELDS:
        assert getattr(row, field) == message[field], field
    assert row.timestamp == datetime(2026, 10, 24, 12, 15, 30)  # converted to UTC
    assert row.received_at is not None


def test_fractional_seconds_are_truncated_not_rounded(mqtt_publisher, sensor_id):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:00.6Z"))
    [row] = wait_until(lambda: telemetry_rows(sensor_id))
    assert row.timestamp == datetime(2026, 10, 24, 12, 0, 0)  # MySQL alone would store 12:00:01


def test_first_message_auto_registers_sensor_online(mqtt_publisher, sensor_id):
    assert get_sensor(sensor_id) is None
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, battery=42.5))

    sensor = wait_until(lambda: get_sensor(sensor_id))
    assert sensor.status == "ONLINE"
    assert sensor.battery == 42.5
    assert sensor.last_seen is not None
    assert sensor.sensor_type == "ENVIRONMENT"


def test_later_messages_update_sensor_state_and_append_telemetry(mqtt_publisher, sensor_id):
    for battery in (80.0, 79.5, 79.0):
        mqtt_publisher(sensor_id, valid_telemetry(sensor_id, battery=battery))

    wait_until(lambda: len(telemetry_rows(sensor_id)) == 3)
    assert get_sensor(sensor_id).battery == 79.0
    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(Sensor).where(Sensor.sensor_id == sensor_id))
    assert count == 1  # upsert, not duplicate rows


@pytest.mark.parametrize(
    "payload, reason",
    [
        (b"{not json", "not valid JSON"),
        (b"\xff\xfe", "not valid UTF-8"),
        (b"[1, 2]", "must be an object"),
        ("OUT_OF_RANGE", "out of range"),
        ("WRONG_TYPE", "must be a number"),
        ("MISSING_FIELD", "missing required field: battery"),
        ("BAD_TIMESTAMP", "is not ISO 8601"),
    ],
)
def test_invalid_messages_are_rejected_and_not_stored(receiver_process, mqtt_publisher, sensor_id, payload, reason):
    variants = {
        "OUT_OF_RANGE": valid_telemetry(sensor_id, temperature=85.01),
        "WRONG_TYPE": valid_telemetry(sensor_id, humidity="45"),
        "MISSING_FIELD": {k: v for k, v in valid_telemetry(sensor_id).items() if k != "battery"},
        "BAD_TIMESTAMP": valid_telemetry(sensor_id, timestamp="24/10/2026"),
    }
    mqtt_publisher(sensor_id, variants.get(payload, payload))

    wait_for_log(receiver_process, f"Rejected message on iot/sensors/{sensor_id}/telemetry")
    rejection = next(line for line in receiver_process().splitlines() if f"iot/sensors/{sensor_id}/" in line)
    assert reason in rejection
    assert telemetry_rows(sensor_id) == []
    assert get_sensor(sensor_id) is None


def test_sensor_id_must_match_topic(receiver_process, mqtt_publisher, sensor_id):
    impostor = valid_telemetry(f"{sensor_id}-OTHER")
    mqtt_publisher(f"{sensor_id}-OTHER", impostor, topic_sensor_id=sensor_id)

    wait_for_log(receiver_process, f"does not match topic 'iot/sensors/{sensor_id}/telemetry'")
    assert get_sensor(sensor_id) is None
    assert get_sensor(f"{sensor_id}-OTHER") is None


def test_receiver_keeps_working_after_bad_messages(receiver_process, mqtt_publisher, sensor_id):
    mqtt_publisher(sensor_id, b"garbage")
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, temperature=999))
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id))

    rows = wait_until(lambda: telemetry_rows(sensor_id))
    assert len(rows) == 1
    assert "Traceback" not in receiver_process()


def test_latest_reading_pointer_follows_newest_timestamp(mqtt_publisher, sensor_id):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:00Z", temperature=10.0))
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:05Z", temperature=11.0))
    rows = wait_until(lambda: len(telemetry_rows(sensor_id)) == 2 and telemetry_rows(sensor_id))

    sensor = get_sensor(sensor_id)
    assert sensor.latest_telemetry_id == rows[1].id
    assert sensor.latest_reading_at == datetime(2026, 10, 24, 12, 0, 5)


def test_late_message_does_not_replace_newer_latest_reading(mqtt_publisher, sensor_id):
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:05Z", temperature=11.0))
    # Arrives second but was taken earlier (e.g. delayed in a network buffer).
    mqtt_publisher(sensor_id, valid_telemetry(sensor_id, timestamp="2026-10-24T12:00:00Z", temperature=10.0))
    rows = wait_until(lambda: len(telemetry_rows(sensor_id)) == 2 and telemetry_rows(sensor_id))

    newest = next(r for r in rows if r.temperature == 11.0)
    assert get_sensor(sensor_id).latest_telemetry_id == newest.id  # history keeps both rows


def test_boundary_values_are_accepted_end_to_end(mqtt_publisher, sensor_id):
    minimums = valid_telemetry(sensor_id, temperature=-40, humidity=0, pressure=300, light=0, battery=0)
    maximums = valid_telemetry(sensor_id, temperature=85, humidity=100, pressure=1100, light=100000, battery=100,
                               timestamp="2026-10-24T12:00:01Z")
    mqtt_publisher(sensor_id, minimums)
    mqtt_publisher(sensor_id, maximums)

    rows = wait_until(lambda: len(telemetry_rows(sensor_id)) == 2 and telemetry_rows(sensor_id))
    assert [(r.temperature, r.humidity, r.pressure, r.light, r.battery) for r in rows] == [
        (-40, 0, 300, 0, 0), (85, 100, 1100, 100000, 100)
    ]
