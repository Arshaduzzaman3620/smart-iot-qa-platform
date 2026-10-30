"""The receiver's half of commands (Phase 15d): sensor responses, timeouts and status announcements,
through the real receiver process, broker and MySQL."""

import json
from datetime import timedelta

import pytest

from database.models import Command, Sensor
from database.session import SessionLocal
from helpers import valid_telemetry, wait_until
from storage.telemetry_repository import utc_now


@pytest.fixture
def sensor(receiver_process, sensor_id):
    with SessionLocal() as session, session.begin():
        session.add(Sensor(sensor_id=sensor_id, status="ONLINE"))
    return sensor_id


def make_command(sensor_id, command="RESTART", age_seconds=0, status="SENT") -> int:
    with SessionLocal() as session, session.begin():
        row = Command(sensor_id=sensor_id, command=command, params="{}", status=status, requested_by="test",
                      created_at=utc_now() - timedelta(seconds=age_seconds))
        session.add(row)
        session.flush()
        return row.id


def command(command_id) -> Command:
    with SessionLocal() as session:
        return session.get(Command, command_id)


def sensor_row(sensor_id) -> Sensor | None:
    with SessionLocal() as session:
        return session.query(Sensor).filter_by(sensor_id=sensor_id).one_or_none()


# ---- responses -----------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_response_completes_the_command(sensor, mqtt_publisher, status):
    command_id = make_command(sensor)
    mqtt_publisher(sensor, {"command_id": command_id, "status": status, "message": "done"}, kind="response")
    row = wait_until(lambda: (c := command(command_id)).status != "SENT" and c)
    assert row.status == status
    assert row.message == "done"
    assert row.completed_at is not None


def test_long_message_is_cut_to_the_column_size(sensor, mqtt_publisher):
    command_id = make_command(sensor)
    mqtt_publisher(sensor, {"command_id": command_id, "status": "FAILED", "message": "x" * 400}, kind="response")
    row = wait_until(lambda: (c := command(command_id)).status != "SENT" and c)
    assert row.message == "x" * 255


def test_a_sensor_cannot_answer_another_sensors_command(sensor, mqtt_publisher, receiver_process):
    command_id = make_command(sensor)
    other = f"{sensor}-X"
    mqtt_publisher(other, {"command_id": command_id, "status": "SUCCEEDED"}, kind="response")
    wait_until(lambda: f"Ignored response from {other} for command {command_id}" in receiver_process())
    assert command(command_id).status == "SENT"


def test_duplicate_response_does_not_change_the_outcome(sensor, mqtt_publisher, receiver_process):
    command_id = make_command(sensor)
    mqtt_publisher(sensor, {"command_id": command_id, "status": "SUCCEEDED", "message": "first"}, kind="response")
    wait_until(lambda: command(command_id).status == "SUCCEEDED")
    mqtt_publisher(sensor, {"command_id": command_id, "status": "FAILED", "message": "second"}, kind="response")
    wait_until(lambda: f"Ignored response from {sensor} for command {command_id}" in receiver_process())
    row = command(command_id)
    assert (row.status, row.message) == ("SUCCEEDED", "first")


@pytest.mark.parametrize("payload, reason", [
    ({"command_id": "1", "status": "SUCCEEDED"}, "command_id must be a positive integer"),
    ({"command_id": 1, "status": "TIMED_OUT"}, "status must be one of"),
    (b"not json", "not valid JSON"),
])
def test_invalid_response_is_rejected(sensor, mqtt_publisher, receiver_process, payload, reason):
    mqtt_publisher(sensor, payload, kind="response")
    wait_until(lambda: f"iot/sensors/{sensor}/response" in receiver_process() and reason in receiver_process())


# ---- timeouts --------------------------------------------------------------------------------

def test_unanswered_command_times_out(sensor):
    command_id = make_command(sensor, age_seconds=10)  # receiver under test: COMMAND_TIMEOUT=3
    row = wait_until(lambda: (c := command(command_id)).status == "TIMED_OUT" and c, timeout=10)
    assert row.message == "No response within 3 s"
    assert row.completed_at is not None


def test_recent_command_is_left_waiting(sensor):
    command_id = make_command(sensor, age_seconds=0)
    old_id = make_command(sensor, age_seconds=10)
    wait_until(lambda: command(old_id).status == "TIMED_OUT", timeout=10)
    assert command(command_id).status == "SENT"


def test_late_answer_after_timeout_is_ignored(sensor, mqtt_publisher, receiver_process):
    command_id = make_command(sensor, age_seconds=10)
    wait_until(lambda: command(command_id).status == "TIMED_OUT", timeout=10)
    mqtt_publisher(sensor, {"command_id": command_id, "status": "SUCCEEDED"}, kind="response")
    wait_until(lambda: f"Ignored response from {sensor} for command {command_id}" in receiver_process())
    assert command(command_id).status == "TIMED_OUT"


# ---- status announcements --------------------------------------------------------------------

STATUS = {"sensor_type": "ENVIRONMENT", "name": "Room 9 Sensor", "location": "Room-9", "firmware_version": "1.2.3",
          "interval": 5}


def test_status_registers_an_unknown_sensor_as_offline(receiver_process, sensor_id, mqtt_publisher):
    mqtt_publisher(sensor_id, {"sensor_id": sensor_id, **STATUS}, kind="status")
    row = wait_until(lambda: sensor_row(sensor_id))
    assert (row.name, row.location, row.firmware_version) == ("Room 9 Sensor", "Room-9", "1.2.3")
    assert row.status == "OFFLINE"  # announced, but no reading yet

    mqtt_publisher(sensor_id, valid_telemetry(sensor_id))
    wait_until(lambda: sensor_row(sensor_id).status == "ONLINE")


def test_status_keeps_an_operators_name_but_updates_firmware(sensor, mqtt_publisher):
    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=sensor).update({"name": "Freezer", "firmware_version": "1.0.0"})
    mqtt_publisher(sensor, {"sensor_id": sensor, **STATUS}, kind="status")
    row = wait_until(lambda: (r := sensor_row(sensor)).firmware_version == "1.2.3" and r)
    assert row.name == "Freezer"          # set by an operator: kept
    assert row.location == "Room-9"       # was empty: filled in


@pytest.mark.parametrize("payload, reason", [
    ({"name": "x" * 101}, "name longer than 100"),
    ({"firmware_version": 2}, "firmware_version must be a string"),
    ({"sensor_id": "SOMEONE-ELSE"}, "does not match topic"),
])
def test_invalid_status_is_rejected(sensor, mqtt_publisher, receiver_process, payload, reason):
    mqtt_publisher(sensor, payload, kind="status")
    wait_until(lambda: f"Rejected status on iot/sensors/{sensor}/status" in receiver_process()
               and reason in receiver_process())
    assert sensor_row(sensor).firmware_version is None


def test_telemetry_still_flows_alongside(sensor, mqtt_publisher):
    # Three topic kinds on one subscription set: telemetry must be unaffected.
    mqtt_publisher(sensor, json.dumps(valid_telemetry(sensor)).encode())
    wait_until(lambda: sensor_row(sensor).latest_telemetry_id is not None)
