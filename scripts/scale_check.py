"""Scale check: run N simulated sensors through the real pipeline and measure what arrives.

    python scripts/scale_check.py --sensors 100 --interval 5 --duration 60

Starts its own receiver (stop any receiver you started by hand first, or every message is
stored twice), runs the simulator with SENSOR_COUNT=N, then compares every reading the simulator
logged as sent against what is in MySQL:

  - loss / duplicates (every sent reading must be stored exactly once; waits for the
    receiver to drain any backlog first, so "missing" means lost, not late)
  - stored throughput (messages per second)
  - sensor-to-storage latency (received_at - timestamp; MySQL DATETIME has 1 s resolution),
    failing above --max-latency (default 5 s)
  - GET /sensors response time and row count (needs the API running on API_PORT)

Needs the broker and MySQL running (docker compose -f docker/docker-compose.yml up -d).
"""

import argparse
import ast
import os
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from database.models import Telemetry  # noqa: E402
from database.session import SessionLocal  # noqa: E402

SENT_LINE = re.compile(r"Telemetry sent: (\{.*\})")
DROPPED_LINE = re.compile(r"Telemetry dropped")


def start(command, cwd, log_path, extra_env=None):
    log = open(log_path, "w", encoding="utf-8")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    # Own process group on Windows so it can receive Ctrl+Break (see graceful_stop).
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env,
                            creationflags=flags), log


def wait_for(path: Path, text: str, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if text in path.read_text(encoding="utf-8"):
            return
        time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {text!r} in {path}")


def graceful_stop(process, log_path: Path):
    """Ask the simulator to finish its current reading and exit (Ctrl+Break on Windows, SIGTERM elsewhere).

    Killing it outright can land between publishing a reading and logging it, which would show up
    as a phantom "duplicate" (stored but never logged as sent).
    """
    process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
    if "Simulator stopped" not in log_path.read_text(encoding="utf-8"):
        print("warning: simulator did not stop cleanly; counts near the end may be off")


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def stored_rows(sensor_ids, since):
    with SessionLocal() as session:
        return session.scalars(
            select(Telemetry).where(Telemetry.sensor_id.in_(sensor_ids), Telemetry.received_at >= since)
        ).all()


def wait_for_drain(sensor_ids, since, quiet: float = 3.0, timeout: float = 120.0) -> float:
    """Wait until the receiver stops storing (backlog drained). Returns seconds waited."""
    t0 = time.monotonic()
    last, last_change = -1, t0
    while time.monotonic() - t0 < timeout:
        count = len(stored_rows(sensor_ids, since))
        if count != last:
            last, last_change = count, time.monotonic()
        elif time.monotonic() - last_change >= quiet:
            break
        time.sleep(0.5)
    return last_change - t0


def percentile(values, pct):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def measure_api(api_url: str, expected_min_rows: int, calls: int = 30):
    with httpx.Client(base_url=api_url, timeout=10) as client:
        try:
            client.get("/health", timeout=2)
        except httpx.HTTPError:
            return None
        timings, rows = [], 0
        for _ in range(calls):
            t0 = time.perf_counter()
            response = client.get("/sensors")
            timings.append((time.perf_counter() - t0) * 1000)
            response.raise_for_status()
            rows = len(response.json())
    return {"rows": rows, "p50_ms": percentile(timings, 50), "p95_ms": percentile(timings, 95),
            "max_ms": max(timings), "enough_rows": rows >= expected_min_rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sensors", type=int, required=True)
    parser.add_argument("--interval", type=int, default=5, help="seconds between readings per sensor")
    parser.add_argument("--duration", type=int, default=60, help="seconds to run the simulator")
    parser.add_argument("--max-latency", type=float, default=5.0,
                        help="fail if any reading took longer than this (s) from sensor to MySQL")
    # 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 ::1 first, and since the API only
    # listens on IPv4 every request would wait ~2 s for that attempt to fail.
    parser.add_argument("--api", default=f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}")
    args = parser.parse_args()

    logs = Path(tempfile.mkdtemp(prefix="scale_check_"))
    python = sys.executable
    started_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(seconds=1)

    receiver, receiver_log = start([python, "main.py"], ROOT / "receiver", logs / "receiver.log")
    try:
        wait_for(logs / "receiver.log", "Subscribed to iot/sensors/+/telemetry", 15)
        print(f"Running {args.sensors} sensors every {args.interval}s for {args.duration}s ...")
        simulator, simulator_log = start(
            [python, "main.py"], ROOT / "sensor-simulator", logs / "simulator.log",
            {"SENSOR_COUNT": str(args.sensors), "SENSOR_INTERVAL": str(args.interval)},
        )
        time.sleep(args.duration)
        graceful_stop(simulator, logs / "simulator.log")
        simulator_log.close()
        sim_text = (logs / "simulator.log").read_text(encoding="utf-8")
        sensor_ids = {ast.literal_eval(m.group(1))["sensor_id"] for m in SENT_LINE.finditer(sim_text)}
        # Under overload the receiver falls behind; give it time to work through its backlog
        # so "missing" means lost, not merely late.
        drain_seconds = wait_for_drain(sensor_ids, started_at)
    finally:
        stop(receiver)
        receiver_log.close()

    sent = [ast.literal_eval(m.group(1)) for m in SENT_LINE.finditer(sim_text)]
    dropped = len(DROPPED_LINE.findall(sim_text))
    rows = stored_rows(sensor_ids, started_at)
    latencies = [(r.received_at - r.timestamp).total_seconds() for r in rows]

    # Counted per (sensor, second) rather than as sets: at a 1 s interval a sensor can legitimately
    # send twice within the same second, which a set would collapse.
    sent_counts = Counter((m["sensor_id"], m["timestamp"]) for m in sent)
    stored_counts = Counter((r.sensor_id, r.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")) for r in rows)
    missing = sum((sent_counts - stored_counts).values())
    duplicates = sum((stored_counts - sent_counts).values())
    receiver_text = (logs / "receiver.log").read_text(encoding="utf-8")
    rejected = receiver_text.count("Rejected message")
    db_errors = receiver_text.count("Failed to store")

    api = measure_api(args.api, args.sensors)

    print()
    print(f"sensors publishing        {len(sensor_ids)} / {args.sensors}")
    print(f"readings sent             {len(sent)}   (dropped before publish: {dropped})")
    print(f"readings stored           {len(rows)}   (backlog drained {drain_seconds:.0f}s after the simulator stopped)")
    print(f"missing                   {missing}")
    print(f"duplicates                {duplicates}")
    print(f"receiver rejected / DB errors   {rejected} / {db_errors}")
    print(f"stored throughput         {len(rows) / (args.duration + drain_seconds):.1f} msg/s "
          f"(expected ~{args.sensors / args.interval:.1f})")
    if latencies:
        print(f"latency sensor->MySQL     avg {statistics.mean(latencies):.2f}s  max {max(latencies):.0f}s  (1 s resolution)")
    if api:
        print(f"GET /sensors              {api['rows']} rows, p50 {api['p50_ms']:.1f} ms, "
              f"p95 {api['p95_ms']:.1f} ms, max {api['max_ms']:.1f} ms")
    else:
        print(f"GET /sensors              skipped (API not reachable at {args.api})")
    print(f"logs                      {logs}")

    max_latency = max(latencies, default=0)
    ok = (len(sensor_ids) == args.sensors and not missing and not duplicates and not db_errors and not rejected
          and max_latency <= args.max_latency)
    if max_latency > args.max_latency:
        print(f"latency {max_latency:.0f}s exceeds --max-latency {args.max_latency:.0f}s (receiver can't keep up)")
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
