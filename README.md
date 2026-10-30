# SmartIoT Sensor Quality Engineering Platform

A fully simulated, fictional IoT sensor platform built to learn and demonstrate Software Quality Assurance and test automation end-to-end: Python, TypeScript, MQTT, FastAPI, MySQL, Playwright, pytest, Docker, CI/CD, and AI-assisted QA.

**This project uses no real hardware, company code, company data, or company credentials.** Every sensor, message, and dataset is fictional, generated entirely from scratch for learning purposes.

## What this is

A virtual IoT sensor sends fictional telemetry (temperature, humidity, pressure, light, battery) over MQTT. A receiver service validates and stores that data in MySQL. A FastAPI backend exposes it over REST. A web dashboard displays it. Every layer of that pipeline is covered by automated tests — unit, API, MQTT, integration, end-to-end, performance, security, and reliability — built up one phase at a time.

## Quick start

The only requirement is [Docker Desktop](https://www.docker.com/products/docker-desktop/). The same commands work on macOS, Windows and Linux.

```bash
docker compose up -d --build                                  # the whole platform
# dashboard: http://localhost:8080    API docs: http://localhost:8000/docs

docker compose -f compose.test.yaml run --rm --build tests     # the whole test suite
docker compose down                                           # stop
```

Running services with Python and Node on the host instead, plus troubleshooting: [docs/development/setup.md](docs/development/setup.md).

## Architecture

```text
VIRTUAL SENSOR
     |
     | Generate Data
     v
MQTT PUBLISH
     |
     v
MQTT BROKER (Mosquitto)
     |
     v
MQTT RECEIVER
     |
     v
PARSER -> VALIDATOR
     |
   +-+-----------------+
   | VALID              | INVALID
   v                     v
PROCESS               REJECT + LOG
   |
   v
MySQL
   |
   v
FastAPI
   |
   v
Web Dashboard
   |
   v
Automated Testing (Playwright / pytest / k6)
```

## Tech stack

| Layer | Technology |
|---|---|
| Sensor simulator | Python, paho-mqtt |
| Message broker | Mosquitto (MQTT) |
| Receiver | Python, paho-mqtt |
| Backend API | Python, FastAPI, Pydantic, SQLAlchemy |
| Database | MySQL |
| Frontend | TypeScript, React |
| UI automation | Playwright |
| API automation | pytest, httpx |
| Performance | k6 |
| Containerization | Docker, Docker Compose |
| CI/CD | GitHub Actions |

## Development phases

This project is built one phase at a time, with a commit + pull request + merge cycle after each phase is verified working. See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full phase-by-phase roadmap and current progress.

Currently: **Phase 15d — sensor commands** is complete: operators restart sensors, request readings and change intervals from the dashboard, through the API and MQTT, with each command's outcome tracked. Before it: JWT sign-in with VIEWER / OPERATOR / ADMIN roles (15c), and the whole platform and test suite running in Docker on any OS, with CI. 490 automated tests. Phase 15 continues with FOTA, reliability, security and performance. See [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Documentation

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
