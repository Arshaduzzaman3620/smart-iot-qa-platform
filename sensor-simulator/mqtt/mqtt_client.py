import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger("mqtt_client")


class MQTTClient:
    """Thin wrapper around paho-mqtt: connect, publish, reconnect, log. No sensor logic here."""

    def __init__(self, host: str, port: int, client_id: str):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._host = host
        self._port = port

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT broker %s:%s", self._host, self._port)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)

    def connect(self):
        # connect_async + loop_start lets paho retry in the background (via
        # reconnect_delay_set) instead of raising if the broker is unreachable
        # at startup.
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def publish(self, topic: str, payload: str) -> bool:
        if not self._client.is_connected():
            logger.warning("Skipping publish to %s: not connected to broker", topic)
            return False
        try:
            result = self._client.publish(topic, payload)
            result.wait_for_publish(timeout=5)
            logger.info("Published to %s", topic)
            return True
        except (RuntimeError, ValueError) as exc:
            logger.warning("Publish to %s failed: %s", topic, exc)
            return False

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT client stopped cleanly")
