"""Write a full asset set into a brand file, from the brand's own words.

Nobody should hand-author 120 asset entries. This reads what the brand already
says — the overview blocks, the prose rules, the meta line — and spreads those
lines across every template in the registry, in each colourway the template
supports.

    python3 -m engine.scaffold brands/<slug>/brand.json          # preview
    python3 -m engine.scaffold brands/<slug>/brand.json --write  # write it in

Editing any single asset afterwards is editing its JSON. This only ever produces
the starting point.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .templates_assets import REGISTRY

TONES = ("light", "dark", "accent")


# Blocks that describe the brand DOCUMENT rather than the business. Harvesting
# these put "Not written yet." and a brand's own hard rule on
# an ad, which is meta-commentary wearing a headline's clothes.
_META_TITLES = ("voice", "tagline", "the name", "what we are not", "rules",
                "distinction", "files", "misuse", "clear space")


def _lines(brand: dict) -> dict[str, list[str]]:
    """Harvest usable copy out of the brand file. Never invent a sentence.

    A brand can skip all of this by declaring `messages` in its meta: a short
    list of the things it actually wants to say. That is always better than a
    guess, and the guess is only here so a brand with nothing declared still
    gets a usable set.
    """
    declared = brand.get("meta", {}).get("messages")
    if declared:
        m = list(declared)[:6]
        # Pair each message with the NEXT one as its supporting line. Using
        # meta.line put the same logo rule under all 190 assets, which is a
        # sentence about the artwork, not something to say to a customer.
        return {"heads": m, "subs": m[1:] + m[:1], "rules": []}
    heads: list[str] = []
    subs: list[str] = []
    rules: list[str] = []
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") == "overview":
                for b in page.get("blocks", []):
                    if any(m in (b.get("title") or "").lower() for m in _META_TITLES):
                        continue
                    body = (b.get("body") or "").strip()
                    first = body.split(". ")[0].strip(" .")
                    if first and len(first) < 90:
                        heads.append(first + ".")
                    rest = body[len(first) + 2:].strip()
                    if rest:
                        subs.append(rest.split(". ")[0].strip(" .") + ".")
            if page.get("kind") == "prose":
                rules += [i for i in page.get("items", []) if len(i) < 100]
    # Section summaries are already one-line statements about the brand, so they
    # are the best remaining source once the overview blocks run out.
    for sec in brand.get("sections", []):
        if any(m in (sec.get("title") or "").lower() for m in _META_TITLES):
            continue
        summary = (sec.get("summary") or "").strip()
        if summary and len(summary) < 90:
            heads.append(summary.split(". ")[0].strip(" .") + ".")

    line = (brand.get("meta", {}).get("line") or "").strip()
    if line:
        subs.insert(0, line.split(". ")[0].strip(" .") + ".")
    name = brand.get("meta", {}).get("name", "")
    if not heads:
        heads = [name]
    # Six messages is a campaign. More than that and the set repeats itself.
    seen, unique = set(), []
    for h in heads:
        if h.lower() not in seen:
            seen.add(h.lower()); unique.append(h)
    return {"heads": unique[:6], "subs": subs or [name], "rules": rules}


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "asset"


def scaffold(brand: dict) -> list[dict]:
    copy = _lines(brand)
    heads, subs, rules = copy["heads"], copy["subs"], copy["rules"]
    out: list[dict] = []
    seen: set[str] = set()

    def add(tid: str, name: str, values: dict) -> None:
        n, i = name, 2
        while n in seen:
            n, i = f"{name}-{i}", i + 1
        seen.add(n)
        out.append({"template": tid, "name": n, "values": values})

    # A stat card with no statistic is a card showing the number one. Only build
    # it when the brand has actually declared some.
    stats = brand.get("meta", {}).get("stats") or []

    for tid, spec in sorted(REGISTRY.items()):
        if tid == "stat-card" and not stats:
            continue
        group = spec["group"]
        # Posts and ads carry a message, so they get one per line and per tone.
        if group in ("social-posts", "ads"):
            # Every message in every colourway. A brand with four things to say
            # gets twelve versions of each post shape, which is what a real
            # campaign folder looks like.
            for m_i, h in enumerate(heads):
                s_line = subs[m_i % len(subs)]
                for tone in TONES:
                    add(tid, f"{tid}-{_slug(h)[:24]}-{tone}", {
                        "headline": h, "sub": s_line, "tone": tone,
                        "cta": "Find out more",
                        "quote": h, "who": brand["meta"].get("name", ""),
                        "figure": (stats[m_i % len(stats)]["figure"] if stats else ""),
                        "label": (stats[m_i % len(stats)]["label"] if stats else s_line),
                        "bullets": rules[:3] or subs[:3]})
        elif group == "ads-display":
            add(tid, tid, {"headline": heads[0], "cta": "Find out more",
                           "tone": "accent"})
        else:
            add(tid, tid, {
                "headline": heads[0], "sub": subs[0], "line": subs[0],
                "cta": "Find out more",
                "quote": heads[0], "who": brand["meta"].get("name", ""),
                "figure": "1", "label": subs[0],
                "bullets": rules[:3] or subs[:3]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold a brand's asset set.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--write", action="store_true", help="write it into the brand file")
    args = ap.parse_args(argv)

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    items = scaffold(brand)
    groups: dict[str, int] = {}
    for i in items:
        g = REGISTRY[i["template"]]["group"]
        groups[g] = groups.get(g, 0) + 1

    print(f"{len(items)} assets across {len(groups)} groups")
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"   {n:4d}  {g}")
    if args.write:
        brand["assetSet"] = items
        args.brand.write_text(json.dumps(brand, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        print(f"written into {args.brand}")
    else:
        print("(preview only, pass --write to save)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
