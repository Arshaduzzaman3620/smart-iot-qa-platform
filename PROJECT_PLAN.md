# Project Plan — SmartIoT Sensor Quality Engineering Platform

This project is built **one phase at a time**. A phase is not started until the previous phase is implemented, manually verified, tested (positive + negative), documented, and committed. See "Definition of Done" below.

## Phase roadmap

- [x] **Phase 0** — Project definition, repository scaffold, foundational docs
- [~] **Phase 1** — Development environment verification (Python, Node.js, Git, Docker Desktop, VS Code) *(partially confirmed: Python 3.12.6, Docker 29.7.2 verified working; Node.js/Git not yet checked)*
- [x] **Phase 2** — MQTT broker (Mosquitto) proven working with a minimal publisher/subscriber
- [x] **Phase 3** — First simulated sensor (SENSOR-001): connect, generate realistic telemetry, publish, reconnect on failure, stop cleanly *(includes Phase 4/5 scope — data generator and MQTT publisher were built together as one working sensor, not separately)*
- [ ] **Phase 6** — MQTT receiver (subscribes to `iot/sensors/+/telemetry`) *(next)*
- [ ] **Phase 7** — Telemetry validation (parser + validator, reject invalid messages)
- [ ] **Phase 8** — MySQL database (`smart_iot`: sensors, telemetry, alerts tables)
- [ ] **Phase 9** — Receiver writes validated telemetry into MySQL (first full data flow: sensor → MQTT → receiver → validate → MySQL)
- [ ] **Phase 10** — FastAPI backend (`/health`, `/sensors`, `/sensors/{id}`, `/sensors/{id}/telemetry`)
- [ ] **Phase 11** — Frontend dashboard (basic sensor table: ID, temperature, humidity, battery, status, last seen)
- [ ] **Phase 12** — Full first E2E flow verified manually (sensor → MQTT → receiver → validate → MySQL → FastAPI → dashboard)
- [ ] **Phase 13** — Test automation foundation (unit, API, MQTT, integration, UI, E2E)
- [ ] **Phase 14** — Scale to multiple sensors (5 → 10 → 50 → 100)
- [ ] **Phase 15** — Advanced features: alerts, commands, authentication, FOTA, failure injection, performance, security, reliability
- [ ] **Phase 16** — Final portfolio polish: docs, reports, CI/CD, AI QA assistant, final regression

## Definition of Done (per phase)

- [ ] Implementation completed
- [ ] Application runs
- [ ] Manual verification completed
- [ ] Positive tests completed
- [ ] Negative tests completed
- [ ] Errors handled
- [ ] Logs added
- [ ] Documentation updated
- [ ] Ready to commit (owner commits, pushes, and merges)

## Workflow per phase

1. Implement the phase's scope only — nothing from later phases.
2. Verify manually (run it, see the expected result).
3. Add positive and negative tests where applicable.
4. Update relevant docs under `docs/`.
5. When the phase is finished, it's reported as ready — commit, branch, push, PR, and merge are all done by the repo owner, not automated.
6. Check this file's roadmap box, move to the next phase.

## Current status

**Phase 3 complete.** `sensor-simulator/` implements SENSOR-001 with separated responsibilities per the architecture doc: `sensors/` (identity/state), `generator/` (realistic gradual-drift values within the documented ranges), `mqtt/` (connect/publish/reconnect), `config/` (`.env`-driven settings). Verified:
- Positive: connects to Mosquitto, publishes valid telemetry matching the required schema every `SENSOR_INTERVAL` seconds, values drift realistically instead of jumping, subscriber receives every message.
- Negative/reliability: found and fixed a crash-on-startup bug when the broker is unreachable (blocking `connect()` raised `ConnectionRefusedError`); switched to `connect_async` + made `publish()` fail soft (log + skip) instead of raising. Verified the sensor keeps running with the broker down, and auto-reconnects and resumes publishing once the broker comes back — no restart needed.

Next: **Phase 6** — MQTT receiver that subscribes to `iot/sensors/+/telemetry` and logs received messages (no validation/database yet, per the spec's own "first development target").
