import pytest

SENSOR_FIELDS = {
    "sensor_id", "sensor_type", "name", "location", "status", "firmware_version",
    "battery", "last_seen", "created_at", "updated_at",
}
TELEMETRY_FIELDS = {
    "id", "sensor_id", "timestamp", "temperature", "humidity", "pressure", "light", "battery", "received_at",
}


# ---- GET /sensors -----------------------------------------------------------------------

def test_list_includes_seeded_sensor_with_latest_reading(client, seeded_sensor):
    response = client.get("/sensors")
    assert response.status_code == 200
    sensors = {s["sensor_id"]: s for s in response.json()}
    sensor = sensors[seeded_sensor["sensor_id"]]

    assert set(sensor) == SENSOR_FIELDS | {"latest_telemetry", "active_alerts"}
    assert sensor["active_alerts"] == 0
    assert sensor["status"] == "ONLINE"
    assert sensor["battery"] == 88.0
    latest = seeded_sensor["readings"][-1]
    assert sensor["latest_telemetry"]["temperature"] == latest["temperature"]
    assert sensor["latest_telemetry"]["light"] == latest["light"]


def test_list_is_sorted_by_sensor_id(client, seeded_sensor):
    ids = [s["sensor_id"] for s in client.get("/sensors").json()]
    assert ids == sorted(ids)


def test_list_sensor_without_readings_has_null_latest(client, sensor_id):
    from database.models import Sensor
    from database.session import SessionLocal

    with SessionLocal() as session, session.begin():
        session.add(Sensor(sensor_id=sensor_id))
    try:
        sensors = {s["sensor_id"]: s for s in client.get("/sensors").json()}
        assert sensors[sensor_id]["latest_telemetry"] is None
        assert sensors[sensor_id]["status"] == "OFFLINE"  # DB default
    finally:
        with SessionLocal() as session, session.begin():
            session.query(Sensor).filter_by(sensor_id=sensor_id).delete()


# ---- GET /sensors/{id} ------------------------------------------------------------------

def test_get_sensor(client, seeded_sensor):
    response = client.get(f"/sensors/{seeded_sensor['sensor_id']}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == SENSOR_FIELDS
    assert body["sensor_id"] == seeded_sensor["sensor_id"]
    assert body["last_seen"] == "2026-10-24T12:02:00Z"


@pytest.mark.parametrize("unknown", ["SENSOR-DOES-NOT-EXIST", "' OR '1'='1", "TEST-%", "a" * 300])
def test_get_unknown_sensor_is_404(client, unknown):
    response = client.get(f"/sensors/{unknown}")
    assert response.status_code == 404
    assert response.json() == {"detail": f"Sensor {unknown} not found"}


# ---- GET /sensors/{id}/telemetry --------------------------------------------------------

def test_telemetry_newest_first_with_exact_values(client, seeded_sensor):
    response = client.get(f"/sensors/{seeded_sensor['sensor_id']}/telemetry")
    assert response.status_code == 200
    rows = response.json()
    assert [set(r) for r in rows] == [TELEMETRY_FIELDS] * 3
    expected = list(reversed(seeded_sensor["readings"]))
    for row, reading in zip(rows, expected):
        for field in ("temperature", "humidity", "pressure", "light", "battery"):
            assert row[field] == reading[field], field
    assert [r["timestamp"] for r in rows] == ["2026-10-24T12:02:00Z", "2026-10-24T12:01:00Z", "2026-10-24T12:00:00Z"]


@pytest.mark.parametrize("limit, expected_count", [(1, 1), (2, 2), (3, 3), (1000, 3)])
def test_telemetry_limit(client, seeded_sensor, limit, expected_count):
    response = client.get(f"/sensors/{seeded_sensor['sensor_id']}/telemetry", params={"limit": limit})
    assert response.status_code == 200
    assert len(response.json()) == expected_count


def test_telemetry_limit_one_returns_newest(client, seeded_sensor):
    rows = client.get(f"/sensors/{seeded_sensor['sensor_id']}/telemetry", params={"limit": 1}).json()
    assert rows[0]["timestamp"] == "2026-10-24T12:02:00Z"


@pytest.mark.parametrize("limit", ["0", "1001", "-1", "abc", "1.5", ""])
def test_telemetry_invalid_limit_is_422(client, seeded_sensor, limit):
    response = client.get(f"/sensors/{seeded_sensor['sensor_id']}/telemetry", params={"limit": limit})
    assert response.status_code == 422


def test_telemetry_for_unknown_sensor_is_404(client):
    response = client.get("/sensors/SENSOR-DOES-NOT-EXIST/telemetry")
    assert response.status_code == 404


# ---- read-only surface --------------------------------------------------------------------

@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_not_allowed(client, seeded_sensor, method):
    assert getattr(client, method)("/sensors").status_code == 405
    assert getattr(client, method)(f"/sensors/{seeded_sensor['sensor_id']}").status_code == 405


def test_unknown_route_is_404(client):
    assert client.get("/does-not-exist").status_code == 404
