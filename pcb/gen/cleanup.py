"""Removes dangling track stubs the autorouter leaves behind: segments with an end that touches
no pad, via or other track of the same net. Run with KiCad's Python before fixup.py."""
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import board as B  # noqa: E402

b = pcbnew.LoadBoard(B.OUT)
removed = 0
# --drc: only remove what the last DRC report calls dangling (it judges track ends more strictly
# than the check below). Its own run, since KiCad's Python handles go stale after removals.
while "--drc" not in sys.argv:
    tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads()]

    def connected(t, pt):
        net, layer = t.GetNetCode(), t.GetLayer()
        for o in tracks:
            if o is not t and o.GetNetCode() == net and o.GetLayer() == layer and o.HitTest(pt, 1000):
                return True
        if any(v.GetNetCode() == net and v.HitTest(pt, 1000) for v in vias):
            return True
        return any(p.GetNetCode() == net and p.IsOnLayer(layer) and p.HitTest(pt, 1000) for p in pads)

    def inside_one_pad(t):
        # Both ends in the same pad: the segment joins nothing that wasn't already joined.
        return any(p.GetNetCode() == t.GetNetCode() and p.IsOnLayer(t.GetLayer())
                   and p.HitTest(t.GetStart(), 0) and p.HitTest(t.GetEnd(), 0) for p in pads)

    dangling = [t for t in tracks if not t.IsLocked() and (
        not (connected(t, t.GetStart()) and connected(t, t.GetEnd())) or inside_one_pad(t))]
    if not dangling:
        break
    for t in dangling:
        b.Remove(t)
    removed += len(dangling)
# Whatever the last DRC still called dangling (it judges ends more strictly than the above).
report = os.path.join(os.path.dirname(B.OUT), "drc.rpt")
if "--drc" in sys.argv and os.path.exists(report):
    import re
    text = open(report, encoding="utf-8").read()
    spots = [(float(x), float(y)) for x, y in re.findall(r"\[track_dangling\][^\n]*\n[^\n]*\n\s+@\(([-\d.]+) mm, ([-\d.]+) mm\)", text)]
    for t in list(b.GetTracks()):
        if t.GetClass() == "PCB_TRACK" and not t.IsLocked():
            sx, sy = pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)
            if any(abs(sx - x) < 0.002 and abs(sy - y) < 0.002 for x, y in spots):
                b.Remove(t)
                removed += 1
pcbnew.SaveBoard(B.OUT, b)
print(f"removed {removed} dangling track segments")
