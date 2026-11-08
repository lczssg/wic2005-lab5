#!/usr/bin/env python3
"""Replay a saved command file through Mininet's real CLI, echoing commands."""
import os
import sys
from mininet.cli import CLI
import topo


class RecordedCLI(CLI):
    def onecmd(self, line):
        print(f"mininet> {line.rstrip()}", flush=True)
        return super().onecmd(line)


commands = os.environ["LAB_COMMANDS"]
topo.CLI = lambda net: RecordedCLI(net, script=commands)
topo.main()
