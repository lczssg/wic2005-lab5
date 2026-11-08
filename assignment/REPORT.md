# Week 5 assignment — Put a limit on the tunnel

Student ID (last 4 digits only): **6101**

## 1. Analysis: the loop

I started from the completed Steps 4/5 program, saved unchanged as `tunnel_v1.p4`.
The C1 table dump shows exit 3 on s2 has handle 2 and initially selects port 3.
I changed it with `./p4cli s2 "table_modify MyIngress.myTunnel_exact MyIngress.myTunnel_forward 2 1"`.
s1's exit-3 entry already selects port 2 towards s2. A single h1 packet with
`--tunnel 3` therefore returns from s2 port 1 to s1 indefinitely.

In `evidence/loop-before.txt`, the first counts are s1 **74**, s2 **73** at
16:46:31 UTC on 8 November 2026. Five seconds later they are **932** and **932**.
These are cumulative processing events, not distinct packets. Each visit looks
up exit 3 again. The network was then stopped; it did not stop the loop itself.
The `loop-before-s1-sample.txt` and `loop-before-s2-sample.txt` files retain the
first 200 lines of each switch log, rather than the entire unbounded trace.
The local observation date is 9 November 2026 in UTC+8.

The tunnel path does not call `ipv4_forward`, so it never changes the inner TTL.
Even on the plain IPv4 path, this particular program only subtracts one from an
unsigned `bit<8>` TTL. It has no TTL-zero/one drop condition. A table-induced
IPv4 loop would therefore continue: 1 becomes 0 and is still forwarded, then
0 wraps to 255 on the next subtraction. Recomputing a checksum does not enforce
TTL policy, and BMv2 does not add IP-router behavior that P4 never specified.
I leave the plain IPv4 implementation unchanged for this focused tunnel task.

## 2. Design: the hop limit

The new wire order is **proto_id (16 bits), dst_id (16 bits), hops (8 bits)**,
network byte order: a five-byte tunnel header immediately after Ethernet and
before IPv4. Eight bits allow budgets 0–255 with one added byte; a smaller field
would need packing/padding choices, and 16 bits are unnecessary for this two-
switch topology. Appending the byte preserves the existing protocol and exit
offsets, but shifts IPv4 by one byte for an old parser. This is deliberately
evaluated in C5; unchanged prefix fields do not guarantee full compatibility.

The sender defaults to **4**, twice the two-switch delivery path. `--hops H`
allows boundary and loop tests. On each successfully parsed tunnel arrival,
ingress first checks for zero and drops immediately if exhausted. Otherwise it
subtracts one and applies the existing tunnel table. A table miss still drops.
The zero check occurs before subtraction, so unsigned underflow cannot renew
the budget. The drop branch cannot subsequently be overwritten by forwarding.
Parser errors are also dropped before any table is applied.

With initial H and a usable route, there can be at most H forwarding events.
In a closed loop the next arrival is processed and dropped: H+1 processing
events in total. Thus H=4 predicts s1/s2 processing counts **3/2**, four forwards
and a final drop on s1. Delivery across two switches with H=4 predicts an
arriving value of 2; H=2 may arrive with 0, since the host is not another switch.
H=0 must drop on s1 and H=1 on s2. These conventions make the word 'hop' precise.

## 3. Implementation

`tunnel.p4` adds `hops`, enforces the parser-error and zero guards, and decrements
inside the tunnel branch before `myTunnel_exact`. Extracting/emitting the named
header automatically includes the added field, so parser and deparser remain
consistent. The old program stays in `tunnel_v1.p4` for the mixed experiment.

`send.py` and `receive.py` use matching Scapy `ByteField` definitions. The sender
accepts `--hops` with default 4 and rejects values outside 0–255 before accessing
an interface. Tunnel IDs are similarly checked against their 16-bit width. The
receiver prints `hops` beside `dst_id`, while preserving the TTL and payload
display. Its sniff loop is under the normal Python main guard so its decoder
can be imported for the small `check_wire.py` check.

## 4. Evidence: it works

`evidence/delivery.txt` records the actual C4 run:

| Probe | Receiver observation |
|---|---|
| Default H=4, exit 2, IP destination 10.1.0.3 | h2 prints `h2-default`, hops **2**, TTL **64** |
| Default H=4, exit 3 | h3 prints `h3-default`, hops **2**, TTL **64** |
| H=2, exit 3 | h3 prints `exact-budget`, hops **0**, TTL **64** |
| H=0 and H=1, exit 3 | Neither receiver prints either marker; switch logs show the zero guard dropping them |
| H=255, exit 2 | h2 prints `max-budget`, hops **253**, TTL **64** |
| Plain `h1 ping -c 2 h3` | **2/2** replies, **0%** loss, reply TTL **62** |

The receiver and full switch logs are retained in `evidence/delivery/`. This
also demonstrates that tunnel routing can deliver to h2 despite the inner IP
destination naming h3. `evidence/host-check.txt` checks the host wire layout,
decoder output and CLI bounds separately from network behavior.

In the fresh network of `evidence/loop-after.txt`, the same exit-3 loop with
H=4 stops at s1 **3**, s2 **2**. Counts remain identical after another five
seconds. The complete trace in `evidence/loop-after/` shows two forwards per
switch and a final zero-guard drop at s1. Thus there are five processing events,
of which four forward the packet: exactly the C2 convention, without wraparound.

## 5. Evaluation

### a. Prediction recorded before the mixed run

This prediction is committed before running `--s2-program tunnel_v1.p4`.
For the first probe I will send `10.1.0.3 "mixed" --tunnel 2 --hops 4`.
s1 emits the prefix `08 00 00 02 03 45 00 00 21 ...`: it has reduced hops to 3.
Old s2 still extracts the first four tunnel bytes correctly, then starts its
20-byte IPv4 extraction at **03**, one byte early. Its apparent IPv4 version
is 0, IHL 3, TTL 0 and protocol 64. It does not validate version/IHL. The exit
lookup should still hit 2, and s2 should not decrement the real hop byte.

Crucially, the old checksum block runs for any valid extracted IPv4 header,
even on the tunnel path. Its checksum byte positions now overlap the real
IPv4 protocol byte and first checksum byte. It may corrupt those bytes.
A one's-complement calculation using the predicted IPv4 bytes
`45 00 00 21 00 01 00 00 40 11 66 c6 0a 01 00 01 0a 01 00 03`
gives a special case: inserting hop **3** and omitting the last IPv4 octet **3**
leaves the shifted checksum valid. The legacy checksum is **0x1166**, the
same two bytes already there. I therefore predict that this default probe
can reach h2 and print **hops=3**, TTL 64, despite the incorrect legacy parse.

For a second identical `mixed` message with initial **H=5**, s1 emits hops 4.
The same calculation predicts legacy checksum **0x1066**, changing the real
IPv4 protocol from **0x11 (UDP)** to **0x10**. A frame should reach h2, but the
UDP-only receiver should not print it. I will capture both frames, rather than
treat an empty receiver log as proof of no frame delivery.

For the exit-3 mixed loop with H=4, only s1 reduces the budget. I predict
**5 new processing events on s1 and 4 on s2**, eight forwards and a final s1
drop. The delivery probes will already have incremented the counters, so I
will record a baseline and compare deltas. No loop containing only old switches
would have a bound from this new field.

### Mixed-run observations

Pending actual run. Rollout, control-plane comparison and hardware evaluation
will be completed after inspecting the measured behavior.

## AI use

**OpenAI Codex** read Spectrum and the teacher's website/template, helped design
the hop semantics and tests, edited the P4 and Python files, operated the actual
Codespace experiments, inspected logs, and drafted this report from the outputs.
The terminal results are actual BMv2/Mininet runs, not AI-generated measurements.
The student must review, understand and be able to defend the submitted design,
code and analysis. AI assistance is declared under the course's **Level 3 (Open)**
policy. The course-wide Appendix 2(b) declaration is additionally required for
end-of-course submission; it is kept separately from the public repository.

## Evidence files

| File | What it shows |
|---|---|
| `evidence/loop-before.txt` | Real v1 loop and increasing processing counts |
| `evidence/loop-before-s1-sample.txt`, `loop-before-s2-sample.txt` | Bounded samples of the original loop parser/table trace |
| `evidence/delivery.txt` | Pending C4 tunnel and plain IPv4 results |
| `evidence/loop-after.txt` | Pending C4 bounded loop results |
| `evidence/mixed.txt` | Pending C5 mixed-program results |
