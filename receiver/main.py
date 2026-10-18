import logging
import time

from config import settings
from mqtt.mqtt_client import MQTTSubscriber
from parser.message_parser import MessageParser, ParseError
from validator.telemetry_validator import TelemetryValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("receiver")

TELEMETRY_TOPIC = "iot/sensors/+/telemetry"


def on_message(client, userdata, msg):
    # Receiver never trusts incoming data: parse first, then validate.
    # No storage yet -- that's Phase 9 (MySQL writes).
    try:
        data = MessageParser.parse(msg.payload)
    except ParseError as exc:
        logger.warning("Rejected message on %s: %s (raw=%r)", msg.topic, exc, msg.payload[:200])
        return

    errors = TelemetryValidator.validate(data)
    if errors:
        logger.warning("Rejected message on %s: %s", msg.topic, "; ".join(errors))
        return

    logger.info("Accepted telemetry on %s: %s", msg.topic, data)


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
