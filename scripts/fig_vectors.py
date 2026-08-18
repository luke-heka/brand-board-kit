#!/usr/bin/env python3
"""
fig_vectors.py - export the VECTOR artwork out of a decoded Figma .fig into SVG.

Why this exists: fig_decode.py's document.json keeps only presentation metadata
(name/type/size/paints).  The actual outlines never make it into that file, so
the logos and icons are invisible to anything downstream.  This walks the same
binary and writes real SVG.

------------------------------------------------------------------ the geometry

Every drawable NodeChange carries `fillGeometry` / `strokeGeometry`, each an
array of `Path { windingRule, commandsBlob, styleID }`.  `commandsBlob` is NOT
path text - it is a uint index into the root Message's `blobs` array.  The blob
is a flat little-endian binary command stream, no header, no count:

    byte opcode, then opcode-many float32 args
        0 = CLOSE     0 floats
        1 = MOVE_TO   2 floats   x y
        2 = LINE_TO   2 floats   x y
        4 = CUBIC_TO  6 floats   c1x c1y c2x c2y x y

(3 exists in the schema's vector-network blobs as a 4-float quadratic but is
never used by a commandsBlob in this file.)  Verified: all 3,708 referenced
blobs parse to exactly their byte length under this grammar, and 47,888 MOVEs /
193,615 LINEs / 98,250 CUBICs / 47,618 CLOSEs come out.

Coordinates are already in the node's own local pixel space, 0..width by
0..height - not normalised, despite `vectorData.normalizedSize` sitting next to
them.  A 325x225 frame yields a rect spanning exactly 0..325 by 0..225.

`strokeGeometry` is the stroke *already outlined into a closed ring* (a 1px
INSIDE stroke on a 325x225 frame comes back as a 56-command two-ring shape
spanning -1..326).  It is therefore filled with the stroke paint, never stroked
- stroking it would draw the outline twice as thick and smeared.  strokeWeight
is recorded in the SVG as a data attribute for reference only.

Usage:  python3 fig_vectors.py [path/to/figma/dir]
Writes vectors/<section-slug>/<layer-name>.svg and vectors/INDEX.md.
"""

import os
import re
import struct
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fig_decode as fd  # noqa: E402

# Sections worth exporting; these carry vector artwork and no image fills.
SECTIONS = [
    "Logo Assets",
    "Graphic Elements",
    "UI Branding Assets",
    "Linkedin Banner",
    "Project Proposal",
    "Ai Reality Check Ebook",
    "State of Ai in Australia Ebook",
]

# A container is only broken open into separate SVGs if it is at least this big
# in both directions.  Without it a 48x48 icon made of 6 paths would be split
# into 6 useless fragments, and a 153x45 button would lose its own background.
SPLIT_MIN_SIDE = 160


# --------------------------------------------------------------------------
# path commands
# --------------------------------------------------------------------------

_ARGC = {0: 0, 1: 2, 2: 2, 3: 4, 4: 6}


def parse_commands(blob):
    """Binary command stream -> list of (opcode, floats)."""
    out, i, n = [], 0, len(blob)
    while i < n:
        op = blob[i]
        i += 1
        argc = _ARGC.get(op)
        if argc is None:
            raise ValueError(f"unknown path opcode {op} at byte {i - 1}/{n}")
        args = struct.unpack_from("<%df" % argc, blob, i) if argc else ()
        i += 4 * argc
        out.append((op, args))
    return out


def _num(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def commands_to_d(cmds):
    """-> SVG path data, and the (x0,y0,x1,y1) bbox of its on-curve points."""
    parts = []
    xs, ys = [], []
    for op, a in cmds:
        if op == 0:
            parts.append("Z")
        elif op == 1:
            parts.append(f"M{_num(a[0])} {_num(a[1])}")
            xs.append(a[0]); ys.append(a[1])
        elif op == 2:
            parts.append(f"L{_num(a[0])} {_num(a[1])}")
            xs.append(a[0]); ys.append(a[1])
        elif op == 3:
            parts.append(f"Q{_num(a[0])} {_num(a[1])} {_num(a[2])} {_num(a[3])}")
            xs.append(a[2]); ys.append(a[3])
        elif op == 4:
            parts.append("C" + " ".join(_num(v) for v in a))
            xs += [a[0], a[2], a[4]]
            ys += [a[1], a[3], a[5]]
    box = (min(xs), min(ys), max(xs), max(ys)) if xs else None
    return "".join(parts), box


# --------------------------------------------------------------------------
# paint
# --------------------------------------------------------------------------

def _chan(v):
    return max(0, min(255, round((v or 0) * 255)))


def paint_hex(color):
    if not isinstance(color, dict):
        return None
    return "#{:02X}{:02X}{:02X}".format(
        _chan(color.get("r")), _chan(color.get("g")), _chan(color.get("b")))


def visible_paints(paints):
    return [p for p in (paints or [])
            if isinstance(p, dict) and p.get("visible") is not False
            and p.get("type") != "IMAGE"]


def invert_2x3(t):
    a, b, c = t.get("m00", 1), t.get("m01", 0), t.get("m02", 0)
    d, e, f = t.get("m10", 0), t.get("m11", 1), t.get("m12", 0)
    det = a * e - b * d
    if abs(det) < 1e-12:
        return None
    return (e / det, -b / det, (b * f - c * e) / det,
            -d / det, a / det, (c * d - a * f) / det)


class Defs:
    """Collects <linearGradient> definitions for one SVG file."""

    def __init__(self):
        self.items = []

    def gradient(self, paint, w, h):
        """Figma stores a matrix taking the node's 0..1 box into gradient space.
        Inverting it and mapping (0,0) and (1,0) back gives the SVG handles."""
        inv = invert_2x3(paint.get("transform") or {})
        if inv is None:
            return None
        a, b, c, d, e, f = inv
        x1, y1 = c * w, f * h
        x2, y2 = (a + c) * w, (d + f) * h
        gid = f"g{len(self.items)}"
        stops = []
        for s in (paint.get("stops") or []):
            col = s.get("color") or {}
            alpha = col.get("a", 1)
            stops.append(
                f'<stop offset="{_num(s.get("position", 0))}" '
                f'stop-color="{paint_hex(col)}"'
                + (f' stop-opacity="{_num(alpha)}"' if alpha not in (1, 1.0) else "")
                + "/>")
        if not stops:
            return None
        self.items.append(
            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
            f'x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(x2)}" y2="{_num(y2)}">'
            + "".join(stops) + "</linearGradient>")
        return f"url(#{gid})"

    def render(self):
        return "<defs>" + "".join(self.items) + "</defs>" if self.items else ""


def fill_attrs(paint, defs, w, h):
    """-> dict of SVG attributes for one paint, or None if it paints nothing."""
    ptype = paint.get("type") or "SOLID"
    if ptype == "SOLID":
        value = paint_hex(paint.get("color"))
        alpha = (paint.get("color") or {}).get("a", 1)
    elif ptype.startswith("GRADIENT"):
        # radial/angular/diamond are approximated by their linear handles;
        # only GRADIENT_LINEAR actually occurs in these sections.
        value = defs.gradient(paint, w, h)
        alpha = 1
    else:
        return None
    if not value:
        return None
    opacity = paint.get("opacity", 1)
    if opacity is None:
        opacity = 1
    total = float(alpha if alpha is not None else 1) * float(opacity)
    out = {"fill": value}
    if total < 0.999:
        out["fill-opacity"] = _num(total)
    return out


# --------------------------------------------------------------------------
# tree
# --------------------------------------------------------------------------

class Doc:
    def __init__(self, fig_path):
        version, chunks = fd.read_chunks(fig_path)
        schema = fd.Schema(chunks[0])
        decoder = fd.Decoder(schema, fd.ByteBuffer(chunks[1]))
        message = decoder.compound(schema.defs[schema.by_name["Message"]])
        self.version = version
        self.blobs = [b["bytes"] if isinstance(b, dict) else b
                      for b in (message.get("blobs") or [])]
        self.nodes = {}
        for change in (message.get("nodeChanges") or []):
            key = fd.guid_key(change.get("guid"))
            if key is not None:
                self.nodes.setdefault(key, {}).update(change)
        self.children = defaultdict(list)
        for key, node in self.nodes.items():
            parent = node.get("parentIndex")
            pkey = fd.guid_key(parent.get("guid")) if isinstance(parent, dict) else None
            pos = parent.get("position") if isinstance(parent, dict) else None
            node["_pos"] = pos if isinstance(pos, str) else ""
            if pkey and pkey in self.nodes:
                self.children[pkey].append(key)
        for key in self.children:
            self.children[key].sort(key=lambda c: (self.nodes[c]["_pos"], c))

    def kids(self, key):
        return self.children.get(key, [])

    def walk(self, key):
        yield key
        for child in self.kids(key):
            yield from self.walk(child)

    def size(self, key):
        s = self.nodes[key].get("size") or {}
        return float(s.get("x") or 0), float(s.get("y") or 0)

    def geometry(self, key):
        n = self.nodes[key]
        return (n.get("fillGeometry") or []), (n.get("strokeGeometry") or [])

    def draws(self, key):
        """Does this node itself put ink on the page?"""
        n = self.nodes[key]
        if n.get("visible") is False:
            return False
        fills, strokes = self.geometry(key)
        return bool((fills and visible_paints(n.get("fillPaints")))
                    or (strokes and visible_paints(n.get("strokePaints"))))

    def subtree_draws(self, key):
        return any(self.draws(k) for k in self.walk(key))


# --------------------------------------------------------------------------
# choosing what to export
# --------------------------------------------------------------------------

def split_into(doc, key):
    """True if this node is a layout board / asset sheet rather than one asset.

    Two signals, both requiring the node to be large enough that its children
    are plausibly separate assets:
      * it holds TEXT labels next to drawn children  -> a captioned board
      * it holds six or more drawn *container* children -> an asset sheet
    """
    node = doc.nodes[key]
    if node.get("type") == "SECTION":
        return True
    w, h = doc.size(key)
    if min(w, h) < SPLIT_MIN_SIDE:
        return False
    kids = doc.kids(key)
    drawn = [k for k in kids if doc.subtree_draws(k)]
    if not drawn:
        return False
    if any(doc.nodes[k].get("type") == "TEXT" for k in kids):
        return True
    return sum(1 for k in drawn if doc.kids(k)) >= 6


def export_targets(doc, section_key):
    """Deepest sensible artwork units under a section, outermost-first."""
    out = []

    def visit(key):
        if doc.nodes[key].get("visible") is False:
            return
        if split_into(doc, key):
            before = len(out)
            for child in doc.kids(key):
                visit(child)
            if len(out) > before or doc.nodes[key].get("type") == "SECTION":
                return
            # nothing usable came out of the children - keep the board itself
        if doc.subtree_draws(key):
            w, h = doc.size(key)
            if w > 0 and h > 0:
                out.append(key)

    visit(section_key)
    return out


# --------------------------------------------------------------------------
# SVG emission
# --------------------------------------------------------------------------

def matrix_attr(t):
    if not isinstance(t, dict):
        return None
    m = [t.get("m00", 1), t.get("m10", 0), t.get("m01", 0),
         t.get("m11", 1), t.get("m02", 0), t.get("m12", 0)]
    if m == [1, 0, 0, 1, 0, 0]:
        return None
    return "matrix(" + " ".join(_num(v) for v in m) + ")"


def apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def compose(outer, inner):
    a, b, c, d, e, f = outer
    A, B, C, D, E, F = inner
    return (a * A + c * B, b * A + d * B,
            a * C + c * D, b * C + d * D,
            a * E + c * F + e, b * E + d * F + f)


def node_matrix(node):
    t = node.get("transform")
    if not isinstance(t, dict):
        return (1, 0, 0, 1, 0, 0)
    return (t.get("m00", 1), t.get("m10", 0), t.get("m01", 0),
            t.get("m11", 1), t.get("m02", 0), t.get("m12", 0))


IDENTITY = (1, 0, 0, 1, 0, 0)


def emit(doc, key, defs, out, ctm, bbox, depth=0):
    """Append SVG for `key` and its subtree; accumulate the world-space bbox."""
    node = doc.nodes[key]
    if node.get("visible") is False:
        return
    pad = "  " * (depth + 1)
    fills, strokes = doc.geometry(key)
    width, height = doc.size(key)

    body = []
    for geoms, paints, kind in ((fills, node.get("fillPaints"), "fill"),
                                (strokes, node.get("strokePaints"), "stroke")):
        painted = visible_paints(paints)
        if not geoms or not painted:
            continue
        for geom in geoms:
            blob = doc.blobs[geom["commandsBlob"]]
            if not blob:
                continue
            d, box = commands_to_d(parse_commands(blob))
            if not d or box is None:
                continue
            for corner in ((box[0], box[1]), (box[2], box[1]),
                           (box[0], box[3]), (box[2], box[3])):
                x, y = apply(ctm, *corner)
                bbox[0] = min(bbox[0], x); bbox[1] = min(bbox[1], y)
                bbox[2] = max(bbox[2], x); bbox[3] = max(bbox[3], y)
            rule = "evenodd" if geom.get("windingRule") == "ODD" else "nonzero"
            for paint in painted:
                attrs = fill_attrs(paint, defs, width or 1, height or 1)
                if not attrs:
                    continue
                # strokeGeometry is already an outlined ring, so it is filled
                # with the stroke paint rather than stroked.
                extra = ""
                if kind == "stroke":
                    weight = node.get("strokeWeight")
                    extra = (f' data-stroke-weight="{_num(weight)}"'
                             if isinstance(weight, (int, float)) else "")
                    extra += f' data-stroke-align="{node.get("strokeAlign") or ""}"'
                body.append(
                    f'{pad}<path d="{d}" fill-rule="{rule}" '
                    + " ".join(f'{k}="{v}"' for k, v in attrs.items())
                    + extra + "/>")

    inner = []
    for child in doc.kids(key):
        emit(doc, child, defs, inner, compose(ctm, node_matrix(doc.nodes[child])),
             bbox, depth + 1)

    if not body and not inner:
        return

    opacity = node.get("opacity")
    needs_group = depth > 0 or (isinstance(opacity, float) and opacity < 0.999)
    if not needs_group:
        out.extend(body + inner)
        return

    attrs = ""
    if depth > 0:
        m = matrix_attr(doc.nodes[key].get("transform"))
        if m:
            attrs += f' transform="{m}"'
    if isinstance(opacity, float) and opacity < 0.999:
        attrs += f' opacity="{_num(opacity)}"'
    label = (node.get("name") or "").replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;").replace('"', "&quot;")
    out.append(f'{"  " * depth}<g{attrs} data-name="{label[:80]}">')
    out.extend(body + inner)
    out.append(f'{"  " * depth}</g>')


_D_RE = re.compile(r'\sd="([^"]+)"')
_PT_RE = re.compile(r"[ML](-?[\d.]+) (-?[\d.]+)")


def is_bare_rectangle(svg):
    """One straight-edged path forming an axis-aligned box - a colour block, not
    artwork.  The ebook sections are full of these single-fill backing rects.
    A gradient-filled rectangle is kept - that is a designed band, not a swatch."""
    if "url(#" in svg:
        return False
    ds = _D_RE.findall(svg)
    if len(ds) != 1 or "C" in ds[0] or "Q" in ds[0]:
        return False
    pts = {(a, b) for a, b in _PT_RE.findall(ds[0])}
    if not 3 <= len(pts) <= 4:
        return False
    return len({p[0] for p in pts}) == 2 and len({p[1] for p in pts}) == 2


def clips(doc, key):
    node = doc.nodes[key]
    return node.get("type") in ("FRAME", "SECTION", "COMPONENT", "INSTANCE") \
        and node.get("frameMaskDisabled") is not True


def build_svg(doc, key):
    node = doc.nodes[key]
    width, height = doc.size(key)
    defs = Defs()
    body = []
    bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    emit(doc, key, defs, body, IDENTITY, bbox)
    if not body:
        return None, None

    if clips(doc, key) or bbox[0] == float("inf"):
        vx, vy, vw, vh = 0.0, 0.0, width, height
    else:
        vx = min(0.0, bbox[0])
        vy = min(0.0, bbox[1])
        vw = max(width, bbox[2]) - vx
        vh = max(height, bbox[3]) - vy
    if vw <= 0 or vh <= 0:
        return None, None

    head = (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{_num(vw)}" height="{_num(vh)}" '
            f'viewBox="{_num(vx)} {_num(vy)} {_num(vw)} {_num(vh)}" '
            f'fill="none">')
    svg = "\n".join([head, defs.render()] if defs.items else [head])
    svg += "\n" + "\n".join(body) + "\n</svg>\n"
    return svg, (round(vw, 2), round(vh, 2))


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------

def slug(text, fallback="untitled"):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return (text or fallback)[:70]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: fig_vectors.py <file.fig | folder-holding-canvas.fig>\n"
                 "       decode a Figma export first with scripts/fig_decode.py")
    base = sys.argv[1]
    fig = base if os.path.isfile(base) else os.path.join(base, "canvas.fig")
    base = os.path.dirname(fig)
    outdir = os.path.join(base, "vectors")

    doc = Doc(fig)
    print(f"decoded {fig} (format {doc.version}): "
          f"{len(doc.nodes):,} nodes, {len(doc.blobs):,} blobs")

    sections = {}
    for key, node in doc.nodes.items():
        if node.get("type") == "SECTION" and node.get("name") in SECTIONS:
            sections.setdefault(node["name"], []).append(key)
    for name in SECTIONS:
        if name not in sections:
            print(f"  WARNING: section {name!r} not found")

    os.makedirs(outdir, exist_ok=True)
    index = []
    totals = Counter()
    dupes = Counter()

    for name in SECTIONS:
        for section_key in sections.get(name, []):
            folder = slug(name)
            dest = os.path.join(outdir, folder)
            os.makedirs(dest, exist_ok=True)
            used, seen = {}, {}
            rows = []
            for key in export_targets(doc, section_key):
                svg, size = build_svg(doc, key)
                if not svg or is_bare_rectangle(svg):
                    continue
                if svg in seen:
                    dupes[name] += 1
                    continue
                stem = slug(doc.nodes[key].get("name"), "layer")
                n = used.get(stem, 0) + 1
                used[stem] = n
                filename = f"{stem}.svg" if n == 1 else f"{stem}-{n}.svg"
                seen[svg] = filename
                with open(os.path.join(dest, filename), "w") as f:
                    f.write(svg)
                paths = svg.count("<path ")
                rows.append((filename, doc.nodes[key].get("name") or "(unnamed)",
                             size, paths))
                totals[name] += 1
            index.append((name, folder, rows))

    lines = [
        "# Vector export", "",
        "SVGs recovered from `canvas.fig` by `scripts/fig_vectors.py`, straight "
        "out of each node's `fillGeometry` / `strokeGeometry` command blobs.", "",
        "Paths only. Figma stores live TEXT as characters plus a font "
        "reference, not as outlines, so text layers are **not** in these files "
        "- logos are unaffected because their wordmarks are already outlined "
        "vectors, but UI components such as buttons come out as their shape "
        "without the label.", "",
        "`strokeGeometry` is stored pre-outlined, so stroke shapes are filled "
        "with the stroke colour; the original `strokeWeight` is kept on each "
        "path as `data-stroke-weight`.", "",
        "| Section | Files |", "|---|---|",
    ]
    for name, folder, rows in index:
        lines.append(f"| {name} | {len(rows)} |")
    lines.append(f"| **Total** | **{sum(totals.values())}** |")
    lines.append("")

    for name, folder, rows in index:
        lines += [f"## {name}", "",
                  f"`vectors/{folder}/` - {len(rows)} files"
                  + (f", {dupes[name]} duplicate layers skipped" if dupes[name] else ""),
                  "", "| File | Layer name | Size (px) | Paths |",
                  "|---|---|---|---|"]
        for filename, layer, size, paths in rows:
            lines.append(f"| `{filename}` | {layer} | "
                         f"{size[0]:g} x {size[1]:g} | {paths} |")
        lines.append("")
    with open(os.path.join(outdir, "INDEX.md"), "w") as f:
        f.write("\n".join(lines))

    print()
    for name, folder, rows in index:
        print(f"  {name:34s} {len(rows):4d} svg"
              + (f"   ({dupes[name]} duplicates skipped)" if dupes[name] else ""))
    print(f"  {'TOTAL':34s} {sum(totals.values()):4d} svg -> {outdir}")


if __name__ == "__main__":
    main()
