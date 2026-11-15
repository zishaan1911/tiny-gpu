"""Routes the last few connections Freerouting leaves open, with a small grid maze router.

Reads the unconnected pairs from pcb/drc.rpt (run outputs.py first), rasterises the board on a
0.05 mm grid for the top and bottom layers, marks every other net's copper plus clearance as a
wall, and finds each path with A*, dropping a via where it changes layer. The new copper is
ordinary tracks and vias, so the next DRC checks it like anything else.
Run with KiCad's Python:  C:/Users/Zishaan/Tools/kicad/bin/python.exe finish_routes.py
"""

import heapq
import math
import os
import re
import sys

import numpy as np
import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import board as B  # noqa: E402

RES = 0.05            # grid, mm
CLR = 0.22            # clearance kept to other nets (the strictest rule here is 0.2)
TRACK = 0.2           # new track width
VIA_D, VIA_DRILL = 0.6, 0.3
VIA_COST = 40         # in grid steps: a via costs about as much as 2 mm of track
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
NX = int(round(B.W / RES)) + 1
NY = int(round(B.H / RES)) + 1
mm = pcbnew.ToMM


def cell(x, y):
    return int(round((y - B.Y0) / RES)), int(round((x - B.X0) / RES))


def point(iy, ix):
    return B.X0 + ix * RES, B.Y0 + iy * RES


GX, GY = np.meshgrid(np.arange(NX) * RES + B.X0, np.arange(NY) * RES + B.Y0)


def block_rect(grid, x0, y0, x1, y1, infl):
    a = cell(x0 - infl, y0 - infl)
    b = cell(x1 + infl, y1 + infl)
    grid[max(a[0], 0):min(b[0] + 1, NY), max(a[1], 0):min(b[1] + 1, NX)] = True


def block_seg(grid, ax, ay, bx, by, radius):
    a = cell(min(ax, bx) - radius, min(ay, by) - radius)
    b = cell(max(ax, bx) + radius, max(ay, by) + radius)
    sy, sx = slice(max(a[0], 0), min(b[0] + 1, NY)), slice(max(a[1], 0), min(b[1] + 1, NX))
    px, py = GX[sy, sx], GY[sy, sx]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = np.zeros_like(px) if L == 0 else np.clip(((px - ax) * dx + (py - ay) * dy) / L, 0, 1)
    grid[sy, sx] |= np.hypot(ax + t * dx - px, ay + t * dy - py) <= radius


def obstacles(board, net):
    """Two maps per layer: where a track centre may go, and where a via centre may go."""
    track = [np.zeros((NY, NX), bool) for _ in LAYERS]
    via = [np.zeros((NY, NX), bool) for _ in LAYERS]
    for grid_set, hw in ((track, TRACK / 2), (via, VIA_D / 2)):
        edge = 0.5 + hw
        for g in grid_set:
            g[:int(edge / RES), :] = g[-int(edge / RES):, :] = True
            g[:, :int(edge / RES)] = g[:, -int(edge / RES):] = True
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() == net and p.GetNetCode() > 0:
                    continue
                bb = p.GetBoundingBox()
                for li, layer in enumerate(LAYERS):
                    if p.IsOnLayer(layer) or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                        block_rect(grid_set[li], mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()), CLR + hw)
        for t in board.GetTracks():
            if t.GetNetCode() == net:
                continue
            if t.GetClass() == "PCB_VIA":
                x, y, r = mm(t.GetPosition().x), mm(t.GetPosition().y), mm(t.GetWidth(pcbnew.F_Cu)) / 2
                for g in grid_set:
                    block_seg(g, x, y, x, y, r + CLR + hw)
            else:
                li = LAYERS.index(t.GetLayer()) if t.GetLayer() in LAYERS else None
                if li is not None:
                    block_seg(grid_set[li], mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y),
                              mm(t.GetWidth()) / 2 + CLR + hw)
    return track, via


def astar(track, via, starts, goals):
    goal_set = set(goals)
    gy = sum(g[1] for g in goals) / len(goals)
    gx = sum(g[2] for g in goals) / len(goals)
    h = lambda s: math.hypot(s[1] - gy, s[2] - gx)
    openq = []
    best = {}
    came = {}
    for s in starts:
        best[s] = 0
        heapq.heappush(openq, (h(s), 0, s))
    steps = [(dy, dx, math.hypot(dy, dx)) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    while openq:
        f, g, s = heapq.heappop(openq)
        if s in goal_set:
            path = [s]
            while s in came:
                s = came[s]
                path.append(s)
            return path[::-1]
        if g > best.get(s, 1e18):
            continue
        layer, y, x = s
        nbrs = []
        for dy, dx, c in steps:
            ny, nx = y + dy, x + dx
            if 0 <= ny < NY and 0 <= nx < NX and (not track[layer][ny, nx] or (layer, ny, nx) in goal_set):
                nbrs.append(((layer, ny, nx), c))
        other = 1 - layer
        if not via[0][y, x] and not via[1][y, x]:
            nbrs.append(((other, y, x), VIA_COST))
        for n, c in nbrs:
            ng = g + c
            if ng < best.get(n, 1e18):
                best[n] = ng
                came[n] = s
                heapq.heappush(openq, (ng + h(n), ng, n))
    return None


def item_cells(board, desc, x, y, net):
    """Cells to start or end on for a DRC item: a pad's area, a via, or a track's whole length."""
    if desc.startswith("Pad") or desc.startswith("PTH pad"):
        m = re.match(r"(?:PTH )?[Pp]ad (\S+) \[[^\]]*\] of (\S+)", desc)
        fp = board.FindFootprintByReference(m.group(2))
        p = next(p for p in fp.Pads() if p.GetNumber() == m.group(1))
        bb = p.GetBoundingBox()
        cells = []
        for li, layer in enumerate(LAYERS):
            if p.IsOnLayer(layer):
                a = cell(mm(bb.GetLeft()) + 0.1, mm(bb.GetTop()) + 0.1)
                b = cell(mm(bb.GetRight()) - 0.1, mm(bb.GetBottom()) - 0.1)
                cells += [(li, iy, ix) for iy in range(a[0], b[0] + 1) for ix in range(a[1], b[1] + 1)]
        return cells
    best, item = 1e9, None
    for t in board.GetTracks():
        if t.GetNetCode() != net:
            continue
        d = t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetStart()
        dist = math.hypot(mm(d.x) - x, mm(d.y) - y)
        if dist < best:
            best, item = dist, t
    if item.GetClass() == "PCB_VIA":
        c = cell(mm(item.GetPosition().x), mm(item.GetPosition().y))
        return [(0, *c), (1, *c)]
    li = LAYERS.index(item.GetLayer())
    ax, ay, bx, by = mm(item.GetStart().x), mm(item.GetStart().y), mm(item.GetEnd().x), mm(item.GetEnd().y)
    n = max(1, int(math.hypot(bx - ax, by - ay) / RES))
    return list({(li, *cell(ax + (bx - ax) * k / n, ay + (by - ay) * k / n)) for k in range(n + 1)})


def rip_near(board, net, cells, radius=1.0):
    """Removes other nets' unlocked tracks and vias within `radius` mm of the given cells."""
    pts = np.array([point(c[1], c[2]) for c in cells])
    ripped = set()
    for t in list(board.GetTracks()):
        if t.GetNetCode() == net or t.IsLocked():
            continue
        if t.GetClass() == "PCB_VIA":
            ends = [(mm(t.GetPosition().x), mm(t.GetPosition().y))]
        else:
            ax, ay, bx, by = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
            n = max(1, int(math.hypot(bx - ax, by - ay) / 0.1))
            ends = [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n + 1)]
        e = np.array(ends)
        d = np.min(np.hypot(e[:, None, 0] - pts[None, :, 0], e[:, None, 1] - pts[None, :, 1]))
        if d < radius:
            ripped.add(t.GetNetname())
            board.Remove(t)
    return ripped


def unconnected_pairs(report):
    pairs = []
    lines = open(report, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("[unconnected_items]"):
            items = []
            for l in lines[i + 1:i + 5]:
                m = re.match(r"\s+@\(([-\d.]+) mm, ([-\d.]+) mm\): (.*)", l)
                if m:
                    items.append((float(m.group(1)), float(m.group(2)), m.group(3)))
            if len(items) == 2 and not any(d.startswith("Zone") for _, _, d in items):
                pairs.append(items)
    return pairs


def lay(board, path, net):
    """Track segments along the path (straight runs merged) and a via at each layer change."""
    added = 0

    def seg(a, b):
        nonlocal added
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(B.vec(*point(a[1], a[2])))
        t.SetEnd(B.vec(*point(b[1], b[2])))
        t.SetLayer(LAYERS[a[0]])
        t.SetWidth(B.MM(TRACK))
        t.SetNet(net)
        board.Add(t)
        added += 1

    run_start = path[0]
    for i in range(1, len(path)):
        prev, cur = path[i - 1], path[i]
        if cur[0] != prev[0]:
            if prev != run_start:
                seg(run_start, prev)
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(B.vec(*point(cur[1], cur[2])))
            v.SetWidth(B.MM(VIA_D))
            v.SetDrill(B.MM(VIA_DRILL))
            v.SetNet(net)
            board.Add(v)
            run_start = cur
            continue
        nxt = path[i + 1] if i + 1 < len(path) else None
        straight = nxt and nxt[0] == cur[0] and (nxt[1] - cur[1], nxt[2] - cur[2]) == (cur[1] - prev[1], cur[2] - prev[2])
        if not straight:
            seg(run_start, cur)
            run_start = cur
    return added


def main():
    board = pcbnew.LoadBoard(B.OUT)
    report = os.path.join(os.path.dirname(B.OUT), "drc.rpt")
    done = failed = 0
    for (x1, y1, d1), (x2, y2, d2) in unconnected_pairs(report):
        name = re.search(r"\[([^\]]+)\]", d1).group(1)
        net = board.FindNet(name)
        track, via = obstacles(board, net.GetNetCode())
        starts = item_cells(board, d1, x1, y1, net.GetNetCode())
        goals = item_cells(board, d2, x2, y2, net.GetNetCode())
        path = astar(track, via, starts, goals)
        if not path:
            # Boxed in: rip up other nets' tracks hugging either end, route this one first;
            # the ripped-up nets are routed again on the next pass.
            ripped = rip_near(board, net.GetNetCode(), starts + goals)
            if ripped:
                # KiCad's Python handles go stale after removing items: save, and let the next
                # pass (a fresh process, after a fresh DRC) route this net and the ripped ones.
                pcbnew.SaveBoard(B.OUT, board)
                print(f"  {name}: ripped up {sorted(ripped)} around it; run again")
                return
        if not path:
            print(f"  {name}: no path")
            failed += 1
            continue
        n = lay(board, path, net)
        length = sum(math.hypot(path[i][1] - path[i - 1][1], path[i][2] - path[i - 1][2]) for i in range(1, len(path))) * RES
        vias = sum(path[i][0] != path[i - 1][0] for i in range(1, len(path)))
        print(f"  {name}: {length:.1f} mm, {vias} vias, {n} segments")
        done += 1
    pcbnew.SaveBoard(B.OUT, board)
    print(f"routed {done} connections, {failed} without a path")


if __name__ == "__main__":
    main()
