import json
import logging
import time
from datetime import datetime, timezone

from config import settings
from generator.data_generator import DataGenerator
from mqtt.mqtt_client import MQTTClient
from sensors.environment_sensor import EnvironmentSensor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sensor_simulator")


def build_telemetry(sensor: EnvironmentSensor) -> dict:
    return {
        "sensor_id": sensor.sensor_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temperature": sensor.temperature,
        "humidity": sensor.humidity,
        "pressure": sensor.pressure,
        "light": sensor.light,
        "battery": sensor.battery,
    }


def main():
    sensor = EnvironmentSensor("SENSOR-001", name="Room A Sensor", location="Room-A")
    generator = DataGenerator()
    mqtt_client = MQTTClient(settings.MQTT_HOST, settings.MQTT_PORT, client_id=sensor.sensor_id)

    topic = f"iot/sensors/{sensor.sensor_id}/telemetry"

    mqtt_client.connect()
    sensor.mark_online()
    logger.info("Sensor %s starting (interval=%ss)", sensor.sensor_id, settings.SENSOR_INTERVAL)

    try:
        while True:
            sensor.temperature = generator.generate_temperature(sensor.temperature)
            sensor.humidity = generator.generate_humidity(sensor.humidity)
            sensor.pressure = generator.generate_pressure(sensor.pressure)
            sensor.light = generator.generate_light(sensor.light)
            sensor.battery = generator.generate_battery(sensor.battery)
            sensor.touch()

            payload = build_telemetry(sensor)
            mqtt_client.publish(topic, json.dumps(payload))
            logger.info("Telemetry: %s", payload)

            time.sleep(settings.SENSOR_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Stop requested (Ctrl+C)")
    finally:
        sensor.mark_offline()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
