"""Generate a brand's asset set from its tokens.

An asset is a template plus its values, not a picture. The template is HTML
rendered by the same Chromium the decks use; the values are a small JSON block
holding the headline and whatever else that template reads. Change a value,
re-render, and the asset is different without anyone opening a design tool.

    python3 -m engine.assets brands/<slug>/brand.json            # build them all
    python3 -m engine.assets brands/<slug>/brand.json --only ig-post

Each asset writes three files side by side, so the render always has its source
next to it:

    <name>.png    the render, full resolution
    <name>.html   the source, self-contained, opens in a browser
    <name>.json   the values, the only thing normally edited

Templates live in `engine/templates_assets/`. Adding one is adding a function and
a row in its registry — nothing here needs to change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import theme as theme_mod
from .pages import asset as inline_asset
from .pages import esc  # noqa: F401  (templates import it from here)
from .templates_assets import REGISTRY

# Text that does not fit should get smaller, not get an ellipsis. A headline
# clipped mid-word reads as broken; the same words a size down read as designed.
# This runs before the screenshot, so the PNG and the HTML always agree.
_FIT = """
(function(){
  var sel = '.a-head,.a-quote,.a-stat,[data-fit]';
  document.querySelectorAll(sel).forEach(function(el){
    var cs = getComputedStyle(el);
    // An element free to grow cannot overflow, and a 3px line-height rounding
    // difference is not overflow. Only shrink what is genuinely boxed in.
    var boxed = cs.overflow === 'hidden' || cs.overflowY === 'hidden' ||
                cs.webkitLineClamp !== 'none' ||
                (cs.maxHeight !== 'none' && cs.maxHeight !== '') ||
                (cs.height !== 'auto' && cs.height !== '');
    // Text can also spill past the canvas itself without its own box ever
    // reporting overflow, which is how a 728x90 leaderboard ended up with a
    // headline printed above the banner.
    var canvas = document.querySelector('.canvas');
    function spills(){
      if(!canvas) return false;
      var a = el.getBoundingClientRect(), c = canvas.getBoundingClientRect();
      return a.top < c.top - 1 || a.bottom > c.bottom + 1 ||
             a.left < c.left - 1 || a.right > c.right + 1;
    }
    if(!boxed && !spills()) return;
    var size = parseFloat(cs.fontSize), guard = 0;
    function over(){
      return el.scrollHeight > el.clientHeight + 4 ||
             el.scrollWidth  > el.clientWidth + 4 || spills();
    }
    while(over() && size > 8 && guard++ < 120){
      size *= 0.96; el.style.fontSize = size + 'px';
    }
  });
})();
"""


ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        sys.exit("Playwright is not installed. From this folder run:\n"
                 "  python3 -m venv .venv && source .venv/bin/activate\n"
                 "  pip install playwright pypdf && playwright install chromium")
    return sync_playwright()


def document(brand: dict, root: Path, spec: dict, values: dict) -> str:
    """One self-contained HTML file for one asset."""
    css = theme_mod.stylesheet(brand, [TEMPLATES / "asset.css"], root=root)
    body = spec["fn"](brand, values, root)
    w, h = spec["w"], spec["h"]
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<title>{esc(values.get("_asset", spec["id"]))}</title><style>'
        f'@page{{size:{w}px {h}px;margin:0}}'
        f'html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden}}'
        f'{css}'
        f'.canvas{{width:{w}px;height:{h}px;position:relative;overflow:hidden}}'
        f'</style></head><body><div class="canvas">{body}</div>'
        f'<script>{_FIT}</script></body></html>')


def build(brand: dict, root: Path, out: Path, want: str | None = None) -> list[dict]:
    """Render every asset the brand declares. Returns what was written."""
    declared = brand.get("assetSet") or []
    if not declared:
        return []

    jobs = []
    for item in declared:
        tid = item["template"]
        if want and tid != want:
            continue
        spec = REGISTRY.get(tid)
        if not spec:
            raise KeyError(f"unknown asset template '{tid}' — known: "
                           f"{', '.join(sorted(REGISTRY))}")
        jobs.append((spec, item))
    if not jobs:
        return []

    made = []
    with _browser() as p:
        browser = p.chromium.launch(headless=True)
        for spec, item in jobs:
            values = dict(item.get("values") or {})
            values.setdefault("_asset", item.get("name", spec["id"]))
            group = out / spec["group"]
            group.mkdir(parents=True, exist_ok=True)
            stem = group / item.get("name", spec["id"])

            html = document(brand, root, spec, values)
            stem.with_suffix(".html").write_text(html, encoding="utf-8")
            stem.with_suffix(".json").write_text(
                json.dumps({"template": spec["id"], "values": values},
                           indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            page = browser.new_page(viewport={"width": spec["w"], "height": spec["h"]},
                                    device_scale_factor=spec.get("scale", 2))
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(250)
            page.screenshot(path=str(stem.with_suffix(".png")),
                            clip={"x": 0, "y": 0, "width": spec["w"], "height": spec["h"]})
            page.close()
            made.append({"id": spec["id"], "group": spec["group"],
                         "name": stem.name, "w": spec["w"], "h": spec["h"]})
        browser.close()

    # Names are derived from the values, so changing a headline changes the
    # filename and the old render survives beside the new one. Sweeping keeps
    # the folder equal to what the brand actually declares.
    if want is None:
        keep = {f"{m['group']}/{m['name']}" for m in made}
        for f in sorted(out.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(out)
            stem = f"{rel.parent.as_posix()}/{f.stem}"
            if stem not in keep:
                f.unlink()
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate a brand's asset set.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path, help="defaults to <brand>/assets/generated")
    ap.add_argument("--only", help="build one template id")
    ap.add_argument("--list", action="store_true", help="list the template ids")
    args = ap.parse_args(argv)

    if args.list:
        for tid, spec in sorted(REGISTRY.items()):
            print(f"  {tid:26s} {spec['w']:>5}x{spec['h']:<5}  {spec['group']}")
        return 0

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    root = args.brand.parent
    out = args.out or (root / "assets" / "generated")
    made = build(brand, root, out, args.only)

    if not made:
        print("nothing to build: the brand file declares no assetSet")
        return 0
    groups = {}
    for m in made:
        groups[m["group"]] = groups.get(m["group"], 0) + 1
    print(f"assets {len(made)} rendered into {len(groups)} groups -> {out}")
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"   {n:4d}  {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
