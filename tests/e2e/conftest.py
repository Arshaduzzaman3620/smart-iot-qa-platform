import pytest
from playwright.sync_api import expect

from browser_servers import API_URL, DASHBOARD_URL
from helpers import login_headers


@pytest.fixture
def stack(receiver_process, api_server, dashboard_server, test_users):
    """Broker + receiver + MySQL + API + dashboard all running. Returns the receiver log reader."""
    return receiver_process


@pytest.fixture
def api_headers(stack, test_users):
    """Authorization header for the running API, obtained through the real login endpoint."""
    return login_headers(API_URL, *test_users["VIEWER"])


@pytest.fixture
def open_signed_in(stack, test_users, page):
    """Open the dashboard and sign in through the login form, as a VIEWER."""

    def open_():
        username, password = test_users["VIEWER"]
        page.goto(DASHBOARD_URL)
        page.get_by_test_id("login-username").fill(username)
        page.get_by_test_id("login-password").fill(password)
        page.get_by_test_id("login-submit").click()
        expect(page.get_by_test_id("user-name")).to_have_text(username)
        return page

    return open_


@pytest.fixture
def simulated_sensor(stack, tmp_path):
    """The real simulator running one sensor with a test-only ID (TEST-SIMxxxx-001), slow schedule so
    the test decides when readings happen. Yields (sensor_id, log reader)."""
    import os
    import subprocess
    import sys
    import uuid

    import paho.mqtt.client as mqtt

    from helpers import MQTT_HOST, MQTT_PORT, ROOT, wait_until

    prefix = f"TEST-SIM{uuid.uuid4().hex[:6].upper()}-"
    sensor_id = f"{prefix}001"
    log_path = tmp_path / "simulator.log"
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "SENSOR_COUNT": "1",
           "SENSOR_INTERVAL": "60", "SENSOR_ID_PREFIX": prefix, "RESTART_SECONDS": "1"}
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "main.py"], cwd=ROOT / "sensor-simulator", stdout=log,
                                   stderr=subprocess.STDOUT, env=env)

    def read() -> str:
        return log_path.read_text(encoding="utf-8")

    try:
        wait_until(lambda: "Starting 1 sensor(s)" in read() and f"Telemetry sent: {{'sensor_id': '{sensor_id}'" in read(),
                   timeout=15)
        yield sensor_id, read
    finally:
        process.terminate()
        process.wait(timeout=10)
        # Clear its retained status, so the broker doesn't keep announcing a sensor that is gone.
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()
        client.publish(f"iot/sensors/{sensor_id}/status", b"", qos=1, retain=True).wait_for_publish(5)
        client.loop_stop()
        client.disconnect()


@pytest.fixture
def operator_headers(stack, test_users):
    return login_headers(API_URL, *test_users["OPERATOR"])
