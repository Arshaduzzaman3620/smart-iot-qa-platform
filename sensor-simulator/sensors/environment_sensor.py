from sensors.base_sensor import Sensor


class EnvironmentSensor(Sensor):
    """An ENVIRONMENT sensor: temperature, humidity, pressure, light, battery."""

    def __init__(self, sensor_id: str, name: str, location: str):
        super().__init__(sensor_id, sensor_type="ENVIRONMENT", name=name, location=location)
        self.temperature = 24.0
        self.humidity = 50.0
        self.pressure = 1013.0
        self.light = 400.0
