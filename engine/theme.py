"""brand.json -> CSS custom properties.

The stylesheet never hard-codes a value. Everything a page can see comes through
here, so a brand is one JSON file away from a complete deck.
"""

from __future__ import annotations

from pathlib import Path

from . import fonts

# Defaults exist so a half-filled brand still renders something honest rather
# than collapsing. Every one of them is overridden by a real brand file.
PALETTE_DEFAULTS = {
    "canvas": "#F7F5EF",
    "surface": "#FFFFFA",
    "ink": "#242424",
    "inkMuted": "#616161",
    "accent": "#6736E2",
    "accentPressed": "#5024C0",
    "groundDark": "#242424",
    "inkOnDark": "#FFFFFA",
    "inkOnDarkMuted": "rgba(255,255,250,.66)",
    "inkOnAccent": "#EEE8FF",
}

SHAPE_DEFAULTS = {
    "margin": 88,
    "safeTop": 80,
    "gap": 20,
    "captionWidth": 360,
    "panelX": 536,
    "panelWidth": 1296,
    "panelHeight": 824,
    "radiusField": 20,
    "radiusCard": 30,
    "radiusPill": 40,
}


def _legible_on(ground: str, ink: str, light: str) -> str:
    """Pick whichever of the brand's own two text colours reads on this ground.

    A caption sitting on an accent tile is the document's choice, not the
    brand's, so the document has to make it readable. This never introduces a
    colour — it only chooses between ink and the light ink already declared.
    """
    from .pages import _luminance

    def ratio(a: str, b: str) -> float:
        la, lb = _luminance(a), _luminance(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + .05) / (lo + .05)

    return light if ratio(light, ground) >= ratio(ink, ground) else ink


def _hairlines(ink: str) -> tuple[str, str]:
    """Rules are the ink at low alpha, never a grey from nowhere."""
    ink = ink.lstrip("#")
    if len(ink) == 3:
        ink = "".join(c * 2 for c in ink)
    r, g, b = (int(ink[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},.10)", f"rgba({r},{g},{b},.22)"


def font_specs(brand: dict) -> list[dict]:
    t = brand.get("type", {})
    specs = []
    for key in ("display", "body"):
        f = t.get(key)
        if not f:
            continue
        specs.append({
            "family": f["family"],
            "variable": bool(f.get("variable")),
            "weights": f.get("weights"),
            "file": f.get("file"),
        })
    return specs


_HEX = __import__("re").compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def check_palette(brand: dict) -> None:
    """Reject a malformed hex at render time, not just at verify time.

    A value like `#12` is not a colour. Chromium silently discards it, the deck
    falls back to a white ground it was never designed for, and the render exits
    zero reporting success. Failing here is the difference between a bad build
    and a bad build nobody noticed.
    """
    bad = [f"{k}={v!r}" for k, v in brand.get("palette", {}).items()
           if not (isinstance(v, str) and _HEX.match(v))]
    if bad:
        raise ValueError("palette values are not hex colours: " + ", ".join(bad))


def variables(brand: dict) -> str:
    check_palette(brand)
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    s = {**SHAPE_DEFAULTS, **brand.get("shape", {})}
    t = brand.get("type", {})
    disp = t.get("display", {"family": "Manrope", "variable": True, "weight": 585, "weightXL": 500})
    body = t.get("body", {"family": disp["family"], "weight": 600})

    hair, hair_strong = _hairlines(p["ink"])
    stack = "system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"

    rows = {
        "--canvas": p["canvas"],
        "--surface": p["surface"],
        "--ink": p["ink"],
        "--ink-muted": p["inkMuted"],
        "--accent": p["accent"],
        "--accent-pressed": p.get("accentPressed", p["accent"]),
        "--ground-dark": p["groundDark"],
        "--ink-on-dark": p["inkOnDark"],
        "--ink-on-dark-muted": p.get("inkOnDarkMuted", PALETTE_DEFAULTS["inkOnDarkMuted"]),
        "--ink-on-accent": p["inkOnAccent"],
        "--label-on-accent": _legible_on(p["accent"], p["ink"], p["inkOnDark"]),
        "--label-on-dark": _legible_on(p["groundDark"], p["ink"], p["inkOnDark"]),
        "--hairline": hair,
        "--hairline-strong": hair_strong,
        "--font-display": f"'{disp['family']}', {stack}",
        "--font-body": f"'{body['family']}', {stack}",
        "--display-weight": str(disp.get("weight", 600)),
        "--display-weight-xl": str(disp.get("weightXL", disp.get("weight", 600))),
        "--body-weight": str(body.get("weight", 400)),
        "--margin": f"{s['margin']}px",
        "--safe-top": f"{s['safeTop']}px",
        "--gap": f"{s['gap']}px",
        "--caption-w": f"{s['captionWidth']}px",
        "--panel-x": f"{s['panelX']}px",
        "--panel-w": f"{s['panelWidth']}px",
        "--panel-h": f"{s['panelHeight']}px",
        "--radius-field": f"{s['radiusField']}px",
        "--radius-card": f"{s['radiusCard']}px",
        "--radius-pill": f"{s['radiusPill']}px",
    }
    body_css = ";".join(f"{k}:{v}" for k, v in rows.items())
    return f":root{{{body_css}}}"


def stylesheet(brand: dict, css_files: list[Path], root: Path | None = None) -> str:
    """Fonts + variables + the deck stylesheet, in that order."""
    parts = [fonts.stylesheet(font_specs(brand), root=root), variables(brand)]
    parts += [p.read_text(encoding="utf-8") for p in css_files]
    return "\n".join(parts)
