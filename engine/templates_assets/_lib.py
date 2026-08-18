"""Shared pieces every template can use."""

from __future__ import annotations

from pathlib import Path

from ..pages import asset, esc


def _lockups(brand: dict) -> list[dict]:
    return [p for sec in brand.get("sections", []) if sec.get("id") == "logo"
            for p in sec.get("pages", []) if p.get("kind") == "lockup"]


def _marks(brand: dict) -> list[dict]:
    return [m for sec in brand.get("sections", []) if sec.get("id") == "logo"
            for p in sec.get("pages", []) if p.get("kind") == "marks"
            for m in p.get("marks", [])]


def _match(items: list[dict], key: str, variant: str) -> dict | None:
    """Prefer a labelled match, otherwise take the first one there is.

    A brand names its variants whatever it likes. One calls them Ember, Ink and
    Paper, so asking for "primary" matched nothing and the artwork silently
    vanished from the asset. Falling back to the first is always better than
    rendering an empty box.
    """
    want = variant.lower()
    for i in items:
        if want in (i.get(key, "") or "").lower():
            return i
    # A ground-based guess, then simply the first.
    for alias in ("primary", "reversed", "dark", "ember", "ink", "paper"):
        if alias == want:
            continue
        for i in items:
            if want in ("reversed", "dark") and (i.get("ground") in ("dark", "accent")):
                return i
    return items[0] if items else None


def logo(brand: dict, root: Path, variant: str = "primary", height: int = 64) -> str:
    """The brand's lockup, or its wordmark set in type when there is no file."""
    hit = _match(_lockups(brand), "variant", variant)
    if hit:
        return (f'<img class="a-logo" style="height:{height}px" '
                f'src="{asset(hit["src"], root)}" alt="">')
    return f'<span class="a-wordmark">{esc(brand["meta"].get("wordmark", ""))}</span>'


def mark(brand: dict, root: Path, variant: str = "primary", size: int = 64) -> str:
    hit = _match(_marks(brand), "label", variant)
    if hit:
        return f'<img style="height:{size}px" src="{asset(hit["src"], root)}" alt="">'
    return ""


def _art_luminance(src: str, root: Path) -> float | None:
    """Rough lightness of an SVG's own fills, so artwork can be matched to a ground."""
    from ..pages import _luminance
    import re
    f = Path(src)
    if not f.is_absolute():
        f = root / f
    if not f.exists() or f.suffix.lower() != ".svg":
        return None
    hexes = re.findall(r"#[0-9a-fA-F]{6}", f.read_text(encoding="utf-8", errors="replace"))
    if not hexes:
        return None
    return sum(_luminance(h) for h in hexes) / len(hexes)


def mark_on(brand: dict, root: Path, ground: str, size: int = 64) -> str:
    """The mark that can actually be seen on this ground.

    Asking for a variant by name put an ember mark on an ember avatar, because
    the name says nothing about contrast. Compare the artwork's own colours to
    the ground instead, which works for a brand whose variants are called
    anything at all.
    """
    from ..pages import _luminance
    items = _marks(brand)
    if not items:
        return ""
    gl = _luminance(ground)
    best, best_gap = items[0], -1.0
    for m in items:
        al = _art_luminance(m.get("src", ""), root)
        if al is None:
            continue
        gap = abs(al - gl)
        if gap > best_gap:
            best, best_gap = m, gap
    return f'<img style="height:{size}px" src="{asset(best["src"], root)}" alt="">'


def dot() -> str:
    return '<span class="a-dot"></span>'
