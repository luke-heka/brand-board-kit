"""Pull a Figma file apart into files a person, and a later build, can read.

    python3 scripts/figma_pull.py <file-key-or-url>
    python3 scripts/figma_pull.py <url> --node 7774:145 --images --format svg

A Figma file is the design source of record and a black box at the same time:
the only way to see what is in it is to scroll it, and the only way to reuse a
colour is to eyedropper it. Dev Mode's MCP would answer that, but it is gated
behind a paid seat. The REST API is not — it needs a Personal Access Token with
read scopes and nothing else.

So this reads the file and writes down what is actually in there:

    structure.json      the raw document tree, so nothing is lost
    INVENTORY.md        every page and every top-level frame, as a table
    styles.json         named text, paint and effect styles, resolved to values
    tokens.draft.json   every distinct fill and type combination, by frequency
    assets/             rendered SVG or PNG per frame, with --images

This tool only ever reads. There is no code path here that writes to Figma.
"""

from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.figma.com"

# Figma rejects an id list past a certain length rather than truncating it, and
# the documented limit has moved before, so batches stay well under it.
CHUNK = 50
PAUSE = 0.5  # between render batches, so a large file does not walk into a 429

URL_KEY = re.compile(r"figma\.com/(?:file|design|proto|board|slides|deck)/([A-Za-z0-9]+)")
BARE_KEY = re.compile(r"^[A-Za-z0-9]{8,}$")

# Types worth asking Figma to render. Anything else on a canvas is scaffolding.
RENDERABLE = {
    "FRAME", "GROUP", "COMPONENT", "COMPONENT_SET", "INSTANCE", "VECTOR",
    "RECTANGLE", "ELLIPSE", "POLYGON", "STAR", "LINE", "BOOLEAN_OPERATION",
    "TEXT", "SLICE",
}


class FigmaError(RuntimeError):
    """Something a message can tell the user how to fix."""


# --- token -----------------------------------------------------------------
# The token is read from Keeper at runtime and held in memory only. It is never
# printed, never written to a file, and never put into an error message.

def token_help(record: str) -> str:
    return (
        f"No Figma token found.\n"
        f"\n"
        f"Simplest: put it in the environment and run again.\n"
        f"  export FIGMA_TOKEN=your-token-here\n"
        f"\n"
        f"Or, if you keep secrets in a Keeper vault, store it under '{record}'.\n"
        f"\n"
        f"One-time setup:\n"
        f"  1. In Figma, open Settings, then Security, then Personal access tokens.\n"
        f"  2. Generate a new token.\n"
        f"  3. Give it read access to 'file_content' and 'file_dev_resources'.\n"
        f"     Read is enough. This tool never writes to Figma.\n"
        f"  4. Copy the token — Figma shows it once and never again.\n"
        f"  5. Export it as FIGMA_TOKEN, or store it in your password manager\n"
        f"     under the record name '{record}'.\n"
        f"\n"
        f"Then run this command again."
    )


def read_token(record: str) -> str:
    # The environment first: it needs no vault, no CLI and no account, which is
    # the only version of this that works on somebody else's machine.
    env = os.environ.get("FIGMA_TOKEN", "").strip()
    if env:
        return env
    try:
        proc = subprocess.run(["kp", "pass", record],
                              capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise FigmaError(
            "No FIGMA_TOKEN is set, and no password-manager CLI is on PATH.\n\n"
            + token_help(record))
    except subprocess.TimeoutExpired:
        raise FigmaError(
            f"Reading '{record}' from the password manager timed out after 30 "
            f"seconds. It is probably locked. Unlock it, or set FIGMA_TOKEN instead.")
    token = proc.stdout.strip()
    if proc.returncode != 0 or not token:
        raise FigmaError(token_help(record))
    return token


# --- target ----------------------------------------------------------------

def normalise_node_id(raw: str) -> str:
    """`node-id=7774-145` in a URL is node `7774:145` in the API."""
    nid = urllib.parse.unquote(raw).strip()
    return nid if ":" in nid else nid.replace("-", ":", 1)


def parse_target(raw: str) -> tuple[str, str | None]:
    """Accept a bare file key or any Figma URL, and pull the node out of the URL."""
    raw = raw.strip()
    if BARE_KEY.match(raw):
        return raw, None
    m = URL_KEY.search(raw)
    if not m:
        raise FigmaError(
            f"'{raw}' is not a Figma file key or a Figma file URL.\n"
            f"Open the file in Figma and copy the address bar. It looks like\n"
            f"  https://www.figma.com/design/<key>/<file-name>\n"
            f"or paste just the <key> part on its own.")
    node = None
    values = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("node-id")
    if values:
        node = normalise_node_id(values[0])
    return m.group(1), node


# --- HTTP ------------------------------------------------------------------

def _detail(exc: urllib.error.HTTPError) -> str:
    """Figma's own error text, which carries no credential."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
        return str(body.get("err") or body.get("message") or "").strip()
    except Exception:
        return ""


def _explain(code: int, detail: str, key: str) -> str:
    tail = f"\nFigma said: {detail}" if detail else ""
    if code == 401:
        return ("Figma rejected the token (401). It has expired, been revoked, or "
                "is not a Personal Access Token.\nGenerate a fresh one in Settings, "
                "Security, Personal access tokens, and save it over the same Keeper "
                "record." + tail)
    if code == 403:
        return ("Figma refused the request (403). Either the token is missing a "
                "scope or the account cannot open this file.\n"
                "The token needs 'file_content:read', and 'file_dev_resources:read' "
                "for dev resources. Scopes are fixed when the token is created, so "
                "a token made without them has to be replaced, not edited." + tail)
    if code == 404:
        return (f"Figma has no file '{key}' for this account (404).\n"
                f"Either the key is wrong — it is the part between /design/ and the "
                f"file name in the URL — or the account that owns this token has no "
                f"access to the file. Open the file in a browser signed in as that "
                f"account to check." + tail)
    if code == 429:
        return ("Figma is rate limiting this token (429) and did not let up after "
                "several waits.\nLeave it a few minutes, then run again. If this "
                "happened during --images, the file has a lot of frames; re-run "
                "with --node to pull one page at a time." + tail)
    if code == 400:
        return f"Figma rejected the request as malformed (400).{tail}"
    return f"Figma returned HTTP {code}.{tail}"


def api_get(path: str, token: str, params: dict | None = None, *,
            key: str = "", attempts: int = 4) -> dict:
    url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers={
        "X-Figma-Token": token,
        "User-Agent": "brand-board-figma-pull",
    })
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _detail(exc)
            if exc.code == 429 and attempt < attempts:
                # Honour Retry-After when Figma sends one, otherwise back off.
                try:
                    wait = int(exc.headers.get("Retry-After", ""))
                except (TypeError, ValueError):
                    wait = 5 * (2 ** (attempt - 1))
                print(f"  rate limited, waiting {wait}s "
                      f"(attempt {attempt} of {attempts})")
                time.sleep(wait)
                continue
            raise FigmaError(_explain(exc.code, detail, key)) from exc
        except urllib.error.URLError as exc:
            if attempt < attempts:
                time.sleep(2 * attempt)
                continue
            raise FigmaError(
                f"Could not reach api.figma.com ({exc.reason}). Check the network "
                f"and run again.") from exc
    raise FigmaError("Figma did not answer after several attempts.")


# --- tree ------------------------------------------------------------------

def walk(node: dict):
    """Every node, depth-first. Iterative, because Figma trees nest deeply."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.get("children") or []))


def pages_of(doc: dict) -> list[dict]:
    """The canvases of a whole file, or the single node when --node was used."""
    return list(doc.get("children") or []) if doc.get("type") == "DOCUMENT" else [doc]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "untitled"


def size_of(node: dict) -> tuple[float, float] | None:
    box = node.get("absoluteBoundingBox") or node.get("size")
    if not box:
        return None
    if "width" in box:
        return box["width"], box["height"]
    return box.get("x", 0), box.get("y", 0)  # `size` uses x/y for w/h


# --- colour and type -------------------------------------------------------

def hex_of(colour: dict, opacity: float | None = None) -> str:
    """#RRGGBB, or #RRGGBBAA when the paint is not fully opaque."""
    r, g, b = colour.get("r", 0), colour.get("g", 0), colour.get("b", 0)
    a = colour.get("a", 1)
    if opacity is not None:
        a *= opacity
    out = "#%02X%02X%02X" % tuple(round(c * 255) for c in (r, g, b))
    return out if a >= 0.999 else out + "%02X" % round(a * 255)


def solid_paints(paints) -> list[str]:
    if not isinstance(paints, list):
        return []
    return [hex_of(p.get("color", {}), p.get("opacity")) for p in paints
            if p.get("type") == "SOLID" and p.get("visible", True)]


def solid_fills(node: dict) -> list[str]:
    return solid_paints(node.get("fills"))


def _tidy(value):
    """Figma returns line heights like 134.39999999999998. Nobody needs that."""
    return round(value, 2) if isinstance(value, float) else value


def type_key(style: dict) -> tuple[str, float, int]:
    return (style.get("fontFamily", "?"),
            style.get("fontSize", 0),
            style.get("fontWeight", 0))


# --- outputs ---------------------------------------------------------------

def write_structure(out: Path, payload: dict) -> None:
    (out / "structure.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_inventory(out: Path, meta: dict, pages: list[dict]) -> None:
    """The 'what is actually in this file' artefact, grouped by page."""
    lines = [f"# {meta.get('name', 'Figma file')} — inventory", ""]
    if meta.get("node"):
        lines += [f"Scoped to node `{meta['node']}`, not the whole file.", ""]
    lines += [f"- File key: `{meta['key']}`",
              f"- Version: `{meta.get('version', 'unknown')}`",
              f"- Last modified in Figma: {meta.get('lastModified', 'unknown')}", ""]

    for page in pages:
        children = page.get("children") or []
        lines += [f"## {page.get('name', 'Untitled')}", "",
                  f"`{page.get('type')}` · {len(children)} top-level item(s)", ""]
        # A leaf node describes itself. An empty page has nothing to describe.
        rows = children or ([page] if page.get("type") != "CANVAS" else [])
        if not rows:
            lines += ["Nothing on this page.", ""]
            continue
        lines += ["| Name | Type | Size | Children | Node id |",
                  "|---|---|---|---|---|"]
        for child in rows:
            dims = size_of(child)
            size = f"{dims[0]:.0f}×{dims[1]:.0f}" if dims else "—"
            name = str(child.get("name", "")).replace("|", "\\|")
            lines.append(f"| {name} | {child.get('type')} | {size} | "
                         f"{len(child.get('children') or [])} | `{child.get('id')}` |")
        lines.append("")
    (out / "INVENTORY.md").write_text("\n".join(lines), encoding="utf-8")


def write_styles(out: Path, file_json: dict, nodes: list[dict]) -> dict:
    """Named styles, resolved to the values the nodes using them actually carry.

    The file response names a style and stops there — it never says what colour
    or size it is. The values only exist on the nodes that reference it, so each
    style is matched back to its first user and read off that.
    """
    # The slot matters, not just the id: one paint style can be a fill on one
    # node and a stroke on the next, and reading the wrong list would report a
    # colour the style does not have.
    usage: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for node in nodes:
        for slot, sid in (node.get("styles") or {}).items():
            usage[sid].append((slot, node))

    slot_for = {"TEXT": ("text",), "FILL": ("fill", "fills", "stroke", "strokes"),
                "EFFECT": ("effect", "effects"), "GRID": ("grid", "grids")}

    grouped: dict[str, list[dict]] = defaultdict(list)
    for sid, style in (file_json.get("styles") or {}).items():
        kind = style.get("styleType", "UNKNOWN")
        users = usage.get(sid, [])
        entry = {
            "id": sid,
            "key": style.get("key"),
            "name": style.get("name"),
            "description": style.get("description") or "",
            "usedByNodes": len(users),
        }
        wanted = slot_for.get(kind, ())
        sample = next(((s, n) for s, n in users if s in wanted), users[0] if users else None)
        if sample is not None:
            slot, node = sample
            if kind == "TEXT" and node.get("style"):
                s = node["style"]
                entry["text"] = {k: _tidy(s.get(k)) for k in (
                    "fontFamily", "fontPostScriptName", "fontWeight", "fontSize",
                    "lineHeightPx", "letterSpacing", "textCase", "textAlignHorizontal")
                    if s.get(k) is not None}
            elif kind == "FILL":
                stroke = slot.startswith("stroke")
                paints = node.get("strokes") if stroke else node.get("fills")
                entry["appliedAs"] = "stroke" if stroke else "fill"
                entry["colours"] = solid_paints(paints) or None
                if entry["colours"] is None:
                    # Gradients and images have no single hex; keep the raw paint.
                    entry["paints"] = paints
            elif kind == "EFFECT":
                entry["effects"] = node.get("effects")
            elif kind == "GRID":
                entry["layoutGrids"] = node.get("layoutGrids")
        grouped[kind].append(entry)

    for entries in grouped.values():
        entries.sort(key=lambda e: (e["name"] or "").lower())

    # Variables live behind a separate endpoint that is Enterprise-only, so they
    # are reported when the response happens to carry them and never invented.
    collections = file_json.get("variableCollections") or file_json.get("variables")
    payload = {
        "text": grouped.get("TEXT", []),
        "fill": grouped.get("FILL", []),
        "effect": grouped.get("EFFECT", []),
        "grid": grouped.get("GRID", []),
        "variableCollections": {
            "present": bool(collections),
            "data": collections or None,
            "note": ("This response carried no variables. Published variables come "
                     "from /v1/files/{key}/variables/local, which Figma restricts to "
                     "Enterprise plans."),
        },
    }
    (out / "styles.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def write_tokens_draft(out: Path, nodes: list[dict]) -> tuple[Counter, Counter]:
    """Observed values, counted. Not named, because naming is a human's call."""
    colours: Counter = Counter()
    types: Counter = Counter()
    line_heights: dict[tuple, Counter] = defaultdict(Counter)

    for node in nodes:
        # A node with the same hex twice is still one node using it.
        for hexv in set(solid_fills(node)):
            colours[hexv] += 1
        style = node.get("style")
        if node.get("type") == "TEXT" and style:
            key = type_key(style)
            types[key] += 1
            if style.get("lineHeightPx") is not None:
                line_heights[key][round(style["lineHeightPx"], 2)] += 1

    payload = {
        "_draft": (
            "DRAFT — measured, not designed. Every value below is something that "
            "exists in the Figma file, counted by how many nodes use it. Nothing "
            "here has been named or interpreted. A person decides which of these "
            "are the brand and which are one-off, then writes them into "
            "brands/<slug>/brand.json. Do not ship this file as a palette."),
        "palette": [{"hex": h, "nodes": c} for h, c in colours.most_common()],
        "type": [
            {"family": fam, "size": size, "weight": weight, "nodes": count,
             "lineHeightPx": [lh for lh, _ in line_heights[(fam, size, weight)].most_common(3)]}
            for (fam, size, weight), count in types.most_common()
        ],
        "_mapTo": {
            "note": "The palette keys brand.json expects. Fill each one by hand.",
            "palette": ["canvas", "surface", "ink", "inkMuted", "accent",
                        "accentPressed", "groundDark", "inkOnDark", "inkOnAccent"],
            "type": ["display.family", "display.weights", "body.family", "body.weights"],
        },
    }
    (out / "tokens.draft.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return colours, types


# --- images ----------------------------------------------------------------

def render_targets(pages: list[dict]) -> list[dict]:
    """Top-level frames per page. A section is a container, so descend through it."""
    targets = []
    for page in pages:
        children = page.get("children") or []
        if not children and page.get("type") in RENDERABLE:
            targets.append(page)
        for child in children:
            if child.get("type") == "SECTION":
                targets += [g for g in (child.get("children") or [])
                            if g.get("type") in RENDERABLE]
            elif child.get("type") in RENDERABLE:
                targets.append(child)
    return targets


def pull_images(out: Path, key: str, token: str, targets: list[dict],
                fmt: str, scale: float) -> tuple[int, list[str]]:
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    by_id = {t["id"]: t for t in targets}
    ids = list(by_id)
    urls: dict[str, str | None] = {}

    for i in range(0, len(ids), CHUNK):
        batch = ids[i:i + CHUNK]
        params = {"ids": ",".join(batch), "format": fmt}
        if fmt == "png":
            params["scale"] = scale  # scale applies to raster output only
        print(f"  rendering {i + 1}-{i + len(batch)} of {len(ids)}")
        resp = api_get(f"/v1/images/{key}", token, params, key=key)
        if resp.get("err"):
            raise FigmaError(f"Figma could not render this batch: {resp['err']}")
        urls.update(resp.get("images") or {})
        if i + CHUNK < len(ids):
            time.sleep(PAUSE)

    written, skipped = 0, []
    for nid in ids:
        url = urls.get(nid)
        name = by_id[nid].get("name", "")
        if not url:
            skipped.append(f"{name} ({nid})")
            continue
        # The node id keeps two frames called "Logo" from overwriting each other.
        path = assets / f"{slug(name)[:60]}--{nid.replace(':', '-')}.{fmt}"
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                path.write_bytes(resp.read())
            written += 1
        except Exception as exc:
            skipped.append(f"{name} ({nid}) — download failed: {exc}")
    return written, skipped


# --- main ------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="figma_pull.py",
        description="Read a Figma file and write out its structure, styles, "
                    "draft tokens and rendered assets. Read-only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Needs a Figma Personal Access Token stored in Keeper. Run without "
               "one to be told exactly how to create it.")
    ap.add_argument("target", help="Figma file key, or any Figma file URL")
    ap.add_argument("--node", help="restrict to one node, e.g. 7774:145 or 7774-145")
    ap.add_argument("--out", help="output folder (default figma/<file-name>)")
    ap.add_argument("--record", default="figma-token",
                    help="password-manager record holding the token")
    ap.add_argument("--images", action="store_true",
                    help="also render and download every top-level frame")
    ap.add_argument("--format", default="svg", choices=("svg", "png"),
                    help="render format for --images (default svg)")
    ap.add_argument("--scale", type=float, default=2,
                    help="render scale for png, 0.01 to 4 (default 2)")
    args = ap.parse_args(argv)

    key, url_node = parse_target(args.target)
    node = normalise_node_id(args.node) if args.node else url_node
    if args.format == "png" and not 0.01 <= args.scale <= 4:
        raise FigmaError(f"--scale {args.scale} is outside the 0.01 to 4 Figma allows.")

    token = read_token(args.record)

    print(f"Reading file {key}" + (f", node {node}" if node else ""))
    file_json = api_get(f"/v1/files/{key}", token, key=key)
    name = file_json.get("name", key)

    if node:
        nodes_json = api_get(f"/v1/files/{key}/nodes", token, {"ids": node}, key=key)
        found = (nodes_json.get("nodes") or {}).get(node)
        if not found or not found.get("document"):
            raise FigmaError(
                f"Node '{node}' is not in this file. Node ids come from the "
                f"'node-id' in a Figma URL — select the frame in Figma, copy its "
                f"link, and use the id from that. INVENTORY.md also lists every "
                f"top-level node id once you have run this without --node.")
        root_doc = found["document"]
        payload = nodes_json
    else:
        root_doc = file_json.get("document") or {}
        payload = file_json

    pages = pages_of(root_doc)
    nodes = [n for p in pages for n in walk(p)]

    out = Path(args.out) if args.out else ROOT / "figma" / slug(name)
    out.mkdir(parents=True, exist_ok=True)

    meta = {"key": key, "name": name, "node": node,
            "version": file_json.get("version"),
            "lastModified": file_json.get("lastModified")}
    write_structure(out, payload)
    write_inventory(out, meta, pages)
    write_styles(out, file_json, nodes)
    colours, types = write_tokens_draft(out, nodes)

    written, skipped = 0, []
    if args.images:
        targets = render_targets(pages)
        if not targets:
            print("  nothing renderable found, so no assets were requested")
        else:
            written, skipped = pull_images(out, key, token, targets,
                                           args.format, args.scale)

    sections = sum(1 for n in nodes if n.get("type") == "SECTION")
    top_level = sum(len(p.get("children") or []) for p in pages)
    print(f"\n{name}")
    print(f"  {len(pages)} page(s), {sections} section(s), {top_level} top-level "
          f"frame(s), {len(nodes)} nodes")
    print(f"  {len(colours)} distinct solid fill colours, "
          f"{len(types)} distinct type combinations")
    print(f"  {written} asset(s) written" if args.images else "  no assets (--images off)")
    if skipped:
        print(f"  {len(skipped)} not rendered:")
        for s in skipped:
            print(f"    - {s}")
    print(f"\nWritten to {out}")
    print("tokens.draft.json is a DRAFT. Read it before any of it becomes a brand.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FigmaError as exc:
        print(f"\n{exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
