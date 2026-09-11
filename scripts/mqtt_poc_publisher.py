"""Phase 2 proof-of-concept: publish a single test message and exit."""
import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "iot/sensors/SENSOR-001/telemetry"
MESSAGE = "Hello from SENSOR-001"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

result = client.publish(TOPIC, MESSAGE)
result.wait_for_publish()
print(f"Published to {TOPIC}: {MESSAGE}")

client.disconnect()
