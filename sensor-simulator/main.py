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
from fota.fota_client import FotaError, parse_update, run_update
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
# Work for the main thread, as callables: commands and firmware requests arriving on paho's network
# threads, and finished firmware downloads. The main thread owns all sensor state, so no locking.
main_thread_work: queue.Queue = queue.Queue()


def run_on_main_thread(work):
    main_thread_work.put(work)
    wakeup.set()


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
    """Carries out commands (Phase 15d: REQUEST_TELEMETRY, SET_INTERVAL, RESTART) and firmware
    updates (15e) for the fleet. Called on the main thread only."""

    def __init__(self, sensors: dict, clients: dict, generator: DataGenerator, next_due: dict):
        self.sensors, self.clients, self.generator, self.next_due = sensors, clients, generator, next_due
        # sensor_id -> [monotonic time the "reboot" ends, reconnect started?, what to do once back online]
        self.restarting: dict[str, list] = {}
        self.updating: set[str] = set()  # sensors with a firmware update in progress

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
            self.reboot(sensor_id, lambda: self.reply(sensor_id, command.command_id, True,
                                                      f"Restarted ({settings.RESTART_SECONDS:g} s)"))

    def reboot(self, sensor_id: str, when_back):
        """Like a device rebooting: drop off the network, come back after RESTART_SECONDS, then `when_back()`."""
        self.sensors[sensor_id].mark_offline()
        self.clients[sensor_id].disconnect()
        self.restarting[sensor_id] = [time.monotonic() + settings.RESTART_SECONDS, False, when_back]

    # ---- firmware over the air (Phase 15e) ----

    def fota_report(self, sensor_id: str, update_id: int, status: str, message: str):
        payload = json.dumps({"update_id": update_id, "status": status, "message": message})
        self.clients[sensor_id].publish(topic(sensor_id, "firmware_status"), payload, qos=1)
        log = logger.warning if status == "FAILED" else logger.info
        log("Firmware update %s on %s: %s %s", update_id, sensor_id, status, message)

    def handle_firmware(self, sensor_id: str, payload: bytes):
        if sensor_id in self.restarting:
            return
        try:
            request = parse_update(payload)
        except FotaError as exc:
            logger.warning("Rejected firmware request for %s: %s", sensor_id, exc)
            if exc.update_id is not None:
                self.fota_report(sensor_id, exc.update_id, "FAILED", str(exc))
            return
        if sensor_id in self.updating:
            self.fota_report(sensor_id, request.update_id, "FAILED", "another update is in progress")
            return
        sensor = self.sensors[sensor_id]
        self.updating.add(sensor_id)
        # Download and verify off the main thread, so the rest of the fleet keeps reading meanwhile.
        threading.Thread(target=self._update_worker, name=f"fota-{sensor_id}", daemon=True,
                         args=(sensor_id, request, sensor.firmware_version, sensor.battery)).start()

    def _update_worker(self, sensor_id, request, current_version, battery):
        def report(status, message):
            self.fota_report(sensor_id, request.update_id, status, message)

        try:
            version = run_update(request, current_version, battery, report, base_url=settings.API_BASE_URL,
                                 failure=settings.FOTA_FAILURE, min_battery=settings.FOTA_MIN_BATTERY,
                                 step_seconds=settings.FOTA_STEP_SECONDS)
        except FotaError as exc:
            report("FAILED", str(exc))
            run_on_main_thread(lambda: self.updating.discard(sensor_id))
            return
        run_on_main_thread(lambda: self._installed(sensor_id, request.update_id, current_version, version))

    def _installed(self, sensor_id, update_id, old_version, version):
        # The new firmware runs after a reboot; the retained status announced on reconnect carries it.
        self.sensors[sensor_id].firmware_version = version

        def back_online():
            self.updating.discard(sensor_id)
            self.fota_report(sensor_id, update_id, "SUCCEEDED", f"{old_version} -> {version}, rebooted")

        self.reboot(sensor_id, back_online)

    def advance_restarts(self) -> float | None:
        """Reconnect sensors whose reboot is over; answer once connected. Returns seconds until the next check."""
        if not self.restarting:
            return None
        now = time.monotonic()
        for sensor_id, state in list(self.restarting.items()):
            until, reconnecting, when_back = state
            if now < until:
                continue
            client = self.clients[sensor_id]
            if not reconnecting:
                client.connect()
                state[1] = True
            elif client.is_connected():
                del self.restarting[sensor_id]
                self.sensors[sensor_id].mark_online()
                self.next_due[sensor_id] = now  # first reading right after the reboot
                when_back()
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

        sid = sensor.sensor_id
        client.subscribe(topic(sid, "command"),
                         lambda payload, sid=sid: run_on_main_thread(lambda: runner.handle(sid, payload)))
        client.subscribe(topic(sid, "firmware"),
                         lambda payload, sid=sid: run_on_main_thread(lambda: runner.handle_firmware(sid, payload)))
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
            while not main_thread_work.empty() and not stop_requested.is_set():
                main_thread_work.get_nowait()()
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
