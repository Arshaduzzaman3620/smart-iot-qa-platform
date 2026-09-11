# SmartIoT Sensor Quality Engineering Platform

A fully simulated, fictional IoT sensor platform built to learn and demonstrate Software Quality Assurance and test automation end-to-end: Python, TypeScript, MQTT, FastAPI, MySQL, Playwright, pytest, Docker, CI/CD, and AI-assisted QA.

**This project uses no real hardware, company code, company data, or company credentials.** Every sensor, message, and dataset is fictional, generated entirely from scratch for learning purposes.

## What this is

A virtual IoT sensor sends fictional telemetry (temperature, humidity, pressure, light, battery) over MQTT. A receiver service validates and stores that data in MySQL. A FastAPI backend exposes it over REST. A web dashboard displays it. Every layer of that pipeline is covered by automated tests — unit, API, MQTT, integration, end-to-end, performance, security, and reliability — built up one phase at a time.

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

Currently: **Phase 0 — Project definition and repository scaffold.**

## Documentation

- [Requirements](docs/requirements/requirements.md)
- [Architecture](docs/architecture/architecture.md)
- [Sensor behavior](docs/architecture/sensor-behavior.md)
- [MQTT topic design](docs/mqtt/topics.md)
- [Database structure](docs/architecture/database.md)
- [Testing strategy](docs/testing/strategy.md)
