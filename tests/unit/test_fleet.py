import random

import pytest

from sensors.fleet import MAX_SENSORS, create_fleet, sensor_ids, start_offsets
from validator.telemetry_validator import RANGES


def test_sensor_ids_are_sequential_and_zero_padded():
    assert sensor_ids(3) == ["SENSOR-001", "SENSOR-002", "SENSOR-003"]
    assert sensor_ids(1000)[-1] == "SENSOR-1000"


def test_single_sensor_keeps_original_defaults():
    (sensor,) = create_fleet(1)
    assert sensor.sensor_id == "SENSOR-001"
    assert (sensor.temperature, sensor.humidity, sensor.pressure, sensor.light, sensor.battery) == (
        24.0, 50.0, 1013.0, 400.0, 100.0)


def test_fleet_has_unique_ids_and_metadata():
    fleet = create_fleet(100, random.Random(1))
    assert len({s.sensor_id for s in fleet}) == 100
    assert fleet[41].name == "Room 42 Sensor" and fleet[41].location == "Room-42"
    assert all(s.sensor_type == "ENVIRONMENT" and s.status == "OFFLINE" for s in fleet)


def test_fleet_starting_values_vary_and_are_valid():
    fleet = create_fleet(100, random.Random(1))
    assert len({s.temperature for s in fleet}) > 90  # not all identical
    for sensor in fleet:
        for field, (low, high) in RANGES.items():
            assert low <= getattr(sensor, field) <= high


@pytest.mark.parametrize("count", [0, -1, MAX_SENSORS + 1])
def test_rejects_invalid_counts(count):
    with pytest.raises(ValueError, match="sensor count must be between"):
        create_fleet(count)


def test_start_offsets_spread_evenly_across_one_interval():
    offsets = start_offsets(5, 5)
    assert offsets == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert all(0 <= o < 5 for o in start_offsets(100, 5))
    assert len(set(start_offsets(100, 5))) == 100


def test_custom_id_prefix():
    # Tests run the real simulator with their own prefix, so they never collide with SENSOR-001...
    assert sensor_ids(2, "TEST-SIM1-") == ["TEST-SIM1-001", "TEST-SIM1-002"]
    assert [s.sensor_id for s in create_fleet(2, prefix="X-")] == ["X-001", "X-002"]


def test_sensor_describes_itself_for_the_status_topic():
    (sensor,) = create_fleet(1)
    assert sensor.describe() == {"sensor_id": "SENSOR-001", "sensor_type": "ENVIRONMENT", "name": "Room 1 Sensor",
                                 "location": "Room-1", "firmware_version": "1.0.0", "interval": 5}
