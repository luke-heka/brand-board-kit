#!/usr/bin/env python3
"""Generate site/index.html for the brand-board showcase.

Values come from templates/deck.css + board.css + brands/*/brand.json.
Nothing is invented: palette, radii, tracking and weights are the system's own.
"""
import base64, json, shutil, subprocess, sys
from pathlib import Path

# Derived, not hard-coded: this script ships inside the skill and has to work
# wherever the skill is cloned to.
ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ASSETS = SITE / "assets"
OUT = ROOT / "out"

FONT = ROOT / "assets/fonts/Manrope-var.woff2"
b64 = base64.b64encode(FONT.read_bytes()).decode("ascii")

def size(p: Path) -> str:
    n = p.stat().st_size
    return f"{n/1_048_576:.1f} MB" if n >= 1_048_576 else f"{n/1024:.0f} KB"


def page_count(pdf: Path) -> int:
    """Read it off the file. A hard-coded count is a number that goes stale
    silently and makes the page lie about what it is linking to."""
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def preview(pdf: Path, dest: Path, dpi: int, page: int = 1) -> None:
    stem = dest.with_suffix("")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png",
                    str(pdf), str(stem)], check=True)
    # pdftoppm zero-pads the page suffix by page count, so the produced name is
    # -1.png or -01.png depending on the document. Glob rather than guess.
    made = sorted(stem.parent.glob(f"{stem.name}-*.png"))
    if not made:
        raise SystemExit(f"preview failed for {pdf.name}")
    made[0].replace(dest)
    for extra in made[1:]:
        extra.unlink()


# Sync from out/ every run. The generator used to read whatever happened to be
# sitting in site/assets, so a rebuilt PDF never reached the page and the file
# sizes printed beside the links belonged to an older document.
ASSETS.mkdir(parents=True, exist_ok=True)
BRANDS = []
def _order(d: Path) -> tuple:
    m = json.loads((d / "brand.json").read_text())["meta"]
    return (m.get("order", 100), m.get("name", d.name))

for brand_dir in sorted((p for p in (ROOT / "brands").iterdir()
                         if p.is_dir() and not p.name.startswith("_") and (p / "brand.json").exists()), key=_order):
    slug = brand_dir.name
    meta = json.loads((brand_dir / "brand.json").read_text())
    src_pres = OUT / slug / f"{slug}-brand-presentation.pdf"
    src_board = OUT / slug / f"{slug}-brand-board.pdf"
    src_hub = OUT / slug / f"{slug}-brand-hub.html"
    if not (src_pres.exists() and src_board.exists()):
        sys.exit(f"{slug}: render it first — missing {src_pres.name} or {src_board.name}")
    pres, board = ASSETS / src_pres.name, ASSETS / src_board.name
    shutil.copy2(src_pres, pres)
    shutil.copy2(src_board, board)
    hub = ASSETS / src_hub.name
    if src_hub.exists():
        shutil.copy2(src_hub, hub)
    preview(pres, ASSETS / f"{slug}-presentation-cover.png", 40, page=2)
    preview(board, ASSETS / f"{slug}-board-preview.png", 40)
    BRANDS.append({
        "name": meta["meta"]["name"],
        "line": meta["meta"].get("line", ""),
        "palette": meta["palette"],
        "pres": {"href": pres.name, "pages": f"{page_count(pres)} pages", "size": size(pres),
                 "thumb": f"{slug}-presentation-cover.png"},
        "board": {"href": board.name, "pages": "1 sheet", "size": size(board),
                  "thumb": f"{slug}-board-preview.png"},
        "hub": {"href": hub.name, "size": size(hub)} if src_hub.exists() else None,
    })

CHIP_KEYS = [("canvas", "Canvas"), ("surface", "Surface"), ("ink", "Ink"),
             ("accent", "Accent"), ("accentPressed", "Accent pressed")]


def chips(pal):
    out = []
    for key, label in CHIP_KEYS:
        hexv = pal.get(key)
        if not hexv:
            continue
        pale = int(hexv[1:3], 16) + int(hexv[3:5], 16) + int(hexv[5:7], 16) > 600
        cls = " chip--pale" if pale else ""
        out.append(f'<li class="chip{cls}" style="background:{hexv}">'
                   f'<span class="visually-hidden">{label} {hexv}</span></li>')
    return "\n            ".join(out)


def hub_row(b):
    h = b.get("hub")
    if not h:
        return ""
    return (f'<a class="btn btn--primary hub" href="assets/{h["href"]}">'
            f'<span class="btn__dot"></span>Open the asset hub'
            f'<span class="hub__meta">every file, click to download &middot; {h["size"]}</span></a>')


def doc_tile(d, brand, kind, label, blurb):
    return f"""<article class="doc">
              <a class="doc__shot doc__shot--{kind}" href="assets/{d['href']}">
                <img src="assets/{d['thumb']}" alt="{brand} {label.lower()}, first page" loading="lazy" width="1067" height="600">
              </a>
              <h4 class="doc__name">{label}</h4>
              <p class="doc__blurb">{blurb}</p>
              <p class="doc__meta">{d['pages']} &middot; PDF &middot; {d['size']}</p>
              <a class="btn btn--{'primary' if kind == 'deck' else 'secondary'}" href="assets/{d['href']}">
                <span class="btn__dot"></span>Open {label.lower()}
              </a>
            </article>"""


cards = []
for b in BRANDS:
    cards.append(f"""<section class="card" aria-labelledby="{b['name'].lower().replace(' ', '-')}-title">
          <header class="card__head">
            <h3 class="card__title" id="{b['name'].lower().replace(' ', '-')}-title">{b['name']}</h3>
            <p class="card__line">{b['line']}</p>
          </header>
          <ul class="chips" aria-label="{b['name']} core palette">
            {chips(b['palette'])}
          </ul>
          <div class="docs">
            {doc_tile(b['pres'], b['name'], 'deck', 'Presentation', 'The system page by page, each rule beside the reasoning behind it.')}
            {doc_tile(b['board'], b['name'], 'board', 'Board', 'The same system compressed onto one sheet you keep open while you work.')}
          </div>
          {hub_row(b)}
        </section>""")

STEPS = [
    ("01", "Read the presentation end to end, so the reasoning lands before the values do."),
    ("02", "Keep the board open beside the work as the single reference for colour, type and shape."),
    ("03", "Rebuild the same sections for your own brand, measuring real values instead of recalling them."),
]
steps = "\n            ".join(
    f'<li class="step"><span class="step__num">{n}</span><p class="step__text">{t}</p></li>'
    for n, t in STEPS)

HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brand boards</title>
<meta name="description" content="Two finished brand identities, each shipped as a presentation and a one-sheet board.">
<style>
@font-face{{font-family:'Manrope';src:url(data:font/woff2;base64,{b64}) format('woff2');font-weight:200 800;font-style:normal;font-display:block;}}

:root{{
  --canvas:#F7F5EF;
  --surface:#FFFFFA;
  --ink:#242424;
  --ink-muted:#616161;
  --accent:#6736E2;
  --accent-pressed:#5024C0;
  --ink-on-accent:#EEE8FF;
  --hairline:rgba(36,36,36,.10);
  --hairline-strong:rgba(36,36,36,.22);
  --radius-field:20px;
  --radius-card:30px;
  --radius-pill:40px;
}}

*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{-webkit-text-size-adjust:100%}}
body{{
  background:var(--canvas);
  color:var(--ink);
  font-family:'Manrope',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif;
  font-weight:600;
  font-variation-settings:'wght' 600;
  -webkit-font-smoothing:antialiased;
  overflow-x:hidden;
}}
img{{display:block;max-width:100%;height:auto}}
a{{color:inherit;text-decoration:none}}
ul,ol{{list-style:none}}

.visually-hidden{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}

.wrap{{width:100%;max-width:1180px;margin:0 auto;padding:0 20px}}
@media (min-width:760px){{.wrap{{padding:0 40px}}}}

/* --- hero ------------------------------------------------------------- */
.hero{{padding:72px 0 48px}}
@media (min-width:760px){{.hero{{padding:120px 0 72px}}}}
.eyebrow{{
  font-size:13px;letter-spacing:-.025em;color:var(--ink-muted);
  margin-bottom:22px;
}}
.hero__title{{
  font-size:clamp(40px,8.2vw,84px);line-height:1.02;letter-spacing:-.04em;
  font-weight:500;font-variation-settings:'wght' 500;
  max-width:14ch;
}}
.hero__lead{{
  margin-top:26px;max-width:60ch;
  font-size:clamp(17px,2.1vw,20px);line-height:1.5;letter-spacing:-.03em;
  color:var(--ink-muted);
}}

/* --- brand cards ------------------------------------------------------ */
.cards{{display:grid;gap:20px;padding-bottom:20px}}
@media (min-width:1000px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}

.card{{
  background:var(--surface);
  border:1px solid var(--hairline);
  border-radius:var(--radius-card);
  padding:26px 22px 30px;
}}
@media (min-width:760px){{.card{{padding:44px}}}}
.card__title{{
  font-size:clamp(34px,5vw,45px);line-height:1.1;letter-spacing:-.04em;
  font-weight:585;font-variation-settings:'wght' 585;
}}
.card__line{{
  margin-top:16px;max-width:48ch;
  font-size:17px;line-height:1.5;letter-spacing:-.03em;color:var(--ink-muted);
}}

.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:28px 0 30px}}
.chip{{
  width:46px;height:42px;border-radius:var(--radius-field);flex:0 0 auto;
}}
@media (min-width:560px){{.chips{{gap:10px}}.chip{{width:52px;height:44px}}}}
.chip--pale{{border:1px solid var(--hairline)}}

/* --- document tiles --------------------------------------------------- */
.docs{{display:grid;gap:20px}}
@media (min-width:560px){{.docs{{grid-template-columns:repeat(2,1fr)}}}}

.doc{{
  background:var(--canvas);
  border-radius:var(--radius-field);
  padding:18px 18px 22px;
  display:flex;flex-direction:column;align-items:flex-start;
}}
.doc__shot{{
  display:block;width:100%;height:150px;overflow:hidden;
  border-radius:var(--radius-field);border:1px solid var(--hairline);
  background:var(--surface);margin-bottom:20px;
}}
.doc__shot img{{width:100%;height:100%;object-fit:cover;object-position:top center}}
.doc__shot--deck img{{object-position:left center}}
.doc__name{{
  font-size:clamp(25px,3.4vw,30px);line-height:1.2;letter-spacing:-.04em;
  font-weight:585;font-variation-settings:'wght' 585;
}}
.doc__blurb{{
  margin-top:10px;font-size:15px;line-height:1.5;letter-spacing:-.03em;
  color:var(--ink-muted);
}}
.doc__meta{{
  margin-top:14px;margin-bottom:6px;font-size:13px;letter-spacing:-.025em;
  color:var(--ink-muted);font-variant-numeric:tabular-nums;
}}

/* --- buttons ---------------------------------------------------------- */
.btn{{
  display:inline-flex;align-items:center;justify-content:center;gap:12px;
  border-radius:var(--radius-pill);padding:15px 20px;margin-top:20px;
  font-size:15px;letter-spacing:-.03em;font-weight:600;
  font-variation-settings:'wght' 600;
  border:1px solid transparent;white-space:nowrap;
}}
.doc .btn{{align-self:stretch;margin-top:auto}}
.btn__dot{{width:10px;height:10px;border-radius:50%;display:block;flex:0 0 auto}}
.btn--primary{{background:var(--accent);color:var(--ink-on-accent)}}
.btn--primary .btn__dot{{background:var(--ink-on-accent)}}
.btn--primary:hover,.btn--primary:focus-visible{{background:var(--accent-pressed)}}
.btn--secondary{{background:transparent;color:var(--accent);border-color:var(--accent)}}
.btn--secondary .btn__dot{{background:var(--accent)}}
.btn--secondary:hover,.btn--secondary:focus-visible{{background:var(--accent);color:var(--ink-on-accent)}}
.btn--secondary:hover .btn__dot,.btn--secondary:focus-visible .btn__dot{{background:var(--ink-on-accent)}}
a:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}

/* --- how it works ----------------------------------------------------- */
.how{{
  margin:20px 0 0;background:var(--surface);
  border:1px solid var(--hairline);border-radius:var(--radius-card);
  padding:30px 22px;
}}
@media (min-width:760px){{.how{{padding:44px}}}}
.how__title{{
  font-size:clamp(25px,3.4vw,30px);line-height:1.2;letter-spacing:-.04em;
  font-weight:585;font-variation-settings:'wght' 585;margin-bottom:28px;
}}
.steps{{display:grid;gap:24px}}
@media (min-width:760px){{.steps{{grid-template-columns:repeat(3,1fr);gap:40px}}}}
.step{{border-top:1px solid var(--hairline);padding-top:18px}}
.step__num{{
  display:block;font-size:clamp(30px,4vw,45px);line-height:1;letter-spacing:-.04em;
  font-weight:500;font-variation-settings:'wght' 500;color:var(--accent);
  font-variant-numeric:tabular-nums;
}}
.hub{{width:100%;justify-content:center;margin-top:20px;flex-wrap:wrap;gap:10px 12px}}
.hub__meta{{font-size:13px;letter-spacing:-.025em;opacity:.78;width:100%;text-align:center}}
.step__text{{
  margin-top:14px;font-size:17px;line-height:1.5;letter-spacing:-.03em;
  color:var(--ink-muted);
}}

/* --- foot ------------------------------------------------------------- */
.foot{{
  margin-top:40px;padding:26px 0 56px;border-top:1px solid var(--hairline);
  font-size:13px;letter-spacing:-.025em;color:var(--ink-muted);
}}
</style>
</head>
<body>

<header class="hero wrap">
  <p class="eyebrow">Brand boards</p>
  <h1 class="hero__title">The whole identity, on one canvas.</h1>
  <p class="hero__lead">A brand board puts an entire identity on a single canvas: logo, colour, type, motion and components, all checkable at a glance. Each brand here ships twice, as a presentation that walks the system page by page and as a board that compresses that system onto one sheet.</p>
</header>

<main class="wrap">
  <div class="cards">
        {chr(10).join(cards)}
  </div>

  <section class="how" aria-labelledby="how-title">
    <h2 class="how__title" id="how-title">How it works</h2>
    <ol class="steps">
            {steps}
    </ol>
  </section>
</main>

<footer class="foot wrap">Built with Brand Board</footer>

</body>
</html>
"""

(SITE / "index.html").write_text(HTML)
print("wrote", SITE / "index.html", len(HTML), "bytes")
