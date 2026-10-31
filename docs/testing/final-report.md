# Final QA Report

SmartIoT Sensor Quality Engineering Platform, release candidate after Phase 16 (2026-10-30). Everything is fictional and simulated. All results below were produced in Docker on one Apple-silicon Mac, and CI re-runs them on Linux for every push.

## Summary

| | |
|---|---|
| Automated tests | **733**, in 7 layers, all passing ([inventory](#test-inventory)) |
| Requirements | **11 of 11** functional requirements implemented and covered by tests ([traceability](#requirements-traceability)) |
| Defects found and fixed | **34** across the phases, each with a test that now guards it ([defect log](#defect-log)) |
| Reliability | 0 readings lost, 0 stored twice, through MySQL, broker and receiver outages ([reliability.md](reliability.md)) |
| Performance | 303 req/s at 300 virtual users with 0 % errors; 100 sensors at 1 reading/s stored with ≤ 1 s latency ([performance.md](performance.md)) |
| Security | JWT roles, broker auth + ACLs, rate limiting, CSP, dependency audit ([security.md](../security/security.md)) |
| TLS (Phase 17) | HTTPS, MQTT over TLS, MySQL TLS, certificate and host-name checks, production check ([tls.md](../security/tls.md)) |
| Open limits | Listed [below](#known-limits): one shared device account, one API process |

## Test inventory

| Layer | Tests | What it proves | Needs |
|---|---|---|---|
| unit | 331 | Parser, validator (every boundary ±0.01), generator, alert rules, batch writer (outage hold, acks), passwords and tokens, FOTA device logic, command parsing, fault injector, rate limiter, middleware, AI QA assistant, certificates and HTTPS downloads, production check | nothing |
| api | 252 | Every endpoint: success, boundaries, 401/403 by role, 404/409/413/422/429/503, hostile input, headers, firmware tokens | MySQL |
| mqtt | 28 | Broker round trip, wildcards, ordering, **ACLs per account**, **TLS listener** (certificate, host name, TLS 1.1 refused) | broker |
| integration | 56 | Real receiver process: storage, rejection, alerts, offline detection, batching, commands, firmware progress, status messages | broker + MySQL |
| reliability | 4 | MySQL outage, broker outage, receiver SIGKILL, faulty sensors, via TCP proxies | broker + MySQL |
| ui | 48 | Every dashboard state in Chromium, API mocked: sign-in, tables, alerts, details, commands, firmware, XSS, phone width | Node |
| e2e | 14 | Whole stack with the **real simulator**: reading → dashboard, commands, FOTA success and three injected failures, low battery | everything |

One command runs all of them: `docker compose -f compose.test.yaml run --rm --build tests` (about 3½ minutes). Load tests (k6) and the 100-sensor scale check run separately, see [performance.md](performance.md).

## Requirements traceability

| Requirement ([requirements.md](../requirements/requirements.md)) | Delivered in | Evidence |
|---|---|---|
| Simulate realistic fictional sensors | Phases 3, 14 | `unit/test_data_generator.py`, `unit/test_fleet.py`; scale check 100 sensors |
| Publish telemetry over MQTT per sensor | 3, 15f (QoS 1, buffering) | `mqtt/`, `reliability/` broker outage |
| Receive, parse, validate; reject and log bad input | 6, 7 | `unit/test_message_parser.py`, `unit/test_telemetry_validator.py`, `integration/test_receive_chain.py` |
| Persist telemetry, status, alerts in MySQL | 8, 9, 15a | `integration/`, `api/test_sensors.py`, `api/test_alerts.py` |
| REST API with authentication and roles | 10, 15c | `api/test_auth.py`, `api/test_users.py`, `api/test_api_security.py` |
| Dashboard: list, details, history, alerts | 11, 15a, 15c | `ui/`, `e2e/test_full_flow.py` |
| Sensor commands (restart, request reading, interval) | 15d | `api/test_commands.py`, `integration/test_command_flow.py`, `e2e/test_commands_e2e.py` |
| Simulated FOTA with failure scenarios | 15e | `api/test_firmware.py`, `unit/test_fota.py`, `integration/test_firmware_flow.py`, `e2e/test_fota_e2e.py` |
| Scale from 1 to 100 sensors | 14, re-measured 15g | [scale-results.md](scale-results.md), [performance.md](performance.md) |
| Tests in every layer incl. performance, security, reliability | 13, 15f, 15g | this report; k6 profiles; `reliability/`; `mqtt/test_acl.py` |
| Full stack in Docker Compose, CI on GitHub Actions | portable env, 15g | `compose.yaml`, `compose.test.yaml`, `.github/workflows/ci.yml` (tests, full-stack start, dependency audit) |

Non-functional requirements: configuration from `.env` with working defaults ([setup.md](../development/setup.md)), separated responsibilities per service, logs without secrets (checked in auth and DB-error tests), and graceful degradation (503s, reliability layer).

## Defect log

Every defect below was found by a test, a manual check or a measurement while building, fixed, and is now guarded by a test.

| # | Phase | Defect | Found by | Fix |
|---|---|---|---|---|
| 1 | 3 | Simulator crashed at startup when the broker was down | manual negative test | async connect, fail-soft publish |
| 2 | 8 | `FLOAT` columns altered values such as 99999.99 | boundary check | `DOUBLE` |
| 3 | 12 | First reading lost on every simulator start | E2E trace | wait for the first connection |
| 4 | 12 | Simulator logged readings as sent when they weren't | E2E trace | `sent` / `dropped` logs |
| 5 | 14 | `GET /sensors` took 1.7 s at 1M rows (full scan) | scale test | latest-reading pointer: 2.5 ms |
| 6 | 14 | Simulator could stop between publish and log | scale test | stop flag between readings |
| 7 | 14 | `localhost` cost about 2 s per connection on Windows | measurement | `127.0.0.1` |
| 8 | 15a | Receiver log in cp932 broke on "°C" | tests | UTF-8 child processes |
| 9 | 15a | Offline check locked the whole sensors table (latency 39 s) | scale test | lock only stale candidates |
| 10 | 15a | MySQL rounds fractional seconds (time in the future) | flaky test | truncate before writing |
| 11 | 15a | Dashboard poll cancelled itself when the API was slower than 5 s | UI test with fake clock | skip a tick instead |
| 12 | 15b | `sensor_id` > 50 chars passed validation, then failed in MySQL | test | validator limit = column size |
| 13 | env | CI race: `init-db` started before MySQL accepted TCP | CI | TCP healthcheck + retry |
| 14 | 15c | A 422 echoed rejected passwords back | manual check | stripped from errors |
| 15 | 15d | Status announcements lost (sensors connect before the receiver subscribes) | manual check | retained status |
| 16 | 15d | Image build failed on a truncated pip download | build | pip timeout and retries |
| 17 | 15e | Root `fota/` folder shadowed the simulator's `fota` package | design review | removed placeholder |
| 18 | 15e | Slow-API UI test relied on a fixed 300 ms wait | full-suite run | wait for the request itself |
| 19 | 15f | paho acknowledged messages before they were stored (lost on crash) | design of crash test | manual acks after storing |
| 20 | 15f | Broker-outage test passed while losing all buffered readings | suspicious numbers | test counts buffered readings; reconnect cap 10 s; flush on stop |
| 21 | 15f | Simulator `publish()` reported success without a PUBACK | review | `is_published()` |
| 22 | 15f | Unit test raced the writer's shutdown | test run | test waits for stores |
| 23 | 15g | **API connection leak: dead after a stress run** | k6 stress | async session cleanup, 503 on pool exhaustion |
| 24 | 15g | Throughput collapse in a spike (29 req/s, 13 % failed) | k6 spike | auth's own session, pool = threads |
| 25 | 15g | Requests still held connections between thread hops | k6 spike | concurrency limit: 0 % errors, 303 req/s |
| 26 | 15g | Two test modules with the same name broke collection | full-suite run | renamed |
| 27 | 15g | Async test helper clashed with Playwright's event loop | full-suite run | helper runs on its own thread |
| 28 | 15g | Dashboard buttons wrapped ("Set interval" on two lines) | screenshot review | `nowrap` |
| 29 | 15g | PyJWT warning: test signing keys under 32 bytes | test warnings | longer keys; API warns on short `JWT_SECRET` |
| 30 | env | Mac sleep paused Docker (looked like data loss) | manual check | documented; re-measured awake |
| 31 | 16 | Pytest tried to collect the `TestCase` / `TestPlan` models | test run | `__test__ = False` |
| 32 | 17 | Certificate generator recognised its own certificates by name, so it would overwrite one from another CA | unit test | check by signature |
| 33 | 17 | TLS 1.1 test passed because the *client* refused TLS 1.1, never asking the broker | review of a too-easy pass | client offers TLS 1.1; test expects the broker's alert |
| 34 | 17 | Two test modules named `test_tls` broke collection (same as #26) | full-suite run | renamed `test_broker_tls` |

## Known limits

- **TLS** was added in Phase 17 ([tls.md](../security/tls.md#limits) lists what it doesn't cover yet: per-device client certificates, one shared server certificate).
- **One shared device account** on the broker: the receiver catches mismatched IDs, but per-device credentials would be needed to stop a compromised device using another's topic.
- **One API process** at about 300 req/s. Scaling out needs a fixed `JWT_SECRET` and a shared login limiter.
- **Tokens can't be revoked individually** before they expire (60 min), except by deleting the user.
- **The AI QA assistant wasn't run against the live API** while building (no key on the build machine). It is fully tested with a fake client, so running it once with a key is the remaining manual check ([ai-qa-assistant.md](ai-qa-assistant.md)).

## Final regression (2026-10-30)

| Check | Result |
|---|---|
| **Phase 17 (2026-10-31): full suite** | **733 / 733 passed** (3 min 31 s) |
| **Phase 17: fresh stack with new certificates** | `301` to HTTPS, plain MySQL refused, 5 sensors reporting over HTTPS, 0 error lines |
| Full suite, run twice in a row | **703 / 703 passed both times** (3 min 22 s, 3 min 27 s), no flaky tests |
| Fresh install from empty volumes (isolated Compose project) | All services healthy, initial admin created, sign-in through the dashboard, 5 / 5 sensors reporting with firmware and names, 0 error lines in any log |
| Mutation check: temperature limit widened 85 → 86 (test container only) | Caught by 3 tests: validator unit, generator/validator range consistency, receiver integration |
| CI workflow | Valid; jobs `tests`, `stack` (full-stack start), `audit` (pip-audit, npm audit) |
| Load / stress / spike / soak, 100-sensor ingestion | 0 % errors; see [performance.md](performance.md) |

The first `docker compose up` of the fresh install failed instantly once, with its output not captured. The identical command succeeded right after and the failure didn't recur, so the cause is unknown.

## How to reproduce

```bash
docker compose up -d --build                                    # the platform, https://localhost:8443 (admin / admin-dev-password)
docker compose -f compose.test.yaml run --rm --build tests       # all 733 tests
docker compose --profile perf run --rm k6 run -e PROFILE=load /scripts/api.js
docker compose -f compose.test.yaml run --rm tests python scripts/scale_check.py --sensors 100 --interval 1 --duration 30
```
