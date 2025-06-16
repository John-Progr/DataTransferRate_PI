import subprocess
import json

# Set the role here
role = "forwarder"  # Change this to "receiver" or "forwarder"

# Target IP for sender
sender_ip = "192.168.2.40"

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

        print("[SUCCESS] iPerf3 test completed. Parsing result.json...")

        # Load the JSON data from the result file
        with open("result.json", "r") as file:
            data = json.load(file)

        # Extract transfer rates
        sum_sent = data['end']['sum_sent']
        sum_received = data['end']['sum_received']
        sent_rate = sum_sent['bits_per_second']
        received_rate = sum_received['bits_per_second']

        # Print results
        print(f"Sent Rate: {sent_rate / 1e6:.2f} Mbps")
        print(f"Received Rate: {received_rate / 1e6:.2f} Mbps")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to run iperf3 as sender: {e}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] Failed to parse result.json: {e}")

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

        our_ip = get_our_ip(sender_ip_

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
    

