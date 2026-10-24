# Manual End-to-End Verification (Phase 12)

The first full pipeline was verified by hand: **sensor → MQTT → receiver → validate → MySQL → FastAPI → dashboard**. This document is the runbook and the recorded result. Phase 13 turns these checks into automated tests.

Run date: 2026-10-24. Stack: Mosquitto 2 + MySQL 8.4 (Docker Compose), receiver, FastAPI, and the Vite dev server running locally, with the simulator at `SENSOR_INTERVAL=3`.

## How to reproduce

```bash
docker compose -f docker/docker-compose.yml up -d --wait
python -m database.init_db
cd receiver && python main.py                 # terminal 1
python -m backend.app.main                    # terminal 2 (repo root)
cd frontend && npm run dev                    # terminal 3
cd sensor-simulator && python main.py         # terminal 4: let it run ~15 s, then Ctrl+C
```

Stopping the simulator freezes the "latest" reading so every layer can be compared at rest. Then compare the same reading at each hop:

| Hop | Where to look |
|---|---|
| 1. Simulator | log lines `Telemetry sent: {...}` |
| 2. Receiver | log lines `Stored telemetry id=N from SENSOR-001: {...}` |
| 3. MySQL | `SELECT * FROM telemetry ORDER BY id;` and `SELECT * FROM sensors;` |
| 4. API | `GET /sensors/SENSOR-001/telemetry` and `GET /sensors` (`latest_telemetry`) |
| 5. Dashboard | `http://localhost:5173`: the SENSOR-001 row |

## Results

### Happy path: values identical at every hop ✅

5 readings published, 5 stored (ids 70–74). Latest reading, traced:

| Field | Simulator | Receiver | MySQL | API | Dashboard |
|---|---|---|---|---|---|
| timestamp | `2026-10-24T13:04:40Z` | same | `2026-10-24 13:04:40` | `2026-10-24T13:04:40Z` | last seen "8s ago" |
| temperature | 24.88 | 24.88 | 24.88 | 24.88 | 24.9 °C |
| humidity | 50.4 | 50.4 | 50.4 | 50.4 | 50.4 % |
| pressure | 1011.97 | 1011.97 | 1011.97 | 1011.97 | — (not shown) |
| light | 401.62 | 401.62 | 401.62 | 401.62 | — (not shown) |
| battery | 99.88 | 99.88 | 99.88 | 99.88 | 99.9 % |

- All 5 rows matched across simulator, receiver, MySQL, and API. The API also returned them newest first.
- `sensors` row: `ONLINE`, battery 99.88, `last_seen` 13:04:41. `GET /sensors` → `latest_telemetry.id = 74`.
- Sensor-to-storage latency (`received_at − timestamp`): 0 s at one-second resolution.
- The dashboard rounds to one decimal by design. **Automated E2E tests must compare against the API value rounded to 1 dp, not the raw value.**

### Negative path: invalid data never reaches the API or UI ✅

| Message | Receiver | API | Dashboard |
|---|---|---|---|
| new `SENSOR-BAD`, `temperature=999` | rejected: out of range | `GET /sensors/SENSOR-BAD` → 404 | no row |
| new `SENSOR-BAD2`, `humidity="wet"` | rejected: must be a number | 404 | no row |
| new `SENSOR-BAD3`, non-UTF-8 bytes | rejected: not valid UTF-8 | 404 | no row |
| new `SENSOR-002`, valid, battery 15.5 | stored, sensor auto-registered | listed | new row within one refresh, battery in red (< 20 %) |

### Reliability ✅

- **Broker restart:** the receiver logged the disconnect, then reconnected and resubscribed on its own. All 11 readings published after the broker returned were stored.
- **Simulator started with broker down:** it waited 5 s, logged `Broker not reachable yet; continuing`, logged each reading as `Telemetry dropped`, then connected and resumed publishing. No crash, no restart.

## Defects found and fixed in this phase

1. **First reading lost on every simulator start.** `connect()` is asynchronous, so the first publish ran before the connection existed and was skipped. Fix: `MQTTClient.wait_until_connected()`. `main.py` waits up to 5 s for the first connection, then proceeds, keeping the "keep running if the broker is down" behaviour. Verified: 5/5 readings stored after the fix (4/5 before).
2. **Misleading simulator log.** `Telemetry: {...}` was logged even when the publish was skipped, so the log over-reported sent readings. Fix: log `Telemetry sent` only on a successful publish, otherwise `Telemetry dropped (not published)` as a warning.

## Known limitations (not fixed here)

- **Stale ONLINE status:** after the simulator stopped, SENSOR-001 still shows ONLINE, with only "last seen" growing. Nothing marks a silent sensor OFFLINE. Planned: heartbeat timeout (Phase 15).
- **No buffering on outages:** readings produced while the broker (simulator side) or MySQL (receiver side) is down are dropped, not queued. Planned: reliability work (Phase 15).
- **Sensor metadata not propagated:** `name`, `location`, and `firmware_version` stay `null` in `sensors` because telemetry messages don't carry them. Planned: sensor registration/metadata (Phase 15).
