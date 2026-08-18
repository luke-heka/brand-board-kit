#!/usr/bin/env python3
"""Generate stand-in artwork so a brand renders before the real files exist.

    python3 scripts/make_placeholders.py brands/your-brand/brand.json

Reads the brand's own palette and wordmark, then writes the seven assets the
gate asks for as SVG. Every one is visibly a placeholder and says on its face
which file replaces it, so nobody ships one by accident.

The point is order of operations. Rendering the whole document on day one and
replacing artwork one file at a time beats staring at a list of seven missing
files with nothing on screen.

Existing files are never overwritten unless --force is passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

LOGO = ["lockup-primary.svg", "lockup-reversed.svg", "mark-primary.svg"]
APPS = ["website.png", "social.png", "card.png", "signage.png"]


def _mark(fg: str, size: int = 240) -> str:
    """A ring and a bar. Geometric on purpose: nothing here reads as a real logo.

    The ground is transparent. A logo file that paints its own background shows
    up as a pale box the moment it lands on a dark panel, which is the single
    most common thing wrong with a supplied logo.
    """
    c = size / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <circle cx="{c}" cy="{c}" r="{size*0.30:.1f}" fill="none" stroke="{fg}" stroke-width="{size*0.075:.1f}"/>
  <rect x="{c - size*0.045:.1f}" y="{c - size*0.30:.1f}" width="{size*0.09:.1f}" height="{size*0.60:.1f}" rx="{size*0.045:.1f}" fill="{fg}"/>
</svg>'''


def _lockup(word: str, fg: str, note: str) -> str:
    w, h = 900, 260
    word = escape(word)[:28]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <circle cx="120" cy="{h/2}" r="52" fill="none" stroke="{fg}" stroke-width="18"/>
  <rect x="112" y="{h/2 - 52}" width="16" height="104" rx="8" fill="{fg}"/>
  <text x="212" y="{h/2 + 4}" font-family="Inter, Helvetica, Arial, sans-serif"
        font-size="64" font-weight="600" letter-spacing="-2" fill="{fg}"
        dominant-baseline="middle">{word}</text>
  <text x="212" y="{h/2 + 62}" font-family="Inter, Helvetica, Arial, sans-serif"
        font-size="19" font-weight="400" letter-spacing="0.5" fill="{fg}"
        opacity="0.55" dominant-baseline="middle">PLACEHOLDER {escape(note)}</text>
</svg>'''


def _application(label: str, filename: str, fg: str, bg: str, accent: str) -> str:
    """A flat mock of a touchpoint. 4:3 so the 2x2 grid stays even."""
    w, h = 1200, 900
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <rect width="{w}" height="{h}" fill="{bg}"/>
  <rect x="60" y="60" width="{w-120}" height="{h-120}" rx="34" fill="none"
        stroke="{fg}" stroke-opacity="0.18" stroke-width="3" stroke-dasharray="16 12"/>
  <circle cx="{w/2}" cy="{h/2 - 96}" r="74" fill="none" stroke="{accent}" stroke-width="24"/>
  <rect x="{w/2 - 11}" y="{h/2 - 170}" width="22" height="148" rx="11" fill="{accent}"/>
  <text x="{w/2}" y="{h/2 + 74}" text-anchor="middle" fill="{fg}"
        font-family="Inter, Helvetica, Arial, sans-serif" font-size="56" font-weight="600"
        letter-spacing="-1.5">{escape(label)}</text>
  <text x="{w/2}" y="{h/2 + 136}" text-anchor="middle" fill="{fg}" opacity="0.55"
        font-family="Inter, Helvetica, Arial, sans-serif" font-size="27" font-weight="400">
    placeholder, replace with {escape(filename)}
  </text>
</svg>'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("brand_json")
    ap.add_argument("--force", action="store_true",
                    help="overwrite artwork that is already there")
    a = ap.parse_args()

    bj = Path(a.brand_json).expanduser().resolve()
    if not bj.is_file():
        print(f"no brand file at {bj}")
        return 1
    brand = json.loads(bj.read_text())
    root = bj.parent

    pal = brand.get("palette", {})
    canvas = pal.get("canvas", "#F4F3F1")
    ink = pal.get("ink", "#1F1F1F")
    dark = pal.get("groundDark", ink)
    on_dark = pal.get("inkOnDark", "#FFFFFC")
    accent = pal.get("accent", ink)
    word = brand.get("meta", {}).get("wordmark") or brand.get("meta", {}).get("name") or "Your Business"

    written, skipped = [], []

    def put(rel: str, body: str) -> None:
        p = root / rel
        if p.exists() and not a.force:
            skipped.append(rel)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        written.append(rel)

    put("assets/logo/lockup-primary.svg", _lockup(word, ink, "light ground"))
    put("assets/logo/lockup-reversed.svg", _lockup(word, on_dark, "dark ground"))
    put("assets/logo/mark-primary.svg", _mark(ink))
    put("assets/logo/mark-reversed.svg", _mark(on_dark))

    for name, label in (("website.png", "Website"), ("social.png", "Social"),
                        ("card.png", "Business card"), ("signage.png", "Signage")):
        # written as SVG under a .png name would break the mime sniff, so keep .svg
        put(f"assets/applications/{Path(name).stem}.svg",
            _application(label, name, ink, canvas, accent))

    for rel in written:
        print(f"  wrote   {rel}")
    for rel in skipped:
        print(f"  kept    {rel} (already there, --force to replace)")
    print(f"\n{len(written)} placeholder(s) written, {len(skipped)} kept.")
    if written:
        print("Point brand.json at the .svg names, render, then replace them one at a time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
