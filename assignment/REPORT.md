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

`evidence/mixed.txt` starts at **16:53:22 UTC**, after prediction commit
`280401b`. Both programs compiled and loaded six table entries per switch.
The actual results match the prediction:

| Probe | Capture and receiver evidence |
|---|---|
| H=4, message `mixed`, exit 2 | Frame reaches h2; bytes include `0002 0345 ... 0040 1166 c60a`. Receiver prints **hops=3**, TTL 64. |
| H=5, same message and exit | Frame reaches h2; bytes instead include `0002 0445 ... 0040 1066 c60a`. Receiver log gains **no second delivery**. |
| Mixed loop, H=4 | Baseline **2/2** after the probes; then **7/6**, unchanged after five seconds. Delta **5/4**, eight forwards then drop on s1. |

The full captures are `evidence/mixed/h2cap-h4.txt` and `h2cap-h5.txt`.
At Ethernet byte offset 18 is the new hop byte. True IPv4 starts at 19, while
the legacy parser starts at 18. Its checksum positions are therefore bytes
28–29, the real IPv4 protocol and high checksum byte. H=5 changes byte 28 from
0x11 to 0x10; the real IPv4 checksum is then also inconsistent with its changed
protocol. The UDP-only receiver cannot decode this as the expected UDP message.
For H=4, those bytes happen to stay unchanged. This accidental success is not
wire-format compatibility. The s2 log confirms `parse_myTunnel` selects 0800,
the tunnel lookup still uses 0002/0003, and the checksum block runs on the
misaligned IPv4 extraction. All raw switch and receiver logs are in
`evidence/mixed/`.

The loop bound is weaker during rollout: only an upgraded switch consumes the
budget. Here every circuit returns to s1, so it eventually drops. A cycle wholly
inside old switches can run forever, and H no longer means H physical forwards.
The first probe's successful delivery alone would have hidden both problems.

### b. Safe rollout options

| Option | Deployment sequence and tradeoff |
|---|---|
| New EtherType with dual-format support | Reserve a distinct v2 type. First upgrade switches and receivers to recognize both layouts while senders still emit v1. Verify every switch on each eligible path supports v2, including failure paths; only then switch those senders. Drain v1 traffic before removing its parser. This permits staged service, but needs temporary dual parsers, configuration/version inventory and format-aware tests. An old switch receiving an unknown type drops in this lab, rather than silently misparsing it. Premature activation can still cause outages, so the capability barrier is essential. |
| Drain and coordinated cutover | Stop tunnel injection, drain or deliberately discard old in-flight packets, load the new program on all path switches, update host decoders and senders, verify tables, then resume with small probes. This avoids simultaneous format support but causes downtime and needs coordinated rollback. Queued old-format traffic must not be released into the new parser. |

I would use the first option where continuity matters and the second for a small
lab/maintenance window. Merely appending a field preserves the tunnel lookup
prefix but does not preserve the following IPv4 offset. A new version byte also
cannot rescue a parser that was never programmed to recognize it: a discriminator
and dual-format handling must be designed or predeployed before new traffic.
During migration, validate old-format paths and do not claim a network-wide hop
bound until every relevant forwarder enforces it.

### c. Data plane and control plane

Week 3's `check_paths()` can inspect a modeled forwarding graph before deployment,
detect cycles or dead ends and explain a bad path without first injecting traffic.
For this tunnel it would need the exit-ID table model; an IPv4-only model does not
describe `myTunnel_exact`. Its result is only as accurate and current as the model
and installation state. It can miss transient inconsistent updates, unexpected
failover or unmodeled/stale device entries.

The hop field limits what a real packet can do under the installed data plane,
without a controller reacting to every loop. It covers those transient cases if
the actual path enforces decrement and zero-drop. It does not find or repair the
wrong entry, prove destination reachability, prevent a black hole, or distinguish
a loop from a valid path exceeding the budget. Old-only cycles and reset/ignored
hop fields defeat its assumption. Real systems need predeployment path validation,
safe update procedures and an independent packet-lifetime bound together.

### d. Cost on a hardware switch at line rate

The tunnel header grows **32 → 40 bits**, adding eight header-vector bits and one
byte for parser extraction and deparser emission. When the frame really grows,
serialization uses another 8/R seconds at link rate R; Ethernet padding and MTU
boundaries affect the actual wire cost. This also reduces payload headroom near
the MTU. No new match key, table entries, SRAM/TCAM allocation, register or
per-flow state is required by this design.

Ingress needs a zero comparison, an eight-bit subtraction and conditional drop/
table selection; the defensive parser-error comparison uses existing architecture
metadata. The dependent operations need available ALUs/PHV routing and may affect
stage placement. I cannot infer an exact stage count or throughput from BMv2.
The compiler for the actual ASIC must confirm that it fits and sustains line rate.
The existing IPv4 checksum operation remains present; the hop byte is outside the
IPv4 header, so no new checksum is introduced for it. Operational costs include
host format changes, migration/testing and the temporary dual-format resources.

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
| `evidence/delivery.txt` and `delivery/` | C4 tunnel, budget boundaries and plain IPv4 results |
| `evidence/loop-after.txt` and `loop-after/` | C4 stable 3/2 processing counts and final s1 drop |
| `evidence/mixed.txt` and `mixed/` | C5 captures, parser/checksum behavior and stable mixed-loop counts |
| `evidence/host-check.txt` | Host wire layout, decoder display and invalid CLI input bounds |
| `evidence/compile-local.txt` | Final Codespace compiler command and successful result |

Base-lab experiments and wrap-up answers are in `../LAB-NOTES.md` and
`../lab-evidence/`. `../replay.py` echoes commands and uses the unchanged
Mininet topology via its native CLI script input. Each run archives its logs;
the runner clears append-only switch logs before the next fresh network.

Requirements checked: [Spectrum submission](https://spectrum.um.edu.my/mod/assign/view.php?id=1148969),
[teacher's Week 5 instructions](https://firdaussahran.github.io/wic2005/weeks/week-05/).
Spectrum specifies **13 November 2026 00:00 Asia/Kuala_Lumpur (UTC+8)** and a PR
link, with a green **Compile tunnel.p4** check. The PR is kept open for review.
