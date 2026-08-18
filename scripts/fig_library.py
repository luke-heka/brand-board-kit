#!/usr/bin/env python3
"""Turn a decoded .fig into a browsable, named asset library.

`fig_decode.py` gets the pixels out, but they land hash-named, which is no use to
a person. This walks the node tree, works out which section each image sits in
and what the layer was called, and writes a copy under a readable path.

    python3 scripts/fig_library.py figma/<name>

Reads `document.min.json` and `raw/`, writes `library/<section>/<layer>.<ext>`
and `LIBRARY.md`. The originals in `raw/` are never touched, so the hash names
stay available as the ground truth.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# A section or a page is the unit a person navigates by. Frames below that are
# layout, not location, so they become part of the name instead of the folder.
CONTAINERS = {"CANVAS", "SECTION"}

# Canvas order matters. Everything up to and including the State of AI ebook is
# the brand system; everything after it is campaign and ad work, which is worth
# keeping but is not what a brand document is built from.
BRAND_SYSTEM_LAST = "state of ai in australia ebook"


def slug(s: str, limit: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", (s or "untitled").strip()).strip()
    s = re.sub(r"[\s_]+", "-", s).lower()
    return (s[:limit] or "untitled").strip("-")


def image_hashes(node: dict) -> list[tuple[str, str]]:
    """Every image hash a node references, wherever it hangs.

    Guessing paint key names missed 212 of 463 blobs: images also arrive as
    background paints, thumbnails and inside nested paint data. Search the
    node's own properties for any hash object instead, and never descend into
    `children`, which belong to their own node.
    """
    out: list[tuple[str, str]] = []

    def scan(obj, label: str, under_thumb: bool = False) -> None:
        if isinstance(obj, dict):
            h = (obj.get("hash") or {}).get("hex") if isinstance(obj.get("hash"), dict) else None
            if h and not under_thumb:
                out.append((h, obj.get("name") or label))
            for k, v in obj.items():
                if k != "children":
                    scan(v, obj.get("name") or label,
                         under_thumb or k == "imageThumbnail")
        elif isinstance(obj, list):
            for v in obj:
                scan(v, label, under_thumb)

    for k, v in node.items():
        if k != "children":
            scan(v, k, k == "imageThumbnail")
    return out


def walk(node: dict, section: str, page: str, trail: list[str], hits: list[dict]) -> None:
    kind = node.get("type")
    name = node.get("name") or ""
    if kind == "CANVAS":
        page, section = name, ""
    elif kind == "SECTION":
        section = name

    here = trail + ([name] if name and kind not in CONTAINERS else [])
    for h, slot in image_hashes(node):
        hits.append({"hash": h, "page": page, "section": section,
                     "layer": name or slot, "trail": here[-3:],
                     "w": node.get("width"), "h": node.get("height")})
    for child in node.get("children") or []:
        walk(child, section, page, here, hits)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = Path(argv[0]).resolve()
    doc = json.loads((root / "document.min.json").read_text())
    raw = root / "raw"
    lib = root / "library"

    by_hash = {p.stem: p for p in raw.iterdir() if p.is_file()}
    hits: list[dict] = []
    for top in doc if isinstance(doc, list) else [doc]:
        walk(top, "", "", [], hits)

    # One image can be painted in many places. The first use in canvas order is
    # the one worth naming it after, and the rest are recorded as extra uses.
    # The cut line is a position on the canvas, not a position in the tree, so
    # order sections by their x coordinate the way they read on screen.
    order: list[tuple[float, str]] = []
    def sections(node, ):
        if node.get("type") == "SECTION" and node.get("name"):
            order.append((node.get("x") or 0, node["name"]))
        for c in node.get("children") or []:
            sections(c)
    for top in doc if isinstance(doc, list) else [doc]:
        sections(top)
    ordered = [n for _, n in sorted(order)]
    cut = next((i for i, n in enumerate(ordered)
                if n.strip().lower() == BRAND_SYSTEM_LAST), len(ordered) - 1)
    campaign = {n for n in ordered[cut + 1:]}
    for h in hits:
        h["after_cut"] = h["section"] in campaign

    first: dict[str, dict] = {}
    uses: dict[str, int] = defaultdict(int)
    for h in hits:
        uses[h["hash"]] += 1
        first.setdefault(h["hash"], h)

    written, missing, seen = 0, [], set()
    for h, meta in first.items():
        src = by_hash.get(h)
        if not src:
            missing.append(h)
            continue
        sec = meta["section"] or meta["page"] or "unsorted"
        group = "02-campaigns" if meta.get("after_cut") else "01-brand-system"
        folder = f"{group}/{slug(sec)}"
        base = slug(meta["layer"] or "image", 48)
        dest_dir = lib / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem, n = base, 2
        while (key := f"{folder}/{stem}") in seen:
            stem, n = f"{base}-{n}", n + 1
        seen.add(key)
        shutil.copy2(src, dest_dir / f"{stem}{src.suffix}")
        written += 1

    orphans = sorted(set(by_hash) - set(first))   # the low-res thumbnails
    if orphans:
        (lib / "_thumbnails").mkdir(parents=True, exist_ok=True)
        for h in orphans:
            shutil.copy2(by_hash[h], lib / "_thumbnails" / by_hash[h].name)

    folders = defaultdict(int)
    for p in lib.rglob("*"):
        if p.is_file():
            folders[str(p.parent.relative_to(lib))] += 1

    lines = ["# Asset library", "",
             f"{written} images placed by the section they appear in, "
             f"{len(orphans)} low-res thumbnails set aside in `_thumbnails`.", "",
             "Names come from the Figma layer. `raw/` still holds every blob under its",
             "original hash, so nothing here is the only copy.", "",
             "| Folder | Images |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(folders.items(), key=lambda kv: -kv[1])]
    (root / "LIBRARY.md").write_text("\n".join(lines) + "\n")

    print(f"placed   {written}")
    print(f"thumbs   {len(orphans)} (set aside in library/_thumbnails)")
    print(f"missing  {len(missing)}")
    print(f"folders  {len(folders)}")
    for k, v in sorted(folders.items(), key=lambda kv: -kv[1])[:12]:
        print(f"   {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
