import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger("receiver.mqtt_client")


class MQTTSubscriber:
    """Thin wrapper around paho-mqtt: connect, subscribe, reconnect, log. No parsing/validation here."""

    def __init__(self, host: str, port: int, client_id: str = "receiver"):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._host = host
        self._port = port
        self._topics: list[str] = []

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT broker %s:%s", self._host, self._port)
            # Re-issued here (not just once at startup) so subscriptions
            # survive a reconnect after the broker drops and comes back.
            for topic in self._topics:
                client.subscribe(topic)
                logger.info("Subscribed to %s", topic)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)

    def set_message_handler(self, handler):
        self._client.on_message = handler

    def connect(self, topics: list[str]):
        self._topics = topics
        # connect_async + loop_start lets paho retry in the background (via
        # reconnect_delay_set) instead of raising if the broker is unreachable
        # at startup.
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT client stopped cleanly")
