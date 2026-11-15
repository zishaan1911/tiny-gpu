"""Applies board.finalize() to the routed board without touching its routing, then refills the
zones. Run with KiCad's Python:  C:/Users/Zishaan/Tools/kicad/bin/python.exe fixup.py"""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import board as B  # noqa: E402
import netlist  # noqa: E402

b = pcbnew.LoadBoard(B.OUT)
B.finalize(b, netlist.resolve())
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(B.OUT, b)
print("finalized", B.OUT)
