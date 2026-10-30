"""Harness for reliability tests: the real receiver and simulator as processes, with TCP proxies in
front of MySQL and the broker so a test can cut either one. Each test gets its own topic root, sensor
IDs and receiver session, so it is isolated from other tests and from a running dev stack."""

import ast
import os
import re
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import text

from database import config as db_config
from database.session import SessionLocal
from helpers import MQTT_HOST, MQTT_PORT, ROOT, wait_until
from tcp_proxy import TcpProxy

SENT = re.compile(r"Telemetry sent: (\{.*\})")
# Kept by the simulator during a broker outage: each must be sent (and stored) once it is back.
BUFFERED = re.compile(r"Telemetry buffered \(.*?\): (\{.*\})")


class Harness:
    def __init__(self, tmp_path):
        tag = uuid.uuid4().hex[:6].upper()
        self.topic_root = f"rtest{tag.lower()}/sensors"
        self.prefix = f"TEST-REL{tag}-"
        self.client_id = f"receiver-rel-{tag.lower()}"
        self.tmp = tmp_path
        self.mysql = TcpProxy(db_config.MYSQL_HOST, db_config.MYSQL_PORT).__enter__()
        self.broker = TcpProxy(MQTT_HOST, MQTT_PORT).__enter__()  # for the simulator only
        self.receiver = self.simulator = None
        self.receiver_starts = 0

    # ---- processes -------------------------------------------------------------------------

    def _start(self, name, cwd, env):
        log = open(self.tmp / f"{name}.log", "a", encoding="utf-8")
        base = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "TOPIC_ROOT": self.topic_root}
        return subprocess.Popen([sys.executable, "main.py"], cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                env={**base, **env})

    def log(self, name) -> str:
        path = self.tmp / f"{name}.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def start_receiver(self, **env):
        self.receiver_starts += 1
        self.receiver = self._start("receiver", ROOT / "receiver", {
            "RECEIVER_CLIENT_ID": self.client_id, "MYSQL_HOST": "127.0.0.1", "MYSQL_PORT": str(self.mysql.port),
            "OFFLINE_CHECK_INTERVAL": "1", **env})
        starts = self.receiver_starts
        wait_until(lambda: self.log("receiver").count(f"Subscribed to {self.topic_root}/+/telemetry") >= starts,
                   timeout=15)

    def kill_receiver(self):
        """Crash it: SIGKILL, no chance to store or acknowledge anything."""
        self.receiver.kill()
        self.receiver.wait(timeout=10)

    def start_simulator(self, count=5, interval=1, **env):
        self.simulator = self._start("simulator", ROOT / "sensor-simulator", {
            "SENSOR_ID_PREFIX": self.prefix, "SENSOR_COUNT": str(count), "SENSOR_INTERVAL": str(interval),
            "MQTT_HOST": "127.0.0.1", "MQTT_PORT": str(self.broker.port), **env})
        wait_until(lambda: "Telemetry sent" in self.log("simulator"), timeout=15)

    def stop_simulator(self):
        self.simulator.terminate()
        self.simulator.wait(timeout=30)
        assert "Simulator stopped" in self.log("simulator")

    def close(self):
        for process in (self.simulator, self.receiver):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
        self.mysql.cut()
        self.broker.cut()

    # ---- what was sent vs what is stored ---------------------------------------------------

    def sent(self) -> list[tuple]:
        """Every reading the simulator took and meant to deliver: sent at once, or buffered for later."""
        log = self.log("simulator")
        readings = [ast.literal_eval(m.group(1)) for pattern in (SENT, BUFFERED) for m in pattern.finditer(log)]
        # A buffered reading is logged twice (buffered, then sent): count it once.
        return sorted({(r["sensor_id"], r["timestamp"], r["temperature"]) for r in readings})

    def stored(self) -> list[tuple]:
        with SessionLocal() as session:
            rows = session.execute(text(
                "SELECT sensor_id, DATE_FORMAT(timestamp, '%Y-%m-%dT%H:%i:%sZ'), temperature FROM telemetry "
                "WHERE sensor_id LIKE :p ORDER BY id"), {"p": f"{self.prefix}%"}).all()
        return [tuple(r) for r in rows]

    def wait_until_all_stored(self, timeout=60) -> float:
        """Seconds until every reading the simulator sent is in MySQL."""
        start = time.monotonic()
        expected = set(self.sent())
        wait_until(lambda: expected <= set(self.stored()), timeout=timeout, interval=0.25)
        return time.monotonic() - start

    def assert_no_loss_no_duplicates(self):
        sent, stored = self.sent(), self.stored()
        assert sent, "the simulator sent nothing"
        assert "buffered readings not sent" not in self.log("simulator")
        missing = set(sent) - set(stored)
        assert not missing, f"{len(missing)} of {len(sent)} readings lost, e.g. {sorted(missing)[:3]}"
        assert len(stored) == len(set(stored)), f"{len(stored) - len(set(stored))} duplicate rows stored"
        assert set(stored) <= set(sent), "stored a reading the simulator never logged as sent"
        return len(sent)

    def offline_alerts(self) -> int:
        with SessionLocal() as session:
            return session.execute(text(
                "SELECT COUNT(*) FROM alerts WHERE alert_type = 'OFFLINE' AND sensor_id LIKE :p"),
                {"p": f"{self.prefix}%"}).scalar()


@pytest.fixture
def harness(mysql_available, broker_available, clean_test_rows, tmp_path):
    h = Harness(tmp_path)
    yield h
    h.close()

