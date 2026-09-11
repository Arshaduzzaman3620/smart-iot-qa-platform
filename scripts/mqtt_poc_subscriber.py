"""Phase 2 proof-of-concept: subscribe to the test topic and print incoming messages."""
import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC = "iot/sensors/SENSOR-001/telemetry"


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected to broker (reason_code={reason_code})")
    client.subscribe(TOPIC)
    print(f"Subscribed to {TOPIC}")


def on_message(client, userdata, msg):
    print(f"Received on {msg.topic}: {msg.payload.decode()}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
print("Waiting for messages... (Ctrl+C to stop)")
client.loop_forever()
