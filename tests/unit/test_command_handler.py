"""The simulator's command parsing (sensor-simulator/commands) and the receiver's checks on what
sensors send back (receiver/validator/device_message_validator.py)."""

import json

import pytest

from commands.command_handler import MAX_INTERVAL, MIN_INTERVAL, CommandError, parse_command, response
from validator.device_message_validator import validate_response, validate_status


def raw(**fields) -> bytes:
    return json.dumps(fields).encode()


# ---- simulator: parse_command ------------------------------------------------------------------

@pytest.mark.parametrize("name", ["RESTART", "REQUEST_TELEMETRY"])
def test_commands_without_params(name):
    command = parse_command(raw(command_id=7, command=name, params={}))
    assert (command.command_id, command.name, command.params) == (7, name, {})


def test_params_may_be_omitted():
    assert parse_command(raw(command_id=1, command="RESTART")).params == {}


@pytest.mark.parametrize("interval", [MIN_INTERVAL, 10, MAX_INTERVAL])
def test_set_interval_boundaries_accepted(interval):
    assert parse_command(raw(command_id=1, command="SET_INTERVAL", params={"interval": interval})).params == {
        "interval": interval}


@pytest.mark.parametrize("interval", [MIN_INTERVAL - 1, MAX_INTERVAL + 1, -5, 2.5, "10", None, True])
def test_set_interval_out_of_range_or_wrong_type(interval):
    with pytest.raises(CommandError) as exc:
        parse_command(raw(command_id=3, command="SET_INTERVAL", params={"interval": interval}))
    assert exc.value.command_id == 3  # the sensor can still answer FAILED


def test_set_interval_extra_params_are_dropped():
    command = parse_command(raw(command_id=1, command="SET_INTERVAL", params={"interval": 5, "x": 1}))
    assert command.params == {"interval": 5}


def test_unknown_command_keeps_its_id_for_the_answer():
    with pytest.raises(CommandError) as exc:
        parse_command(raw(command_id=9, command="SELF_DESTRUCT"))
    assert exc.value.command_id == 9
    assert "unknown command" in str(exc.value)


def test_params_on_a_command_that_takes_none():
    with pytest.raises(CommandError, match="takes no params"):
        parse_command(raw(command_id=1, command="RESTART", params={"interval": 5}))


@pytest.mark.parametrize("payload", [b"", b"not json", b"\xff\xfe", b"[1,2]", b'"RESTART"', b"null"])
def test_garbage_has_no_id_to_answer(payload):
    with pytest.raises(CommandError) as exc:
        parse_command(payload)
    assert exc.value.command_id is None


@pytest.mark.parametrize("command_id", [None, 0, -1, "5", 1.5, True])
def test_command_id_must_be_a_positive_integer(command_id):
    with pytest.raises(CommandError) as exc:
        parse_command(raw(command_id=command_id, command="RESTART"))
    assert exc.value.command_id is None


def test_response_message_shape():
    assert json.loads(response(4, True, "done")) == {"command_id": 4, "status": "SUCCEEDED", "message": "done"}
    assert json.loads(response(4, False, "no"))["status"] == "FAILED"


def test_simulator_and_receiver_agree_on_responses():
    for ok in (True, False):
        assert validate_response(json.loads(response(1, ok, "x"))) == []


# ---- receiver: validate_response / validate_status -------------------------------------------

@pytest.mark.parametrize("data, error", [
    ({"status": "SUCCEEDED"}, "command_id"),
    ({"command_id": 0, "status": "SUCCEEDED"}, "command_id"),
    ({"command_id": "1", "status": "SUCCEEDED"}, "command_id"),
    ({"command_id": True, "status": "SUCCEEDED"}, "command_id"),
    ({"command_id": 1}, "status"),
    ({"command_id": 1, "status": "TIMED_OUT"}, "status"),  # only the receiver decides a timeout
    ({"command_id": 1, "status": "succeeded"}, "status"),
    ({"command_id": 1, "status": "SUCCEEDED", "message": 5}, "message"),
])
def test_invalid_responses(data, error):
    errors = validate_response(data)
    assert errors and error in errors[0]


def test_response_message_is_optional():
    assert validate_response({"command_id": 1, "status": "FAILED"}) == []


def test_valid_status():
    assert validate_status({"sensor_id": "S", "sensor_type": "ENVIRONMENT", "name": "Room 1", "location": "R1",
                            "firmware_version": "1.0.0", "interval": 5}) == []


@pytest.mark.parametrize("field, value", [
    ("name", "x" * 101), ("location", "x" * 101), ("firmware_version", "1." * 11), ("sensor_type", "x" * 51),
    ("name", 5), ("firmware_version", ["1"]),
])
def test_invalid_status_fields(field, value):
    assert validate_status({field: value})


def test_status_fields_at_column_size_are_accepted():
    assert validate_status({"name": "x" * 100, "location": "x" * 100, "firmware_version": "x" * 20}) == []
