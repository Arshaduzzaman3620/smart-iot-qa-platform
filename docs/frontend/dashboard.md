# Web Dashboard

React 18 + TypeScript app built with Vite, in [frontend/](../../frontend/).

## Running it

```bash
# 1. infrastructure + data flow (see docs/architecture/database.md)
docker compose up -d --wait mqtt mysql    # infrastructure only
python -m database.init_db
cd receiver && python main.py               # terminal 1
cd sensor-simulator && python main.py       # terminal 2
ADMIN_PASSWORD=admin-dev-password python -m backend.app.main   # terminal 3, repo root

# 2. dashboard
cd frontend
npm install
npm run dev                                 # http://localhost:5173
```

In development, Vite forwards `/api/*` to FastAPI at `http://localhost:8000` (override with `VITE_API_TARGET`), so the backend needs no CORS configuration.

## Signing in

The dashboard opens on a sign-in form (Phase 15c, [auth.md](../api/auth.md)). Nothing is requested from the API before signing in. The header then shows the user, their role and **Sign out**. The session is kept in `sessionStorage`, so it survives a reload but not closing the tab. When the API answers `401` (token expired, user deleted), the dashboard returns to the form with the reason ("Token expired. Please sign in again."). A wrong password shows the API's message and clears the password field.

## Sensor details

Clicking a sensor ID opens a details panel above the table:

- name, location, type, firmware, status and last seen
- the 20 newest readings (`GET /sensors/{id}/telemetry?limit=20`), refetched whenever a newer reading arrives
- the sensor's alert history, active and resolved (`GET /sensors/{id}/alerts`)
- for OPERATOR and ADMIN only: a form to change the name and location (`PATCH /sensors/{id}`), showing "Saved" or the API's reason for rejecting it

Names and locations are rendered as text, never as HTML. A UI test checks that markup typed into a name stays inert.

## What it shows

An **alerts panel** lists every active alert, CRITICAL first and then newest first: severity badge (WARNING amber, CRITICAL red), sensor, message, and how long ago it was raised. With no active alerts it shows "No active alerts." Below it is one row per sensor. Both refresh every 5 s, matching the simulator's default interval, and come from `GET /sensors` and `GET /alerts?status=ACTIVE`, requested together:

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
- **Error banner** (either request failing): "Cannot reach the API" (FastAPI down) or "Database unavailable" (API returned 503). If data was already loaded, the table stays visible with "Showing last known data". Polling continues, and the banner clears automatically on recovery. A poll is skipped while the previous one is still running, so a slow API (> 5 s) still gets its response on screen instead of being cancelled by the next tick.

## Test hooks

Stable `data-testid` attributes for Playwright (Phase 13): `sensor-table`, `sensor-row-{SENSOR_ID}`, and per cell `sensor-id` (a button that opens the details), `temperature`, `humidity`, `battery`, `status`, `last-seen`, plus `error-banner`, `sensors-empty`, `loading`, `last-updated`. Alerts: `alerts-panel`, `alerts-none`, `alert-{id}`, and per alert `alert-severity`, `alert-sensor`, `alert-message`, `alert-since`. Sign-in: `login-form`, `login-username`, `login-password`, `login-submit`, `login-error`, `login-notice`, `user-menu`, `user-name`, `user-role`, `logout`. Details: `sensor-details`, `details-close`, `details-name`, `details-location`, `details-firmware`, `history-table`, `history-empty`, `details-alerts`, `details-alerts-empty`, `edit-sensor`, `edit-name`, `edit-location`, `edit-save`, `edit-message`.

UI tests sign in by putting a session into `sessionStorage` before the page loads (`open_dashboard(role)` in `tests/ui/conftest.py`). E2E tests sign in through the real form and API.

## Offline sensors

Since Phase 15a, a sensor with no stored reading for 30 s (`OFFLINE_TIMEOUT`) is shown as OFFLINE and gets an OFFLINE alert. It turns ONLINE again with its next reading. See [alerts.md](../architecture/alerts.md).
