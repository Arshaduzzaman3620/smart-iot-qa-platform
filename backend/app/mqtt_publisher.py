"""The API's one MQTT connection, used to send commands to sensors. No HTTP or database code here."""

import logging
import os
import uuid

import paho.mqtt.client as mqtt

logger = logging.getLogger("backend.mqtt")

PUBLISH_TIMEOUT = 3  # seconds to wait for the broker's PUBACK


class CommandPublisher:
    def __init__(self, host: str, port: int):
        # Unique client ID: two API instances with the same ID would keep kicking each other off.
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"api-{uuid.uuid4().hex[:8]}")
        self._client.on_connect = lambda c, u, f, rc, p: logger.info("Connected to MQTT broker %s:%s (%s)", host, port, rc)
        self._client.on_disconnect = lambda c, u, f, rc, p: logger.warning("Disconnected from MQTT broker (%s)", rc)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._host, self._port = host, port

    def start(self):
        # Asynchronous, like the other services: the API starts even while the broker is down.
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str) -> bool:
        """QoS 1 and wait for the broker to accept it. False if the broker is unreachable."""
        if not self._client.is_connected():
            return False
        try:
            info = self._client.publish(topic, payload, qos=1)
            info.wait_for_publish(timeout=PUBLISH_TIMEOUT)
            return info.is_published()
        except (RuntimeError, ValueError) as exc:
            logger.warning("Publish to %s failed: %s", topic, exc)
            return False


def from_env() -> CommandPublisher:
    return CommandPublisher(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")))
