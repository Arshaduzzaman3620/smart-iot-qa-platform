# SmartIoT: project brief

**One sentence:** a fully simulated smart-home IoT platform (sensors, MQTT broker, receiver, database, REST API, web dashboard), built phase by phase to show professional software quality engineering: every layer is tested, secured, measured and documented.

Everything is fictional: no real devices, company code or data.

## The problem it models

A home or building has many small sensors (temperature, humidity, pressure, light, battery). Their readings must arrive reliably, be checked, stored and shown; people must be warned when something is wrong, and the devices must be controllable and updatable remotely. All of this has to keep working when parts fail, and only the right people may do the right things.

## What it does

| For the user | How |
|---|---|
| See the whole home at a glance | Dashboard with a home status banner, overview tiles, list and rooms views, trend charts |
| Be warned in time | Threshold alerts (battery, temperature, humidity) with escalation, offline detection |
| Control devices | Restart, request a reading, change the interval, each outcome tracked |
| Update firmware over the air | Upload, roll out, verified install, safe failure (the device keeps its old firmware) |
| Manage access | Sign-in, roles VIEWER / OPERATOR / ADMIN, user management |
| Get an account and recover it | Self sign-up with admin approval, forgot username / password by email, one-time reset links |

## How it is built

```text
Sensors (simulated, Python) --MQTT over TLS--> Mosquitto broker (accounts, ACLs)
        ^ commands, firmware                          |
        |                                              v
   FastAPI REST API (JWT roles) <---- MySQL <---- Receiver (validate, batch, alerts)
        ^
        | HTTPS
   React dashboard (TypeScript, nginx)
```

Python, FastAPI, SQLAlchemy, MySQL 8.4, Mosquitto, paho-mqtt, React + TypeScript + Vite, nginx, Docker Compose, GitHub Actions. Tests: pytest, Playwright, k6. AI-assisted QA with the Claude API.

## Evidence of quality

| Claim | Proof |
|---|---|
| 823 automated tests in 7 layers (unit, API, MQTT, integration, reliability, browser UI, end-to-end), all passing | [final report](testing/final-report.md#test-inventory), `docker compose -f compose.test.yaml run --rm --build tests` |
| Tests catch real regressions | Mutation checks: widening a sensor limit failed 3 tests in 3 layers; removing a UI fix failed its test ([final report](testing/final-report.md)) |
| No data lost or duplicated through outages | MySQL, broker and receiver killed mid-stream: 0 lost, 0 duplicated ([reliability](testing/reliability.md)) |
| Fast under load | 303 requests/s at 300 concurrent users, 0 % errors; 100 sensors at 1 reading/s ([performance](testing/performance.md)) |
| Secure by default | JWT roles, broker accounts + ACLs, rate-limited login, CSP and security headers, TLS on every connection, production mode that refuses dev settings, dependency audit in CI ([security](security/security.md), [TLS](security/tls.md)) |
| Every requirement covered | 11 of 11 requirements traced to tests ([traceability](testing/final-report.md#requirements-traceability)) |
| Honest about defects | 41 defects found and fixed, each with the test that now guards it ([defect log](testing/final-report.md#defect-log)) |
| Reproducible anywhere | One command starts everything on macOS, Windows or Linux; CI repeats the tests, a fresh full-stack start and the audit on every pull request |

## How it was built

19 phases, each one: implement only that scope, verify by hand, add positive / negative / boundary tests, update the docs, then commit and review. Highlights:

| Phases | What |
|---|---|
| 0–9 | Plan, requirements, simulator, MQTT, receiver, validation, database |
| 10–14 | REST API, dashboard, end-to-end, test automation, 100-sensor scale |
| 15a–15g | Alerts, batched writes, auth and roles, commands, firmware over the air, reliability, security and performance |
| 16 | AI QA assistant (generates test cases, explains failing runs), final report |
| 17 | TLS everywhere, production configuration check |
| 18 | Dashboard as a modern smart-home app: redesign, motion, search / filter / sort, rooms view, users screen |
| 19 | Accounts: sign-up with approval, email, forgot username / password, reset links; animated sign-in page |

## A 5-minute demo

1. `docker compose up -d --build`, open https://localhost:8443, sign in (`admin` / `admin-dev-password`, or your own `.env`).
2. The **home status** banner and tiles: everything live, refreshing every 5 s.
3. **Devices**: search with `/`, filter Offline, sort by temperature, switch to **Rooms**.
4. Open a sensor: trend chart, change the range to 100, **Restart** (it asks first), watch the command turn SUCCEEDED.
5. **Firmware**: upload an image, update a sensor, watch DOWNLOADING → VERIFYING → INSTALLING → SUCCEEDED.
6. Sign out, **Create account**, then approve it in Users as admin; try **Forgot username or password?** and open the email at http://localhost:8025.
7. Stop MySQL (`docker compose stop mysql`), watch the dashboard say so, start it again: nothing was lost.
8. Run the tests: `docker compose -f compose.test.yaml run --rm --build tests`.

## Talking points

- **Testing is layered on purpose:** fast unit tests for logic, real broker and database for integration, a real browser for the UI, and the whole stack for end-to-end, so each failure points at one layer.
- **Failures are designed in, not hoped away:** TCP proxies cut the database and broker mid-test; acknowledgements happen only after data is stored.
- **Measurements changed the design:** load tests found an API that stopped responding after a stress run; the fix took it from 124 to 303 requests/s.
- **Recovery without leaks:** reset links are single-use, stored only as a hash, end every session, and the forgot form answers the same for every address.
- **Security is checked, not assumed:** every role against every endpoint, every broker account against every topic, the broker's own refusal of old TLS versions.

## What would come next

Per-device broker credentials, live push updates (WebSockets), database migrations and data retention, monitoring (Prometheus / Grafana), automated backups. See [known limits](testing/final-report.md#known-limits).
