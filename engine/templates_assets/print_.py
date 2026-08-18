"""Printed stationery, drawn at 300dpi so a file goes straight to a printer.

A business card is 1050x600 rather than 350x200 for that reason, and the type is
sized in the same units: at 300dpi a point is a little over four pixels, so a 9pt
contact line is set at 38px, not at 9.

Every name, address and number below is an obvious placeholder. A brand file
supplies the real ones through the asset's values, and nothing here ever ships a
real person's details.
"""

from __future__ import annotations

from pathlib import Path

from ..pages import esc
from ._lib import _lockups, logo, mark_on

# Which class paints a ground, which palette key holds the hex it paints, and
# what a brand calls the lockup it drew for that ground.
_TONES = {"light": ("a-light", "canvas", ""),
          "dark": ("a-dark", "groundDark", "dark"),
          "accent": ("a-accent", "accent", "accent")}

# `name` is not usable here: the generator writes the asset's own file name into
# that value, so the person's name has its own key.
_PERSON = {"fullName": "Full Name", "role": "Role or title",
           "email": "name@example.com", "phone": "+00 0000 0000",
           "site": "example.com"}

_PLACE = {"email": "hello@example.com", "phone": "+00 0000 0000",
          "site": "example.com", "address": "1 Example Street, City"}


def _tone(brand: dict, name: str, default: str = "accent") -> tuple[str, str, str]:
    """The ground a template paints: its class, its hex, and the lockup to use.

    The hex is what `mark_on` needs, and both it and the lockup come from the
    brand's own file, so the artwork is chosen against the colour actually on the
    page rather than by a name that says nothing about contrast.
    """
    cls, key, ground = _TONES[name if name in _TONES else default]
    palette = brand.get("palette", {})
    variant = "primary"
    for lock in _lockups(brand):
        if (lock.get("ground") or "") == ground:
            variant = lock.get("variant") or variant
            break
    return cls, palette.get(key) or palette.get("groundDark", "#000000"), variant


def _values(defaults: dict, v: dict) -> dict:
    """Defaults, overridden only by values that actually carry something."""
    return {**defaults, **{k: x for k, x in v.items() if x}}


def _display(text: str, size: int, extra: str = "") -> str:
    return (f'<div style="font-family:var(--font-display);'
            f'font-weight:var(--display-weight);'
            f"font-variation-settings:'wght' var(--display-weight);"
            f'font-size:{size}px;line-height:1.04;letter-spacing:-.035em;'
            f'{extra}">{esc(text)}</div>')


def _lines(items, size: int, *, align: str = "left", gap: int = 12,
           opacity: float = .68) -> str:
    """A small stacked block of detail lines, kept whole inside a flex row."""
    kept = [t for t in items if t]
    rows = "".join(
        f'<div style="font-size:{size}px;line-height:1.34;letter-spacing:-.02em;'
        f'text-align:{align};opacity:{opacity};margin-top:{0 if i == 0 else gap}px">'
        f'{esc(t)}</div>' for i, t in enumerate(kept))
    return f'<div style="flex:none">{rows}</div>' if rows else ""


def _rule(margin: str = "0", weight: int = 2, opacity: float = .18) -> str:
    """A hairline that works on any ground, because it borrows the text colour."""
    return (f'<div style="height:{weight}px;background:currentColor;'
            f'opacity:{opacity};margin:{margin};flex:none"></div>')


def _bar(height: int) -> str:
    return f'<div style="height:{height}px;background:var(--accent);flex:none"></div>'


def _sheet(inner: str, bar: int = 22) -> str:
    """An accent edge, then a padded column that owns the rest of the sheet.

    `a-stack` and `a-row` only set the direction; the display comes from `a-fill`.
    A nested block needs its own, or every child collapses to the top of the page.
    """
    return (f'<div class="a-fill a-light a-stack">{_bar(bar)}'
            f'<div class="a-pad a-stack" style="display:flex;flex:1;min-height:0">'
            f'{inner}</div></div>')


def _block(inner: str, extra: str = "") -> str:
    """A wrapper that stops a flex column stretching an image out of shape."""
    return f'<div style="flex:none;{extra}">{inner}</div>'


def _footer(brand: dict, v: dict) -> str:
    meta = brand.get("meta", {})
    if v.get("footer"):
        return str(v["footer"])
    bits = [meta.get("name", ""), str(meta.get("year", "")), meta.get("legal", "")]
    return "  ·  ".join(b for b in bits if b)


# --------------------------------------------------------------------------- cards

def card_front(brand: dict, v: dict, root: Path) -> str:
    d = _values(_PERSON, v)
    cls, _, variant = _tone(brand, v.get("tone", "light"), "light")
    sep = '<span style="opacity:.42;margin:0 16px">/</span>'
    contact = sep.join(esc(d[k]) for k in ("email", "phone", "site") if d.get(k))
    return (f'<div class="a-fill {cls} a-pad a-stack">'
            f'{_block(logo(brand, root, variant, 58))}'
            f'<div class="a-grow"></div>'
            f'{_display(d["fullName"], 58)}'
            f'{_lines([d.get("role")], 34, gap=0, opacity=.6)}'
            f'{_rule("40px 0 30px")}'
            f'<div style="font-size:30px;letter-spacing:-.02em;opacity:.72">'
            f'{contact}</div></div>')


def card_back(brand: dict, v: dict, root: Path) -> str:
    """The bold side: the mark alone on a full-bleed colour."""
    cls, ground, _ = _tone(brand, v.get("tone", "accent"))
    line = v.get("line") or brand.get("meta", {}).get("tagline", "")
    tail = (f'<div style="font-size:30px;letter-spacing:-.02em;opacity:.8;'
            f'margin-top:44px;max-width:24ch">{esc(line)}</div>') if line else ""
    return (f'<div class="a-fill {cls} a-center a-stack" style="text-align:center">'
            f'{mark_on(brand, root, ground, v.get("markSize", 300))}{tail}</div>')


# ----------------------------------------------------------------------- a4 stationery

def letterhead(brand: dict, v: dict, root: Path) -> str:
    """A4: a header that carries the identity, an open body, a footer that closes it."""
    d = _values(_PLACE, v)
    _, _, variant = _tone(brand, "light", "light")
    body = v.get("body") or []
    if isinstance(body, str):
        body = [p for p in body.split("\n\n") if p.strip()]
    para = "".join(
        f'<p style="font-size:46px;line-height:1.55;letter-spacing:-.015em;'
        f'max-width:44ch;margin-top:{0 if i == 0 else 40}px">{esc(p)}</p>'
        for i, p in enumerate(body))
    head = (f'<div style="display:flex;flex:none;align-items:flex-start">'
            f'{logo(brand, root, variant, 118)}<div class="a-grow"></div>'
            f'{_lines([d.get("site"), d.get("email"), d.get("phone")], 34, align="right", gap=8)}'
            f'</div>')
    foot = (f'<div style="display:flex;flex:none;font-size:32px;'
            f'letter-spacing:-.02em;opacity:.6">'
            f'<span>{esc(_footer(brand, v))}</span><div class="a-grow"></div>'
            f'<span>{esc(d.get("address", ""))}</span></div>')
    return _sheet(f'{head}{_rule("54px 0 0")}'
                  f'<div style="flex:1;min-height:0;padding-top:120px">{para}</div>'
                  f'{_rule("0 0 34px")}{foot}', bar=24)


def compliment_slip(brand: dict, v: dict, root: Path) -> str:
    d = _values(_PLACE, v)
    _, _, variant = _tone(brand, "light", "light")
    line = _display(v.get("line", "With compliments"), 122)
    return _sheet(
        f'{_block(logo(brand, root, variant, 96))}'
        f'<div class="a-grow"></div>'
        f'<div style="display:flex;flex:none;align-items:flex-end">'
        f'<div style="flex:1">{line}</div>'
        f'{_lines([d.get("site"), d.get("email"), d.get("phone"), d.get("address")], 32, align="right", gap=8)}'
        f'</div>', bar=20)


def notepad(brand: dict, v: dict, root: Path) -> str:
    """A5 pad: the logo, then a ruled field that runs to the foot of the sheet."""
    step = int(v.get("ruleStep", 94))
    _, _, variant = _tone(brand, "light", "light")
    rules = (f'<div style="flex:1;min-height:0;opacity:.26;background:'
             f'repeating-linear-gradient(to bottom,transparent 0,transparent {step - 2}px,'
             f'currentColor {step - 2}px,currentColor {step}px)"></div>')
    head = (f'<div style="display:flex;flex:none;align-items:flex-end">'
            f'{logo(brand, root, variant, 82)}<div class="a-grow"></div>'
            f'{_lines([v.get("kicker", "Notes")], 30, align="right", opacity=.5)}</div>')
    return _sheet(
        f'{head}<div style="height:56px;flex:none"></div>{rules}'
        f'<div style="height:36px;flex:none"></div>'
        f'<div style="flex:none;font-size:28px;letter-spacing:-.02em;opacity:.5">'
        f'{esc(v.get("site", _PLACE["site"]))}</div>', bar=18)


TEMPLATES = {
    "card-front":      {"id": "card-front",      "w": 1050, "h": 600,  "group": "print", "fn": card_front},
    "card-back":       {"id": "card-back",       "w": 1050, "h": 600,  "group": "print", "fn": card_back},
    "letterhead":      {"id": "letterhead",      "w": 2480, "h": 3508, "group": "print", "fn": letterhead},
    "compliment-slip": {"id": "compliment-slip", "w": 2480, "h": 1169, "group": "print", "fn": compliment_slip},
    "notepad":         {"id": "notepad",         "w": 1748, "h": 2480, "group": "print", "fn": notepad},
}
