# Architecture

SmartIoT is a set of small services, each with a single responsibility, connected by MQTT (devices) and HTTPS (people). Every connection is encrypted and authenticated, and every service runs in its own container.

- [System overview](#system-overview)
- [Components](#components)
- [Telemetry: from a sensor to the screen](#telemetry-from-a-sensor-to-the-screen)
- [Commands and firmware updates](#commands-and-firmware-updates)
- [Security boundaries](#security-boundaries)
- [Deployment view](#deployment-view)
- [Design principles](#design-principles)

## System overview

```mermaid
flowchart LR
    U(["People<br/>viewer · operator · admin"])

    subgraph Devices["Devices (simulated)"]
        S["Sensor simulator<br/>SENSOR-001 … 100"]
    end

    subgraph Platform["SmartIoT platform"]
        N["nginx<br/>dashboard + /api proxy"]
        API["FastAPI<br/>REST API"]
        B[("Mosquitto<br/>MQTT broker")]
        R["Receiver<br/>parse · validate · store"]
        DB[("MySQL 8.4")]
        M["Mail server<br/>(Mailpit locally)"]
    end

    U -- HTTPS --> N
    N --> API
    API --> DB
    API -- "commands,<br/>firmware updates" --> B
    API -- "welcome and<br/>reset emails" --> M
    S -- "telemetry, status,<br/>command results" --> B
    B -- "commands,<br/>firmware updates" --> S
    B --> R
    R --> DB
    S -. "firmware download<br/>(HTTPS, one-time token)" .-> N

    classDef person fill:#dbeafe,stroke:#2563eb,stroke-width:1px,color:#0b2447;
    classDef device fill:#f1f5f9,stroke:#475569,stroke-width:1px,color:#0f172a;
    classDef edge fill:#e0e7ff,stroke:#4f46e5,stroke-width:1px,color:#1e1b4b;
    classDef service fill:#ede9fe,stroke:#7c3aed,stroke-width:1px,color:#2e1065;
    classDef broker fill:#fef3c7,stroke:#d97706,stroke-width:1px,color:#7c2d12;
    classDef store fill:#dcfce7,stroke:#16a34a,stroke-width:1px,color:#14532d;
    classDef mail fill:#fce7f3,stroke:#db2777,stroke-width:1px,color:#831843;
    class U person;
    class S device;
    class N edge;
    class API,R service;
    class B broker;
    class DB store;
    class M mail;
```

## Components

| Component | Responsibility | Code | Details |
|---|---|---|---|
| Sensor simulator | Generates realistic readings for up to 100 sensors, answers commands, installs firmware; can inject faults | `sensor-simulator/` | [sensor behaviour](sensor-behavior.md) |
| MQTT broker | Routes device messages; one account per role, topic ACLs, TLS on 8883 | `docker/mosquitto/` | [topics](../mqtt/topics.md) |
| Receiver | Parses and validates every message, stores telemetry in batches, raises alerts, detects offline sensors, records command and firmware outcomes | `receiver/` | [alerts](alerts.md) |
| Database | Sensors, telemetry, alerts, commands, firmware, users, reset links; schema created and upgraded at start | `database/` | [database](database.md) |
| REST API | Sign-in and roles, sensor data, alerts, commands, firmware, user administration, account recovery | `backend/app/` | [endpoints](../api/endpoints.md), [auth](../api/auth.md) |
| Dashboard | React single-page app served by nginx over HTTPS, which also proxies `/api` | `frontend/`, `docker/nginx.conf.template` | [dashboard](../frontend/dashboard.md) |
| Certificates | Creates a private CA and server certificate on first start, or uses real ones | `docker/tls/` | [TLS](../security/tls.md) |
| Test framework | Unit, API, MQTT, integration, reliability, UI and end-to-end tests; k6 load tests | `tests/`, `perf/` | [strategy](../testing/strategy.md) |
| AI QA assistant | Turns requirements into test cases and explains failing runs, using the Claude API | `qa-assistant/` | [AI QA assistant](../testing/ai-qa-assistant.md) |

## Telemetry: from a sensor to the screen

```mermaid
sequenceDiagram
    autonumber
    participant S as Sensor
    participant B as Broker
    participant R as Receiver
    participant DB as MySQL
    participant API as API
    participant D as Dashboard

    S->>B: publish iot/sensors/SENSOR-001/telemetry (QoS 1, TLS)
    B->>R: deliver (persistent session)
    R->>R: parse JSON, validate ranges and fields
    alt valid
        R->>DB: store in a batch, skipping an identical reading already stored
        R->>DB: update the sensor's state, open or close alerts
        R-->>B: acknowledge only after the commit
    else invalid
        R->>R: log the reason, acknowledge
    end
    loop every few seconds
        D->>API: GET /api/sensors (token, HTTPS)
        API->>DB: latest readings and active alerts
        API-->>D: JSON
    end
```

A reading is acknowledged only after it is stored, so a receiver or database outage delays data but never loses it, and a redelivered reading is recognised and stored once ([reliability](../testing/reliability.md)).

## Commands and firmware updates

```mermaid
sequenceDiagram
    autonumber
    actor O as Operator
    participant API as API
    participant B as Broker
    participant S as Sensor
    participant R as Receiver
    participant N as nginx

    O->>API: POST /sensors/{id}/commands (restart)
    API->>B: publish …/command
    B->>S: deliver
    S->>B: publish …/response (SUCCEEDED)
    B->>R: deliver
    R->>R: match it to the request, record the outcome

    O->>API: POST /sensors/{id}/firmware-updates
    API->>B: publish …/firmware (version, SHA-256, URL with a 10-minute token)
    B->>S: deliver
    S->>N: GET /api/firmware/{id}/download?token=…
    N-->>S: image
    S->>S: verify SHA-256, install, reboot
    S->>B: publish …/firmware_status (SUCCEEDED or FAILED)
    B->>R: deliver and record
```

A command or update with no answer becomes `TIMED_OUT`. A failed or interrupted install leaves the sensor on its previous version ([commands](commands.md), [FOTA](fota.md)).

## Security boundaries

```mermaid
flowchart TB
    subgraph Internet
        U(["Browser"])
        S["Devices"]
    end

    subgraph Host["Server: only 8443, 8080 and 8883 are published"]
        N["nginx :443<br/>TLS 1.2+, HSTS, strict CSP"]
        B["Mosquitto :8883<br/>TLS, accounts, ACLs"]
        subgraph Internal["Private Docker network"]
            API["API :8000<br/>tokens, roles, rate limits"]
            R["Receiver"]
            DB[("MySQL<br/>TLS required")]
        end
    end

    U -- HTTPS --> N
    S -- "MQTT over TLS" --> B
    S -- "HTTPS + download token" --> N
    N -- "HTTP inside Docker" --> API
    API -- TLS --> DB
    R -- TLS --> DB
    API -- TLS --> B
    R -- TLS --> B

    classDef person fill:#dbeafe,stroke:#2563eb,stroke-width:1px,color:#0b2447;
    classDef device fill:#f1f5f9,stroke:#475569,stroke-width:1px,color:#0f172a;
    classDef edge fill:#e0e7ff,stroke:#4f46e5,stroke-width:1px,color:#1e1b4b;
    classDef service fill:#ede9fe,stroke:#7c3aed,stroke-width:1px,color:#2e1065;
    classDef broker fill:#fef3c7,stroke:#d97706,stroke-width:1px,color:#7c2d12;
    classDef store fill:#dcfce7,stroke:#16a34a,stroke-width:1px,color:#14532d;
    class U person;
    class S device;
    class N edge;
    class B broker;
    class API,R service;
    class DB store;
```

| Boundary | Control |
|---|---|
| Browser → dashboard | HTTPS only (HTTP redirects), HSTS, a Content Security Policy with no inline code, security headers |
| Dashboard → API | Signed tokens (HS256, algorithm pinned), three roles checked on every request, sign-in and reset rate limits |
| Devices → broker | TLS, a password per account, topic ACLs, no anonymous access |
| Services → MySQL | TLS required by the server, a dedicated user, no root access from the app |
| Production start | `APP_ENV=production` makes the API and the broker refuse development passwords, weak secrets and missing TLS |

Threats, controls and test evidence: [security](../security/security.md) and [TLS](../security/tls.md).

## Deployment view

```mermaid
flowchart LR
    certs["certs<br/>(runs once)"] --> mqtt & mysql & dashboard
    mysql --> initdb["init-db<br/>(runs once)"]
    initdb --> receiver & api
    mqtt --> receiver
    api --> dashboard
    mqtt & receiver & dashboard --> simulator

    classDef oneshot fill:#fef9c3,stroke:#ca8a04,stroke-width:1px,color:#713f12;
    classDef svc fill:#ede9fe,stroke:#7c3aed,stroke-width:1px,color:#2e1065;
    classDef store fill:#dcfce7,stroke:#16a34a,stroke-width:1px,color:#14532d;
    classDef broker fill:#fef3c7,stroke:#d97706,stroke-width:1px,color:#7c2d12;
    classDef edge fill:#e0e7ff,stroke:#4f46e5,stroke-width:1px,color:#1e1b4b;
    class certs,initdb oneshot;
    class mysql store;
    class mqtt broker;
    class dashboard edge;
    class receiver,api,simulator svc;
```

Arrows show start order: each service starts once the ones before it are ready.

| Service | Image | Published port |
|---|---|---|
| `dashboard` | nginx 1.27 + built React app | 8443 (HTTPS), 8080 (redirect) |
| `mqtt` | eclipse-mosquitto 2 | 8883 (TLS); 1883 on 127.0.0.1 only |
| `api` | Python 3.12, non-root | 8000 on 127.0.0.1 only |
| `mysql` | mysql 8.4 | 3307 on 127.0.0.1 only |
| `receiver`, `simulator` | Python 3.12, non-root | none |
| `mailpit` | axllent/mailpit (local inbox) | 8025 on 127.0.0.1 only |

Running it on a server: [deployment guide](../deployment.md).

## Design principles

- **One responsibility per service**, and per module inside each service, so every part can be tested alone.
- **Never trust input.** Every MQTT message is parsed and validated before it touches the database; every API request is checked against a schema and a role.
- **At least once, stored once.** Acknowledge after the commit; recognise redelivered readings.
- **Secure by default.** Encryption everywhere, least-privilege accounts, and a production mode that refuses unsafe settings.
- **Configuration in the environment** (`.env`, see `.env.example`), never in code.
- **Built in verified phases**: [PROJECT_PLAN.md](../../PROJECT_PLAN.md).
