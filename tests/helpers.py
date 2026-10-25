"""Plain helpers and constants shared by test modules (fixtures live in conftest.py)."""

import os
import socket
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read after conftest has loaded the repo-root .env (database.config does that on import).
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TEST_PREFIX = "TEST-"


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
