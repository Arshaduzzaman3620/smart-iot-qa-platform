import json
import queue
import threading
import uuid

import paho.mqtt.client as mqtt
import pytest

from helpers import MQTT_HOST, MQTT_PORT

pytestmark = pytest.mark.usefixtures("broker_available")


def make_client(on_message=None) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pytest-{uuid.uuid4().hex[:8]}")
    if on_message:
        client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    return client


@pytest.fixture
def subscriber():
    """Subscribe to a topic filter and collect (topic, payload) pairs in a queue."""
    received: queue.Queue = queue.Queue()
    subscribed = threading.Event()
    client = make_client(lambda c, u, msg: received.put((msg.topic, msg.payload)))
    client.on_subscribe = lambda c, u, mid, reason_codes, props: subscribed.set()

    def subscribe(topic_filter: str):
        result, _ = client.subscribe(topic_filter, qos=1)
        assert result == mqtt.MQTT_ERR_SUCCESS
        # Publishing before the broker acknowledges the subscription would lose the message.
        assert subscribed.wait(timeout=5), "no SUBACK from broker"
        return received

    yield subscribe
    client.loop_stop()
    client.disconnect()


@pytest.fixture
def publisher():
    client = make_client()
    yield client
    client.loop_stop()
    client.disconnect()


def drain(received: queue.Queue, count: int, timeout: float = 5.0) -> list:
    return [received.get(timeout=timeout) for _ in range(count)]


def test_publish_subscribe_roundtrip(subscriber, publisher, sensor_id):
    topic = f"iot/sensors/{sensor_id}/telemetry"
    received = subscriber(topic)
    payload = json.dumps({"sensor_id": sensor_id, "temperature": 21.5})

    publisher.publish(topic, payload, qos=1).wait_for_publish(timeout=5)

    assert drain(received, 1) == [(topic, payload.encode())]


def test_wildcard_receives_every_sensor(subscriber, publisher):
    run = uuid.uuid4().hex[:6].upper()
    received = subscriber("iot/sensors/+/telemetry")
    topics = [f"iot/sensors/TEST-{run}-{i}/telemetry" for i in range(3)]
    for topic in topics:
        publisher.publish(topic, b"{}", qos=1).wait_for_publish(timeout=5)

    got = set()
    while not set(topics) <= got:
        got.add(received.get(timeout=5)[0])  # other live sensors may also publish; ignore them


def test_wildcard_does_not_match_other_topics(subscriber, publisher, sensor_id):
    received = subscriber(f"iot/sensors/{sensor_id}/telemetry")
    publisher.publish(f"iot/sensors/{sensor_id}/commands", b"{}", qos=1).wait_for_publish(timeout=5)
    publisher.publish(f"iot/sensors/{sensor_id}/telemetry/extra", b"{}", qos=1).wait_for_publish(timeout=5)
    with pytest.raises(queue.Empty):
        received.get(timeout=1.5)


def test_messages_arrive_in_order(subscriber, publisher, sensor_id):
    topic = f"iot/sensors/{sensor_id}/telemetry"
    received = subscriber(topic)
    for i in range(20):
        publisher.publish(topic, str(i), qos=1)
    payloads = [p for _, p in drain(received, 20)]
    assert payloads == [str(i).encode() for i in range(20)]


def test_binary_and_empty_payloads_are_delivered_unchanged(subscriber, publisher, sensor_id):
    # The broker passes anything through; rejecting bad payloads is the receiver's job.
    topic = f"iot/sensors/{sensor_id}/telemetry"
    received = subscriber(topic)
    for payload in (b"", b"\xff\xfe", b"{not json"):
        publisher.publish(topic, payload, qos=1).wait_for_publish(timeout=5)
    assert [p for _, p in drain(received, 3)] == [b"", b"\xff\xfe", b"{not json"]
