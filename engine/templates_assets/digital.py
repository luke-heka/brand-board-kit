"""Screen artwork: icons, share cards, backgrounds and course covers.

Everything that carries the mark asks `mark_on` for it, handing over the hex the
template is actually painting. The brand's palette decides that hex, so the
artwork is chosen for contrast against the real ground rather than by a name that
says nothing about whether it can be seen.
"""

from __future__ import annotations

from pathlib import Path

from ..pages import esc
from ._lib import _lockups, dot, logo, mark_on

# Which class paints a ground, which palette key holds the hex it paints, and
# what a brand calls the lockup it drew for that ground.
_TONES = {"light": ("a-light", "canvas", ""),
          "dark": ("a-dark", "groundDark", "dark"),
          "accent": ("a-accent", "accent", "accent")}


def _tone(brand: dict, name: str, default: str = "dark") -> tuple[str, str, str]:
    """The ground a template paints: its class, its hex, and the lockup to use.

    Asking for the "reversed" lockup on an accent ground put an ember wordmark on
    ember and lost a letter. A brand already says which ground each lockup was
    drawn for, so read that instead of guessing from a name.
    """
    cls, key, ground = _TONES[name if name in _TONES else default]
    palette = brand.get("palette", {})
    variant = "primary"
    for lock in _lockups(brand):
        if (lock.get("ground") or "") == ground:
            variant = lock.get("variant") or variant
            break
    return cls, palette.get(key) or palette.get("groundDark", "#000000"), variant


def _head(text: str, size: int, extra: str = "") -> str:
    return (f'<h1 class="a-head" style="font-size:{size}px;{extra}">'
            f'{esc(text)}</h1>') if text else ""


def _sub(text: str, size: int, extra: str = "") -> str:
    return (f'<p class="a-sub" style="font-size:{size}px;{extra}">'
            f'{esc(text)}</p>') if text else ""


def _kicker(text: str, size: int, extra: str = "") -> str:
    return (f'<div class="a-kicker" style="font-size:{size}px;{extra}">'
            f'{esc(text)}</div>') if text else ""


def _corner_mark(brand: dict, root: Path, ground: str, size: int,
                 right: str = "6%") -> str:
    """A large mark held against one edge, clear of whatever sits in the middle."""
    return (f'<div style="position:absolute;inset:0;display:flex;'
            f'align-items:center;justify-content:flex-end;padding-right:{right};'
            f'pointer-events:none">{mark_on(brand, root, ground, size)}</div>')


def _block(inner: str, extra: str = "") -> str:
    """A wrapper that stops a flex column stretching an image out of shape."""
    return f'<div style="flex:none;{extra}">{inner}</div>'


# ------------------------------------------------------------------------ icons

def app_icon(brand: dict, v: dict, root: Path) -> str:
    cls, ground, _ = _tone(brand, v.get("tone", "accent"))
    return (f'<div class="a-fill {cls} a-center">'
            f'{mark_on(brand, root, ground, v.get("markSize", 520))}</div>')


def favicon(brand: dict, v: dict, root: Path) -> str:
    """Same idea as the app icon, but the mark fills more of it so it survives 16px."""
    cls, ground, _ = _tone(brand, v.get("tone", "accent"))
    return (f'<div class="a-fill {cls} a-center">'
            f'{mark_on(brand, root, ground, v.get("markSize", 340))}</div>')


# ------------------------------------------------------------------- share + screen

def og_card(brand: dict, v: dict, root: Path) -> str:
    """The picture a link becomes when it is pasted anywhere."""
    cls, ground, variant = _tone(brand, v.get("tone", "dark"))
    return (f'<div class="a-fill {cls} a-pad a-stack" style="position:relative">'
            f'{_corner_mark(brand, root, ground, v.get("markSize", 300), "7%")}'
            f'<div style="position:relative">{logo(brand, root, variant, 46)}</div>'
            f'<div class="a-grow"></div>'
            f'<div style="position:relative;max-width:70%">'
            f'{_kicker(v.get("kicker", ""), 26)}'
            f'{_head(v.get("headline", ""), 74)}'
            f'{_sub(v.get("sub", ""), 28)}</div></div>')


def zoom_background(brand: dict, v: dict, root: Path) -> str:
    """Branding down the left and the mark to the right, so the middle stays clear."""
    cls, ground, variant = _tone(brand, v.get("tone", "dark"))
    return (f'<div class="a-fill {cls} a-pad a-stack" style="position:relative">'
            f'{_corner_mark(brand, root, ground, v.get("markSize", 420), "8%")}'
            f'<div style="position:relative">{logo(brand, root, variant, 78)}</div>'
            f'<div class="a-grow"></div>'
            f'<div style="position:relative;max-width:46%">'
            f'{_sub(v.get("line", ""), 32, "margin-top:0")}</div></div>')


def presentation_title(brand: dict, v: dict, root: Path) -> str:
    cls, _, variant = _tone(brand, v.get("tone", "light"), "light")
    foot = [t for t in (v.get("presenter"), v.get("date")) if t]
    sep = '<span style="opacity:.4;margin:0 18px">·</span>'
    return (f'<div class="a-fill {cls} a-pad a-stack">'
            f'{_block(logo(brand, root, variant, 62))}'
            f'<div class="a-grow"></div>'
            f'{_kicker(v.get("kicker", ""), 30)}'
            f'{_head(v.get("headline", ""), 112, "max-width:18ch")}'
            f'{_sub(v.get("sub", ""), 34)}'
            f'<div class="a-grow"></div>'
            f'<div style="font-size:28px;letter-spacing:-.02em;opacity:.6">'
            f'{sep.join(esc(t) for t in foot)}</div></div>')


# ----------------------------------------------------------------------- covers

def course_cover(brand: dict, v: dict, root: Path) -> str:
    cls, ground, variant = _tone(brand, v.get("tone", "dark"))
    return (f'<div class="a-fill {cls} a-pad a-stack" style="position:relative">'
            f'{_corner_mark(brand, root, ground, v.get("markSize", 330), "7%")}'
            f'<div style="position:relative">{logo(brand, root, variant, 46)}</div>'
            f'<div class="a-grow"></div>'
            f'<div style="position:relative;max-width:66%">'
            f'{_kicker(v.get("kicker", "Course"), 28)}'
            f'{_head(v.get("headline", ""), 86, "max-width:14ch")}'
            f'{_sub(v.get("sub", ""), 28)}</div></div>')


def module_cover(brand: dict, v: dict, root: Path) -> str:
    """A numbered lesson tile. The number is the thing you read from across a grid."""
    cls, ground, _ = _tone(brand, v.get("tone", "light"), "light")
    number = (f'<div style="font-family:var(--font-display);'
              f'font-weight:var(--display-weight);'
              f"font-variation-settings:'wght' var(--display-weight);"
              f'font-size:200px;line-height:.9;letter-spacing:-.05em;'
              f'{"color:var(--accent)" if cls == "a-light" else ""}">'
              f'{esc(str(v.get("number", "01")))}</div>')
    return (f'<div class="a-fill {cls} a-pad a-stack">'
            f'<div style="display:flex;flex:none;align-items:center">'
            f'{number}<div class="a-grow"></div>'
            f'{mark_on(brand, root, ground, v.get("markSize", 120))}</div>'
            f'<div class="a-grow"></div>'
            f'{_head(v.get("headline", ""), 72, "max-width:13ch")}'
            f'{_sub(v.get("sub", ""), 26)}</div>')


def event_cover(brand: dict, v: dict, root: Path) -> str:
    cls, ground, variant = _tone(brand, v.get("tone", "accent"))
    cta = (f'<span class="a-btn" style="font-size:30px">{esc(v["cta"])}{dot()}</span>'
           ) if v.get("cta") else ""
    return (f'<div class="a-fill {cls} a-pad a-stack" style="position:relative">'
            f'{_corner_mark(brand, root, ground, v.get("markSize", 340), "7%")}'
            f'<div style="position:relative">{logo(brand, root, variant, 58)}</div>'
            f'<div class="a-grow"></div>'
            f'<div style="position:relative;max-width:64%">'
            f'{_kicker(v.get("when", ""), 32)}'
            f'{_head(v.get("headline", ""), 108, "max-width:13ch")}'
            f'{_sub(v.get("sub", ""), 32)}</div>'
            f'<div class="a-foot" style="position:relative">{cta}</div></div>')


TEMPLATES = {
    "app-icon":           {"id": "app-icon",           "w": 1024, "h": 1024, "group": "digital", "fn": app_icon},
    "favicon":            {"id": "favicon",            "w": 512,  "h": 512,  "group": "digital", "fn": favicon},
    "og-card":            {"id": "og-card",            "w": 1200, "h": 630,  "group": "digital", "fn": og_card},
    "zoom-background":    {"id": "zoom-background",    "w": 1920, "h": 1080, "group": "digital", "fn": zoom_background},
    "presentation-title": {"id": "presentation-title", "w": 1920, "h": 1080, "group": "digital", "fn": presentation_title},
    "course-cover":       {"id": "course-cover",       "w": 1460, "h": 752,  "group": "covers",  "fn": course_cover},
    "module-cover":       {"id": "module-cover",       "w": 1080, "h": 720,  "group": "covers",  "fn": module_cover},
    "event-cover":        {"id": "event-cover",        "w": 1920, "h": 1080, "group": "covers",  "fn": event_cover},
}
