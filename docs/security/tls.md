# TLS

Phase 17. Every connection that leaves a container is encrypted and checks the other side's certificate. Plain ports remain only on `127.0.0.1`, for tools and tests on the same machine.

| Connection | Protocol | Port | Certificate check |
|---|---|---|---|
| Browser → dashboard and API | HTTPS (TLS 1.2 / 1.3, HTTP/2) | **8443** | Browser, against `certs/ca.crt` once you trust it |
| Browser → plain HTTP | redirect only (`301` to HTTPS) | 8080 | |
| Sensors, receiver, API → broker | MQTT over TLS (TLS 1.2+) | **8883** | `MQTT_TLS_CA`: certificate and host name `mqtt` |
| Sensors → firmware download | HTTPS through nginx | 443 (inside Docker) | `API_CA_FILE`: certificate and host name `dashboard` |
| Receiver, API, init-db → MySQL | MySQL TLS, required (`require_secure_transport=ON`) | 3306 (inside Docker) | `MYSQL_SSL_CA`: certificate and host name `mysql` |
| Local tools only | plain MQTT, HTTP API, MySQL over TLS | `127.0.0.1`: 1883, 8000, 3307 | |

## Certificates

On first start the one-shot `certs` service ([docker/tls/make_certs.py](../../docker/tls/make_certs.py)) creates them in `./certs` (git-ignored, and kept out of Docker images by `.dockerignore`):

| File | What | Who reads it |
|---|---|---|
| `ca.crt` | "SmartIoT Dev CA", a private certificate authority, valid 10 years | every client; your browser once you trust it |
| `ca.key` | its private key (mode 0600) | only `make_certs.py`, to issue server certificates |
| `server.crt` / `server.key` | one ECDSA P-256 server certificate for `localhost, 127.0.0.1, mqtt, dashboard, mysql`, valid 397 days (the browser maximum) | nginx, Mosquitto, MySQL |

It never replaces what is already there. The server certificate is re-issued only when it is one of ours (checked by signature) and lacks a host name in `TLS_HOSTNAMES` or expires within 30 days. The CA stays the same, so a browser that trusts it keeps trusting it. Mosquitto and MySQL run as their own users, so each gets a private copy of the key at start.

### Trust the CA in your browser (once)

Until you do, the browser warns that the certificate is not trusted. That's correct: it doesn't know our CA.

```bash
# macOS (asks for your password; Safari and Chrome use the system keychain)
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain certs/ca.crt
# Windows (PowerShell as administrator)
Import-Certificate -FilePath certs\ca.crt -CertStoreLocation Cert:\LocalMachine\Root
# Firefox has its own store: Settings > Privacy & Security > Certificates > View Certificates > Authorities > Import
```

Command-line tools: `curl --cacert certs/ca.crt https://localhost:8443/api/health`.

To remove it again on macOS: Keychain Access → System → "SmartIoT Dev CA" → Delete.

## On a real server

1. **Real certificates.** Put the certificate (full chain) and key from your CA (for example Let's Encrypt) in `certs/server.crt` and `certs/server.key`, and point the clients at a CA that signed them: `MQTT_TLS_CA=system` uses the OS's trusted CAs. The `certs` service leaves foreign certificates alone. Or set `TLS_HOSTNAMES=iot.example.com,mqtt,dashboard,mysql` to get one from our own CA for a new name.
2. **HSTS.** `HSTS_MAX_AGE=31536000`. It's `0` by default because HSTS applies to a whole host name: on `localhost` it would force HTTPS on every other project you open there.
3. **Plain ports.** Remove the 127.0.0.1 port mappings you don't need from `compose.yaml`, and the `listener 1883` block from `docker/mosquitto/mosquitto.conf`.
4. **Production check.** `APP_ENV=production` makes the API refuse to start while any dev default is left: an empty or short `JWT_SECRET`, the dev `ADMIN_PASSWORD`, `MYSQL_PASSWORD` or `API_MQTT_PASSWORD`, or a missing `MQTT_TLS_CA` / `MYSQL_SSL_CA` ([config_check.py](../../backend/app/config_check.py)). Each problem is logged, then startup fails.

## Tests

| What | Where |
|---|---|
| Certificate generator: signed by the CA, host names, server-only use, ≤ 398 days, key permissions, idempotent, re-issues for a new host but keeps the CA, never replaces a certificate from another CA | `tests/unit/test_tls.py` |
| Firmware download over HTTPS: works with our CA; refused with an unknown CA or a certificate for another host | `tests/unit/test_tls.py` (local HTTPS server) |
| MQTT clients (receiver, simulator, API): TLS only when given a CA; certificate and host name required; TLS 1.2 minimum | `tests/unit/test_tls.py` |
| Production check: each dev setting reported; the API doesn't start | `tests/unit/test_tls.py` |
| Real broker on 8883: round trip; no CA → refused; reached by IP → host name mismatch; wrong password still refused; plain MQTT gets no answer; TLS 1.1 refused **by the broker** (the client is made to offer it, otherwise Python refuses it itself and the test proves nothing) | `tests/mqtt/test_broker_tls.py` |
| Whole stack from scratch: `301` to HTTPS, plain MySQL refused, sign-in and telemetry over HTTPS with certificate checking | CI job "Full stack starts" |

### Checked by hand (2026-10-31)

- `http://localhost:8080/` → `301 https://localhost:8443/`. HTTPS with `--cacert certs/ca.crt`: `200` over HTTP/2. Without it: refused (untrusted). TLS 1.1: refused.
- All 5 sensors reporting, signed in over HTTPS. Receiver, API and simulator logs: `Connected to MQTT broker mqtt:8883`. Plain MQTT on 8883: no connection.
- MySQL with `--ssl-mode=DISABLED`: `ERROR 3159 … insecure transport are prohibited`. The API's own connection: `TLSv1.3`, `TLS_AES_256_GCM_SHA384`.
- Firmware update on 3 sensors: all `SUCCEEDED`; nginx logged the 3 downloads (`200`, 4096 bytes) on its HTTPS server.
- `APP_ENV=production` with the dev `.env`: four configuration errors logged, then `Application startup failed`.

## Limits

- **One server certificate** for all three servers. Separate certificates per service would limit what one stolen key exposes.
- **Devices still sign in with a password**, over TLS now. Client certificates per device (`require_certificate true`, `use_identity_as_username true` in Mosquitto) would also solve the shared device account ([security.md](security.md#known-limits)).
- **Inside Docker, nginx → API is plain HTTP** on the private Compose network, as usual behind a TLS-terminating proxy.
- No certificate revocation (CRL/OCSP) for our CA: for a dev CA, delete `./certs` and restart to start over.
