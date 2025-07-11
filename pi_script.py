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
    
    def _on_message(self, client, userdata, rc):
        try:
            self.logger.info(f"Received message on {msg.topic}: {msg.payload.decode()}")
            payload = json.loads(msg.payload)
            #Here i insert what messages i want to extract!
            # I extract the messages about forwarder and stuff 
            # and i execute the datatransfer measurement and i save the result.json
        except Exception as e:
            self.logger.error(f"Error Processing message: {e}")

    

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
        



    def dataTransferMeasurement(self, role):
        if role == "sender":
            print("[INFO] Acting as sender...")

            try:
            # Run iperf3 client and save JSON output
                with open("result.json", "w") as outfile:
                    subprocess.run([
                    "iperf3",
                    "-c", sender_ip,
                    "--json"
                    ], check=True, stdout=outfile)

                print("[SUCCESS] iPerf3 test completed")

        elif role == "receiver":
            print("[INFO] Acting as receiver...")
            try:
            subprocess.run(["iperf3", "-s"], check=True)
            except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to run iperf3 as receiver: {e}")

        elif role == "forwarder":
            print("[INFO] Acting as forwarder... enabling IP forwarding.")
            try:
        
            # Enable IP forwarding
            subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)

            # Check current ip_forward status
            with open("/proc/sys/net/ipv4/ip_forward", "r") as f:
                    status = f.read().strip()
            print(f"IP forwarding is set to: {status}")

            our_ip = self.get_device_ip()

            if not our_ip:
                print("[ERROR] Could not determine our IP address for routing")
            else:
                print(f"Our IP address for routing: {our_ip}")
        
                # Add static route for 192.168.2.40 via our IP
                route_cmd = ["sudo", "ip", "route", "add", "192.168.2.40", "via", our_ip]
                # It might fail if the route already exists, so handle that gracefully
                result = subprocess.run(route_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("Route added successfully")
                else:
                    # Could be route exists or error
                    print(f"Failed to add route: {result.stderr.strip()}")

            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed to enable IP forwarding or add route: {e}")



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
    

