import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.api.commands import get_publisher
from backend.app.main import app
from backend.app.security import create_token
from database.models import Sensor, Telemetry
from database.session import SessionLocal


@pytest.fixture(scope="session")
def headers_for(test_users):
    """headers_for("OPERATOR") -> an Authorization header for that role's test user."""

    def make(role: str) -> dict:
        username, _ = test_users[role]
        return {"Authorization": f"Bearer {create_token(username, role)}"}

    return make


@pytest.fixture(scope="session")
def client(mysql_available, clean_test_rows, headers_for):
    """Signed in as a VIEWER (least privilege); pass headers=headers_for(...) for more."""
    with TestClient(app, headers=headers_for("VIEWER")) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def anon_client(mysql_available):
    """No Authorization header at all."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_sensor(sensor_id):
    """A TEST-* sensor with 3 readings one minute apart; removed afterwards."""
    base = datetime(2026, 10, 24, 12, 0, 0)
    readings = [
        dict(timestamp=base + timedelta(minutes=i), temperature=20.0 + i, humidity=40.0 + i,
             pressure=1000.0 + i, light=99999.99 - i, battery=90.0 - i)
        for i in range(3)
    ]
    with SessionLocal() as session, session.begin():
        sensor = Sensor(sensor_id=sensor_id, status="ONLINE", battery=88.0, last_seen=base + timedelta(minutes=2))
        session.add(sensor)
        session.flush()
        rows = [Telemetry(sensor_id=sensor_id, **r) for r in readings]
        session.add_all(rows)
        session.flush()
        # Same pointer the receiver maintains (see TelemetryRepository.save).
        sensor.latest_telemetry_id, sensor.latest_reading_at = rows[-1].id, rows[-1].timestamp

    yield {"sensor_id": sensor_id, "readings": readings}

    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=sensor_id).delete()


class FakePublisher:
    """Stands in for the API's MQTT connection: records what would be published; `up=False` = broker down."""

    def __init__(self):
        self.sent, self.up = [], True

    def publish(self, topic, payload):
        if self.up:
            self.sent.append((topic, json.loads(payload)))
        return self.up


@pytest.fixture
def broker():
    fake = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_publisher, None)


@pytest.fixture(autouse=True)
def fresh_login_limits():
    """Failed logins in one test must not lock accounts in the next (backend/app/rate_limit.py)."""
    from backend.app.api.auth import forgot_limiter, limiter

    for each in (limiter, forgot_limiter):
        each.reset()
    yield
    for each in (limiter, forgot_limiter):
        each.reset()
