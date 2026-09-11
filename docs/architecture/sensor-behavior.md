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

## Data ranges (used for validation and boundary testing)

| Field | Min | Max |
|---|---|---|
| Temperature | -40 °C | 85 °C |
| Humidity | 0 % | 100 % |
| Pressure | 300 hPa | 1100 hPa |
| Light | 0 lux | 100000 lux |
| Battery | 0 % | 100 % |

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
