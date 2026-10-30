"""Plain helpers and constants shared by test modules (fixtures live in conftest.py)."""

import os
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read after conftest has loaded the repo-root .env (database.config does that on import).
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TEST_PREFIX = "TEST-"
TEST_USER_PREFIX = "test-"
TEST_PASSWORD = "test-password-123"


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def valid_telemetry(sensor_id: str = "SENSOR-001", **overrides) -> dict:
    data = {
        "sensor_id": sensor_id,
        "timestamp": "2026-10-24T12:00:00Z",
        "temperature": 22.5,
        "humidity": 45.0,
        "pressure": 1013.25,
        "light": 350.0,
        "battery": 88.8,
    }
    data.update(overrides)
    return data


def wait_until(condition, timeout: float = 10.0, interval: float = 0.2):
    """Poll `condition()` until it returns something truthy; return that value or raise on timeout."""
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"condition not met within {timeout}s")
        time.sleep(interval)


def login_headers(api_url: str, username: str, password: str) -> dict:
    """Sign in to a running API over HTTP; returns the Authorization header to send."""
    import httpx

    response = httpx.post(f"{api_url}/auth/login", json={"username": username, "password": password}, timeout=10)
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def report(name: str, **metrics):
    """One line of measurements per scenario, shown with `pytest -s` (used by the reliability tests)."""
    print(f"\n[{name}] " + ", ".join(f"{k}={v}" for k, v in metrics.items()))
