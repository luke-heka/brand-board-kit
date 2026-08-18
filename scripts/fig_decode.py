#!/usr/bin/env python3
"""
fig_decode.py - decode a Figma .fig document binary into a readable node tree.

Container framing (verified against canvas.fig, format version 106):

    offset 0   : b"fig-kiwi"                    8 bytes ASCII magic
    offset 8   : uint32 LE                      format version (106)
    offset 12  : uint32 LE  + payload           chunk 1 - the kiwi SCHEMA
    then       : uint32 LE  + payload           chunk 2 - the message DATA
    ...repeats until EOF

Each chunk is length-prefixed. The compression is *per chunk and sniffed*, not
fixed: in this file the schema chunk is raw deflate (zlib -15) while the data
chunk is zstd (magic 28 b5 2f fd). Assuming deflate for both is what produces
"zlib.error: invalid stored block lengths".

The schema is the standard evanw/kiwi compiled binary schema:

    varuint definition_count
    definition := string name, byte kind, varuint field_count, field*
    field      := string name, varint type, byte is_array, varuint id
    kind        : 0=ENUM 1=STRUCT 2=MESSAGE
    type        : >=0 index into definitions, <0 builtin (-1-index into
                  [bool byte int uint float string int64 uint64])

Strings are null-terminated UTF-8. Ints are LEB128 varints, signed ones
zigzagged. Floats use kiwi's rotated-exponent varfloat (single 0 byte for zero).

Usage:  python3 fig_decode.py [path/to/dir]
Writes document.json, document.min.json, INVENTORY.md, styles.json,
colours.md and fonts.md next to canvas.fig.
"""

import json
import os
import re
import struct
import sys
import zlib
from collections import Counter, defaultdict

# --------------------------------------------------------------------------
# container
# --------------------------------------------------------------------------

MAGIC = b"fig-kiwi"


def _inflate(chunk: bytes) -> bytes:
    """Decompress one chunk, sniffing the codec from its magic bytes."""
    if chunk[:4] == b"\x28\xb5\x2f\xfd":  # zstd frame magic
        import zstandard

        return zstandard.ZstdDecompressor().stream_reader(chunk).read()
    if chunk[:2] in (b"\x78\x01", b"\x78\x9c", b"\x78\xda"):  # zlib wrapper
        return zlib.decompress(chunk)
    return zlib.decompress(chunk, -15)  # raw deflate


def read_chunks(path):
    """Yield the inflated chunks of a .fig file, in order."""
    data = open(path, "rb").read()
    if data[:8] != MAGIC:
        raise ValueError(f"not a .fig file: magic is {data[:8]!r}")
    version, = struct.unpack_from("<I", data, 8)
    pos = 12
    chunks = []
    while pos + 4 <= len(data):
        n, = struct.unpack_from("<I", data, pos)
        pos += 4
        if n == 0 or pos + n > len(data):
            break
        chunks.append(_inflate(data[pos:pos + n]))
        pos += n
    return version, chunks


# --------------------------------------------------------------------------
# kiwi byte buffer
# --------------------------------------------------------------------------

_F32 = struct.Struct("<f")
_U32 = struct.Struct("<I")

BUILTINS = ["bool", "byte", "int", "uint", "float", "string", "int64", "uint64"]
KINDS = ["ENUM", "STRUCT", "MESSAGE"]


class ByteBuffer:
    __slots__ = ("b", "i", "n")

    def __init__(self, b):
        self.b = b
        self.i = 0
        self.n = len(b)

    def eof(self):
        return self.i >= self.n

    def byte(self):
        v = self.b[self.i]
        self.i += 1
        return v

    def varuint(self):
        r = 0
        shift = 0
        b = self.b
        i = self.i
        while True:
            c = b[i]
            i += 1
            r |= (c & 0x7F) << shift
            if c < 0x80:
                break
            shift += 7
        self.i = i
        return r & 0xFFFFFFFF

    def varint(self):
        v = self.varuint()
        return (v >> 1) ^ -(v & 1)

    def varuint64(self):
        r = 0
        shift = 0
        while True:
            c = self.b[self.i]
            self.i += 1
            r |= (c & 0x7F) << shift
            if c < 0x80:
                break
            shift += 7
        return r & 0xFFFFFFFFFFFFFFFF

    def varint64(self):
        v = self.varuint64()
        return (v >> 1) ^ -(v & 1)

    def varfloat(self):
        """kiwi rotates the float bits so the exponent lands in the low byte;
        an all-zero low byte means the value is exactly 0 and costs 1 byte."""
        if self.b[self.i] == 0:
            self.i += 1
            return 0.0
        bits, = _U32.unpack_from(self.b, self.i)
        self.i += 4
        bits = ((bits << 23) | (bits >> 9)) & 0xFFFFFFFF
        return _F32.unpack(_U32.pack(bits))[0]

    def string(self):
        j = self.b.index(0, self.i)
        s = self.b[self.i:j].decode("utf-8", "replace")
        self.i = j + 1
        return s

    def raw(self, n):
        v = self.b[self.i:self.i + n]
        self.i += n
        return v


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

class Schema:
    def __init__(self, blob):
        bb = ByteBuffer(blob)
        count = bb.varuint()
        self.defs = []
        for _ in range(count):
            name = bb.string()
            kind = bb.byte()
            nfields = bb.varuint()
            fields = []
            for _ in range(nfields):
                fname = bb.string()
                ftype = bb.varint()
                is_array = bb.byte() != 0
                fid = bb.varuint()
                fields.append(
                    {"name": fname, "type": ftype, "array": is_array, "id": fid}
                )
            self.defs.append({"name": name, "kind": kind, "fields": fields})
        self.consumed = bb.i
        self.total = len(blob)
        self.by_name = {d["name"]: i for i, d in enumerate(self.defs)}
        # message field lookup by id, enum value lookup
        for d in self.defs:
            if d["kind"] == 2:
                d["by_id"] = {f["id"]: f for f in d["fields"]}
            elif d["kind"] == 0:
                d["by_val"] = {f["id"]: f["name"] for f in d["fields"]}


# --------------------------------------------------------------------------
# decoder
# --------------------------------------------------------------------------

class Decoder:
    def __init__(self, schema: Schema, bb: ByteBuffer):
        self.s = schema
        self.bb = bb

    def value(self, ftype):
        bb = self.bb
        if ftype < 0:
            t = BUILTINS[-1 - ftype]
            if t == "bool":
                return bb.byte() != 0
            if t == "byte":
                return bb.byte()
            if t == "int":
                return bb.varint()
            if t == "uint":
                return bb.varuint()
            if t == "float":
                return bb.varfloat()
            if t == "string":
                return bb.string()
            if t == "int64":
                return bb.varint64()
            if t == "uint64":
                return bb.varuint64()
            raise ValueError(t)
        return self.compound(self.s.defs[ftype])

    def field(self, f):
        if f["array"]:
            n = self.bb.varuint()
            if f["type"] == -2:  # byte[] - read raw, do not varint each one
                return self.bb.raw(n)
            return [self.value(f["type"]) for _ in range(n)]
        return self.value(f["type"])

    def compound(self, d):
        kind = d["kind"]
        if kind == 0:  # ENUM
            v = self.bb.varuint()
            return d["by_val"].get(v, v)
        if kind == 1:  # STRUCT - fields in declared order, no ids
            return {f["name"]: self.field(f) for f in d["fields"]}
        # MESSAGE - (id, value) pairs terminated by id 0
        out = {}
        while True:
            fid = self.bb.varuint()
            if fid == 0:
                return out
            f = d["by_id"].get(fid)
            if f is None:
                raise ValueError(f"unknown field id {fid} in message {d['name']}")
            out[f["name"]] = self.field(f)


def jsonable(o):
    """bytes -> hex/ascii preview so json.dump never chokes."""
    if isinstance(o, bytes):
        return {"$bytes": len(o), "hex": o[:64].hex()}
    if isinstance(o, dict):
        return {k: jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [jsonable(v) for v in o]
    if isinstance(o, float):
        return round(o, 6) if o == o and abs(o) != float("inf") else str(o)
    return o


# --------------------------------------------------------------------------
# figma-specific helpers
# --------------------------------------------------------------------------

def guid_key(g):
    if not isinstance(g, dict):
        return None
    return f"{g.get('sessionID', 0)}:{g.get('localID', 0)}"


def to_hex(color):
    """Figma stores linear-ish 0..1 sRGB floats; Figma's own UI shows the raw
    channel * 255 rounded, so match that."""
    if not isinstance(color, dict):
        return None
    try:
        r, g, b = (color.get(k, 0) or 0 for k in ("r", "g", "b"))
    except Exception:
        return None
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, round(r * 255))),
        max(0, min(255, round(g * 255))),
        max(0, min(255, round(b * 255))),
    )


def is_local(n):
    """Figma copies every *used* library style/variable into the file's
    internal canvas alongside the ones defined here. The local ones are
    publishable and carry no library key; the imported ones are the reverse.
    Only the local set is what the Figma UI counts in its styles panel."""
    return bool(n.get("isPublishable")) and not n.get("sourceLibraryKey") \
        and not n.get("key")


def is_live(n):
    return not n.get("isSoftDeleted")


def unit_value(v):
    """lineHeight / letterSpacing are {value, units} structs."""
    if not isinstance(v, dict):
        return None
    val = v.get("value")
    units = v.get("units")
    if val is None:
        return None
    if units == "PERCENT":
        return f"{val:g}%"
    if units == "PIXELS":
        return f"{val:g}px"
    return f"{val:g}"  # RAW == multiplier


def resolve_variable_value(vd):
    """variableData -> a plain python value (hex for colours)."""
    if not isinstance(vd, dict):
        return None
    val = vd.get("value")
    if not isinstance(val, dict):
        return jsonable(val)
    if "colorValue" in val:
        c = val["colorValue"]
        out = {"hex": to_hex(c)}
        if isinstance(c, dict) and c.get("a", 1) not in (1, 1.0, None):
            out["alpha"] = round(c["a"], 4)
        return out
    for k in ("floatValue", "textValue", "boolValue"):
        if k in val:
            return val[k]
    if "alias" in val:
        return {"alias": jsonable(val["alias"])}
    return jsonable(val)


def node_size(n):
    sz = n.get("size")
    if isinstance(sz, dict):
        return sz.get("x"), sz.get("y")
    return None, None


def node_xy(n):
    """Absolute-ish x/y from the node's own affine transform."""
    t = n.get("transform")
    if isinstance(t, dict):
        return t.get("m02"), t.get("m12")
    return None, None


def fmt_px(v):
    if v is None:
        return "?"
    return f"{v:,.0f}"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.abspath(__file__)
    )
    if os.path.isdir(base):
        fig = os.path.join(base, "canvas.fig")
    else:
        fig = base
        base = os.path.dirname(fig)
    out = base

    version, chunks = read_chunks(fig)
    log = [f"format version {version}", f"{len(chunks)} chunks"]
    schema = Schema(chunks[0])
    log.append(
        f"schema: {len(schema.defs)} definitions, "
        f"{schema.consumed}/{schema.total} bytes consumed"
    )
    if schema.consumed != schema.total:
        log.append("WARNING: schema not fully consumed")

    body = chunks[1]
    log.append(f"data chunk inflated to {len(body):,} bytes")

    bb = ByteBuffer(body)
    dec = Decoder(schema, bb)
    root_def = schema.defs[schema.by_name["Message"]]
    message = dec.compound(root_def)
    log.append(f"message decoded, {bb.i:,}/{bb.n:,} bytes consumed")
    trailing = bb.n - bb.i
    if trailing:
        log.append(f"NOTE: {trailing:,} trailing bytes after root message")

    changes = message.get("nodeChanges") or []
    log.append(f"nodeChanges: {len(changes)}")

    # ---- index nodes -----------------------------------------------------
    nodes = {}
    for c in changes:
        k = guid_key(c.get("guid"))
        if k is None:
            continue
        if k in nodes:
            nodes[k].update(c)  # later changes win
        else:
            nodes[k] = dict(c)

    # ---- build the tree via parentIndex ---------------------------------
    children = defaultdict(list)
    roots = []
    for k, n in nodes.items():
        pi = n.get("parentIndex")
        pk = guid_key(pi.get("guid")) if isinstance(pi, dict) else None
        pos = pi.get("position") if isinstance(pi, dict) else None
        n["_key"] = k
        n["_pos"] = pos if isinstance(pos, str) else ""
        if pk and pk in nodes:
            children[pk].append(k)
        else:
            roots.append(k)
    for k in children:
        children[k].sort(key=lambda c: (nodes[c]["_pos"], c))

    def build(k, depth=0):
        n = nodes[k]
        w, h = node_size(n)
        x, y = node_xy(n)
        kids = children.get(k, [])
        node = {
            "id": k,
            "name": n.get("name"),
            "type": n.get("type"),
            "x": x, "y": y, "width": w, "height": h,
            "visible": n.get("visible", True),
            "childCount": len(kids),
        }
        for extra in ("styleId", "textData", "fillPaints", "strokePaints",
                      "fontName", "fontSize", "opacity", "blendMode",
                      "cornerRadius", "componentKey", "symbolData"):
            if extra in n:
                node[extra] = jsonable(n[extra])
        if kids:
            node["children"] = [build(c, depth + 1) for c in kids]
        return node

    # the document root is the node with type DOCUMENT; pages are its children
    doc_keys = [k for k in nodes if nodes[k].get("type") == "DOCUMENT"]
    tree_roots = doc_keys if doc_keys else roots
    document = [build(k) for k in tree_roots]

    with open(os.path.join(out, "document.min.json"), "w") as f:
        json.dump(document, f, separators=(",", ":"), default=str)
    with open(os.path.join(out, "document.json"), "w") as f:
        json.dump(document, f, indent=2, default=str)

    # ---- pages + sections -----------------------------------------------
    # "Internal Only Canvas" is Figma's own bucket for styles, variables and
    # detached component definitions. It is not a user page.
    INTERNAL = "Internal Only Canvas"
    pages, internal = [], None
    for d in document:
        for pg in d.get("children", []):
            if pg.get("type") not in ("CANVAS", "PAGE"):
                continue
            tops = sorted(pg.get("children", []) or [],
                          key=lambda c: (c.get("x") if c.get("x") is not None
                                         else 1e12))
            rec = {"page": pg, "tops": tops}
            if pg.get("name") == INTERNAL:
                internal = rec
            else:
                pages.append(rec)

    lines = ["# Figma inventory - " + os.path.basename(base), ""]
    try:
        meta = json.load(open(os.path.join(base, "meta.json")))
        lines += [f"**File:** {meta.get('file_name')}  ",
                  f"**Exported:** {meta.get('exported_at')}  ", ""]
    except Exception:
        pass
    lines += [
        f"Decoded from `canvas.fig` (fig-kiwi format version {version}).  ",
        f"**{len(nodes):,} nodes**, **{len(pages)} user pages**"
        + (f", plus Figma's `{INTERNAL}` "
           f"({len(internal['tops'])} style/variable/component records)."
           if internal else "."),
        "",
        "Top-level items are listed left-to-right by canvas x position, so the "
        "order matches the order on screen.", "",
    ]

    def table(rows_src):
        rows = ["| # | Name | Type | Size (px) | x | Children |",
                "|---|------|------|-----------|---|----------|"]
        for i, t in enumerate(rows_src, 1):
            rows.append(
                f"| {i} | {t.get('name') or '(unnamed)'} | {t.get('type')} | "
                f"{fmt_px(t.get('width'))} x {fmt_px(t.get('height'))} | "
                f"{fmt_px(t.get('x'))} | {t.get('childCount')} |")
        return rows

    for p in pages:
        pg = p["page"]
        secs = [t for t in p["tops"] if t.get("type") == "SECTION"]
        lines += [f"## {pg.get('name') or '(unnamed page)'}", "",
                  f"{len(p['tops'])} top-level items"
                  + (f" ({len(secs)} sections)" if secs else ""), ""]
        lines += table(p["tops"])
        lines.append("")
        # one level down inside each section - that is where the real work sits
        deep = [t for t in p["tops"]
                if t.get("type") == "SECTION" and t.get("children")]
        if deep:
            lines += [f"### Inside the sections of {pg.get('name')}", ""]
            for s in deep:
                kids = sorted(s.get("children", []),
                              key=lambda c: (c.get("x") if c.get("x")
                                             is not None else 1e12))
                lines.append(f"**{s.get('name')}** - {len(kids)} children")
                lines.append("")
                for c in kids:
                    lines.append(
                        f"- `{c.get('name') or '(unnamed)'}` "
                        f"[{c.get('type')}] "
                        f"{fmt_px(c.get('width'))}x{fmt_px(c.get('height'))}"
                        + (f", {c.get('childCount')} children"
                           if c.get("childCount") else ""))
                lines.append("")

    if internal:
        kinds = Counter(t.get("type") for t in internal["tops"])
        lines += [f"## {INTERNAL} (Figma internal, not a user page)", "",
                  "Holds the file's style, variable and component records.", "",
                  "| Record type | Count |", "|---|---|"]
        for k, c in kinds.most_common():
            lines.append(f"| {k} | {c} |")
        lines += ["", "See `styles.json` for these resolved to real values.",
                  ""]
    open(os.path.join(out, "INVENTORY.md"), "w").write("\n".join(lines))

    # ---- styles ----------------------------------------------------------
    def font_of(n):
        fn = n.get("fontName") or {}
        if isinstance(fn, dict):
            return {"family": fn.get("family"), "style": fn.get("style"),
                    "postscript": fn.get("postscript")}
        return {}

    def bucket(n):
        if not is_live(n):
            return "deleted"
        return "local" if is_local(n) else "library"

    styles = {
        "_note": (
            "local = defined in this file (what Figma's styles panel counts). "
            "library = imported from a subscribed library and cached here "
            "because something in the file uses it. deleted = soft-deleted, "
            "still present in the binary."),
        "textStyles": {"local": [], "library": [], "deleted": []},
        "paintStyles": {"local": [], "library": [], "deleted": []},
        "effectStyles": {"local": [], "library": [], "deleted": []},
        "gridStyles": {"local": [], "library": [], "deleted": []},
        "variableCollections": [],
        "variables": {"local": [], "library": []},
    }

    set_by_guid, set_by_key = {}, {}
    for k, n in nodes.items():
        if n.get("type") == "VARIABLE_SET":
            set_by_guid[k] = n
            if n.get("key"):
                set_by_key[n["key"]] = n

    for k, n in nodes.items():
        st = n.get("styleType")
        b = bucket(n)
        if st == "TEXT":
            styles["textStyles"][b].append({
                "id": k, "name": n.get("name"),
                "description": n.get("styleDescription") or n.get("description"),
                "fontFamily": (n.get("fontName") or {}).get("family"),
                "fontWeight": (n.get("fontName") or {}).get("style"),
                "postscript": (n.get("fontName") or {}).get("postscript"),
                "fontSize": n.get("fontSize"),
                "lineHeight": unit_value(n.get("lineHeight")),
                "letterSpacing": unit_value(n.get("letterSpacing")),
                "textCase": n.get("textCase"),
                "paragraphSpacing": n.get("paragraphSpacing"),
            })
        elif st == "FILL":
            styles["paintStyles"][b].append({
                "id": k, "name": n.get("name"),
                "description": n.get("styleDescription"),
                "paints": [{
                    "type": p.get("type"),
                    "hex": to_hex(p.get("color")),
                    "alpha": round((p.get("color") or {}).get("a", 1), 4)
                    if isinstance(p.get("color"), dict) else None,
                    "opacity": p.get("opacity"),
                } for p in (n.get("fillPaints") or []) if isinstance(p, dict)],
            })
        elif st == "EFFECT":
            styles["effectStyles"][b].append(
                {"id": k, "name": n.get("name"),
                 "effects": jsonable(n.get("effects"))})
        elif st == "GRID":
            styles["gridStyles"][b].append(
                {"id": k, "name": n.get("name"),
                 "grids": jsonable(n.get("layoutGrids"))})

    for k, n in set_by_guid.items():
        styles["variableCollections"].append({
            "id": k, "name": n.get("name"),
            "scope": "local" if is_local(n) else "library",
            "sourceLibraryKey": n.get("sourceLibraryKey"),
            "modes": jsonable(n.get("variableSetModes")),
            "variableCount": 0,
        })
    coll_by_id = {c["id"]: c for c in styles["variableCollections"]}

    for k, n in nodes.items():
        if n.get("type") != "VARIABLE":
            continue
        ref = n.get("variableSetID") or {}
        owner = None
        if isinstance(ref.get("guid"), dict):
            owner = set_by_guid.get(guid_key(ref["guid"]))
        elif isinstance(ref.get("assetRef"), dict):
            owner = set_by_key.get(ref["assetRef"].get("key"))
        vals = []
        for e in ((n.get("variableDataValues") or {}).get("entries") or []):
            vals.append({"mode": guid_key(e.get("modeID")),
                         "value": resolve_variable_value(e.get("variableData"))})
        scope = "local" if is_local(n) else "library"
        styles["variables"][scope].append({
            "id": k, "name": n.get("name"),
            "collection": owner.get("name") if owner else None,
            "resolvedType": n.get("variableResolvedType"),
            "values": vals,
        })
        if owner is not None:
            c = coll_by_id.get(guid_key(owner["guid"]))
            if c:
                c["variableCount"] += 1

    styles["_counts"] = {
        grp: {b: len(v) for b, v in val.items()}
        for grp, val in styles.items()
        if isinstance(val, dict) and grp != "_counts"
        and all(isinstance(x, list) for x in val.values())
    }
    styles["_counts"]["variableCollections"] = len(
        styles["variableCollections"])
    with open(os.path.join(out, "styles.json"), "w") as f:
        json.dump(styles, f, indent=2, default=str)

    # ---- colours ---------------------------------------------------------
    colour_nodes = defaultdict(Counter)
    colour_count = Counter()
    for k, n in nodes.items():
        seen = set()
        for key in ("fillPaints", "strokePaints"):
            for p in (n.get(key) or []):
                if not isinstance(p, dict):
                    continue
                if p.get("type") not in (None, "SOLID"):
                    continue
                if p.get("visible") is False:
                    continue
                hx = to_hex(p.get("color"))
                if hx:
                    seen.add(hx)
        for hx in seen:
            colour_count[hx] += 1
            colour_nodes[hx][n.get("name") or "(unnamed)"] += 1

    clines = ["# Solid fill colours", "",
              f"{len(colour_count)} distinct solid hex values across "
              f"{sum(colour_count.values()):,} node uses.", "",
              "| Hex | Nodes | Most common node names |",
              "|-----|-------|------------------------|"]
    for hx, c in colour_count.most_common():
        top = ", ".join(f"{nm} ({ct})"
                        for nm, ct in colour_nodes[hx].most_common(4))
        clines.append(f"| `{hx}` | {c} | {top} |")
    open(os.path.join(out, "colours.md"), "w").write("\n".join(clines))

    # ---- fonts -----------------------------------------------------------
    combos = Counter()
    families = Counter()
    for k, n in nodes.items():
        fn = n.get("fontName")
        if not isinstance(fn, dict):
            continue
        fam = fn.get("family")
        if not fam:
            continue
        sty = fn.get("style") or ""
        size = n.get("fontSize")
        size_s = f"{size:g}" if isinstance(size, (int, float)) else "?"
        combos[(fam, sty, size_s)] += 1
        families[fam] += 1

    style_combos = Counter()
    for s in styles["textStyles"]["local"]:
        size = s.get("fontSize")
        style_combos[(s.get("fontFamily"), s.get("fontWeight"),
                      f"{size:g}" if isinstance(size, (int, float)) else "?")] += 1

    flines = ["# Fonts", "",
              f"Across every node that carries a font: **{len(families)} "
              f"distinct families**, {len(combos)} family/style/size "
              f"combinations.", "",
              "## Families (all nodes)", "",
              "| Family | Nodes |", "|--------|-------|"]
    for fam, c in families.most_common():
        flines.append(f"| {fam} | {c} |")
    flines += ["", "## Family / style / size (all nodes)", "",
               "| Family | Style | Size | Nodes |",
               "|--------|-------|------|-------|"]
    for (fam, sty, size), c in combos.most_common():
        flines.append(f"| {fam} | {sty} | {size} | {c} |")
    flines += ["", "## Local text styles only", "",
               f"{len(styles['textStyles']['local'])} local text styles.", "",
               "| Family | Weight | Size | Styles |",
               "|--------|--------|------|--------|"]
    for (fam, sty, size), c in sorted(style_combos.items(),
                                      key=lambda kv: (-kv[1], str(kv[0]))):
        flines.append(f"| {fam} | {sty} | {size} | {c} |")
    open(os.path.join(out, "fonts.md"), "w").write("\n".join(flines))

    # ---- report / verification ------------------------------------------
    print("\n".join(log))
    print(f"\nnodes indexed: {len(nodes):,}")
    print(f"user pages: {len(pages)}"
          + (f" (+ Figma's internal canvas, {len(internal['tops'])} records)"
             if internal else ""))
    for p in pages:
        secs = sum(1 for t in p["tops"] if t.get("type") == "SECTION")
        print(f"  - {p['page'].get('name')!r}: {len(p['tops'])} top-level "
              f"({secs} SECTION)")

    c = styles["_counts"]
    print(f"\ntext styles   local {c['textStyles']['local']:3d}  "
          f"library {c['textStyles']['library']:3d}  "
          f"deleted {c['textStyles']['deleted']:3d}")
    print(f"paint styles  local {c['paintStyles']['local']:3d}  "
          f"library {c['paintStyles']['library']:3d}  "
          f"deleted {c['paintStyles']['deleted']:3d}")
    print(f"effect styles local {c['effectStyles']['local']:3d}  "
          f"library {c['effectStyles']['library']:3d}  "
          f"deleted {c['effectStyles']['deleted']:3d}")
    for col in styles["variableCollections"]:
        print(f"  collection {col['name']!r} [{col['scope']}] "
              f"{col['variableCount']} variables")
    print(f"distinct solid colours: {len(colour_count)}")
    print(f"local text style families: "
          f"{sorted({s['fontFamily'] for s in styles['textStyles']['local']})}")
    print(f"all font families: {sorted(families)}")

    big = max(pages, key=lambda p: len(p["tops"])) if pages else None
    if big:
        print(f"\nfirst 20 top-level on {big['page'].get('name')!r} "
              f"(left to right):")
        for i, t in enumerate(big["tops"][:20], 1):
            print(f"  {i:2d}. {t.get('name')!r} [{t.get('type')}] "
                  f"{fmt_px(t.get('width'))}x{fmt_px(t.get('height'))} "
                  f"x={fmt_px(t.get('x'))} kids={t.get('childCount')}")

    # ground-truth spot check
    all_names = {n.get("name") for n in nodes.values()}
    expect = ["Logo Assets", "Linkedin Banner", "Graphic Elements",
              "Stationery & Print Collateral", "UI Branding Assets",
              "Social Media & Marketing", "Advertising & Campaigns",
              "Mockups & Presentations", "Static Ad Designs",
              "Branding Guidelines", "Brand Overview", "Email Signatures",
              "Project Proposal", "Gold Coast Workshops", "Melbourne"]
    expect += [f"LM{i:02d}" for i in range(1, 7)]
    expect += [f"DWY-{i:02d}" for i in range(6, 29)]
    missing = [e for e in expect if e not in all_names]
    print(f"\nground-truth names present: {len(expect) - len(missing)}"
          f"/{len(expect)}"
          + (f"  MISSING: {missing}" if missing else "  (all found)"))


if __name__ == "__main__":
    main()
