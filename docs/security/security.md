# Security

What protects each part of the platform, and the tests that prove it. Everything here is fictional and local: the passwords below are **dev defaults** for a project that runs on one machine. Set your own in `.env` for anything else.

## Threats and controls

| Threat | Control | Where | Tested by |
|---|---|---|---|
| Anyone reading or writing the API | Every endpoint except `/health` needs a JWT. Roles are VIEWER < OPERATOR < ADMIN, read from the database on every request. | [auth.md](../api/auth.md) | `tests/api/test_auth.py` |
| Password theft from the database | Salted scrypt hashes, never logged, never echoed back in a 422 | `backend/app/security.py` | `test_security.py`, `test_users.py` |
| Password guessing | 5 failed logins per username, and 20 per client, within 5 minutes → `429` with `Retry-After` | `backend/app/rate_limit.py` | `test_api_security.py` |
| Username enumeration | Same message and same work (one scrypt check) for unknown users and wrong passwords | `api/auth.py` | `test_auth.py` |
| Forged or replayed tokens | HS256 with the algorithm pinned (no `alg: none`), `exp` required, 60-minute lifetime. The role claim is ignored in favour of the database. A deleted user's token stops working at once. | `deps.py` | `test_auth.py`, `test_security.py` |
| Firmware download abuse | Download tokens are scoped to one image and one sensor, valid 10 minutes, and never accepted as logins (and logins never as download tokens) | [fota.md](../architecture/fota.md) | `test_firmware.py`, `test_fota.py` |
| **Anyone publishing to the broker** | `allow_anonymous false`. Four accounts with passwords from the environment, written to the broker's password file on start. | `docker/mosquitto/` | `tests/mqtt/test_acl.py` |
| **Fake commands, fake sensor data** | Broker ACLs: `sensor` may only send device topics and receive commands and firmware. `api` may only send commands and firmware. `receiver` may only read. | `docker/mosquitto/acl` | `test_acl.py` (each account against each topic), checked by hand on the live broker |
| A sensor impersonating another | The receiver rejects telemetry whose `sensor_id` doesn't match its topic, and applies command or firmware responses only to that sensor's own requests. (All devices share one broker account, so the broker can't tell them apart: per-device accounts would be the next step.) | `receiver/main.py` | integration tests |
| Malicious or malformed messages | The receiver parses and validates everything (types, ranges, lengths that match the DB columns) before storing | receiver validators | unit + integration tests |
| SQL injection | Only parameterised SQLAlchemy queries, no string-built SQL | everywhere | `test_api_security.py` (hostile path, query and body values) |
| Stored XSS | React renders text, never HTML. A strict Content-Security-Policy on the dashboard blocks inline and foreign scripts even if markup got through. | `docker/nginx.conf.template` | UI tests (`<img onerror>` in a name stays inert), browser check (no CSP violations) |
| Clickjacking, MIME sniffing, referrer leaks | `X-Frame-Options: DENY` / `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` on the API and dashboard. API responses also get `Cache-Control: no-store` and `default-src 'none'`. | `main.py`, `nginx.conf` | `test_api_security.py` |
| Other websites calling the API from a browser | No CORS headers: the dashboard is same-origin | `main.py` | `test_api_security.py` |
| Oversized uploads | Firmware is capped at 1 MiB while the stream is read; nginx `client_max_body_size 2m` | `api/firmware.py` | `test_firmware.py` |
| Leaking internals | Database errors become a bare `503`. No stack traces in responses, no `Server` version from nginx. | `main.py`, `nginx.conf` | `test_health.py`, `test_api_security.py` |
| Vulnerable dependencies | Exact version pins. CI runs `pip-audit` (Python) and `npm audit --omit=dev` (dashboard) on every push. | `.github/workflows/ci.yml` | CI |
| **Eavesdropping, man in the middle** | TLS on every connection that leaves a container: HTTPS, MQTT 8883, MySQL with `require_secure_transport`. Clients check the certificate and host name. Plain ports only on 127.0.0.1. | [tls.md](tls.md) | `test_tls.py`, `test_broker_tls.py`, CI full-stack job |
| Account takeover through recovery | Reset links: 32 random bytes, only their SHA-256 stored, single use, 30 min, a new one cancels the old; sessions end on reset; the owner is emailed. Recovery never reveals whether an address exists (same answer, email in the background). Rate limited per address and client. | `api/auth.py`, [auth.md](../api/auth.md#accounts-sign-up-approval-recovery-phase-19) | `test_accounts.py` |
| Self-registration abuse | Sign-ups start PENDING and VIEWER, can't choose a role, need an admin's approval; rate limited | `api/auth.py` | `test_accounts.py`, `test_accounts_ui.py` |
| Production with dev settings | `APP_ENV=production` refuses to start with dev passwords, a weak `JWT_SECRET` or without TLS | `backend/app/config_check.py` | `test_tls.py` |
| Secrets in git | `.env` is git-ignored. Passwords and `JWT_SECRET` come only from the environment, and logs never contain them. | | review |

## Broker accounts

| Account | Used by | May publish | May subscribe | Password (env) |
|---|---|---|---|---|
| `sensor` | simulator | `+/sensors/+/{telemetry,response,status,firmware_status}` | `+/sensors/+/{command,firmware}` | `SENSOR_MQTT_PASSWORD` |
| `receiver` | receiver | nothing | `+/sensors/+/{telemetry,response,status,firmware_status}` | `RECEIVER_MQTT_PASSWORD` |
| `api` | API | `iot/sensors/+/{command,firmware}` | nothing | `API_MQTT_PASSWORD` |
| `qa` | tests only | anything | anything | `QA_MQTT_PASSWORD`. Leave it empty in any shared environment and the account isn't created. |

With MQTT 3.1.1, a denied publish or subscribe is dropped silently (the client isn't told), so `test_acl.py` checks what is actually delivered.

## Verified by hand (2026-10-30)

- `mosquitto_sub` without credentials, or with a wrong password: `Connection Refused: not authorised`.
- The `sensor` account publishing a `RESTART` to `iot/sensors/SENSOR-001/command`: a subscriber on that topic received nothing.
- Five wrong passwords for `admin` through the dashboard's nginx, then `429` with `Retry-After: 300`.
- The dashboard (production build behind nginx, strict CSP) signed in, opened a sensor, ran a command and showed the firmware library, with **no console errors or CSP violations**.

## Known limits

- **TLS since Phase 17** ([tls.md](tls.md)). Its own limits: one server certificate for all servers, devices sign in with a password rather than a client certificate, and nginx → API is plain HTTP inside the Docker network.
- **One shared device account.** The broker can't stop one sensor publishing on another's topic. The receiver's topic and `sensor_id` checks catch a mismatch inside the payload, but not a device using another's topic and ID together. The fix is per-device credentials (client certificates, or Mosquitto's dynamic security plugin) with `%u` patterns in the ACL.
- **In-memory login limiter.** Right for one API instance. Several instances would need a shared store, and an API restart resets the counts.
- **Tokens can't be revoked individually** before they expire, except by deleting the user or changing `JWT_SECRET`.
