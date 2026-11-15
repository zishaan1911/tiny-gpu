"""Builds pcb/tiny_gpu.kicad_pcb from design.py: outline, four copper layers, rules, every
footprint placed with its nets, and the ground and 3.3 V planes. Routing is done afterwards by
route.py. Run with KiCad's own Python:  C:/Users/Zishaan/Tools/kicad/bin/python.exe board.py

Board: 76 x 56 mm, 4 layers (signal / GND / 3V3 / signal), JLCPCB standard rules.
USB-C on the left edge, the VGA socket on the right edge, data flowing left to right:
USB -> FT2232H -> FPGA -> DAC resistors -> VGA.
"""

import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import netlist  # noqa: E402
import sexpr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "tiny_gpu.kicad_pcb"))
MM = pcbnew.FromMM

X0, Y0, W, H = 100.0, 100.0, 76.0, 56.0
X1, Y1 = X0 + W, Y0 + H

# Fixed placements: (x, y, rotation in degrees). Coordinates in mm, y down, KiCad convention.
PLACE = {
    # Edge connectors: USB-C's front face (+3.65 mm in its footprint) on the left edge,
    # the VGA socket's board edge (+6.83 mm in its footprint) on the right edge.
    "J1": (X0 + 3.65, 122.0, 270),
    "J2": (X1 - 6.83, 128.0 - 4.315, 90),
    "U1": (111.5, 122.0, 90),
    "R1": (109.5, 114.5, 0),
    "R2": (109.5, 129.5, 0),
    "U2": (110.5, 145.0, 0),
    "C1": (104.5, 141.0, 90),
    "C2": (117.5, 145.0, 90),
    "D1": (104.0, 151.0, 0),
    "R4": (107.5, 151.0, 0),
    "U4": (125.0, 120.0, 0),
    "Y1": (114.5, 111.0, 0),
    "C7": (111.5, 108.5, 0),
    "C8": (117.5, 108.5, 0),
    "R5": (116.0, 116.5, 0),
    "R6": (116.0, 125.5, 0),
    "U5": (122.5, 104.3, 0),
    "R7": (117.5, 104.0, 0),
    "R8": (127.5, 102.5, 0),
    "R9": (127.5, 104.5, 0),
    "R10": (127.5, 106.5, 0),
    "C20": (117.5, 106.0, 0),
    "U6": (147.0, 120.0, 0),
    # The oscillator sits in the gap between the FPGA and the DAC column, its output pad (3)
    # level with the clock pin (35), so the clock is a 2.4 mm straight trace between the VGA lines.
    "X1": (154.3, 116.925, 180),
    "C29": (155.6, 120.3, 0),
    "U7": (147.0, 136.0, 0),
    "R14": (141.0, 141.0, 90),
    "R15": (153.0, 141.0, 90),
    "C28": (153.0, 136.0, 90),
    "R11": (138.0, 129.0, 90),
    "R12": (136.0, 129.0, 90),
    "R13": (140.0, 133.0, 90),
    "SW1": (127.0, 150.0, 0),
    "U3": (134.0, 140.0, 0),
    "C3": (134.0, 136.5, 0),
    "C4": (134.0, 144.0, 0),
    "R3": (140.5, 124.5, 0),
    "C5": (139.5, 113.5, 90),
    "C6": (141.5, 115.5, 0),
    "D2": (162.0, 151.0, 0),
    "R16": (158.5, 151.0, 0),
    "H1": (X0 + 3.5, Y0 + 3.5, 0),
    "H2": (X1 - 3.5, Y0 + 3.5, 0),
    "H3": (X0 + 3.5, Y1 - 3.5, 0),
    "H4": (X1 - 3.5, Y1 - 3.5, 0),
}
# DAC resistors in one column, in the same order as their FPGA pins going round the chip's
# top-right corner (VS at the top ... red bit 0 at the bottom), so the traces never cross.
DAC_ORDER = ["R30", "R29", "R25", "R26", "R27", "R28", "R21", "R22", "R23", "R24", "R17", "R18", "R19", "R20"]
for i, ref in enumerate(DAC_ORDER):
    PLACE[ref] = (159.0, 102.5 + i * 2.2, 0)

# Decoupling: each capacitor goes beside a power pin of its chip (ref, pad number).
DECOUPLE = {
    "C9": ("U4", "49"), "C10": ("U4", "12"), "C11": ("U4", "37"), "C12": ("U4", "64"),
    "C13": ("U4", "20"), "C14": ("U4", "31"), "C15": ("U4", "42"), "C16": ("U4", "56"),
    "C17": ("U4", "4"), "C18": ("U4", "9"), "C19": ("U4", "50"),
    "C21": ("U6", "5"), "C22": ("U6", "30"), "C23": ("U6", "1"), "C24": ("U6", "33"),
    "C25": ("U6", "22"), "C26": ("U6", "24"), "C27": ("U6", "33"),
}

POWER = {"VBUS": 0.5, "+3V3": 0.3, "+1V2": 0.3, "FT_1V8": 0.3, "VCCPLL": 0.3, "GND": 0.3}


def vec(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def load(fp_id):
    lib, name = fp_id.split(":")
    return pcbnew.FootprintLoad(os.path.join(sexpr.FOOTPRINTS, lib + ".pretty"), name)


def rules(board):
    board.SetCopperLayerCount(4)
    # Layers 2 and 3 are the ground and 3.3 V planes, but may carry the odd signal where the
    # FPGA's surroundings are too tight for two layers. Every plane pad has its own via into its
    # plane (fanout), so a few cuts through a plane don't strand anything.
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_MIXED)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_MIXED)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = MM(0.127)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_HoleClearance = MM(0.25)
    ds.m_HoleToHoleMin = MM(0.25)
    ds.m_TentViasFront = True
    ds.m_TentViasBack = True
    ns = ds.m_NetSettings
    d = ns.GetDefaultNetclass()
    d.SetTrackWidth(MM(0.2))
    d.SetClearance(MM(0.15))
    d.SetViaDiameter(MM(0.6))
    d.SetViaDrill(MM(0.3))
    for name, width in (("Power", 0.3), ("VBUS", 0.5)):
        nc = pcbnew.NETCLASS(name)
        nc.SetTrackWidth(MM(width))
        nc.SetClearance(MM(0.15))
        nc.SetViaDiameter(MM(0.6))
        nc.SetViaDrill(MM(0.3))
        ns.SetNetclass(name, nc)
    for net, width in POWER.items():
        ns.SetNetclassPatternAssignment(net, "VBUS" if net == "VBUS" else "Power")


def outline(board):
    r = 2.0
    pts = [(X0 + r, Y0), (X1 - r, Y0), (X1, Y0 + r), (X1, Y1 - r), (X1 - r, Y1), (X0 + r, Y1), (X0, Y1 - r), (X0, Y0 + r)]
    for i in range(0, 8, 2):
        a, b = pts[i], pts[i + 1]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(vec(*a))
        seg.SetEnd(vec(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.1))
        board.Add(seg)
    corners = [((X1 - r, Y0 + r), (X1 - r, Y0)), ((X1 - r, Y1 - r), (X1, Y1 - r)), ((X0 + r, Y1 - r), (X0 + r, Y1)), ((X0 + r, Y0 + r), (X0, Y0 + r))]
    for centre, start in corners:
        arc = pcbnew.PCB_SHAPE(board)
        arc.SetShape(pcbnew.SHAPE_T_ARC)
        arc.SetCenter(vec(*centre))
        arc.SetStart(vec(*start))
        arc.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
        arc.SetLayer(pcbnew.Edge_Cuts)
        arc.SetWidth(MM(0.1))
        board.Add(arc)


def zone(board, net, layer, inset=0.5, priority=0):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.2))
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.3))
    o = z.Outline()
    o.NewOutline()
    for x, y in ((X0 + inset, Y0 + inset), (X1 - inset, Y0 + inset), (X1 - inset, Y1 - inset), (X0 + inset, Y1 - inset)):
        o.Append(MM(x), MM(y))
    board.Add(z)
    return z


def bbox(fp):
    b = fp.GetBoundingBox(False)
    return (pcbnew.ToMM(b.GetLeft()), pcbnew.ToMM(b.GetTop()), pcbnew.ToMM(b.GetRight()), pcbnew.ToMM(b.GetBottom()))


def overlaps(a, b, gap=0.25):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def decouple(board, fp, chip, pad_no, placed):
    """Puts a capacitor just outside the chip, in line with the pad, its first pad facing the
    chip; tries further out and to either side until it fits."""
    pad = next(p for p in chip.Pads() if p.GetNumber() == pad_no)
    px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
    cx, cy = pcbnew.ToMM(chip.GetPosition().x), pcbnew.ToMM(chip.GetPosition().y)
    body = bbox(chip)
    dx, dy = px - cx, py - cy
    if abs(dx) >= abs(dy):
        out = (1 if dx > 0 else -1, 0)
        edge = body[2] if dx > 0 else body[0]
        base = (edge, py)
        rot = 0 if dx > 0 else 180
    else:
        out = (0, 1 if dy > 0 else -1)
        edge = body[3] if dy > 0 else body[1]
        base = (px, edge)
        rot = 270 if dy > 0 else 90
    for dist in (1.3, 3.0, 4.7, 6.4):
        for side in (0, 1.1, -1.1, 2.2, -2.2):
            x = base[0] + out[0] * dist + (side if out[0] == 0 else 0)
            y = base[1] + out[1] * dist + (side if out[1] == 0 else 0)
            fp.SetPosition(vec(x, y))
            fp.SetOrientationDegrees(rot)
            box = bbox(fp)
            if box[0] > X0 + 0.5 and box[2] < X1 - 0.5 and box[1] > Y0 + 0.5 and box[3] < Y1 - 0.5 \
                    and not any(overlaps(box, b) for b in placed):
                return box
    # Crowded side: the nearest free spot to where it wanted to be.
    return nearest_free(fp, base[0] + out[0] * 3.0, base[1] + out[1] * 3.0, rot, placed)


def nearest_free(fp, x, y, rot, placed):
    """The free spot nearest (x, y), searching outwards in rings."""
    import math
    fp.SetOrientationDegrees(rot)
    for r in [0] + [0.5 * k for k in range(1, 25)]:
        steps = 1 if r == 0 else max(8, int(2 * math.pi * r / 0.6))
        for k in range(steps):
            a = 2 * math.pi * k / steps
            fp.SetPosition(vec(x + r * math.cos(a), y + r * math.sin(a)))
            box = bbox(fp)
            if box[0] > X0 + 0.5 and box[2] < X1 - 0.5 and box[1] > Y0 + 0.5 and box[3] < Y1 - 0.5                     and not any(overlaps(box, b) for b in placed):
                return box
    raise SystemExit(f"no room for {fp.GetReference()} near {x}, {y}")


def stitch(board, pitch=2.5):
    """Ground vias on a grid wherever they fit, tying the outer ground pours to the ground plane so
    no piece of pour floats. Done once, after routing; skipped if the board already has them."""
    gnd = board.FindNet("GND")
    if not any(t.GetClass() == "PCB_TRACK" and not t.IsLocked() for t in board.GetTracks()):
        return  # not routed yet: only the locked pre-route is there
    keep = 0.6  # copper-to-copper distance from the via's edge
    r = 0.3
    tracks = [t for t in board.GetTracks()]
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    courtyards = [bbox(fp) for fp in board.GetFootprints()]

    def seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5

    mm = pcbnew.ToMM
    added = 0
    y = Y0 + 2.5
    while y < Y1 - 2.0:
        x = X0 + 2.5
        while x < X1 - 2.0:
            ok = not any(b[0] - 0.2 < x < b[2] + 0.2 and b[1] - 0.2 < y < b[3] + 0.2 for b in courtyards)
            # Already stitched here on an earlier run: leave it.
            ok = ok and not any(t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd.GetNetCode()
                                and abs(mm(t.GetPosition().x) - x) < 0.01 and abs(mm(t.GetPosition().y) - y) < 0.01 for t in tracks)
            for t in tracks if ok else []:
                if t.GetClass() == "PCB_VIA":
                    d = ((mm(t.GetPosition().x) - x) ** 2 + (mm(t.GetPosition().y) - y) ** 2) ** 0.5 - mm(t.GetWidth(pcbnew.F_Cu)) / 2
                else:
                    d = seg_dist(x, y, mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)) - mm(t.GetWidth()) / 2
                if d < r + keep:
                    ok = False
                    break
            for p in pads if ok else []:
                bb = p.GetBoundingBox()
                if mm(bb.GetLeft()) - r - keep < x < mm(bb.GetRight()) + r + keep and mm(bb.GetTop()) - r - keep < y < mm(bb.GetBottom()) + r + keep:
                    ok = False
                    break
            if ok:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(vec(x, y))
                v.SetWidth(MM(0.6))
                v.SetDrill(MM(0.3))
                v.SetNet(gnd)
                v.SetLocked(True)
                board.Add(v)
                added += 1
            x += pitch
        y += pitch
    print(f"stitching: {added} ground vias")


def pad_vias(board):
    """A 3 x 3 grid of ground vias inside each large ground pad (the FPGA's exposed pad), where
    none are yet and nothing of another net is in the way on any layer."""
    import math
    mm = pcbnew.ToMM
    gnd = board.FindNet("GND")
    others = [t for t in board.GetTracks() if t.GetNetCode() != gnd.GetNetCode()]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            w, h = mm(bb.GetWidth()), mm(bb.GetHeight())
            if p.GetNetCode() != gnd.GetNetCode() or w < 3 or h < 3 or not p.IsOnLayer(pcbnew.F_Cu)                     or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    x, y = px + i * w / 3.5, py + j * h / 3.5
                    if any(t.GetClass() == "PCB_VIA" and math.hypot(mm(t.GetPosition().x) - x, mm(t.GetPosition().y) - y) < 0.7
                           for t in board.GetTracks()):
                        continue
                    blocked = False
                    for t in others:
                        if t.GetClass() == "PCB_VIA":
                            d = math.hypot(mm(t.GetPosition().x) - x, mm(t.GetPosition().y) - y) - mm(t.GetWidth(pcbnew.F_Cu)) / 2
                        else:
                            ax, ay, bx, by = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
                            dx, dy = bx - ax, by - ay
                            L = dx * dx + dy * dy
                            k = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L))
                            d = math.hypot(ax + k * dx - x, ay + k * dy - y) - mm(t.GetWidth()) / 2
                        if d < 0.3 + 0.25:
                            blocked = True
                            break
                    if not blocked:
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(vec(x, y))
                        v.SetWidth(MM(0.6))
                        v.SetDrill(MM(0.3))
                        v.SetNet(gnd)
                        v.SetLocked(True)
                        board.Add(v)


def finalize(board, parts):
    """Things that keep the board in step with the schematic and clean for the DRC. Safe to run
    again on a routed board (fixup.py does), since it touches no copper."""
    by_ref = {p["ref"]: p for p in parts}
    open_names = netlist.kicad_open_pin_names()
    for fp in board.GetFootprints():
        p = by_ref[fp.GetReference()]
        lib, name = p["footprint"].split(":")
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        for key in ("MPN", "LCSC"):
            if fp.HasField(key):
                fp.GetField(key).SetText(p[key.lower()])
            else:
                f = pcbnew.PCB_FIELD(fp, fp.GetNextFieldOrdinal(), key)
                f.SetText(p[key.lower()])
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
                fp.Add(f)
        if fp.HasField("Description"):
            fp.GetField("Description").SetText(p["note"])
        # Pins the schematic leaves open get the net name KiCad gives them there.
        for pad in fp.Pads():
            num = pad.GetNumber()
            name = open_names.get((p["ref"], num))
            if name and p["nets"].get(num) is None and pad.GetNetname() != name:
                net = board.FindNet(name)
                if net is None:
                    net = pcbnew.NETINFO_ITEM(board, name)
                    board.Add(net)
                pad.SetNet(net)
        # Small parts are too tightly packed for legible silkscreen: their names go on the
        # fabrication drawing instead.
        if p["ref"][0] in "RCDH" or p["ref"] in ("Y1", "U1"):
            fp.Reference().SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
    # Ground on both outer layers as well (after routing; they would wall off the autorouter).
    if any(t.GetClass() == "PCB_TRACK" and not t.IsLocked() for t in board.GetTracks()):
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not any(z.GetLayer() == layer for z in board.Zones()):
                zone(board, board.FindNet("GND"), layer)
    stitch(board)
    pad_vias(board)
    for z in board.Zones():
        # Solid connections to ground and 3.3 V, and no floating copper islands.
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)


def preroute(board):
    """The FPGA's two core supply pins (5 on the left, 30 on the right) are joined by hand under
    the chip on the bottom layer before autorouting. Left to the autorouter, pin 30 ends up boxed
    in by the VGA fan-out on the right side. Pin 30's capacitor, C22, sits on the underside right
    under the via at the end of its stub, which keeps the top-side channels beside pins 29 and 31
    clear for the VGA lines. Positions follow the QFN footprint at PLACE["U6"]."""
    net = board.FindNet("+1V2")
    ux, uy, _ = PLACE["U6"]
    p5 = (ux - 3.438, uy - 0.75)    # pin 5
    p30 = (ux + 3.438, uy + 0.25)   # pin 30
    v_left = (ux - 4.8, p5[1])      # on the way to C21, outside the pads
    v_right = (ux + 6.0, p30[1])    # end of pin 30's stub; C22 is under it, on the bottom
    def track(a, b, layer, width=0.3):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(vec(*a))
        t.SetEnd(vec(*b))
        t.SetLayer(layer)
        t.SetWidth(MM(width))
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)

    def via(at):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(vec(*at))
        v.SetWidth(MM(0.6))
        v.SetDrill(MM(0.3))
        v.SetNet(net)
        v.SetLocked(True)
        board.Add(v)

    track(p5, v_left, pcbnew.F_Cu, 0.25)
    track(p30, v_right, pcbnew.F_Cu, 0.25)
    via(v_left)
    via(v_right)

    # C22 to the underside, its +1V2 pad on the via and its ground pad pointing away from the chip.
    c22 = board.FindFootprintByReference("C22")
    if not c22.IsFlipped():
        c22.Flip(c22.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    c22.SetOrientationDegrees(0)
    pads = {p.GetNumber(): p for p in c22.Pads()}
    if pads["2"].GetPosition().x < pads["1"].GetPosition().x:
        c22.SetOrientationDegrees(180)
    off = c22.GetPosition() - pads["1"].GetPosition()
    c22.SetPosition(vec(*v_right) + off)
    # Under the chip the link runs between the rows of the exposed pad's ground vias (fanout()).
    lane = uy + 0.8
    track(v_left, (v_left[0], lane), pcbnew.B_Cu, 0.3)
    track((v_left[0], lane), (v_right[0] - 0.45, lane), pcbnew.B_Cu, 0.3)
    track((v_right[0] - 0.45, lane), v_right, pcbnew.B_Cu, 0.3)


def fanout(board):
    """Every surface-mount pad on a plane net (GND, +3V3) gets its own via to the plane, on a
    short locked stub, placed outward from its part wherever it fits. The autorouter treats plane
    nets as already joined and never drops these vias itself. The FPGA's exposed ground pad gets
    a 3 x 3 grid of vias inside it."""
    import math
    mm = pcbnew.ToMM
    r, gap = 0.3, 0.2
    planes = {"GND", "+3V3"}
    items = []  # (kind, geometry, netcode) for everything a via must keep clear of

    def note_via(x, y, net):
        items.append(("via", (x, y, r), net))

    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            note_via(mm(t.GetPosition().x), mm(t.GetPosition().y), t.GetNetCode())
        else:
            items.append(("seg", (mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y), mm(t.GetWidth()) / 2), t.GetNetCode()))
    pads = [(fp, p) for fp in board.GetFootprints() for p in fp.Pads()]
    for fp, p in pads:
        bb = p.GetBoundingBox()
        items.append(("box", (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())), p.GetNetCode()))

    def clear(x, y, net, own_pad_box):
        if not (X0 + 1 < x < X1 - 1 and Y0 + 1 < y < Y1 - 1):
            return False
        for kind, g, n in items:
            if kind == "via":
                if math.hypot(g[0] - x, g[1] - y) < g[2] + r + gap:
                    return False
            elif kind == "seg":
                ax, ay, bx, by, hw = g
                dx, dy = bx - ax, by - ay
                L = dx * dx + dy * dy
                t = 0 if L == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / L))
                if math.hypot(ax + t * dx - x, ay + t * dy - y) < hw + r + gap:
                    return False
            else:
                if g == own_pad_box or n == net:
                    continue  # a via may touch pads of its own net
                if g[0] - r - gap < x < g[2] + r + gap and g[1] - r - gap < y < g[3] + r + gap:
                    return False
        return True

    def path_clear(ax, ay, bx, by, hw, net, own_pad_box):
        """The stub from the pad to its via keeps clear of every other pad and track."""
        steps = max(2, int(math.hypot(bx - ax, by - ay) / 0.05))
        for k in range(steps + 1):
            x, y = ax + (bx - ax) * k / steps, ay + (by - ay) * k / steps
            for kind, g, n in items:
                if kind == "via" and n != net:
                    if math.hypot(g[0] - x, g[1] - y) < g[2] + hw + gap:
                        return False
                elif kind == "box" and g != own_pad_box:
                    if g[0] - hw - gap < x < g[2] + hw + gap and g[1] - hw - gap < y < g[3] + hw + gap:
                        return False
                elif kind == "seg" and n != net:
                    sx, sy, ex, ey, shw = g
                    dx, dy = ex - sx, ey - sy
                    L = dx * dx + dy * dy
                    t = 0 if L == 0 else max(0, min(1, ((x - sx) * dx + (y - sy) * dy) / L))
                    if math.hypot(sx + t * dx - x, sy + t * dy - y) < shw + hw + gap:
                        return False
        return True

    def add(x, y, net, stub_from=None, stub_w=0.3, stub_layer=pcbnew.F_Cu):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(vec(x, y))
        v.SetWidth(MM(0.6))
        v.SetDrill(MM(0.3))
        v.SetNet(net)
        v.SetLocked(True)
        board.Add(v)
        note_via(x, y, net.GetNetCode())
        if stub_from:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(vec(*stub_from))
            t.SetEnd(vec(x, y))
            t.SetLayer(stub_layer)
            t.SetWidth(MM(stub_w))
            t.SetNet(net)
            t.SetLocked(True)
            board.Add(t)
            items.append(("seg", (stub_from[0], stub_from[1], x, y, stub_w / 2), net.GetNetCode()))

    placed = skipped = 0
    for fp, p in pads:
        net = p.GetNet()
        if net.GetNetname() not in planes or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
        bb = p.GetBoundingBox()
        box = (mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        w, h = box[2] - box[0], box[3] - box[1]
        if w > 3 and h > 3:
            # Exposed thermal pad: vias inside it.
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    x, y = px + i * w / 3.5, py + j * h / 3.5
                    if clear(x, y, net.GetNetCode(), box):
                        add(x, y, net)
                        placed += 1
            continue
        cx, cy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        ox, oy = px - cx, py - cy
        if abs(ox) < 1e-6 and abs(oy) < 1e-6:
            ox, oy = 1.0, 0.0
        n = math.hypot(ox, oy)
        ox, oy = ox / n, oy / n
        # Outward first, then fanning round to either side.
        # Fine-pitch chip pins only fan straight out, on a thin stub; anything else may angle.
        fine = min(w, h) < 0.45
        stub_w = 0.2 if fine else 0.3
        angles = (0,) if fine else (0, 35, -35, 70, -70, 110, -110, 180)
        if fine:
            # Pins fan out at right angles to their chip's edge.
            ox, oy = (math.copysign(1, ox), 0.0) if abs(ox) > abs(oy) else (0.0, math.copysign(1, oy))
        done = False
        for dist in (0.9, 1.3, 1.8, 2.4, 3.0):
            for ang in angles:
                a = math.radians(ang)
                dx, dy = ox * math.cos(a) - oy * math.sin(a), ox * math.sin(a) + oy * math.cos(a)
                reach = dist + max(w, h) / 2
                x, y = round(px + dx * reach, 3), round(py + dy * reach, 3)
                if clear(x, y, net.GetNetCode(), box) and path_clear(px, py, x, y, stub_w / 2, net.GetNetCode(), box):
                    add(x, y, net, (px, py), stub_w, pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
                    placed += 1
                    done = True
                    break
            if done:
                break
        if not done:
            skipped += 1
    print(f"plane fan-out: {placed} vias, {skipped} pads left to the router")


def build():
    parts = netlist.resolve()
    board = pcbnew.CreateEmptyBoard()
    rules(board)
    outline(board)

    nets = {}
    for p in parts:
        for net in p["nets"].values():
            if net and net not in nets:
                ni = pcbnew.NETINFO_ITEM(board, net)
                board.Add(ni)
                nets[net] = ni

    fps = {}
    for p in parts:
        if not p["footprint"]:
            continue
        fp = load(p["footprint"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + netlist.uid("sym", p["ref"], 1)))
        fp.SetSheetfile("tiny_gpu.kicad_sch")
        fp.SetSheetname("/")
        for pad in fp.Pads():
            net = p["nets"].get(pad.GetNumber())
            if net:
                pad.SetNet(nets[net])
        fp.Reference().SetTextSize(vec(0.8, 0.8))
        fp.Reference().SetTextThickness(MM(0.12))
        board.Add(fp)
        fps[p["ref"]] = fp

    # Big parts exactly where planned, then the decoupling capacitors against their pins, then
    # every small part at the free spot nearest its planned position.
    placed = []
    small = lambda r: r[0] in "RCD" and not r.startswith("DE")
    for ref, (x, y, rot) in PLACE.items():
        if small(ref):
            continue
        fp = fps[ref]
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
        placed.append(bbox(fp))
    for ref, (chip, pad_no) in DECOUPLE.items():
        placed.append(decouple(board, fps[ref], fps[chip], pad_no, placed))
    for ref, (x, y, rot) in PLACE.items():
        if small(ref):
            placed.append(nearest_free(fps[ref], x, y, rot, placed))

    missing = [r for r in fps if r not in PLACE and r not in DECOUPLE]
    if missing:
        raise SystemExit(f"not placed: {missing}")
    clashes = [(a, b) for i, a in enumerate(fps) for b in list(fps)[i + 1:] if overlaps(bbox(fps[a]), bbox(fps[b]), gap=0)]
    if clashes:
        print("footprints overlapping:", clashes)

    # Planes: ground on layer 2, 3.3 V on layer 3. Ground also poured on both outer layers
    # after routing (route.py), so every spare bit of copper is shield.
    preroute(board)
    fanout(board)
    zone(board, nets["GND"], pcbnew.In1_Cu)
    zone(board, nets["+3V3"], pcbnew.In2_Cu)

    finalize(board, parts)
    title = board.GetTitleBlock()
    title.SetTitle("Tiny GPU board")
    title.SetRevision("1")
    title.SetComment(0, "iCE40UP5K GPU, FT2232H USB link, VGA out")
    board.SetFileName(OUT)
    pcbnew.SaveBoard(OUT, board)
    return board, clashes


if __name__ == "__main__":
    board, clashes = build()
    print(f"wrote {OUT}: {len(list(board.GetFootprints()))} footprints, {board.GetNetCount()} nets, {len(clashes)} overlaps")
