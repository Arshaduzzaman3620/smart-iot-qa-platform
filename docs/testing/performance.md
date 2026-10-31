# Performance

Two kinds of load (Phase 15g). **API load**: people looking at dashboards, measured with k6. **Ingestion load**: sensors sending telemetry, measured with `scripts/scale_check.py`. Machine: Apple-silicon Mac, everything in Docker Desktop (8 GB, all services on one host), one API process.

## How to run

```bash
docker compose up -d --build                                                  # the stack, with sensors
docker compose --profile perf run --rm k6 run -e PROFILE=load /scripts/api.js  # smoke | load | stress | spike | soak

docker compose -f compose.test.yaml run --rm tests \
  python scripts/scale_check.py --sensors 100 --interval 5 --duration 60
```

Each k6 virtual user (VU) is a dashboard tab. It fetches the sensor list, the active alerts and one sensor's 20 newest readings, then waits 1 s, which is 5× more often than the real dashboard's 5 s refresh. It signs in once, in `setup()`, so the test measures the API, not password hashing. Pass criteria: under 1 % failed requests, and p95 under 300 ms per endpoint.

## API results (final)

| Profile | Shape | Requests | Throughput | p95 | max | Failed |
|---|---|---|---|---|---|---|
| smoke | 1 VU, 30 s | 92 | 1 req/s | 8 ms | 27 ms | 0 % |
| load | 50 VUs, 2 min | 17 471 | 144 req/s | 38 ms | 197 ms | **0 %** ✓ |
| soak | 20 VUs, 3 min | 10 526 | 58 req/s | 30 ms | 101 ms | **0 %** ✓ (memory flat at 133 MiB) |
| stress | 0 → 300 VUs over 3 min | 63 791 | **303 req/s** | 387 ms | 718 ms | **0 %** |
| spike | 10 → 300 VUs in 10 s | 20 213 | 182 req/s | 454 ms | 510 ms | **0 %** |

Fifty dashboards at 5× the real refresh rate stay under 40 ms at p95. About 300 req/s is the ceiling of one API process here. Beyond it, requests wait in line (p95 grows to about 0.4 s), but none fail and none hang. The real dashboard sends 3 requests per 5 s refresh, so that is roughly 500 open dashboards.

## Defects found by the load tests

The first stress run found three problems, fixed one at a time and re-measured:

| Run | Throughput | Failed | max | After the test |
|---|---|---|---|---|
| Before | 124 req/s | 1.1 % (500s) | 60 s (k6 timeout) | **API dead**: `/health` timed out, no DB connections left |
| + async session cleanup, 5 s pool timeout, pure-ASGI middleware | 166 req/s | 1.9 % (`503 Database busy`) | 60 s | healthy |
| + auth with its own short session, pool sized to threads | 231 req/s | 0.66 % | 45 s | healthy |
| + concurrency limit | **303 req/s** | **0 %** | **0.7 s** | healthy |

1. **Connection leak that killed the API.** The DB session was closed in a *sync* dependency's cleanup, which FastAPI runs on a worker thread. Under overload all 40 threads were waiting for a pool connection, and when k6 gave up on a request, its cleanup never ran. The pool (5 + 10) stayed exhausted after the load ended. MySQL showed the API's 15 connections idle, and `/health` never answered. **Fix:** `get_db` is async, so the session is closed on the event loop and always closes. Pool exhaustion now answers `503 Database busy` after 5 s instead of a 500 after 30 s. The headers middleware became plain ASGI instead of `BaseHTTPMiddleware`.
2. **Throughput collapse in a spike (29 req/s, 13 % failed).** A request hops between worker threads (auth, endpoint, response serialization) and held its DB connection while waiting for the next hop. With 300 requests arriving at once, waiting requests held every connection, so working threads couldn't get one. **Fix:** the user check uses its own session and returns the connection at once, and the pool now matches the 40 threads.
3. **Too many requests inside at once.** That fix still left hops holding connections. **Fix:** `ConcurrencyLimit` admits at most 32 requests at a time (`API_MAX_CONCURRENCY`). The rest wait outside the app, holding nothing, in arrival order. One that waits more than 10 s (`API_MAX_WAIT`) gets `503 Server busy` with `Retry-After`, which never happened in these runs.

The 2.4× throughput gain came from removing that contention, not from more hardware.

## Ingestion results (100 sensors)

After Phase 15f added QoS 1, per-message acknowledgement after storing, and duplicate checks:

| Load | Sent | Stored | Missing / duplicates | Throughput | Max latency |
|---|---|---|---|---|---|
| 100 sensors every 5 s, 60 s | 1 196 | 1 196 | 0 / 0 | 19.9 msg/s | 1 s ✓ |
| 100 sensors every 1 s, 30 s | 2 977 | 2 977 | 0 / 0 | 99.1 msg/s | 1 s ✓ |

The extra work per message didn't cost throughput. 100 msg/s, 5× the 100-sensor target, is stored with at most 1 s latency, slightly better than Phase 15b's ceiling of about 95 msg/s (measured on a different machine). History: [scale-results.md](scale-results.md).

## Limits

- **One API process.** More would need a fixed `JWT_SECRET` (each process otherwise makes its own random one) and a shared login rate limiter.
- The numbers are from one laptop with everything in one Docker VM. A suspended Mac pauses everything (see [reliability.md](reliability.md)), so measure on an awake machine.
