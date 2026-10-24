# Web Dashboard

React 18 + TypeScript app built with Vite, in [frontend/](../../frontend/).

## Running it

```bash
# 1. infrastructure + data flow (see docs/architecture/database.md)
docker compose -f docker/docker-compose.yml up -d --wait
python -m database.init_db
cd receiver && python main.py               # terminal 1
cd sensor-simulator && python main.py       # terminal 2
python -m backend.app.main                  # terminal 3, from repo root

# 2. dashboard
cd frontend
npm install
npm run dev                                 # http://localhost:5173
```

In development, Vite forwards `/api/*` to FastAPI at `http://localhost:8000` (override with `VITE_API_TARGET`), so the backend needs no CORS configuration.

## What it shows

One row per sensor, refreshed every 5 s (matching the simulator's default interval):

| Column | Source |
|---|---|
| Sensor ID | `sensor_id` |
| Temperature, Humidity | `latest_telemetry` from `GET /sensors` (shows `—` if the sensor has no readings) |
| Battery | `battery` (red below 20 %) |
| Status | `status` badge: ONLINE (green), OFFLINE (grey), ERROR (red) |
| Last seen | relative time (`6s ago`); hover for the exact UTC timestamp |

## States

- **Loading**: first fetch in progress.
- **Empty**: no sensors have reported yet.
- **Error banner**: "Cannot reach the API" (FastAPI down) or "Database unavailable" (API returned 503). If data was already loaded, the table stays visible with "Showing last known data". Polling continues, and the banner clears automatically on recovery.

## Test hooks

Stable `data-testid` attributes for Playwright (Phase 13): `sensor-table`, `sensor-row-{SENSOR_ID}`, and per cell `sensor-id`, `temperature`, `humidity`, `battery`, `status`, `last-seen`, plus `error-banner`, `sensors-empty`, `loading`, `last-updated`.

## Known limitation

`status` is whatever the receiver last wrote, and nothing marks a silent sensor `OFFLINE` yet. A sensor that stopped publishing keeps showing ONLINE, with a growing "last seen". Offline detection (heartbeat timeout) is part of Phase 15.
