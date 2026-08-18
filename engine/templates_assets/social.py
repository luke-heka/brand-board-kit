"""Social posts and profile artwork."""

from __future__ import annotations

from pathlib import Path

from ..pages import esc
from ._lib import dot, logo, mark, mark_on


def _post(brand: dict, v: dict, root: Path, *, tone: str) -> str:
    kicker = f'<div class="a-kicker">{esc(v["kicker"])}</div>' if v.get("kicker") else ""
    sub = f'<p class="a-sub">{esc(v["sub"])}</p>' if v.get("sub") else ""
    cta = (f'<span class="a-btn">{esc(v["cta"])}{dot()}</span>') if v.get("cta") else ""
    return (
        f'<div class="a-fill a-{tone} a-pad a-stack">'
        f'{logo(brand, root, "reversed" if tone != "light" else "primary", 52)}'
        f'<div class="a-grow"></div>{kicker}'
        f'<h1 class="a-head">{esc(v.get("headline", ""))}</h1>{sub}'
        f'<div class="a-foot">{cta}</div></div>')


def ig_square(brand, v, root):   return _post(brand, v, root, tone=v.get("tone", "light"))
def ig_portrait(brand, v, root): return _post(brand, v, root, tone=v.get("tone", "dark"))
def ig_story(brand, v, root):    return _post(brand, v, root, tone=v.get("tone", "accent"))


def quote(brand: dict, v: dict, root: Path) -> str:
    who = f'<div class="a-who">{esc(v["who"])}</div>' if v.get("who") else ""
    return (f'<div class="a-fill a-light a-pad a-stack">'
            f'{mark(brand, root, "primary", 56)}<div class="a-grow"></div>'
            f'<blockquote class="a-quote">{esc(v.get("quote", ""))}</blockquote>{who}'
            f'<div class="a-foot">{logo(brand, root, "primary", 40)}</div></div>')


def stat(brand: dict, v: dict, root: Path) -> str:
    return (f'<div class="a-fill a-accent a-pad a-stack">'
            f'{logo(brand, root, "tertiary", 48)}<div class="a-grow"></div>'
            f'<div class="a-stat">{esc(v.get("figure", ""))}</div>'
            f'<p class="a-sub">{esc(v.get("label", ""))}</p></div>')


def banner(brand: dict, v: dict, root: Path) -> str:
    """Wide profile artwork: X, LinkedIn, Facebook, YouTube."""
    return (f'<div class="a-fill a-dark a-pad a-row">'
            f'<div>{logo(brand, root, "reversed", v.get("logoHeight", 72))}'
            f'<p class="a-sub a-tight">{esc(v.get("line", ""))}</p></div>'
            f'<div class="a-grow"></div>{mark_on(brand, root, brand.get("palette", {}).get("groundDark", "#000000"), v.get("markSize", 120))}'
            f'</div>')


def avatar(brand: dict, v: dict, root: Path) -> str:
    ground = {**{"accent": "#000000"}, **brand.get("palette", {})}.get("accent", "#000000")
    return (f'<div class="a-fill a-accent a-center">'
            f'{mark_on(brand, root, ground, v.get("markSize", 520))}</div>')


TEMPLATES = {
    "ig-square":   {"id": "ig-square",   "w": 1080, "h": 1080, "group": "social-posts",   "fn": ig_square},
    "ig-portrait": {"id": "ig-portrait", "w": 1080, "h": 1350, "group": "social-posts",   "fn": ig_portrait},
    "ig-story":    {"id": "ig-story",    "w": 1080, "h": 1920, "group": "social-posts",   "fn": ig_story},
    "quote-card":  {"id": "quote-card",  "w": 1080, "h": 1080, "group": "social-posts",   "fn": quote},
    "stat-card":   {"id": "stat-card",   "w": 1080, "h": 1080, "group": "social-posts",   "fn": stat},
    "x-banner":    {"id": "x-banner",    "w": 1500, "h": 500,  "group": "social-profile", "fn": banner},
    "li-banner":   {"id": "li-banner",   "w": 1584, "h": 396,  "group": "social-profile", "fn": banner},
    "fb-cover":    {"id": "fb-cover",    "w": 820,  "h": 312,  "group": "social-profile", "fn": banner},
    "yt-banner":   {"id": "yt-banner",   "w": 2560, "h": 1440, "group": "social-profile", "fn": banner},
    "avatar":      {"id": "avatar",      "w": 1000, "h": 1000, "group": "social-profile", "fn": avatar},
}
