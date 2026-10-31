# SmartIoT Sensor Quality Engineering Platform

A fully simulated, fictional IoT sensor platform built to learn and demonstrate Software Quality Assurance and test automation end-to-end: Python, TypeScript, MQTT, FastAPI, MySQL, Playwright, pytest, Docker, CI/CD, and AI-assisted QA.



## What this is

Virtual sensors send fictional telemetry (temperature, humidity, pressure, light, battery) over MQTT. A receiver validates it and stores it in MySQL, raising alerts and spotting offline sensors. A FastAPI backend serves it with role-based access. A React dashboard shows it, and lets operators send commands and roll out firmware. Every layer is covered by automated tests, from unit tests to outage and load tests, built up one phase at a time.

**Results:** 703 automated tests in 7 layers, all passing. 0 readings lost or duplicated through database, broker and receiver outages. 303 API requests/s at 300 concurrent users with 0 % errors. 31 defects found and fixed along the way. Full picture: **[Final QA report](docs/testing/final-report.md)**.

## Quick start

The only requirement is [Docker Desktop](https://www.docker.com/products/docker-desktop/). The same commands work on macOS, Windows and Linux.

```bash
docker compose up -d --build                                  # the whole platform, with 5 simulated sensors
# dashboard: http://localhost:8080  (sign in: admin / admin-dev-password)
# API docs:  http://localhost:8000/docs

docker compose -f compose.test.yaml run --rm --build tests     # all 703 tests (~3.5 min)
docker compose --profile perf run --rm k6 run -e PROFILE=load /scripts/api.js   # load test
docker compose down                                           # stop
```

Running services with Python and Node on the host instead, plus troubleshooting: [docs/development/setup.md](docs/development/setup.md).

## Features

| Area | What it does | Docs |
|---|---|---|
| Telemetry pipeline | Sensors → MQTT → receiver (parse, validate, store in batches) → MySQL → API → dashboard | [architecture](docs/architecture/architecture.md), [database](docs/architecture/database.md) |
| Alerts | Threshold alerts (battery, temperature, humidity) with escalation and hysteresis; offline detection | [alerts](docs/architecture/alerts.md) |
| Access control | JWT sign-in, VIEWER / OPERATOR / ADMIN, user management, login rate limiting | [auth](docs/api/auth.md) |
| Commands | Restart, request a reading, change the interval, with each outcome tracked | [commands](docs/architecture/commands.md) |
| Firmware over the air | Upload, scoped download tokens, verified install and reboot, injectable failures | [FOTA](docs/architecture/fota.md) |
| Reliability | At-least-once with deduplication through MySQL, broker and receiver failures | [reliability](docs/testing/reliability.md) |
| Security | Broker accounts and ACLs, CSP and security headers, hostile-input tests, dependency audit | [security](docs/security/security.md) |
| Performance | k6 load, stress, spike and soak; 100-sensor ingestion check | [performance](docs/testing/performance.md) |
| AI QA assistant | Claude generates test cases from requirements and analyses failing runs, grounded in these docs | [AI QA assistant](docs/testing/ai-qa-assistant.md) |

## Architecture

```text
SENSOR SIMULATOR (SENSOR-001 … SENSOR-100)          dashboard (React, nginx)
   | telemetry, status, responses   ^ commands,            | /api
   v  (QoS 1, buffered)             | firmware             v
MQTT BROKER (Mosquitto: accounts + ACLs) <------------ FastAPI (JWT roles)
   |                                                        ^
   v                                                        |
RECEIVER: parse -> validate -> batch writer -> MySQL -------+
          alerts, offline detection, command / firmware outcomes
```

## Tech stack

| Layer | Technology |
|---|---|
| Sensor simulator | Python, paho-mqtt |
| Message broker | Mosquitto (MQTT), password file + ACLs |
| Receiver | Python, paho-mqtt (persistent session, manual acks), SQLAlchemy |
| Backend API | Python, FastAPI, Pydantic, SQLAlchemy, PyJWT |
| Database | MySQL 8.4 |
| Frontend | TypeScript, React, Vite; nginx in production |
| Test automation | pytest, httpx, Playwright (Python), paho-mqtt |
| Performance | k6 |
| AI-assisted QA | Claude API (Anthropic Python SDK, structured outputs) |
| Containers and CI | Docker Compose, GitHub Actions (tests, full-stack start, dependency audit) |

## Development phases

This project is built one phase at a time, with a commit + pull request + merge cycle after each phase is verified working. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full phase-by-phase roadmap and current progress.

Currently: **all phases are complete** (0–16). See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the history and the [final QA report](docs/testing/final-report.md) for the results.

## Documentation

- [Final QA report](docs/testing/final-report.md)
- [Development setup](docs/development/setup.md)
- [Requirements](docs/requirements/requirements.md)
- [Architecture](docs/architecture/architecture.md)
- [Sensor behavior](docs/architecture/sensor-behavior.md)
- [MQTT topic design](docs/mqtt/topics.md)
- [Database structure](docs/architecture/database.md)
- [REST API](docs/api/endpoints.md)
- [Authentication and roles](docs/api/auth.md)
- [Web dashboard](docs/frontend/dashboard.md)
- [Testing strategy](docs/testing/strategy.md)
- [Manual E2E verification](docs/testing/e2e-manual-verification.md)
- [Test automation](docs/testing/automation.md)
- [Multi-sensor scale results](docs/testing/scale-results.md)
- [Alerts and offline detection](docs/architecture/alerts.md)
- [Sensor commands](docs/architecture/commands.md)
- [Firmware over the air](docs/architecture/fota.md)
- [Reliability and failure injection](docs/testing/reliability.md)
- [Security](docs/security/security.md)
- [Performance](docs/testing/performance.md)
- [AI QA assistant](docs/testing/ai-qa-assistant.md)
