"""Intake — turn whatever a business hands over into a valid brand.json.

    python3 -m engine.intake --name "Acme Roofing" \
        --site https://acme.example --logo logo.svg --files ~/Downloads/brand

Everything except `--name` is optional. Whatever is supplied gets read, in the
order a real brand arrives: the website first because it is what the world
already sees, then the logo files, then a dropped folder, then nothing.

The one rule the whole module is built around: **never invent a value.** A
colour that was measured says where it was measured. A colour that was computed
from a measured one says so, and says which one. A colour that could not be
found is reported missing and no plausible substitute is put in its place. The
output feeds a document that claims to be the brand's truth, so a confident
guess in it is worse than a gap.

Derived values may be nudged until they clear WCAG AA. Measured ones never are:
a measured pairing that fails is a fact about the brand, and it is reported as
a finding for its owner to decide on.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import fonts as fonts_mod
from .pages import contrast, _luminance

ROOT = Path(__file__).resolve().parent.parent

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif"}
FONT_EXT = {".woff2", ".woff", ".ttf", ".otf"}
LOGO_WORDS = ("logo", "lockup", "mark", "icon", "symbol", "wordmark", "favicon",
              "brand", "glyph", "emblem", "avatar")
MARK_WORDS = ("mark", "icon", "symbol", "glyph", "favicon", "avatar", "emblem")

# A face the engine already has cached, so a brand whose real face cannot be
# resolved still renders offline instead of dying at font-fetch time.
FALLBACK_FAMILY = "Inter"
GENERIC_FAMILIES = {
    "system-ui", "-apple-system", "blinkmacsystemfont", "sans-serif", "serif",
    "monospace", "cursive", "fantasy", "ui-sans-serif", "ui-serif",
    "ui-monospace", "ui-rounded", "segoe ui", "helvetica", "helvetica neue",
    "arial", "roboto", "apple color emoji", "segoe ui emoji", "inherit",
    "initial", "unset",
}


# --------------------------------------------------------------------------
# the record — every value carries how it got here
# --------------------------------------------------------------------------

class Report:
    """What was measured, what was computed, and what is simply not known.

    Nothing in the brand file is allowed to exist without a line in here, which
    is what stops a derived colour being quoted later as a measured one.
    """

    def __init__(self) -> None:
        self.values: list[dict] = []
        self.missing: list[dict] = []
        self.notes: list[str] = []
        self.findings: list[str] = []

    def _put(self, slot: str, value, how: str, source: str) -> None:
        self.values = [v for v in self.values if v["slot"] != slot]
        self.values.append({"slot": slot, "value": value, "how": how, "source": source})

    def measured(self, slot: str, value, source: str) -> None:
        self._put(slot, value, "measured", source)

    def derived(self, slot: str, value, source: str) -> None:
        self._put(slot, value, "derived", source)

    def gap(self, what: str, why: str) -> None:
        if not any(m["what"] == what for m in self.missing):
            self.missing.append({"what": what, "why": why})

    def note(self, text: str) -> None:
        self.notes.append(text)

    def finding(self, text: str) -> None:
        self.findings.append(text)

    def how(self, slot: str) -> str | None:
        for v in self.values:
            if v["slot"] == slot:
                return v["how"]
        return None

    def print(self) -> None:
        width = max([len(v["slot"]) for v in self.values] + [12])
        for v in self.values:
            val = v["value"] if isinstance(v["value"], str) else json.dumps(v["value"])
            print(f"  {v['how']:<9}{v['slot']:<{width}}  {val:<22}  {v['source']}")
        for m in self.missing:
            print(f"  missing  {m['what']:<{width}}  {'':<22}  {m['why']}")
        for f in self.findings:
            print(f"  finding  {f}")
        for n in self.notes:
            print(f"  note     {n}")


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)\s*(?:[,/]\s*([\d.%]+)\s*)?\)")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def parse_colour(css: str | None) -> tuple[str, float] | None:
    """A computed colour string -> (#RRGGBB, alpha). None when unusable."""
    if not css:
        return None
    css = css.strip()
    m = _RGB.match(css)
    if m:
        a = m.group(4)
        alpha = 1.0 if a is None else (float(a.rstrip("%")) / 100 if a.endswith("%") else float(a))
        return _hex((float(m.group(1)), float(m.group(2)), float(m.group(3)))), alpha
    if _HEX.match(css):
        h = css.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return "#" + h.upper(), 1.0
    return None


def rgb_of(hexv: str) -> tuple[int, int, int]:
    h = hexv.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def to_hsl(hexv: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in rgb_of(hexv))
    hi, lo = max(r, g, b), min(r, g, b)
    l = (hi + lo) / 2
    if hi == lo:
        return 0.0, 0.0, l
    d = hi - lo
    s = d / (2 - hi - lo) if l > .5 else d / (hi + lo)
    if hi == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif hi == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h / 6, s, l


def from_hsl(h: float, s: float, l: float) -> str:
    if s == 0:
        v = l * 255
        return _hex((v, v, v))

    def hue(p: float, q: float, t: float) -> float:
        t = t % 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < .5 else l + s - l * s
    p = 2 * l - q
    return _hex(tuple(hue(p, q, h + o) * 255 for o in (1 / 3, 0, -1 / 3)))


def lightness(hexv: str) -> float:
    return to_hsl(hexv)[2]


def shift_lightness(hexv: str, delta: float) -> str:
    h, s, l = to_hsl(hexv)
    return from_hsl(h, s, max(0.0, min(1.0, l + delta)))


def mix(a: str, b: str, t: float) -> str:
    ra, rb = rgb_of(a), rgb_of(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def is_neutral(hexv: str) -> bool:
    """Greys, blacks and papers. Not a candidate for the accent."""
    _, s, l = to_hsl(hexv)
    return s < .18 or l < .10 or l > .93


def fit_contrast(fg: str, bg: str, target: float = 4.5) -> tuple[str, bool]:
    """Push a DERIVED colour away from its ground until it clears AA.

    Hue and saturation are kept, so the value stays recognisably the one it was
    derived from. Only ever called on values this module computed — a measured
    colour that fails is reported, never corrected.
    """
    if contrast(fg, bg) >= target:
        return fg, False
    up = _luminance(bg) < .18
    cur = fg
    for _ in range(60):
        cur = shift_lightness(cur, .02 if up else -.02)
        if contrast(cur, bg) >= target:
            return cur, True
        if lightness(cur) in (0.0, 1.0):
            break
    end = "#FFFFFF" if up else "#000000"
    return (end, True) if contrast(end, bg) >= target else (fg, False)


# --------------------------------------------------------------------------
# website intake
# --------------------------------------------------------------------------

SITE_JS = r"""() => {
  const abs = u => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
  const cs = el => getComputedStyle(el);
  const out = { url: location.href, title: document.title || '', bg: null, htmlBg: null,
                surfaces: [], text: [], accent: [], radii: [], scale: [], logos: [],
                inlineSvg: null };
  out.bg = cs(document.body).backgroundColor;
  out.htmlBg = cs(document.documentElement).backgroundColor;

  const all = Array.from(document.querySelectorAll('body *')).slice(0, 4000);
  for (const el of all) {
    const s = cs(el);
    if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) continue;
    const r = el.getBoundingClientRect();
    const tag = el.tagName.toLowerCase();
    const cls = (el.classList && el.classList.value) || '';
    if (r.width > 1 && r.height > 1) {
      out.surfaces.push({ colour: s.backgroundColor, area: Math.round(r.width * r.height), tag });
      const rad = s.borderTopLeftRadius;
      if (rad && rad.endsWith('px') && parseFloat(rad) > 0.5) out.radii.push(Math.round(parseFloat(rad)));
    }
    let len = 0;
    for (const n of el.childNodes) if (n.nodeType === 3) len += n.textContent.trim().length;
    if (len > 0) {
      out.text.push({ colour: s.color, len: len, size: Math.round(parseFloat(s.fontSize)),
                      weight: parseInt(s.fontWeight) || 400, family: s.fontFamily, tag: tag,
                      tracking: s.letterSpacing });
    }
    const heading = /^h[1-3]$/.test(tag);
    const button = tag === 'button' || el.getAttribute('role') === 'button' ||
                   /\b(btn|button|cta)\b/i.test(cls);
    if (heading) out.accent.push({ colour: s.color, where: 'heading text' });
    if (tag === 'a' && !button) out.accent.push({ colour: s.color, where: 'link text' });
    if (button) {
      out.accent.push({ colour: s.backgroundColor, where: 'button background' });
      out.accent.push({ colour: s.color, where: 'button text' });
      out.accent.push({ colour: s.borderTopColor, where: 'button border' });
    }
  }

  // Priority order matters, and querySelector with a list ignores it — it
  // returns whatever comes first in the document, which on a partner-logo strip
  // is somebody else's brand. So each selector is tried on its own, in order.
  const push = (u, where) => { const a = u && abs(u); if (a) out.logos.push({ url: a, where: where }); };
  const first = sels => { for (const s of sels) { const el = document.querySelector(s); if (el) return el; } return null; };
  const inHead = first(['header a[href="/"] img', 'nav a[href="/"] img',
                        'header [class*="logo" i] img', 'nav [class*="logo" i] img',
                        'header img', 'nav img']);
  const svg = first(['header a[href="/"] svg', 'header [class*="logo" i] svg',
                     'nav [class*="logo" i] svg', 'header svg', 'nav svg']);
  if (svg && svg.outerHTML.length < 200000) out.inlineSvg = svg.outerHTML;
  // A logo-classed image anywhere on the page is only worth chasing when the
  // header held nothing. Partner strips and customer logos are logo-classed too,
  // and one of those is somebody else's brand.
  const img = inHead || (svg ? null : first(['img[class*="logo" i]', 'img[alt*="logo" i]',
                                             '[class*="logo" i] img']));
  if (img) push(img.currentSrc || img.getAttribute('src'), 'header image');
  document.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]')
    .forEach(l => push(l.getAttribute('href'), 'favicon'));
  const og = document.querySelector('meta[property="og:image"], meta[name="og:image"]');
  if (og) push(og.getAttribute('content'), 'og:image');

  const roles = [['Display', 'h1'], ['Heading', 'h2'], ['Card title', 'h3'],
                 ['Body', 'p'], ['Meta', 'small, figcaption, footer p, .caption']];
  for (const [role, sel] of roles) {
    const el = Array.from(document.querySelectorAll(sel))
      .find(e => e.getBoundingClientRect().height > 0 && e.textContent.trim().length > 1);
    if (!el) continue;
    const s = cs(el);
    out.scale.push({ role: role, px: Math.round(parseFloat(s.fontSize)),
                     tracking: s.letterSpacing, family: s.fontFamily,
                     weight: parseInt(s.fontWeight) || 400 });
  }
  return out;
}"""


def read_site(url: str) -> dict:
    """Load the page in Chromium and read the COMPUTED styles off the real DOM.

    Never the stylesheet source. A stylesheet says what an author wrote; the
    computed style says what the visitor is looking at, which is the only thing
    a brand document is entitled to call the brand.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        sys.exit("Playwright is not installed. See the Install section of SKILL.md.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900},
                                user_agent=UA)
        try:
            page.goto(url, wait_until="load", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(700)
            data = page.evaluate(SITE_JS)
        finally:
            browser.close()
    return data


def _opaque(samples, key="colour"):
    for s in samples:
        c = parse_colour(s.get(key) if isinstance(s, dict) else s)
        if c and c[1] > .5:
            yield c[0], s


def site_palette(data: dict, r: Report) -> dict:
    """Computed styles -> the colours a brand document is allowed to claim."""
    found: dict[str, str] = {}

    # --- canvas: the body's own ground, else the largest painted surface -----
    body = parse_colour(data.get("bg"))
    html = parse_colour(data.get("htmlBg"))
    surfaces = [(c, s["area"], s["tag"]) for c, s in _opaque(data.get("surfaces", []))]
    biggest = max(surfaces, key=lambda x: x[1], default=None)
    def _neutralish(c: str) -> bool:
        """A page ground is almost never saturated. A brand band can be."""
        h = c.lstrip("#")
        rr, gg, bb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return (max(rr, gg, bb) - min(rr, gg, bb)) < 40

    # A saturated body background is a theme colour, not the paper the page is
    # printed on. One reference site paints body purple behind a full-height hero, so
    # trusting body alone made the brand's ground its accent.
    if body and body[1] > .5 and _neutralish(body[0]):
        found["canvas"] = body[0]
        r.measured("palette.canvas", body[0], "site: computed background-color of body")
    elif html and html[1] > .5 and _neutralish(html[0]):
        found["canvas"] = html[0]
        r.measured("palette.canvas", html[0], "site: computed background-color of html")
    else:
        # Prefer the largest NEUTRAL surface. A saturated band is a brand
        # section, not the paper the page is printed on.
        neutral = [x for x in surfaces if _neutralish(x[0])]
        pick = max(neutral, key=lambda x: x[1], default=None) or biggest
        if pick:
            found["canvas"] = pick[0]
            r.measured("palette.canvas", pick[0],
                       f"site: largest neutral surface (<{pick[2]}>, {pick[1]:,}px2)"
                       if pick in neutral else
                       f"site: largest painted surface (<{pick[2]}>, {pick[1]:,}px2)")

    # --- surface: the card ground, if the page paints one ---------------------
    if "canvas" in found:
        area: Counter = Counter()
        for c, a, _tag in surfaces:
            if c != found["canvas"] and abs(lightness(c) - lightness(found["canvas"])) < .22:
                area[c] += a
        if area:
            top, px_area = area.most_common(1)[0]
            if px_area > 20000:
                found["surface"] = top
                r.measured("palette.surface", top,
                           f"site: largest card surface behind the canvas ({px_area:,}px2)")

    # --- ink and the muted ink -----------------------------------------------
    by_colour: Counter = Counter()
    for c, s in _opaque(data.get("text", [])):
        by_colour[c] += s["len"]
    if by_colour and "canvas" in found:
        # The ink is not simply the commonest text colour: on most sites that is
        # the grey the body copy is set in, and taking it as the ink loses the
        # real one and leaves the document with no muted tone at all. Among the
        # colours in genuine use, the ink is the one that reads hardest against
        # the ground, and the muted ink is the most-used of the softer ones.
        total = sum(by_colour.values())
        real = {c: n for c, n in by_colour.items() if n >= max(30, total * .04)} or dict(by_colour)
        ground = found["canvas"]
        ink = max(real, key=lambda c: (round(contrast(c, ground), 1), real[c]))
        found["ink"] = ink
        r.measured("palette.ink", ink,
                   f"site: text colour that reads hardest on the ground, in real use "
                   f"({real[ink]:,} characters)")
        muted = [(n, c) for c, n in real.items()
                 if c != ink and 1.8 < contrast(c, ground) < contrast(ink, ground)]
        if muted:
            best = max(muted)[1]
            found["inkMuted"] = best
            r.measured("palette.inkMuted", best,
                       f"site: most-used softer text colour ({dict(real)[best]:,} characters)")
    elif by_colour:
        ink = by_colour.most_common(1)[0][0]
        found["ink"] = ink
        r.measured("palette.ink", ink,
                   f"site: most-used text colour ({by_colour[ink]:,} characters), with no ground "
                   f"measured to compare it against")

    # --- the accent -----------------------------------------------------------
    weight: Counter = Counter()
    where: dict[str, set] = defaultdict(set)
    # Chrome paints an unstyled link #0000EE, a visited one #551A8B, and some
    # engines use #0000FF. Any of them outvotes a real brand colour on a page
    # with one plain link in the footer.
    _UA_LINK = {"#0000EE", "#0000FF", "#551A8B", "#1A0DAB"}
    for c, s in _opaque(data.get("accent", [])):
        if c.upper() in _UA_LINK:
            continue
        if is_neutral(c) or c in (found.get("ink"), found.get("canvas"), found.get("surface")):
            continue
        weight[c] += 1
        where[c].add(s["where"])
    if weight:
        accent = weight.most_common(1)[0][0]
        found["accent"] = accent
        r.measured("palette.accent", accent,
                   f"site: most common non-neutral colour on {', '.join(sorted(where[accent]))} "
                   f"({weight[accent]} element{'s' if weight[accent] != 1 else ''})")
    return found


def site_type(data: dict, r: Report) -> dict:
    """Which families are actually rendering, and at which weights."""
    fam_len: Counter = Counter()
    fam_weights: dict[str, Counter] = defaultdict(Counter)
    head_len: Counter = Counter()
    stacks: Counter = Counter()
    for t in data.get("text", []):
        stacks[t.get("family", "")] += t["len"]
        fam = first_family(t.get("family", ""))
        if not fam:
            continue
        fam_len[fam] += t["len"]
        fam_weights[fam][t["weight"]] += t["len"]
        if re.fullmatch(r"h[1-3]", t.get("tag", "")):
            head_len[fam] += t["len"]
    if not fam_len:
        # Text was read; it is simply set in whatever face the reader's own
        # machine supplies, which is not a face this brand owns.
        if stacks:
            stack = stacks.most_common(1)[0][0][:80]
            r.measured("type.stack", stack, "site: the computed font-family on the page")
            r.gap("typeface", f"the site sets its type in the system stack ({stack}), so the "
                              f"face a reader sees is their machine's, not this brand's")
        else:
            r.gap("typeface", "no rendered text was read")
        return {}
    body_family = fam_len.most_common(1)[0][0]
    display_family = head_len.most_common(1)[0][0] if head_len else body_family
    out = {
        "display": {"family": display_family,
                    "weights": top_weights(fam_weights[display_family])},
        "body": {"family": body_family, "weights": top_weights(fam_weights[body_family])},
    }
    r.measured("type.display", f"{display_family} {out['display']['weights']}",
               f"site: family rendering in h1-h3 ({head_len[display_family]:,} characters)")
    r.measured("type.body", f"{body_family} {out['body']['weights']}",
               f"site: most-used rendering family ({fam_len[body_family]:,} characters)")
    return out


def first_family(stack: str) -> str | None:
    """The first family in a computed stack that is a real face, not a fallback."""
    for part in stack.split(","):
        name = part.strip().strip('"\'').strip()
        if not name or name.lower() in GENERIC_FAMILIES or name.startswith("__"):
            continue
        return name
    return None


def top_weights(counter: Counter, keep: int = 2) -> list[int]:
    """Round rendered weights onto the scale a font file can actually ship."""
    scale = [100, 200, 300, 400, 500, 600, 700, 800, 900]
    rounded: Counter = Counter()
    for w, n in counter.items():
        rounded[min(scale, key=lambda s: abs(s - w))] += n
    picked = sorted(w for w, _ in rounded.most_common(keep))
    return picked or [400, 600]


def site_scale(data: dict, r: Report) -> list[dict]:
    """The sizes the page is really set at, one row per role.

    Headings come from the first visible h1-h3, which is what a reader meets
    first. Body and meta come from the distribution instead, because the first
    <p> on a marketing page is usually an oversized lead and taking it as the
    body size puts a 32px body under a 32px heading.
    """
    by_role = {s["role"]: s for s in data.get("scale", [])}
    sizes: Counter = Counter()
    track: dict[int, Counter] = defaultdict(Counter)
    for t in data.get("text", []):
        if t.get("size") and t["len"] > 2:
            sizes[t["size"]] += t["len"]
            track[t["size"]][t.get("tracking") or "normal"] += t["len"]

    def tracking(px: int, fallback: str | None = None) -> str:
        if track.get(px):
            return track[px].most_common(1)[0][0]
        return fallback or "normal"

    rows = []
    for role in ("Display", "Heading", "Card title"):
        s = by_role.get(role)
        if s:
            rows.append({"role": role, "px": s["px"], "tracking": tracking(s["px"], s["tracking"])})
    if sizes:
        body = sizes.most_common(1)[0][0]
        rows.append({"role": "Body", "px": body, "tracking": tracking(body)})
        smaller = [s for s in sizes if s < body]
        if smaller:
            meta = max(smaller, key=lambda s: sizes[s])
            rows.append({"role": "Meta", "px": meta, "tracking": tracking(meta)})
    elif by_role.get("Body"):
        rows.append({"role": "Body", "px": by_role["Body"]["px"],
                     "tracking": by_role["Body"]["tracking"]})

    seen, out = set(), []
    for row in sorted(rows, key=lambda x: -x["px"]):
        if row["px"] in seen:
            continue
        seen.add(row["px"])
        out.append(row)
    if out:
        r.measured("type.scale", [f"{s['role']} {s['px']}px" for s in out],
                   "site: computed font-size, headings from the first visible h1-h3 and body "
                   "from the commonest size on the page")
    return out


def site_radii(data: dict, r: Report) -> list[int]:
    counts = Counter(v for v in data.get("radii", []) if 1 < v < 200)
    top = sorted({v for v, _ in counts.most_common(3)})
    if top:
        r.measured("shape.radii", top,
                   "site: the three most common non-zero border-radius values")
    return top


# --------------------------------------------------------------------------
# logo intake
# --------------------------------------------------------------------------

_STRIP = re.compile(r"<(defs|mask|clipPath|filter|pattern)\b.*?</\1\s*>", re.S | re.I)
_PAINT = re.compile(r"(?:fill|stroke|stop-color)\s*[:=]\s*[\"']?\s*([^\"';\s/>]+)", re.I)


def svg_colours(path: Path) -> list[str]:
    """An SVG's own paint. Masks, filters and defs are excluded on purpose.

    The black-and-white rectangles inside a mask are drawing machinery, not the
    brand, and counting them turns every masked logo into a monochrome brand.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = _STRIP.sub("", text)
    out = []
    for raw in _PAINT.findall(text):
        c = parse_colour(raw)
        if c and c[1] > .1:
            out.append(c[0])
    return out


def _shares(colours: list[str], counts: list[int] | None = None) -> dict[str, float]:
    """How much of this one artwork each colour covers, as a fraction of it."""
    tally: Counter = Counter()
    for i, c in enumerate(colours):
        tally[c] += counts[i] if counts else 1
    total = sum(tally.values()) or 1
    return {c: n / total for c, n in tally.items()}


def png_colours(path: Path, top: int = 6) -> tuple[list[str], list[int], float | None]:
    """Dominant colours, how many pixels each covers, and the mean lightness.

    Near-white is dropped from the dominant list because it is nearly always the
    ground the artwork was exported onto, but it is kept in the lightness mean,
    which is what decides whether this file is the light-ground or the
    dark-ground variant.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return [], [], None
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        return [], [], None
    img.thumbnail((180, 180))
    sums: dict[tuple, list] = {}
    lit, n = 0.0, 0
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a < 40:
                continue
            lit += (.2126 * r + .7152 * g + .0722 * b) / 255
            n += 1
            if r > 242 and g > 242 and b > 242:
                continue
            key = (r // 14, g // 14, b // 14)
            s = sums.setdefault(key, [0, 0, 0, 0])
            s[0] += r; s[1] += g; s[2] += b; s[3] += 1
    ranked = [s for s in sorted(sums.values(), key=lambda s: -s[3])[:top]
              if s[3] > max(4, n * .002)]
    colours = [_hex((s[0] / s[3], s[1] / s[3], s[2] / s[3])) for s in ranked]
    return colours, [s[3] for s in ranked], (lit / n if n else None)


def read_artwork(path: Path) -> dict:
    """One logo file -> its colours, how much of it each covers, and how light."""
    if path.suffix.lower() == ".svg":
        cols = svg_colours(path)
        mean = sum(_luminance(c) for c in cols) / len(cols) if cols else None
        return {"path": path, "colours": _dedupe(cols), "shares": _shares(cols),
                "lightness": mean, "kind": "svg"}
    cols, counts, mean = png_colours(path)
    return {"path": path, "colours": cols, "shares": _shares(cols, counts),
            "lightness": mean, "kind": "raster"}


def _dedupe(colours: list[str]) -> list[str]:
    seen, out = set(), []
    for c in colours:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def logo_palette(arts: list[dict], r: Report, known: dict) -> dict:
    """Palette candidates out of the artwork, filling only what is still empty.

    Every colour is scored by how much of the artwork it actually covers, summed
    over the files, so the ink is the ink the letters are drawn in and not a
    stray near-black an antialiased export left in one corner.
    """
    cover: Counter = Counter()
    for a in arts:
        for c, share in a["shares"].items():
            cover[c] += share
    pool = [c for c in cover if cover[c] >= .03] or list(cover)
    if not pool:
        return {}
    found = {}
    src = ", ".join(sorted({a["path"].name for a in arts}))

    accent = [c for c in pool if not is_neutral(c)]
    if accent and "accent" not in known:
        # The accent is the colour of emphasis, so it is usually a small part of
        # the artwork. Saturation finds it where coverage would not.
        pick = max(accent, key=lambda c: to_hsl(c)[1])
        found["accent"] = pick
        r.measured("palette.accent", pick, f"logo: most saturated colour in {src}")

    darks = [c for c in pool if lightness(c) < .35]
    if darks and "ink" not in known:
        pick = max(darks, key=lambda c: (round(cover[c], 2), -lightness(c)))
        found["ink"] = pick
        r.measured("palette.ink", pick, f"logo: the dark colour covering most of {src}")

    lights = [c for c in pool if lightness(c) > .82]
    if lights and "canvas" not in known:
        pick = max(lights, key=lambda c: (round(cover[c], 2), lightness(c)))
        found["canvas"] = pick
        r.measured("palette.canvas", pick, f"logo: the pale colour covering most of {src}")
    return found


def sort_variants(arts: list[dict], r: Report) -> list[dict]:
    """Light-ground and dark-ground versions identify themselves by lightness.

    Dark artwork is drawn for a pale ground; pale artwork is the reverse. No
    filename is trusted for this, because filenames lie and pixels do not.
    """
    known = [a for a in arts if a["lightness"] is not None]
    unknown = [a for a in arts if a["lightness"] is None]
    known.sort(key=lambda a: a["lightness"])
    for a in known:
        a["ground"] = "dark" if a["lightness"] > .6 else "light"
    for a in unknown:
        a["ground"] = "light"
    if len(known) > 1:
        r.note("logo variants sorted by mean lightness: " + ", ".join(
            f"{a['path'].name} {a['lightness']:.2f} -> {a['ground']} ground" for a in known))
    return known + unknown


# --------------------------------------------------------------------------
# dropped files
# --------------------------------------------------------------------------

def classify_folder(folder: Path, r: Report) -> dict:
    """Sort a dropped folder into logos, images, documents, fonts and Figma."""
    out: dict[str, list[Path]] = {"logo": [], "image": [], "pdf": [], "font": [], "fig": []}
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        stem = p.stem.lower()
        if ext == ".fig":
            out["fig"].append(p)
        elif ext == ".pdf":
            out["pdf"].append(p)
        elif ext in FONT_EXT:
            out["font"].append(p)
        elif ext in IMAGE_EXT:
            (out["logo"] if (ext == ".svg" or any(w in stem for w in LOGO_WORDS))
             else out["image"]).append(p)
    for p in out["fig"]:
        r.note(f"{p.name} is a Figma file — run scripts/fig_decode.py on it and re-run "
               f"intake against what it writes out. This tool does not open .fig itself.")
    for p in out["pdf"]:
        r.note(f"{p.name}: {_pdf_pages(p)} — copied to assets/source/")
    for p in out["font"]:
        r.note(f"{p.name} is a font file — copied to assets/fonts/. Point type.display.file "
               f"at it to use it instead of a fetched family.")
    return out


def _pdf_pages(path: Path) -> str:
    try:
        from pypdf import PdfReader
        return f"{len(PdfReader(str(path)).pages)} page PDF"
    except Exception as exc:
        return f"PDF, page count unreadable ({exc})"


# --------------------------------------------------------------------------
# palette assembly
# --------------------------------------------------------------------------

def build_palette(found: dict, r: Report) -> dict:
    """Everything measured, plus the rest computed from it and labelled as such.

    The engine has defaults for every slot, and they are somebody else's brand.
    Leaving a slot empty silently adopts them, so each one is filled from this
    brand's own measured values instead — and the report says which is which.
    """
    p: dict[str, str] = {}
    measured = set(found)

    if "canvas" not in found and "ink" in found:
        # Dark artwork with nothing else known is drawn for a pale ground.
        found["canvas"] = "#FFFFFF" if lightness(found["ink"]) < .5 else "#141414"
        r.derived("palette.canvas", found["canvas"],
                  "no ground measured; a plain ground opposite the measured ink")
    if "ink" not in found and "canvas" in found:
        found["ink"] = "#141414" if lightness(found["canvas"]) > .5 else "#FFFFFF"
        r.derived("palette.ink", found["ink"],
                  "no text colour measured; plain ink opposite the measured ground")
    if "canvas" not in found and "ink" not in found:
        found["canvas"], found["ink"] = "#FFFFFF", "#141414"
        r.derived("palette.canvas", "#FFFFFF", "nothing measured: plain paper")
        r.derived("palette.ink", "#141414", "nothing measured: plain ink")
        r.gap("colour", "nothing was read, so not one colour in this file is this brand's")

    canvas, ink = found["canvas"], found["ink"]
    p["canvas"], p["ink"] = canvas, ink

    # card surface: a step off the canvas, away from the ink so cards lift
    if "surface" in found:
        p["surface"] = found["surface"]
    else:
        step = .035 if lightness(canvas) < lightness(ink) else -.035
        surface = shift_lightness(canvas, step)
        if surface == canvas:  # canvas already at the end of the axis
            surface = shift_lightness(canvas, -step)
        p["surface"] = surface
        r.derived("palette.surface", surface,
                  f"canvas lightness moved {abs(step) * 100:.1f}% away from the ink so cards "
                  f"separate from the ground")

    # muted ink: the ink walked toward the ground, then walked back until it reads
    if "inkMuted" in found:
        p["inkMuted"] = found["inkMuted"]
    else:
        muted = mix(ink, canvas, .42)
        fixed, moved = fit_contrast(muted, canvas)
        p["inkMuted"] = fixed
        r.derived("palette.inkMuted", fixed,
                  "ink mixed 42% toward the canvas" +
                  (", then pulled back until it clears AA on the canvas" if moved else ""))

    # the dark ground: the darkest thing this brand actually owns
    dark = min([canvas, ink] + ([found["accent"]] if "accent" in found else []), key=lightness)
    if lightness(dark) > .3:
        dark = shift_lightness(dark, -(lightness(dark) - .12))
        r.derived("palette.groundDark", dark,
                  "the darkest colour on file, taken down to a usable dark ground")
    else:
        r.derived("palette.groundDark", dark, "the darkest colour on file, used as-is")
    p["groundDark"] = dark

    light = max([canvas, ink], key=lightness)
    on_dark, moved = fit_contrast(light, dark)
    p["inkOnDark"] = on_dark
    r.derived("palette.inkOnDark", on_dark,
              "the lightest colour on file" + (", lifted until it clears AA on the dark ground"
                                               if moved else ", which clears AA on the dark ground"))

    if "accent" in found:
        p["accent"] = found["accent"]
        pressed = shift_lightness(found["accent"], -.09 if lightness(found["accent"]) > .25 else .09)
        p["accentPressed"] = pressed
        r.derived("palette.accentPressed", pressed, "accent lightness moved 9% for the pressed state")
        best = max([ink, on_dark], key=lambda c: contrast(c, found["accent"]))
        fixed, moved = fit_contrast(best, found["accent"])
        p["inkOnAccent"] = fixed
        r.derived("palette.inkOnAccent", fixed,
                  "whichever of the brand's two inks reads best on the accent" +
                  (", adjusted until it clears AA" if moved else ""))
    else:
        # No accent was found, so no accent is claimed. The document runs on the
        # brand's own ink rather than adopting the engine's default, which is a
        # colour from another brand entirely.
        p["accent"] = ink
        p["accentPressed"] = shift_lightness(ink, .09 if lightness(ink) < .5 else -.09)
        p["inkOnAccent"], _ = fit_contrast(max([canvas, on_dark], key=lambda c: contrast(c, ink)),
                                           ink)
        r.derived("palette.accent", ink,
                  "NO ACCENT FOUND — the document runs monochrome on this brand's own ink rather "
                  "than adopting a colour it has never used")
        r.derived("palette.accentPressed", p["accentPressed"],
                  "ink lightness moved 9% for the pressed state")
        r.derived("palette.inkOnAccent", p["inkOnAccent"],
                  "whichever ground reads on the ink standing in for the accent")
        r.gap("accent", "no non-neutral colour on the buttons, links, headings or artwork read")

    # measured pairings are reported, never corrected
    for name, fg, bg in (("ink on canvas", p["ink"], p["canvas"]),
                         ("ink on accent", p["inkOnAccent"], p["accent"])):
        if {fg, bg} <= measured and contrast(fg, bg) < 4.5:
            r.finding(f"{name} ({fg} on {bg}) is {contrast(fg, bg):.2f}:1 — both are measured "
                      f"values, so neither was changed")
    return p


# --------------------------------------------------------------------------
# fonts
# --------------------------------------------------------------------------

def _cache_face(family: str, weights: list[int]) -> bool:
    """Pull every weight into assets/fonts/ so the render needs no network."""
    try:
        for w in weights:
            fonts_mod._cached_weight(family, w) or fonts_mod._download_weight(family, w)
        return True
    except Exception:
        return False


def resolve_family(family: str | None, weights: list[int], r: Report, role: str) -> dict:
    """Make sure the declared face can actually render, offline, afterwards.

    A face is only worth declaring if the document can be built from it. A
    licensed or obfuscated web font resolves to nothing, and a brand file that
    names it renders as a silent fallback nobody chose.
    """
    if not family:
        r.derived(f"type.{role}", f"{FALLBACK_FAMILY} {weights}",
                  "no family measured; the engine's cached fallback face")
        return {"family": FALLBACK_FAMILY, "weights": weights}
    if _cache_face(family, weights):
        return {"family": family, "weights": weights}
    r.note(f"'{family}' is rendering on the site but is not a fetchable web font, so the "
           f"document is set in {FALLBACK_FAMILY}. Drop the real file into assets/fonts/ "
           f"and set type.{role}.file to use it.")
    # The measured weights belong to the measured face. If the stand-in cannot be
    # cached at them, it drops to the pair the engine already ships.
    if not _cache_face(FALLBACK_FAMILY, weights):
        weights = [400, 600]
    r.derived(f"type.{role}", f"{FALLBACK_FAMILY} {weights}",
              f"substituted for the measured '{family}', which could not be resolved")
    return {"family": FALLBACK_FAMILY, "weights": weights}


# --------------------------------------------------------------------------
# assets
# --------------------------------------------------------------------------

def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.") or "asset"
    return name[:60].lower()


def copy_in(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name(src.name)
    i = 2
    while dest.exists() and dest.read_bytes() != src.read_bytes():
        dest = dest_dir / f"{safe_name(src.stem)}-{i}{src.suffix.lower()}"
        i += 1
    shutil.copyfile(src, dest)
    return dest


def download(url: str, dest_dir: Path, r: Report) -> Path | None:
    """GET one asset. Read-only, and it never follows anything but the URL given."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read(6_000_000)
    except Exception as exc:
        r.note(f"could not download {url.split('?')[0][:80]} ({exc})")
        return None
    if not (ctype.startswith("image/") or "svg" in ctype):
        r.note(f"skipped {url.split('?')[0][:80]} — it is {ctype or 'unknown'}, not an image")
        return None
    stem = safe_name(Path(url.split("?")[0]).name) or "logo"
    if "." not in stem:
        stem += {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg",
                 "image/webp": ".webp"}.get(ctype.split(";")[0], ".png")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / stem
    dest.write_bytes(data)
    return dest


# --------------------------------------------------------------------------
# the brand file
# --------------------------------------------------------------------------

NOT_RECORDED = "Not recorded. "


def overview_blocks(has_site: bool) -> list[dict]:
    close = ("The business's own answer, in one sentence, written into this block."
             if not has_site else
             "The business's own answer. The website was read for colour, type and shape only; "
             "nothing on it was treated as an approved statement of what the business is.")
    return [
        {"title": "What it is",
         "body": NOT_RECORDED + "One plain sentence naming the product or service and who buys "
                                "it. " + close},
        {"title": "Who it is for",
         "body": NOT_RECORDED + "The specific buyer, described the way they would describe "
                                "themselves."},
        {"title": "How it should feel",
         "body": NOT_RECORDED + "Three words, chosen so their opposites are also plausible "
                                "brands."},
        {"title": "Voice and tagline",
         "body": NOT_RECORDED + "Nothing has been approved, so nothing is quoted here. Any line "
                                "currently circulating is a draft."},
    ]


def provenance_rules(r: Report) -> list[str]:
    """Hard rules a stranger can follow, stated from what was actually read."""
    items = []
    measured = [v for v in r.values if v["how"] == "measured" and v["slot"].startswith("palette.")]
    if measured:
        items.append("Measured values, taken from what the brand already ships: " +
                     ", ".join(f"{v['slot'].split('.')[1]} {v['value']}" for v in measured) +
                     ". These are the brand. Do not change them here.")
    derived = [v for v in r.values if v["how"] == "derived" and v["slot"].startswith("palette.")]
    if derived:
        items.append("Computed values, worked out from the measured ones so the document has a "
                     "full palette: " +
                     ", ".join(v["slot"].split(".")[1] for v in derived) +
                     ". They are a starting point and the brand's owner can overrule any of them.")
    if any(m["what"] == "accent" for m in r.missing):
        items.append("No accent colour was found, so this brand does not have one on record. The "
                     "document runs monochrome rather than showing a colour the brand has never "
                     "used. Set palette.accent once a real accent exists.")
    items.append("One accent colour. Variety comes from photography and from space, never from "
                 "adding hexes.")
    items.append("Never recolour the artwork. Pick the variant that suits the ground instead.")
    return items


def build_sections(r: Report, palette: dict, arts: list[dict], images: list[Path],
                   scale: list[dict], type_block: dict, has_site: bool) -> list[dict]:
    sections: list[dict] = [{
        "id": "overview",
        "title": "Overview",
        "summary": "What this business is, and which parts of the brand are not written down yet.",
        "pages": [
            {"kind": "overview", "captionTitle": "Overview",
             "caption": "Every block below is empty on purpose. Nothing about what this business "
                        "is was measurable, and a plausible sentence here would outlive the "
                        "person who knew it was a guess.",
             "blocks": overview_blocks(has_site)},
            {"kind": "prose", "captionTitle": "Measured, computed, missing",
             "caption": "Where each value in this document came from. Nothing here was chosen to "
                        "look right.",
             "items": provenance_rules(r)},
        ],
    }]

    marks = [a for a in arts if any(w in a["path"].stem.lower() for w in MARK_WORDS)]
    lockups = [a for a in arts if a not in marks]
    if arts:
        pages = []
        for a in lockups[:3]:
            variant = "Reversed" if a.get("ground") == "dark" else "Primary"
            if any(p.get("variant") == variant for p in pages):
                variant = a["path"].stem.replace("-", " ").title()
            page = {"kind": "lockup", "variant": variant,
                    "src": a["rel"], "captionTitle": variant,
                    "caption": f"Read from {a['path'].name}. "
                               + ("Its artwork is pale, so it is the version for dark grounds."
                                  if a.get("ground") == "dark" else
                                  "Its artwork is dark, so it is the version for pale grounds.")}
            if a.get("ground") == "dark":
                page["ground"] = "dark"
            pages.append(page)
        if marks:
            pages.append({
                "kind": "marks", "captionTitle": "The mark",
                "caption": "The symbol alone, for avatars, app icons and favicons. The size below "
                           "which the full lockup stops reading is not recorded yet.",
                "marks": [{"label": m["path"].stem.replace("-", " ").title(), "src": m["rel"],
                           **({"ground": "dark"} if m.get("ground") == "dark" else {})}
                          for m in marks[:4]]})
        if pages:
            sections.append({"id": "logo", "title": "Logo",
                             "summary": "The artwork that was supplied, and the grounds each "
                                        "version is drawn for.",
                             "pages": pages})

    core = [("Canvas", palette["canvas"]), ("Ink", palette["ink"])]
    if r.how("palette.accent") == "measured":
        core.append(("Accent", palette["accent"]))
    extended = [(n, palette[k]) for n, k in (("Surface", "surface"), ("Ink muted", "inkMuted"),
                                             ("Dark ground", "groundDark"),
                                             ("Ink on dark", "inkOnDark"))]
    colour_pages = [{
        "kind": "colourStack", "captionTitle": "Core",
        "caption": "Measured off what the brand already ships. These are the values every other "
                   "colour in this document was worked out from.",
        "colours": [{"name": n, "hex": h} for n, h in core]}]
    if extended:
        colour_pages.append({
            "kind": "colourRamp", "captionTitle": "Computed",
            "caption": "Not measured. Each one was computed from the core above so the system is "
                       "complete, and each one is the brand owner's to overrule.",
            "colours": [{"name": n, "hex": h} for n, h in extended]})
    sections.append({"id": "colour", "title": "Colour",
                     "summary": "The measured core, and the values computed from it.",
                     "pages": colour_pages})

    faces, seen = [], set()
    for role in ("display", "body"):
        spec = type_block[role]
        if spec["family"] in seen:
            continue
        seen.add(spec["family"])
        faces.append({
            "kind": "typeface", "family": spec["family"],
            "captionTitle": "The typeface" if len(seen) == 1 else "The second typeface",
            "caption": f"Set in {spec['family']}, the family rendering in "
                       f"{'headings' if role == 'display' else 'body text'}. What each weight is "
                       f"for is not recorded yet.",
            "weights": [{"name": f"{w}", "value": w} for w in spec["weights"]]})
    if scale:
        faces.append({
            "kind": "typescale", "captionTitle": "The scale",
            "caption": "Measured off the live site, one element per role. Every row is set here at "
                       "its true pixel value, so a wrong number is visible rather than hidden.",
            "scale": scale})
    sections.append({"id": "typography", "title": "Typography",
                     "summary": "The families actually rendering, and the sizes they are set at.",
                     "pages": faces})

    if images:
        sections.append({
            "id": "applications", "title": "Applications",
            "summary": "The artefacts that came in with the brand.",
            "pages": [{"kind": "applications", "captionTitle": "Touchpoints",
                       "caption": "Supplied with the brand, not made for this document. They are "
                                  "here as evidence of what the brand looks like in use.",
                       "items": [{"src": p} for p in images[:6]]}]})
    return sections


def build_brand(name: str, slug: str, palette: dict, type_block: dict, radii: list[int],
                sections: list[dict], marks: dict, r: Report, sources: dict) -> dict:
    shape = {}
    if radii:
        names = ["radiusField", "radiusCard", "radiusPill"]
        for key, value in zip(names, radii):
            shape[key] = value
        for key in names[len(radii):]:
            r.derived(f"shape.{key}", None, "not measured; the engine's default")
    brand = {
        "$intake": {
            "ranAt": date.today().isoformat(),
            "sources": sources,
            "read": "Every value below records how it got here. 'measured' was taken off "
                    "something the brand already ships. 'derived' was computed from a measured "
                    "value and is a starting point, not the brand. Nothing was invented.",
            "values": r.values,
            "missing": r.missing,
            "findings": r.findings,
            "notes": r.notes,
        },
        "meta": {
            "slug": slug,
            "name": name,
            "wordmark": name,
            "document": "Brand Guideline",
            "boardTitle": "Brand Board",
            "year": date.today().year,
            "legal": "All rights reserved",
            "closing": "Thank you",
            "line": "Built by intake from what this brand already ships. Measured values are the "
                    "brand; computed values are a starting point and say so.",
            "order": 100,
            **marks,
        },
        "palette": palette,
        "type": {
            "display": {**type_block["display"],
                        "weight": max(type_block["display"]["weights"]),
                        "weightXL": min(type_block["display"]["weights"])},
            "body": {**type_block["body"], "weight": min(type_block["body"]["weights"])},
        },
        "sections": sections,
    }
    if shape:
        brand["shape"] = shape
    return brand


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "brand"


def gather_logos(logo_args: list[Path], dropped: list[Path], out: Path,
                 r: Report) -> list[Path]:
    files: list[Path] = []
    for given in logo_args:
        if given.is_dir():
            files += [p for p in sorted(given.iterdir())
                      if p.suffix.lower() in IMAGE_EXT and p.is_file()]
        elif given.exists():
            files.append(given)
        else:
            r.note(f"--logo {given} does not exist")
    files += dropped
    return [copy_in(f, out / "assets" / "logo") for f in files]


def run(args) -> int:
    r = Report()
    slug = args.slug or slugify(args.name)
    out = (args.out or (ROOT / "brands" / slug)).resolve()
    if (out / "brand.json").exists() and not args.force:
        print(f"{out}/brand.json already exists. Pass --force to overwrite it.", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    slug = out.name
    sources: dict = {}

    # --- website ----------------------------------------------------------
    site_found: dict = {}
    type_measured: dict = {}
    radii: list[int] = []
    scale: list[dict] = []
    site_images: list[Path] = []
    site_logos: list[Path] = []
    if args.site:
        try:
            data = read_site(args.site)
        except Exception as exc:
            r.note(f"the site could not be read ({exc})")
            data = None
        if data:
            from urllib.parse import urlparse
            u = urlparse(data.get("url") or args.site)
            sources["site"] = f"{u.scheme}://{u.netloc}"
            site_found = site_palette(data, r)
            type_measured = site_type(data, r)
            radii = site_radii(data, r)
            scale = site_scale(data, r)
            if data.get("inlineSvg"):
                p = out / "assets" / "logo" / "header-inline.svg"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(data["inlineSvg"], encoding="utf-8")
                site_logos.append(p)
                r.measured("logo.header", p.name, "site: inline <svg> in the header")
            seen_urls = set()
            for cand in data.get("logos", []):
                if cand["url"] in seen_urls:
                    continue
                seen_urls.add(cand["url"])
                target = "applications" if cand["where"] == "og:image" else "logo"
                got = download(cand["url"], out / "assets" / target, r)
                if not got:
                    continue
                r.measured(f"logo.{cand['where'].replace(' ', '-')}", got.name,
                           f"site: {cand['where']}")
                (site_images if target == "applications" else site_logos).append(got)
            if not site_logos:
                r.gap("logo", "no header image, inline header SVG or favicon on the site")

    # --- dropped folder ---------------------------------------------------
    dropped_logos: list[Path] = []
    dropped_images: list[Path] = []
    if args.files:
        folder = args.files
        if not folder.is_dir():
            r.note(f"--files {folder} is not a folder")
        else:
            sources["files"] = str(folder)
            kinds = classify_folder(folder, r)
            dropped_logos = kinds["logo"]
            dropped_images = [copy_in(p, out / "assets" / "applications")
                              for p in kinds["image"][:8]]
            for p in kinds["pdf"][:6]:
                copy_in(p, out / "assets" / "source")
            for p in kinds["font"][:6]:
                copy_in(p, out / "assets" / "fonts")
            r.measured("files", {k: len(v) for k, v in kinds.items() if v} or "nothing usable",
                       f"folder: {folder}")

    # --- logos ------------------------------------------------------------
    logo_files = site_logos + gather_logos(args.logo, dropped_logos, out, r)
    if args.logo:
        sources["logo"] = [str(p) for p in args.logo]
    # A favicon declared three times downloads to one file three times.
    logo_files = list(dict.fromkeys(p.resolve() for p in logo_files))[:6]
    arts = [read_artwork(p) for p in logo_files]
    arts = [a for a in arts if a["colours"] or a["kind"] == "raster"]
    arts = sort_variants(arts, r)
    for a in arts:
        a["rel"] = str(a["path"].relative_to(out))
    logo_found = logo_palette(arts, r, site_found) if arts else {}

    # --- palette ----------------------------------------------------------
    found = {**logo_found, **site_found}
    if not found:
        r.note("nothing was supplied but a name — what follows is a valid, honest, empty brand, "
               "and every value in it is labelled as computed")
    palette = build_palette(found, r)

    # --- type -------------------------------------------------------------
    display = type_measured.get("display", {})
    body = type_measured.get("body", {})
    type_block = {
        "display": resolve_family(display.get("family"), display.get("weights", [400, 600]),
                                  r, "display"),
        "body": resolve_family(body.get("family"), body.get("weights", [400, 600]), r, "body"),
    }
    if not type_measured:
        r.gap("typeface", "no site was read, so the document is set in the engine's cached "
                          "fallback face")

    # --- artwork slots ----------------------------------------------------
    marks = {}
    if arts:
        # The cover prints on a dark ground and the board head on the canvas. An
        # artwork that cannot be seen on its ground is not a logo on a page, it
        # is a blank square, so the slot is left empty and recorded as a gap.
        lit = lambda a: a["lightness"] if a["lightness"] is not None else .5
        cover = max(arts, key=lit)
        board = min(arts, key=lit)
        if lit(cover) > .45:
            marks["coverMark"] = cover["rel"]
        else:
            r.gap("logo for dark grounds",
                  "every artwork supplied is dark, so none of them reads on the dark cover — "
                  "the cover carries no logo rather than an invisible one")
        if lit(board) < .62:
            marks["boardMark"] = board["rel"]
        else:
            r.gap("logo for pale grounds",
                  "every artwork supplied is pale, so none of them reads on the canvas")
    else:
        r.gap("logo", "no artwork was supplied and none was found")

    images = [str(p.relative_to(out)) for p in (site_images + dropped_images)]
    sections = build_sections(r, palette, arts, images, scale, type_block, bool(args.site))
    brand = build_brand(args.name, slug, palette, type_block, radii, sections, marks, r, sources)

    (out / "brand.json").write_text(json.dumps(brand, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")

    print(f"\n{args.name}  ->  {out}")
    if sources:
        for k, v in sources.items():
            print(f"  source   {k}: {v}")
    print()
    r.print()
    from . import plan as plan_mod
    print(f"\n  wrote    {out / 'brand.json'} — {len(brand['sections'])} sections, "
          f"{len(plan_mod.build(brand))} pages")
    print(f"  next     python3 -m engine.verify {out}\n"
          f"           python3 -m engine.render {out / 'brand.json'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m engine.intake",
        description="Turn a website, a logo, a folder, or nothing at all into a valid brand.json.")
    ap.add_argument("--name", required=True, help="the business name — the only required input")
    ap.add_argument("--site", help="a public URL, read read-only for its computed styles")
    ap.add_argument("--logo", type=Path, action="append", default=[],
                    help="a logo file or a folder of them; repeatable")
    ap.add_argument("--files", type=Path, help="a folder of whatever the business has")
    ap.add_argument("--out", type=Path, help="defaults to brands/<slug>")
    ap.add_argument("--slug", help="defaults to a slug of the name")
    ap.add_argument("--force", action="store_true", help="overwrite an existing brand.json")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
