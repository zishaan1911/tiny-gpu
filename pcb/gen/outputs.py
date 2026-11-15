"""Checks the routed board: KiCad's design-rule check, including parity with the schematic.
Writes pcb/drc.rpt and prints the summary.  Run with any Python:  python outputs.py
"""

import os
import subprocess

CLI = r"C:\Users\Zishaan\Tools\kicad\bin\kicad-cli.exe"
PCB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PCB = os.path.join(PCB_DIR, "tiny_gpu.kicad_pcb")


def main():
    drc = os.path.join(PCB_DIR, "drc.rpt")
    r = subprocess.run([CLI, "pcb", "drc", "--schematic-parity", "--severity-error", "--severity-warning",
                        "--format", "report", "-o", drc, PCB], capture_output=True, text=True)
    if r.returncode not in (0, 5):  # 5: violations found, listed in the report
        raise SystemExit(r.stdout + r.stderr)
    with open(drc, encoding="utf-8") as f:
        print("\n".join(l for l in f.read().splitlines() if l.startswith("**")))


if __name__ == "__main__":
    main()
