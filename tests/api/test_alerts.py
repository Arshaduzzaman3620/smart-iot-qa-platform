from datetime import datetime, timedelta

import pytest

from database.models import Alert
from database.session import SessionLocal

ALERT_FIELDS = {"id", "sensor_id", "alert_type", "severity", "value", "message", "status", "created_at", "resolved_at"}
BASE = datetime(2026, 10, 24, 12, 0, 0)


@pytest.fixture
def seeded_alerts(seeded_sensor):
    """Three alerts on the seeded sensor, oldest first: resolved LOW_BATTERY, active HIGH_TEMPERATURE, active OFFLINE."""
    sensor_id = seeded_sensor["sensor_id"]
    rows = [
        Alert(sensor_id=sensor_id, alert_type="LOW_BATTERY", severity="WARNING", value=15.0, message="Battery low",
              status="RESOLVED", created_at=BASE, resolved_at=BASE + timedelta(minutes=5)),
        Alert(sensor_id=sensor_id, alert_type="HIGH_TEMPERATURE", severity="CRITICAL", value=72.5,
              message="Temperature high", created_at=BASE + timedelta(minutes=10)),
        Alert(sensor_id=sensor_id, alert_type="OFFLINE", severity="WARNING", value=45, message="No telemetry",
              created_at=BASE + timedelta(minutes=20)),
    ]
    with SessionLocal() as session, session.begin():
        session.add_all(rows)
    return sensor_id


def test_list_alerts_for_sensor_newest_first(client, seeded_alerts):
    response = client.get("/alerts", params={"sensor_id": seeded_alerts})
    assert response.status_code == 200
    body = response.json()
    assert [a["alert_type"] for a in body] == ["OFFLINE", "HIGH_TEMPERATURE", "LOW_BATTERY"]
    assert set(body[0]) == ALERT_FIELDS


def test_alert_fields_and_utc_timestamps(client, seeded_alerts):
    resolved = client.get("/alerts", params={"sensor_id": seeded_alerts, "status": "RESOLVED"}).json()
    assert len(resolved) == 1
    alert = resolved[0]
    assert (alert["severity"], alert["value"], alert["message"]) == ("WARNING", 15.0, "Battery low")
    assert alert["created_at"] == "2026-10-24T12:00:00Z"
    assert alert["resolved_at"] == "2026-10-24T12:05:00Z"


def test_filter_active(client, seeded_alerts):
    active = client.get("/alerts", params={"sensor_id": seeded_alerts, "status": "ACTIVE"}).json()
    assert [a["alert_type"] for a in active] == ["OFFLINE", "HIGH_TEMPERATURE"]
    assert all(a["resolved_at"] is None for a in active)


def test_unfiltered_list_contains_seeded_alerts(client, seeded_alerts):
    ids = {a["sensor_id"] for a in client.get("/alerts", params={"limit": 1000}).json()}
    assert seeded_alerts in ids


def test_limit(client, seeded_alerts):
    body = client.get("/alerts", params={"sensor_id": seeded_alerts, "limit": 1}).json()
    assert [a["alert_type"] for a in body] == ["OFFLINE"]


@pytest.mark.parametrize("params", [
    {"status": "OPEN"}, {"status": "active"}, {"status": ""},
    {"limit": 0}, {"limit": 1001}, {"limit": "abc"},
])
def test_invalid_query_parameters_are_422(client, params):
    assert client.get("/alerts", params=params).status_code == 422


def test_unknown_sensor_filter_returns_empty_list(client):
    response = client.get("/alerts", params={"sensor_id": "NO-SUCH-SENSOR"})
    assert response.status_code == 200
    assert response.json() == []


def test_sensor_alerts_endpoint(client, seeded_alerts):
    body = client.get(f"/sensors/{seeded_alerts}/alerts", params={"status": "ACTIVE"}).json()
    assert [a["alert_type"] for a in body] == ["OFFLINE", "HIGH_TEMPERATURE"]


def test_sensor_alerts_unknown_sensor_is_404(client):
    response = client.get("/sensors/NO-SUCH-SENSOR/alerts")
    assert response.status_code == 404
    assert response.json() == {"detail": "Sensor NO-SUCH-SENSOR not found"}


def test_sensor_list_counts_only_active_alerts(client, seeded_alerts):
    sensors = {s["sensor_id"]: s for s in client.get("/sensors").json()}
    assert sensors[seeded_alerts]["active_alerts"] == 2


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_alerts_are_read_only(client, method):
    assert getattr(client, method)("/alerts").status_code == 405
