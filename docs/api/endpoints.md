# REST API

FastAPI backend in [backend/](../../backend/). It is read-only at this stage. Authentication and write endpoints arrive in Phase 15.

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
| GET | `/sensors` | `200` list of sensors, sorted by `sensor_id` | `503` DB down |
| GET | `/sensors/{sensor_id}` | `200` one sensor | `404 {"detail":"Sensor X not found"}`, `503` |
| GET | `/sensors/{sensor_id}/telemetry?limit=N` | `200` readings, newest first | `404` unknown sensor, `422` limit outside 1–1000 or not an integer, `503` |

`limit` defaults to 100. All datetimes are UTC ISO 8601 with a `Z` suffix, for example `2026-10-24T12:41:41Z`.

### Sensor

```json
{
  "sensor_id": "SENSOR-001", "sensor_type": "ENVIRONMENT", "name": null, "location": null,
  "status": "ONLINE", "firmware_version": null, "battery": 99.92,
  "last_seen": "2026-10-24T12:41:41Z", "created_at": "2026-10-24T12:29:18Z", "updated_at": "2026-10-24T12:41:41Z"
}
```

### Telemetry

```json
{
  "id": 15, "sensor_id": "SENSOR-001", "timestamp": "2026-10-24T12:41:41Z",
  "temperature": 24.29, "humidity": 50.32, "pressure": 1015.06, "light": 428.06, "battery": 99.92,
  "received_at": "2026-10-24T12:41:41Z"
}
```

## Error handling

- Any database connection failure returns `503 {"detail":"Database unavailable"}`. The client never sees a stack trace or connection details. The full error is logged server-side, without credentials.
- The API recovers automatically once MySQL is back (`pool_pre_ping`), with no restart needed.
