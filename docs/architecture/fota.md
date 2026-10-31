# Firmware Over The Air (FOTA)

Simulated firmware updates for the simulated sensors (Phase 15e). The "firmware" is any small file. What is real is the flow around it: upload, checksum, a scoped download, verification, install, reboot, and every failure along the way.

## Flow

```text
ADMIN   ──POST /firmware?version=1.1.0 (raw bytes)──> API: stores bytes, SHA-256, size
OPERATOR──POST /sensors/{id}/firmware-updates {"firmware_id": 2}──> API: row REQUESTED
API ──iot/sensors/{id}/firmware──> sensor:
        {"update_id": 7, "version": "1.1.0", "size": 4096, "sha256": "03aa…", "url": "/firmware/2/download?token=…"}
sensor: battery check → DOWNLOADING (GET API_BASE_URL + url) → VERIFYING (size + SHA-256) → INSTALLING → reboot
sensor ──iot/sensors/{id}/firmware_status──> receiver ──> firmware_updates row, sensors.firmware_version
sensor (after reboot) ──retained iot/sensors/{id}/status──> receiver   (reports the new version too)
```

| Status | Set by | Meaning |
|---|---|---|
| `REQUESTED` | API | Published to the sensor |
| `DOWNLOADING`, `VERIFYING`, `INSTALLING` | sensor | Progress. Reports may only move forward: a late `DOWNLOADING` can't undo `INSTALLING`. |
| `SUCCEEDED` | sensor | Installed and rebooted. The receiver sets `sensors.firmware_version` at once. |
| `FAILED` | sensor, or API | `error_message` says why. The sensor keeps its old firmware. The API sets it when the broker is unreachable (`503`). |
| `TIMED_OUT` | receiver | No progress for `FOTA_TIMEOUT` (default 300 s), for example the sensor is offline |

The API refuses (`409`) to start an update to the version the sensor already runs, or while another update of that sensor is unfinished.

## Failure scenarios

| Scenario | How it happens | Result |
|---|---|---|
| Battery too low | Below `FOTA_MIN_BATTERY` (20 %); checked before downloading | `FAILED` "battery too low (12 %, needs 20 %)" |
| Download fails | HTTP error, API unreachable, expired token; or injected `FOTA_FAILURE=download` | `FAILED` "download failed: …" |
| Corrupt image | Size or SHA-256 differs from the update message; or injected `FOTA_FAILURE=corrupt` (one flipped byte) | `FAILED` "checksum mismatch; staying on 1.0.0" |
| Install fails | Injected `FOTA_FAILURE=install` | `FAILED` "install failed (injected); rolled back to 1.0.0" |
| Already on that version | API check, and again on the device | `409` from the API; `FAILED` from the device |
| Two updates at once | API check, and again on the device | `409`; `FAILED` "another update is in progress" |
| Sensor never answers | Offline, or the message was lost | `TIMED_OUT` after `FOTA_TIMEOUT` |
| Broker down | API can't publish | `503`, row `FAILED` "MQTT broker unreachable" |

Inject a failure on the running stack: `FOTA_FAILURE=corrupt docker compose up -d simulator` (also `download`, `install`; `none` to stop).

## Security

- **Upload:** ADMIN only. Raw `application/octet-stream`, at most 1 MiB (enforced while reading the stream, not only from `Content-Length`; `413` above it). Empty files are refused. `version` must look like `1.2.3`, and `filename` may only use `A-Z a-z 0-9 _ . -` (no paths). Duplicate versions get `409`.
- **Download token:** sensors have no user accounts, so the update message carries a JWT with `scope: firmware:download`, `fw: <firmware id>` and `sub: <sensor id>`, valid for **10 minutes**. `GET /firmware/{id}/download?token=…` accepts only that scope **for that image**. A login token, a token for another image, a tampered or expired token all get `401`. In the other direction, a download token is never accepted as a login (`401` on every other endpoint), even if its subject matched a username.
- **On the device:** the update message is validated (version format, size 1 B–1 MiB, 64-hex SHA-256), and `url` must be a `/firmware/` path on the configured API. A message can't point the device at another host. The image is verified against size and SHA-256 before "installing".
- **Receiver:** a progress report is applied only to an unfinished update **of the sensor whose topic it came on**. A device can't claim `REQUESTED` or `TIMED_OUT`.

## Where the code is

| Part | File |
|---|---|
| API | [backend/app/api/firmware.py](../../backend/app/api/firmware.py), tokens in [security.py](../../backend/app/security.py) |
| Device logic (parse, download, verify, install) | [sensor-simulator/fota/fota_client.py](../../sensor-simulator/fota/fota_client.py) |
| Device wiring (worker thread, reboot) | `CommandRunner` in [sensor-simulator/main.py](../../sensor-simulator/main.py) |
| Receiver | [receiver/storage/firmware_repository.py](../../receiver/storage/firmware_repository.py) |
| Dashboard | `FirmwareLibrary` (list; upload for ADMIN), `FirmwarePanel` in the sensor details (history, update for OPERATOR+) |

The download and verification run on a worker thread, so the rest of the fleet keeps publishing during an update. The result is applied on the main thread, which owns sensor state. The reboot reuses the `RESTART` command's reboot. Images are stored in MySQL (`MEDIUMBLOB`) because they are tiny. Real firmware would go to object storage.

Settings: `API_BASE_URL` (where sensors download from; `http://api:8000` in Compose), `FOTA_FAILURE`, `FOTA_MIN_BATTERY`, `FOTA_STEP_SECONDS` (simulated time per stage, default 1 s) on the simulator; `FOTA_TIMEOUT` on the receiver.
