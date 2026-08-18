"""Email blocks: header, signature, footer, announcement.

Email art is banner-shaped, so the deck's percentage padding would eat most of
a 1200x300 footer. Every block sets its margins in pixels and scales the `.a-*`
type by its own base font size instead.

Nothing here carries a real person. The signature's name, role and link are
values, and their defaults are visibly placeholders.
"""

from __future__ import annotations

from pathlib import Path

from ..pages import asset, esc
from ._lib import logo, dot

CLAMP = ("display:-webkit-box;-webkit-box-orient:vertical;"
         "overflow:hidden;overflow-wrap:anywhere;-webkit-line-clamp:")

GROUNDS = {"light": (None, "light", "paper"), "dark": ("dark",), "accent": ("accent",)}


def _variant(tone: str) -> str:
    return "primary" if tone == "light" else "reversed"


def _lockup(brand: dict, root: Path, tone: str, height: int) -> str:
    """The lockup the brand drew for this ground, picked by ground not by name.

    Names differ per brand and say nothing about contrast: one brand's dark-ground
    lockup carries an ember disc that disappears on an ember footer. The ground
    the brand recorded is the only reliable answer.
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
    """The lockup at its natural width — a bare `<img>` is stretched by the column."""
    return (f'<div style="flex:none;align-self:{align}">'
            f'{_lockup(brand, root, tone, size)}</div>')


def _button(v: dict, default: str = "Read more") -> str:
    label = v.get("cta", default)
    return f'<span class="a-btn">{esc(label)}{dot()}</span>' if label else ""


def header(brand: dict, v: dict, root: Path) -> str:
    """The block at the top of a campaign: lockup, then the promise."""
    tone = v.get("tone", "light")
    kicker = f'<div class="a-kicker">{esc(v["kicker"])}</div>' if v.get("kicker") else ""
    return (f'<div class="a-fill a-{tone} a-stack" style="padding:56px 72px;font-size:14px">'
            f'{_mark(brand, root, tone, 48)}'
            f'<div class="a-grow"></div>{kicker}'
            f'<h1 class="a-head" style="{CLAMP}2">{esc(v.get("headline", ""))}</h1>'
            f'</div>')


def signature(brand: dict, v: dict, root: Path) -> str:
    """A sign-off block. Every line is a value, every default is a placeholder.

    The person's key is `person`, not `name`: the engine writes the asset's own
    file name into `values["name"]` before the template runs, so a signature
    reading `name` signs itself "email-signature-bare".
    """
    tone = v.get("tone", "light")
    name = esc(v.get("person", "Your Name"))
    role = esc(v.get("role", "Your Role"))
    link = esc(v.get("link", "yourdomain.example"))
    tint = "color:var(--accent)" if tone == "light" else "opacity:.92"
    # The rule is sized to the three lines beside it, not to the canvas, or it
    # runs past the text top and bottom and reads as a stray line.
    rule = ('<div style="flex:none;width:1px;height:136px;align-self:center;'
            'background:currentColor;opacity:.18;margin:0 44px"></div>')
    return (
        f'<div class="a-fill a-{tone} a-row" style="padding:52px 60px">'
        f'{_mark(brand, root, tone, 56, "center")}{rule}'
        f'<div style="flex:1 1 auto;min-width:0">'
        f'<div style="font-family:var(--font-display);font-weight:var(--display-weight);'
        f"font-variation-settings:'wght' var(--display-weight);"
        f'font-size:40px;line-height:1.1;letter-spacing:-.035em;{CLAMP}1">{name}</div>'
        f'<div style="font-size:24px;line-height:1.3;letter-spacing:-.02em;opacity:.68;'
        f'margin-top:9px;{CLAMP}1">{role}</div>'
        f'<div style="font-size:23px;line-height:1.3;letter-spacing:-.02em;'
        f'margin-top:18px;{tint};{CLAMP}1">{link}</div>'
        f'</div></div>')


def footer(brand: dict, v: dict, root: Path) -> str:
    """Lockup, one line of what the brand is, one small line of legal."""
    tone = v.get("tone", "dark")
    m = brand.get("meta", {})
    bits = []
    if m.get("year"):
        bits.append(f"© {m['year']} {m.get('name', '')}".strip())
    elif m.get("name"):
        bits.append(m["name"])
    if m.get("legal"):
        bits.append(m["legal"])
    legal = esc(v.get("legal") or " · ".join(bits))

    line = ""
    if v.get("line"):
        line = (f'<div style="font-size:30px;line-height:1.4;letter-spacing:-.025em;'
                f'opacity:.8;margin-top:26px;max-width:800px;{CLAMP}2">'
                f'{esc(v["line"])}</div>')
    small = ""
    if legal:
        small = (f'<div style="font-size:20px;line-height:1.4;letter-spacing:-.01em;'
                 f'opacity:.5;margin-top:20px">{legal}</div>')
    return (f'<div class="a-fill a-{tone} a-stack a-center" '
            f'style="padding:40px 80px;text-align:center">'
            f'{_lockup(brand, root, tone, 40)}{line}{small}</div>')


def announcement(brand: dict, v: dict, root: Path) -> str:
    """The body block: headline, a paragraph, one button."""
    tone = v.get("tone", "light")
    kicker = f'<div class="a-kicker">{esc(v["kicker"])}</div>' if v.get("kicker") else ""
    body = ""
    if v.get("body"):
        body = (f'<p class="a-sub" style="font-size:2.3em;max-width:46ch;{CLAMP}4">'
                f'{esc(v["body"])}</p>')
    return (f'<div class="a-fill a-{tone} a-stack" style="padding:88px 96px;font-size:14px">'
            f'{_mark(brand, root, tone, 46)}'
            f'<div class="a-grow"></div>{kicker}'
            f'<h1 class="a-head" style="{CLAMP}2">{esc(v.get("headline", ""))}</h1>{body}'
            f'<div class="a-foot">{_button(v)}</div></div>')


TEMPLATES = {
    "email-header":       {"id": "email-header",       "w": 1200, "h": 400, "group": "email", "fn": header},
    "email-signature":    {"id": "email-signature",    "w": 900,  "h": 300, "group": "email", "fn": signature},
    "email-footer":       {"id": "email-footer",       "w": 1200, "h": 300, "group": "email", "fn": footer},
    "email-announcement": {"id": "email-announcement", "w": 1200, "h": 800, "group": "email", "fn": announcement},
}
