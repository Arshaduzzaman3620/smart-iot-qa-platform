import random

TEMPERATURE_RANGE = (-40.0, 85.0)
HUMIDITY_RANGE = (0.0, 100.0)
PRESSURE_RANGE = (300.0, 1100.0)
LIGHT_RANGE = (0.0, 100000.0)
BATTERY_RANGE = (0.0, 100.0)


def _drift(previous: float, delta: float, bounds: tuple[float, float]) -> float:
    """Move the value slightly from its previous reading, clamped to valid bounds."""
    low, high = bounds
    new_value = previous + random.uniform(-delta, delta)
    return round(max(low, min(high, new_value)), 2)


class DataGenerator:
    """Generates realistic, gradually-varying telemetry values for one sensor."""

    def generate_temperature(self, previous: float) -> float:
        return _drift(previous, 0.5, TEMPERATURE_RANGE)

    def generate_humidity(self, previous: float) -> float:
        return _drift(previous, 1.0, HUMIDITY_RANGE)

    def generate_pressure(self, previous: float) -> float:
        return _drift(previous, 0.8, PRESSURE_RANGE)

    def generate_light(self, previous: float) -> float:
        return _drift(previous, 20.0, LIGHT_RANGE)

    def generate_battery(self, previous: float) -> float:
        # Battery only drains, very slowly, never regenerates on its own.
        drained = previous - random.uniform(0.0, 0.05)
        return round(max(BATTERY_RANGE[0], drained), 2)
