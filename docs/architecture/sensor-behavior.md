# Sensor Behavior

## Sensor types

Initial implementation: **ENVIRONMENT_SENSOR** only, producing temperature, humidity, pressure, light, and battery.

Later (not before the environment sensor works end-to-end): `MOTION_SENSOR`, `AIR_QUALITY_SENSOR`, `POWER_SENSOR`.

## Sensor object

```json
{
  "sensor_id": "SENSOR-001",
  "sensor_type": "ENVIRONMENT",
  "name": "Room A Sensor",
  "location": "Room-A",
  "status": "ONLINE",
  "firmware_version": "1.0.0",
  "battery": 92
}
```

Fields: `sensor_id`, `sensor_type`, `name`, `location`, `status`, `firmware_version`, `battery`, `created_at`, `last_seen`.

## Sensor states

Initial: `ONLINE`, `OFFLINE`, `ERROR`. Later: `CONNECTING`, `UPDATING`.

A sensor becomes `ONLINE` when the receiver stores a reading from it, and `OFFLINE` after `OFFLINE_TIMEOUT` seconds (default 30) with no stored reading. See [alerts.md](alerts.md).

## Data ranges (used for validation and boundary testing)

| Field | Min | Max |
|---|---|---|
| Temperature | -40 °C | 85 °C |
| Humidity | 0 % | 100 % |
| Pressure | 300 hPa | 1100 hPa |
| Light | 0 lux | 100000 lux |
| Battery | 0 % | 100 % |

## Running many sensors

`SENSOR_COUNT` (default 1, max 1000) sets how many sensors the simulator runs: `SENSOR-001` … `SENSOR-NNN`, located in `Room-1` … `Room-N`. Each sensor:

- has its own MQTT connection (client ID = sensor ID), like separate physical devices;
- starts from different, valid readings (only when `SENSOR_COUNT > 1`; a single sensor keeps the original defaults);
- publishes on a fixed schedule, with first publishes spread evenly across one interval so the fleet doesn't send in bursts.

Telemetry is published at QoS 1. While the broker is unreachable, each sensor keeps up to `SENSOR_BUFFER_MAX` (1000) readings and sends them in order after reconnecting. `FAULT_INVALID_RATE`, `FAULT_MALFORMED_RATE` and `FAULT_DUPLICATE_RATE` inject bad messages ([reliability.md](../testing/reliability.md)).

`SENSOR_ID_PREFIX` (default `SENSOR-`) changes the ID prefix. Tests run the real simulator as `TEST-SIMxxxxxx-001` so they never collide with real sensors.

Each sensor also announces its metadata on `iot/sensors/{id}/status` (retained) when it connects, and carries out `REQUEST_TELEMETRY`, `SET_INTERVAL` and `RESTART` commands from `iot/sensors/{id}/command`. Commands are queued from the MQTT threads and run on the main loop, which owns all sensor state. See [commands.md](commands.md).

Stopping (Ctrl+C, SIGTERM, Ctrl+Break on Windows) finishes the current reading, disconnects every sensor cleanly, and logs `Simulator stopped`.

## Data generation logic

1. Create a sensor.
2. Connect to MQTT.
3. Generate sensor values (small realistic variation from the previous reading, not random jumps).
4. Build a telemetry message.
5. Publish it.
6. Wait for the configured interval (default 5s, via `SENSOR_INTERVAL` env var).
7. Repeat until stopped.

## Simulator internal structure

```text
SensorSimulator
   +-- Sensor            (state, identity — no DB or MQTT logic)
   +-- DataGenerator     (temperature/humidity/pressure/light/battery generation)
   +-- MQTTClient        (connect, publish, reconnect — no calculation logic)
   +-- Configuration
   +-- Logger
```
