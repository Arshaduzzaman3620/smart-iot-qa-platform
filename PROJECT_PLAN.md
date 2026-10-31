# Project Plan — SmartIoT Sensor Quality Engineering Platform

This project is built **one phase at a time**. A phase is not started until the previous phase is implemented, manually verified, tested (positive + negative), documented, and committed. See "Definition of Done" below.

## Phase roadmap

- [x] **Phase 0** — Project definition, repository scaffold, foundational docs
- [~] **Phase 1** — Development environment verification (Python, Node.js, Git, Docker Desktop, VS Code) *(partially confirmed: Python 3.12.6, Docker 29.7.2 verified working; Node.js/Git not yet checked)*
- [x] **Phase 2** — MQTT broker (Mosquitto) proven working with a minimal publisher/subscriber
- [x] **Phase 3** — First simulated sensor (SENSOR-001): connect, generate realistic telemetry, publish, reconnect on failure, stop cleanly *(includes Phase 4/5 scope — data generator and MQTT publisher were built together as one working sensor, not separately)*
- [x] **Phase 6** — MQTT receiver (subscribes to `iot/sensors/+/telemetry`)
- [x] **Phase 7** — Telemetry validation (parser + validator, reject invalid messages)
- [x] **Phase 8** — MySQL database (`smart_iot`: sensors, telemetry, alerts tables)
- [x] **Phase 9** — Receiver writes validated telemetry into MySQL (first full data flow: sensor → MQTT → receiver → validate → MySQL)
- [x] **Phase 10** — FastAPI backend (`/health`, `/sensors`, `/sensors/{id}`, `/sensors/{id}/telemetry`)
- [x] **Phase 11** — Frontend dashboard (basic sensor table: ID, temperature, humidity, battery, status, last seen)
- [x] **Phase 12** — Full first E2E flow verified manually (sensor → MQTT → receiver → validate → MySQL → FastAPI → dashboard)
- [x] **Phase 13** — Test automation foundation (unit, API, MQTT, integration, UI, E2E)
- [x] **Phase 14** — Scale to multiple sensors (5 → 10 → 50 → 100)
- [x] **Phase 15** — Advanced features: alerts, commands, authentication, FOTA, failure injection, performance, security, reliability *(in progress, one PR per part)*
  - [x] **15a** — Threshold alerts and offline detection
  - [x] **15b** — Receiver throughput: batched writes
  - [x] **Portable environment** — whole platform and test suite in Docker, CI on every push
  - [x] **15c** — Authentication and roles
  - [x] **15d** — Sensor commands
  - [x] **15e** — FOTA (firmware over the air)
  - [x] **15f** — Reliability and failure injection
  - [x] **15g** — Security and performance
- [x] **Phase 16** — Final portfolio polish: docs, reports, CI/CD, AI QA assistant, final regression
- [x] **Phase 17** — Real-world TLS: HTTPS, MQTT over TLS, MySQL TLS, production configuration check

## Definition of Done (per phase)

- [ ] Implementation completed
- [ ] Application runs
- [ ] Manual verification completed
- [ ] Positive tests completed
- [ ] Negative tests completed
- [ ] Errors handled
- [ ] Logs added
- [ ] Documentation updated
- [ ] Committed, pushed to `test-phase`, pull request opened

## Workflow per phase

1. Implement the phase's scope only — nothing from later phases.
2. Verify manually (run it, see the expected result).
3. Add positive and negative tests where applicable.
4. Update relevant docs under `docs/`.
5. When the phase is finished: commit, push to `test-phase`, and open a pull request into `main` (the owner reviews and merges).
6. Check this file's roadmap box, move to the next phase.

## Current status

**Phase 17 complete: TLS everywhere** ([docs/security/tls.md](docs/security/tls.md)).
- A one-shot `certs` service creates a private CA and a server certificate in `./certs`; existing or real certificates are never replaced.
- Dashboard and API over HTTPS (8443, HTTP/2, TLS 1.2+), plain HTTP only redirects. Optional HSTS.
- Sensors, receiver and API use MQTT over TLS (8883) with certificate and host-name checks; firmware downloads go over HTTPS; MySQL requires TLS. Plain ports are bound to 127.0.0.1 only.
- `APP_ENV=production` makes the API refuse to start with dev passwords, a weak `JWT_SECRET` or without TLS.
- Verification found two test defects and one product defect: a duplicate test module name, a TLS 1.1 test that passed because the *client* refused TLS 1.1, and the generator recognising its own certificates by name (it would have overwritten a certificate from another CA).

**Phase 16:** the project's original scope is finished. Results: [docs/testing/final-report.md](docs/testing/final-report.md).
- **AI QA assistant** ([qa-assistant/](qa-assistant/), [doc](docs/testing/ai-qa-assistant.md)): `generate-tests` turns a requirement into positive, negative and boundary test cases per layer, marking what is already covered. `analyze-failures` classifies each failure of a pytest run, with evidence and a next step. Claude Opus 5.5 via the Anthropic SDK, with structured outputs (Pydantic), the project docs as the cached specification, refusal fallback, and every non-answer turned into a clear error. 17 tests with a fake client (no API calls, no key needed in CI). Not yet run against the live API (no key on the build machine).
- **Final QA report:** test inventory (703 tests, 7 layers), requirements traceability (11 of 11 covered), the defect log (31 found and fixed), known limits, and how to reproduce.
- **Docs polish:** the README is the project's front page (results, quick start, features, architecture, stack), test counts are updated, and every doc link was checked.
- **CI** (since the portable environment): test suite, full-stack start and dependency audit on every push.
- **Final regression (2026-10-30):** the full suite twice in a row, **703 / 703 passed both times** (3 min 22 s and 3 min 27 s, no flaky tests). A fresh install from empty volumes in an isolated Compose project: all services healthy, first admin created, sign-in through the dashboard, 5 / 5 sensors reporting with firmware and names, 0 error lines. A mutation check (temperature limit widened 85 → 86 in the test container only) was caught by 3 tests in 3 places. CI workflow YAML valid (jobs: tests, stack, audit). Load, stress, spike and soak and the 100-sensor ingestion check: see 15g. One `docker compose up` of the fresh project failed instantly on the first try with its output discarded; the identical command then succeeded, and it did not recur.

**Phase 15g (previous): security and performance. Phase 15 is done.** Details: [docs/security/security.md](docs/security/security.md), [docs/testing/performance.md](docs/testing/performance.md).
- **MQTT security:** no anonymous access. Four accounts (`sensor`, `receiver`, `api`, `qa` for tests), passwords from the environment, written to the broker's password file at start. ACLs limit each account to its own topics. Verified on the live broker: anonymous and wrong-password clients are refused, and a `sensor` account's forged RESTART command never arrives.
- **API security:** login rate limiting (5 failures per username, 20 per client, per 5 min → 429 + Retry-After). Security headers on every response (strict CSP, nosniff, DENY framing, no-referrer, no-store), and a strict CSP on the dashboard: the real build runs with **no CSP violations** in a browser. No CORS. Hostile-input tests (SQL injection, traversal, oversized and malformed bodies). `pip-audit` and `npm audit` in CI.
- **Performance (k6, in Docker):** load (50 VUs) 144 req/s, p95 38 ms, 0 % errors. Soak 0 % errors, flat memory. Stress and spike up to 300 VUs: **0 % errors, 303 req/s, max 0.7 s.** Ingestion at 100 sensors: 100 msg/s stored with 0 missing, 0 duplicates, max latency 1 s.
- **Defects found by the load tests:** (1) **A DB connection leak killed the API** after a stress run: sync session cleanup never ran for requests cancelled under overload, so `/health` never answered again. The session now closes in an async dependency, and pool exhaustion gives a fast `503 Database busy`. (2) **Throughput collapsed in a spike** (29 req/s, 13 % failed): requests held connections while waiting for worker threads. Auth now uses its own short session, and the pool matches the threads. (3) **Admission:** a concurrency limit (32 in flight, others wait outside holding nothing). Result: 124 → 303 req/s, 1.1 % → 0 % errors, max 60 s → 0.7 s.
- Also: dashboard buttons no longer wrap. Test-isolation fixes (an async test helper that runs alongside Playwright, unique test module names).
- Tests: 686 (66 new: MQTT ACLs, rate limiting, headers, hostile input, middleware). All pass.

**Phase 15f (previous): reliability and failure injection.** Details: [docs/testing/reliability.md](docs/testing/reliability.md).
- The pipeline is now **at-least-once with deduplication**. MySQL down: the receiver holds and retries (was: dropped). Broker unreachable: sensors buffer up to 1000 readings and resend in order (was: dropped). Receiver down or crashed: persistent MQTT session + QoS 1, so the broker queues for it. Broker restart: Mosquitto persistence. Redeliveries and resends: identical readings stored once. Offline detection pauses during an outage and its backlog. This closes the Phase 12 "no buffering" limitation.
- Fault injection: `FAULT_INVALID_RATE` / `FAULT_MALFORMED_RATE` / `FAULT_DUPLICATE_RATE` in the simulator, and an in-test TCP proxy that cuts MySQL or the broker without Docker access, so it works the same in CI.
- New `tests/reliability` layer: MySQL outage (50 held, stored 5.3 s after recovery), broker outage (75 buffered, stored 5.4 s after), receiver SIGKILL (50 queued, stored 0.3 s after restart), faulty sensors. **0 lost and 0 duplicates in every scenario.** Verified on the real stack too: `docker compose stop mysql` 20 s → 48 sent, 48 stored; `docker compose restart mqtt` → 0 duplicates.
- Defects found and fixed: (1) paho acknowledged QoS 1 messages when queued, not when stored, so a receiver crash lost them; now manual acks after storing. (2) The first broker-outage test passed while every buffered reading was lost, because it only compared against "sent". Fixed the test, capped reconnect backoff at 10 s, and the simulator flushes and reports on shutdown. (3) The simulator's `publish()` reported success without a PUBACK.
- Measurement caveat found: a suspended Mac freezes the simulated sensors too (one run looked like loss until the log showed a 90 s system sleep).
- Tests: 620 (21 new). All pass.

**Phase 15e (previous): firmware over the air.** Details: [docs/architecture/fota.md](docs/architecture/fota.md).
- ADMIN uploads an image (raw bytes, at most 1 MiB, SHA-256 computed). OPERATOR starts an update. The sensor gets the version, size, checksum and a **10-minute download token scoped to that one image**, downloads over HTTP, verifies size and SHA-256, installs and reboots, reporting DOWNLOADING → VERIFYING → INSTALLING → SUCCEEDED / FAILED. The receiver applies progress forward-only and only for the sensor's own update, sets the new version on success, and times out stalled updates (`FOTA_TIMEOUT`).
- Failure scenarios: low battery, download failure, corrupt image, install failure with rollback, same version, concurrent update, no answer, broker down. `download` / `corrupt` / `install` can be injected with `FOTA_FAILURE`. In every failure the sensor keeps its old firmware.
- Verified by hand: upload validation (409 duplicate, 413 > 1 MiB, 422 empty or bad version), a full update 1.0.0 → 1.1.0, each injected failure (sensor stays on 1.0.0), then a normal update succeeding, and 5 token attacks (tampered, login-as-download, wrong image, download-as-login, none) all refused.
- Dashboard: firmware library (upload for ADMIN) and a per-sensor firmware panel with live progress.
- Removed the empty Phase 0 `fota/` placeholder folder. FOTA lives in the services, and the folder name shadowed the simulator's `fota` package.
- Defect fixed in a test: the slow-API UI test waited a fixed 300 ms for React's second dev mount, which the extra startup requests made too short. It now waits for the request itself.
- Tests: 599 (109 new), incl. E2E with the real simulator for success, three injected failures, low battery, and an update from the dashboard. All pass.

**Phase 15d (previous): sensor commands.** Details: [docs/architecture/commands.md](docs/architecture/commands.md).
- `REQUEST_TELEMETRY`, `SET_INTERVAL` (1–3600 s) and `RESTART` travel dashboard → API → MQTT → sensor, and the sensor's answer travels back → receiver → MySQL → dashboard. A command is `SENT`, then `SUCCEEDED` / `FAILED` from the sensor, or `TIMED_OUT` after `COMMAND_TIMEOUT` (30 s). A broker outage is `503` and is recorded as `FAILED`.
- Checked at every hop: the API (strict types and ranges, OPERATOR+), the sensor (answers `FAILED` with the reason), and the receiver (a response only completes a still-`SENT` command *of the sensor it came from*; duplicates, late answers and other sensors' ids are ignored).
- Sensors announce name, location, type and firmware on `.../status` when they connect. This closes the Phase 12 "metadata not propagated" limitation. Operator-set names are never overwritten.
- Defect found by manual check: the first status announcements were all lost, because sensors connect before the receiver subscribes. Status is now **retained**, so the broker delivers it whenever the receiver (re)subscribes. Verified: firmware `1.0.0` stored for all 5 sensors, operator names kept.
- Verified by hand against the running stack: each command (SET_INTERVAL 2 → readings 2 s apart; RESTART → SENT for 3 s, then SUCCEEDED), 6 invalid requests → 422/404, a forged command answered FAILED by the sensor, and a sensor's attempt to answer another sensor's command ignored.
- Build: pip got `PIP_DEFAULT_TIMEOUT` / `PIP_RETRIES`, after a slow network truncated a download ("hashes do not match").
- Tests: 490 (112 new): parser/validator unit tests, API tests with a fake publisher (exact payload, validation, roles, broker down), integration tests through the real receiver (responses, ownership, duplicates, timeouts, status), E2E with the **real simulator** (metadata, all three commands, a dashboard click), and UI tests for the commands panel. All pass.

**Phase 15c (previous): authentication and roles.** Details: [docs/api/auth.md](docs/api/auth.md).
- `POST /auth/login` issues a JWT (HS256, 60 min). Every endpoint except `/health` needs one. Roles are VIEWER (read) < OPERATOR (also `PATCH /sensors/{id}` name/location) < ADMIN (also `/users`: list, create, delete). The role is read from the database on every request, so deleting a user or demoting them takes effect at once, and a token's own role claim is never trusted.
- Passwords are salted scrypt from the standard library and are never stored, logged or echoed in a 422. An unknown username takes as long to reject as a wrong password, with the same message, so usernames can't be enumerated. Tokens with `alg: none`, a wrong signature, or no expiry are rejected.
- The first admin is created on API startup when the users table is empty (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, Compose dev default `admin` / `admin-dev-password`).
- Dashboard: sign-in form, user and role in the header, sign out, and automatic sign-out with the reason on any 401. New sensor details panel: metadata, the 20 newest readings, alert history, and an edit form for OPERATOR+.
- Verified by hand with curl (21 positive and negative checks) and in a real browser (login, wrong password, details, edit, reload, sign out, 375 px width). A name containing `<img onerror>` is shown as text.
- Hardening found while testing: FastAPI's default 422 echoed the rejected password back in `input`. It is now stripped for password fields. A `JWT_SECRET` under 32 bytes triggers a warning.
- Tests: 378 (131 new: token, hash and role unit tests; login, token, role and user-management API tests; PATCH validation including 100-char boundaries and control characters; sign-in, session-expiry, details and XSS UI tests). E2E tests now sign in through the real form and API. All pass.

**Portable environment (previous, 2026-10-29).** The project moved from a Windows laptop to a Mac (Apple Silicon), which had Python 3.9 and no Node. Instead of fixing one machine, Docker is now the only requirement. Details: [docs/development/setup.md](docs/development/setup.md).
- `docker compose up -d --build` runs everything: broker, MySQL, a one-shot `init-db`, receiver, API, simulator (5 sensors) and the dashboard (production build behind nginx, which proxies `/api`). Verified on macOS arm64: all services healthy, 5 sensors reporting through the API and through the dashboard proxy.
- `docker compose -f compose.test.yaml run --rm --build tests` runs all 241 tests in a container (Python 3.12, Node 22, Playwright Chromium) against its own broker and an in-memory MySQL. **241 passed in 50 s with no skips**, while the dev stack was running.
- GitHub Actions ([ci.yml](.github/workflows/ci.yml)) runs the suite and a full `docker compose up` smoke test on every push.
- Graceful stop verified in Docker: `docker compose stop` stops the simulator first, then the receiver drains its queue, and both exit with code 0. `stop_grace_period: 60s` allows for a long drain.
- Host-run fixes: defaults now match the published ports (`127.0.0.1:3307`, `127.0.0.1:1883`), so `.env` is optional. `API_HOST` is configurable. Python below 3.10 stops with a clear message instead of a TypeError inside SQLAlchemy. Versions pinned in `.python-version`, `frontend/.nvmrc` and `engines`.
- Portability fixes: `.gitattributes` forces LF (a CRLF checkout would break files in Linux containers). Browser tests use Playwright's Chromium instead of an installed Google Chrome, which doesn't exist for Linux arm64. `node_modules` is never copied from the host, because esbuild ships per-OS binaries.
- Defect fixed (found by CI): the "full stack starts" job failed intermittently (2 of 3 runs). On first start, the MySQL image runs a temporary server that accepts only socket connections, and the healthcheck pinged through the socket, so it reported healthy too early. `init-db` then got `Connection refused` on TCP and exited 1. The healthcheck now runs `SELECT 1` over TCP as the app user. As a second safety net, `init-db` retries "can't connect" errors for up to `INIT_DB_WAIT` seconds (60 in Compose; 0 on the host, so a wrong host still fails at once), and fails immediately on errors that won't fix themselves, such as a wrong password. Verified with 3 of 3 fresh starts from an empty database and 6 new unit tests (247 total, all pass).
- `docker/docker-compose.yml` was replaced by `compose.yaml` at the repo root. The project name and volume are unchanged, so existing data is kept.

**Phase 15b (previous): batched writes.** Details: [docs/testing/scale-results.md](docs/testing/scale-results.md#phase-15b-batched-writes-2026-10-25).
- The receiver validates on the MQTT thread and queues messages for one writer thread. That thread stores whatever is waiting (up to 200) in one transaction with one commit. There is no added latency at low load, and per-sensor order and alert behavior are unchanged.
- Ceiling: 33 → ~95 msg/s (~4.5× the 100-sensor target). 100 sensors: 3 of 3 runs pass (max latency 1–2 s), where most runs had failed after 15a. Overload never loses data.
- A failed batch is retried one by one, so a single bad message no longer costs the others.
- Graceful stop on Ctrl+C / SIGTERM / Ctrl+Break: every accepted message is stored before exit (verified: stop after 300 of 2000 messages, all 2000 stored, exit code 0).
- Defect fixed: a `sensor_id` over 50 characters passed validation but was rejected by MySQL (`VARCHAR(50)`). The validator now rejects it, and a test keeps the limit equal to the column size.
- Tests: 241 (20 new). All pass.

**Phase 15a (previous): alerts and offline detection.** Details: [docs/architecture/alerts.md](docs/architecture/alerts.md).
- The receiver raises alerts while storing telemetry: `LOW_BATTERY`, `HIGH_TEMPERATURE`, `LOW_TEMPERATURE`, `HIGH_HUMIDITY`, each WARNING → CRITICAL. One active alert per (sensor, type), hysteresis on resolve, and only the newest reading is judged, so late messages are ignored.
- Offline detection fixes the Phase 12 "stale ONLINE" limitation: a sensor with no reading for 30 s becomes OFFLINE with an `OFFLINE` alert, and it recovers automatically on its next reading. There is a startup grace period, so a receiver restart doesn't flag live sensors.
- API: `GET /alerts`, `GET /sensors/{id}/alerts`, and `active_alerts` on `GET /sensors`. Dashboard: an active-alerts panel.
- Defect fixed: the receiver's log was written in the Windows code page (cp932) when redirected, so a "°C" in an alert message broke every test reading the log. Child processes started by tests and `scale_check.py` now use UTF-8.
- Defect fixed: the first offline check used a locking read over the whole `sensors` table. Under REPEATABLE READ that locked every row and gap every 5 s and stalled the receiver (100 sensors: max latency 39 s). It now reads without locks and locks only the stale candidates.
- Finding (not caused by 15a): a receiver commit costs 18–39 ms on this machine today, against ~15 ms during Phase 14. The 100-sensor scale check now usually fails on latency, with Phase 14 code as well (1 of 3 runs passed). Nothing is lost. Batched writes are the next part (15b). See [scale-results.md](docs/testing/scale-results.md).
- Defect fixed: MySQL `DATETIME` *rounds* fractional seconds (`12:00:00.6` → `12:00:01`), so sensor timestamps and `last_seen` could be stored up to 0.5 s in the future. This showed up as an intermittently failing offline test ("4 min" instead of "5 min"). The receiver now truncates to whole seconds before writing.
- Defect fixed: each dashboard poll aborted the previous one if it was still running, so an API slower than 5 s would never show data, and no error either. The dashboard now skips a tick while a load is in flight. A UI test reproduces this with a fake clock: it fails on the old code and passes on the new.
- Tests: 221 (88 new). All pass.

**Phase 14 (previous). The simulator runs N sensors (`SENSOR_COUNT`, 1–1000), each with its own MQTT connection, start times spread across the interval, and varied starting conditions. The pipeline was verified at 5 → 10 → 50 → 100 sensors with the new `scripts/scale_check.py`. Full results: [docs/testing/scale-results.md](docs/testing/scale-results.md).
- 100 sensors: 1189/1189 readings stored, 0 missing, 0 duplicates, ≤ 1 s latency. All four steps pass. The dashboard shows all 100 sensors.
- Capacity: the receiver tops out at ~65–75 msg/s (3.3× the 100-sensor target). Above that nothing is lost, but latency grows. Batching is deferred to Phase 15 performance work.
- Defect fixed: `GET /sensors` scanned the whole telemetry table (1.7 s at 1M rows). It now uses a latest-reading pointer on `sensors` maintained by the receiver (1.7 s → **2.5 ms** at 1M rows, independent of table size). The pointer only moves forward, so late messages don't replace newer readings. Existing DBs are upgraded by `python -m database.init_db` (new `database/migrations.py`).
- Defect fixed: the simulator now stops gracefully on Ctrl+C / SIGTERM / Ctrl+Break, never between publishing and logging a reading (needed for `docker stop` in Phase 16 as well).
- Defect fixed: `localhost` cost ~2 s per new connection on Windows (IPv6 first, API is IPv4-only). The scale script, e2e tests, and Vite proxy now use `127.0.0.1`.
- Tests: 133 (13 new: 8 fleet unit tests, 4 concurrent multi-sensor and latest-pointer integration tests, 1 100-row dashboard test). All pass.

Next: **Phase 15**: advanced features (alerts, commands, authentication, FOTA, failure injection, performance, security, reliability), including the limitations carried from Phase 12 (stale ONLINE status, no outage buffering, sensor metadata) and receiver throughput.

**Phase 13 (previous).** 120 automated tests across six layers, one command (`pytest`, ~1 min). Guide: [docs/testing/automation.md](docs/testing/automation.md).
- unit (60): parser, validator (every boundary ±0.01 from `tests/test-data/telemetry.json`), data generator, UTC handling.
- api (29): every endpoint with positive, boundary, and negative cases, plus a 503 when the DB is down.
- mqtt (5): round trip, wildcard, ordering.
- integration (13): the real `receiver/main.py` process, from broker to MySQL.
- ui (10): Playwright in installed Chrome with the API mocked; every dashboard state.
- e2e (3): MQTT message to rendered dashboard.
- Isolation: unique `TEST-*` sensor IDs, purged before and after the session, so it is safe against the dev DB. Session fixtures are registered once (`pytest_plugins`) so only one receiver ever runs. Browser tests reuse running servers or start and stop their own.
- Missing MySQL/broker → skipped with a reason. `REQUIRE_SERVICES=1` makes that a failure (for CI).
- Verified the suite catches regressions: widening the validator's temperature max (85 → 86) failed 3 tests in 3 layers. Verified the full run leaves no servers running and no TEST rows behind.
- Flaky-test fixes made while building: MQTT tests now wait for the broker's SUBACK before publishing, and the relative-time UI test freezes the browser clock.

Next: **Phase 14**: scale to multiple sensors (5 → 10 → 50 → 100). The simulator runs N sensors, and receiver, DB, API, and dashboard behaviour are checked at each step.

**Phase 12 (previous).** The full pipeline was verified by hand, tracing the same readings through simulator → receiver → MySQL → API → dashboard. Runbook and recorded results: [docs/testing/e2e-manual-verification.md](docs/testing/e2e-manual-verification.md).
- Happy path: 5/5 readings published and stored. Every value is identical in the simulator log, receiver log, MySQL, and API. The dashboard shows the latest reading rounded to 1 dp, as designed.
- Negative path: out-of-range, wrong-type, and non-UTF-8 messages from brand-new sensors were rejected by the receiver, so those sensors are 404 in the API and absent from the dashboard. A valid new sensor appeared within one refresh, with its low battery highlighted.
- Reliability: the receiver auto-reconnected and resubscribed after a broker restart, and 11/11 later readings were stored. The simulator started with the broker down keeps running and resumes once it connects.
- Defects found and fixed: (1) the simulator lost its first reading on every start, because `connect()` is async; it now waits up to 5 s for the first connection via `MQTTClient.wait_until_connected()`. (2) The simulator logged readings as sent even when the publish was skipped; it now logs `Telemetry sent` or `Telemetry dropped`.
- Known limitations carried forward to Phase 15: stale ONLINE status, no buffering during outages, sensor metadata not propagated.

Next: **Phase 13**: test automation foundation. pytest unit tests (parser, validator, generator), API tests (httpx), MQTT/integration tests, and Playwright UI/E2E tests, automating the checks above.

**Phase 11 (previous).** React 18 + TypeScript dashboard (Vite) in `frontend/`, documented in [docs/frontend/dashboard.md](docs/frontend/dashboard.md). It shows a sensor table (ID, temperature, humidity, battery, status badge, relative last seen) that polls every 5 s through Vite's `/api` dev proxy to FastAPI. It has loading, empty, and error states, and keeps showing the last good data when the API or database fails. Every cell has a `data-testid` for Playwright. Backend change for it: `GET /sensors` now includes each sensor's `latest_telemetry`, fetched for all sensors in one query instead of one request per sensor. Verified with the full stack running (simulator, receiver, API, Vite) and headless-Chrome screenshots:
- Positive: `tsc` strict type check and production build pass. The table rendered both sensors with their latest readings and refreshed live (SENSOR-001's "last seen" stayed within seconds while the simulator ran). The proxy response matched the API.
- Negative: API stopped → "Cannot reach the API. Retrying…". MySQL stopped → "Database unavailable. Retrying…". After MySQL restarted, the table returned with no page reload.
- Layout: at narrow widths the table scrolls inside its card and the page never scrolls horizontally. Light and dark themes follow the OS.
- Regression: all 19 Phase 10 API checks still pass after the `/sensors` change.
- Known limitation: a sensor that stops publishing still shows ONLINE (status is never set to OFFLINE). Offline detection is in Phase 15.

Next: **Phase 12**: verify the complete first E2E flow manually (sensor → MQTT → receiver → validate → MySQL → FastAPI → dashboard), checking the same values at every hop.

**Phase 10 (previous).** A read-only FastAPI backend in `backend/app/` reads MySQL through the shared `database` package. Layout: `api/health.py`, `api/sensors.py` (routers), `schemas.py` (Pydantic response models; DB DATETIMEs are labelled UTC so JSON ends in `Z`), and `deps.py` (one session per request). `main.py` holds the app plus an `OperationalError` handler that turns DB outages into a clean `503`. Run with `python -m backend.app.main`, which reads `API_PORT` from `.env`. Endpoint reference: [docs/api/endpoints.md](docs/api/endpoints.md). Verified live (19/19 checks against the running API + MySQL):
- Positive: `/health` → 200. `/sensors` returns every DB sensor, sorted, with fields equal to the DB rows. `/sensors/{id}` → 200. `/sensors/{id}/telemetry` returns every row newest-first with values identical to MySQL. With the receiver and simulator running, the API's newest reading equalled the simulator's last published payload, confirming sensor → MQTT → receiver → MySQL → API end to end.
- Boundary: `limit=1` returns exactly the newest row. `limit=1000` → 200.
- Negative: unknown sensor → 404 with a clear message (both endpoints). `limit` = 0 / 1001 / -5 / `abc` → 422. SQL-injection-style ID → 404 (parameterised query, no data leaked). Unknown route → 404. `POST /sensors` → 405.
- Error handling: with MySQL stopped, `/health` → 503 `degraded` and `/sensors` → 503 `Database unavailable`, with no stack trace to the client. After MySQL restarted, both returned 200 with no API restart. The log has no secrets.

Next: **Phase 11**: frontend dashboard (React + TypeScript): a sensor table with ID, temperature, humidity, battery, status, and last seen, fed by this API.

**Phase 9 (previous).** First full data flow works: sensor → MQTT → receiver → parse → validate → MySQL. New `receiver/storage/telemetry_repository.py` (`TelemetryRepository.save`) runs one transaction per message. It upserts the `sensors` row with `INSERT ... ON DUPLICATE KEY UPDATE` (status `ONLINE`, `battery`, `last_seen`, `updated_at`), so a first-seen sensor is registered automatically and concurrent receivers can't race into a duplicate-key error. It then inserts the `telemetry` row, converting the ISO 8601 timestamp to naive UTC. `main.py` adds the repo root to `sys.path` so it can import the shared `database` package. Two validation additions: the validator now rejects a `timestamp` that isn't ISO 8601, and the receiver rejects a message whose `sensor_id` doesn't match its topic, so a sensor can only publish its own readings. Verified live (broker + MySQL via Docker Compose, simulator running):
- Positive: every telemetry message the simulator published was stored, with all values identical to the published payload. `sensors` shows SENSOR-001 `ONLINE` with the latest battery and `last_seen`. A message from a never-seen SENSOR-002 auto-registered the sensor. A `+09:00` timestamp was stored as the correct UTC time.
- Negative: non-ISO timestamp, `sensor_id`/topic mismatch, out-of-range temperature, and invalid JSON were each rejected with a specific reason. None reached the database.
- Reliability: with MySQL stopped mid-run, the receiver logged `Failed to store telemetry ... Lost connection` and kept running. After MySQL restarted, the next message was stored with no receiver restart (`pool_pre_ping`). Known limitation: messages received while MySQL is down are dropped, not buffered. Buffering/retry belongs to the reliability work in Phase 15.

Next: **Phase 10**: FastAPI backend (`/health`, `/sensors`, `/sensors/{id}`, `/sensors/{id}/telemetry`) reading from MySQL via the shared `database` package.

**Phase 8 (previous).** MySQL 8.4 runs in Docker via `docker/docker-compose.yml`, which also defines the Mosquitto broker. The database and app user come from `.env`, and root gets a random password. Host port is 3307 to avoid clashing with a locally installed MySQL. The new shared `database/` package is used by the receiver (Phase 9) and later the API (Phase 10). It contains `models.py` (SQLAlchemy 2.0 models for `sensors`, `telemetry`, `alerts` per [database.md](docs/architecture/database.md)), `session.py` (engine + `SessionLocal`, with `pool_pre_ping` for MySQL restarts), `config.py` (`.env`-driven), and `init_db.py` (`python -m database.init_db`, which creates missing tables, is safe to re-run, and never logs the password). The receiver still doesn't write to the database. Verified against the live container:
- Positive: schema created and the DDL inspected in MySQL. A re-run is a no-op. A sensor + telemetry + alert insert reads back with every value exact, and the defaults (`status=OFFLINE`, `sensor_type=ENVIRONMENT`, alert `status=ACTIVE`, `created_at`/`received_at`) are applied, including on raw SQL inserts. `updated_at` changes on update.
- Boundary: every documented min/max range value is stored and read back exactly. Verification initially caught single-precision `FLOAT` columns, which would alter values like `99999.99`, and they were switched to `DOUBLE`.
- Negative: duplicate `sensor_id`, telemetry/alert for an unknown sensor (FK), telemetry missing a reading (NOT NULL), and a sensor with no `sensor_id` are each rejected by the database. Deleting a sensor cascades to its telemetry and alerts.
- Error handling: with MySQL stopped, `init_db` logs a clear connection error and exits 1, with no traceback and no secrets.

Next: **Phase 9**. The receiver writes validated telemetry into MySQL: it upserts the `sensors` row (status `ONLINE`, `last_seen`, `battery`) and inserts a `telemetry` row, for the first full flow sensor → MQTT → receiver → validate → MySQL.

**Phase 7 (previous).** `receiver/` now parses and validates every message before accepting it, per the architecture principle "the receiver never trusts incoming data": `parser/message_parser.py` (`MessageParser` — decodes UTF-8, parses JSON, confirms it's an object; raises `ParseError` otherwise, no validation logic) and `validator/telemetry_validator.py` (`TelemetryValidator` — checks all required fields present, correct non-bool numeric types, and within the ranges from [sensor-behavior.md](docs/architecture/sensor-behavior.md); returns a list of error strings, empty = valid). `main.py`'s message handler now parses, then validates, then logs either `Accepted telemetry ...` or `Rejected message ...` with the reason(s) — still no database write, that's Phase 9. Verified (manually, broker in Docker, simulator running live):
- Positive: valid telemetry from `sensor-simulator` logged as accepted.
- Negative: invalid JSON, a message missing a required field (`battery`), an out-of-range value (`temperature=999`), and a wrong type (`humidity` as a string) were each rejected with a clear, specific reason; receiver kept running after every one.
- Boundary: a message with every field set to its exact min/max (`temperature=-40`, `humidity=100`, `pressure=1100`, `light=100000`, `battery=0`) was correctly accepted — confirms the range checks are inclusive, not off-by-one.

Next: **Phase 8** — MySQL database (`smart_iot`: `sensors`, `telemetry`, `alerts` tables) — schema only at this phase, per [database.md](docs/architecture/database.md); the receiver doesn't write to it until Phase 9.

**Phase 6 (previous).** `receiver/` subscribed to `iot/sensors/+/telemetry` and logged every message received, with the same separated structure as the simulator: `mqtt/` (subscribe/reconnect wrapper), `config/` (`.env`-driven settings). Verified: receiver logs the simulator's live telemetry byte-for-byte; wildcard subscription confirmed with a second sensor ID; malformed/empty payloads logged without crashing; survives a Mosquitto broker stop/restart (auto-reconnect + resubscribe).

**Phase 3 (previous).** `sensor-simulator/` implements SENSOR-001 with separated responsibilities per the architecture doc: `sensors/` (identity/state), `generator/` (realistic gradual-drift values within the documented ranges), `mqtt/` (connect/publish/reconnect), `config/` (`.env`-driven settings). Verified:
- Positive: connects to Mosquitto, publishes valid telemetry matching the required schema every `SENSOR_INTERVAL` seconds, values drift realistically instead of jumping, subscriber receives every message.
- Negative/reliability: found and fixed a crash-on-startup bug when the broker is unreachable (blocking `connect()` raised `ConnectionRefusedError`); switched to `connect_async` + made `publish()` fail soft (log + skip) instead of raising. Verified the sensor keeps running with the broker down, and auto-reconnects and resumes publishing once the broker comes back — no restart needed.
