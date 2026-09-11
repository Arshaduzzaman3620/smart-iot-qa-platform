# Testing Strategy

## Test pyramid

```text
              E2E
             /   \
        Integration
          /       \
        API       MQTT
         \         /
             Unit
```

Not every test should be an E2E test — most coverage should sit at the unit and API/MQTT layers.

## Layers

- **Unit** — `DataGenerator`, `TelemetryValidator`, `MessageParser`, `AlertService`, `SensorService`, `FirmwareService`.
- **API** — FastAPI endpoints: positive, negative, and boundary tests (pytest + httpx). Covers auth, authorization, validation, error handling.
- **MQTT** — publish/subscribe, reconnect, invalid payloads, commands/responses (pytest + paho-mqtt).
- **Integration** — the full receive chain: sensor → MQTT → receiver → validator → processor → MySQL.
- **E2E** — full stack including the dashboard, verified with Playwright: sensor publishes → MQTT → receiver → validate → MySQL → FastAPI → dashboard displays the same values.
- **Performance** — k6, at 10 / 50 / 100 simulated sensors: normal load, stress, spike, soak.
- **Security** — authN/authZ, role permissions, invalid/expired tokens, SQL injection, XSS, input validation, rate limiting.
- **Reliability** — broker/receiver/MySQL/FastAPI/sensor restarts; measure recovery time, data loss, error rate.

## Negative testing baseline

Every validated input path (telemetry, sensor create/update, auth) must have negative and boundary cases: missing required fields, invalid types, out-of-range values, invalid JSON, unauthorized access. See sensor-behavior.md's data ranges table for the boundary values to use.

## Test data

Reusable fixtures under `tests/test-data/`: `valid_sensors.json`, `invalid_sensors.json`, `telemetry.json`, `users.json`, `firmware.json` — created when test automation begins (Phase 13), not before.

Automation is not written until the underlying feature works manually — see [PROJECT_PLAN.md](../../PROJECT_PLAN.md) workflow.
