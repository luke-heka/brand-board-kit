"""Render a brand file to a deck (PDF + PNGs) and a brand board.

    python3 -m engine.render brands/your-brand/brand.json --out out/your-brand

Chromium via Playwright, the same engine the rest of the kit renders with.
Fonts are embedded, images are inlined, so the HTML that gets printed is one
self-contained file that renders identically with the network off.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import board as board_mod
from . import pages as pages_mod
from . import plan as plan_mod
from . import theme as theme_mod

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

PAGE_W, PAGE_H = 1920, 1080

DOC_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title><style>
@page {{ size: {w}px {h}px; margin: 0; }}
html, body {{ margin:0; padding:0; background:{canvas}; }}
{css}
</style></head><body>{body}</body></html>"""


def load_brand(path: Path) -> tuple[dict, Path]:
    brand = json.loads(path.read_text(encoding="utf-8"))
    return brand, path.parent


def deck_html(brand: dict, root: Path, doc: dict | None = None) -> tuple[str, int]:
    css = theme_mod.stylesheet(brand, [TEMPLATES / "deck.css"], root=root)
    ctx = plan_mod.context(brand, root)
    if doc:
        ctx = {**ctx, "meta": {**ctx["meta"], **{k: v for k, v in doc.items()
                                                  if k not in ("sections", "slug")}}}
    plan = plan_mod.build(brand, doc.get("sections") if doc else None,
                          dividers=(doc or {}).get("dividers", True),
                          contents=(doc or {}).get("contents", True))
    body = "".join(pages_mod.render(p, ctx, i) for i, p in enumerate(plan, start=1))
    return DOC_HEAD.format(
        title=f'{brand["meta"]["name"]} — {brand["meta"].get("document", "Brand Guideline")}',
        w=PAGE_W, h=PAGE_H, css=css, body=body,
        canvas=ctx["palette"]["canvas"]), len(plan)


def board_html(brand: dict, root: Path) -> tuple[str, int, int]:
    css = theme_mod.stylesheet(brand, [TEMPLATES / "board.css"], root=root)
    body, w, h = board_mod.build(brand, root)
    palette = plan_mod.context(brand, root)["palette"]
    html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{brand["meta"]["name"]} — Brand Board</title><style>'
            f'@page {{ size: {w}px {h}px; margin: 0; }}'
            f'html,body{{margin:0;padding:0;background:{palette["canvas"]};}}'
            f'{css}</style></head><body>{body}</body></html>')
    return html, w, h


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        sys.exit("Playwright is not installed. From this folder run:\n"
                 "  python3 -m venv .venv && source .venv/bin/activate\n"
                 "  pip install playwright pypdf && playwright install chromium")
    return sync_playwright()


def render(html: str, out_stem: Path, w: int, h: int, *, pngs: bool, pdf: bool,
           auto_height: bool = False) -> tuple[list[Path], int]:
    """Render one document. Returns the files written and the true page height.

    `auto_height` measures the laid-out document and prints at that exact
    height, which is what makes the board one continuous page instead of an
    arbitrary canvas with a band of dead space at the foot.
    """
    written: list[Path] = []
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    html_path = out_stem.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    written.append(html_path)

    with _browser() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(400)

        if auto_height:
            h = int(page.evaluate(
                "Math.ceil(document.documentElement.getBoundingClientRect().height)"))
            page.add_style_tag(content=f"@page{{size:{w}px {h}px;margin:0}}")
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(200)

        if pdf:
            page.emulate_media(media="screen")
            pdf_path = out_stem.with_suffix(".pdf")
            page.pdf(path=str(pdf_path), width=f"{w}px", height=f"{h}px",
                     print_background=True, prefer_css_page_size=True,
                     margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            written.append(pdf_path)

        if pngs:
            sections = page.query_selector_all("section.page, section.board")
            targets = sections or [page.query_selector("body")]
            for i, el in enumerate(targets, start=1):
                shot = out_stem.parent / f"{out_stem.name}-{i:02d}.png"
                el.screenshot(path=str(shot))
                written.append(shot)

        browser.close()
    return written, h


def verify_pdf(path: Path, expect_pages: int, w: int, h: int) -> list[str]:
    """Read the written PDF back. A file that exists is not proof it is right."""
    problems = []
    try:
        from pypdf import PdfReader
    except ImportError:
        return ["pypdf not installed — PDF not verified (pip3 install pypdf)"]
    reader = PdfReader(str(path))
    if len(reader.pages) != expect_pages:
        problems.append(f"{path.name}: {len(reader.pages)} pages, expected {expect_pages}")
    box = reader.pages[0].mediabox
    got_w, got_h = float(box.width), float(box.height)
    # Chromium prints CSS px as pt at 0.75 scale.
    want_w, want_h = w * 0.75, h * 0.75
    if abs(got_w - want_w) > 2 or abs(got_h - want_h) > 2:
        problems.append(f"{path.name}: page is {got_w:.0f}x{got_h:.0f}pt, expected {want_w:.0f}x{want_h:.0f}pt")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render a brand file to a deck and a board.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path,
                    help="defaults to out/<slug>, which is where verify looks")
    ap.add_argument("--only", choices=["deck", "board"], help="render just one artefact")
    ap.add_argument("--no-png", action="store_true", help="PDF and HTML only")
    args = ap.parse_args(argv)

    brand, root = load_brand(args.brand)
    slug = brand["meta"].get("slug") or args.brand.parent.name
    # Default rather than require. verify only ever reads out/<slug>, so a
    # required flag pointing anywhere else silently disabled every PDF check.
    out = args.out or (ROOT / "out" / slug)
    out.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    made: list[Path] = []

    if args.only != "board":
        # The primary document keeps the canonical filename so the gate, the
        # site and every existing link still resolve. Extras sit beside it.
        docs = brand.get("documents") or [None]
        for i, doc in enumerate(docs):
            html, count = deck_html(brand, root, doc)
            name = (f"{slug}-brand-presentation" if i == 0
                    else f"{slug}-{doc.get('slug', f'document-{i}')}")
            stem = out / name
            files, _ = render(html, stem, PAGE_W, PAGE_H, pngs=not args.no_png, pdf=True)
            made += files
            problems += verify_pdf(stem.with_suffix(".pdf"), count, PAGE_W, PAGE_H)
            label = (doc or {}).get("document", brand["meta"].get("document", "Brand Guideline"))
            print(f"deck   {count} pages  {label} -> {stem.with_suffix('.pdf')}")

    if args.only != "deck":
        html, w, h = board_html(brand, root)
        stem = out / f"{slug}-brand-board"
        files, true_h = render(html, stem, w, h, pngs=not args.no_png, pdf=True,
                               auto_height=True)
        made += files
        problems += verify_pdf(stem.with_suffix(".pdf"), 1, w, true_h)
        print(f"board  {w}x{true_h} -> {stem.with_suffix('.pdf')}")

    for p in problems:
        print(f"  ! {p}", file=sys.stderr)
    print(f"{len(made)} files written to {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
