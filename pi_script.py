import logging
import time
import json
import paho.mqtt.client as mqtt
import subprocess
import re

class MqttDevice:
    DEVICE_USERNAME = "pi"
    DEVICE_PASSWORD = "auebiot123"
    DEVICE_ID = "device1"
    MQTT_BROKER_HOST = "192.168.0.120"
    MQTT_BROKER_PORT = 1883

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        self.client = mqtt.Client()
        self.client.username_pw_set(
            username=self.DEVICE_USERNAME,
            password=self.DEVICE_PASSWORD
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # we add a gloabl variable for the role
        self.current_role = None
        self.iperf_server_process = None

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("✅ Successfully connected to MQTT broker")
            command_topic = f"command/{self.DEVICE_ID}/req/#"
            self.client.subscribe(command_topic)
            self.client.subscribe("telemetry")
            self.logger.info(f"📥 Subscribed to command topic: {command_topic}")
        else:
            self.logger.error(f"❌ Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.logger.warning(f"⚠️ Disconnected from MQTT broker with code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            self.logger.info(f"📩 Received message on topic '{msg.topic}': {msg.payload.decode()}")


            # If telemetry message and we're server, stop iperf3
            if msg.topic == "telemetry" and self.current_role == "server":
                self.logger.info("📊 Client finished, stopping iperf3 server")
                subprocess.run(["sudo", "pkill", "-f", "iperf3.*-s"], check=False)
                self.current_role = None
                return
    
            payload = json.loads(msg.payload)
            message = payload.get('value', {})
            role = message.get("role")


            if role == "server":
                self.flush_routes()
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                self.dataTransferServer(wireless_channel, region)

            elif role == "forwarder":
                self.flush_routes()
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_routing = message.get("ip_routing")
                self.forwarder(wireless_channel, region, ip_routing)

            elif role == "client":
                self.flush_routes()
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_server = message.get("ip_server")
                ip_routing = message.get("ip_routing")
                self.dataTransferClient(wireless_channel, region, ip_server, ip_routing)
                rates = self.extractMeasurement(role)
                self.send_telemetry(wireless_channel, rates[0])

            else:
                self.logger.warning(f"⚠️ Unknown role received: {role}")

        except Exception as e:
            self.logger.error(f"❗ Error processing message: {e}")

   

    def flush_routes(self):
        try:
            result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
            routes = result.stdout.strip().split('\n')

            for route in routes:
                route = route.strip()
                if not route:
                    continue

                parts = route.split()
                destination = parts[0]
                gateway = parts[2] if len(parts) > 2 else "0.0.0.0"

                # Keep default route, link-local, and main subnets
                if destination == "default" or \
                destination.startswith("169.254.") or \
                destination.startswith("192.168.0.") or \
                destination.startswith("192.168.2.") or \
                gateway == "0.0.0.0":
                    continue

                # Delete only other manual routes
                subprocess.run(["sudo", "ip", "route", "del", destination], check=False)
                print(f"[INFO] Flushed manual route: {destination}")

        except Exception as e:
            print(f"[ERROR] Failed to flush routes: {e}")

    
    def dataTransferServer(self, wireless_channel, region):
        print("[INFO] Acting as receiver...")

        try:
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")

            # NEW: Apply channel immediately
            subprocess.run(["sudo", "iwconfig", "wlan0", "channel", str(wireless_channel)], check=True)

            interfaces_file = "/etc/network/interfaces.d/wlan0"
            try:
                with open(interfaces_file, "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
                lines = []

            channel_line_index = None
            channel_pattern = re.compile(r"^\s*wireless-channel\s+\d+", re.IGNORECASE)

            for i, line in enumerate(lines):
                if channel_pattern.match(line):
                    channel_line_index = i
                    break

            new_line = f"   wireless-channel {wireless_channel}\n"  # ✅ fixed \n
            if channel_line_index is not None:
                lines[channel_line_index] = new_line
            else:
                lines.append(new_line)

            with open(interfaces_file, "w") as f:
                f.writelines(lines)
            print(f"[INFO] Updated wireless-channel to {wireless_channel} in {interfaces_file}")

            print("[INFO] Restarting wlan0 interface...")
            subprocess.run(["sudo", "ifdown", "wlan0"], check=True)
            subprocess.run(["sudo", "ifup", "wlan0"], check=True)
            print("[INFO] wlan0 restarted")

            # subprocess.run(["iperf3", "-s"], check=True)
            self.iperf_server_process = subprocess.Popen(["iperf3", "-s"])
            self.current_role = "server"

            print("[SUCCESS] iPerf3 server started")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Command failed: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")

    def forwarder(self, wireless_channel, region, ip_routing):
        print("[INFO] Acting as forwarder...")

        try:
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")

            subprocess.run(["sudo", "iwconfig", "wlan0", "channel", str(wireless_channel)], check=True)

            interfaces_file = "/etc/network/interfaces.d/wlan0"
            try:
                with open(interfaces_file, "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
                lines = []

            channel_pattern = re.compile(r"^\s*wireless-channel\s+\d+", re.IGNORECASE)
            new_line = f"   wireless-channel {wireless_channel}\n"
            lines = [new_line if channel_pattern.match(line) else line for line in lines]
            if all(not channel_pattern.match(line) for line in lines):
                lines.append(new_line)

            with open(interfaces_file, "w") as f:
                f.writelines(lines)
            print(f"[INFO] Updated wireless-channel to {wireless_channel} in {interfaces_file}")

            # Enable forwarding
            subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)
            print("[INFO] Enabled IP forwarding")

            subprocess.run(["sudo", "ifdown", "wlan0"], check=True)
            subprocess.run(["sudo", "ifup", "wlan0"], check=True)
            print("[INFO] wlan0 restarted")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed during forwarder setup: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")


    def dataTransferClient(self, wireless_channel, region, ip_server, ip_routing):
        print("[INFO] Acting as sender...")

        try:
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")

            subprocess.run(["sudo", "iwconfig", "wlan0", "channel", str(wireless_channel)], check=True)

            interfaces_file = "/etc/network/interfaces.d/wlan0"
            try:
                with open(interfaces_file, "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
                lines = []

            channel_pattern = re.compile(r"^\s*wireless-channel\s+\d+", re.IGNORECASE)
            new_line = f"   wireless-channel {wireless_channel}\n"
            lines = [new_line if channel_pattern.match(line) else line for line in lines]
            if all(not channel_pattern.match(line) for line in lines):
                lines.append(new_line)

            with open(interfaces_file, "w") as f:
                f.writelines(lines)
            print(f"[INFO] Updated wireless-channel to {wireless_channel} in {interfaces_file}")

            # ✅ Correct route: server via forwarder
            print(f"[INFO] Adding route: {ip_server} via {ip_routing}")
            route_cmd = ["sudo", "ip", "route", "add", ip_server, "via", ip_routing]
            result = subprocess.run(route_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("[INFO] Route added successfully")
            else:
                print(f"[WARNING] Failed to add route: {result.stderr.strip()}")

            with open("result.json", "w") as outfile:
                subprocess.run([
                    "iperf3",
                    "-c", ip_server,
                    "--json"
                ], check=True, stdout=outfile)

            print("[SUCCESS] iPerf3 test completed")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Command failed: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")

    def get_device_ip(self):
        try:
            command = "hostname -I | awk '{print $1}'"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            device_ip = result.stdout.strip()
            if device_ip:
                return device_ip
            else:
                self.logger.error("No IP address found for wlan0")
                return "0.0.0.0"
        except Exception as e:
            self.logger.error(f"Error fetching device IP: {e}")
            return "0.0.0.0"

    def extractMeasurement(self, role):
        try:
            with open("result.json", "r") as file:
                data = json.load(file)
            sent_rate = data['end']['sum_sent']['bits_per_second']
            received_rate = data['end']['sum_received']['bits_per_second']
            return [sent_rate / 1e6, received_rate / 1e6]
        except Exception as e:
            print(f"[ERROR] Failed to extract measurement: {e}")
            return [0, 0]

    def send_telemetry(self, wireless_channel, sent_rate):
        topic = "telemetry"
        payload = {
            "wireless_channel": wireless_channel,
            "sent_rate_mbps": round(sent_rate, 2)
        }
        message = json.dumps(payload)
        self.client.publish(topic, message)
        self.logger.info(f"📤 Published telemetry to '{topic}': {message}")

    def connect(self):
        self.client.connect(self.MQTT_BROKER_HOST, self.MQTT_BROKER_PORT)
        self.client.loop_start()

    def run(self):
        self.logger.info("📡 Listening for messages...")

def main():
    device = MqttDevice()
    device.connect()

    try:
        while True:
            device.run()
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
