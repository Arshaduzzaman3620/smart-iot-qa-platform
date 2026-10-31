import logging
import ssl

import paho.mqtt.client as mqtt

logger = logging.getLogger("receiver.mqtt_client")


def tls_context(ca_file: str) -> ssl.SSLContext:
    """Verify the broker's certificate and host name (TLS 1.2+). "system" = the OS's trusted CAs,
    for a broker with a certificate from a public CA; otherwise the path of our CA (docs/security/tls.md)."""
    context = ssl.create_default_context(cafile=None if ca_file == "system" else ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class MQTTSubscriber:
    """Thin wrapper around paho-mqtt: connect, subscribe, reconnect, log. No parsing/validation here."""

    def __init__(self, host: str, port: int, client_id: str = "receiver", persistent_session: bool = True,
                 username: str | None = None, password: str | None = None, tls_ca: str | None = None):
        # Persistent session (clean_session=False) + QoS 1: while the receiver is down or restarting,
        # the broker queues its messages and delivers them on reconnect, instead of dropping them.
        # manual_ack: a QoS 1 message is acknowledged only when the receiver calls ack(), i.e. after it is
        # stored -- not when the callback returns, when it is merely queued in memory.
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
                                   clean_session=not persistent_session, manual_ack=True)
        if username:
            self._client.username_pw_set(username, password)
        if tls_ca:
            self._client.tls_set_context(tls_context(tls_ca))
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
                client.subscribe(topic, qos=1)
                logger.info("Subscribed to %s", topic)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)

    def ack(self, mid: int, qos: int):
        """Acknowledge a received message. Safe from any thread."""
        if qos > 0:
            self._client.ack(mid, qos)

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
