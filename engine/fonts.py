"""Font resolution and embedding.

Every font a deck uses is embedded as a base64 data URI. A remote @import means
"no internet, silent Times fallback, no error" — which is how a render can look
fine in CI and wrong on someone's laptop. Files are cached under assets/fonts/
so the second build of any brand is offline-safe.
"""

from __future__ import annotations

import base64
import re
import urllib.request
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
GF_CSS = "https://fonts.googleapis.com/css2?family={spec}&display=swap"
# Google serves woff2 only to browsers that say so.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

MIME = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".otf": "font/otf"}


class FontError(RuntimeError):
    pass


def _slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def _cached(family: str, variable: bool) -> Path | None:
    stem = _slug(family)
    for name in ([f"{stem}-var", stem] if variable else [stem, f"{stem}-var"]):
        for ext in (".woff2", ".woff", ".ttf", ".otf"):
            p = ASSETS / f"{name}{ext}"
            if p.exists():
                return p
    # Manrope ships as Manrope-var.woff2 (mixed case) from the design-language skill
    for p in ASSETS.glob("*"):
        if p.suffix in MIME and _slug(p.stem).startswith(stem):
            return p
    return None


def _cached_weight(family: str, weight: int) -> Path | None:
    p = ASSETS / f"{_slug(family)}-{weight}.woff2"
    return p if p.exists() else None


def _download_weight(family: str, weight: int) -> Path:
    """One file, one weight.

    A css2 response for a static family returns one @font-face per weight, and
    taking the last URL takes the heaviest. That shipped an entire deck in bold
    with no error anywhere, so each weight is now requested on its own.
    """
    path = _download(family, f"wght@{weight}", stem=f"{_slug(family)}-{weight}")
    return path


def _download(family: str, axis: str, stem: str | None = None) -> Path:
    """Fetch a Google Font and cache it. `axis` is a css2 spec fragment."""
    spec = family.replace(" ", "+") + (f":{axis}" if axis else "")
    req = urllib.request.Request(GF_CSS.format(spec=spec), headers={"User-Agent": UA})
    try:
        css = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception as exc:  # offline, blocked, family misspelled
        raise FontError(
            f"'{family}' is not in assets/fonts/ and could not be fetched ({exc}). "
            f"Drop a .woff2 or .ttf named {_slug(family)}.woff2 into "
            f"{ASSETS} and build again — no internet needed after that."
        ) from exc

    urls = re.findall(r"url\((https://[^)]+\.woff2)\)", css)
    if not urls:
        raise FontError(f"Google Fonts returned no woff2 for '{family}'.")
    # The last src in a css2 response is the widest unicode-range (latin).
    data = urllib.request.urlopen(
        urllib.request.Request(urls[-1], headers={"User-Agent": UA}), timeout=30).read()
    ASSETS.mkdir(parents=True, exist_ok=True)
    name = stem or f"{_slug(family)}{'-var' if axis and '..' in axis else ''}"
    out = ASSETS / f"{name}.woff2"
    out.write_bytes(data)
    return out


def resolve(family: str, *, variable: bool = False, weights: list[int] | None = None,
            file: str | None = None, root: Path | None = None) -> Path:
    """Find a font file for `family`, downloading and caching it if needed."""
    if file:
        p = Path(file)
        if not p.is_absolute() and root:
            p = root / p
        if not p.exists():
            raise FontError(f"Font file not found: {p}")
        return p
    hit = _cached(family, variable)
    if hit:
        return hit
    if variable:
        axis = "wght@200..800"
    elif weights:
        axis = "wght@" + ";".join(str(w) for w in sorted(set(weights)))
    else:
        axis = "wght@400;600"
    return _download(family, axis)


def face(family: str, path: Path, *, variable: bool = False,
         weights: list[int] | None = None) -> str:
    """One @font-face rule with the file inlined as base64."""
    mime = MIME.get(path.suffix.lower(), "font/woff2")
    fmt = {"font/woff2": "woff2", "font/woff": "woff",
           "font/ttf": "truetype", "font/otf": "opentype"}[mime]
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    if variable:
        rng = "200 800"
    elif weights:
        rng = f"{min(weights)} {max(weights)}"
    else:
        rng = "100 900"
    return (f"@font-face{{font-family:'{family}';"
            f"src:url(data:{mime};base64,{b64}) format('{fmt}');"
            f"font-weight:{rng};font-style:normal;font-display:block;}}")


def stylesheet(specs: list[dict], root: Path | None = None) -> str:
    """Build the @font-face block for a brand's font list.

    Each spec: {family, variable?, weights?, file?}
    A variable family is one file covering the axis. A static family is one file
    per weight, each declared at its exact weight, because a single file
    declared across a range renders every weight as whichever one was fetched.
    """
    out, seen = [], set()
    for s in specs:
        fam = s["family"]
        if fam in seen:
            continue
        seen.add(fam)
        variable, weights, file = s.get("variable", False), s.get("weights"), s.get("file")

        if variable or file or not weights:
            p = resolve(fam, variable=variable, weights=weights, file=file, root=root)
            out.append(face(fam, p, variable=variable, weights=weights))
            continue

        for w in sorted(set(weights)):
            p = _cached_weight(fam, w) or _download_weight(fam, w)
            out.append(face(fam, p, weights=[w]))
    return "\n".join(out)
