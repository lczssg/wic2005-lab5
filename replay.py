#!/usr/bin/env python3
"""Replay a saved command file through Mininet's real CLI, echoing commands."""
import os
from datetime import datetime, timezone
from pathlib import Path
from mininet.cli import CLI
import topo


class RecordedCLI(CLI):
    def onecmd(self, line):
        print(f"mininet> {line.rstrip()}", flush=True)
        return super().onecmd(line)


commands = os.environ["LAB_COMMANDS"]
print(f"Run started (UTC): {datetime.now(timezone.utc).isoformat()}", flush=True)
# BMv2 appends its switch logs. Earlier runs have been archived by the command file.
for switch in ("s1", "s2"):
    Path("logs").mkdir(exist_ok=True)
    Path(f"logs/{switch}.txt").write_text("")
topo.CLI = lambda net: RecordedCLI(net, script=commands)
topo.main()
