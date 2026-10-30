"""POST/GET sensor commands (Phase 15d). MQTT is replaced by a fake publisher, so every test can
check exactly what would have been published, and can simulate the broker being down."""

import pytest

from database.models import Command
from database.session import SessionLocal

COMMAND_FIELDS = {"id", "sensor_id", "command", "params", "status", "message", "requested_by", "created_at",
                  "completed_at"}


@pytest.fixture
def operator(headers_for):
    return headers_for("OPERATOR")


def send(client, sensor_id, headers, **body):
    return client.post(f"/sensors/{sensor_id}/commands", headers=headers, json=body)


# ---- sending -------------------------------------------------------------------------------

@pytest.mark.parametrize("body, params", [
    ({"command": "REQUEST_TELEMETRY"}, {}),
    ({"command": "RESTART"}, {}),
    ({"command": "SET_INTERVAL", "interval": 10}, {"interval": 10}),
])
def test_command_is_stored_and_published(client, broker, operator, seeded_sensor, body, params):
    sid = seeded_sensor["sensor_id"]
    response = send(client, sid, operator, **body)
    assert response.status_code == 202
    command = response.json()
    assert set(command) == COMMAND_FIELDS
    assert command["status"] == "SENT" and command["params"] == params
    assert command["requested_by"] == "test-operator"
    assert command["created_at"].endswith("Z") and command["completed_at"] is None

    (topic, payload), = broker.sent
    assert topic == f"iot/sensors/{sid}/command"
    assert payload == {"command_id": command["id"], "command": body["command"], "params": params,
                       "issued_at": command["created_at"]}


@pytest.mark.parametrize("interval", [1, 3600])
def test_interval_boundaries_accepted(client, broker, operator, seeded_sensor, interval):
    assert send(client, seeded_sensor["sensor_id"], operator, command="SET_INTERVAL",
                interval=interval).status_code == 202


@pytest.mark.parametrize("body", [
    {}, {"command": "FORMAT_DISK"}, {"command": "restart"}, {"command": None},
    {"command": "SET_INTERVAL"}, {"command": "SET_INTERVAL", "interval": 0},
    {"command": "SET_INTERVAL", "interval": 3601}, {"command": "SET_INTERVAL", "interval": -1},
    {"command": "SET_INTERVAL", "interval": 2.5}, {"command": "SET_INTERVAL", "interval": "10"},
    {"command": "SET_INTERVAL", "interval": True},
    {"command": "RESTART", "interval": 5}, {"command": "RESTART", "params": {}}, {"command": "RESTART", "force": 1},
])
def test_invalid_command_is_422_and_nothing_is_published(client, broker, operator, seeded_sensor, body):
    assert send(client, seeded_sensor["sensor_id"], operator, **body).status_code == 422
    assert broker.sent == []


def test_unknown_sensor_is_404(client, broker, operator):
    assert send(client, "TEST-NOPE", operator, command="RESTART").status_code == 404
    assert broker.sent == []


def test_viewer_cannot_send_commands(client, broker, seeded_sensor):
    response = send(client, seeded_sensor["sensor_id"], {}, command="RESTART")  # default client is a VIEWER
    assert response.status_code == 403
    assert broker.sent == []


def test_anonymous_cannot_send_commands(anon_client, broker, seeded_sensor):
    assert send(anon_client, seeded_sensor["sensor_id"], {}, command="RESTART").status_code == 401


def test_broker_down_is_503_and_recorded_as_failed(client, broker, operator, seeded_sensor):
    broker.up = False
    sid = seeded_sensor["sensor_id"]
    response = send(client, sid, operator, command="RESTART")
    assert response.status_code == 503
    assert response.json() == {"detail": "MQTT broker unreachable"}

    (command,) = client.get(f"/sensors/{sid}/commands").json()
    assert command["status"] == "FAILED"
    assert command["message"] == "MQTT broker unreachable"
    assert command["completed_at"] is not None


# ---- reading -------------------------------------------------------------------------------

def test_history_is_newest_first_and_limited(client, broker, operator, seeded_sensor):
    sid = seeded_sensor["sensor_id"]
    ids = [send(client, sid, operator, command="REQUEST_TELEMETRY").json()["id"] for _ in range(3)]
    history = client.get(f"/sensors/{sid}/commands").json()
    assert [c["id"] for c in history] == ids[::-1]
    assert len(client.get(f"/sensors/{sid}/commands?limit=2").json()) == 2


@pytest.mark.parametrize("limit", ["0", "1001", "x"])
def test_history_limit_validated(client, seeded_sensor, limit):
    assert client.get(f"/sensors/{seeded_sensor['sensor_id']}/commands?limit={limit}").status_code == 422


def test_history_of_unknown_sensor_is_404(client):
    assert client.get("/sensors/TEST-NOPE/commands").status_code == 404


def test_get_one_command_reflects_the_outcome(client, broker, operator, seeded_sensor):
    command_id = send(client, seeded_sensor["sensor_id"], operator, command="RESTART").json()["id"]
    with SessionLocal() as session, session.begin():  # what the receiver does with the sensor's answer
        session.get(Command, command_id).status = "SUCCEEDED"
    assert client.get(f"/commands/{command_id}").json()["status"] == "SUCCEEDED"


def test_unknown_command_id_is_404(client):
    assert client.get("/commands/999999999").status_code == 404
    assert client.get("/commands/abc").status_code == 422


def test_commands_are_deleted_with_their_sensor(client, broker, operator, seeded_sensor):
    command_id = send(client, seeded_sensor["sensor_id"], operator, command="RESTART").json()["id"]
    from database.models import Sensor
    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=seeded_sensor["sensor_id"]).delete()
    assert client.get(f"/commands/{command_id}").status_code == 404
