# Project Plan — SmartIoT Sensor Quality Engineering Platform

This project is built **one phase at a time**. A phase is not started until the previous phase is implemented, manually verified, tested (positive + negative), documented, and committed. See "Definition of Done" below.

## Phase roadmap

- [x] **Phase 0** — Project definition, repository scaffold, foundational docs
- [~] **Phase 1** — Development environment verification (Python, Node.js, Git, Docker Desktop, VS Code) *(partially confirmed: Python 3.12.6, Docker 29.7.2 verified working; Node.js/Git not yet checked)*
- [x] **Phase 2** — MQTT broker (Mosquitto) proven working with a minimal publisher/subscriber
- [x] **Phase 3** — First simulated sensor (SENSOR-001): connect, generate realistic telemetry, publish, reconnect on failure, stop cleanly *(includes Phase 4/5 scope — data generator and MQTT publisher were built together as one working sensor, not separately)*
- [x] **Phase 6** — MQTT receiver (subscribes to `iot/sensors/+/telemetry`)
- [x] **Phase 7** — Telemetry validation (parser + validator, reject invalid messages)
- [ ] **Phase 8** — MySQL database (`smart_iot`: sensors, telemetry, alerts tables) *(next)*
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

**Phase 7 complete.** `receiver/` now parses and validates every message before accepting it, per the architecture principle "the receiver never trusts incoming data": `parser/message_parser.py` (`MessageParser` — decodes UTF-8, parses JSON, confirms it's an object; raises `ParseError` otherwise, no validation logic) and `validator/telemetry_validator.py` (`TelemetryValidator` — checks all required fields present, correct non-bool numeric types, and within the ranges from [sensor-behavior.md](docs/architecture/sensor-behavior.md); returns a list of error strings, empty = valid). `main.py`'s message handler now parses, then validates, then logs either `Accepted telemetry ...` or `Rejected message ...` with the reason(s) — still no database write, that's Phase 9. Verified (manually, broker in Docker, simulator running live):
- Positive: valid telemetry from `sensor-simulator` logged as accepted.
- Negative: invalid JSON, a message missing a required field (`battery`), an out-of-range value (`temperature=999`), and a wrong type (`humidity` as a string) were each rejected with a clear, specific reason; receiver kept running after every one.
- Boundary: a message with every field set to its exact min/max (`temperature=-40`, `humidity=100`, `pressure=1100`, `light=100000`, `battery=0`) was correctly accepted — confirms the range checks are inclusive, not off-by-one.

Next: **Phase 8** — MySQL database (`smart_iot`: `sensors`, `telemetry`, `alerts` tables) — schema only at this phase, per [database.md](docs/architecture/database.md); the receiver doesn't write to it until Phase 9.

**Phase 6 (previous).** `receiver/` subscribed to `iot/sensors/+/telemetry` and logged every message received, with the same separated structure as the simulator: `mqtt/` (subscribe/reconnect wrapper), `config/` (`.env`-driven settings). Verified: receiver logs the simulator's live telemetry byte-for-byte; wildcard subscription confirmed with a second sensor ID; malformed/empty payloads logged without crashing; survives a Mosquitto broker stop/restart (auto-reconnect + resubscribe).

**Phase 3 (previous).** `sensor-simulator/` implements SENSOR-001 with separated responsibilities per the architecture doc: `sensors/` (identity/state), `generator/` (realistic gradual-drift values within the documented ranges), `mqtt/` (connect/publish/reconnect), `config/` (`.env`-driven settings). Verified:
- Positive: connects to Mosquitto, publishes valid telemetry matching the required schema every `SENSOR_INTERVAL` seconds, values drift realistically instead of jumping, subscriber receives every message.
- Negative/reliability: found and fixed a crash-on-startup bug when the broker is unreachable (blocking `connect()` raised `ConnectionRefusedError`); switched to `connect_async` + made `publish()` fail soft (log + skip) instead of raising. Verified the sensor keeps running with the broker down, and auto-reconnects and resumes publishing once the broker comes back — no restart needed.
