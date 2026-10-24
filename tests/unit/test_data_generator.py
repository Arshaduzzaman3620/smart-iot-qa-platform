import random

import pytest

from generator.data_generator import (
    BATTERY_RANGE,
    HUMIDITY_RANGE,
    LIGHT_RANGE,
    PRESSURE_RANGE,
    TEMPERATURE_RANGE,
    DataGenerator,
)
from validator.telemetry_validator import RANGES

STEPS = 2000

# (method, range, max drift per step) -- drift values from generator/data_generator.py.
CHANNELS = [
    ("generate_temperature", TEMPERATURE_RANGE, 0.5),
    ("generate_humidity", HUMIDITY_RANGE, 1.0),
    ("generate_pressure", PRESSURE_RANGE, 0.8),
    ("generate_light", LIGHT_RANGE, 20.0),
]


@pytest.fixture(autouse=True)
def seeded():
    random.seed(1234)


@pytest.mark.parametrize("method, bounds, delta", CHANNELS, ids=[c[0] for c in CHANNELS])
def test_values_drift_gradually_and_stay_in_range(method, bounds, delta):
    generate = getattr(DataGenerator(), method)
    value = (bounds[0] + bounds[1]) / 2
    for _ in range(STEPS):
        new_value = generate(value)
        assert bounds[0] <= new_value <= bounds[1]
        # Small realistic change, not a random jump (+0.01 for rounding to 2 dp).
        assert abs(new_value - value) <= delta + 0.01
        value = new_value


@pytest.mark.parametrize("method, bounds, delta", CHANNELS, ids=[c[0] for c in CHANNELS])
def test_values_are_clamped_at_the_boundaries(method, bounds, delta):
    generate = getattr(DataGenerator(), method)
    for _ in range(200):
        assert generate(bounds[0]) >= bounds[0]
        assert generate(bounds[1]) <= bounds[1]


def test_battery_only_drains_and_never_goes_negative():
    generator = DataGenerator()
    battery = 1.0
    for _ in range(STEPS):
        new_battery = generator.generate_battery(battery)
        assert BATTERY_RANGE[0] <= new_battery <= battery
        battery = new_battery
    assert battery == 0.0


def test_values_have_at_most_two_decimals():
    generator = DataGenerator()
    for _ in range(100):
        value = generator.generate_temperature(21.123456)
        assert round(value, 2) == value


def test_generator_ranges_match_validator_ranges():
    # If these drift apart, the simulator could publish data the receiver rejects.
    assert TEMPERATURE_RANGE == RANGES["temperature"]
    assert HUMIDITY_RANGE == RANGES["humidity"]
    assert PRESSURE_RANGE == RANGES["pressure"]
    assert LIGHT_RANGE == RANGES["light"]
    assert BATTERY_RANGE == RANGES["battery"]
