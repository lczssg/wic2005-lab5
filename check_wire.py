#!/usr/bin/env python3
"""Small host-format and input-boundary check; actual switch tests are separate."""
from contextlib import redirect_stdout
from io import StringIO
import struct
import subprocess
import sys
from scapy.all import Ether, IP, UDP, Raw
from send import MyTunnel as SendTunnel
from receive import MyTunnel as ReceiveTunnel, show

for hops in (0, 1, 2, 4, 255):
    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / SendTunnel(dst_id=3, hops=hops) / IP(src="10.1.0.1", dst="10.1.0.3") / UDP(sport=4321, dport=4321) / Raw(b"wire-check")
    wire = bytes(packet)
    assert wire[14:19] == struct.pack("!HHB", 0x0800, 3, hops)
    decoded = ReceiveTunnel(wire[14:])
    assert decoded.hops == hops and decoded.dst_id == 3
    assert decoded[IP].src == "10.1.0.1" and decoded[IP].dst == "10.1.0.3"
    assert decoded[UDP].dport == 4321 and decoded[Raw].load == b"wire-check"
    output = StringIO()
    with redirect_stdout(output):
        show(Ether(dst="ff:ff:ff:ff:ff:ff") / decoded)
    assert f"hops={hops}" in output.getvalue()

for args in (("--hops", "-1"), ("--hops", "256"), ("--tunnel", "65536")):
    result = subprocess.run([sys.executable, "send.py", "10.1.0.3", "invalid", *args], capture_output=True, text=True)
    assert result.returncode == 2 and "must be between" in result.stderr

print("PASS: 5-byte network-order header, sender/receiver agreement for 0/1/2/4/255, receiver output, and invalid CLI bounds")
