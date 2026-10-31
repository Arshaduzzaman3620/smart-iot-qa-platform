# Web Dashboard

React 18 + TypeScript app built with Vite, in [frontend/](../../frontend/).

## Design

A smart-home control center (redesigned in Phases 17–18):

- **Layout:** a sidebar (brand, section links that highlight the section on screen, theme switch, signed-in user) that becomes a top bar below 900 px. A greeting with a live-connection indicator, then a **home status banner** that says in one sentence what needs attention (critical alerts first, then warnings, offline devices, or "Everything is running smoothly") with the average indoor climate, then five overview tiles.
- **Devices:** a **list** (sortable columns, status dots, battery bars) or a **rooms** view (one card per device with a big temperature, a comfort label such as Comfortable / Warm / Cold / Humid, humidity, battery and last seen). Search by ID, name or room (press `/` to jump to it), filter by status with live counts. The chosen view is remembered.
- **Device details:** reading tiles, a temperature and humidity trend chart over the last 20, 50 or 100 readings, the history table, and the device's info, commands, firmware and alerts. The selected sensor is in the address (`?sensor=SENSOR-001`), so it can be bookmarked or shared, and Back closes it.
- **Signed-out home (Phase 19):** a split screen with an animated scene (a house drawing itself, lit windows, signal ripples, floating glass widgets over a moving colour mesh) and a card with **Sign in** / **Create account** tabs. *Forgot username or password?* asks for the email; an emailed link (`?reset=…`) opens **Choose a new password**. Password fields have Show / Hide, a Caps Lock warning, and a strength bar on new passwords; confirm fields must match before anything is sent. Success and wait states are explicit ("Request sent", "Check your email").
- **Users (ADMIN):** list with email, add (with email and a role hint), change any other account's role in place, delete; sign-ups waiting for approval are listed apart with **Approve as <role>** and **Reject**, and a "waiting" count. An admin can't change or delete their own account.
- **Feedback:** toasts confirm what happened ("Restart sent to SENSOR-001"); errors stay inline next to the action. Disruptive actions ask first in a dialog (restart a device, delete a user); Escape cancels.
- **Motion:** sections rise in, numbers count to their value, a reading that changed glows once, cards lift on hover, a slow aurora moves behind the content, loading shows shimmering placeholders. With "reduce motion" set in the OS, nothing moves.
- **Theme:** Light, Dark or System (the default), remembered per browser and applied before the first paint.
- **No extra dependencies:** icons are inline SVG ([Icons.tsx](../../frontend/src/components/Icons.tsx)), fonts are the system's, the chart is hand-drawn SVG, the dialog is the native `<dialog>`. So the strict Content-Security-Policy needs no exceptions, and no request leaves the site.
- **Phone width:** two tiles per row, one card per row, the table scrolls inside its card, long names end in "…", and the page never scrolls sideways (UI tests check list and rooms views).

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
- **Commands** (Phase 15d): the 10 newest commands with status badge (SENT amber, SUCCEEDED green, FAILED / TIMED_OUT red), the sensor's answer, who sent it and when. For OPERATOR+: **Request reading**, **Restart** (asks for confirmation first, Phase 18) and **Set interval** (1–3600 s). While a command is SENT, the list is refetched every second until the answer arrives. A refused send shows the API's reason, for example "MQTT broker unreachable".
- **Firmware** (Phase 15e): the 5 newest updates (status badge, `from → to` version, the failure reason, who started it), polled every second while one is running. For OPERATOR+: a version picker (only versions the sensor doesn't already run) and **Update**, disabled while an update is in progress.

Below the sensor table, the **Firmware** library lists uploaded images (version, file, size, SHA-256 prefix, uploader). ADMIN gets an upload form: a version like `1.1.0` and a file of at most 1 MiB. File names are made API-safe before upload, for example `my firmware.bin` becomes `my_firmware.bin`.

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

Stable `data-testid` attributes for Playwright (Phase 13): `sensor-table`, `sensor-row-{SENSOR_ID}`, and per cell `sensor-id` (a button that opens the details), `temperature`, `humidity`, `battery`, `status`, `last-seen`, plus `error-banner`, `sensors-empty`, `loading`, `last-updated`. Alerts: `alerts-panel`, `alerts-none`, `alert-{id}`, and per alert `alert-severity`, `alert-sensor`, `alert-message`, `alert-since`. Sign-in: `login-form`, `login-username`, `login-password`, `login-submit`, `login-error`, `login-notice`, `user-menu`, `user-name`, `user-role`, `logout`. Details: `sensor-details`, `details-close`, `details-name`, `details-location`, `details-firmware`, `history-table`, `history-empty`, `details-alerts`, `details-alerts-empty`, `edit-sensor`, `edit-name`, `edit-location`, `edit-save`, `edit-message`. Commands: `commands`, `cmd-request`, `cmd-restart`, `cmd-interval-value`, `cmd-interval`, `cmd-error`, `commands-empty`, `command-list`, `command-{id}`, and per item `command-status`, `command-name`, `command-message`. Firmware: `firmware-panel`, `fw-form`, `fw-select`, `fw-start`, `fw-error`, `fw-none`, `fw-updates`, `fw-update-{id}` (`fw-status`, `fw-versions`, `fw-message`), and the library `firmware-library`, `fw-library`, `fw-library-empty`, `fw-image-{version}`, `fw-upload`, `fw-version`, `fw-file`, `fw-upload-submit`, `fw-upload-message`. Phase 18: `device-search`, `filter-{all,online,offline,error}`, `sort-{id,temperature,humidity,battery,status,last_seen}`, `view-list`, `view-grid`, `device-grid`, `device-card-{SENSOR_ID}`, `devices-count`, `devices-no-match`, `devices-clear`, `home-status`, `home-status-headline`, `nav-{section}`, `theme-{light,dark,system}`, `range-{20,50,100}`, `confirm-dialog`, `confirm-ok`, `confirm-cancel`, `toasts`, `toast`, `users-panel`, `users-table`, `user-row-{name}`, `user-role-cell`, `user-delete`, `user-form`, `user-new-name`, `user-new-password`, `user-new-role`, `user-create`, `users-error`. Phase 19: `auth-page`, `auth-tab-signin`, `auth-tab-signup`, `auth-flash`, `forgot-link`, `signup-form`, `signup-username`, `signup-email`, `signup-password`, `signup-confirm`, `signup-submit`, `signup-error`, `signup-done`, `forgot-form`, `forgot-email`, `forgot-submit`, `forgot-error`, `forgot-done`, `reset-form`, `reset-password`, `reset-confirm`, `reset-submit`, `reset-error`, `reset-new-link`, `back-to-signin`, `{field}-toggle`, `{field}-caps`, `password-strength`, `pending-users`, `pending-{name}`, `pending-count`, `approve-role`, `approve`, `reject`, `user-new-email`.

UI tests sign in by putting a session into `sessionStorage` before the page loads (`open_dashboard(role)` in `tests/ui/conftest.py`). E2E tests sign in through the real form and API.

## Offline sensors

Since Phase 15a, a sensor with no stored reading for 30 s (`OFFLINE_TIMEOUT`) is shown as OFFLINE and gets an OFFLINE alert. It turns ONLINE again with its next reading. See [alerts.md](../architecture/alerts.md).
