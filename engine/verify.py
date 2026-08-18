"""The gate. Run it before anything ships.

    python3 -m engine.verify                 # every brand in brands/
    python3 -m engine.verify brands/your-brand     # one

Exits non-zero on any failure. Each check answers a way this has actually gone
wrong: a hex that renders as black, a logo path that silently disappeared, a
caption nobody can read, a person's name in a file that goes to a stranger.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

from . import plan as plan_mod
from . import pages as pages_mod
from .theme import PALETTE_DEFAULTS, SHAPE_DEFAULTS, font_specs
from . import fonts as fonts_mod

ROOT = Path(__file__).resolve().parent.parent
HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Stored encoded so this checker does not itself carry the strings it bans.
_BANNED = base64.b64decode(
    "bHVrZUAsbHVrZS5oZWthLEx1a2UgSGVrYSxAbHVrZXNlbHIsQGx1a2VoZWthLE1yLWhla2EsKzYxLH"
    "NlbHJncm91cC5jb20uYXUsaGVrei5jb20uYXU="
).decode().split(",")
_ESCAPE_HATCHES = re.compile(
    r"ask (a |the )?(human|someone)|reach out|if you get stuck|contact us|message us",
    re.I)


class Result:
    """Three severities, because they mean genuinely different things.

    A *failure* is this tool getting it wrong: a broken path, a plan that will
    not build, a PDF that does not match its plan. A *finding* is the brand
    getting it wrong: a real property of colours somebody else locked. Findings
    are reported, never silently fixed, because quietly recolouring a locked
    brand is a worse outcome than telling its owner the truth.
    """

    def __init__(self) -> None:
        self.fail: list[str] = []
        self.warn: list[str] = []
        self.findings: list[str] = []
        self.checks = 0

    def check(self, ok: bool, message: str, *, warn: bool = False,
              finding: bool = False) -> bool:
        self.checks += 1
        if not ok:
            bucket = self.findings if finding else (self.warn if warn else self.fail)
            bucket.append(message)
        return ok


def _contrast(a: str, b: str) -> float:
    la, lb = pages_mod._luminance(a), pages_mod._luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + .05) / (lo + .05)


def check_brand(path: Path, r: Result) -> None:
    label = path.name
    try:
        brand = json.loads((path / "brand.json").read_text(encoding="utf-8"))
    except Exception as exc:
        r.check(False, f"{label}: brand.json will not parse ({exc})")
        return

    # --- shape of the file ------------------------------------------------
    for key in ("meta", "palette", "type", "sections"):
        r.check(key in brand, f"{label}: brand.json is missing '{key}'")
    meta = brand.get("meta", {})
    for key in ("name", "wordmark", "year"):
        r.check(key in meta, f"{label}: meta is missing '{key}'")

    palette = {**PALETTE_DEFAULTS, **brand.get("palette", {})}

    # --- every colour is a real colour ------------------------------------
    for name, hexv in brand.get("palette", {}).items():
        r.check(bool(HEX.match(hexv)), f"{label}: palette.{name} is not a hex ({hexv})")
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            for c in page.get("colours", []):
                # A colour entry either names a palette key, which is the way that
                # cannot drift, or states its own hex for a value the palette does
                # not carry. Anything else is a page that will not build.
                tok = c.get("token")
                if tok is not None:
                    r.check(tok in palette,
                            f"{label}: colour '{c.get('name')}' names token '{tok}', "
                            f"which is not in the palette")
                    continue
                if "hex" not in c:
                    r.check(False,
                            f"{label}: colour '{c.get('name')}' has neither a 'token' "
                            f"naming a palette key nor a literal 'hex'")
                    continue
                r.check(bool(HEX.match(c["hex"])),
                        f"{label}: colour '{c.get('name')}' is not a hex ({c['hex']})")

    # --- text a person can actually read ----------------------------------
    pairs = [("ink on canvas", palette["ink"], palette["canvas"]),
             ("ink on card", palette["ink"], palette["surface"]),
             ("muted ink on canvas", palette["inkMuted"], palette["canvas"]),
             ("ink on dark", palette["inkOnDark"], palette["groundDark"]),
             ("ink on accent", palette["inkOnAccent"], palette["accent"])]
    for name, fg, bg in pairs:
        ratio = _contrast(fg, bg)
        if ratio >= 4.5:
            r.check(True, "")
            continue
        # 3:1 clears AA for large text only, which is a different sentence to
        # "this pairing fails", and the difference decides whether it can carry
        # a caption or only a headline.
        large_only = ratio >= 3.0
        detail = ("clears AA for large text only, so it must not carry body or "
                  "caption sizes" if large_only else "fails AA at every size")
        r.check(False, f"{label}: {name} ({fg} on {bg}) is {ratio:.2f}:1 — {detail}",
                finding=True)

    # --- the page plan builds and every asset exists -----------------------
    try:
        plan = plan_mod.build(brand)
    except Exception as exc:
        r.check(False, f"{label}: page plan will not build ({exc})")
        return
    r.check(len(plan) >= 4, f"{label}: only {len(plan)} pages, that is not a document")

    unknown = sorted({p["kind"] for p in plan} - set(pages_mod.RENDERERS))
    r.check(not unknown,
            f"{label}: page kinds that cannot render: {', '.join(unknown)} — known kinds are "
            f"{', '.join(sorted(pages_mod.RENDERERS))}")

    missing = []
    for page in plan:
        for key in ("src", "mark"):
            if page.get(key):
                missing += _missing(page[key], path)
        for m in page.get("marks", []):
            missing += _missing(m["src"], path)
        for c in page.get("cells", []):
            if c.get("src"):
                missing += _missing(c["src"], path)
        for i in page.get("items", []):
            if isinstance(i, dict) and i.get("src"):
                missing += _missing(i["src"], path)
        for reg in page.get("registers", []):
            missing += _missing(reg["src"], path)
    for key in ("coverMark", "boardMark"):
        if meta.get(key):
            missing += _missing(meta[key], path)
    r.check(not missing, f"{label}: missing assets: {', '.join(sorted(set(missing)))}")

    # --- radii stay on the declared scale ----------------------------------
    shape = {**SHAPE_DEFAULTS, **brand.get("shape", {})}
    allowed = {shape["radiusField"], shape["radiusCard"], shape["radiusPill"]}
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            for item in page.get("items", []):
                if isinstance(item, dict) and item.get("kind") == "radii":
                    off = [v for v, _ in item["values"] if v not in allowed]
                    r.check(not off,
                            f"{label}: radii page shows {off}, which are not on the scale "
                            f"{sorted(allowed)}")

    # --- fonts resolve without a network -----------------------------------
    for spec in font_specs(brand):
        cached = fonts_mod._cached(spec["family"], spec.get("variable", False))
        r.check(cached is not None or bool(spec.get("file")),
                f"{label}: {spec['family']} is not cached in assets/fonts, so this build "
                f"needs the network", warn=True)


def _missing(src: str, root: Path) -> list[str]:
    p = Path(src)
    if not p.is_absolute():
        p = root / p
    return [] if p.exists() else [src]


def check_output(path: Path, r: Result, out_root: Path | None = None) -> None:
    """A PDF that exists is not a PDF that is right."""
    slug = path.name
    # meta.slug names the output files; the folder name is where the gate looks.
    # When they disagree the render lands somewhere else and this check happily
    # validates whatever an earlier run left behind, which is a stale deck the
    # gate has blessed. Catch it before reading a single PDF.
    try:
        declared = json.loads((path / "brand.json").read_text(encoding="utf-8")) \
            .get("meta", {}).get("slug")
    except Exception:
        declared = None
    if not r.check(declared == slug,
                   f"{slug}: meta.slug is {declared!r} but the folder is {slug!r}. "
                   f"They must match, or the render lands in out/{declared} while this "
                   f"check reads out/{slug} and passes on an older build."):
        return
    out = (out_root / slug) if out_root else (ROOT / "out" / slug)
    if not out.exists():
        r.check(False, f"{slug}: nothing rendered in {out}. Run "
                       f"'python3 -m engine.render {path.as_posix()}/brand.json' first")
        return
    try:
        from pypdf import PdfReader
    except ImportError:
        r.check(False, "pypdf not installed, PDFs not read back", warn=True)
        return

    brand = json.loads((path / "brand.json").read_text(encoding="utf-8"))
    expect = len(plan_mod.build(brand))
    deck = out / f"{slug}-brand-presentation.pdf"
    if r.check(deck.exists(), f"{slug}: no deck PDF at {deck.name}"):
        got = len(PdfReader(str(deck)).pages)
        r.check(got == expect, f"{slug}: deck has {got} pages, the plan says {expect}")
        box = PdfReader(str(deck)).pages[0].mediabox
        r.check(abs(float(box.width) - 1440) < 2 and abs(float(box.height) - 810) < 2,
                f"{slug}: deck page is {float(box.width):.0f}x{float(box.height):.0f}pt, "
                f"expected 1440x810pt (1920x1080 CSS px)")
    board = out / f"{slug}-brand-board.pdf"
    if r.check(board.exists(), f"{slug}: no board PDF at {board.name}"):
        r.check(len(PdfReader(str(board)).pages) == 1,
                f"{slug}: the board must be one continuous page")


def check_firewall(r: Result) -> None:
    """Nothing that ships carries a person, and nothing sends the reader to one."""
    targets = list((ROOT / "brands").rglob("*.json")) + \
              list((ROOT / "out").rglob("SKILL.md")) + \
              [p for p in ROOT.glob("*.md")] + \
              [p for p in (ROOT / "docs").glob("*.md")]
    for f in targets:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits = [b for b in _BANNED if b.lower() in text.lower()]
        r.check(not hits, f"{f.relative_to(ROOT)}: contains {hits}")
        m = _ESCAPE_HATCHES.search(text)
        r.check(m is None,
                f"{f.relative_to(ROOT)}: sends the reader to a person ('{m.group(0) if m else ''}')")


# Folder names that either declare non-public intent, or say outright that the
# folder holds pictures of people. Matched as whole path segments, never as
# substrings, because "ig-portrait" is an aspect ratio and "…replace-people…"
# is a headline someone wrote.
_PRIVATE_INTENT = re.compile(
    r"^(.*[-_])?(internal|private|confidential|unreleased|nda|do[-_]?not[-_]?publish)"
    r"([-_].*)?$", re.I)
_PEOPLE_FOLDER = re.compile(
    r"^(portraits?|headshots?|staff|team[-_ ]?photos?|faces|crew)$", re.I)

# Rendered output, not filed source material. The engine drew these.
_SKIP_TREES = {"generated"}


def check_people(brands: list[Path], r: Result) -> None:
    """Catch folders that say they are not for publishing, before the page reads them.

    The underscore rule is a good guard and it is not enough on its own, because
    it depends on whoever filed the image naming the folder with a leading
    underscore. A folder called `internal-only-canvas` reads as private to any
    human and is wide open to the guard, which is how real portraits reached a
    public URL twice.

    Be honest about the ceiling. This checks names, so it catches a folder that
    declares itself, and it cannot catch a portrait filed as `8.png` inside a
    general folder. Nothing name-based can. That case is what the review pass is
    for, and no gate replaces somebody looking at the pictures.
    """
    for b in brands:
        assets = b / "assets"
        if not assets.is_dir():
            continue
        for d in assets.rglob("*"):
            if not d.is_dir():
                continue
            parts = d.relative_to(b).parts
            if any(x.startswith("_") for x in parts) or _SKIP_TREES & set(parts):
                continue
            name = d.name
            if _PRIVATE_INTENT.match(name) or _PEOPLE_FOLDER.match(name):
                has_images = any(f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
                                 for f in d.iterdir() if f.is_file())
                r.check(not has_images,
                        f"{b.name}: {d.relative_to(b).as_posix()}/ names itself as not for "
                        f"publishing but sits in a publishable tree. Rename it with a leading "
                        f"underscore, or move it under _private/.")


def write_findings(brands: list[Path], r: Result) -> None:
    """Findings belong to the brand's owner, so they get written down."""
    if not r.findings:
        return
    for b in brands:
        mine = [f for f in r.findings if f.startswith(f"{b.name}:")]
        if not mine:
            continue
        out = ROOT / "out" / b.name
        out.mkdir(parents=True, exist_ok=True)
        lines = ["# Findings", "",
                 "Properties of this brand's own values, measured. Nothing here was",
                 "changed. Each one is the brand owner's call.", ""]
        lines += [f"- {f.split(': ', 1)[1]}" for f in mine]
        (out / "FINDINGS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    out_root = None
    if "--out" in args:
        i = args.index("--out")
        out_root = Path(args[i + 1])
        del args[i:i + 2]
    if args:
        # Accept either the folder or the brand.json inside it. The three
        # commands sit next to each other in the docs and two of them take a
        # file, so this asymmetry only ever produced a confusing parse error.
        brands = [Path(a).parent if Path(a).name == "brand.json" else Path(a) for a in args]
    else:
        brands = sorted(p for p in (ROOT / "brands").iterdir()
                        if p.is_dir() and not p.name.startswith("_") and (p / "brand.json").exists())

    r = Result()
    for b in brands:
        check_brand(b, r)
        check_output(b, r, out_root)
    check_firewall(r)
    check_people(brands, r)
    write_findings(brands, r)

    for w in r.warn:
        print(f"  warn     {w}")
    for f in r.findings:
        print(f"  finding  {f}")
    for f in r.fail:
        print(f"  FAIL     {f}")
    print(f"\n{r.checks} checks, {len(r.fail)} failed, {len(r.findings)} findings, "
          f"{len(r.warn)} warnings across {len(brands)} brand(s)")
    if r.findings:
        print("Findings are properties of the brand, not build errors. They are "
              "written to out/<brand>/FINDINGS.md and are the owner's call.")
    if r.fail or (strict and r.findings):
        print("VERIFY FAILED")
        return 1
    print("VERIFY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
