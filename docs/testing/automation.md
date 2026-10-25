# Test Automation

pytest drives every layer, including the browser tests (Playwright for Python), so the whole suite is one command. The layers follow the pyramid in [strategy.md](strategy.md).

```text
tests/
  conftest.py          sys.path setup, layer markers, service checks, TEST-* cleanup
  helpers.py           valid_telemetry(), wait_until(), shared constants
  stack_fixtures.py    receiver_process (real receiver/main.py), mqtt_publisher
  browser_servers.py   api_server, dashboard_server (start or reuse FastAPI / Vite)
  test-data/telemetry.json   validator cases (valid / invalid with expected error)
  unit/          parser, validator, data generator, UTC handling          no services
  api/           FastAPI endpoints via TestClient                         MySQL
  mqtt/          broker publish/subscribe, wildcards, ordering            broker
  integration/   broker -> receiver process -> MySQL                      broker + MySQL
  ui/            dashboard in Chrome, API mocked with page.route          Node (Vite)
  e2e/           MQTT message -> receiver -> MySQL -> API -> dashboard    everything
```

## Running

```bash
pip install -r tests/requirements.txt         # once
docker compose -f docker/docker-compose.yml up -d --wait
python -m database.init_db

pytest                     # everything (~1 min)
pytest tests/unit          # one layer by folder...
pytest -m "unit or api"    # ...or by marker
pytest -m "not e2e and not ui"
```

- **Browser:** tests use the installed Google Chrome (`--browser-channel=chrome` in `pytest.ini`), so no Playwright browser download is needed. Add `--headed` to watch, or `--slowmo 500` to slow it down.
- **Servers:** `api_server` and `dashboard_server` reuse a FastAPI or Vite server that is already running on 8000 / 5173, and otherwise start one for the session and stop it afterwards.
- **Receiver:** integration and e2e tests start their own `receiver/main.py`. **Stop any receiver you started by hand first**, or every test message is stored twice and the exact-count assertions fail.
- **Missing services:** tests that need MySQL or the broker are skipped with a reason when those aren't running. Set `REQUIRE_SERVICES=1` (e.g. in CI) to make that a failure instead.

## Test data isolation

Tests never touch real sensors. Each test gets a unique `TEST-XXXXXXXX` sensor ID from the `sensor_id` fixture. Every `TEST-*` sensor (with its telemetry and alerts, by cascade) is deleted before and after the session, so the suite is safe to run against your dev database while the simulator is running.

## What is covered

| Layer | Tests | Highlights |
|---|---|---|
| unit | 68 | Parser rejects non-UTF-8, invalid JSON, and non-objects. Validator runs every boundary ±0.01, plus wrong types (incl. `bool`), missing/null fields, and bad timestamps, all from `test-data/telemetry.json`. Generator: drift ≤ max step, clamped to range, battery never increases, ranges identical to the validator's. Fleet: unique IDs, varied valid starting values, count limits, spread start offsets. Timestamps converted to naive UTC, and the API renders them with `Z`. |
| api | 29 | Every endpoint: fields, sorting, exact values, newest-first, `limit` boundaries (1, 1000) and invalid values (0, 1001, -1, `abc`, `1.5`, empty) → 422. Unknown / injection-style IDs → 404. Write methods → 405. DB down → 503 with no details leaked. |
| mqtt | 5 | Round trip, `+` wildcard, non-matching topics, ordering at QoS 1, binary/empty payloads passed through unchanged. |
| integration | 17 | Exact values stored, `+09:00` timestamp → UTC, auto-registration, upsert (one sensor row, N telemetry rows). Seven kinds of invalid message rejected with the right reason and nothing stored. Topic/`sensor_id` mismatch rejected. Receiver survives bad input. Boundary values stored exactly. Latest-reading pointer follows the newest timestamp and ignores late messages. 20 concurrent sensors × 5 readings stored exactly once. |
| ui | 11 | Formatting (1 dp, units, relative time with a frozen clock), headers, low-battery threshold (19.99 red, 20.0 not), status badges, sensor with no readings, empty state, both error banners, keeps last data and recovers, renders 100 sensors, no horizontal scroll at 375 px. |
| e2e | 3 | Published reading appears on the dashboard with matching values. The dashboard updates without reload. A rejected reading never reaches the API or the dashboard. |

**Total: 133 tests.** Verified that the suite catches regressions: widening the validator's temperature max from 85 to 86 failed 3 tests across 3 layers (unit, generator/validator consistency, integration).

## Writing new tests

- Put the test in the folder for its layer; the marker is added automatically.
- Use the `sensor_id` fixture for anything that writes to MySQL or publishes to MQTT.
- Wait with `wait_until(...)` (or Playwright's `expect`), never `time.sleep`.
- Prefer `data-testid` selectors in browser tests (listed in [dashboard.md](../frontend/dashboard.md)).
