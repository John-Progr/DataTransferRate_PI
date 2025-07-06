import subprocess
import json
import time
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta 


class HonoMqttDevice:
    DEVICE_AUTH_ID = ""
    DEVICE_PASSWORD = ""
    DEVICE_NAME =""
    MQTT_BROKER_HOST =""
    MQTT_BROKER_PORT = 8883
    TENANT_ID =""
    CA_FILE_PATH = "/tmp/c2e_hono_truststore.pem"


    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        self.client = mqtt.Client(client_id=self.DEVICE_AUTH_ID, clean_session=False)
        self.client.username_pw_set(
            username=f"{self.DEVICE_AUTH_ID}@{self.TENANT_ID}",
            password=self.DEVICE_PASSWORD
        )
        try:
            self.client.tls_set(
                ca_certs=self.CA_FILE_PATH,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCL_TLS
            )
            self.client.tls_insecure_set(True)
        except Exception as e:
            self.logger.error(f"TLS setup failed: {e}")
            raise
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.jsoninfo = JsonInfo()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Succesfully connected to MQTT broker")
            self.client.subscribe(f"command/{self.TENANT_ID}//req/#")
        else:
            self.logger.error(f"Connection failed with code {rc}")


    def _on_disconnect(self, client, userdata, rc):
        self.logger.warning(f"Disconnected with code {rc}")
    
    def _on_message(self, client, userdata, msg):
        try:
            self.logger.info(f"Received message on {msg.topic}: {msg.payload.decode()}")
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

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")


    

    def get_device_ip(self):
        try:
            # Get the IP address of the device on the wlan0 interface
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
        


    
    def dataTransferClient(self, wireless_channel, region, ip_server, ip_routing):
        print("[INFO] Acting as sender...")

        try:
            # 1. Set WLAN region
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")

            # 2. Update wireless_channel in /etc/network/interfaces.d/wlan0
            interfaces_file = "/etc/network/interfaces.d/wlan0"
            try:
                with open(interfaces_file, "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
                lines = []

            channel_line_index = None
            channel_pattern = re.compile(r"^\s*wireless_channel\s+\d+", re.IGNORECASE)

            # Find existing wireless_channel line
            for i, line in enumerate(lines):
                if channel_pattern.match(line):
                    channel_line_index = i
                    break

            new_line = f"wireless_channel {wireless_channel}\n"
            if channel_line_index is not None:
                lines[channel_line_index] = new_line
            else:
                # Append if not found
                lines.append(new_line)

            # Write back the updated lines
            with open(interfaces_file, "w") as f:
                f.writelines(lines)
            print(f"[INFO] Updated wireless_channel to {wireless_channel} in {interfaces_file}")

            # 3. Add route for ip_routing via our_ip
            our_ip = self.get_device_ip()
            if not our_ip:
                print("[ERROR] Could not determine our IP address for routing")
            else:
                print(f"[INFO] Adding route: {ip_routing} via {our_ip}")
                route_cmd = ["sudo", "ip", "route", "add", ip_routing, "via", our_ip]
                result = subprocess.run(route_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("[INFO] Route added successfully")
                else:
                    print(f"[WARNING] Failed to add route: {result.stderr.strip()} (may already exist)")

            # 4. Run iperf3 client and save JSON output
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

    def dataTransferServer(self, wireless_channel, region):
        print("[INFO] Acting as receiver...")

        try:
            # 1. Set WLAN region
            subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
            print(f"[INFO] Set wireless region to: {region}")

            # 2. Update wireless_channel in /etc/network/interfaces.d/wlan0
            interfaces_file = "/etc/network/interfaces.d/wlan0"
            try:
                with open(interfaces_file, "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
                lines = []

            channel_line_index = None
            channel_pattern = re.compile(r"^\s*wireless_channel\s+\d+", re.IGNORECASE)

            for i, line in enumerate(lines):
                if channel_pattern.match(line):
                    channel_line_index = i
                    break

            new_line = f"wireless_channel {wireless_channel}\n"
            if channel_line_index is not None:
                lines[channel_line_index] = new_line
            else:
                lines.append(new_line)

            with open(interfaces_file, "w") as f:
                f.writelines(lines)
            print(f"[INFO] Updated wireless_channel to {wireless_channel} in {interfaces_file}")

            # 3. Run iperf3 server
            subprocess.run(["iperf3", "-s"], check=True)
            print("[SUCCESS] iPerf3 server started")

        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Command failed: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")

    def forwarder(self, wireless_channel, region, ip_routing):
    print("[INFO] Acting as forwarder...")

    try:
        # 1. Set wireless region
        subprocess.run(["sudo", "iw", "reg", "set", region], check=True)
        print(f"[INFO] Set wireless region to: {region}")

        # 2. Update wireless_channel config in /etc/network/interfaces.d/wlan0
        interfaces_file = "/etc/network/interfaces.d/wlan0"
        try:
            with open(interfaces_file, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"[WARNING] {interfaces_file} not found, skipping wireless channel update.")
            lines = []

        channel_line_index = None
        channel_pattern = re.compile(r"^\s*wireless_channel\s+\d+", re.IGNORECASE)

        for i, line in enumerate(lines):
            if channel_pattern.match(line):
                channel_line_index = i
                break

        new_line = f"wireless_channel {wireless_channel}\n"
        if channel_line_index is not None:
            lines[channel_line_index] = new_line
        else:
            lines.append(new_line)

        with open(interfaces_file, "w") as f:
            f.writelines(lines)
        print(f"[INFO] Updated wireless_channel to {wireless_channel} in {interfaces_file}")

        # 3. Enable IP forwarding
        subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)
        with open("/proc/sys/net/ipv4/ip_forward", "r") as f:
            status = f.read().strip()
        print(f"IP forwarding is set to: {status}")

        # 4. Get our IP
        our_ip = self.get_device_ip()

        if not our_ip:
            print("[ERROR] Could not determine our IP address for routing")
        else:
            print(f"Our IP address for routing: {our_ip}")

            # 5. Add static route to ip_routing via our_ip
            route_cmd = ["sudo", "ip", "route", "add", ip_routing, "via", our_ip]
            result = subprocess.run(route_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Route to {ip_routing} added successfully via {our_ip}")
            else:
                print(f"Failed to add route: {result.stderr.strip()}")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed during forwarder setup: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")




    def extractMeasurement(self, role):
        if(role == "sender"):
            try:
                results_path = "./results.json"
                # Load the JSON data from the result file
                with open("result.json", "r") as file:
                    data = json.load(file)

                # Extract transfer rates
                sum_sent = data['end']['sum_sent']
                sum_received = data['end']['sum_received']
                sent_rate = sum_sent['bits_per_second']
                received_rate = sum_received['bits_per_second']

                 # Return as Mbps
                return [sent_rate / 1e6, received_rate / 1e6]

            except subprocess.CalledProcessError as e:
               print(f"[ERROR] Failed to run iperf3 as sender: {e}")
            except (json.JSONDecodeError, KeyError) as e:
               print(f"[ERROR] Failed to parse result.json: {e}")
                


    def send_telemetry(self,role):
        topic = "telemetry"
        device_ip = self.get_device_ip()
        # a function to extact the results.json if the role = sender
        payload = {
          "topic": f"org.acme/{self.DEVICE_NAME}/things/twin/commands/modify",
          "headers": {},
          "path": "/features/network/properties",
          "value": {
              "device_ip": device_ip,
              "sent_rate_mbps": rates[0],
              "received_rate_mbps": rates[1],  # Add device_ip field

          }
        }
        self.client.publish(topic, json.dumps(payload))
        self.logger.info(f"Published telemetry to {topic}: {json.dumps(payload)}")

    def connect(self):
           try:
             self.client.connect(self.MQTT_BROKER_HOST, self.MQTT_BROKER_PORT, 120)
             self.client.loop_start()  # Keeps the connection alive
             self.logger.info("Successfully connected to MQTT broker — Ready to receive commands.")
           except Exception as e:
             self.logger.error(f"Connection error: {e}")
             raise

    def run(self):

        try:
            while not self.message_queue.empty():
                msg = self.message_queue.get()
                try:
                    payload = json.loads(msg.payload)
                    self.logger.info(f"Processing message")
                    self.dataTransferMeasurement(self, payload.get("role"))
                    self.send_telemetry(self, payload.get("role"))
                
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
            


                    

           

    

    
def main():
    # HonoMqttDevice.wait_until_next_time(20, 48)

    device = HonoMqttDevice()
    device.connect()
    while True:
        try:
            device.run() # check for messages and send telemetry
            time.sleep(30) # Run every 30 seconds
        except KeyboardInterrupt:
            print("\nExecution interrupted by user. Exiting...")
            print("Cleaning up resources...")
            device.client.loop_stop()
            device.client.disconnect()
            print("MQTT client disconnected")
            break
        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
    

