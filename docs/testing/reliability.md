# Reliability and Failure Injection

Phase 15f made the pipeline **at-least-once with deduplication** end to end. A reading a sensor takes survives an outage of the broker, of MySQL, or a crash of the receiver, and is stored exactly once.

## What happens when something fails

| Failure | Before 15f | Now |
|---|---|---|
| **MySQL down** | Each message failed and was dropped (Phase 9 limitation) | The writer keeps the batch and retries with backoff (1 → 10 s). New messages wait in its queue (10 000), then at the broker. The first success logs `Database back after N s` and stores the backlog. |
| **Broker unreachable for sensors** | `Telemetry dropped` | Each sensor buffers up to `SENSOR_BUFFER_MAX` (1000) readings and sends them **in order** after reconnecting (backoff capped at 10 s). If it is stopped while still disconnected, it logs how many were lost. |
| **Receiver down or crashed** | Messages published meanwhile were lost | The receiver has a **persistent MQTT session** and subscribes at QoS 1, and sensors publish at QoS 1, so the broker queues its messages (up to 100 000) and delivers them on reconnect. |
| **Receiver crashes with messages in memory** | Lost: paho acknowledged them as soon as they were *queued* | **Manual acks.** A message is acknowledged only after it is stored (or rejected), so the broker redelivers anything unacknowledged. |
| **Broker restart** | Sessions and queued messages lost | Mosquitto persistence (`/mosquitto/data`, a volume in Compose) keeps them |
| **Same reading twice** (QoS 1 redelivery, a sensor resend) | Stored twice | The receiver skips a reading identical to one already stored (same sensor, timestamp and values; uses the existing `(sensor_id, timestamp)` index) and logs `Duplicate telemetry … ignored` |
| **Offline detection after an outage** | (would mark every sensor OFFLINE, since nothing was stored) | Paused while the database is down or its backlog is being stored, plus one grace period |

Messages the receiver rejects (invalid, malformed) are acknowledged at once, because redelivering them can't help. If the database is *still unreachable when the receiver stops*, it doesn't acknowledge, so the broker delivers those messages again on the next start.

## Fault injection

| Where | Setting | Effect |
|---|---|---|
| Simulator | `FAULT_INVALID_RATE` | Probability per reading of an out-of-range value (`temperature: 999`) |
| Simulator | `FAULT_MALFORMED_RATE` | … of truncated JSON |
| Simulator | `FAULT_DUPLICATE_RATE` | … of sending the same message twice |
| Simulator | `FOTA_FAILURE` | `download` / `corrupt` / `install` on every firmware update ([fota.md](../architecture/fota.md)) |
| Tests | `TcpProxy` ([tests/tcp_proxy.py](../../tests/tcp_proxy.py)) | Sits between a service and MySQL or the broker. `cut()` drops every connection and refuses new ones, and `restore()` reopens. It needs no Docker access, so it runs the same locally and in CI. |

For example: `FAULT_DUPLICATE_RATE=0.2 FAULT_INVALID_RATE=0.1 docker compose up -d simulator`.

## Automated scenarios (`tests/reliability`)

Each scenario runs the real receiver and simulator as processes, with their own topic root (`rtest…/sensors`), sensor IDs and receiver session, so they can't interfere with other tests or a running stack. Each checks that **nothing is lost and nothing is stored twice**, comparing every reading the simulator logged as sent or buffered with MySQL, and measures recovery. Run `pytest tests/reliability -s` to see the numbers.

Results (2026-10-30, Docker on an Apple-silicon Mac, 5 sensors at 1 reading/s, 10 s outages):

| Scenario | Held / queued | Lost | Duplicates | Recovery |
|---|---|---|---|---|
| MySQL unreachable 10 s | 50 held by the receiver | 0 | 0 | backlog stored 5.3 s after MySQL was back (backoff step); no OFFLINE alerts with a 5 s offline timeout |
| Broker unreachable for sensors 10 s | 75 buffered by the sensors | 0 | 0 | all stored 5.4 s after the broker was reachable; each sensor's rows in order |
| Receiver killed (SIGKILL) for 10 s | 50 queued by the broker | 0 | 0 | backlog stored 0.3 s after restart |
| Faulty sensors (20 % invalid, 20 % malformed, 30 % duplicate) | 20 faults injected | 0 | 0 | 17 rejected, 6 duplicates ignored |

Recovery after a MySQL outage is bounded by the retry backoff, which is at most 10 s.

## Verified on the real Docker stack

- `docker compose stop mysql` for 20 s while 5 sensors reported: the receiver logged `Database unreachable (2013 …); holding`, then `Database back after 25.1 s; storing 26 held message(s)`. In that window the simulator sent 48 readings and **48 were stored**. No OFFLINE alerts.
- `docker compose restart mqtt`: sensors disconnected, buffered, reconnected within 1 s and resent. 21 readings stored for the window (about 20 expected), **0 duplicate rows**.
- One run first looked like data loss (23 of about 44 stored). The log showed the **whole Mac had been suspended** for about 90 s: a `sleep 10` in the check took 95 s, and every container was silent. Re-run with the machine awake, it was 48 of 48. A host that sleeps stops the simulated sensors too. This is not a pipeline defect, but it is worth knowing when reading measurements.

## Defects found while building this

1. **paho acknowledged QoS 1 messages before they were stored.** The ack went out when `on_message` returned, which was only when the message was queued in memory, so a receiver crash lost whatever was queued. Fixed with manual acks after storing.
2. **The first broker-outage test passed while losing every buffered reading.** It compared MySQL with the readings logged as *sent*, and the 50 *buffered* readings were never sent: paho's reconnect backoff had grown to 30 s, and the test stopped the simulator first. The test now counts buffered readings as owed. The reconnect backoff is capped at 10 s, and the simulator flushes on shutdown and logs any it couldn't send.
3. **`publish()` reported success without a PUBACK.** It returned True after `wait_for_publish` timed out, so a reading lost mid-publish counted as sent. It now returns `is_published()`.
