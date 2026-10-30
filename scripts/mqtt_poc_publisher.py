"""Phase 2 proof-of-concept: publish a single test message and exit."""
import os

import paho.mqtt.client as mqtt

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
TOPIC = "iot/sensors/SENSOR-001/telemetry"
MESSAGE = "Hello from SENSOR-001"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
# Since Phase 15g the broker requires sign-in; the test-harness account may use any topic.
client.username_pw_set("qa", os.getenv("QA_MQTT_PASSWORD", "qa-dev-password"))
client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)

result = client.publish(TOPIC, MESSAGE)
result.wait_for_publish()
print(f"Published to {TOPIC}: {MESSAGE}")

client.disconnect()
