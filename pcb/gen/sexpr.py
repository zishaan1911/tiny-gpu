"""A small reader and writer for KiCad's s-expression files, and the library lookups the
board generator needs: symbols (flattened, with their pins) and footprints (with their pads)."""

import math
import os
import re

KICAD = os.environ.get("KICAD_DIR", r"C:\Users\Zishaan\Tools\kicad")
SYMBOLS = os.path.join(KICAD, "share", "kicad", "symbols")
FOOTPRINTS = os.path.join(KICAD, "share", "kicad", "footprints")


class Sym(str):
    """A bare symbol (not a quoted string) in an s-expression."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"cannot parse at {pos}: {text[pos:pos + 40]!r}")
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            done = stack.pop()
            stack[-1].append(done)
        elif m.group(3) is not None:
            stack[-1].append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(Sym(m.group(4)))
    return stack[0]


def dump(node, indent=0):
    """Writes a node back out, one list per line where that helps readability."""
    if isinstance(node, list):
        if not node:
            return "()"
        simple = all(not isinstance(c, list) for c in node)
        if simple:
            return "(" + " ".join(dump(c) for c in node) + ")"
        pad = "  " * (indent + 1)
        head = []
        rest = []
        for c in node:
            (rest if (isinstance(c, list) or rest) else head).append(c)
        out = "(" + " ".join(dump(c) for c in head)
        for c in rest:
            out += "\n" + pad + dump(c, indent + 1)
        return out + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, bool):
        return "yes" if node else "no"
    if isinstance(node, (int,)):
        return str(node)
    if isinstance(node, float):
        s = f"{node:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return '"' + str(node).replace("\\", "\\\\").replace('"', '\\"') + '"'


def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


# Symbols -----------------------------------------------------------------------------------

_lib_cache = {}


def _library(name):
    if name not in _lib_cache:
        with open(os.path.join(SYMBOLS, name + ".kicad_sym"), encoding="utf-8") as f:
            root = parse(f.read())[0]
        _lib_cache[name] = {s[1]: s for s in find_all(root, "symbol")}
    return _lib_cache[name]


def symbol(lib_id):
    """The symbol, flattened (an `extends` symbol gets its parent's drawing and pins), renamed to
    its full lib_id the way a schematic's lib_symbols section holds it."""
    lib, name = lib_id.split(":")
    syms = _library(lib)
    s = syms[name]
    ext = find(s, "extends")
    if ext:
        parent = symbol(f"{lib}:{ext[1]}")
        # Child properties override the parent's; units come from the parent.
        props = {p[1]: p for p in find_all(s, "property")}
        merged = [Sym("symbol"), lib_id]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in props:
                merged.append(props.pop(c[1]))
            elif isinstance(c, list) and c[0] == "symbol":
                merged.append([Sym("symbol"), c[1].replace(parent[1].split(":")[-1], name, 1)] + c[2:])
            else:
                merged.append(c)
        merged.extend(props.values())
        return merged
    out = [Sym("symbol"), lib_id]
    for c in s[2:]:
        out.append(c)
    return out


def pins(sym):
    """Every pin: number, name, electrical type, unit, and its connection point (x, y) in mm, y up."""
    result = []
    for unit in find_all(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", unit[1])
        unit_no = int(m.group(1)) if m else 1
        for p in find_all(unit, "pin"):
            at = find(p, "at")
            result.append({
                "number": find(p, "number")[1],
                "name": find(p, "name")[1],
                "type": str(p[1]),
                "unit": unit_no,
                "x": float(at[1]), "y": float(at[2]), "angle": float(at[3]) if len(at) > 3 else 0.0,
                "hidden": any(isinstance(c, Sym) and c == "hide" for c in p) or bool(find(p, "hide")),
            })
    return result


def prop(sym, key):
    p = next((c for c in find_all(sym, "property") if c[1] == key), None)
    return p[2] if p else None


# Footprints --------------------------------------------------------------------------------

def footprint_path(fp_id):
    lib, name = fp_id.split(":")
    return os.path.join(FOOTPRINTS, lib + ".pretty", name + ".kicad_mod")


def pads(fp_id):
    with open(footprint_path(fp_id), encoding="utf-8") as f:
        root = parse(f.read())[0]
    out = []
    for p in find_all(root, "pad"):
        at = find(p, "at")
        size = find(p, "size")
        out.append({"number": p[1], "kind": str(p[2]), "x": float(at[1]), "y": float(at[2]),
                    "w": float(size[1]), "h": float(size[2])})
    return out


def rotate(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
