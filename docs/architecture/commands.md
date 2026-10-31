# Sensor Commands

Operators can send three commands to a sensor from the dashboard or the API (Phase 15d).

| Command | Params | What the sensor does | Its answer |
|---|---|---|---|
| `REQUEST_TELEMETRY` | none | Publishes a reading now, outside its schedule | `Reading published` |
| `SET_INTERVAL` | `interval`: whole seconds, 1–3600 | Changes its reading interval, starting from now | `Interval set to 10 s` |
| `RESTART` | none | Drops off the network for `RESTART_SECONDS` (default 3), reconnects, resumes reading | `Restarted (3 s)` |

## Flow

```text
Dashboard ──POST /sensors/{id}/commands──> API ──stores SENT──> MySQL
                                            └──publish QoS 1──> iot/sensors/{id}/command ──> sensor
sensor ──> iot/sensors/{id}/response ──> receiver ──SUCCEEDED / FAILED──> MySQL
receiver (every OFFLINE_CHECK_INTERVAL) ──SENT for > COMMAND_TIMEOUT──> TIMED_OUT
Dashboard ──GET /sensors/{id}/commands (every 1 s while one is SENT)──> API
```

The API answers `202 Accepted` with the command in state `SENT`: the request was published, but the sensor hasn't answered yet. The final state comes later:

| Status | Set by | When |
|---|---|---|
| `SENT` | API | Published to the broker (QoS 1, broker acknowledged) |
| `SUCCEEDED` / `FAILED` | receiver | The sensor's response arrived. `message` is the sensor's text. |
| `TIMED_OUT` | receiver | No response within `COMMAND_TIMEOUT` (default 30 s), for example the sensor is offline |
| `FAILED` | API | The broker was unreachable: the API also answers `503 MQTT broker unreachable` |

The row is stored *before* publishing, so a response that arrives within milliseconds always finds it.

## Messages

`iot/sensors/{id}/command` (API → sensor):

```json
{"command_id": 12, "command": "SET_INTERVAL", "params": {"interval": 10}, "issued_at": "2026-10-30T10:35:41Z"}
```

`iot/sensors/{id}/response` (sensor → receiver):

```json
{"command_id": 12, "status": "SUCCEEDED", "message": "Interval set to 10 s"}
```

## Trust boundaries

Commands and responses are checked at every hop, because anything that can publish to the broker can send anything. MQTT authentication arrives in the security part (15g).

- **API:** `command` must be one of the three values. `interval` is required for `SET_INTERVAL` only, must be a strict integer (`"10"`, `10.5` and `true` are rejected) and must be 1–3600. Unknown fields are rejected. Only OPERATOR and ADMIN can send.
- **Sensor:** parses every command again (`sensor-simulator/commands/command_handler.py`). An invalid command with a usable `command_id` is answered `FAILED` with the reason. One without a usable id is only logged.
- **Receiver:** a response must have a positive integer `command_id` and a status of `SUCCEEDED` or `FAILED` (a sensor can't claim `TIMED_OUT`). It is applied only to a command that is still `SENT` **and belongs to the sensor whose topic it came on**. Responses for another sensor's command, duplicates, and late answers after a timeout are logged as "Ignored" and change nothing. Messages are cut to the 255-character column.

## Sensor status announcements

When a sensor connects (and after a `RESTART`), it publishes what it is on `iot/sensors/{id}/status`, **retained**:

```json
{"sensor_id": "SENSOR-001", "sensor_type": "ENVIRONMENT", "name": "Room 1 Sensor", "location": "Room-1",
 "firmware_version": "1.0.0", "interval": 5}
```

The receiver stores `firmware_version` and `sensor_type` every time. It fills `name` and `location` only when they are empty, so a name set by an operator (`PATCH /sensors/{id}`) is never overwritten. A sensor that has announced itself but not sent a reading stays `OFFLINE`.

Retained matters. At startup the sensors usually connect before the receiver has subscribed, and the first manual check found every announcement lost (`firmware_version` NULL for all five sensors). With `retain`, the broker keeps each sensor's latest status and delivers it whenever the receiver subscribes, including after a receiver restart. Clearing it means publishing an empty retained message; the receiver ignores those silently.

This also closes the Phase 12 limitation "sensor metadata not propagated".
