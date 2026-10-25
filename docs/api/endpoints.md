# REST API

FastAPI backend in [backend/](../../backend/). It is read-only at this stage. Authentication and write endpoints arrive later in Phase 15.

## Running it

```bash
# from the repo root, with MySQL up (see docs/architecture/database.md)
pip install -r backend/requirements.txt
python -m backend.app.main          # serves on 127.0.0.1:$API_PORT (default 8000)
```

Interactive docs: `http://localhost:8000/docs` (Swagger UI), `http://localhost:8000/redoc`.

## Endpoints

| Method | Path | Success | Errors |
|---|---|---|---|
| GET | `/health` | `200 {"status":"ok","database":"ok"}` | `503 {"status":"degraded","database":"unavailable"}` |
| GET | `/sensors` | `200` list of sensors, sorted by `sensor_id`, each with `latest_telemetry` | `503` DB down |
| GET | `/sensors/{sensor_id}` | `200` one sensor | `404 {"detail":"Sensor X not found"}`, `503` |
| GET | `/sensors/{sensor_id}/telemetry?limit=N` | `200` readings, newest first | `404` unknown sensor, `422` limit outside 1–1000 or not an integer, `503` |
| GET | `/sensors/{sensor_id}/alerts?status=&limit=N` | `200` the sensor's alerts, newest first | `404` unknown sensor, `422`, `503` |
| GET | `/alerts?status=&sensor_id=&limit=N` | `200` alerts, newest first | `422` bad `status` or `limit`, `503` |

`limit` defaults to 100. `status` is `ACTIVE` or `RESOLVED` (exact case), or omitted for both. An unknown `sensor_id` filter on `/alerts` returns `[]`. All datetimes are UTC ISO 8601 with a `Z` suffix, for example `2026-10-24T12:41:41Z`.

### Sensor

```json
{
  "sensor_id": "SENSOR-001", "sensor_type": "ENVIRONMENT", "name": null, "location": null,
  "status": "ONLINE", "firmware_version": null, "battery": 99.92,
  "last_seen": "2026-10-24T12:41:41Z", "created_at": "2026-10-24T12:29:18Z", "updated_at": "2026-10-24T12:41:41Z"
}
```

`GET /sensors` items also carry `latest_telemetry`: the sensor's most recently stored reading (Telemetry object below), or `null` if it has none. It is fetched for all sensors in one query, so the dashboard needs a single request per refresh. They also carry `active_alerts`: the number of the sensor's alerts with status `ACTIVE`.

### Telemetry

```json
{
  "id": 15, "sensor_id": "SENSOR-001", "timestamp": "2026-10-24T12:41:41Z",
  "temperature": 24.29, "humidity": 50.32, "pressure": 1015.06, "light": 428.06, "battery": 99.92,
  "received_at": "2026-10-24T12:41:41Z"
}
```

### Alert

```json
{
  "id": 7, "sensor_id": "SENSOR-007", "alert_type": "LOW_BATTERY", "severity": "WARNING", "value": 19.5,
  "message": "Battery low: 19.5 % (below 20 %)", "status": "ACTIVE",
  "created_at": "2026-10-25T10:12:03Z", "resolved_at": null
}
```

`alert_type` is one of `LOW_BATTERY`, `HIGH_TEMPERATURE`, `LOW_TEMPERATURE`, `HIGH_HUMIDITY`, or `OFFLINE`. `severity` is `WARNING` or `CRITICAL`. Rules and lifecycle: [alerts.md](../architecture/alerts.md).

## Error handling

- Any database connection failure returns `503 {"detail":"Database unavailable"}`. The client never sees a stack trace or connection details. The full error is logged server-side, without credentials.
- The API recovers automatically once MySQL is back (`pool_pre_ping`), with no restart needed.
