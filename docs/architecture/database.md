# Database Structure

Database: `smart_iot`

## sensors

`id, sensor_id, sensor_type, name, location, status, firmware_version, battery, last_seen, created_at, updated_at`

## telemetry

`id, sensor_id, timestamp, temperature, humidity, pressure, light, battery, received_at`

## alerts

`id, sensor_id, alert_type, severity, value, message, created_at, resolved_at, status`

## users

`id, username, password_hash, role, created_at`

Roles: `ADMIN`, `OPERATOR`, `VIEWER`

## firmware

`id, version, filename, checksum, size, created_at`

## firmware_updates

`id, sensor_id, firmware_id, status, started_at, completed_at, error_message`

## Relationships

```text
sensors
   +-- telemetry
   +-- alerts
   +-- firmware_updates
```

## Implementation status

`sensors`, `telemetry`, and `alerts` are implemented as SQLAlchemy models in [database/models.py](../../database/models.py) (Phase 8). `users`, `firmware`, and `firmware_updates` are still design only and arrive with their features in Phase 15.

Implementation notes:

- `telemetry.sensor_id` and `alerts.sensor_id` are foreign keys to `sensors.sensor_id` (the unique string ID such as `SENSOR-001`, not the integer `id`), with `ON DELETE CASCADE`. A sensor row must exist before its telemetry can be stored.
- Numeric readings are `DOUBLE`, not `FLOAT`, so values come back exactly as the sensor sent them. End-to-end tests compare dashboard values with published values.
- `status` defaults to `OFFLINE` (sensors) and `ACTIVE` (alerts), and `sensor_type` defaults to `ENVIRONMENT`. These are database-side defaults, so raw SQL inserts get them too.
- Indexes: `telemetry (sensor_id, timestamp)` for history queries, `alerts (sensor_id, status)` for active-alert lookups.

- `sensors.latest_telemetry_id` / `latest_reading_at` (Phase 14) point at each sensor's newest reading by sensor timestamp, so `GET /sensors` can join on the primary key instead of scanning telemetry. These columns have no FK constraint, because telemetry already references sensors and a constraint in both directions would conflict with the cascade.

## Schema upgrades

`python -m database.init_db` creates missing tables and then runs [database/migrations.py](../../database/migrations.py). Those are small, idempotent steps for columns added after a table was first created, because `create_all` never alters existing tables. Re-running is always safe.

## How the receiver writes

For each accepted message, `receiver/storage/telemetry_repository.py` runs one transaction:

1. Upsert `sensors` by `sensor_id`: insert if new (auto-registration), otherwise set `status=ONLINE`, `battery`, `last_seen` (receiver's UTC clock), and `updated_at`.
2. Insert one `telemetry` row. `timestamp` is the sensor's ISO 8601 value converted to UTC. `received_at` is set by MySQL.
3. Advance `sensors.latest_telemetry_id` / `latest_reading_at` to the new row, only if its timestamp is not older than the current latest. A delayed message stays in the history but never replaces a newer reading.
4. Update `alerts` (Phase 15a): resolve the sensor's active `OFFLINE` alert, and, only if step 3 advanced the pointer, raise / escalate / resolve threshold alerts. See [alerts.md](alerts.md).

Separately, the receiver's offline check sets silent `ONLINE` sensors to `OFFLINE` and inserts their `OFFLINE` alerts.

All `DATETIME` columns hold UTC, in whole seconds. The receiver truncates fractions itself, because MySQL would round them, which can put a time up to 0.5 s in the future. If MySQL is unavailable, the message is logged and dropped, and the receiver keeps running.

## Running it locally

```bash
# from the repo root
docker compose -f docker/docker-compose.yml up -d --wait mysql
pip install -r database/requirements.txt
python -m database.init_db        # creates any missing tables; safe to re-run
```

The container publishes MySQL on host port **3307** so it can't collide with a locally installed MySQL on 3306. Python running on the host therefore uses `MYSQL_HOST=localhost` and `MYSQL_PORT=3307` in `.env`. The database and app user are created from `.env` on the container's first start. Root gets a random password because the app never uses it.
