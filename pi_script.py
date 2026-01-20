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
                ip_client = message.get("ip_client")
                ip_previous = message.get("previous_ip")
                self.dataTransferServer(wireless_channel, region, ip_client, ip_previous)

            elif role == "forwarder":
                self.flush_routes()
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_next_routing = message.get("ip_routing_next")
                ip_previous_routing = message.get("ip_routing_previous")
                ip_server = message.get("ip_server")
                ip_client = message.get("ip_client")
                self.forwarder(wireless_channel, region, ip_next_routing, ip_previous_routing, ip_server, ip_client)

            elif role == "client":
                self.flush_routes()
                region = message.get("region")
                wireless_channel = message.get("wireless_channel")
                ip_server = message.get("ip_server")
                ip_routing = message.get("ip_routing")
                self.dataTransferClient(wireless_channel, region, ip_server, ip_routing)
                rates = self.extractMeasurement(role)
                self.send_telemetry(wireless_channel, rates[1])

            else:
                self.logger.warning(f"⚠️ Unknown role received: {role}")

        except Exception as e:
            self.logger.error(f"❗ Error processing message: {e}")

   

    def flush_routes(self):
        try:
            # Get all current routes
            result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
            routes = result.stdout.strip().split('\n')

            for route_line in routes:
                parts = route_line.strip().split()
                if not parts:
                    continue

                # Identify a manual host route (e.g., 192.168.2.10 via 192.168.2.20)
                if "via" in parts and parts[0].startswith("192.168.2."):
                    # Get the destination and gateway from the parsed parts
                    destination = parts[0]
                    gateway = parts[2]
                    
                    # Use a specific, robust command to delete the route
                    subprocess.run(["sudo", "ip", "route", "del", destination, "via", gateway], check=False)
                    print(f"[INFO] Flushed specific manual route: {destination} via {gateway}")
                
        except Exception as e:
            print(f"[ERROR] Failed to flush routes: {e}")
            try:
                # Get all current routes
                result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
                routes = result.stdout.strip().split('\n')

                for route_line in routes:
                    parts = route_line.strip().split()
                    if not parts:
                        continue

                    destination = parts[0]
                    
                    # Identify a manual host route (e.g., 192.168.2.10 via 192.168.2.20)
                    # by checking if it contains the "via" keyword and is in the 192.168.2.x subnet.
                    if "via" in parts and destination.startswith("192.168.2."):
                        route_to_delete = " ".join(parts)
                        subprocess.run(["sudo", "ip", "route", "del", route_to_delete], check=False)
                        print(f"[INFO] Flushed specific manual route: {route_to_delete}")

            except Exception as e:
                print(f"[ERROR] Failed to flush routes: {e}")

    
    def dataTransferServer(self, wireless_channel, region, ip_client, ip_previous):
        print("[INFO] Acting as receiver...")

        try:
            subprocess.run(["sudo", "pkill", "-f", "iperf3.*-s"], check=False)
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")
            
            # NEW: Apply channel immediately
            subprocess.run(["sudo", "iwconfig", "wlan0", "channel", str(wireless_channel)], check=True)
            result = subprocess.run(
                ["iwconfig", "wlan0"],
                capture_output=True,
                text=True
            )
            print(result)
            
            print(f"[INFO] Adding route: {ip_server} via {ip_previous}")
            route_cmd = ["sudo", "ip", "route", "add", ip_client, "via", ip_previous]
            result = subprocess.run(route_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("[INFO] Route added successfully")
            else:
                print(f"[WARNING] Failed to add route: {result.stderr.strip()}")

            
            subprocess.run(["sudo", "pkill", "-f", "iperf3.*-s"], check=False)
            #time.sleep(1)  # small delay to ensure the port is released

            # subprocess.run(["iperf3", "-s"], check=True)
            self.current_role = "server"
            self.iperf_server_process = subprocess.Popen(["iperf3", "-s"])
            

            print("[SUCCESS] iPerf3 server started")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Command failed: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")



    
    def forwarder(self, wireless_channel, region, ip_next_routing, ip_previous_routing, ip_server, ip_client):
            print("[INFO] Acting as forwarder...")
        
            try:
                subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
                print(f"[INFO] Set wireless region to: {region}")
        
                subprocess.run(["sudo", "iwconfig", "wlan0", "channel", str(wireless_channel)], check=True)
        
                result = subprocess.run(
                    ["iwconfig", "wlan0"],
                    capture_output=True,
                    text=True
                )
                print(result)
    
                # Enable forwarding
                subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)
                print("[INFO] Enabled IP forwarding")
        
                # ✅ Add route: server via next hop
                print(f"[INFO] Adding route: server via {ip_routing}")
                route_1_cmd = ["sudo", "ip", "route", "add", ip_server, "via", ip_next_routing]
                route_2_cmd = ["sudo", "ip", "route", "add", ip_client, "via", ip_previous_routing]
                result = subprocess.run(route_1_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("[INFO] Route added successfully")
                else:
                    print(f"[WARNING] Failed to add route: {result.stderr.strip()}")
                result = subprocess.run(route_2_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("[INFO] Route added successfully")
                else:
                    print(f"[WARNING] Failed to add route: {result.stderr.strip()}")
        
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

            result = subprocess.run(
                ["iwconfig", "wlan0"],
                capture_output=True,
                text=True
            )
            
            # ✅ Correct route: server via forwarder
            print(f"[INFO] Adding route: {ip_server} via {ip_routing}")
            route_cmd = ["sudo", "ip", "route", "add", ip_server, "via", ip_routing]
            result = subprocess.run(route_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("[INFO] Route added successfully")
            else:
                print(f"[WARNING] Failed to add route: {result.stderr.strip()}")

            max_retries = 3
            retry_delay = 5  # seconds
            
            for attempt in range(1, max_retries + 1):
                try:
                    print(f"[INFO] Running iPerf3 test (attempt {attempt}/{max_retries})")
            
                    with open("result.json", "w") as outfile:
                        subprocess.run(
                            ["iperf3", "-c", ip_server, "--json"],
                            check=True,
                            stdout=outfile
                        )

                    print("[SUCCESS] iPerf3 test completed")
                    break  # ✅ stop retrying, continue function
            
                except subprocess.CalledProcessError as e:
                    print(f"[WARNING] iPerf3 failed (attempt {attempt}): {e}")
            
                    if attempt < max_retries:
                        print(f"[INFO] Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        print("[ERROR] iPerf3 failed after maximum retries")

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
        pass

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
