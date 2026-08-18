"""The brand board — the whole system on one surface.

This is the Figma-board deliverable, rebuilt so it needs no Figma. Same idea as
the ecosystem file: titled sections on one canvas, each holding the real
artwork, so a person can see the entire identity by looking rather than paging.

The deck argues the system one page at a time. The board proves it all at once.
"""

from __future__ import annotations

from pathlib import Path

from .pages import _swatch_hex, asset, esc, readable_on, _is_pale, _curve_svg, ALPHA, LOWER

BOARD_W = 2560


def _card(title: str, body: str, *, span: int = 4, tone: str = "") -> str:
    cls = f"card {tone}".strip()
    return (f'<section class="{cls}" style="grid-column:span {span}">'
            f'<h2 class="card__title">{esc(title)}</h2>'
            f'<div class="card__body">{body}</div></section>')


def _header(brand: dict, root: Path) -> str:
    m = brand["meta"]
    logo = ""
    if m.get("boardMark") or m.get("coverMark"):
        src = asset(m.get("boardMark") or m.get("coverMark"), root)
        logo = f'<img class="board__mark" src="{src}" alt="">'
    line = m.get("line", "")
    return (
        '<header class="board__head">'
        f'<div>{logo}<div class="board__name">{esc(m["name"])}</div>'
        f'<div class="board__doc">{esc(m.get("boardTitle", "Brand Board"))}</div></div>'
        f'<div class="board__line">{esc(line)}</div>'
        '</header>'
    )


def _logo_card(sec: dict, root: Path) -> str:
    lockups = [p for p in sec.get("pages", []) if p["kind"] == "lockup"]
    marks = next((p for p in sec.get("pages", []) if p["kind"] == "marks"), None)
    tiles = []
    for lk in lockups:
        ground = lk.get("ground", "canvas")
        cls = {"dark": "tile--dark", "accent": "tile--accent"}.get(ground, "")
        tiles.append(
            f'<div class="tile {cls}">'
            f'<img src="{asset(lk["src"], root)}" alt="">'
            f'<span class="tile__cap">{esc(lk.get("variant", ""))}</span></div>'
        )
    marks_html = ""
    if marks:
        grounds = {"dark": "markchip--dark", "accent": "markchip--accent"}
        items = "".join(
            f'<div class="markchip {grounds.get(m.get("ground", ""), "")}">'
            f'<img src="{asset(m["src"], root)}" alt="">'
            f'<span>{esc(m["label"])}</span></div>'
            for m in marks["marks"]
        )
        marks_html = f'<div class="markchips">{items}</div>'
    return _card("Logo", f'<div class="tiles">{"".join(tiles)}</div>{marks_html}', span=6)


def _colour_card(sec: dict, palette: dict) -> str:
    pool = (palette["ink"], palette["inkOnDark"],
            palette["canvas"], palette["groundDark"])
    groups = []
    for p in sec.get("pages", []):
        if p["kind"] not in ("colourStack", "colourRamp"):
            continue
        resolved = [(c, _swatch_hex(c, palette)) for c in p["colours"]]
        chips = "".join(
            f'<div class="chip{" chip--pale" if _is_pale(h) else ""}" '
            f'style="background:{esc(h)}">'
            f'<span style="color:{readable_on(h, *pool)}">'
            f'{esc(c.get("name", ""))}<br><em>{esc(h.upper())}</em></span></div>'
            for c, h in resolved
        )
        groups.append(f'<div class="chipgroup"><h3>{esc(p.get("captionTitle", "Colour"))}</h3>'
                      f'<div class="chips">{chips}</div></div>')
    return _card("Colour", "".join(groups), span=6)


def _type_card(sec: dict) -> str:
    faces = [p for p in sec.get("pages", []) if p["kind"] == "typeface"]
    scale = next((p for p in sec.get("pages", []) if p["kind"] == "typescale"), None)
    bits = []
    # A brand with a display face and a body face has to show both, or the board
    # is only half the type system.
    for face in faces:
        fam = face["family"]
        bits.append(f'<div class="specimen" style="font-family:\'{esc(fam)}\'">'
                    f'<div class="specimen__big">{esc(fam)}</div>'
                    f'<div class="specimen__alpha">{ALPHA}<br>{LOWER}</div></div>')
        rows = "".join(
            f'<div class="wrow"><span>{esc(w["name"])}</span>'
            f'<b style="font-weight:{w["value"]};font-variation-settings:\'wght\' {w["value"]};'
            f'font-family:\'{esc(fam)}\'">The quick brown fox</b></div>'
            for w in face["weights"])
        bits.append(f'<div class="wrows">{rows}</div>')
    if scale:
        rows = "".join(
            f'<div class="srow"><span>{s["px"]}</span>'
            f'<b style="font-size:{min(s["px"], 56)}px;letter-spacing:{esc(s.get("tracking", "-0.04em"))}">'
            f'{esc(s["role"])}</b></div>'
            for s in scale["scale"])
        bits.append(f'<div class="srows">{rows}</div>')
    return _card("Typography", "".join(bits), span=6)


def _imagery_card(sec: dict, root: Path) -> str:
    page = next((p for p in sec.get("pages", []) if p["kind"] == "imagery"), None)
    if not page:
        return ""
    cells = "".join(
        f'<div class="shot"><div class="shot__img" style="background-image:url({asset(r["src"], root)})"></div>'
        f'<b>{esc(r["name"])}</b><span>{esc(r["direction"])}</span></div>'
        for r in page["registers"])
    return _card("Imagery", f'<div class="shots">{cells}</div>', span=6)


def _motion_card(sec: dict) -> str:
    page = next((p for p in sec.get("pages", []) if p["kind"] == "motion"), None)
    if not page:
        return ""
    curves = "".join(
        f'<div class="curve">{_curve_svg(c["points"])}<b>{esc(c["name"])}</b>'
        f'<code>cubic-bezier({esc(c["points"])})</code></div>'
        for c in page["curves"])
    durs = "".join(f'<span class="pill">{esc(d["ms"])}ms · {esc(d["use"])}</span>'
                   for d in page.get("durations", []))
    return _card("Motion", f'<div class="curves">{curves}</div><div class="pills">{durs}</div>', span=4)


def _components_card(sec: dict) -> str:
    page = next((p for p in sec.get("pages", []) if p["kind"] == "components"), None)
    if not page:
        return ""
    bits = []
    for item in page["items"]:
        if item["kind"] == "button":
            dot = '<span class="btn__dot"></span>' if item.get("dot", True) else ''
            bits.append(f'<span class="btn btn--{esc(item.get("variant", "primary"))}">'
                        f'{esc(item["label"])}{dot}</span>')
        elif item["kind"] == "field":
            bits.append(f'<span class="field">{esc(item["label"])}</span>')
        elif item["kind"] == "radii":
            cells = "".join(f'<div><div class="radii__i" style="border-radius:{r}px"></div>'
                            f'<span class="radii__l">{r}</span></div>'
                            for r, _ in item["values"])
            bits.append(f'<div class="radii">{cells}</div>')
    return _card("Components", f'<div class="specimens">{"".join(bits)}</div>', span=4)


def _applications_card(sec: dict, root: Path, title: str = "Applications") -> str:
    pages = [p for p in sec.get("pages", []) if p["kind"] == "applications"]
    if not pages:
        return ""
    page = pages[0]
    cells = "".join(
        f'<div class="app" style="background-image:url({asset(i["src"], root)})"></div>'
        for i in page["items"])
    return _card(title, f'<div class="apps">{cells}</div>', span=12)


def _story_card(sec: dict) -> str:
    page = next((p for p in sec.get("pages", []) if p["kind"] == "overview"), None)
    if not page:
        return ""
    blocks = "".join(f'<div class="story"><h3>{esc(b["title"])}</h3><p>{esc(b["body"])}</p></div>'
                     for b in page["blocks"])
    return _card(sec["title"], f'<div class="stories">{blocks}</div>', span=12)


BUILDERS = {
    "overview": lambda s, r, p: _story_card(s),
    "logo": lambda s, r, p: _logo_card(s, r),
    "colour": lambda s, r, p: _colour_card(s, p),
    "color": lambda s, r, p: _colour_card(s, p),
    "typography": lambda s, r, p: _type_card(s),
    "imagery": lambda s, r, p: _imagery_card(s, r),
    "motion": lambda s, r, p: _motion_card(s),
    "components": lambda s, r, p: _components_card(s),
    "applications": lambda s, r, p: _applications_card(s, r),
    "graphic": lambda s, r, p: _applications_card(s, r, title="Graphic elements"),
}


def build(brand: dict, root: Path) -> tuple[str, int, int]:
    """Return (html, width, nominal height). True height is measured at render."""
    from .theme import PALETTE_DEFAULTS
    palette = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    cards = []
    for sec in brand.get("sections", []):
        key = sec.get("id", sec["title"]).lower()
        fn = BUILDERS.get(key)
        if fn:
            html = fn(sec, root, palette)
            if html:
                cards.append(html)
    body = (f'<div class="board">{_header(brand, root)}'
            f'<div class="grid">{"".join(cards)}</div>'
            f'<footer class="board__foot">{esc(brand["meta"].get("wordmark", ""))} · '
            f'{esc(brand["meta"].get("boardTitle", "Brand Board"))} · '
            f'© {esc(brand["meta"].get("year", ""))}</footer></div>')
    return body, BOARD_W, 3200
