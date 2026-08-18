"""brand.json -> one self-contained page of downloadable brand assets.

    python3 -m engine.hub brands/your-brand/brand.json

The deck argues the system, the board proves it, the skill teaches a model. This
is the one the owner of the brand works from: every file the brand owns, grouped
the way the brand groups itself, each one a click away from being saved. It is a
single HTML file with every asset embedded, so it survives being emailed, opened
off a USB stick, or read with the network unplugged.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from . import theme as theme_mod
from .emit_skill import tokens_css, tokens_json
from .pages import _swatch_hex, AssetError, asset, esc, readable_on, _is_pale, _luminance
from .theme import PALETTE_DEFAULTS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# Walking for path keys rather than switching on `kind` means a page type added
# to pages.py later shows up in the hub without this file being touched.
_ASSET_KEYS = ("src", "bg")
_LABEL_KEYS = ("label", "variant", "name")

# The one page that must not contribute. Its artwork is stretched, rotated,
# recoloured or deliberately drawn wrong to demonstrate a rule — a download hub
# offering "Never let ember reach the letters" as a file is worse than useless.
_NOT_DELIVERABLE = {"misuse"}

_PALE = 0.75  # artwork this light disappears on a light frame


def _refs(node, ground: str = ""):
    """Every asset reference inside a page, whatever the page kind."""
    if isinstance(node, dict):
        ground = node.get("ground", ground)
        label = next((str(node[k]) for k in _LABEL_KEYS if node.get(k)), "")
        for key in _ASSET_KEYS:
            src = node.get(key)
            if isinstance(src, str) and src:
                yield {"src": src, "label": label, "ground": ground}
        for key, value in node.items():
            if key not in _ASSET_KEYS and isinstance(value, (dict, list)):
                yield from _refs(value, ground)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item, ground)


def _resolve(src: str, root: Path) -> Path:
    p = Path(src)
    return (p if p.is_absolute() else root / p).resolve()


def groups(brand: dict, root: Path) -> list[dict]:
    """The brand's own sections, carrying whatever each one actually owns.

    Section titles come from the brand file, never from a list in here — a brand
    with a Sound section or no Motion section gets the page it declared.
    """
    seen_files: set[Path] = set()
    out = []
    for sec in brand.get("sections", []):
        assets, sets, seen_hex = [], [], set()
        for page in sec.get("pages", []):
            for ref in ([] if page.get("kind") in _NOT_DELIVERABLE else _refs(page)):
                path = _resolve(ref["src"], root)
                if path in seen_files:
                    continue
                seen_files.add(path)
                assets.append({**ref, "path": path})
            colours = []
            for c in page.get("colours", []) or []:
                try:
                    hx = _swatch_hex(c, palette)
                except Exception:
                    continue
                if hx.upper() in seen_hex:
                    continue
                seen_hex.add(hx.upper())
                colours.append({**c, "hex": hx})
            if colours:
                sets.append({"label": page.get("captionTitle") or sec["title"],
                             "colours": colours})
        if assets or sets:
            out.append({"title": sec["title"], "summary": sec.get("summary", ""),
                        "assets": assets, "sets": sets})
    return out


def _name_downloads(gs: list[dict]) -> None:
    """Give every asset a filename that is unique across the whole page.

    Two files called `mark.svg` in different folders would otherwise both save as
    `mark.svg`, and the second quietly overwrites the first in Downloads.
    """
    used: set[str] = set()
    for g in gs:
        for a in g["assets"]:
            name = a["path"].name
            if name in used:
                name = f"{a['path'].parent.name}-{name}"
            used.add(name)
            a["file"] = name


def _size(path: Path) -> str:
    n = path.stat().st_size if path.exists() else 0
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.0f} KB" if n < 1048576 else f"{n / 1048576:.1f} MB"


def _pale_artwork(path: Path) -> bool:
    """True when every colour in an SVG is light enough to vanish on a pale frame.

    A reversed mark that the brand file forgot to give a `ground` renders as a
    white shape on a near-white tile — present, downloadable, and invisible.
    This reads the artwork's own colours rather than guessing from the filename.
    """
    if path.suffix.lower() != ".svg" or not path.exists():
        return False
    import re
    hexes = re.findall(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b",
                       path.read_text(encoding="utf-8", errors="replace"))
    return bool(hexes) and all(_luminance(h) > _PALE for h in hexes)


def _text_uri(text: str, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(text.encode('utf-8')).decode('ascii')}"


def _asset_card(a: dict, root: Path) -> str:
    declared = a.get("ground") or ("dark" if _pale_artwork(a["path"]) else "")
    ground = {"dark": " asset__frame--dark",
              "accent": " asset__frame--accent"}.get(declared, "")
    label = a["label"] or a["path"].stem.replace("-", " ")
    # The preview shares the anchor's data URI instead of carrying its own copy.
    # Two copies of every asset doubles the page for no gain; the hydrating line
    # of script at the foot costs nothing and halves the file.
    return (
        f'<a class="asset" download="{esc(a["file"])}" title="{esc(a["file"])}" '
        f'href="{asset(a["src"], root)}">'
        f'<span class="asset__frame{ground}"><img alt="{esc(label)}"></span>'
        f'<span class="asset__name">{esc(label)}</span>'
        f'<span class="asset__meta"><span>{esc(a["file"])}</span>'
        f'<span class="asset__size">{_size(a["path"])} &#8595;</span></span>'
        '</a>'
    )


def _swatch(c: dict, pool: tuple[str, ...]) -> str:
    hexv = c["hex"]
    ink = readable_on(hexv, *pool)
    pale = " swatch--pale" if _is_pale(hexv) else ""
    return (
        f'<button type="button" class="swatch{pale}" data-copy="{esc(hexv.upper())}" '
        f'style="background:{esc(hexv)};color:{ink}">'
        f'<b>{esc(c.get("name", "Colour"))}</b>'
        f'<span class="js-note">{esc(hexv.upper())}</span>'
        '</button>'
    )


def _group_html(g: dict, root: Path, pool: tuple[str, ...]) -> str:
    bits = []
    for s in g["sets"]:
        bits.append(f'<h3 class="set__label">{esc(s["label"])}</h3>'
                    f'<div class="swatches">'
                    f'{"".join(_swatch(c, pool) for c in s["colours"])}</div>')
    if g["assets"]:
        bits.append('<div class="assets">'
                    + "".join(_asset_card(a, root) for a in g["assets"]) + '</div>')
    return (f'<section class="group"><h2 class="group__title">{esc(g["title"])}</h2>'
            + (f'<p class="group__note">{esc(g["summary"])}</p>' if g["summary"] else "")
            + "".join(bits) + '</section>')


def _head(brand: dict, root: Path, files: int, colours: int, count: int) -> str:
    m = brand["meta"]
    mark = m.get("boardMark") or m.get("coverMark")
    logo = f'<img class="hub__mark" src="{asset(mark, root)}" alt="">' if mark else ""
    tally = (f"{files} file{'s' if files != 1 else ''}, {colours} colour"
             f"{'s' if colours != 1 else ''}, {count} group{'s' if count != 1 else ''}. "
             f"Every one is embedded in this page, so it opens with the network off.")
    return (
        '<header class="hub__head">'
        f'<div>{logo}<div class="hub__name">{esc(m["name"])}</div>'
        f'<div class="hub__doc">Brand assets</div></div>'
        f'<p class="hub__tally">{esc(tally)}</p>'
        '</header>'
    )


def _kit(brand: dict, gs: list[dict], slug: str) -> str:
    """The palette as files, and the honest answer to "download everything"."""
    css_uri = _text_uri(tokens_css(brand), "text/css")
    json_uri = _text_uri(json.dumps(tokens_json(brand), indent=2) + "\n", "application/json")
    parents = {str(a["path"].parent) for g in gs for a in g["assets"]}
    folder = Path(os.path.commonpath(sorted(parents)) if parents else str(ROOT))
    # Relative when it can be, because an absolute path bakes this machine's
    # home folder into a file that gets emailed on.
    try:
        shown, where = folder.relative_to(ROOT).as_posix(), "From the brand-board folder, this"
    except ValueError:
        shown, where = str(folder), "This"
    line = f'cp -R "{shown}" ~/Desktop/{slug}-brand-assets'
    return (
        '<section class="kit">'
        '<div class="kit__files">'
        f'<a class="tok" download="{esc(slug)}-tokens.css" href="{css_uri}">'
        '<b>tokens.css</b><span>The whole palette as custom properties &#8595;</span></a>'
        f'<a class="tok" download="{esc(slug)}-tokens.json" href="{json_uri}">'
        '<b>tokens.json</b><span>The same values, machine readable &#8595;</span></a>'
        '</div>'
        '<p class="kit__note">Each card below saves one file. A page cannot hand you a '
        'folder, so there is no download-everything button here that would work. '
        f'{where} line copies the lot:</p>'
        f'<button type="button" class="copyline" data-copy="{esc(line)}">'
        f'<code>{esc(line)}</code><span class="js-note">Copy</span></button>'
        '</section>'
    )


JS = """
for (const a of document.querySelectorAll('a.asset')) a.querySelector('img').src = a.href;

function flash(el) {
  const note = el.querySelector('.js-note');
  const was = note.textContent;
  note.textContent = 'Copied';
  el.classList.add('is-copied');
  setTimeout(() => { note.textContent = was; el.classList.remove('is-copied'); }, 1100);
}
function fallback(text, el) {
  const t = document.createElement('textarea');
  t.value = text;
  t.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
  document.body.appendChild(t);
  t.select();
  try { document.execCommand('copy'); flash(el); } finally { t.remove(); }
}
for (const el of document.querySelectorAll('[data-copy]')) {
  el.addEventListener('click', () => {
    const text = el.dataset.copy;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => flash(el), () => fallback(text, el));
    } else {
      fallback(text, el);
    }
  });
}
"""

DOC = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>{body}<script>{js}</script></body></html>"""


def hub_html(brand: dict, root: Path) -> tuple[str, int, int]:
    """Returns the page, the file count and the count of `<a download>` on it."""
    gs = groups(brand, root)
    if not gs:
        raise AssetError("brand file declares no assets and no colours")
    _name_downloads(gs)

    palette = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    pool = (palette["ink"], palette["inkOnDark"], palette["canvas"], palette["groundDark"])

    files = sum(len(g["assets"]) for g in gs)
    colours = sum(len(s["colours"]) for g in gs for s in g["sets"])
    m = brand["meta"]
    slug = m.get("slug", m["name"].lower().replace(" ", "-"))

    body = ('<div class="wrap">'
            + _head(brand, root, files, colours, len(gs))
            + _kit(brand, gs, slug)
            + "".join(_group_html(g, root, pool) for g in gs)
            + f'<footer class="hub__foot">{esc(m.get("wordmark", m["name"]))} &middot; '
              f'Brand assets &middot; &copy; {esc(m.get("year", ""))} '
              f'{esc(m.get("legal", "All rights reserved"))}</footer>'
            + '</div>')

    html = DOC.format(
        title=f'{m["name"]} — Brand assets',
        css=theme_mod.stylesheet(brand, [TEMPLATES / "hub.css"], root=root),
        body=body, js=JS)
    return html, files, files + 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a downloadable brand asset hub.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path, help="defaults to out/<slug>")
    args = ap.parse_args(argv)

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    slug = brand["meta"].get("slug") or args.brand.parent.name
    out = args.out or (ROOT / "out" / slug)
    out.mkdir(parents=True, exist_ok=True)

    html, files, links = hub_html(brand, args.brand.parent)
    path = out / f"{slug}-brand-hub.html"
    path.write_text(html, encoding="utf-8")
    print(f"hub    {files} assets, {links} downloads, "
          f"{path.stat().st_size / 1048576:.1f} MB -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
