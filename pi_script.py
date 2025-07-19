import logging
import time
import json
import paho.mqtt.client as mqtt

class MqttDevice:
    DEVICE_USERNAME = "pi"
    DEVICE_PASSWORD = "auebiot123"
    DEVICE_ID = "device1"
    MQTT_BROKER_HOST = "localhost"
    MQTT_BROKER_PORT = 1883  # No TLS

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        # Initialize MQTT client
        self.client = mqtt.Client()

        # Set username and password
        self.client.username_pw_set(
            username=self.DEVICE_USERNAME,
            password=self.DEVICE_PASSWORD
        )

        # Attach callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("✅ Successfully connected to MQTT broker")
            command_topic = f"command/{self.DEVICE_ID}/req/#"
            self.client.subscribe(command_topic)
            self.logger.info(f"📥 Subscribed to command topic: {command_topic}")
        else:
            self.logger.error(f"❌ Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.logger.warning(f"⚠️ Disconnected from MQTT broker with code {rc}")

    def _on_message(self, client, userdata, msg):
        self.logger.info(f"📩 Received message on topic '{msg.topic}': {msg.payload.decode()}")

    def connect(self):
        self.client.connect(self.MQTT_BROKER_HOST, self.MQTT_BROKER_PORT)
        self.client.loop_start()

    def send_telemetry(self, role):
        topic = "telemetry"
        message = f"STATE: Device role is {role}"
        self.client.publish(topic, message)
        self.logger.info(f"📤 Published telemetry to '{topic}': {message}")

    def run(self):
        self.logger.info("📡 Listening for messages...")
        self.send_telemetry("sender")  # or "client" / "server" etc.


def main():
    device = MqttDevice()
    device.connect()

    while True:
        try:
            device.run()
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n👋 Execution interrupted by user. Exiting...")
            print("🔄 Cleaning up resources...")
            device.client.loop_stop()
            device.client.disconnect()
            print("🛑 MQTT client disconnected")
            break
        except Exception as e:
            print(f"❗ An error occurred: {e}")


if __name__ == "__main__":
    main()
