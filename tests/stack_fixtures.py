"""Session fixtures for tests that need the running pipeline: the real receiver process and an MQTT publisher."""

import json
import os
import subprocess
import sys
import uuid

import paho.mqtt.client as mqtt
import pytest

from helpers import MQTT_HOST, MQTT_PORT, ROOT, wait_until


@pytest.fixture(scope="session")
def receiver_process(broker_available, mysql_available, clean_test_rows, tmp_path_factory):
    """Run the real receiver (receiver/main.py) as a separate process for the whole session.

    Stop any receiver you started by hand first, otherwise every test message is stored twice.
    """
    log_path = tmp_path_factory.mktemp("receiver") / "receiver.log"
    log_file = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=ROOT / "receiver",
        stdout=log_file,
        stderr=subprocess.STDOUT,
        # Check for silent sensors every second from the start; the 30 s timeout itself stays the default.
        # Commands and firmware updates time out after 3 s instead of 30 / 300, so timeout tests are quick.
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "OFFLINE_CHECK_INTERVAL": "1", "OFFLINE_STARTUP_GRACE": "0",
             "COMMAND_TIMEOUT": "3", "FOTA_TIMEOUT": "3"},
    )

    def log() -> str:
        return log_path.read_text(encoding="utf-8")

    try:
        wait_until(lambda: "Subscribed to iot/sensors/+/telemetry" in log(), timeout=15)
    except AssertionError:
        process.kill()
        pytest.fail(f"receiver did not start:\n{log()}")

    yield log

    process.terminate()
    process.wait(timeout=10)
    log_file.close()


@pytest.fixture(scope="session")
def mqtt_publisher(broker_available):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pytest-pub-{uuid.uuid4().hex[:8]}")
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()

    def publish(sensor_id: str, payload, topic_sensor_id: str | None = None, kind: str = "telemetry"):
        topic = f"iot/sensors/{topic_sensor_id or sensor_id}/{kind}"
        body = payload if isinstance(payload, bytes) else json.dumps(payload)
        client.publish(topic, body, qos=1).wait_for_publish(timeout=5)

    yield publish
    client.loop_stop()
    client.disconnect()
