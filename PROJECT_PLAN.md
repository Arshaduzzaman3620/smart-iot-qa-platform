# Project Plan — SmartIoT Sensor Quality Engineering Platform

This project is built **one phase at a time**. A phase is not started until the previous phase is implemented, manually verified, tested (positive + negative), documented, and committed. See "Definition of Done" below.

## Phase roadmap

- [x] **Phase 0** — Project definition, repository scaffold, foundational docs
- [~] **Phase 1** — Development environment verification (Python, Node.js, Git, Docker Desktop, VS Code) *(partially confirmed: Python 3.12.6, Docker 29.7.2 verified working; Node.js/Git not yet checked)*
- [x] **Phase 2** — MQTT broker (Mosquitto) proven working with a minimal publisher/subscriber
- [ ] **Phase 3** — First simulated sensor (SENSOR-001 only): connect, generate, publish, stop cleanly *(next)*
- [ ] **Phase 4** — Sensor data generator (temperature, humidity, pressure, light, battery)
- [ ] **Phase 5** — Sensor MQTT publisher (telemetry topic + payload)
- [ ] **Phase 6** — MQTT receiver (subscribes to `iot/sensors/+/telemetry`)
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

**Phase 2 complete.** Mosquitto broker runs in Docker (`docker/mosquitto/mosquitto.conf`), proven working end to end with `scripts/mqtt_poc_publisher.py` and `scripts/mqtt_poc_subscriber.py` — see [docs/mqtt/topics.md](docs/mqtt/topics.md#phase-2-verification-mqtt-broker-proven-working) for details. Project virtual environment (`.venv`) created with `paho-mqtt` installed.

Next: **Phase 3** — build the first real simulated sensor (SENSOR-001), replacing the throwaway PoC scripts.
