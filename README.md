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
