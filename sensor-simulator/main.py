import json
import logging
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timezone

if sys.version_info < (3, 10):  # `X | None` annotations below fail on import otherwise
    raise SystemExit(f"Python 3.10+ is required (3.12 recommended), this is {sys.version.split()[0]}. "
                     "See docs/development/setup.md, or run everything in Docker: docker compose up -d --build")

from commands.command_handler import CommandError, parse_command, response
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
# Wakes the main loop early: a stop request or an incoming command.
wakeup = threading.Event()
# Commands arrive on paho's network threads; they are queued and run on the main thread, which owns
# all sensor state, so no locking is needed.
incoming_commands: queue.Queue = queue.Queue()


def request_stop(signum, frame):
    logger.info("Stop requested (%s)", signal.Signals(signum).name)
    stop_requested.set()
    wakeup.set()


def install_stop_handlers():
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK exists only on Windows
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)


def topic(sensor_id: str, kind: str) -> str:
    return f"iot/sensors/{sensor_id}/{kind}"


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


def publish_reading(sensor: EnvironmentSensor, client: MQTTClient, generator: DataGenerator) -> bool:
    next_reading(sensor, generator)
    payload = build_telemetry(sensor)
    if client.publish(topic(sensor.sensor_id, "telemetry"), json.dumps(payload)):
        logger.info("Telemetry sent: %s", payload)
        return True
    logger.warning("Telemetry dropped (not published): %s", payload)
    return False


class CommandRunner:
    """Carries out commands for the fleet (Phase 15d): REQUEST_TELEMETRY, SET_INTERVAL, RESTART."""

    def __init__(self, sensors: dict, clients: dict, generator: DataGenerator, next_due: dict):
        self.sensors, self.clients, self.generator, self.next_due = sensors, clients, generator, next_due
        # sensor_id -> [command_id, monotonic time the "reboot" ends, reconnect started?]
        self.restarting: dict[str, list] = {}

    def reply(self, sensor_id: str, command_id: int, ok: bool, message: str):
        self.clients[sensor_id].publish(topic(sensor_id, "response"), response(command_id, ok, message), qos=1)
        logger.info("Command %s on %s %s: %s", command_id, sensor_id, "succeeded" if ok else "failed", message)

    def handle(self, sensor_id: str, payload: bytes):
        if sensor_id in self.restarting:
            return  # disconnected while "rebooting": nothing can arrive, but be safe
        try:
            command = parse_command(payload)
        except CommandError as exc:
            logger.warning("Rejected command for %s: %s", sensor_id, exc)
            if exc.command_id is not None:
                self.reply(sensor_id, exc.command_id, False, str(exc))
            return
        logger.info("Command %s %s%s received by %s", command.command_id, command.name, command.params or "", sensor_id)
        sensor, client = self.sensors[sensor_id], self.clients[sensor_id]

        if command.name == "REQUEST_TELEMETRY":
            ok = publish_reading(sensor, client, self.generator)
            self.reply(sensor_id, command.command_id, ok, "Reading published" if ok else "Reading could not be published")
        elif command.name == "SET_INTERVAL":
            sensor.interval = command.params["interval"]
            self.next_due[sensor_id] = time.monotonic() + sensor.interval
            self.reply(sensor_id, command.command_id, True, f"Interval set to {sensor.interval} s")
        elif command.name == "RESTART":
            # Like a device rebooting: drop off the network, come back after RESTART_SECONDS, then answer.
            sensor.mark_offline()
            client.disconnect()
            self.restarting[sensor_id] = [command.command_id, time.monotonic() + settings.RESTART_SECONDS, False]

    def advance_restarts(self) -> float | None:
        """Reconnect sensors whose reboot is over; answer once connected. Returns seconds until the next check."""
        if not self.restarting:
            return None
        now = time.monotonic()
        for sensor_id, state in list(self.restarting.items()):
            command_id, until, reconnecting = state
            if now < until:
                continue
            client = self.clients[sensor_id]
            if not reconnecting:
                client.connect()
                state[2] = True
            elif client.is_connected():
                del self.restarting[sensor_id]
                self.sensors[sensor_id].mark_online()
                self.next_due[sensor_id] = now  # first reading right after the reboot
                self.reply(sensor_id, command_id, True, f"Restarted ({settings.RESTART_SECONDS:g} s)")
        return 0.2 if self.restarting else None


def main():
    install_stop_handlers()
    try:
        fleet = create_fleet(settings.SENSOR_COUNT, prefix=settings.SENSOR_ID_PREFIX)
    except ValueError as exc:
        logger.error("Invalid SENSOR_COUNT: %s", exc)
        sys.exit(1)

    generator = DataGenerator()
    sensors = {s.sensor_id: s for s in fleet}
    clients = {s.sensor_id: MQTTClient(settings.MQTT_HOST, settings.MQTT_PORT, client_id=s.sensor_id) for s in fleet}
    for sensor in fleet:
        sensor.interval = settings.SENSOR_INTERVAL
        client = clients[sensor.sensor_id]
        # Announce who this sensor is on every (re)connect, so name/location/firmware reach the receiver.
        # Retained: the broker keeps the latest one and hands it to the receiver whenever it subscribes.
        # Without that, a sensor connecting before the receiver (the usual case at startup) went unheard.
        client.on_connected(lambda s=sensor, c=client: c.publish_nowait(
            topic(s.sensor_id, "status"), json.dumps(s.describe()), retain=True))

        def queue_command(payload: bytes, sensor_id=sensor.sensor_id):
            incoming_commands.put((sensor_id, payload))
            wakeup.set()

        client.subscribe(topic(sensor.sensor_id, "command"), queue_command)
    connect_all(list(clients.values()))
    for sensor in fleet:
        sensor.mark_online()
    logger.info("Starting %d sensor(s) (interval=%ss)", len(fleet), settings.SENSOR_INTERVAL)

    start = time.monotonic()
    next_due = {s.sensor_id: start + offset
                for s, offset in zip(fleet, start_offsets(len(fleet), settings.SENSOR_INTERVAL))}
    runner = CommandRunner(sensors, clients, generator, next_due)

    try:
        while not stop_requested.is_set():
            while not incoming_commands.empty() and not stop_requested.is_set():
                runner.handle(*incoming_commands.get_nowait())
            restart_check = runner.advance_restarts()

            for sensor in fleet:
                if stop_requested.is_set():
                    break
                if sensor.sensor_id in runner.restarting or time.monotonic() < next_due[sensor.sensor_id]:
                    continue
                publish_reading(sensor, clients[sensor.sensor_id], generator)
                # Fixed schedule (not "now + interval") so timing doesn't drift under load.
                next_due[sensor.sensor_id] += sensor.interval

            # Event.wait instead of sleep: wakes immediately for a stop request or a command.
            timeout = max(0.0, min(next_due.values()) - time.monotonic())
            if restart_check is not None:
                timeout = min(timeout, restart_check)
            wakeup.wait(timeout)
            wakeup.clear()
    finally:
        for sensor in fleet:
            sensor.mark_offline()
        for client in clients.values():
            client.disconnect()  # also fine for a sensor that is mid-"reboot"
        logger.info("Simulator stopped")


if __name__ == "__main__":
    main()
