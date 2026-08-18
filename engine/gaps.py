"""The completeness layer: what a finished brand has, and what this one is missing.

    python3 -m engine.gaps brands/<slug>/brand.json           # print the report
    python3 -m engine.gaps brands/<slug>/brand.json --write    # also write out/<slug>/PENDING.md

A batch of generated assets reads as a finished brand. It usually is not. Nobody
handed a folder of PNGs can tell that the logo has no dark-ground version, that
every asset is type-only because no photograph exists, or that mail going out in
this brand's name has no signature. This module is the thing that says so.

Nothing here fabricates. A gap is reported and left open, because a placeholder
that looks finished is worse than an empty slot that says what it needs. Every
gap carries the action that closes it, written for somebody who does not open a
design tool.

The expectations are read off the engine itself wherever possible — the palette
keys come from `theme.PALETTE_DEFAULTS`, the asset families come from the asset
template registry — so adding a capability to the engine raises the bar here
without anybody editing a list.

--------------------------------------------------------------------------------
THE CONTRACT — `gaps(brand, root)`
--------------------------------------------------------------------------------

    from .gaps import gaps
    for g in gaps(brand, brand_dir):
        ...render one Pending card...

`gaps()` returns ONLY what is missing, in section order, each one a plain dict.
Every dict has exactly these keys, always present, always a string except `have`:

    id       str   stable dotted identifier, e.g. "logo.dark". Safe as an anchor,
                   a CSS class or a dict key. Never changes once shipped.
    section  str   which part of a brand this belongs to: one of
                   logo, colour, type, imagery, voice, documents, assets.
    group    str   the human name of that section, e.g. "Logo". Card heading.
    title    str   short human title of the missing thing, e.g. "Dark-ground logo".
                   Two to four words. Card title.
    why      str   one plain sentence, why its absence costs something real.
    fix      str   one action a non-designer can take that closes it.
    detail   str   what was actually found, or "" when there is nothing to add.
                   Never load-bearing — safe to ignore when rendering.
    have     bool  always False in this list. Present so the same record shape
                   works for the satisfied ones too.

The list may be empty. It is never None. The order is stable across runs.

`audit(brand, root)` returns the whole picture when more than the gaps is
wanted — the satisfied expectations and the score:

    {"slug": str, "name": str,
     "expectations": [record, ...],   # everything, in section order
     "present":      [record, ...],   # have is True
     "missing":      [record, ...],   # have is False, identical to gaps()
     "score": {"have": int, "total": int, "pct": int}}

The score is a flat count of expectations met over expectations checked. It is
not weighted, because a weighting is an opinion and this number has to survive
being read by someone who did not write it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .theme import PALETTE_DEFAULTS

ROOT = Path(__file__).resolve().parent.parent

SECTION_TITLES = {
    "logo": "Logo",
    "colour": "Colour",
    "type": "Type",
    "imagery": "Imagery",
    "voice": "Voice",
    "documents": "Documents",
    "assets": "Assets",
}

# The palette keys split three ways. Names come from the engine's own defaults,
# so a colour added to the system is checked here without touching this file.
CORE_COLOURS = {
    "canvas": ("Canvas colour",
               "The ground every page and post sits on falls back to an off-white that "
               "belongs to no brand."),
    "ink": ("Ink colour",
            "Body text falls back to a near-black that belongs to no brand."),
    "inkMuted": ("Muted ink",
                 "Captions and labels have no quieter colour to sit in, so everything on "
                 "the page shouts at the same volume."),
    "accent": ("Accent colour",
               "Nothing carries buttons, links and emphasis, so there is no colour anyone "
               "would recognise this brand by."),
    "accentPressed": ("Pressed accent",
                      "Buttons have no darker state, so pressing one looks like nothing "
                      "happened."),
}
GROUND_COLOURS = ("groundDark", "inkOnDark", "inkOnAccent")
SECONDARY_MINIMUM = 4


# --------------------------------------------------------------------------
# reading the brand file
# --------------------------------------------------------------------------

def _all_sections(brand: dict) -> list[dict]:
    """Every section this brand declares, across the deck and every document.

    A brand can carry its pages at the top level, inside `documents`, or both.
    Credit is given wherever the thing actually is.
    """
    out = list(brand.get("sections") or [])
    for doc in brand.get("documents") or []:
        out += list(doc.get("sections") or [])
    return out


def _pages(brand: dict, kind: str) -> list[dict]:
    return [p for sec in _all_sections(brand)
            for p in (sec.get("pages") or [])
            if isinstance(p, dict) and p.get("kind") == kind]


def _exists(root: Path, src: str | None) -> bool:
    if not src:
        return False
    p = Path(src)
    return (p if p.is_absolute() else root / p).exists()


def _asset_families(brand: dict, root: Path) -> tuple[dict, dict, set]:
    """What asset families this brand declares, and which have real files.

    Returns (declared, rendered, expected) where declared and rendered map a
    family name -> count, and expected is every family the engine can build.
    Families are the template groups collapsed one level: `social-posts` and
    `social-profile` are both social, `ads-display` is ads.
    """
    try:
        from .templates_assets import REGISTRY
    except Exception:                                  # pragma: no cover
        REGISTRY = {}

    def family(group: str) -> str:
        return group.split("-")[0]

    expected = {family(spec["group"]) for spec in REGISTRY.values()}
    if not expected:                                   # pragma: no cover
        expected = {"social", "ads", "email", "print", "digital", "covers"}

    declared: dict[str, int] = {}
    for item in brand.get("assetSet") or []:
        spec = REGISTRY.get(item.get("template"))
        if spec:
            f = family(spec["group"])
            declared[f] = declared.get(f, 0) + 1

    rendered: dict[str, int] = {}
    gen = root / "assets" / "generated"
    if gen.is_dir():
        for d in sorted(gen.iterdir()):
            if not d.is_dir():
                continue
            n = len(list(d.glob("*.png")))
            if n:
                f = family(d.name)
                rendered[f] = rendered.get(f, 0) + n
    return declared, rendered, expected


def _signature(brand: dict, root: Path) -> tuple[bool, bool]:
    """(declared, pasteable) for the email signature.

    Pasteable means the HTML file exists, not only the picture of it — a
    signature that is only a PNG cannot be put into a mail client.
    """
    declared = any("signature" in str(a.get("template", ""))
                   for a in brand.get("assetSet") or [])
    html = list((root / "assets" / "generated").rglob("*signature*.html"))
    return declared, bool(html)


# --------------------------------------------------------------------------
# the expectations
# --------------------------------------------------------------------------

def _rec(id: str, section: str, title: str, why: str, fix: str,
         have: bool, detail: str = "") -> dict:
    return {"id": id, "section": section, "group": SECTION_TITLES[section],
            "title": title, "why": why, "fix": fix, "detail": detail,
            "have": bool(have)}


def _logo(brand: dict, root: Path) -> list[dict]:
    meta = brand.get("meta") or {}
    lockups = _pages(brand, "lockup")

    def ground_of(page: dict) -> str:
        g = (page.get("ground") or "light").lower()
        return "light" if g in ("light", "canvas", "paper") else g

    live = [p for p in lockups if _exists(root, p.get("src"))]
    by_ground = {}
    for p in live:
        by_ground.setdefault(ground_of(p), p)

    marks = [m for page in _pages(brand, "marks") for m in (page.get("marks") or [])
             if _exists(root, m.get("src"))]
    for key in ("coverMark", "boardMark"):
        if _exists(root, meta.get(key)):
            marks.append({"label": key, "src": meta[key]})

    declared, rendered, _ = _asset_families(brand, root)
    icon_names = {"favicon", "app-icon", "avatar"}
    icon_declared = any(a.get("template") in icon_names
                        for a in brand.get("assetSet") or [])
    icon_files = [p for p in (root / "assets" / "generated").rglob("*.png")
                  if p.stem in icon_names] if (root / "assets" / "generated").is_dir() else []

    def where(g: str) -> str:
        p = by_ground.get(g)
        return p.get("src", "") if p else ""

    return [
        _rec("logo.primary", "logo", "Primary lockup",
             "Without one, every document, deck and post has nothing to sign itself with.",
             "Put the main logo file in assets/logo/ and point a lockup page at it in "
             "brand.json.",
             "light" in by_ground, where("light")),
        _rec("logo.dark", "logo", "Dark-ground logo",
             "On a dark background the normal logo goes invisible, so half the assets "
             "cannot carry it.",
             "Save a version of the logo with the wordmark in the light colour, then add "
             "a lockup page with \"ground\": \"dark\".",
             "dark" in by_ground, where("dark")),
        _rec("logo.accent", "logo", "Accent-ground logo",
             "Anything set on the brand colour — a button, a banner, a story frame — has "
             "no logo that reads on it.",
             "Save a one-colour version of the logo, then add a lockup page with "
             "\"ground\": \"accent\".",
             "accent" in by_ground, where("accent")),
        _rec("logo.mark", "logo", "Standalone mark",
             "The full logo will not read at small sizes, so avatars and app icons have "
             "nothing to use.",
             "Save the symbol on its own, without the words, and list it on the marks "
             "page in brand.json.",
             bool(marks), ", ".join(sorted({m["src"] for m in marks}))),
        _rec("logo.favicon", "logo", "Favicon-sized mark",
             "Browser tabs, profile pictures and app tiles all need the mark cropped "
             "square, and a shrunken logo turns to mush there.",
             "Add the favicon and app-icon templates to assetSet in brand.json and run "
             "the asset build.",
             bool(icon_files) or icon_declared,
             ", ".join(sorted(p.name for p in icon_files))),
    ]


def _colour(brand: dict, root: Path) -> list[dict]:
    palette = brand.get("palette") or {}
    out = []
    for key, (title, why) in CORE_COLOURS.items():
        out.append(_rec(
            f"colour.{key.lower()}", "colour", title, why,
            f"Add \"{key}\" to the palette in brand.json as a hex value, for example "
            f"\"{PALETTE_DEFAULTS[key]}\".",
            key in palette, palette.get(key, "")))

    grounds = [k for k in GROUND_COLOURS if k in palette]
    out.append(_rec(
        "colour.grounds", "colour", "Dark-ground colours",
        "Dark sections and accent panels have no declared text colour, so text on them "
        "is a guess and can come out unreadable.",
        "Add \"groundDark\", \"inkOnDark\" and \"inkOnAccent\" to the palette: the dark "
        "background, and the text colour that sits on dark and on the accent.",
        len(grounds) == len(GROUND_COLOURS), ", ".join(grounds)))

    extra = [k for k in palette if k not in CORE_COLOURS and k not in GROUND_COLOURS]
    ramp = [c.get("name", "") for page in _pages(brand, "colourRamp")
            for c in (page.get("colours") or [])]
    secondary = len(extra) + len(ramp)
    out.append(_rec(
        "colour.secondary", "colour", "Secondary colours",
        "Three colours cannot build an interface — cards, borders, hovers and states all "
        "need somewhere to come from.",
        f"Add a colourRamp page to the colour section listing the working colours: card, "
        f"line, hover, and the states. {SECONDARY_MINIMUM} is the floor.",
        secondary >= SECONDARY_MINIMUM,
        f"{secondary} beyond the core" if secondary else ""))
    return out


def _type(brand: dict, root: Path) -> list[dict]:
    t = brand.get("type") or {}
    display, body = t.get("display") or {}, t.get("body") or {}

    def weighted(face: dict) -> bool:
        # A variable face carries every weight on one axis, so it needs no list.
        return bool(face) and (bool(face.get("variable")) or bool(face.get("weights")))

    scale = [s for page in _pages(brand, "typescale") for s in (page.get("scale") or [])]
    faces = [f for f in (display, body) if f]
    return [
        _rec("type.display", "type", "Display typeface",
             "Headlines have no face of their own, so every title falls back to the "
             "system font and the brand reads like a default.",
             "Add \"display\" under \"type\" in brand.json with a family name — any "
             "Google Fonts name works and is cached on first build.",
             bool(display.get("family")), display.get("family", "")),
        _rec("type.body", "type", "Body typeface",
             "Paragraphs have no declared face, so long text is set in whatever the "
             "device chooses.",
             "Add \"body\" under \"type\" in brand.json. It can name the same family as "
             "the display face — one family used well is a decision, not a gap.",
             bool(body.get("family")), body.get("family", "")),
        _rec("type.weights", "type", "Type weights",
             "Without declared weights the build has one thickness to work with, so a "
             "heading and a caption look the same.",
             "Add \"weights\" to each face, for example [400, 600] — the light one for "
             "body, the heavy one for headings.",
             bool(faces) and all(weighted(f) for f in faces),
             ", ".join(f"{f.get('family', '?')}: "
                       f"{'variable axis' if f.get('variable') else f.get('weights') or 'none'}"
                       for f in faces)),
        _rec("type.scale", "type", "Type scale",
             "With no sizes written down, every new page picks its own, and after three "
             "of them nothing lines up.",
             "Add a typescale page to the typography section listing each role and its "
             "pixel size, from the biggest headline down to the smallest label.",
             len(scale) >= 4, f"{len(scale)} sizes" if scale else ""),
    ]


def _imagery(brand: dict, root: Path) -> list[dict]:
    regs = [r for page in _pages(brand, "imagery") for r in (page.get("registers") or [])
            if _exists(root, r.get("src"))]
    names = ", ".join(r.get("name", Path(r["src"]).name) for r in regs)
    return [
        _rec("imagery.photography", "imagery", "Photography",
             "With no photograph, the deck and every social asset can only be type on a "
             "colour, which is why a brand ends up looking like a slide.",
             "Drop a JPG into assets/imagery/, then add it to the imagery section of "
             "brand.json as a register: the file, plus one line saying when to use it.",
             bool(regs), names),
        _rec("imagery.range", "imagery", "Second photograph",
             "One image used everywhere gets stale fast, and a light photograph cannot "
             "do the job of a dark one.",
             "Add a second image to assets/imagery/ that does a different job — a room "
             "with people in it if the first was a texture, and the reverse.",
             len(regs) >= 2, f"{len(regs)} register(s)" if regs else ""),
    ]


def _voice(brand: dict, root: Path) -> list[dict]:
    meta = brand.get("meta") or {}
    line = (meta.get("line") or "").strip()
    messages = [m for m in (meta.get("messages") or []) if str(m).strip()]
    return [
        _rec("voice.line", "voice", "Positioning line",
             "There is no single sentence saying what this brand is, so every person who "
             "writes for it invents a different one.",
             "Add \"line\" under \"meta\" in brand.json: one sentence, the thing about "
             "this brand that is easiest to get wrong.",
             bool(line), line[:80]),
        _rec("voice.messages", "voice", "Message set",
             "Generated assets pull their words from here. With none, every ad and post "
             "says the same thing.",
             "Add \"messages\" under \"meta\" in brand.json: a list of short lines the "
             "brand can lead with. Three is the floor, six is better.",
             len(messages) >= 3, f"{len(messages)} message(s)" if messages else ""),
    ]


def _documents(brand: dict, root: Path) -> list[dict]:
    docs = brand.get("documents") or []
    top = brand.get("sections") or []
    longest = max([len(d.get("sections") or []) for d in docs] + [len(top)])
    return [
        _rec("documents.guideline", "documents", "Full guideline",
             "There is no long document, so anyone working with this brand has to guess "
             "its rules instead of reading them.",
             "Fill out the sections in brand.json — logo, colour, type, imagery — until "
             "there are at least four. The guideline builds itself from them.",
             longest >= 4, f"{longest} sections"),
        _rec("documents.identity", "documents", "Short identity",
             "Nobody reads the long one before making a post. Without the short version "
             "the guideline sits unopened.",
             "Add a second entry to \"documents\" in brand.json with the essential "
             "sections only — logo, colour, type. It reuses the same pages.",
             len(docs) >= 2, f"{len(docs)} document(s)"),
    ]


def _assets(brand: dict, root: Path) -> list[dict]:
    declared, rendered, expected = _asset_families(brand, root)
    titles = {"social": "Social assets", "ads": "Ad creative", "email": "Email assets",
              "print": "Print assets", "digital": "Digital assets",
              "covers": "Cover artwork"}
    why = {
        "social": "Nothing is ready to post, so the first social asset gets built from "
                  "scratch under time pressure.",
        "ads": "Any paid campaign starts with no creative in any size.",
        "email": "Mail goes out with no header, no footer and nothing branded on it.",
        "print": "There is no card, letterhead or anything to hand to a person.",
        "digital": "The website and app have no icon, no favicon and no link preview "
                   "card.",
        "covers": "Courses, events and modules have no cover, so each one gets a "
                  "different look.",
    }
    slug = (brand.get("meta") or {}).get("slug") or root.name
    build_cmd = f"python3 -m engine.assets brands/{slug}/brand.json"
    out = []
    for fam in sorted(expected):
        n_rendered, n_declared = rendered.get(fam, 0), declared.get(fam, 0)
        if n_declared and not n_rendered:
            fix = (f"The templates are listed but the files were never made. Run "
                   f"{build_cmd}")
        else:
            fix = (f"Add the {fam} templates to \"assetSet\" in brand.json, then run "
                   f"{build_cmd}. Adding --list instead prints every template there is.")
        detail = f"{n_rendered} file(s)" if n_rendered else (
            f"{n_declared} declared, none built" if n_declared else "")
        out.append(_rec(
            f"assets.{fam}", "assets", titles.get(fam, f"{fam.title()} assets"),
            why.get(fam, f"Nothing is ready for {fam}."), fix, bool(n_rendered), detail))

    sig_declared, sig_html = _signature(brand, root)
    out.append(_rec(
        "assets.signature", "assets", "Email signature",
        "Every message sent in this brand's name goes out unsigned, which is the most "
        "seen surface a brand has and the one most often forgotten.",
        (f"The signature is listed but was never built. Run {build_cmd} — it writes an "
         f".html file that pastes straight into a mail client.")
        if sig_declared else
        f"Add the email-signature template to \"assetSet\" in brand.json and run "
        f"{build_cmd}. It produces real HTML, not only a picture.",
        sig_html, "pasteable HTML" if sig_html else ""))
    return out


_BUILDERS = (_logo, _colour, _type, _imagery, _voice, _documents, _assets)


# --------------------------------------------------------------------------
# the public shape
# --------------------------------------------------------------------------

def audit(brand: dict, root: Path) -> dict:
    """Everything: the expectations, what is met, what is not, and the score."""
    root = Path(root)
    expectations = [rec for build in _BUILDERS for rec in build(brand, root)]
    present = [e for e in expectations if e["have"]]
    missing = [e for e in expectations if not e["have"]]
    total = len(expectations)
    return {
        "slug": (brand.get("meta") or {}).get("slug", ""),
        "name": (brand.get("meta") or {}).get("name", "This brand"),
        "expectations": expectations,
        "present": present,
        "missing": missing,
        "score": {"have": len(present), "total": total,
                  "pct": round(100 * len(present) / total) if total else 0},
    }


def gaps(brand: dict, root: Path) -> list[dict]:
    """What this brand is missing. See THE CONTRACT at the top of this file."""
    return audit(brand, root)["missing"]


# --------------------------------------------------------------------------
# the two ways a person reads it
# --------------------------------------------------------------------------

def _by_section(records: list[dict]) -> list[tuple[str, list[dict]]]:
    order = list(SECTION_TITLES)
    return [(s, [r for r in records if r["section"] == s])
            for s in order if any(r["section"] == s for r in records)]


def report_text(brand: dict, root: Path) -> str:
    a = audit(brand, root)
    s = a["score"]
    lines = [f"{a['name']} — {s['have']} of {s['total']} things a complete brand has "
             f"({s['pct']}%)", ""]
    for section, recs in _by_section(a["expectations"]):
        have = [r for r in recs if r["have"]]
        lines.append(f"{SECTION_TITLES[section]:<11} {len(have)}/{len(recs)}")
        if have:
            lines.append("   have   " + ", ".join(r["title"] for r in have))
        for r in recs:
            if r["have"]:
                continue
            lines.append(f"   GAP    {r['title']} — {r['why']}")
            lines.append(f"          fix: {r['fix']}")
        lines.append("")
    if not a["missing"]:
        lines.append("Nothing pending. Every expectation is met.")
    else:
        lines.append(f"{len(a['missing'])} pending. Nothing above was filled in with a "
                     f"placeholder — a gap stays a gap until a real file closes it.")
    return "\n".join(lines) + "\n"


def pending_markdown(brand: dict, root: Path) -> str:
    a = audit(brand, root)
    s = a["score"]
    out = [f"# Pending — {a['name']}", "",
           f"This brand has **{s['have']} of the {s['total']} things** a complete brand "
           f"has ({s['pct']}%).", ""]
    out += ["Everything this brand does have was built from its real files. The items "
            "below were not built, because there is nothing to build them from. None of "
            "them was filled in with a stand-in: an empty slot that says what it needs "
            "is worth more than a placeholder that looks done.", ""] if a["missing"] else \
           ["Nothing is outstanding. Every item below was built from a real file, and "
            "none of it is a stand-in.", ""]

    if a["missing"]:
        out += ["## What is still missing", ""]
        for section, recs in _by_section(a["missing"]):
            out += [f"### {SECTION_TITLES[section]}", ""]
            for r in recs:
                out += [f"**{r['title']}.** {r['why']}", "",
                        f"To close it: {r['fix']}", ""]
    else:
        out += ["## What is still missing", "",
                "Nothing. Every item a complete brand needs is here.", ""]

    if a["present"]:
        out += ["## What is already here", ""]
        for section, recs in _by_section(a["present"]):
            out.append(f"- **{SECTION_TITLES[section]}** — "
                       + ", ".join(r["title"].lower() for r in recs))
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="What this brand is missing, and what would close each gap.")
    ap.add_argument("brand", type=Path, help="brands/<slug>/brand.json, or the folder")
    ap.add_argument("--write", action="store_true",
                    help="also write out/<slug>/PENDING.md")
    ap.add_argument("--out", type=Path, help="output root, defaults to out/")
    ap.add_argument("--json", action="store_true", help="print the audit as JSON")
    args = ap.parse_args(argv)

    path = args.brand / "brand.json" if args.brand.is_dir() else args.brand
    if not path.exists():
        print(f"no brand file at {path}", file=sys.stderr)
        return 1
    root = path.parent
    try:
        brand = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"{path} will not parse ({exc})", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(audit(brand, root), indent=2, ensure_ascii=False))
        return 0

    print(report_text(brand, root), end="")
    if args.write:
        slug = (brand.get("meta") or {}).get("slug") or root.name
        out = (args.out or ROOT / "out") / slug
        out.mkdir(parents=True, exist_ok=True)
        (out / "PENDING.md").write_text(pending_markdown(brand, root), encoding="utf-8")
        print(f"\nwritten: {out / 'PENDING.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
