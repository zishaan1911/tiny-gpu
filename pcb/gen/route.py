"""Routes pcb/tiny_gpu.kicad_pcb with Freerouting, then pours ground on the outer layers and fills
every zone. Run with KiCad's Python after board.py:
    C:/Users/Zishaan/Tools/kicad/bin/python.exe route.py
"""

import os
import subprocess
import sys
import time

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import board as B  # noqa: E402

PCB = B.OUT
WORK = os.path.join(os.path.dirname(PCB), "route")
JAR = r"C:\Users\Zishaan\Tools\freerouting\freerouting-1.9.0.jar"


def main():
    os.makedirs(WORK, exist_ok=True)
    dsn = os.path.join(WORK, "tiny_gpu.dsn")
    ses = os.path.join(WORK, "tiny_gpu.ses")
    board = pcbnew.LoadBoard(PCB)
    if "--import-only" in sys.argv:
        # Freerouting already ran (e.g. on its own) and left its session file.
        finish(board, ses)
        return
    if os.path.exists(ses):
        os.remove(ses)

    # Remove any earlier routing so the router starts clean, unless asked to only finish the
    # connections still missing (--finish), keeping what is already routed.
    finishing = "--finish" in sys.argv
    if not finishing:
        for t in list(board.GetTracks()):
            board.Remove(t)
    # The outer ground pours go back on after routing; left in, they'd wall off both layers.
    for z in list(board.Zones()):
        if z.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            board.Remove(z)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        raise SystemExit("DSN export failed")

    start = time.time()
    cmd = ["java", "-jar", JAR, "-de", dsn, "-do", ses, "-mp", "100", "-mt", "1"]
    print("routing:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    log = os.path.join(WORK, "freerouting.log")
    with open(log, "w", encoding="utf-8") as f:
        f.write(proc.stdout + "\n" + proc.stderr)
    if not os.path.exists(ses):
        raise SystemExit(f"Freerouting wrote no session file; see {log}")
    print(f"routed in {time.time() - start:.0f} s")
    finish(board, ses)


def finish(board, ses):
    # The session file carries every wire, old and new; importing it replaces the board's own.
    # KiCad's Python handles go stale after the import, so save and stop here: fixup.py (a fresh
    # process) pours the outer ground layers and fills every zone.
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
    pcbnew.SaveBoard(PCB, board)
    print("imported", ses, "- now run fixup.py")


if __name__ == "__main__":
    main()
