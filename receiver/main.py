import logging
import time

from config import settings
from mqtt.mqtt_client import MQTTSubscriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("receiver")

TELEMETRY_TOPIC = "iot/sensors/+/telemetry"


def on_message(client, userdata, msg):
    # Phase 6 scope only: log what arrives, as-is. No parsing/validation/
    # storage yet -- that's Phase 7 (validator) and Phase 9 (MySQL writes).
    logger.info("Received on %s: %s", msg.topic, msg.payload.decode(errors="replace"))


def main():
    mqtt_client = MQTTSubscriber(settings.MQTT_HOST, settings.MQTT_PORT, client_id="receiver")
    mqtt_client.set_message_handler(on_message)
    mqtt_client.connect([TELEMETRY_TOPIC])
    logger.info("Receiver starting, subscribing to %s", TELEMETRY_TOPIC)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stop requested (Ctrl+C)")
    finally:
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
