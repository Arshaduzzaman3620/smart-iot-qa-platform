# Deployment guide

How to run SmartIoT on a server that others can reach. Locally, `docker compose up -d --build` is all you need. On a server, the defaults are **not** safe: they are development passwords published in this repository. Production mode exists to stop exactly that.

## 1. Server requirements

- Linux with Docker Engine and the Compose plugin, 2 vCPU and 4 GB RAM for the default 5 sensors.
- A DNS name pointing at the server, for example `iot.example.com`.
- Firewall: allow **443** (or your `HTTPS_PORT`), **80** (redirect) and **8883** (MQTT over TLS, only if real devices connect from outside). Nothing else.
- An SMTP account for outgoing email (password resets, welcome emails).

## 2. Configuration

Create `.env` next to `compose.yaml`. It is git-ignored: **never commit it**. Generate every secret fresh:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # run once per secret below
```

```dotenv
APP_ENV=production

# Ports: the dashboard on the standard HTTPS port.
HTTPS_PORT=443
DASHBOARD_PORT=80
HSTS_MAX_AGE=31536000

# Certificates (see step 3).
TLS_HOSTNAMES=iot.example.com,mqtt,dashboard,mysql

# Links in emails.
APP_BASE_URL=https://iot.example.com

# First administrator: created only while there are no users.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generated>
JWT_SECRET=<generated, at least 32 bytes, never changed afterwards>

MYSQL_PASSWORD=<generated>
SENSOR_MQTT_PASSWORD=<generated>
RECEIVER_MQTT_PASSWORD=<generated>
API_MQTT_PASSWORD=<generated>
# The test account is never created in production; leave this empty.
QA_MQTT_PASSWORD=

# Real mail server.
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_STARTTLS=1
SMTP_USER=<user>
SMTP_PASSWORD=<password>
SMTP_FROM=SmartIoT <no-reply@example.com>
```

With `APP_ENV=production` the API and the broker **refuse to start** while any of these is missing or still a development default, and log which one. The interactive API docs are switched off. Rules: [config_check.py](../backend/app/config_check.py), [entrypoint.sh](../docker/mosquitto/entrypoint.sh).

## 3. Certificates

- **Own CA (simplest):** with `TLS_HOSTNAMES` set as above, the `certs` service creates a CA and a server certificate for your DNS name on first start. Devices and services trust `certs/ca.crt`. Browsers warn until users trust that CA, so this suits private deployments.
- **Public certificate (for a public website):** put the full chain and key from your CA (for example Let's Encrypt) in `certs/server.crt` and `certs/server.key`. Details and the client settings: [TLS, on a real server](security/tls.md#on-a-real-server).

Keep `certs/` private and backed up: `ca.key` signs certificates everyone here trusts.

## 4. Start

```bash
docker compose up -d --build --wait
docker compose ps                      # every service healthy or running
docker compose logs api | grep -i "production"   # empty: no configuration problem
```

Then sign in at `https://iot.example.com` as the administrator (keep the generated password in a password manager) and create an account for everyone else in **Users**, with their email so they can choose their own password through **Forgot username or password?**.

## 5. Harden the host

- Remove the `127.0.0.1` port mappings you don't use from `compose.yaml` (MQTT 1883, API 8000, MySQL 3307, Mailpit 8025) and the `listener 1883` block from `docker/mosquitto/mosquitto.conf`.
- Remove the `mailpit` and `simulator` services once real mail and real devices are in use.
- Keep the host and images updated: `docker compose pull && docker compose up -d --build`.
- Back up the `mysql-data` volume and `certs/`.

## 6. Verify

| Check | Expected |
|---|---|
| `curl -I http://iot.example.com` | `301` to `https://` |
| `curl -I https://iot.example.com` | `200` with `Strict-Transport-Security`, `Content-Security-Policy` |
| `curl -s -o /dev/null -w '%{http_code}' https://iot.example.com/api/docs` | `404` (docs off in production) |
| Sign in with a wrong password six times | `429 Too many failed attempts` |
| MQTT with `sensor-dev-password` on 8883 | refused |
| Forgot password with your email | email arrives from your SMTP server |

## Before making a repository public

Already done for this repository (2026-10-31, [security review](security/security.md#security-review-before-going-public-2026-10-31)): no secrets in any commit, `.env` and `certs/` git-ignored, dependency audit clean, CI token read-only. Recommended GitHub settings: enable **secret scanning and push protection**, **Dependabot alerts**, a **branch protection rule** on `main` requiring the CI checks, and in your account's email settings **Keep my email addresses private** with **Block command line pushes that expose my email**.
