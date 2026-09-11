# Requirements

## Functional requirements

- Simulate fictional IoT sensors that generate realistic telemetry (temperature, humidity, pressure, light, battery) without any real hardware.
- Publish telemetry over MQTT on a per-sensor topic.
- Receive, parse, and validate incoming telemetry messages; reject and log anything malformed or out of range.
- Persist valid telemetry, sensor status, and alerts in MySQL.
- Expose stored data through a REST API (FastAPI) with authentication and role-based authorization.
- Display sensor data on a web dashboard (list, details, telemetry history, alerts).
- Support sensor commands (restart, request telemetry, change reporting interval) issued from the dashboard via the API and MQTT.
- Support simulated firmware-over-the-air (FOTA) updates, including failure scenarios.
- Scale from 1 sensor up to 100 concurrently simulated sensors.
- Cover every layer with automated tests: unit, API, MQTT, integration, end-to-end, performance, security, reliability.
- Run the full stack in Docker Compose, with CI/CD via GitHub Actions.

## Non-functional requirements

- No dependency on physical hardware, company code, company data, company networks, or company credentials — everything is fictional and self-contained.
- All configuration (DB credentials, MQTT host/port, API port) via `.env`, never hard-coded; `.env` is never committed.
- Each service (simulator, receiver, backend, frontend) has clear, separated responsibilities — no mixing of MQTT logic with business/calculation logic.
- Logs must be useful (connection events, validation results, errors) and must never contain secrets.
- The system must degrade gracefully: invalid telemetry is rejected and logged, not allowed to corrupt the database or crash a service.
- Development proceeds one phase at a time (see [PROJECT_PLAN.md](../../PROJECT_PLAN.md)); a phase is not considered complete until manually verified and tested.
