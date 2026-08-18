"""brand.json -> an ordered page plan.

Two passes. The first lays out cover, dividers, section pages and the closing
page so every page has a real number; the second fills the table of contents
from those numbers. Nothing about the deck's length is declared by hand — add a
section to the brand file and the contents page follows.
"""

from __future__ import annotations

import copy


def build(brand: dict, sections: list | None = None,
          dividers: bool = True, contents: bool = True) -> list[dict]:
    sections = sections if sections is not None else brand.get("sections", [])
    if not sections:
        raise ValueError("brand file declares no sections")

    meta = brand.get("meta", {})
    pages: list[dict] = [{
        "kind": "cover",
        "mark": meta.get("coverMark"),
    }]

    toc_slot = None
    if contents:
        toc_slot = len(pages)
        pages.append({"kind": "toc", "entries": []})

    entries = []
    for i, sec in enumerate(sections, start=1):
        first = len(pages) + 1
        if dividers:
            pages.append({"kind": "divider", "title": sec["title"], "index": i})
        for p in sec.get("pages", []):
            page = copy.deepcopy(p)
            page.setdefault("section", sec["title"])
            pages.append(page)
        entries.append({
            "title": sec["title"],
            "summary": sec.get("summary", ""),
            "first": first,
            "last": len(pages),
        })

    pages.append({"kind": "closing", "title": meta.get("closing", "Thank you")})
    if toc_slot is not None:
        pages[toc_slot]["entries"] = entries
    return pages


def context(brand: dict, root) -> dict:
    from .theme import PALETTE_DEFAULTS, SHAPE_DEFAULTS
    return {
        "meta": brand["meta"],
        "palette": {**PALETTE_DEFAULTS, **brand.get("palette", {})},
        "shape": {**SHAPE_DEFAULTS, **brand.get("shape", {})},
        "root": root,
    }
