import logging
import ssl
import threading

import paho.mqtt.client as mqtt

logger = logging.getLogger("mqtt_client")


def tls_context(ca_file: str) -> ssl.SSLContext:
    """Verify the broker's certificate and host name (TLS 1.2+). "system" = the OS's trusted CAs,
    for a broker with a certificate from a public CA; otherwise the path of our CA (docs/security/tls.md)."""
    context = ssl.create_default_context(cafile=None if ca_file == "system" else ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


class MQTTClient:
    """Thin wrapper around paho-mqtt: connect, publish, subscribe, reconnect, log. No sensor logic here."""

    def __init__(self, host: str, port: int, client_id: str, username: str | None = None,
                 password: str | None = None, tls_ca: str | None = None):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            self._client.username_pw_set(username, password)
        if tls_ca:
            self._client.tls_set_context(tls_context(tls_ca))
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        # Capped at 10 s: after a long outage a sensor is back within 10 s of the broker (was 30 s).
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        self._host = host
        self._port = port
        self._connected = threading.Event()
        self._subscriptions = {}  # topic -> handler(payload: bytes)
        self._on_connected = None

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT broker %s:%s", self._host, self._port)
            # Re-subscribed on every connect, so commands still arrive after a broker restart.
            for topic in self._subscriptions:
                client.subscribe(topic, qos=1)
            self._connected.set()
            if self._on_connected:
                self._on_connected()
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._connected.clear()
        logger.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        handler = self._subscriptions.get(msg.topic)
        if handler:
            handler(msg.payload)

    def subscribe(self, topic: str, handler):
        """Call `handler(payload: bytes)` for each message on `topic` (exact topic, no wildcards).
        Runs on paho's network thread: keep it short and hand the work off."""
        self._subscriptions[topic] = handler
        if self._client.is_connected():
            self._client.subscribe(topic, qos=1)

    def on_connected(self, callback):
        """`callback()` after every successful (re)connect, on paho's network thread. Use publish_nowait there."""
        self._on_connected = callback

    def connect(self):
        # connect_async + loop_start lets paho retry in the background (via
        # reconnect_delay_set) instead of raising if the broker is unreachable
        # at startup.
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def is_connected(self) -> bool:
        return self._client.is_connected()

    def wait_until_connected(self, timeout: float) -> bool:
        """Block until the first connection succeeds or `timeout` seconds pass. Returns True if connected."""
        return self._connected.wait(timeout)

    def publish(self, topic: str, payload: str | bytes, qos: int = 0) -> bool:
        """True only once the broker has it (for QoS 1: its PUBACK arrived)."""
        if not self._client.is_connected():
            logger.debug("Skipping publish to %s: not connected to broker", topic)
            return False
        try:
            result = self._client.publish(topic, payload, qos=qos)
            result.wait_for_publish(timeout=5)
        except (RuntimeError, ValueError) as exc:
            logger.warning("Publish to %s failed: %s", topic, exc)
            return False
        if not result.is_published():
            # Connection dropped mid-publish: report it, so the caller keeps the reading. If paho
            # delivers it after all, the receiver's duplicate check stores it once.
            logger.warning("Publish to %s not acknowledged within 5 s", topic)
            return False
        logger.info("Published to %s", topic)
        return True

    def publish_nowait(self, topic: str, payload: str, qos: int = 1, retain: bool = False):
        """Queue a publish without waiting for it. Safe inside paho callbacks, where waiting would deadlock."""
        self._client.publish(topic, payload, qos=qos, retain=retain)

    def disconnect(self):
        """Stop cleanly. connect() may be called again afterwards (used by RESTART)."""
        self._client.loop_stop()
        self._client.disconnect()
        self._connected.clear()
        logger.info("MQTT client stopped cleanly")
