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

## Phase 2 verification (MQTT broker proven working)

Before any sensor or receiver code was written, the broker itself was proven working with a minimal publisher/subscriber:

```text
Publisher -> Mosquitto -> Subscriber
```

**Broker**: Mosquitto runs in Docker (`eclipse-mosquitto:2`), config at `docker/mosquitto/mosquitto.conf` (plain listener on 1883, anonymous access — local dev only, revisited in the security phase).

```
docker run -d --name smartiot-mosquitto -p 1883:1883 \
  -v "$(pwd)/docker/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf" \
  eclipse-mosquitto:2
```

**Client scripts**: `scripts/mqtt_poc_publisher.py` and `scripts/mqtt_poc_subscriber.py` (paho-mqtt, installed via `scripts/requirements.txt` into the project `.venv`).

**Result**: subscriber connected, subscribed to `iot/sensors/SENSOR-001/telemetry`, and received `"Hello from SENSOR-001"` published by the publisher script — confirming the broker routes messages correctly end to end. These PoC scripts are throwaway; the real sensor simulator and receiver (Phases 3–7) replace them.
