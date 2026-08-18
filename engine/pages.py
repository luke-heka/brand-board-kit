"""Page renderers — one function per page type.

Every page returns a complete <section class="page"> string. Layout lives in
templates/deck.css; these functions only decide what goes in which slot.

Images are inlined as data URIs. Chromium blocks file:// subresources under
set_content, and a deck that silently drops its own logo is worse than one that
fails loudly, so missing assets raise.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

MAX_TOC_DESC = 2  # lines, matching the source deck


class PageError(RuntimeError):
    """A page declared something the renderer cannot build, said in plain words."""


class AssetError(RuntimeError):
    pass


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def asset(path: str | None, root: Path) -> str:
    """Inline an image as a data URI. SVG is passed through as utf-8."""
    if not path:
        raise AssetError("an image was requested but no path was given")
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    if not p.exists():
        raise AssetError(f"asset not found: {p}")
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if p.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return 1.0
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in (r, g, b)]
    return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + .05) / (lo + .05)


def readable_on(hex_colour: str, *candidates: str) -> str:
    """Pick whichever of the brand's own colours a swatch can actually carry.

    Two failures live here. The first was branching on the swatch's luminance and
    returning ink for anything pale, which assumes ink is the dark one. The second
    is subtler: on a light-on-dark brand, ink and the light ink are often the SAME
    colour, so a two-way choice offers no dark option at all and a pale swatch
    still loses its label. Pass the brand's grounds as candidates too, and take
    the best contrast of the lot. This never mixes a colour the brand has not got.
    """
    usable = [c for c in candidates if c]
    if not usable:
        return "#000000"
    return max(usable, key=lambda c: contrast(c, hex_colour))


def _is_pale(hex_colour: str) -> bool:
    return _luminance(hex_colour) > 0.88


def _aspect(path: str, root: Path) -> float | None:
    """Width divided by height for an asset, or None if it cannot be read."""
    f = Path(path)
    if not f.is_absolute():
        f = root / f
    if not f.exists():
        return None
    if f.suffix.lower() == ".svg":
        head = f.read_text(encoding="utf-8", errors="replace")[:2000]
        m = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', head)
        if m:
            w, h = float(m.group(1)), float(m.group(2))
            return w / h if h else None
        return None
    try:
        from PIL import Image
        with Image.open(f) as im:
            return im.width / im.height
    except Exception:
        return None


def footer(ctx: dict, page_no: int) -> str:
    m = ctx["meta"]
    legal = f"© {esc(m.get('year', ''))} / {esc(m.get('legal', 'All rights reserved'))}"
    return (
        '<div class="footer">'
        f'<span class="footer__brand">{esc(m["wordmark"])}</span>'
        '<span class="footer__right">'
        f'<span class="footer__legal">{legal}</span>'
        f'<span class="footer__page">{page_no:02d}</span>'
        '</span></div>'
    )


def shell(inner: str, ctx: dict, page_no: int, *, modifier: str = "",
          with_footer: bool = True) -> str:
    cls = f"page {modifier}".strip()
    foot = footer(ctx, page_no) if with_footer else ""
    return f'<section class="{cls}">{inner}{foot}</section>'


# --------------------------------------------------------------------------
# structural pages
# --------------------------------------------------------------------------

def cover(page: dict, ctx: dict, n: int) -> str:
    m = ctx["meta"]
    mark = ""
    if page.get("mark"):
        mark = f'<img class="cover__mark" src="{asset(page["mark"], ctx["root"])}" alt="">'
    inner = (
        '<div class="cover">'
        f'<div class="t-display">{esc(m["name"])}</div>'
        f'<div class="t-panel muted cover__type">{esc(m.get("document", "Brand Guideline"))}</div>'
        '</div>' + mark
    )
    legal = f"© {esc(m.get('year', ''))} / {esc(m.get('legal', 'All rights reserved'))}"
    inner += ('<div class="footer"><span class="footer__legal">' + legal + '</span></div>')
    return shell(inner, ctx, n, modifier="page--dark", with_footer=False)


def toc(page: dict, ctx: dict, n: int) -> str:
    rows = []
    for i, s in enumerate(page["entries"], start=1):
        rows.append(
            '<div class="toc__row">'
            f'<div class="toc__num">{i:02d}</div>'
            f'<div class="toc__name">{esc(s["title"])}</div>'
            f'<div class="toc__desc">{esc(s["summary"])}</div>'
            f'<div class="toc__pages">{s["first"]:02d} - {s["last"]:02d}</div>'
            '</div>'
        )
    inner = ('<div class="toc"><div class="toc__label">Table of contents</div>'
             f'<div class="toc__rows">{"".join(rows)}</div></div>')
    return shell(inner, ctx, n)


def divider(page: dict, ctx: dict, n: int) -> str:
    """Full-bleed dark, title top-left, an outlined numeral filling the corner."""
    inner = (
        f'<div class="divider__title t-display">{esc(page["title"])}</div>'
        f'<div class="divider__num">{page["index"]:02d}</div>'
    )
    legal = (f"© {esc(ctx['meta'].get('year', ''))} / "
             f"{esc(ctx['meta'].get('legal', 'All rights reserved'))}")
    inner += f'<div class="footer"><span class="footer__legal">{legal}</span></div>'
    return shell(inner, ctx, n, modifier="page--dark", with_footer=False)


def closing(page: dict, ctx: dict, n: int) -> str:
    inner = f'<div class="closing"><div class="t-display">{esc(page.get("title", "Thank you"))}</div></div>'
    legal = (f"© {esc(ctx['meta'].get('year', ''))} / "
             f"{esc(ctx['meta'].get('legal', 'All rights reserved'))}")
    inner += f'<div class="footer"><span class="footer__legal">{legal}</span></div>'
    return shell(inner, ctx, n, modifier="page--dark", with_footer=False)


# --------------------------------------------------------------------------
# the two-column workhorse
# --------------------------------------------------------------------------

def content(title: str, caption_title: str, caption_body: str, panel_html: str,
            ctx: dict, n: int, *, panel_class: str = "") -> str:
    cap = ""
    if caption_title or caption_body:
        cap = ('<div class="content__caption">'
               + (f'<h3>{esc(caption_title)}</h3>' if caption_title else '')
               + (f'<p>{esc(caption_body)}</p>' if caption_body else '')
               + '</div>')
    # The title column is 424px wide. "Components" sets at roughly 463px at the
    # display size, so a long title has to step down the ramp, not wrap under
    # the panel and lose its own letters.
    step = "t-display" if len(title) <= 9 else ("t-section" if len(title) <= 17 else "t-panel")
    inner = (
        '<div class="content">'
        f'<div class="content__title {step}">{esc(title)}</div>'
        + cap +
        f'<div class="panel {panel_class}">{panel_html}</div>'
        '</div>'
    )
    return shell(inner, ctx, n)


def overview(page: dict, ctx: dict, n: int) -> str:
    """Two text columns, no card.

    The source deck runs this page as plain columns across the sheet, and it is
    right to: a single 1296px column of 17px body is a 150-character measure,
    which nobody reads.
    """
    blocks = "".join(
        '<div class="ovblock">'
        f'<h3 class="t-card">{esc(b["title"])}</h3>'
        f'<p class="t-body muted">{esc(b["body"])}</p>'
        '</div>'
        for b in page["blocks"]
    )
    cols = min(len(page["blocks"]), 3) or 1
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="overview" style="grid-template-columns:repeat({cols},1fr)">'
                   f'{blocks}</div>', ctx, n,
                   panel_class="panel--plain panel--top")


# --------------------------------------------------------------------------
# logo
# --------------------------------------------------------------------------

def lockup(page: dict, ctx: dict, n: int) -> str:
    src = asset(page["src"], ctx["root"])
    cls = {"dark": "panel--dark", "accent": "panel--accent"}.get(page.get("ground", ""), "")
    panel = f'<img class="lockup" src="{src}" alt="{esc(page.get("variant", "logo"))}">'
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class=cls)


def marks(page: dict, ctx: dict, n: int) -> str:
    # A paper mark on a paper panel is invisible, which is correct behaviour and
    # a useless tile. Each mark can name the ground it is meant to be seen on.
    grounds = {"dark": "markrow__i--dark", "accent": "markrow__i--accent"}
    items = "".join(
        f'<div class="markrow__i {grounds.get(m.get("ground", ""), "")}">'
        f'<img src="{asset(m["src"], ctx["root"])}" alt="{esc(m["label"])}">'
        f'<span>{esc(m["label"])}</span>'
        '</div>'
        for m in page["marks"]
    )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="markrow">{items}</div>', ctx, n)


def clearspace(page: dict, ctx: dict, n: int) -> str:
    """The measure is drawn to scale, not described in prose."""
    src = asset(page["src"], ctx["root"])
    h = int(page.get("markHeight", 200))
    ratio_v = page.get("ratioValue", 0.25)

    aspect = _aspect(page["src"], ctx["root"])
    if aspect:
        shape = ctx.get("shape", {})
        inner_w = shape.get("panelWidth", 1296) - 2 * 56       # panel padding
        inner_h = shape.get("panelHeight", 824) - 2 * 56
        # width  = h*aspect + 2*pad + 2*tag,  with pad and tag both linear in h
        pad_f = ratio_v
        tag_f = max(pad_f * 0.55, 0.0) + pad_f * 0.30
        h = int(min(h,
                    inner_w / (aspect + 2 * pad_f + 2 * tag_f),
                    inner_h / (1 + 2 * pad_f + 2 * tag_f)))
    pad = round(h * ratio_v)
    ratio = esc(page.get("ratio", "1/4"))
    off = max(round(pad * 0.55), 26)     # how far the measure sits outside the box
    tag = off + round(pad * 0.30) + 14   # the label clears its own rule
    panel = (
        f'<div class="clear" style="position:relative;margin:{tag}px {tag}px 0 {tag}px">'
        f'  <div class="clear__ghost" style="position:absolute;inset:0"></div>'
        f'  <div style="padding:{pad}px">'
        f'    <img src="{src}" style="height:{h}px;display:block" alt="">'
        f'  </div>'
        # vertical measure, with a leader so it visibly spans the gap
        f'  <div style="position:absolute;left:-{off}px;top:0;height:{pad}px;width:1px;'
        f'background:var(--accent)"></div>'
        f'  <div style="position:absolute;left:-{off}px;top:0;width:{off}px;height:1px;'
        f'background:var(--accent);opacity:.45"></div>'
        f'  <div style="position:absolute;left:-{off}px;top:{pad}px;width:{off}px;height:1px;'
        f'background:var(--accent);opacity:.45"></div>'
        f'  <div style="position:absolute;left:-{tag}px;top:{max(pad // 2 - 10, 0)}px" '
        f'class="clear__tag">{ratio}</div>'
        # horizontal measure
        f'  <div style="position:absolute;top:-{off}px;left:0;width:{pad}px;height:1px;'
        f'background:var(--accent)"></div>'
        f'  <div style="position:absolute;top:-{off}px;left:0;width:1px;height:{off}px;'
        f'background:var(--accent);opacity:.45"></div>'
        f'  <div style="position:absolute;top:-{off}px;left:{pad}px;width:1px;height:{off}px;'
        f'background:var(--accent);opacity:.45"></div>'
        f'  <div style="position:absolute;top:-{tag}px;left:{max(pad // 2 - 10, 0)}px" '
        f'class="clear__tag">{ratio}</div>'
        f'</div>'
    )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--pad")


_X = ('<svg class="dont__x" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      'stroke-width="3" stroke-linecap="round" style="color:var(--accent)">'
      '<path d="M5 5l14 14M19 5L5 19"/></svg>')


def misuse(page: dict, ctx: dict, n: int) -> str:
    cells = []
    for c in page["cells"]:
        art = (f'<img src="{asset(c["src"], ctx["root"])}" style="{c.get("style", "")}" alt="">'
               if c.get("src") else f'<span class="t-card">{esc(c.get("glyph", ""))}</span>')
        art_style = ""
        if c.get("bg"):
            art_style = (f' style="background:url({asset(c["bg"], ctx["root"])}) center/cover;'
                         f'padding:18px 26px;border-radius:12px"')
        cells.append(
            f'<div class="dont__cell">{_X}'
            f'<div class="dont__art"{art_style}>{art}</div>'
            f'<div class="dont__cap">{esc(c["rule"])}</div></div>'
        )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="dont">{"".join(cells)}</div>', ctx, n,
                   panel_class="panel--pad")


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

def _swatch_hex(c: dict, pal: dict) -> str:
    """A colour entry names a palette key, or states its own hex.

    `{"name": "Accent", "token": "accent"}` reads the live palette, so changing
    `palette.accent` changes the colour page too. A literal `hex` still works for
    values that are genuinely not in the core palette, a hairline or a tint.
    Restating a palette value as a literal is what let a deck show one accent on
    its colour page and a different one everywhere else.
    """
    tok = c.get("token")
    if tok:
        if tok not in pal:
            raise AssetError(
                f"colour token '{tok}' is not in the palette. "
                f"Available: {', '.join(sorted(pal))}")
        return pal[tok]
    if "hex" not in c:
        raise AssetError(
            f"colour entry {c.get('name', '(unnamed)')!r} needs either a 'token' "
            f"naming a palette key, or a literal 'hex'")
    return c["hex"]


def colour_stack(page: dict, ctx: dict, n: int) -> str:
    pal = ctx["palette"]
    label_pool = (pal["ink"], pal["inkOnDark"], pal["canvas"], pal["groundDark"])
    bars = []
    for c in page["colours"]:
        hexv = _swatch_hex(c, pal)
        label = readable_on(hexv, *label_pool)
        border = " swatch--bordered" if _is_pale(hexv) else ""
        bars.append(
            f'<div class="swatch{border}" style="background:{esc(hexv)}">'
            f'<div class="swatch__label" style="color:{label}">'
            f'<b>{esc(c.get("name", "HEX"))}</b><span>{esc(hexv.upper())}</span>'
            f'</div></div>'
        )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="swatches">{"".join(bars)}</div>', ctx, n,
                   panel_class="panel--pad")


def colour_ramp(page: dict, ctx: dict, n: int) -> str:
    pal = ctx["palette"]
    chips = []
    for c in page["colours"]:
        hexv = _swatch_hex(c, pal)
        border = " style=\"box-shadow:inset 0 0 0 1px var(--hairline)\"" if _is_pale(hexv) else ""
        chips.append(
            '<div>'
            f'<div class="ramp__chip" style="background:{esc(hexv)}"{border}></div>'
            f'<div class="ramp__name">{esc(c.get("name", ""))}</div>'
            f'<div class="ramp__hex">{esc(hexv.upper())}</div>'
            '</div>'
        )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="ramp">{"".join(chips)}</div>', ctx, n,
                   panel_class="panel--pad")


# --------------------------------------------------------------------------
# typography
# --------------------------------------------------------------------------

ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
FIGS = "0123456789 (!?&@)"


def typeface(page: dict, ctx: dict, n: int) -> str:
    """Weight specimens, plus the axis ramp when the face is variable.

    Three shipping weights that sit 100 units apart look identical in a plain
    alphabet row. The ramp is what makes a variable face legible as a system:
    the same word climbing the axis, with the shipping weights marked.
    """
    fam = page["family"]
    ship = {w["value"] for w in page["weights"]}
    bits = []

    if page.get("showName", True):
        bits.append(f'<div class="t-card" style="margin-bottom:30px">{esc(fam)}</div>')

    axis = page.get("axis")
    if axis:
        lo, hi, steps = axis.get("min", 200), axis.get("max", 800), axis.get("steps", 7)
        word = esc(axis.get("word", fam))
        step = (hi - lo) / max(steps - 1, 1)
        # The shipping weights are forced into the ramp. A 585 that is not on an
        # even 100 would otherwise be silently absent from the page that exists
        # to prove it, and a near neighbour marked in its place would be a lie.
        values = sorted({round(lo + step * i) for i in range(steps)} |
                        {w for w in ship if lo <= w <= hi})
        rows = []
        for v in values:
            mark = ' class="axis__row axis__row--ship"' if v in ship else ' class="axis__row"'
            rows.append(
                f'<div{mark}><span class="axis__v">{v}</span>'
                f'<b style="font-family:\'{esc(fam)}\';font-weight:{v};'
                f'font-variation-settings:\'wght\' {v}">{word}</b></div>')
        bits.append(f'<div class="axis">{"".join(rows)}</div>')

    # With the ramp above, the alphabet rows are a reference, not the argument,
    # so they run on one line and give the page room to breathe.
    compact = bool(axis)
    rows = []
    for w in page["weights"]:
        spec = f'{ALPHA}{esc(FIGS)}' if compact else f'{ALPHA}<br>{LOWER}{esc(FIGS)}'
        cls = "weights__spec weights__spec--compact" if compact else "weights__spec"
        rows.append(
            '<div class="weights__row">'
            f'<div class="weights__name">{esc(w["name"])}</div>'
            f'<div class="{cls}" style="font-family:\'{esc(fam)}\';'
            f'font-weight:{w["value"]};font-variation-settings:\'wght\' {w["value"]}">'
            f'{spec}</div>'
            '</div>'
        )
    gap = ' style="gap:16px"' if compact else ''
    bits.append(f'<div class="weights"{gap}>{"".join(rows)}</div>')

    panel = f'<div style="width:100%">{"".join(bits)}</div>'
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--pad")


def typescale(page: dict, ctx: dict, n: int) -> str:
    """Every specimen is set at its true px value — the page is the proof."""
    rows = []
    for s in page["scale"]:
        px = s["px"]
        rows.append(
            '<div class="scale__row">'
            f'<div class="scale__px">{px} px</div>'
            f'<div class="scale__spec" style="font-size:{px}px;'
            f'letter-spacing:{esc(s.get("tracking", "-0.04em"))}">{esc(s["role"])}</div>'
            '</div>'
        )
    panel = f'<div class="scale">{"".join(rows)}</div>'
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--pad")


# --------------------------------------------------------------------------
# imagery, motion, components, applications
# --------------------------------------------------------------------------

def imagery(page: dict, ctx: dict, n: int) -> str:
    regs = page["registers"]
    cols = min(len(regs), 2 if len(regs) <= 4 else 3)
    cells = "".join(
        '<div class="register">'
        f'<div class="register__img" style="background-image:url({asset(r["src"], ctx["root"])})"></div>'
        f'<div class="register__meta"><b>{esc(r["name"])}</b><span>{esc(r["direction"])}</span></div>'
        '</div>'
        for r in regs
    )
    rows = -(-len(regs) // cols)
    style = (f'grid-template-columns:repeat({cols},1fr);'
             f'grid-template-rows:repeat({rows},1fr)')
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="registers" style="{style}">{cells}</div>', ctx, n,
                   panel_class="panel--pad")


def _curve_svg(points: str) -> str:
    """Draw a cubic-bezier easing curve from its four control numbers."""
    x1, y1, x2, y2 = (float(v) for v in points.split(","))
    w, h = 240.0, 150.0
    px = lambda x: x * w
    py = lambda y: h - y * h
    return (
        f'<svg viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none">'
        f'<path d="M0 {h:.0f} L{w:.0f} 0" stroke="var(--hairline)" stroke-width="1" fill="none"/>'
        f'<path d="M0 {h:.0f} C{px(x1):.1f} {py(y1):.1f} {px(x2):.1f} {py(y2):.1f} {w:.0f} 0" '
        f'stroke="var(--accent)" stroke-width="3" fill="none" stroke-linecap="round"/>'
        f'</svg>'
    )


def motion(page: dict, ctx: dict, n: int) -> str:
    curves = "".join(
        f'<div class="curve">{_curve_svg(c["points"])}'
        f'<b>{esc(c["name"])}</b><code>cubic-bezier({esc(c["points"])})</code></div>'
        for c in page["curves"]
    )
    durs = "".join(
        f'<div class="duration"><b>{esc(d["ms"])}ms</b><span>{esc(d["use"])}</span></div>'
        for d in page.get("durations", [])
    )
    panel = (f'<div style="width:100%"><div class="curves">{curves}</div>'
             + (f'<div class="durations">{durs}</div>' if durs else '') + '</div>')
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--pad")


def components(page: dict, ctx: dict, n: int) -> str:
    bits = []
    for item in page["items"]:
        kind = item["kind"]
        if kind == "button":
            variant = item.get("variant", "primary")
            dot = '<span class="btn__dot"></span>' if item.get("dot", True) else ''
            bits.append(f'<span class="btn btn--{esc(variant)}">{esc(item["label"])}{dot}</span>')
        elif kind == "field":
            bits.append(f'<span class="field">{esc(item["label"])}</span>')
        elif kind == "radii":
            cells = "".join(
                f'<div><div class="radii__i" style="border-radius:{r}px"></div>'
                f'<span class="radii__l">{r}px {esc(lbl)}</span></div>'
                for r, lbl in item["values"]
            )
            bits.append(f'<div class="radii">{cells}</div>')
        elif kind == "swatchRow":
            chips = "".join(
                f'<span style="width:64px;height:64px;border-radius:50%;background:{esc(h)};display:block"></span>'
                for h in item["colours"])
            bits.append(f'<div style="display:flex;gap:14px">{chips}</div>')
        else:
            # Dropping it in silence contradicts how every other missing thing
            # here behaves, and the page just quietly loses a component.
            raise KeyError(
                f"unknown component item kind '{kind}' — known: button, field, radii, swatchRow")
    panel = f'<div class="specimens">{"".join(bits)}</div>'
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--pad")


def applications(page: dict, ctx: dict, n: int) -> str:
    items = page["items"]
    cols = page.get("columns") or (2 if len(items) <= 4 else 3)
    rows = -(-len(items) // cols)
    cells = "".join(
        f'<div class="sheet__cell" style="background-image:url({asset(i["src"], ctx["root"])})"></div>'
        for i in items
    )
    style = f'grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat({rows},1fr)'
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="sheet" style="{style}">{cells}</div>', ctx, n,
                   panel_class="panel--pad")


def prose(page: dict, ctx: dict, n: int) -> str:
    """A panel of plain statements — used for rules, do/don't lists, voice notes."""
    items = "".join(
        f'<div style="padding:26px 0;border-top:1px solid var(--hairline)">'
        f'<div class="t-body">{esc(i)}</div></div>'
        for i in page["items"]
    )
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div style="width:100%">{items}</div>', ctx, n, panel_class="panel--pad")


def dosdonts(page: dict, ctx: dict, n: int) -> str:
    """Do on the left, don't on the right. The short deck's most useful page."""
    def col(title: str, items: list[str], tone: str) -> str:
        rows = "".join(f'<li>{esc(i)}</li>' for i in items)
        return (f'<div class="dd dd--{tone}"><h4>{esc(title)}</h4>'
                f'<ul>{rows}</ul></div>')
    panel = ('<div class="ddwrap">'
             + col(page.get("doLabel", "Do"), page.get("do", []), "yes")
             + col(page.get("dontLabel", "Don't"), page.get("dont", []), "no")
             + '</div>')
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   panel, ctx, n, panel_class="panel--plain panel--top")


def files(page: dict, ctx: dict, n: int) -> str:
    """What is in the kit, as a plain two-column list."""
    rows = "".join(
        f'<div class="filerow"><span>{esc(f["name"])}</span>'
        f'<span class="muted">{esc(f["what"])}</span></div>'
        for f in page["items"])
    return content(page["section"], page.get("captionTitle", ""), page.get("caption", ""),
                   f'<div class="filelist">{rows}</div>', ctx, n,
                   panel_class="panel--pad panel--top")


RENDERERS = {
    "cover": cover, "toc": toc, "divider": divider, "closing": closing,
    "overview": overview, "lockup": lockup, "marks": marks,
    "clearspace": clearspace, "misuse": misuse,
    "colourStack": colour_stack, "colourRamp": colour_ramp,
    "typeface": typeface, "typescale": typescale,
    "imagery": imagery, "motion": motion, "components": components,
    "applications": applications, "prose": prose,
    "dosdonts": dosdonts, "files": files,
}


def render(page: dict, ctx: dict, n: int) -> str:
    kind = page["kind"]
    if kind not in RENDERERS:
        raise KeyError(f"unknown page kind '{kind}' — known: {', '.join(sorted(RENDERERS))}")
    try:
        return RENDERERS[kind](page, ctx, n)
    except KeyError as e:
        # An unknown key is ignored in silence; its missing partner is fatal.
        # A bare KeyError names the key and nothing else, which leaves the
        # reader hunting a 20-page document for the row that caused it.
        missing = e.args[0] if e.args else "?"
        raise PageError(
            f"page {n} ({kind}) in section '{page.get('section', '?')}' is missing the "
            f"required key '{missing}'. Every key each kind reads is listed in "
            f"docs/PAGE-KINDS.md."
        ) from None
