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

Schema will be implemented as SQLAlchemy models in Phase 8 (MySQL) — this document is the reference, not yet executable DDL.
