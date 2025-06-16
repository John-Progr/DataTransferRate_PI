# DataTransferRate_PI
This is the script for measuring data transfer rate depending on the role of each node
# DataTransferRate
An api that when hit it will return the data transfer rate using iperf3 in multihop scenario inlcuding 4 raspberry pi and more (to be continued)

Examining the scenario where we wont run olsr, so the routing tables won't be populated, we need to put fixed ips on the routing tables, wo we can measure data transfer rate by running iperf3 client/server. The keyword here is the multihop 

So if a node is reachable from another node e.g. 192.168.2.10 ( iperf client) to 192.168.2.30 (iperf server) then iperf sends tcp packets and eventually the iperf client gets the measurements. But when we need multihop scenario we need to send from 192.168.2.10 to 192.168.2.30 via another node (or nodes) e.g. 192.168.2.20 (or 192.168.2.20 and 192.168.2.40). These nodes act as forwarders and they need to know where to send the packets to, so they need to check on routing tables

Just a reminder:

client -> iperf3 -c 192.168.2.x
server -> iperf3 -s

We need to highlight this one:

If we dont run Olsrd or something similar ( ad hoc protocol) then each raspberry pi (node) won't forward packets so we need to enable /proc/sys/net/ipv4/ip_forward (this will reset to 0 when we restart, something solvable if we place it in rc.local or even edit the configuration to survive the reboot)
We can check it by typing -> cat /proc/sys/net/ipv4/ip_forward
We can enable it temporarily by typing -> sudo sysctl -w net.ipv4.ip_forward=1


when we set up our raspberry pis we notice that if we type route -n all the routing tables are empty 

We can add an entry to the routing table wiritng -> sudo ip route add <destination-network> via <next-hop-ip> dev <interface> 
dev <interface> can be ommitted though...


![image](https://github.com/user-attachments/assets/cc5407c0-15b8-4b5e-b0e0-6b338595c390)


tcpdump is a great tool to start understanding how packets move in your network

the easiest way to test it is by pinging a node that is within your reach 

but there is a cath with the ping request ->


i need to highlight for three nodes we dont need to put every fixed ip in the routing tables of each node...
but we need to to be sure!

also i noticed that the ip.forward =0/1 is buggy and we need to play with wlan0 enable/disable

The idea is as follows:
Each raspberry pi is active
the input will be as follows -> PiSource,PiDest,OLSR=off/on,Path

api needs to send information o my raspberry pis

This info includes 
Preprocessing

I send RaspberryPi source that i need you to run iperfclient and 
