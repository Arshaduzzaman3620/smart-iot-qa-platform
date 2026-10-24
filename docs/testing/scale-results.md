# Multi-Sensor Scale Results (Phase 14)

The pipeline was scaled from 1 to **5 → 10 → 50 → 100** simulated sensors and measured with [scripts/scale_check.py](../../scripts/scale_check.py). Run date: 2026-10-25, single Windows 11 laptop, with everything local (Mosquitto + MySQL in Docker; receiver, API, and simulator as Python processes).

## How to reproduce

```bash
docker compose -f docker/docker-compose.yml up -d --wait
python -m database.init_db
python -m backend.app.main                 # optional: enables the GET /sensors timing
# stop any receiver you started by hand -- the script runs its own
python scripts/scale_check.py --sensors 100 --interval 5 --duration 60
```

The script starts its own receiver and runs the simulator with `SENSOR_COUNT=N`. It stops the simulator gracefully, so the last reading is never cut off between publish and log, and waits for the receiver to drain any backlog. Then it compares every reading the simulator logged as sent against MySQL. **PASS** = all N sensors published, nothing missing, nothing duplicated, no rejections or DB errors, and every reading stored within `--max-latency` (default 5 s).

## Results at the target load (one reading per sensor every 5 s)

| Sensors | Sent | Stored | Missing | Duplicates | Throughput (expected) | Max latency | Result |
|---|---|---|---|---|---|---|---|
| 5 | 30 | 30 | 0 | 0 | 1.0 msg/s (1.0) | 0 s | ✅ PASS |
| 10 | 60 | 60 | 0 | 0 | 2.0 msg/s (2.0) | 0 s | ✅ PASS |
| 50 | 594 | 594 | 0 | 0 | 9.9 msg/s (10.0) | 0 s | ✅ PASS |
| 100 | 1189 | 1189 | 0 | 0 | 19.5 msg/s (20.0) | 1 s | ✅ PASS |

Latency is `received_at − timestamp`. Both are MySQL `DATETIME` with 1-second resolution, so "0 s" means within the same second.

The dashboard rendered all 100 sensors, each with distinct readings, refreshing every 5 s.

## Capacity: where it stops keeping up

| Load | Sent | Stored | Missing | Throughput | Max latency | Result |
|---|---|---|---|---|---|---|
| 100 sensors every 1 s (100 msg/s offered) | 2922 | 2922 | 0 | ~66 msg/s | 29 s | ❌ latency |

- **The receiver's ceiling is about 65–75 msg/s** (one transaction per message, single-threaded). That is **~3.3× the 100-sensor target** of 20 msg/s.
- Above the ceiling, **nothing is lost**: messages queue, and the receiver drains the backlog after the load stops (14 s here). The cost is latency, which grows for as long as the overload lasts.
- Raising the ceiling (batched inserts, a writer thread) is performance work for Phase 15.

## Defects found and fixed while scaling

1. **`GET /sensors` got slower with every reading stored.** The latest-reading-per-sensor query scanned the whole telemetry table. With 1M rows it took **~1,700 ms** (the table grows ~1.7M rows/day at 100 sensors). MySQL would not use a backward index scan in any per-sensor subquery form (correlated, `MAX()`, or `LATERAL`), as verified with `EXPLAIN ANALYZE`. **Fix:** the receiver keeps a pointer to each sensor's newest reading (`sensors.latest_telemetry_id` / `latest_reading_at`), updated in the same transaction, and the list endpoint joins on it by primary key: **2.5 ms at 1M rows**, independent of table size. The pointer only moves forward, so a delayed (out-of-order) message can't replace a newer reading. Existing databases are upgraded and backfilled by `python -m database.init_db` (see [database/migrations.py](../../database/migrations.py)).
2. **Simulator could be killed between publishing a reading and logging it.** This showed up in measurements as a phantom duplicate (stored but never logged as sent). **Fix:** Ctrl+C, SIGTERM (e.g. `docker stop`), and Ctrl+Break on Windows now set a stop flag that the loop checks between readings, followed by a clean disconnect and `Simulator stopped`.
3. **API calls to `localhost` took ~2 s each on Windows.** `localhost` resolves to IPv6 `::1` first, and the API listens on IPv4 only, so every new connection waited for the IPv6 attempt to fail. The first 5-sensor measurement reported a 2.5 s median for `GET /sensors`. **Fix:** the scale script, the e2e tests, and the Vite dev proxy use `127.0.0.1`. Real latency is 11–75 ms, depending on load.
4. **Measurement fixes in the script itself:** wait for the receiver to drain before counting (otherwise "late" looked like "lost"), and count per (sensor, second) rather than as a set (at a 1 s interval a sensor can send twice in the same second).

## Automated coverage added

- `tests/unit/test_fleet.py`: unique sequential IDs, varied but valid starting values, count limits (1–1000), and evenly spread start offsets.
- `tests/integration/test_multi_sensor.py`: 20 sensors × 5 readings published concurrently, all stored exactly once; each sensor's pointer refers to its own newest reading.
- `tests/integration/test_receive_chain.py`: the pointer follows the newest timestamp, and a late message doesn't move it back.
- `tests/ui/test_dashboard_ui.py`: the dashboard renders 100 sensors.
