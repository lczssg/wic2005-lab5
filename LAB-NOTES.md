# Week 5 lab results

Student suffix: **6101**. All tests used the personal template repository's 2-core
GitHub Codespace and `python3 replay.py --id 6101`. `replay.py` invokes the
unchanged `topo.main()` and Mininet's native CLI script interface, echoing each
command. Switch logs use UTC; the observation date locally is 9 November 2026,
Asia/Shanghai (UTC+8). The compiler is p4c-bm2-ss 1.2.5.18 on x86_64.

| Step | Actual observation | Evidence |
|---|---|---|
| 1–2 | Original program warns that the tunnel table is unused; both host pings succeed with reply TTL 62. | `lab-evidence/steps-1-3.txt` |
| 3 | Delete s2's h3 route (handle 2): 2/2 pings lost. Re-add 10.1.0.3/32 to port 3: 2/2 succeed. The tunnel probe reaches neither receiver; s1 reads EtherType 1212 and drops without a valid IPv4 header. | same transcript and `lab-evidence/steps-1-3/` |
| 4 | Parse and emit myTunnel. IP destination h3 and tunnel exit 2 still reach **h3**, tunnelled, TTL 62. Unused tunnel-table warning remains. | `lab-evidence/step-4.txt` and `step-4/` |
| 5 | Apply tunnel table first. The same destination/exit disagreement now reaches **h2**, TTL 64. Plain ping to h3 succeeds, TTL 62. Each switch loads six entries; no compiler warning. | `lab-evidence/step-5.txt` and `step-5/` |
| 6 | Omit tunnel emission deliberately. Compilation succeeds, but neither receiver prints delivery. s1 sends port 2; s2 parses proto_id 4500 and dst_id 0022, misses the tunnel table and drops. The working deparser was restored afterwards. | `lab-evidence/step-6.txt`, `step-6/`, including `broken-deparser.p4` |

## Explaining Step 6

`test 4` is six bytes. Its IPv4 length is 20 + 8 + 6 = 34 = 0x0022. After s1
removes the four tunnel bytes without changing EtherType 0x1212, s2 interprets
the IPv4 prefix `45 00 00 22` as the tunnel header: proto_id 0x4500, dst_id 34.
There is no exit 34. This is a format agreement failure across parser, ingress
and deparser, although each local program is syntactically valid.

## Wrap-up answers

1. At run time I can change a route's output port or add/delete an existing
   table entry (including mapping a tunnel exit). Adding a header field/parser
   state or changing a table's key/match kind needs recompilation and a pipeline
   reload. Runtime entries cannot invent fields or actions absent from the program.
2. Step 4's ingress still applies ipv4_lpm, so IP destination 10.1.0.3 selects
   h3. The parser marked myTunnel valid and the deparser emits it; forwarding by
   IPv4 does not invalidate or decapsulate that header.
3. In Step 5 tunnel packets use myTunnel_forward, which only selects a port.
   They bypass ipv4_forward, so inner IPv4 TTL remains 64. Plain ping packets
   take ipv4_forward at both switches, giving reply TTL 62.
4. The compiler warned about unused declarations/tables before they were wired
   in. It did not diagnose the wrong forwarding policy in Step 4 or the omitted
   tunnel emission in Step 6. Compilation proves local validity for BMv2, not
   end-to-end protocol agreement or delivery. Packet and switch-log tests are needed.

## Reproduction and retained attempts

For each phase, set `LAB_COMMANDS` to the corresponding `.commands` file and run
`python3 replay.py --id 6101`. Check out the phase's historical commit for its
program version. Each phase saves its switch/receiver logs before teardown.
The runner starts new switch log files because BMv2 otherwise appends to them.

`steps-1-3-attempt1.txt` records an interrupted stdin-driven attempt, replaced
by the completed CLI-script run. `step-4-appended*` retains the first successful
Step 4 run whose switch logs also contained the previous phase; `step-4*` without
that suffix is the isolated rerun. These are actual retained attempts, not new
measurements manufactured from expected results.

The teacher container needed the distribution package `openssh-server` for
GitHub CLI connectivity. No assignment source or host-network behavior was
changed to add that transport. Commits were created in the Codespace; the same
commit objects are transferred by Git bundle and pushed using the existing
local GitHub CLI login, because the container has no push credential helper.

AI assistance: OpenAI Codex read the requirements, prepared command replay,
made the specified edits, ran the tests and drafted these notes from actual
outputs. The assignment report will separately declare its AI use.
