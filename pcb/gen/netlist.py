"""Resolves design.py into concrete pins: every pin of every part gets a net, or None (left open).
Refuses typos: a pin name that matches nothing, a net with only one connection, a passive with
a pin left open."""

import collections
import uuid

import design
import sexpr

PROJECT = "tiny_gpu"
NS = uuid.UUID("6f1d4c3e-6a2b-4b8e-9a8f-1e2d3c4b5a69")


def uid(*parts):
    """Stable UUIDs, so regenerating doesn't churn every file."""
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


ROOT = uid("root")


def resolve():
    out = []
    problems = []
    for p in design.parts:
        sym = sexpr.symbol(p["lib_id"])
        pins = sexpr.pins(sym)
        nets = {}
        for key, net in p["pins"].items():
            if key.startswith("#"):
                hits = [q for q in pins if q["number"] == key[1:]]
            else:
                hits = [q for q in pins if q["number"] == key] or [q for q in pins if q["name"] == key]
            if not hits:
                problems.append(f"{p['ref']}: no pin {key!r}")
            for q in hits:
                if q["number"] in nets and nets[q["number"]] != net:
                    problems.append(f"{p['ref']} pin {q['number']}: both {nets[q['number']]} and {net}")
                nets[q["number"]] = net
        for q in pins:
            nets.setdefault(q["number"], None)
        if p["lib_id"].startswith("Device:") and any(v is None for v in nets.values()):
            problems.append(f"{p['ref']}: a pin of a passive part is open")
        out.append({**p, "symbol": sym, "pin_list": pins, "nets": nets, "uuid": uid("sym", p["ref"])})

    count = collections.Counter(net for p in out for net in p["nets"].values() if net)
    for net, n in count.items():
        if n < 2:
            problems.append(f"net {net} has only one connection")
    if problems:
        raise SystemExit("design problems:\n  " + "\n  ".join(problems))
    return out


def kicad_open_pin_names():
    """The net names KiCad gives each open pin in the schematic, e.g. 'unconnected-(U4-ADBUS3-Pad19)',
    taken from its own netlist export so the board matches them exactly."""
    import os
    import subprocess
    import tempfile

    import sexpr as sx

    here = os.path.dirname(os.path.abspath(__file__))
    sch = os.path.normpath(os.path.join(here, "..", "tiny_gpu.kicad_sch"))
    out = os.path.join(tempfile.mkdtemp(), "net.net")
    subprocess.run([r"C:\Users\Zishaan\Tools\kicad\bin\kicad-cli.exe", "sch", "export", "netlist",
                    "--format", "kicadsexpr", "-o", out, sch], check=True, capture_output=True)
    with open(out, encoding="utf-8") as f:
        root = sx.parse(f.read())[0]
    names = {}
    for net in sx.find_all(sx.find(root, "nets"), "net"):
        name = sx.find(net, "name")[1]
        if name.startswith("unconnected-"):
            for node in sx.find_all(net, "node"):
                names[(sx.find(node, "ref")[1], sx.find(node, "pin")[1])] = name
    return names


if __name__ == "__main__":
    parts = resolve()
    nets = collections.defaultdict(list)
    for p in parts:
        for num, net in p["nets"].items():
            if net:
                nets[net].append(f"{p['ref']}.{num}")
    for net in sorted(nets):
        print(f"{net:16s} {len(nets[net]):3d}  {' '.join(sorted(nets[net])[:12])}{' …' if len(nets[net]) > 12 else ''}")
    print(f"{len(parts)} parts, {len(nets)} nets")
