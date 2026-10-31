# SmartIoT Sensor Quality Engineering Platform

A smart-home IoT platform with simulated sensors, built to demonstrate professional Software Quality Assurance and test automation end to end: Python, TypeScript, MQTT, FastAPI, MySQL, Playwright, pytest, Docker, CI/CD, and AI-assisted QA.



## What this is

Simulated sensors send telemetry (temperature, humidity, pressure, light, battery) over MQTT. A receiver validates it and stores it in MySQL, raising alerts and spotting offline sensors. A FastAPI backend serves it with role-based access. A React dashboard shows it, and lets operators send commands and roll out firmware. Every layer is covered by automated tests, from unit tests to outage and load tests, built up one phase at a time.

**Results:** 813 automated tests in 7 layers, all passing. 0 readings lost or duplicated through database, broker and receiver outages. 303 API requests/s at 300 concurrent users with 0 % errors. 41 defects found and fixed along the way. Full picture: **[Final QA report](docs/testing/final-report.md)**.

## Quick start

The only requirement is [Docker Desktop](https://www.docker.com/products/docker-desktop/). The same commands work on macOS, Windows and Linux.

```bash
docker compose up -d --build                                  # the whole platform, with 5 simulated sensors
# dashboard: https://localhost:8443  (sign in: admin / admin-dev-password)
# emails:    http://localhost:8025     (Mailpit: welcome and password reset emails)
# API docs:  https://localhost:8443/api/docs
# First time: trust certs/ca.crt, or the browser warns (docs/security/tls.md)

docker compose -f compose.test.yaml run --rm --build tests     # all 813 tests (~5 min)
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
| Accounts | Admin-managed accounts with email and roles, welcome email, forgot username / password by email with one-time reset links, sessions end on reset (Mailpit as local inbox) | [accounts](docs/api/auth.md#accounts-and-recovery-phase-19) |
| Commands | Restart, request a reading, change the interval, with each outcome tracked | [commands](docs/architecture/commands.md) |
| Firmware over the air | Upload, scoped download tokens, verified install and reboot, injectable failures | [FOTA](docs/architecture/fota.md) |
| Reliability | At-least-once with deduplication through MySQL, broker and receiver failures | [reliability](docs/testing/reliability.md) |
| Security | Broker accounts and ACLs, CSP and security headers, hostile-input tests, dependency audit | [security](docs/security/security.md) |
| TLS | HTTPS dashboard and API, MQTT over TLS, MySQL TLS, certificate and host-name checks everywhere, production configuration check | [TLS](docs/security/tls.md) |
| Performance | k6 load, stress, spike and soak; 100-sensor ingestion check | [performance](docs/testing/performance.md) |
| Dashboard experience | Home status banner, list and rooms views, search (`/`), status filter, sorting, users screen, confirmations, toasts, light / dark theme, bookmarkable sensors, motion that respects reduced-motion | [dashboard](docs/frontend/dashboard.md) |
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
| TLS | Private CA generated with `cryptography`; nginx (HTTP/2), Mosquitto 8883, MySQL `require_secure_transport` |
| Containers and CI | Docker Compose, GitHub Actions (tests, full-stack start, dependency audit) |

## Development phases

This project is built one phase at a time, with a commit + pull request + merge cycle after each phase is verified working. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full phase-by-phase roadmap and current progress.

Currently: **all phases are complete** (0–19). A one-page summary for presenting the project: [docs/project-brief.md](docs/project-brief.md). See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the history and the [final QA report](docs/testing/final-report.md) for the results.

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
