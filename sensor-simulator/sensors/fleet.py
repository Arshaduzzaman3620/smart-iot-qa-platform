import random

from sensors.environment_sensor import EnvironmentSensor

MAX_SENSORS = 1000


def sensor_ids(count: int, prefix: str = "SENSOR-") -> list[str]:
    """SENSOR-001, SENSOR-002, ... (SENSOR-001 stays the ID of the original single sensor)."""
    return [f"{prefix}{i:03d}" for i in range(1, count + 1)]


def create_fleet(count: int, rng: random.Random | None = None, prefix: str = "SENSOR-") -> list[EnvironmentSensor]:
    """Create `count` environment sensors with varied starting readings. No MQTT logic here."""
    if not 1 <= count <= MAX_SENSORS:
        raise ValueError(f"sensor count must be between 1 and {MAX_SENSORS}, got {count}")
    rng = rng or random.Random()

    fleet = []
    for number, sensor_id in enumerate(sensor_ids(count, prefix), start=1):
        sensor = EnvironmentSensor(sensor_id, name=f"Room {number} Sensor", location=f"Room-{number}")
        if count > 1:
            # Different rooms, different conditions -- otherwise every row on the dashboard looks identical.
            sensor.temperature = round(rng.uniform(18.0, 28.0), 2)
            sensor.humidity = round(rng.uniform(30.0, 65.0), 2)
            sensor.pressure = round(rng.uniform(995.0, 1025.0), 2)
            sensor.light = round(rng.uniform(150.0, 800.0), 2)
            sensor.battery = round(rng.uniform(60.0, 100.0), 2)
        fleet.append(sensor)
    return fleet


def start_offsets(count: int, interval: float) -> list[float]:
    """Spread first publishes evenly across one interval so the fleet doesn't publish in bursts."""
    return [interval * i / count for i in range(count)]
