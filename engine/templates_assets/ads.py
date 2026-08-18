"""Paid media: the three placement ratios, the IAB display set, a lead card.

Two shapes of problem live here. The big placements are the social templates
with a mandatory button, so they lean on the `.a-*` classes and only tune the
base font size. The display set cannot: a 320x50 banner is smaller than the
padding `.a-pad` would give it, and `.a-head` at its natural size would be
taller than the whole unit. Those sizes get explicit pixels and a line clamp,
so a headline that is too long is trimmed rather than pushed off the canvas.
"""

from __future__ import annotations

from pathlib import Path

from ..pages import asset, esc
from ._lib import dot, logo

DISPLAY_CTA = "Learn more"

# A brand declares which ground each lockup was drawn for. These are the values
# a tone will accept, most specific first.
GROUNDS = {"light": (None, "light", "paper"), "dark": ("dark",), "accent": ("accent",)}


def _variant(tone: str) -> str:
    """Fallback when a brand labels its lockups but never says which ground."""
    return "primary" if tone == "light" else "reversed"


def _lockup(brand: dict, root: Path, tone: str, height: int) -> str:
    """The lockup drawn for this ground, chosen by ground and not by name.

    Asking for "reversed" put one brand's dark-ground lockup on a bright ad, and its
    ember disc vanished into the ember — the U simply stopped existing. The
    brand already records the ground each lockup belongs to, so read that.
    """
    for sec in brand.get("sections", []):
        if sec.get("id") != "logo":
            continue
        for p in sec.get("pages", []):
            if p.get("kind") == "lockup" and p.get("ground") in GROUNDS[tone]:
                return (f'<img class="a-logo" style="height:{height}px" '
                        f'src="{asset(p["src"], root)}" alt="">')
    return logo(brand, root, _variant(tone), height)


def _mark(brand: dict, root: Path, tone: str, size: int,
          align: str = "flex-start") -> str:
    """The lockup, held at its natural width.

    A bare `<img>` is a flex item, so a column stretches it edge to edge and the
    artwork centres itself inside that box. It reads as a deliberate centre and
    is not one, so every lockup in a column is pinned to the column's start. A
    bar wants the opposite: `center`, matching the copy beside it.
    """
    return (f'<div style="flex:none;align-self:{align}">'
            f'{_lockup(brand, root, tone, size)}</div>')


def _button(v: dict, size: int | None = None, default: str = DISPLAY_CTA) -> str:
    label = v.get("cta", default)
    if not label:
        return ""
    px = f' style="font-size:{size}px"' if size else ""
    return f'<span class="a-btn"{px}>{esc(label)}{dot()}</span>'


# --------------------------------------------------------------------------
# The big placements: square, portrait, landscape.
# --------------------------------------------------------------------------

def _ad(brand: dict, v: dict, root: Path, *, tone_default: str,
        pad: str, base: int, logo_h: int) -> str:
    tone = v.get("tone", tone_default)
    kicker = f'<div class="a-kicker">{esc(v["kicker"])}</div>' if v.get("kicker") else ""
    sub = f'<p class="a-sub">{esc(v["sub"])}</p>' if v.get("sub") else ""
    return (
        f'<div class="a-fill a-{tone} a-stack" style="padding:{pad};font-size:{base}px">'
        f'{_mark(brand, root, tone, logo_h)}'
        f'<div class="a-grow"></div>{kicker}'
        f'<h1 class="a-head">{esc(v.get("headline", ""))}</h1>{sub}'
        f'<div class="a-foot">{_button(v)}</div></div>')


def ad_square(brand, v, root):
    return _ad(brand, v, root, tone_default="light", pad="76px", base=16, logo_h=52)


def ad_portrait(brand, v, root):
    return _ad(brand, v, root, tone_default="dark", pad="84px", base=17, logo_h=56)


def ad_landscape(brand, v, root):
    # A 1200x628 unit is two thirds padding if the square's 7% is kept, so the
    # margins are set in pixels and the type is scaled down to match.
    return _ad(brand, v, root, tone_default="accent", pad="56px 72px", base=13, logo_h=44)


def lead_card(brand: dict, v: dict, root: Path) -> str:
    """The shape a lead-form ad uses: promise, three proofs, button."""
    tone = v.get("tone", "light")
    rows = "".join(
        f'<div style="display:flex;align-items:flex-start;gap:.7em;font-size:2.1em;'
        f'line-height:1.35;letter-spacing:-.03em;margin-top:.7em">'
        f'<span style="flex:none;opacity:.5;margin-top:.42em">{dot()}</span>'
        f'<span>{esc(line)}</span></div>'
        for line in (v.get("bullets") or [])[:3])
    kicker = f'<div class="a-kicker">{esc(v["kicker"])}</div>' if v.get("kicker") else ""
    return (
        f'<div class="a-fill a-{tone} a-stack a-pad" style="font-size:16px">'
        f'{_mark(brand, root, tone, 52)}'
        f'<div class="a-grow"></div>{kicker}'
        f'<h1 class="a-head">{esc(v.get("headline", ""))}</h1>'
        f'<div style="margin-top:.6em">{rows}</div>'
        f'<div class="a-foot">{_button(v)}</div></div>')


# --------------------------------------------------------------------------
# The IAB display set. Every size is small enough that the text has to be
# measured against the box rather than inherited from the deck's scale.
# --------------------------------------------------------------------------

def _headline(text: str, px: int, lines: int) -> str:
    if lines == 1:
        clip = "overflow:hidden"
    else:
        clip = "overflow:hidden;overflow-wrap:anywhere"
    return (f'<div style="font-family:var(--font-display);'
            f'font-weight:var(--display-weight);'
            f"font-variation-settings:'wght' var(--display-weight);"
            f'font-size:{px}px;line-height:1.06;letter-spacing:-.035em;{clip}" data-fit>'
            f'{text}</div>')


def _subline(text: str, px: int) -> str:
    return (f'<div style="font-size:{px}px;line-height:1.35;letter-spacing:-.02em;'
            f'opacity:.82;margin-top:{round(px * .5)}px;display:-webkit-box;'
            f'-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;'
            f'overflow-wrap:anywhere">{text}</div>')


def _display(brand: dict, v: dict, root: Path, *, axis: str, pad: str, gap: int,
             logo_h: int, head: int, lines: int, cta: int,
             sub: int | None = None, tone_default: str = "dark") -> str:
    tone = v.get("tone", tone_default)
    # No headline falls back to nothing, not to the wordmark: the lockup is
    # already on the unit, and the name twice is worse than a clean bar.
    block = _headline(esc(v["headline"]), head, lines) if v.get("headline") else ""
    if sub and v.get("sub"):
        block += _subline(esc(v["sub"]), sub)

    label = _button(v, cta)
    button = f'<div style="flex:none;display:flex">{label}</div>' if label else ""

    if axis == "stack":
        foot = (f'<div style="flex:none;display:flex;margin-top:{gap}px">{label}</div>'
                if label else "")
        return (f'<div class="a-fill a-{tone} a-stack" style="padding:{pad}">'
                f'{_mark(brand, root, tone, logo_h)}'
                f'<div class="a-grow"></div>{block}<div class="a-grow"></div>'
                f'{foot}</div>')
    if axis == "split":
        # Wide units read better with the lockup stacked over the copy, so the
        # left column keeps its full width for the headline.
        return (f'<div class="a-fill a-{tone} a-row" style="padding:{pad};gap:{gap}px">'
                f'<div style="flex:1 1 auto;min-width:0;display:flex;'
                f'flex-direction:column;justify-content:center">'
                f'{_mark(brand, root, tone, logo_h)}'
                f'<div style="height:{gap}px"></div>{block}</div>'
                f'{button}</div>')
    return (f'<div class="a-fill a-{tone} a-row" style="padding:{pad};gap:{gap}px">'
            f'{_mark(brand, root, tone, logo_h, "center")}'
            f'<div style="flex:1 1 auto;min-width:0">{block}</div>'
            f'{button}</div>')


def ad_300x250(brand, v, root):
    return _display(brand, v, root, axis="stack", pad="20px 22px", gap=11,
                    logo_h=20, head=27, lines=3, sub=13, cta=12, tone_default="dark")


def ad_728x90(brand, v, root):
    return _display(brand, v, root, axis="row", pad="0 24px", gap=18,
                    logo_h=26, head=26, lines=1, cta=13, tone_default="light")


def ad_160x600(brand, v, root):
    return _display(brand, v, root, axis="stack", pad="20px 16px", gap=9,
                    logo_h=18, head=22, lines=6, sub=12, cta=11, tone_default="dark")


def ad_300x600(brand, v, root):
    return _display(brand, v, root, axis="stack", pad="26px 24px", gap=14,
                    logo_h=24, head=34, lines=4, sub=14, cta=13, tone_default="accent")


def ad_970x250(brand, v, root):
    return _display(brand, v, root, axis="split", pad="24px 44px", gap=14,
                    logo_h=34, head=40, lines=2, sub=17, cta=17, tone_default="light")


def ad_320x50(brand, v, root):
    return _display(brand, v, root, axis="row", pad="0 12px", gap=9,
                    logo_h=13, head=15, lines=1, cta=10, tone_default="dark")


TEMPLATES = {
    "ad-square":    {"id": "ad-square",    "w": 1080, "h": 1080, "group": "ads",         "fn": ad_square},
    "ad-portrait":  {"id": "ad-portrait",  "w": 1080, "h": 1350, "group": "ads",         "fn": ad_portrait},
    "ad-landscape": {"id": "ad-landscape", "w": 1200, "h": 628,  "group": "ads",         "fn": ad_landscape},
    "ad-lead-card": {"id": "ad-lead-card", "w": 1080, "h": 1080, "group": "ads",         "fn": lead_card},
    "ad-300x250":   {"id": "ad-300x250",   "w": 300,  "h": 250,  "group": "ads-display", "fn": ad_300x250},
    "ad-728x90":    {"id": "ad-728x90",    "w": 728,  "h": 90,   "group": "ads-display", "fn": ad_728x90},
    "ad-160x600":   {"id": "ad-160x600",   "w": 160,  "h": 600,  "group": "ads-display", "fn": ad_160x600},
    "ad-300x600":   {"id": "ad-300x600",   "w": 300,  "h": 600,  "group": "ads-display", "fn": ad_300x600},
    "ad-970x250":   {"id": "ad-970x250",   "w": 970,  "h": 250,  "group": "ads-display", "fn": ad_970x250},
    "ad-320x50":    {"id": "ad-320x50",    "w": 320,  "h": 50,   "group": "ads-display", "fn": ad_320x50},
}
