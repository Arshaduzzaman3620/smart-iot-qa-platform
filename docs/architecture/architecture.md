# Architecture

## Components

1. Sensor Simulator — generates fictional telemetry and publishes it over MQTT
2. MQTT Broker (Mosquitto) — routes messages between sensors and the receiver
3. MQTT Receiver — subscribes to telemetry, parses and validates it
4. Data Validator — enforces value ranges and required fields
5. Data Processor — enriches valid telemetry, updates sensor state, raises alerts
6. MySQL Database — stores sensors, telemetry, alerts, users, firmware, firmware_updates
7. FastAPI Backend — REST API over the stored data, auth, sensor commands
8. Web Dashboard (React/TypeScript) — displays sensors, telemetry, alerts
9. Test Automation Framework — unit, API, MQTT, integration, E2E, security, performance
10. FOTA Simulation — fictional firmware update flow
11. Failure Injection — intentional faults for reliability testing
12. Docker Environment — containerizes every service
13. CI/CD Pipeline — GitHub Actions running the full test suite on push
14. AI QA Assistant — generates test cases and assists failure analysis

## Data flow

```text
SENSOR SIMULATOR (SENSOR-001 ... SENSOR-100)
        |
        | MQTT Publish (iot/sensors/{sensor_id}/telemetry)
        v
   MQTT BROKER (Mosquitto)
        |
        | MQTT Subscribe (iot/sensors/+/telemetry)
        v
   MQTT RECEIVER
        |
  +-----+------+
  |            |
VALIDATION  PROCESSING
  |            |
  +-----+------+
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
     Playwright / pytest / k6
```

## Design principles

- Each service owns one responsibility (simulator ≠ MQTT client ≠ data generator ≠ database logic). See [sensor-behavior.md](sensor-behavior.md) for how this separation applies inside the simulator.
- The receiver never trusts incoming data — every message is parsed, then validated, before it touches the database.
- Configuration lives in `.env` (see `.env.example`), never hard-coded.
- The system is built and verified one phase at a time; see [PROJECT_PLAN.md](../../PROJECT_PLAN.md).
