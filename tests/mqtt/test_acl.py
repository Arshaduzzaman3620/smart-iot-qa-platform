"""The broker's sign-in and topic permissions (docker/mosquitto/acl, Phase 15g). With MQTT 3.1.1 a
denied publish or subscribe is silently dropped, so each test checks what actually gets delivered."""

import queue
import uuid

import paho.mqtt.client as mqtt
import pytest

from helpers import MQTT_HOST, MQTT_PORT, mqtt_client

pytestmark = pytest.mark.usefixtures("broker_available")


def connect(username, password=None):
    """Connected client, or the CONNACK reason if the broker refused it."""
    client = mqtt_client(username=username, password=password)
    result = queue.Queue()
    client.on_connect = lambda c, u, f, rc, p: result.put(rc)
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    rc = result.get(timeout=5)
    if rc != 0:
        client.loop_stop()
        return None, rc
    return client, rc


def listener(topic):
    """A qa client subscribed to `topic` (qa may read everything); returns its message queue."""
    client, _ = connect("qa")
    received, subscribed = queue.Queue(), queue.Queue()
    client.on_message = lambda c, u, m: received.put(m.payload)
    client.on_subscribe = lambda *a: subscribed.put(True)
    client.subscribe(topic, qos=1)
    subscribed.get(timeout=5)
    return client, received


def delivered(publisher, topic) -> bool:
    watcher, received = listener(topic)
    payload = uuid.uuid4().hex.encode()
    publisher.publish(topic, payload, qos=1).wait_for_publish(5)
    try:
        while True:
            if received.get(timeout=1.5) == payload:
                return True
    except queue.Empty:
        return False
    finally:
        watcher.disconnect()


@pytest.fixture
def sid():
    return f"TEST-ACL{uuid.uuid4().hex[:6].upper()}"


@pytest.mark.parametrize("username, password", [(None, None), ("sensor", "wrong"), ("nobody", "x"), ("api", "")])
def test_unknown_or_wrong_credentials_are_refused(username, password):
    client, rc = connect(username, password)
    assert client is None
    assert rc.is_failure


@pytest.mark.parametrize("kind, allowed", [
    ("telemetry", True), ("response", True), ("status", True), ("firmware_status", True),
    ("command", False), ("firmware", False),          # only the API sends these
])
def test_sensor_account_may_only_send_device_topics(sid, kind, allowed):
    sensor, _ = connect("sensor")
    try:
        assert delivered(sensor, f"iot/sensors/{sid}/{kind}") is allowed
    finally:
        sensor.disconnect()


@pytest.mark.parametrize("kind, allowed", [("command", True), ("firmware", True), ("telemetry", False),
                                           ("status", False)])
def test_api_account_may_only_send_commands_and_firmware(sid, kind, allowed):
    api, _ = connect("api")
    try:
        assert delivered(api, f"iot/sensors/{sid}/{kind}") is allowed
    finally:
        api.disconnect()


def test_receiver_account_cannot_publish(sid):
    receiver, _ = connect("receiver")
    try:
        assert not delivered(receiver, f"iot/sensors/{sid}/telemetry")
    finally:
        receiver.disconnect()


def test_sensor_cannot_eavesdrop_on_other_sensors_telemetry(sid):
    spy, _ = connect("sensor")
    seen, subscribed = queue.Queue(), queue.Queue()
    spy.on_message = lambda c, u, m: seen.put(m.payload)
    spy.on_subscribe = lambda *a: subscribed.put(True)
    spy.subscribe("iot/sensors/+/telemetry", qos=1)
    subscribed.get(timeout=5)
    qa, _ = connect("qa")
    qa.publish(f"iot/sensors/{sid}/telemetry", b"secret", qos=1).wait_for_publish(5)
    with pytest.raises(queue.Empty):
        seen.get(timeout=1.5)
    spy.disconnect()
    qa.disconnect()
