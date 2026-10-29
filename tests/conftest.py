"""Shared test setup.

Layers are selected by folder (tests/unit, tests/api, ...) and each folder gets the matching
marker automatically, so `pytest -m unit` or `pytest tests/unit` both work.

Tests that need MySQL or the broker skip (with a reason) when those aren't running. Set
REQUIRE_SERVICES=1 to turn those skips into failures, e.g. in CI.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Repo root for `database` / `backend`; service folders for their top-level packages
# (receiver: parser, validator, storage; simulator: generator, sensors). Both services also
# have `config` and `mqtt` packages, so tests must not import those from the simulator.
for path in (ROOT, ROOT / "receiver", ROOT / "sensor-simulator"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from database import config as db_config  # noqa: E402  (also loads the repo-root .env)
from helpers import MQTT_HOST, MQTT_PORT, TEST_PREFIX, port_open  # noqa: E402

# Shared fixtures, registered once so session fixtures (e.g. the receiver process) are never duplicated.
pytest_plugins = ["stack_fixtures", "browser_servers"]

LAYERS = ("unit", "api", "mqtt", "integration", "ui", "e2e")


def pytest_collection_modifyitems(config, items):
    for item in items:
        layer = Path(item.fspath).relative_to(ROOT / "tests").parts[0]
        if layer in LAYERS:
            item.add_marker(layer)


def _require(name: str, host: str, port: int):
    if port_open(host, port):
        return
    message = f"{name} not reachable at {host}:{port} (start it with: docker compose up -d mqtt mysql)"
    if os.getenv("REQUIRE_SERVICES") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def mysql_available():
    _require("MySQL", db_config.MYSQL_HOST, db_config.MYSQL_PORT)


@pytest.fixture(scope="session")
def broker_available():
    _require("MQTT broker", MQTT_HOST, MQTT_PORT)


@pytest.fixture
def sensor_id() -> str:
    """A unique sensor ID per test, so tests never collide with each other or with real sensors."""
    return f"{TEST_PREFIX}{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture(scope="session")
def clean_test_rows(mysql_available):
    """Delete every TEST-* sensor (telemetry/alerts cascade) before and after the session."""
    from sqlalchemy import delete

    from database.models import Sensor
    from database.session import SessionLocal

    def purge():
        with SessionLocal() as session, session.begin():
            session.execute(delete(Sensor).where(Sensor.sensor_id.like(f"{TEST_PREFIX}%")))

    purge()
    yield
    purge()

