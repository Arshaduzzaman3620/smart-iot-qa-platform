# Test Automation

pytest drives every layer, including the browser tests (Playwright for Python), so the whole suite is one command. The layers follow the pyramid in [strategy.md](strategy.md).

```text
tests/
  conftest.py          sys.path setup, layer markers, service checks, TEST-* cleanup
  helpers.py           valid_telemetry(), wait_until(), shared constants
  stack_fixtures.py    receiver_process (real receiver/main.py), mqtt_publisher
  browser_servers.py   api_server, dashboard_server (start or reuse FastAPI / Vite)
  test-data/telemetry.json   validator cases (valid / invalid with expected error)
  unit/          parser, validator, data generator, UTC handling, alerts  no services
  api/           FastAPI endpoints via TestClient                         MySQL
  mqtt/          broker publish/subscribe, wildcards, ordering            broker
  integration/   broker -> receiver process -> MySQL                      broker + MySQL
  ui/            dashboard in Chrome, API mocked with page.route          Node (Vite)
  e2e/           MQTT message -> receiver -> MySQL -> API -> dashboard    everything
  reliability/   outages and crashes, cut with tests/tcp_proxy.py         broker + MySQL
```

## Running

### In Docker (any machine, nothing else to install)

```bash
docker compose -f compose.test.yaml run --rm --build tests                   # everything
docker compose -f compose.test.yaml run --rm tests pytest tests/unit -q       # any pytest arguments
docker compose -f compose.test.yaml down                                     # stop the test broker + MySQL
```

This is what CI runs ([.github/workflows/ci.yml](../../.github/workflows/ci.yml)). The test image has Python 3.12, Node 22, Playwright's Chromium and Linux `node_modules`. It gets its own broker and an in-memory MySQL (a separate Compose project with no host ports), so it can run while the dev stack is up and never touches the dev database. `REQUIRE_SERVICES=1` is set, so a missing service fails the run. The image contains a copy of the code, so `--build` picks up your changes.

### On the host (faster to iterate)

Needs Python 3.12 and Node 22 (see [setup.md](../development/setup.md)).

```bash
pip install -r tests/requirements.txt         # once
python -m playwright install chromium         # once
(cd frontend && npm ci)                       # once
docker compose up -d --wait mqtt mysql        # infrastructure only
python -m database.init_db

pytest                     # everything (~1 min)
pytest tests/unit          # one layer by folder...
pytest -m "unit or api"    # ...or by marker
pytest -m "not e2e and not ui"
```

Stop the Docker `receiver` service first (`docker compose stop receiver simulator`) if you started the full stack: the tests run their own receiver, see below.

- **Browser:** tests use Playwright's bundled Chromium. Add `--browser-channel=chrome` to use an installed Google Chrome instead, `--headed` to watch, or `--slowmo 500` to slow it down.
- **Servers:** `api_server` and `dashboard_server` reuse a FastAPI or Vite server that is already running on 8000 / 5173, and otherwise start one for the session and stop it afterwards.
- **Receiver:** integration and e2e tests start their own `receiver/main.py` (offline check every 1 s, no startup grace; it marks any genuinely silent dev sensor OFFLINE, which is correct behavior). **Stop any receiver you started by hand first**, or every test message is stored twice and the exact-count assertions fail.
- **Missing services:** tests that need MySQL or the broker are skipped with a reason when those aren't running. Set `REQUIRE_SERVICES=1` (e.g. in CI) to make that a failure instead.

## Test data isolation

Tests never touch real sensors. Each test gets a unique `TEST-XXXXXXXX` sensor ID from the `sensor_id` fixture. Every `TEST-*` sensor (with its telemetry and alerts, by cascade) is deleted before and after the session, so the suite is safe to run against your dev database while the simulator is running.

## What is covered

| Layer | Tests | Highlights |
|---|---|---|
| unit | 331 | Parser rejects non-UTF-8, invalid JSON, and non-objects. Validator runs every boundary ±0.01, plus wrong types (incl. `bool`), missing/null fields, and bad timestamps, all from `test-data/telemetry.json`. Generator: drift ≤ max step, clamped to range, battery never increases, ranges identical to the validator's. Fleet: unique IDs, varied valid starting values, count limits, spread start offsets. Timestamps converted to naive UTC with fractions truncated (never rounded up), and the API renders them with `Z`. Alert rules: every threshold ±0.01, escalation, hysteresis, thresholds reachable within validator ranges, readable offline durations. Batch writer (fake repository): batching what is queued, size cap, order, retry one by one after a failed batch, survives callback errors, drains on stop. `sensor_id` length matches the DB column. Since Phase 15c: password hashing and tokens, command and FOTA device logic, receiver checks on responses and firmware reports, fault injector, outage hold-and-retry and acks in the batch writer, rate limiter, API middleware, and the AI QA assistant (fake client). |
| api | 252 | Every endpoint: fields, sorting, exact values, newest-first, `limit` boundaries (1, 1000) and invalid values (0, 1001, -1, `abc`, `1.5`, empty) → 422. Unknown / injection-style IDs → 404. Write methods → 405. DB down → 503 with no details leaked. `/alerts` filters, ordering, bad `status` / `limit` → 422, `active_alerts` counts only ACTIVE. Since 15c: login, roles on every endpoint, users, sensor edits, commands, firmware upload, download tokens and updates, rate limiting, security headers, hostile input. |
| mqtt | 28 | Round trip, `+` wildcard, non-matching topics, ordering at QoS 1, binary/empty payloads passed through unchanged. Since 15g: broker sign-in and the ACL of every account against every topic. |
| integration | 56 | Exact values stored, `+09:00` timestamp → UTC, auto-registration, upsert (one sensor row, N telemetry rows). Seven kinds of invalid message rejected with the right reason and nothing stored. Topic/`sensor_id` mismatch rejected. Receiver survives bad input. Boundary values stored exactly. Fractional seconds truncated, not rounded by MySQL. Latest-reading pointer follows the newest timestamp and ignores late messages. 20 concurrent sensors × 5 readings stored exactly once. Alerts: raise, no duplicates, escalate, resolve and re-raise, late reading ignored, silent sensor marked OFFLINE once, recovery back to ONLINE. Batches: results in order, alerts inside one batch identical to one-by-one, all-or-nothing, a rejected message isolated, a 300-message burst through the receiver stored once in per-sensor order. Since 15d: command responses and timeouts, status announcements, firmware progress and timeouts. |
| ui | 77 | Formatting (1 dp, units, relative time with a frozen clock), headers, low-battery threshold (19.99 red, 20.0 not), status badges, sensor with no readings, empty state, both error banners, keeps last data and recovers, a response slower than the refresh interval still shows (fake clock), renders 100 sensors, no horizontal scroll at 375 px. Alerts panel: empty state, severity badges, appears and clears on refresh, CRITICAL listed first, API failure banner. Since 15c: sign-in, session expiry, details panel, commands panel, firmware library and panel, stored-XSS check. |
| reliability | 4 | MySQL outage, broker outage for sensors, receiver SIGKILL, faulty sensors: 0 lost, 0 stored twice, recovery measured ([reliability.md](reliability.md)). |
| e2e | 14 | Published reading appears on the dashboard with matching values. The dashboard updates without reload. A rejected reading never reaches the API or the dashboard. Since 15d, with the real simulator: device metadata, the three commands, a FOTA success, three injected failures and low battery, and actions from the dashboard. |

**Total: 762 tests** (Phase 17: +23 unit and +7 broker tests for TLS, [tls.md](../security/tls.md#tests); Phase 18: +29 UI tests for the dashboard features in `tests/ui/test_experience_ui.py`). Verified that the suite catches regressions: widening the validator's temperature max from 85 to 86 failed 3 tests across 3 layers (unit, generator/validator consistency, integration).

## Writing new tests

- Put the test in the folder for its layer; the marker is added automatically.
- Use the `sensor_id` fixture for anything that writes to MySQL or publishes to MQTT.
- Wait with `wait_until(...)` (or Playwright's `expect`), never `time.sleep`.
- Prefer `data-testid` selectors in browser tests (listed in [dashboard.md](../frontend/dashboard.md)).
