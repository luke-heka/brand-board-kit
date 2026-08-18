"""brand.json -> a deployable one-page brand site.

    python3 -m engine.page brands/your-brand/brand.json      # writes out/your-brand/site/

The deck argues the system and the board proves it. This is the thing that
replaces Figma for the owner of the brand: one permanent link, every file the
brand owns visible and takeable, no account and no export step.

It is a folder rather than a single file on purpose. A mature brand's library is
173MB, and base64 inside one document turns that into roughly 225MB of HTML.
So the page ships with its assets beside it and links to them relatively:

    out/<slug>/site/
      index.html
      assets/...      the real files, copied, original resolution
      previews/...    web-size copies so the page loads quickly
      <doc>.pdf       every document the deck renderer produced
      tokens.css      tokens.json

The rule that earlier attempts broke: this reads the brand's whole `assets/`
folder, not the selection the deck happens to reference. A file that exists in
the brand is a file that appears on the page.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from . import theme as theme_mod
from .emit_skill import tokens_css, tokens_json
from .pages import AssetError, asset, esc, readable_on, _is_pale, _luminance
from .theme import PALETTE_DEFAULTS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# Card previews only ever fill a tile a couple of hundred pixels wide; 640 on the
# long edge covers a 2x screen with room to spare. Document pages are read, not
# glanced at, so they get enough pixels for body copy to stay legible.
PREVIEW_MAX = 640
DOC_PREVIEW_MAX = 1600
QUALITY = 82

RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
PALE = 0.75  # artwork every colour of which would vanish on a light frame

# A generated asset ships as a trio: the render, the self-contained HTML that
# produced it, and the values that HTML reads. The render is the asset; the
# other two are controls on its card, never cards of their own.
PRIMARY = RASTER | {".svg"}
SIBLINGS = (("source", ".html"), ("values", ".json"))

# Open a section with the page when it is this size or smaller. A count, not a
# list of folder names, so a brand nobody has seen yet still opens short.
OPEN_AT_MOST = 20

# De-slugging a folder name is a guess, and these are the guesses that read
# wrong when title-cased letter by letter.
_UPPER = {"ai", "ui", "ux", "og", "url", "pdf", "svg", "png", "jpg", "crm",
          "seo", "html", "css", "js", "cta", "faq", "3d", "id", "qr", "b2b"}
_LOWER = {"and", "or", "of", "the", "for", "to", "in", "on", "a", "an", "vs"}


# --- naming -----------------------------------------------------------------

def title_of(name: str) -> str:
    """`social-media-marketing` -> `Social Media Marketing`."""
    words = [w for w in re.split(r"[-_\s]+", name.strip()) if w]
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in _UPPER:
            out.append(low.upper())
        elif i and low in _LOWER:
            out.append(low)
        elif w.isupper():
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out) or name


def anchor(*parts: str) -> str:
    raw = "-".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "section"


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1048576:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1048576:.1f} MB"


# --- reading the brand's assets ---------------------------------------------

def walk(assets: Path) -> list[Path]:
    """Every real file under `assets/`, relative, sorted, dotfiles excluded."""
    if not assets.is_dir():
        return []
    found = []
    for p in assets.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(assets)
        # A leading dot or underscore means private and never reaches the page.
        # This exists because team portraits, real people, sat in an asset
        # folder and were published as downloadable files on a public URL.
        if any(part.startswith((".", "_")) for part in rel.parts):
            continue
        found.append(rel)
    return sorted(found, key=lambda r: (len(r.parts), r.as_posix().lower()))


def collect_items(rels: list[Path]) -> list[dict]:
    """One card per asset, with its editable source folded in.

    `launch.png` beside `launch.html` and `launch.json` is one asset that can be
    changed and rendered again, not three files. Three cards would triple the
    wall and hide the relationship, so the render keeps the other two and they
    stop being cards. A file with no siblings is unchanged.
    """
    have = set(rels)
    claimed: set[Path] = set()
    extra: dict[Path, dict] = {}
    for rel in rels:
        if rel.suffix.lower() not in PRIMARY:
            continue
        found = {}
        for role, suffix in SIBLINGS:
            sib = rel.with_suffix(suffix)
            if sib in have and sib not in claimed:
                claimed.add(sib)
                found[role] = sib
        if found:
            extra[rel] = found
    return [{"rel": r, **extra.get(r, {})} for r in rels if r not in claimed]


def group_files(items: list[dict]) -> list[dict]:
    """Fold the folder tree into sections, nested exactly one level.

    Section titles are the folder names the brand actually uses, so a brand with
    a `sound/` folder gets a Sound section without this file knowing about it.
    Anything deeper than one level of nesting still appears, folded into its
    grandparent's subsection rather than sprouting a third heading level.
    """
    groups: dict[str, dict] = {}
    for item in items:
        parts = item["rel"].parts
        top = parts[0] if len(parts) > 1 else "assets"
        sub = parts[1] if len(parts) > 2 else ""
        g = groups.setdefault(top, {"key": top, "title": title_of(top),
                                    "items": [], "subs": {}})
        if sub:
            s = g["subs"].setdefault(sub, {"key": sub, "title": title_of(sub),
                                           "items": []})
            s["items"].append(item)
        else:
            g["items"].append(item)
    out = []
    for g in groups.values():
        subs = sorted(g["subs"].values(), key=lambda s: s["title"].lower())
        total = len(g["items"]) + sum(len(s["items"]) for s in subs)
        out.append({**g, "subs": subs, "count": total})
    # Biggest first would bury the logo under the library. Fewest first puts the
    # small, defining folders at the top and the long tail at the bottom.
    return sorted(out, key=lambda g: (g["count"], g["title"].lower()))


# --- previews ---------------------------------------------------------------

def _pale_svg(path: Path) -> bool:
    """True when every colour in an SVG would vanish on a pale frame.

    A reversed mark with no declared ground renders as a white shape on a
    near-white tile: present, downloadable, and invisible.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    hexes = re.findall(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", text)
    return bool(hexes) and all(_luminance(h) > PALE for h in hexes)


def _fresh(src: Path, dst: Path) -> bool:
    return dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime


def make_preview(src: Path, dst_dir: Path, rel: Path, max_edge: int,
                 written: set[Path]) -> tuple[str | None, str | None]:
    """Write a web-size copy. Returns (relative url, problem).

    The original is never touched and never resized: the card links straight at
    it, and this is only what the tile shows.
    """
    if src.suffix.lower() not in RASTER:
        return None, None
    try:
        from PIL import Image
    except ImportError:
        return None, "Pillow is not installed — no previews generated"
    try:
        with Image.open(src) as im:
            im.load()
            alpha = im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info)
            ext = ".png" if alpha else ".jpg"
            dst = dst_dir / rel.with_suffix(ext)
            url = dst.relative_to(dst_dir.parent).as_posix()
            written.add(dst)
            if _fresh(src, dst):
                return url, None
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            if alpha:
                im.convert("RGBA").save(dst, "PNG", optimize=True)
            else:
                im.convert("RGB").save(dst, "JPEG", quality=QUALITY,
                                       optimize=True, progressive=True)
            return url, None
    except Exception as exc:  # a file that will not decode is a fact to report
        return None, f"{rel.as_posix()}: {type(exc).__name__} {exc}"


# --- documents --------------------------------------------------------------

def find_documents(docs_dir: Path, slug: str = "") -> list[dict]:
    """Every rendered document: a PDF with a run of per-page PNGs beside it.

    Discovered rather than named, so the brand identity pitch appears next to
    the guideline the moment its pages are rendered, with nothing changed here.
    """
    if not docs_dir.is_dir():
        return []
    out = []
    for pdf in sorted(docs_dir.glob("*.pdf")):
        pages = sorted(docs_dir.glob(f"{pdf.stem}-[0-9][0-9]*.png"))
        if not pages:
            continue
        # `your-brand-brand-presentation` -> `Brand Presentation`. Only the slug is
        # stripped, because "Presentation" on its own says less than it should.
        label = re.sub(r"^" + re.escape(slug) + r"-", "", pdf.stem) if slug else pdf.stem
        out.append({"stem": pdf.stem, "pdf": pdf, "pages": pages,
                    "title": title_of(label or pdf.stem)})
    # The long guideline is the one a visitor came for, so it leads.
    return sorted(out, key=lambda d: (-len(d["pages"]), d["title"]))


# --- html -------------------------------------------------------------------

def hero(brand: dict, root: Path, groups: list[dict], files: int,
         bytes_total: int, recipes: int, score: dict | None = None) -> str:
    m = brand["meta"]
    mark = m.get("boardMark") or m.get("coverMark")
    logo = f'<img class="hero__mark" src="{asset(mark, root)}" alt="">' if mark else ""
    tally = (f"{files} file{'s' if files != 1 else ''} in "
             f"{len(groups)} group{'s' if len(groups) != 1 else ''}, "
             f"{human_size(bytes_total)}. Every one of them downloads at full "
             f"resolution from this page.")
    # Said in the words of the person who owns the brand, not the person who
    # built the renderer.
    note = (f"{recipes} of them are built rather than drawn. Their card has a "
            f"Source button and a Values button: change one value, render it "
            f"again, and you have a new version that is still on brand."
            if recipes else "")
    # How complete the brand is, stated up front. A page that only shows what
    # exists lets a half-built brand read as a finished one.
    done = ""
    if score and score.get("total"):
        done = (f"This brand is {score['pct']}% complete: "
                f"{score['have']} of {score['total']} things a brand needs are here."
                + (" The rest are listed at the foot of this page."
                   if score["have"] < score["total"] else ""))
    return (
        '<header class="hero">'
        f'{logo}'
        f'<h1 class="hero__name">{esc(m["name"])}</h1>'
        f'<p class="hero__doc">Brand assets</p>'
        + (f'<p class="hero__line">{esc(m["line"])}</p>' if m.get("line") else "")
        + f'<p class="hero__tally">{esc(tally)}</p>'
        + (f'<p class="hero__note">{esc(note)}</p>' if note else "")
        + (f'<p class="hero__note">{esc(done)}</p>' if done else "")
        + '</header>'
    )


def secnav(nav: list[tuple[str, str]]) -> str:
    """The sticky section bar.

    One row that scrolls sideways rather than a block that wraps: a brand with
    fifteen groups must not hand back a third of the window to its own nav.
    """
    chips = "".join(f'<a class="chip" href="#{esc(a)}">{esc(t)}</a>' for a, t in nav)
    return ('<nav class="secnav" aria-label="Sections">'
            f'<div class="secnav__chips">{chips}</div>'
            '<button type="button" class="secnav__all" hidden '
            'aria-pressed="false">Expand all</button>'
            '</nav>')


def section(anchor_id: str, title: str, count: int, body: str,
            extra_class: str = "", open_: bool | None = None) -> str:
    """A collapsible top-level section.

    `<details>` rather than a button and a class, so the page folds and unfolds
    with the browser's own machinery and works with the network off, the
    JavaScript blocked, or the keyboard only.
    """
    is_open = (count <= OPEN_AT_MOST) if open_ is None else open_
    return (f'<details class="group{extra_class}" id="{esc(anchor_id)}"'
            f'{" open" if is_open else ""}>'
            '<summary class="group__head">'
            f'<h2 class="group__title">{esc(title)}'
            f'<span class="group__count">{count}</span></h2></summary>'
            f'<div class="group__body">{body}</div></details>')


def doc_html(doc: dict, urls: list[str], pdf_url: str) -> str:
    n = len(urls)
    return (
        f'<article class="doc" tabindex="0" aria-label="{esc(doc["title"])}, '
        f'{n} page{"s" if n != 1 else ""}">'
        f'<script type="application/json" class="doc__pages">{json.dumps(urls)}</script>'
        f'<h3 class="doc__title">{esc(doc["title"])}</h3>'
        f'<p class="doc__sub">{n} page{"s" if n != 1 else ""}, read it here or take the PDF</p>'
        f'<div class="doc__stage">'
        f'<img class="doc__page" src="{esc(urls[0])}" alt="{esc(doc["title"])} page 1">'
        f'</div>'
        '<div class="doc__bar">'
        '<button type="button" class="doc__nav" data-step="-1" aria-label="Previous page">'
        '&#8592;</button>'
        f'<span class="doc__count"><b class="doc__at">1</b> / {n}</span>'
        '<button type="button" class="doc__nav" data-step="1" aria-label="Next page">'
        '&#8594;</button>'
        f'<a class="doc__dl" download href="{esc(pdf_url)}">PDF &#8595;</a>'
        '</div>'
        '</article>'
    )


def card_html(item: dict, src: Path, preview: str | None) -> str:
    rel = item["rel"]
    name = rel.name
    ext = rel.suffix.lstrip(".").upper() or "FILE"
    dark = " frame--dark" if rel.suffix.lower() == ".svg" and _pale_svg(src) else ""
    if preview:
        inner = f'<img loading="lazy" decoding="async" src="{esc(preview)}" alt="">'
    else:
        inner = f'<span class="frame__ext">{esc(ext)}</span>'

    acts = ""
    if item.get("source") or item.get("values"):
        # Named for what the person gets, not for the file extension. Download
        # is repeated here so the three sit together and read as one asset.
        links = [f'<a class="act act--dl" download href="assets/{esc(rel.as_posix())}">'
                 'Download</a>']
        for role, label in (("source", "Source"), ("values", "Values")):
            sib = item.get(role)
            if sib:
                links.append(f'<a class="act" target="_blank" rel="noopener" '
                             f'href="assets/{esc(sib.as_posix())}">{label}</a>')
        acts = f'<div class="card__acts">{"".join(links)}</div>'

    return (
        '<div class="card">'
        f'<a class="card__hit" download href="assets/{esc(rel.as_posix())}" '
        f'title="{esc(rel.as_posix())}">'
        f'<span class="card__frame{dark}">{inner}</span>'
        f'<span class="card__name">{esc(name)}</span>'
        f'<span class="card__meta"><span>{esc(ext)}</span>'
        f'<span class="card__size">{esc(human_size(src.stat().st_size))} &#8595;</span>'
        f'</span></a>{acts}</div>'
    )


def group_html(g: dict, assets: Path, previews: dict[str, str | None]) -> str:
    def grid(items):
        return ('<div class="cards">'
                + "".join(card_html(i, assets / i["rel"],
                                    previews.get(i["rel"].as_posix()))
                          for i in items)
                + '</div>')

    parent_open = g["count"] <= OPEN_AT_MOST
    bits = [grid(g["items"])] if g["items"] else []
    for s in g["subs"]:
        # A closed parent keeps its subsections closed, so opening the library
        # shows its shelves rather than the whole wall a second time.
        sub_open = parent_open and len(s["items"]) <= OPEN_AT_MOST
        bits.append(
            f'<details class="sub" id="{esc(anchor(g["key"], s["key"]))}"'
            f'{" open" if sub_open else ""}>'
            '<summary class="sub__head">'
            f'<h3 class="sub__title">{esc(s["title"])}'
            f'<span class="sub__count">{len(s["items"])}</span></h3></summary>'
            f'<div class="sub__body">{grid(s["items"])}</div></details>')
    return section(anchor(g["key"]), g["title"], g["count"], "".join(bits))


def swatch_html(c: dict, pool: tuple[str, ...]) -> str:
    hexv = c["hex"]
    ink = readable_on(hexv, *pool)
    pale = " swatch--pale" if _is_pale(hexv) else ""
    return (
        f'<button type="button" class="swatch{pale}" data-copy="{esc(hexv.upper())}" '
        f'style="background:{esc(hexv)};color:{esc(ink)}">'
        f'<b>{esc(c.get("name", "Colour"))}</b>'
        f'<span class="js-note">{esc(hexv.upper())}</span>'
        '</button>'
    )


def colour_sets(brand: dict) -> list[dict]:
    """Every swatch the brand declares: the named sets, then the raw tokens."""
    sets, seen = [], set()
    for sec in brand.get("sections", []):
        for page in sec.get("pages", []):
            colours = []
            for c in page.get("colours") or []:
                key = (c.get("hex") or "").upper()
                if not key or key in seen:
                    continue
                seen.add(key)
                colours.append(c)
            if colours:
                sets.append({"label": page.get("captionTitle") or sec["title"],
                             "colours": colours})
    tokens = [{"name": k, "hex": v} for k, v in brand.get("palette", {}).items()]
    if tokens:
        sets.append({"label": "Tokens", "colours": tokens})
    return sets


def colour_html(brand: dict, pool: tuple[str, ...], slug: str) -> str:
    bits = []
    for s in colour_sets(brand):
        bits.append(f'<h3 class="sub__title">{esc(s["label"])}'
                    f'<span class="sub__count">{len(s["colours"])}</span></h3>'
                    '<div class="swatches">'
                    + "".join(swatch_html(c, pool) for c in s["colours"])
                    + '</div>')
    bits.append(
        '<div class="tokens">'
        f'<a class="tok" download="{esc(slug)}-tokens.css" href="tokens.css">'
        '<b>tokens.css</b><span>The whole palette as custom properties &#8595;</span></a>'
        f'<a class="tok" download="{esc(slug)}-tokens.json" href="tokens.json">'
        '<b>tokens.json</b><span>The same values, machine readable &#8595;</span></a>'
        '</div>')
    body = ('<p class="group__note">Click any swatch to copy its hex.</p>'
            + "".join(bits))
    return section("colour", "Colour",
                   sum(len(s["colours"]) for s in colour_sets(brand)), body)


JS = """
/* --- sections ------------------------------------------------------------
   The folding itself is <details>, which needs none of this. What follows is
   only what a browser cannot do on its own: know which section you are looking
   at, open a closed one you asked for, and open the lot. */
const nav = document.querySelector('.secnav');
const rail = nav && nav.querySelector('.secnav__chips');
const chips = nav ? [...nav.querySelectorAll('.chip')] : [];
const marks = chips.map((c) => document.getElementById(decodeURIComponent(c.hash.slice(1))));
const folds = [...document.querySelectorAll('details.group, details.sub')];

function reveal(el) {
  for (let d = el.closest('details'); d; d = d.parentElement.closest('details')) d.open = true;
}

const allBtn = nav && nav.querySelector('.secnav__all');
function setAll(open) {
  for (const d of folds) d.open = open;
  if (!allBtn) return;
  allBtn.textContent = open ? 'Collapse all' : 'Expand all';
  allBtn.setAttribute('aria-pressed', String(open));
}
if (allBtn) {
  allBtn.hidden = false;
  allBtn.addEventListener('click', () => setAll(allBtn.getAttribute('aria-pressed') !== 'true'));
}

/* Find-in-page cannot see inside a closed section, so the keystroke that opens
   the find bar opens the page first. The browser's own menu item is out of
   reach; that one still only searches what is showing. */
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'f' || e.key === 'F')) setAll(true);
});
window.addEventListener('beforeprint', () => setAll(true));

let here = -1;
function spy() {
  const line = nav.getBoundingClientRect().bottom + 14;
  let at = -1;
  marks.forEach((el, i) => { if (el && el.getBoundingClientRect().top <= line) at = i; });
  if (at === here) return;
  here = at;
  chips.forEach((c, i) => c.classList.toggle('is-here', i === at));
  if (at < 0) return;
  const c = chips[at];
  rail.scrollTo({ left: Math.max(0, c.offsetLeft - (rail.clientWidth - c.offsetWidth) / 2),
                  behavior: 'smooth' });
}
if (nav) {
  let queued = false;
  const tick = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; spy(); });
  };
  window.addEventListener('scroll', tick, { passive: true });
  window.addEventListener('resize', tick);
  for (const d of folds) d.addEventListener('toggle', tick);

  nav.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const el = document.getElementById(decodeURIComponent(a.hash.slice(1)));
    if (!el) return;
    e.preventDefault();
    reveal(el);
    history.replaceState(null, '', a.hash);
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  spy();
}

/* A link into a closed section is a link to nothing, whether it came from the
   nav, a bookmark or somebody's chat message. */
function jump() {
  if (!location.hash) return;
  const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (!el) return;
  reveal(el);
  el.scrollIntoView({ block: 'start' });
}
window.addEventListener('hashchange', jump);
jump();

for (const doc of document.querySelectorAll('.doc')) {
  const pages = JSON.parse(doc.querySelector('.doc__pages').textContent);
  const img = doc.querySelector('.doc__page');
  const at = doc.querySelector('.doc__at');
  let i = 0;
  const show = (next) => {
    i = (next + pages.length) % pages.length;
    img.src = pages[i];
    img.alt = doc.getAttribute('aria-label') + ' page ' + (i + 1);
    at.textContent = String(i + 1);
    const ahead = new Image();
    ahead.src = pages[(i + 1) % pages.length];
  };
  for (const b of doc.querySelectorAll('.doc__nav')) {
    b.addEventListener('click', () => { doc.focus(); show(i + Number(b.dataset.step)); });
  }
  doc.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); show(i + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); show(i - 1); }
  });
  doc.dataset.ready = '1';
}

/* Arrow keys work without clicking first: whichever document is most nearly
   centred in the window is the one being read. */
document.addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
  if (document.activeElement && document.activeElement.closest('.doc')) return;
  const mid = window.innerHeight / 2;
  let best = null, dist = Infinity;
  for (const doc of document.querySelectorAll('.doc')) {
    const r = doc.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) continue;
    const d = Math.abs(r.top + r.height / 2 - mid);
    if (d < dist) { dist = d; best = doc; }
  }
  if (!best) return;
  best.querySelector(`.doc__nav[data-step="${e.key === 'ArrowRight' ? 1 : -1}"]`).click();
});

function flash(el) {
  const note = el.querySelector('.js-note');
  const was = note.textContent;
  note.textContent = 'Copied';
  el.classList.add('is-copied');
  setTimeout(() => { note.textContent = was; el.classList.remove('is-copied'); }, 1100);
}
for (const el of document.querySelectorAll('[data-copy]')) {
  el.addEventListener('click', () => {
    const text = el.dataset.copy;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => flash(el), () => {});
    }
  });
}
"""

DOC = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>{body}<script>{js}</script></body></html>"""


# --- build ------------------------------------------------------------------

def pending_html(items: list[dict]) -> str:
    """What the brand still needs, stated as an action rather than a complaint."""
    if not items:
        return ""
    cards = "".join(
        f'<article class="pend">'
        f'<h4 class="pend__title">{esc(i["title"])}</h4>'
        f'<p class="pend__why">{esc(i["why"])}</p>'
        f'<p class="pend__fix">{esc(i["fix"])}</p>'
        f'<span class="pend__tag">{esc(i["group"])}</span>'
        f'</article>' for i in items)
    return section(
        "pending", "Pending", len(items),
        '<p class="group__note">Not made yet. Nothing here was filled in with a '
        'placeholder, because a placeholder that looks finished is worse than an '
        'empty slot that says what it needs.</p>'
        f'<div class="pend__grid">{cards}</div>')


def build(brand_path: Path, out: Path, docs_dir: Path) -> dict:
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    root = brand_path.parent
    m = brand["meta"]
    slug = m.get("slug") or root.name

    assets = root / "assets"
    rels = walk(assets)
    if not rels:
        raise AssetError(f"no files found under {assets}")
    items = collect_items(rels)
    recipes = sum(1 for i in items if i.get("source") or i.get("values"))
    groups = group_files(items)

    site_assets, site_prev = out / "assets", out / "previews"
    kept_assets: set[Path] = set()
    kept_prev: set[Path] = set()
    problems: list[str] = []

    # Copy the originals. Full resolution, untouched, because the download is
    # the whole point of the page.
    bytes_total = 0
    for rel in rels:
        src, dst = assets / rel, site_assets / rel
        bytes_total += src.stat().st_size
        kept_assets.add(dst)
        if _fresh(src, dst) and dst.stat().st_size == src.stat().st_size:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    previews: dict[str, str | None] = {}
    made = 0
    for rel in rels:
        if rel.suffix.lower() == ".svg":
            previews[rel.as_posix()] = f"assets/{rel.as_posix()}"
            continue
        url, problem = make_preview(assets / rel, site_prev, rel, PREVIEW_MAX, kept_prev)
        previews[rel.as_posix()] = url
        made += bool(url)
        if problem:
            problems.append(problem)

    # Documents: the PDF beside the page, and a web-size copy of every rendered
    # page so the flip-through starts instantly.
    docs, doc_urls = find_documents(docs_dir, slug), []
    for d in docs:
        pdf_dst = out / d["pdf"].name
        kept_assets.add(pdf_dst)
        if not _fresh(d["pdf"], pdf_dst):
            shutil.copy2(d["pdf"], pdf_dst)
        urls = []
        for i, png in enumerate(d["pages"], start=1):
            rel = Path("doc") / d["stem"] / f"{i:03d}.png"
            url, problem = make_preview(png, site_prev, rel, DOC_PREVIEW_MAX, kept_prev)
            if problem:
                problems.append(problem)
            urls.append(url or f"previews/doc/{d['stem']}/{i:03d}.png")
        doc_urls.append(urls)

    # Anything left from a previous run is a file the brand no longer has, and
    # a page that offers it is lying about what the brand contains.
    stale = 0
    for folder, kept in ((site_assets, kept_assets), (site_prev, kept_prev)):
        for p in sorted(folder.rglob("*"), reverse=True) if folder.is_dir() else []:
            if p.is_file() and p not in kept:
                p.unlink()
                stale += 1
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()

    (out / "tokens.css").write_text(tokens_css(brand), encoding="utf-8")
    (out / "tokens.json").write_text(
        json.dumps(tokens_json(brand), indent=2) + "\n", encoding="utf-8")

    palette = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    pool = (palette["ink"], palette["inkOnDark"], palette["canvas"], palette["groundDark"])

    try:
        from .gaps import audit as _audit
        _a = _audit(brand, root)
        pending, score = _a["missing"], _a["score"]
    except Exception:
        pending, score = [], None

    nav = [("documents", "Documents")] if docs else []
    nav += [(anchor(g["key"]), g["title"]) for g in groups] + [("colour", "Colour")]
    if pending:
        nav += [("pending", "Pending")]

    doc_section = ""
    if docs:
        cards = "".join(doc_html(d, urls, d["pdf"].name)
                        for d, urls in zip(docs, doc_urls))
        doc_section = section(
            "documents", "Documents", len(docs),
            '<p class="group__note">Read them here page by page, or take the PDF.</p>'
            f'<div class="docs__grid docs__grid--{min(len(docs), 2)}">{cards}</div>',
            extra_class=" docs")

    body = ('<div class="wrap">'
            + hero(brand, root, groups, len(rels), bytes_total, recipes, score)
            + secnav(nav)
            + doc_section
            + "".join(group_html(g, assets, previews) for g in groups)
            + colour_html(brand, pool, slug)
            + pending_html(pending)
            + f'<footer class="foot">{esc(m.get("wordmark", m["name"]))} &middot; '
              f'Brand assets &middot; &copy; {esc(m.get("year", ""))} '
              f'{esc(m.get("legal", "All rights reserved"))}</footer>'
            + '</div>')

    css = theme_mod.stylesheet(brand, [TEMPLATES / "page.css"], root=root)
    if not pending:
        # No pending cards on the page, so ship no pending styles. page.css keeps
        # its pending block as the last section; cut it at the marker comment.
        css = css.split("/* --- pending ")[0].rstrip() + "\n"
    html = DOC.format(
        title=f'{m["name"]} — Brand assets',
        css=css,
        body=body, js=JS)
    (out / "index.html").write_text(html, encoding="utf-8")

    downloads = html.count("<a class=\"card__hit\" download") + 2 + len(docs)
    return {"slug": slug, "out": out, "files": len(rels), "cards": len(items),
            "recipes": recipes, "groups": len(groups),
            "bytes": bytes_total, "previews": made, "docs": docs,
            "doc_pages": sum(len(u) for u in doc_urls), "downloads": downloads,
            "stale": stale, "problems": problems}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a brand's deployable asset page.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path, help="defaults to out/<slug>/site")
    ap.add_argument("--docs", type=Path,
                    help="where the rendered documents live, defaults to out/<slug>")
    args = ap.parse_args(argv)

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    slug = brand["meta"].get("slug") or args.brand.parent.name
    docs_dir = args.docs or (ROOT / "out" / slug)
    out = args.out or (ROOT / "out" / slug / "site")
    out.mkdir(parents=True, exist_ok=True)

    r = build(args.brand, out, docs_dir)
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"page   {r['files']} files as {r['cards']} cards "
          f"({r['recipes']} with a source) in {r['groups']} groups, "
          f"{r['previews']} previews, {len(r['docs'])} document"
          f"{'s' if len(r['docs']) != 1 else ''} ({r['doc_pages']} pages), "
          f"{r['downloads']} downloads, {human_size(total)} -> {out}")
    if r["stale"]:
        print(f"       {r['stale']} stale file(s) removed")
    for p in r["problems"]:
        print(f"  ! {p}")
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
