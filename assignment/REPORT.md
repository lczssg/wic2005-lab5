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

Runtime validation pending. This section will be completed from actual C4 runs.

## 5. Evaluation

Mixed-rollout prediction and experiment pending. The prediction will be recorded
and committed before running s1 new / s2 old.

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
