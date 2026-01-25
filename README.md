# Dynamic Wireless Network Test Orchestrator (Raspberry Pi)

## Overview

This is a script meant to run on a Raspberry Pi which allows it to dynamically act as either a network client, server, or forwarder based on commands received over MQTT.

Its main purpose is to orchestrate wireless network performance tests using iPerf3, while dynamically configuring:

1. Wi-Fi regulatory region (not all channels are permitted in a specific region)
2. Wireless channel
3. IP routing paths
4. Traffic forwarding behavior

All coordination happens centrally via MQTT messages.

## High-Level Idea

Each Raspberry Pi runs the same script, making it easy to massively deploy across a network.

A controller (or orchestrator) — in our case a Digital Twin Manager — publishes MQTT commands telling each Pi which role to assume:

- **Server** – runs `iperf3 -s`
- **Client** – runs `iperf3 -c` and measures throughput
- **Forwarder** – forwards traffic between client and server

Once the test is finished, the client publishes telemetry results back to MQTT.

## Roles Explanation

### Server Role

When this role is assigned, the Raspberry Pi:

- Flushes old manual routes  
  (for safety purposes we start clean each time)
- Sets Wi-Fi regulatory region and channel
- Adds a route to reach the client via the previous hop  
  (or a previous forwarder)
- Stops any currently running iPerf3 server
- Starts a new iPerf3 server (`iperf3 -s`)
- Waits until telemetry is received
- Stops iPerf3 once the test is complete

### Client Role

When acting as a client, the Raspberry Pi:

- Flushes old routes
- Sets Wi-Fi regulatory region and channel
- Adds a route to the server  
  (via a forwarder if needed)
- Runs `iperf3 -c <server>` with JSON output enabled
- Retries up to 3 times if iPerf fails

The retry mechanism is intentional. Because communication is asynchronous, a node may attempt to run iPerf before other nodes have finished configuring. Failures are expected until all nodes are ready.

This approach works well for this experiment as it lowers message overhead on the control network. For other experiments, additional mechanisms such as QoS, acknowledgements, or explicit readiness responses may be required.

- Extracts throughput metrics from iPerf3 output
- Publishes telemetry results to MQTT

### Forwarder Role

When acting as a forwarder, the Raspberry Pi:

- Flushes old routes
- Sets Wi-Fi regulatory region and channel
- Enables IP forwarding
- Adds:
  - A route to the server via the next hop
  - A route to the client via the previous hop

**Purpose:**  
Act as a relay node in multi-hop wireless experiments.

## Telemetry and Measurements

- iPerf3 results are saved to `result.json`
- The script extracts:
  - Sent bits
  - Received bits
- Only received bits are published to MQTT, as this reflects what the server actually received

In a non-perfect wireless ad-hoc network, sent and received values always differ slightly, and the received value is the metric of interest for these experiments.

## Script Lifecycle

1. Start script
2. Connect to MQTT
3. Wait for commands
4. Reconfigure device dynamically
5. Run iPerf test
6. Send telemetry results
7. Wait for next command



## Technical Overview

This module implements an MQTT-controlled, role-based wireless networking agent designed for dynamic multi-hop throughput experiments using **iPerf3**. The device behavior (server, client, or forwarder) is fully orchestrated via MQTT commands, enabling real-time reconfiguration, controlled routing, and telemetry-driven feedback for external decision managers (e.g., Digital Twin or RL agents).

### Core Components

### 1. `__init__(self, logger=None)`
- Initializes logging and MQTT client configuration  
- Sets MQTT authentication credentials and callback handlers  
- Initializes runtime state variables for role execution and process tracking  

---

### 2. `_on_connect(self, client, userdata, flags, rc)`
- Handles successful or failed connections to the MQTT broker  
- Subscribes to role-based command and telemetry topics  
- Logs connection status  
- Enables dynamic reception of control commands specific to the device ID  

---

### 3. `_on_disconnect(self, client, userdata, rc)`
- Logs expected or unexpected MQTT disconnections  
- Provides visibility into network reliability and session health  
- Assists in diagnosing connectivity issues  

---

### 4. `_on_message(self, client, userdata, msg)`
- Parses incoming MQTT messages and extracts role instructions  
- Routes execution to the appropriate role handler (`server`, `client`, or `forwarder`)  
- Stops the iPerf server when telemetry indicates client completion  
- Acts as the core control logic for role-based behavior  
- Enables real-time reconfiguration driven entirely by MQTT commands  

---

### 5. `flush_routes(self)`
- Retrieves the current IP routing table  
- Removes manually added routes in the `192.168.2.x` subnet  
- Provides fallback deletion logic for robustness  
- Prevents stale or conflicting routes during role transitions  
- Ensures predictable routing behavior before applying new paths  

---

### 6. `dataTransferServer(self, wireless_channel, region, ip_client, ip_previous)`
- Configures wireless regulatory domain and channel  
- Adds routing to reach the client via a previous hop  
- Starts an iPerf3 server process  
- Enables the device to act as a throughput receiver  
- Supports multi-hop routing scenarios with explicit route control  

---

### 7. `forwarder(self, wireless_channel, region, ip_next_routing, ip_previous_routing, ip_server, ip_client)`
- Configures wireless parameters  
- Enables IP forwarding at the kernel level  
- Adds bidirectional routes between client and server  
- Allows the device to operate as an intermediate relay  
- Supports multi-hop wireless topology testing  

---

### 8. `dataTransferClient(self, wireless_channel, region, ip_server, ip_routing)`
- Configures wireless parameters and routing toward the server  
- Executes iPerf3 in client mode with retry logic  
- Ensures controlled and repeatable experiment execution  
- Saves throughput results in JSON format  

---

### 9. `extractMeasurement(self, role)`
- Reads iPerf3 JSON output from disk  
- Extracts sent and received bitrates  
- Converts values to Mbps to match iPerf3 real-time logging semantics  

---

### 10. `send_telemetry(self, wireless_channel, sent_rate)`
- Constructs and publishes telemetry data over MQTT  
- Reports wireless channel and measured throughput  
- Provides feedback to the DT manager for reward computation  

---

### 11. `connect(self)`
- Connects to the MQTT broker  
- Starts the MQTT network loop in a background thread  
- Ensures continuous, non-blocking MQTT communication  

---

### 12. `main()`
- Instantiates the `MQTTDevice`  
- Connects to the MQTT broker and enters the main execution loop  
- Handles graceful shutdown on user or system interruption  
- Serves as the program entry point and ensures controlled startup and cleanup of resources  
