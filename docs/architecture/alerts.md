# Alerts and Offline Detection (Phase 15a)

The receiver raises alerts while it stores telemetry, and it marks sensors that have stopped reporting as `OFFLINE`. Alerts live in the `alerts` table. The API serves them at `GET /alerts`, and the dashboard lists the active ones above the sensor table.

## Threshold rules

Each reading is checked against these rules in [receiver/alerts/alert_service.py](../../receiver/alerts/alert_service.py):

| Alert type | Field | WARNING when | CRITICAL when | Resolves when |
|---|---|---|---|---|
| `LOW_BATTERY` | battery | < 20 % | < 10 % | ≥ 25 % |
| `HIGH_TEMPERATURE` | temperature | > 50 °C | > 70 °C | ≤ 48 °C |
| `LOW_TEMPERATURE` | temperature | < 0 °C | < −20 °C | ≥ 2 °C |
| `HIGH_HUMIDITY` | humidity | > 90 % | (none) | ≤ 85 % |
| `OFFLINE` | (no data) | no stored reading for `OFFLINE_TIMEOUT` | (none) | any new reading |

- **Strict thresholds:** a value exactly at a threshold does not trigger it. For example, battery 20.0 is fine and 19.99 is low, which matches the dashboard's red battery cell.
- **Reachable thresholds:** every threshold lies inside the validator's accepted range. A unit test checks this.
- **Hysteresis:** an alert resolves only once the value is back past its "Resolves when" level, not as soon as it re-crosses the threshold. Without this, a sensor hovering at 19.9 / 20.1 % would raise and resolve an alert on every reading.

## Alert lifecycle

```text
reading breaches a rule ──► RAISE      new row: status ACTIVE, severity, value, message
breach continues        ──► (nothing)  still one ACTIVE row per (sensor, alert type)
WARNING ──► CRITICAL     ──► ESCALATE   same row updated: severity, value, message
CRITICAL ──► WARNING     ──► (nothing)  severity never steps back down while active
value back past clear    ──► RESOLVE    status RESOLVED, resolved_at set
breach again later       ──► RAISE      a new row: a new incident, with its own history
```

The receiver applies these changes in the same transaction that stores the reading (see "How the receiver writes" in [database.md](database.md)).

- **Concurrency:** the sensor-row upsert at the start of that transaction holds the row lock until commit. Two messages from the same sensor therefore can't both raise the same alert.
- **Late readings:** only the sensor's newest reading is judged, meaning one that advanced the latest-reading pointer. A delayed, older reading is kept in the history but never raises or resolves a threshold alert.

The receiver logs every change:

```text
WARNING receiver.alerts: Alert raised for SENSOR-007: LOW_BATTERY WARNING - Battery low: 19.5 % (below 20 %)
WARNING receiver.alerts: Alert escalated for SENSOR-007: LOW_BATTERY CRITICAL - Battery low: 9.8 % (below 10 %)
INFO receiver.alerts: Alert resolved for SENSOR-007: LOW_BATTERY
WARNING receiver.alerts: Sensor SENSOR-042 marked OFFLINE: no telemetry for 31 s
```

## Offline detection

The receiver checks for silent sensors every `OFFLINE_CHECK_INTERVAL` seconds ([receiver/storage/offline_detector.py](../../receiver/storage/offline_detector.py)). Any `ONLINE` sensor whose `last_seen` is older than `OFFLINE_TIMEOUT` is set to `OFFLINE` and gets one `OFFLINE` alert. Its `value` is how many seconds the sensor had been silent.

The sensor's next stored reading sets it back to `ONLINE` and resolves the alert. A late reading counts too, because it still proves the sensor is reachable.

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `OFFLINE_TIMEOUT` | 30 | Seconds without a stored reading before a sensor is OFFLINE (6 missed readings at the default 5 s interval) |
| `OFFLINE_CHECK_INTERVAL` | 5 | Seconds between checks |
| `OFFLINE_STARTUP_GRACE` | = timeout | Delay before the first check after the receiver starts |

- **Startup grace:** while the receiver was down, nothing updated `last_seen`, so every sensor looks stale right after a restart. Checking immediately would mark live sensors OFFLINE until their next reading arrived.
- **No locks in the normal case:** the check first looks for stale sensors with a plain, non-locking read. An earlier version used a locking read (`SELECT ... FOR UPDATE`) over the whole table. Under InnoDB's REPEATABLE READ that next-key-locks every row and gap, so every receiver write stalled behind it every 5 s. In a 100-sensor run, max latency went from 1 s to 39 s and `GET /sensors` p95 from 36 ms to 286 ms.
- **Race with an incoming reading:** only the candidates are then locked, by unique key, and re-checked. A reading arriving at the same moment either waits and then sets the sensor back ONLINE, or commits first and drops out of the re-check. Either way, a live sensor never stays OFFLINE.
- **Single receiver:** detection runs inside the receiver. With several receivers, each would run the check. That is harmless (the second finds nothing to do and never duplicates an alert), but it is wasted work.

## Performance

Alert handling adds one indexed lookup to each stored message (~1 ms round trip, roughly 4 % of a save; `EXPLAIN ANALYZE` shows `ix_alerts_sensor_status`). Writes only happen when an alert actually changes.

The receiver's bottleneck is still committing every message on its own, which costs two disk flushes with MySQL's default durability settings. Commit cost varies a lot on this Windows + Docker machine: 15–40 ms per save, depending on the moment. At the slow end a single receiver no longer keeps up with 100 sensors (20 msg/s), and the 100-sensor scale check fails on latency (no messages are lost). This was also reproduced with Phase 14 code on the same day. Batched writes (Phase 15b) address it.

## Testing

- `tests/unit/test_alert_service.py` covers every threshold ±0.01, escalation, no de-escalation, hysteresis edges, several alerts from one reading, and that the thresholds are reachable and consistent.
- `tests/integration/test_alert_flow.py` runs the real receiver process and checks: raise, no duplicates, escalate, resolve then re-raise, a late reading ignored, a silent sensor marked OFFLINE exactly once, a recent sensor left alone, and recovery.
- `tests/api/test_alerts.py` covers the endpoints, filters, ordering, limits, 404 / 422 / 405 responses, and the `active_alerts` count.
- `tests/unit/test_offline_detector.py` covers the readable silence duration in OFFLINE messages (`31 s`, `5 min`, `9 h 57 min`, `2 days`).
- `tests/ui/test_dashboard_ui.py` covers the alerts panel: empty state, severity badges, CRITICAL listed first, appear and clear on refresh, and API failure.

## Not yet

- Acknowledging or closing alerts by hand: this needs authentication first (later in Phase 15).
- Notifications (email, push).
- Per-sensor or configurable thresholds: the rules are code constants for now.
