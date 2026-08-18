"""brand.json -> a Claude skill that knows the brand.

The PDFs are for people. This is for the machine: a skill folder that drops into
`~/.claude/skills/` so every future build in that account starts from the real
values instead of a screenshot and a guess.

    python3 -m engine.emit_skill brands/your-brand/brand.json --out out/your-brand

Writes `<slug>-brand/` containing SKILL.md, tokens.css, tokens.json, the source
brand.json and a copy of the logo files, with relative paths that survive the
folder being moved.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .theme import PALETTE_DEFAULTS, SHAPE_DEFAULTS, variables

def _scale(brand: dict) -> list[dict]:
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") == "typescale":
                return page.get("scale", [])
    return []


def _tracking_note(brand: dict) -> str | None:
    """State the brand's real tracking, or say nothing.

    A generated law that contradicts the generated table two screens below it is
    worse than no law, and that is exactly what a hard-coded note produces on a
    brand whose scale is not the one it was written from.
    """
    scale = _scale(brand)
    seen: dict[str, list[int]] = {}
    for s in scale:
        t = s.get("tracking")
        if t:
            seen.setdefault(t, []).append(s["px"])
    if not seen:
        return None
    parts = []
    for track, sizes in sorted(seen.items(), key=lambda kv: -max(kv[1])):
        lo, hi = min(sizes), max(sizes)
        span = f"{lo}px" if lo == hi else f"{lo} to {hi}px"
        parts.append(f"`{track}` at {span}")
    return ", ".join(parts)


def _laws(brand: dict) -> list[str]:
    """The rules a model has to hold to keep work on-brand.

    Derived from the brand's own values, so they cannot drift from the tokens
    sitting beside them. Anything the brand has not declared is either omitted
    or labelled as this document's own choice, never presented as brand truth.
    """
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    s = {**SHAPE_DEFAULTS, **brand.get("shape", {})}
    t = brand.get("type", {})
    disp = t.get("display", {})
    body = t.get("body", {})

    laws = [
        f"The ground is `{p['canvas']}` and cards are `{p['surface']}`. "
        f"Never pure white unless one of those is pure white.",
        f"Ink is `{p['ink']}`, muted ink is `{p['inkMuted']}`. Never `#000`.",
        f"One accent, `{p['accent']}`. If a second accent appears, remove it.",
    ]
    if disp:
        if disp.get("variable"):
            laws.append(
                f"{disp['family']} display runs the **variable axis at "
                f"{disp.get('weight')}**, and the giant one-word display drops to "
                f"{disp.get('weightXL', disp.get('weight'))}. If it looks like a plain "
                f"static weight, the axis is not being driven.")
        else:
            laws.append(f"{disp['family']} for display at "
                        f"{disp.get('weight')}, {body.get('family', disp['family'])} for body "
                        f"at {body.get('weight')}.")
    track = _tracking_note(brand)
    if track:
        laws.append(f"Tracking is set per size: {track}. Nothing sits at default tracking.")

    if "shape" in brand:
        laws.append(f"Radii are {s['radiusField']}, {s['radiusCard']}, {s['radiusPill']} "
                    f"or a circle. Nothing else.")
    else:
        laws.append(f"No radius system is recorded for this brand. The documents use "
                    f"{s['radiusField']}, {s['radiusCard']} and {s['radiusPill']} for their own "
                    f"chrome. Lock a real set before quoting these as brand truth.")

    laws.append("No drop shadows. Depth comes from colour and radius.")
    return laws


def _rules_from_deck(brand: dict) -> list[str]:
    """Lift every `prose` page — those are the brand's own stated hard rules."""
    out = []
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") == "prose":
                out += page.get("items", [])
    return out


# Page geometry belongs to the document, not to the brand. Shipping it as a brand
# token tells a future session that 536px is something this business decided.
_LAYOUT_ONLY = {"margin", "safeTop", "gap", "captionWidth",
                "panelX", "panelWidth", "panelHeight"}


def tokens_json(brand: dict) -> dict:
    """Only what the brand declared. Nothing inherited, nothing invented."""
    shape = {k: v for k, v in brand.get("shape", {}).items() if k not in _LAYOUT_ONLY}
    out = {
        "$comment": f"{brand['meta']['name']} design tokens, generated from brand.json "
                    f"by brand-board. Every value here was declared by this brand. "
                    f"Consume this rather than retyping a hex.",
        "colour": dict(brand.get("palette", {})),
        "type": brand.get("type", {}),
    }
    if shape:
        out["shape"] = shape
    tracking = {}
    for s in _scale(brand):
        if s.get("tracking"):
            tracking[str(s["px"])] = s["tracking"]
    if tracking:
        out["tracking"] = tracking
    return out


_LAYOUT_VARS = ("--margin", "--safe-top", "--gap", "--caption-w",
                "--panel-x", "--panel-w", "--panel-h",
                "--label-on-accent", "--label-on-dark")


def tokens_css(brand: dict) -> str:
    """The brand's values as a drop-in stylesheet.

    The deck's own page geometry is stripped. A future session reading this file
    should not learn that 536px is something this business decided.
    """
    head = (f"/* {brand['meta']['name']} design tokens.\n"
            f"   Generated from brand.json by brand-board. Edit brand.json and\n"
            f"   regenerate, never hand-edit this file. */\n")
    body = variables(brand)
    body = body[body.index("{") + 1:body.rindex("}")]
    rows = [r for r in body.split(";") if r.strip()
            and not any(r.strip().startswith(v) for v in _LAYOUT_VARS)]
    return head + ":root {\n  " + ";\n  ".join(r.strip() for r in rows) + ";\n}\n"


def measured(brand: dict) -> list[str]:
    """What the gate measured about this brand, so it travels with the skill.

    The gate went to the trouble of finding these. A skill that hands a future
    session a muted ink without saying it was measured at 3.87:1 has thrown away
    the one thing the check was for.
    """
    from .pages import contrast
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    pairs = [("Ink on canvas", p["ink"], p["canvas"]),
             ("Muted ink on canvas", p["inkMuted"], p["canvas"]),
             ("Ink on card", p["ink"], p["surface"]),
             ("Light ink on the dark ground", p["inkOnDark"], p["groundDark"]),
             ("Ink on accent", p["inkOnAccent"], p["accent"])]
    out = []
    for name, fg, bg in pairs:
        ratio = contrast(fg, bg)
        if ratio >= 4.5:
            continue
        detail = ("clears AA for large text only, so it must not carry body or caption sizes"
                  if ratio >= 3.0 else "fails AA at every size, so it must not carry text")
        out.append(f"**{name}** (`{fg}` on `{bg}`) is **{ratio:.2f}:1**. It {detail}.")
    return out


def skill_md(brand: dict) -> str:
    m = brand["meta"]
    name = m["name"]
    slug = m.get("slug", name.lower().replace(" ", "-"))
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    t = brand.get("type", {})

    colour_rows = []
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") in ("colourStack", "colourRamp"):
                for c in page.get("colours", []):
                    colour_rows.append(f"| {c.get('name', '')} | `{c['hex'].upper()}` |")

    scale_rows = []
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") == "typescale":
                for s in page.get("scale", []):
                    scale_rows.append(f"| {s['role']} | {s['px']}px | `{s.get('tracking', '')}` |")

    story = []
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            if page.get("kind") == "overview":
                for b in page.get("blocks", []):
                    story.append(f"**{b['title']}.** {b['body']}")

    laws = "\n".join(f"{i}. {law}" for i, law in enumerate(_laws(brand), start=1))
    found = measured(brand)
    measured_block = ""
    if found:
        measured_block = ("## Measured\n\nThese are properties of the brand's own colours, "
                          "measured, not opinions. Nothing was changed to make them pass.\n\n"
                          + "\n".join(f"- {f}" for f in found) + "\n\n")
    rules = _rules_from_deck(brand)
    rules_block = ""
    if rules:
        rules_block = ("\n## The brand's own hard rules\n\n"
                       + "\n".join(f"- {r}" for r in rules) + "\n")

    faces = []
    for key in ("display", "body"):
        f = t.get(key)
        if f:
            w = f.get("weights") or [f.get("weight")]
            faces.append(f"- **{key.title()}** — {f['family']}, "
                         f"weight{'s' if len(w) > 1 else ''} {', '.join(str(x) for x in w)}"
                         + (" (variable axis)" if f.get("variable") else ""))

    return f"""---
name: {slug}-brand
description: Use when building, styling or reviewing anything for {name} — a page, post, deck, ad, screen, email or component — and it has to look like {name}. Carries the real colour, type, shape and logo rules, so nothing is eyeballed off a screenshot.
---

# {name} — brand

The values below are the brand, not an interpretation of it. Read this before
building. Do not work from memory of it: the numbers are specific, and
close-but-wrong is exactly what makes work look off-brand.

`tokens.css` is the drop-in for anything that renders HTML. `tokens.json` is the
same system machine-readable. Never retype a hex.

## The laws

{laws}
{rules_block}
## Colour

| Name | Hex |
|---|---|
{chr(10).join(colour_rows) if colour_rows else '| Accent | `' + p['accent'] + '` |'}

## Type

{chr(10).join(faces)}

{('| Role | Size | Tracking |' + chr(10) + '|---|---|---|' + chr(10) + chr(10).join(scale_rows)) if scale_rows else 'No type scale is recorded for this brand yet.'}

## What it is

{(chr(10) + chr(10)).join(story) if story else 'No positioning is recorded for this brand yet.'}

{measured_block}## Logo

Files sit in `assets/logo/`. Use the variant that matches the ground it lands on,
and never recolour, rotate, stretch or add an effect to the artwork.

## Checking your work

Look at the render, never the source.

- Ground and card colours match the table above.
- Nothing sits at default tracking.
- Every radius is on the scale.
- No drop shadow anywhere.
- One accent only.

The full argument for every value, with the artwork, is in the brand
presentation and the brand board that were generated alongside this skill.
"""


def emit(brand: dict, root: Path, out: Path) -> Path:
    slug = brand["meta"].get("slug", brand["meta"]["name"].lower().replace(" ", "-"))
    dest = out / f"{slug}-brand"
    (dest / "assets" / "logo").mkdir(parents=True, exist_ok=True)

    (dest / "SKILL.md").write_text(skill_md(brand), encoding="utf-8")
    (dest / "tokens.css").write_text(tokens_css(brand), encoding="utf-8")
    (dest / "tokens.json").write_text(
        json.dumps(tokens_json(brand), indent=2) + "\n", encoding="utf-8")
    (dest / "brand.json").write_text(
        json.dumps(brand, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            srcs = []
            if page.get("kind") == "lockup":
                srcs = [page["src"]]
            elif page.get("kind") == "marks":
                srcs = [m["src"] for m in page["marks"]]
            for s in srcs:
                f = root / s
                if f.exists():
                    shutil.copy2(f, dest / "assets" / "logo" / f.name)
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Emit a Claude skill from a brand file.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path,
                    help="defaults to out/<slug>")
    args = ap.parse_args(argv)

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    slug = brand["meta"].get("slug") or args.brand.parent.name
    root = Path(__file__).resolve().parent.parent
    dest = emit(brand, args.brand.parent, args.out or (root / "out" / slug))
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    print(f"skill -> {dest}")
    for f in files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
