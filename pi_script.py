import logging
import time
import json
import paho.mqtt.client as mqtt
import subprocess

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
        try:
            self.logger.info(f"📩 Received message on topic '{msg.topic}': {msg.payload.decode()}")
            payload = json.loads(msg.payload)
            message = payload.get('value', {})
            role = message.get("role")

            if role == "server":
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                self.dataTransferServer(wireless_channel, region)

            elif role == "forwarder":
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_routing = message.get("ip_routing")
                self.forwarder(wireless_channel, region, ip_routing)

            elif role == "client":
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_server = message.get("ip_server")
                ip_routing = message.get("ip_routing")
                self.dataTransferClient(wireless_channel, region, ip_server, ip_routing)

            else:
                self.logger.warning(f"⚠️ Unknown role received: {role}")

            # Send telemetry ONLY after processing the message
            self.send_telemetry(role)

        except Exception as e:
            self.logger.error(f"❗ Error processing message: {e}")

    def dataTransferServer(self, wireless_channel, region):
        self.logger.info(f"🔧 Simulating dataTransferServer with channel='{wireless_channel}', region='{region}'")

    def forwarder(self, wireless_channel, region, ip_routing):
        self.logger.info(f"🔧 Simulating forwarder with channel='{wireless_channel}', region='{region}', ip_routing='{ip_routing}'")

    def dataTransferClient(self, wireless_channel, region, ip_server, ip_routing):
        self.logger.info(f"🔧 Simulating dataTransferClient with channel='{wireless_channel}', region='{region}', ip_server='{ip_server}', ip_routing='{ip_routing}'")

    def connect(self):
        self.client.connect(self.MQTT_BROKER_HOST, self.MQTT_BROKER_PORT)
        self.client.loop_start()

    def send_telemetry(self, role):
        # Run a ping command and capture output (example: ping google.com 1 time)
        try:
            ping_result = subprocess.run(
                ["ping", "-c", "1", "google.com"], capture_output=True, text=True, check=True
            )
            ping_output = ping_result.stdout.strip()
        except subprocess.CalledProcessError as e:
            ping_output = f"Ping failed: {e}"

        topic = "telemetry"
        message = f"STATE: Device role is {role}\nPing output:\n{ping_output}"
        self.client.publish(topic, message)
        self.logger.info(f"📤 Published telemetry to '{topic}': {message}")

    def run(self):
        self.logger.info("📡 Listening for messages...")
        # No telemetry here anymore — telemetry sent ONLY after message processed

def main():
    device = MqttDevice()
    device.connect()

    try:
        while True:
            device.run()  # Just logs listening, does NOT send telemetry periodically
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Execution interrupted by user. Exiting...")
        print("🔄 Cleaning up resources...")
        device.client.loop_stop()
        device.client.disconnect()
        print("🛑 MQTT client disconnected")
    except Exception as e:
        print(f"❗ An error occurred: {e}")

if __name__ == "__main__":
    main()
