# MQTT Topic Design

| Purpose | Topic |
|---|---|
| Telemetry | `iot/sensors/{sensor_id}/telemetry` |
| Status | `iot/sensors/{sensor_id}/status` |
| Command | `iot/sensors/{sensor_id}/command` |
| Response | `iot/sensors/{sensor_id}/response` |
| Firmware | `iot/sensors/{sensor_id}/firmware` |

Example: `iot/sensors/SENSOR-001/telemetry`

The receiver subscribes with a wildcard to catch every sensor: `iot/sensors/+/telemetry`.

## Telemetry message

```json
{
  "sensor_id": "SENSOR-001",
  "timestamp": "2026-09-07T10:00:00Z",
  "temperature": 24.5,
  "humidity": 48.0,
  "pressure": 1012.4,
  "light": 350,
  "battery": 91
}
```

Required fields: `sensor_id`, `timestamp`, `temperature`, `humidity`, `pressure`, `light`, `battery`. Messages missing any required field, containing invalid JSON, or failing range validation (see [sensor-behavior.md](../architecture/sensor-behavior.md)) must be rejected by the receiver and logged, never stored.
