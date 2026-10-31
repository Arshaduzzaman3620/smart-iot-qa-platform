# Development Setup

The project runs the same on macOS (Intel and Apple Silicon), Windows and Linux. There are two ways to run it. Docker-only is the recommended one, because it needs nothing else installed.

## Option A: everything in Docker (recommended)

Needs only **Docker Desktop** (or Docker Engine with the Compose plugin on Linux).

```bash
docker compose up -d --build        # broker, MySQL, schema, receiver, API, simulator, dashboard
```

| What | Where |
|---|---|
| Dashboard | **https://localhost:8443** (sign in as `admin` / `admin-dev-password`). http://localhost:8080 redirects there. |
| API + Swagger UI | https://localhost:8443/api/docs, or plain http://localhost:8000/docs from this machine only |
| MQTT broker | TLS on port `8883` (all interfaces); plain `127.0.0.1:1883` for local tools |
| Mailpit (emails the API sends: password resets, approvals) | http://localhost:8025 |
| MySQL | `127.0.0.1:3307` (user `smart_iot_user`, password `changeme`), TLS required: e.g. `--ssl-ca=certs/ca.crt` |

The first start creates `./certs` (a private CA and a server certificate). Trust `certs/ca.crt` once so the browser accepts the dashboard: see [tls.md](../security/tls.md#trust-the-ca-in-your-browser-once).

```bash
docker compose logs -f receiver               # follow one service
docker compose ps                             # what is running
docker compose up -d --build receiver         # rebuild after a code change
docker compose down                           # stop (data is kept)
docker compose down -v                        # stop and delete the database
```

Tests: `docker compose -f compose.test.yaml run --rm --build tests` runs all layers in a container with its own broker and database. See [automation.md](../testing/automation.md).

`init-db` is a one-shot service: it creates or upgrades the schema and exits with code 0. The receiver and API start only after it has succeeded.

## Option B: Python and Node on the host

Faster for editing and debugging one service. Docker still runs the broker and MySQL.

| Tool | Version | Pinned in |
|---|---|---|
| Python | 3.12 (3.10+ works) | `.python-version` |
| Node.js | 22 LTS (20+ works) | `frontend/.nvmrc`, `engines` in `frontend/package.json` |
| Docker | any current Docker Desktop | |

macOS ships Python 3.9, which is too old. The code stops with a clear message if you use it. Install 3.12 from python.org, with `brew install python@3.12`, or with `pyenv install 3.12` (pyenv reads `.python-version`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate                      # Windows: .venv\Scripts\activate
pip install -r tests/requirements.txt -r receiver/requirements.txt -r sensor-simulator/requirements.txt
python -m playwright install chromium          # browser for the UI tests
(cd frontend && npm ci)

docker compose up -d --wait mqtt mysql         # infrastructure only
python -m database.init_db
cd receiver && python main.py                  # terminal 1
cd sensor-simulator && python main.py          # terminal 2
ADMIN_PASSWORD=admin-dev-password python -m backend.app.main   # terminal 3, repo root
cd frontend && npm run dev                     # terminal 4: http://localhost:5173
```

No `.env` is needed: the defaults reach the Docker broker and MySQL from the host. Copy `.env.example` to `.env` only to change something, such as `SENSOR_COUNT`.

Don't run a host receiver and the Docker `receiver` service at the same time. Both would store every message. Use `docker compose up -d --wait mqtt mysql`, or `docker compose stop receiver simulator`.

## Why it is portable

| Problem it avoids | How |
|---|---|
| Different Python, Node or MySQL versions per machine | Pinned base images (`python:3.12-slim-bookworm`, `node:22`, `mysql:8.4`, `eclipse-mosquitto:2`) and pinned dependency versions |
| Native modules built for the wrong OS (esbuild in `node_modules`) | `node_modules` is installed inside each image and never copied from the host (`.dockerignore`) |
| CRLF line endings from a Windows checkout breaking files in Linux containers | `.gitattributes` forces LF |
| Settings that work in one place only | Services find each other by name inside Compose. Host defaults match the published ports, so `.env` is optional. |
| Tests that need a locally installed Chrome (Google Chrome doesn't exist for Linux arm64) | Playwright's bundled Chromium |
| `localhost` resolving to IPv6 first (slow on Windows) | Host defaults use `127.0.0.1` |
| `docker stop` killing the receiver before its queue is stored | `stop_grace_period: 60s` |
| "Works on my machine" | CI runs the test suite and a full `docker compose up` on a clean Linux machine for every push |

## Troubleshooting

- **`port is already allocated`**: another program uses 1883, 3307, 8000 or 8080. Set `MQTT_PORT`, `MYSQL_PORT`, `API_PORT` or `DASHBOARD_PORT` in `.env`.
- **`Cannot connect to the Docker daemon`**: start Docker Desktop.
- **Changed `MYSQL_PASSWORD` but MySQL rejects it**: the user is created only on the first start. Run `docker compose down -v` to recreate the database.
- **Tests counting messages twice**: a second receiver is running (see above).
