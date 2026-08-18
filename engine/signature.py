"""Email signatures a mail client will actually accept.

A picture of a signature is not a signature. It cannot be selected, the links do
not work, and it disappears when images are blocked. This emits real HTML built
the way mail clients still demand: tables, inline styles, no flexbox, no grid,
no stylesheet.

    python3 -m engine.signature brands/<slug>/brand.json
    python3 -m engine.signature brands/<slug>/brand.json --name "Full Name" --role "Role"

Writes one `.html` per person into `out/<slug>/signatures/`, plus `index.html`
listing them with a copy button. Open one, select all, copy, and paste it into
Gmail, Outlook or Apple Mail.

People come from `meta.people` in the brand file. With none declared it emits a
single placeholder signature, because a template nobody has filled in is still
better than a team with no signature at all.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .pages import esc
from .theme import PALETTE_DEFAULTS

ROOT = Path(__file__).resolve().parent.parent


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "signature").lower()).strip("-") or "signature"


def _logo_url(brand: dict) -> str:
    """An absolute https URL to a PNG.

    Three things all have to be true or the logo simply does not appear in the
    recipient's client: it must be a real URL, because data URIs get stripped and
    a local file does not exist for them; it must be https; and it must be PNG,
    because Gmail refuses SVG outright.
    """
    return (brand.get("meta", {}).get("signatureLogo")
            or brand.get("meta", {}).get("pageUrl", "").rstrip("/") + "/assets/logo/lockup-primary-email.png"
            if brand.get("meta", {}).get("pageUrl") else "")


def signature_html(brand: dict, person: dict) -> str:
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    meta = brand.get("meta", {})
    body_face = brand.get("type", {}).get("body", {}).get("family", "Arial")
    # A mail client will not load a webfont, so name the brand face first and
    # let a real fallback carry it. Anything else renders as Times.
    stack = f"'{body_face}', 'Helvetica Neue', Helvetica, Arial, sans-serif"

    logo = _logo_url(brand)
    logo_cell = (
        f'<img src="{esc(logo)}" alt="{esc(meta.get("name",""))}" height="34" '
        f'style="display:block;border:0;outline:none;height:34px;width:auto">'
        if logo else
        f'<span style="font:600 20px {stack};color:{p["ink"]};letter-spacing:-.02em">'
        f'{esc(meta.get("wordmark",""))}</span>')

    rows = []
    if person.get("email"):
        rows.append(f'<a href="mailto:{esc(person["email"])}" '
                    f'style="color:{p["accent"]};text-decoration:none">{esc(person["email"])}</a>')
    if person.get("phone"):
        rows.append(f'<span style="color:{p["inkMuted"]}">{esc(person["phone"])}</span>')
    if person.get("site"):
        url = person["site"]
        href = url if url.startswith("http") else f"https://{url}"
        rows.append(f'<a href="{esc(href)}" '
                    f'style="color:{p["accent"]};text-decoration:none">{esc(url)}</a>')
    contact = ('<span style="color:%s">&nbsp;&nbsp;/&nbsp;&nbsp;</span>' % p["inkMuted"]).join(rows)

    return f"""<table cellpadding="0" cellspacing="0" border="0" role="presentation"
 style="border-collapse:collapse;font-family:{stack};font-size:14px;line-height:1.45;color:{p['ink']}">
 <tr><td style="padding:0 0 10px 0">{logo_cell}</td></tr>
 <tr><td style="padding:0 0 2px 0;font-size:15px;font-weight:700;color:{p['ink']}">
   {esc(person.get('name', 'Full Name'))}</td></tr>
 <tr><td style="padding:0 0 10px 0;font-size:14px;color:{p['inkMuted']}">
   {esc(person.get('role', 'Role or title'))}</td></tr>
 <tr><td style="padding:10px 0 0 0;border-top:1px solid {p['accent']};font-size:13px">
   {contact}</td></tr>
</table>"""


def page(brand: dict, person: dict, html: str) -> str:
    """A wrapper with a copy button, so nobody has to open a code editor."""
    p = {**PALETTE_DEFAULTS, **brand.get("palette", {})}
    name = esc(person.get("name", "Signature"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{name} — email signature</title><style>
body{{margin:0;padding:40px;background:{p['canvas']};color:{p['ink']};
 font:400 15px/1.5 -apple-system,system-ui,'Helvetica Neue',Arial,sans-serif}}
.wrap{{max-width:640px;margin:0 auto}}
h1{{font-size:22px;letter-spacing:-.02em;margin:0 0 6px}}
p{{color:{p['inkMuted']};margin:0 0 22px}}
.box{{background:{p['surface']};border-radius:14px;padding:26px;margin-bottom:16px}}
button{{background:{p['accent']};color:{p['inkOnAccent']};border:0;border-radius:40px;
 padding:12px 22px;font:inherit;cursor:pointer}}
code{{font-size:12px;color:{p['inkMuted']}}}
</style></head><body><div class="wrap">
<h1>{name}</h1>
<p>Select the block below, copy it, and paste it into your mail client's signature
 setting. Gmail, Outlook and Apple Mail all keep the formatting.</p>
<div class="box" id="sig">{html}</div>
<button onclick="copySig()">Copy signature</button>
<p style="margin-top:18px"><code>Pasting into Gmail: Settings, See all settings,
 Signature. Outlook: Settings, Mail, Compose and reply.</code></p>
</div><script>
function copySig(){{
  var r=document.createRange(); r.selectNode(document.getElementById('sig'));
  var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
  document.execCommand('copy'); s.removeAllRanges();
  document.querySelector('button').textContent='Copied';
}}
</script></body></html>"""


def build(brand: dict, out: Path, people: list[dict]) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for person in people:
        html = signature_html(brand, person)
        f = out / f"{_slug(person.get('name', 'signature'))}.html"
        f.write_text(page(brand, person, html), encoding="utf-8")
        (out / f"{f.stem}.snippet.html").write_text(html, encoding="utf-8")
        made.append(f)
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build pasteable email signatures.")
    ap.add_argument("brand", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--name")
    ap.add_argument("--role")
    ap.add_argument("--email")
    ap.add_argument("--phone")
    ap.add_argument("--site")
    args = ap.parse_args(argv)

    brand = json.loads(args.brand.read_text(encoding="utf-8"))
    slug = brand["meta"].get("slug") or args.brand.parent.name
    out = args.out or (ROOT / "out" / slug / "signatures")

    if args.name:
        people = [{k: v for k, v in vars(args).items()
                   if k in ("name", "role", "email", "phone", "site") and v}]
    else:
        # Never ship a real person as a default. A placeholder is honest.
        people = brand["meta"].get("people") or [
            {"name": "Full Name", "role": "Role or title",
             "email": "name@example.com", "site": "example.com"}]

    made = build(brand, out, people)
    print(f"signatures {len(made)} -> {out}")
    for f in made:
        print(f"   {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
