from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from database.models import Sensor, Telemetry
from database.session import SessionLocal


@pytest.fixture(scope="session")
def client(mysql_available, clean_test_rows):
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
        session.add(Sensor(sensor_id=sensor_id, status="ONLINE", battery=88.0, last_seen=base + timedelta(minutes=2)))
        session.flush()
        session.add_all(Telemetry(sensor_id=sensor_id, **r) for r in readings)

    yield {"sensor_id": sensor_id, "readings": readings}

    with SessionLocal() as session, session.begin():
        session.query(Sensor).filter_by(sensor_id=sensor_id).delete()
