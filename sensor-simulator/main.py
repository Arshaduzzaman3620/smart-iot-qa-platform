import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from config import settings
from generator.data_generator import DataGenerator
from mqtt.mqtt_client import MQTTClient
from sensors.environment_sensor import EnvironmentSensor
from sensors.fleet import create_fleet, start_offsets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sensor_simulator")

CONNECT_TIMEOUT = 5

# Set by Ctrl+C / SIGTERM (e.g. `docker stop`) / Ctrl+Break on Windows. The loop only checks it
# between readings, so a stop never lands between publishing a reading and logging it.
stop_requested = threading.Event()


def request_stop(signum, frame):
    logger.info("Stop requested (%s)", signal.Signals(signum).name)
    stop_requested.set()


def install_stop_handlers():
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK exists only on Windows
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)


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


def next_reading(sensor: EnvironmentSensor, generator: DataGenerator):
    sensor.temperature = generator.generate_temperature(sensor.temperature)
    sensor.humidity = generator.generate_humidity(sensor.humidity)
    sensor.pressure = generator.generate_pressure(sensor.pressure)
    sensor.light = generator.generate_light(sensor.light)
    sensor.battery = generator.generate_battery(sensor.battery)
    sensor.touch()


def connect_all(clients: list[MQTTClient]):
    # Each sensor is its own device with its own connection, like real hardware.
    for client in clients:
        client.connect()
    # connect() is asynchronous; without waiting, the first readings are published before the
    # connections exist and silently lost. Don't block forever -- if the broker is down, carry on
    # and let the reconnect logic catch up.
    deadline = time.monotonic() + CONNECT_TIMEOUT
    connected = sum(client.wait_until_connected(max(0.0, deadline - time.monotonic())) for client in clients)
    if connected < len(clients):
        logger.warning("%d/%d sensors connected to the broker; continuing, readings are skipped until they connect",
                       connected, len(clients))


def main():
    install_stop_handlers()
    try:
        fleet = create_fleet(settings.SENSOR_COUNT)
    except ValueError as exc:
        logger.error("Invalid SENSOR_COUNT: %s", exc)
        sys.exit(1)

    generator = DataGenerator()
    clients = {s.sensor_id: MQTTClient(settings.MQTT_HOST, settings.MQTT_PORT, client_id=s.sensor_id) for s in fleet}
    connect_all(list(clients.values()))
    for sensor in fleet:
        sensor.mark_online()
    logger.info("Starting %d sensor(s) (interval=%ss)", len(fleet), settings.SENSOR_INTERVAL)

    start = time.monotonic()
    next_due = {s.sensor_id: start + offset
                for s, offset in zip(fleet, start_offsets(len(fleet), settings.SENSOR_INTERVAL))}

    try:
        while not stop_requested.is_set():
            for sensor in fleet:
                if stop_requested.is_set():
                    break
                if time.monotonic() < next_due[sensor.sensor_id]:
                    continue
                next_reading(sensor, generator)
                payload = build_telemetry(sensor)
                topic = f"iot/sensors/{sensor.sensor_id}/telemetry"
                if clients[sensor.sensor_id].publish(topic, json.dumps(payload)):
                    logger.info("Telemetry sent: %s", payload)
                else:
                    logger.warning("Telemetry dropped (not published): %s", payload)
                # Fixed schedule (not "now + interval") so timing doesn't drift under load.
                next_due[sensor.sensor_id] += settings.SENSOR_INTERVAL

            # Event.wait instead of sleep: wakes immediately when a stop is requested.
            stop_requested.wait(max(0.0, min(next_due.values()) - time.monotonic()))
    finally:
        for sensor in fleet:
            sensor.mark_offline()
        for client in clients.values():
            client.disconnect()
        logger.info("Simulator stopped")


if __name__ == "__main__":
    main()
