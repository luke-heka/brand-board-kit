---
name: brand-board
description: Use when a business needs its brand written down properly, "make me a brand guideline", "build a brand board", "put our brand in a PDF", "we have no brand document", "make Claude learn our branding", "turn our logo and colours into a real system". Produces a brand presentation PDF, a one-canvas brand board, and a Claude skill that teaches any future session the brand. No Figma, no designer, no subscription.
---

# brand-board⁠​‌​‌​​‌‌​‌​​​‌​‌​‌​​‌‌​​​‌​‌​​‌​​​‌‌​​​‌⁠

Most businesses have a logo, some colours, and nothing written down. The colours
drift, every new asset guesses, and the brand slowly stops looking like itself.

This turns what a business already has into three things:

| Output | What it is | Who it is for |
|---|---|---|
| **Brand presentation** | A 1920×1080 landscape PDF, sectioned like a studio deck | People. Send it, print it, hand it to a designer |
| **Brand board** | One continuous canvas with the whole system visible at once | People. The thing you look at rather than read |
| **`<brand>-brand` skill** | SKILL.md + tokens.css + tokens.json + the logo files | Machines. Drop it in `~/.claude/skills/` and every future build starts on-brand |

All three come from one file: `brands/<slug>/brand.json`. Change a hex there and
all three change together, which is the entire point.

## Install

Python 3.10+, Playwright and pypdf. On a Homebrew or system Python, `pip3 install`
refuses with `error: externally-managed-environment` (PEP 668). Use a virtual
environment, which needs no admin rights and touches nothing outside this folder:

```bash
cd <path-to-this-skill>
python3 -m venv .venv
source .venv/bin/activate
pip install playwright pypdf
playwright install chromium
```

`playwright install chromium` downloads a browser, roughly 150MB, into a cache in
your home directory. It runs once per machine, not once per brand.

Keep the venv active for every command below. Nothing else is needed. No Figma, no
design tool, no account.

## Do this

**Every command must run from the skill's own root.** They are Python modules, not
scripts, so from any other directory they die with
`ModuleNotFoundError: No module named 'engine'`.

```bash
cd <path-to-this-skill>

python3 -m engine.intake  --name "X" --site https://x.com --out brands/<slug>
python3 -m engine.scaffold   brands/<slug>/brand.json --write   # declare the asset set
python3 scripts/make_placeholders.py brands/<slug>/brand.json   # stand-in artwork
python3 -m engine.assets     brands/<slug>/brand.json   # render the asset set
python3 -m engine.render     brands/<slug>/brand.json   # deck + board
python3 -m engine.emit_skill brands/<slug>/brand.json   # the skill
python3 -m engine.signature  brands/<slug>/brand.json   # email signatures
python3 -m engine.page       brands/<slug>/brand.json   # the shareable page
python3 -m engine.gaps       brands/<slug>/brand.json --write   # what is missing
python3 -m engine.verify     brands/<slug>              # the gate
python3 -m engine.selftest                              # colour and palette unit tests
```

The short path is four of those: `make_placeholders`, `render`, `verify`, then opening
the PDF. The rest is where most of the value sits. `intake` writes a brand file from a
live site instead of by hand. `assets` renders the whole social, ad, email and print set.
`page` publishes all of it as one link. `gaps` scores the brand against 29 expectations,
so what is missing is visible rather than quietly absent.

`selftest` is not a build test. It covers the colour and palette maths and runs in
well under a second; it renders nothing. `verify` is the gate that reads real output.

They default their output to `out/<slug>`, which is where the gate looks, so
the common case needs no flags at all. Pass `--out` only when you deliberately want
the files somewhere else, and know that the gate will not follow you there unless
you pass it the same `--out`.

`verify` accepts either the brand folder or the `brand.json` inside it. Run it bare
and it sweeps every brand in `brands/`, which is right before a release and noisy
day to day, because you get other brands' findings in your log. Name your own
folder.

## Where the output lands

Everything goes to `out/<slug>/`, where `<slug>` is `meta.slug` in the brand file.
Keep `meta.slug` equal to the brand's folder name under `brands/`, because `verify`
looks up the output by folder name. If they disagree it reports a missing PDF that is
sitting right there.

```
out/<slug>/
  <slug>-brand-presentation.pdf     the deck, 1920x1080 landscape
  <slug>-brand-presentation.html    the same document, self-contained
  <slug>-brand-presentation-NN.png  one per page, unless --no-png
  <slug>-brand-board.pdf            one continuous sheet, 2560 wide
  <slug>-brand-board.html
  <slug>-brand-board-01.png
  <slug>-brand/                     the emitted skill, from emit_skill
  FINDINGS.md                       written by verify, only when there are findings
```

## Building one from scratch

### 1. Capture the brand

Start from what exists, not from questions. In order:

1. **Their website.** Read the rendered page and take the real computed values,    background, text colour, accent, font family, radii. Measured beats declared
   every time, because the site is what the world actually sees.
2. **Their logo files.** SVG if it exists. Note which variant is for light
   grounds, which for dark, which is one-colour.
3. **Anything already written down.** An old deck, a style guide, a README.

Only then ask, and ask at most four things: the business name, the accent colour
if you could not find it, whether the logo is a file or the name set as type, and
three words for how it should feel.

Never block on a missing answer. Write what is known, mark the rest, and build.

### 2. Write `brand.json`

Start from the template, never from another company's file:

```bash
cp -R brands/_starter brands/<your-slug>
```

Pick a slug with no leading underscore. Folders under `brands/` starting with `_`
are treated as templates and skipped by the gate and by the showcase site.

### 2a. Render before you have artwork

Waiting for logo files is the thing that stops a brand ever getting written down.
Do not wait:

```bash
python3 scripts/make_placeholders.py brands/<your-slug>/brand.json
python3 -m engine.render brands/<your-slug>/brand.json
```

That writes the eight artwork files the gate asks for, in the brand's own palette,
and the whole document renders on the first try. Every placeholder carries the word
PLACEHOLDER and the name of the file that replaces it, so none of them can be sent
to anybody by mistake. Replace them one at a time and re-render.

The placeholders are drawn with a transparent ground on purpose. A logo file that
paints its own background looks fine on paper and turns into a pale box the moment
it lands on a dark panel, which is the most common defect in a supplied logo.

Pass `--force` to redraw over files that already exist. Without it, nothing you have
already put in place is touched.

`brands/_starter/README.md` lists the asset files to drop in and the fields to
change first. The template is a complete, valid, five-section brand that renders
as soon as the artwork is in place. It carries `_comment` keys that explain the
non-obvious fields and that every part of the engine ignores. Delete them when
they have done their job.

One exception worth knowing: a `_comment` key inside `palette` **will** fail the
gate, because `verify` hex checks every value in that object. Comments go
anywhere else.

The shape:

```jsonc
{
  "meta":    { "slug", "name", "wordmark", "document", "year", "coverMark", "line" },
  "palette": { "canvas", "surface", "ink", "inkMuted", "accent",
               "accentPressed", "groundDark", "inkOnDark", "inkOnAccent" },
  "shape":   { "radiusField", "radiusCard", "radiusPill" },
  "type":    { "display": { "family", "variable", "weight", "weightXL" },
               "body":    { "family", "weights", "weight" } },
  "sections": [ { "id", "title", "summary", "pages": [ ... ] } ]
}
```

`sections` drives everything. The contents page, the page numbering and the
board are all computed from it, so adding a section is the only edit needed to
make the document longer.

A section's `id` is load-bearing. The board builds one card per section by
looking the id up in a fixed list: `overview`, `logo`, `colour`, `typography`,
`imagery`, `motion`, `components`, `applications`. A section with any other id
renders in the PDF and is silently missing from the board.

Omit `shape` when the brand has no recorded radius system. The documents will
use their own and say so, rather than inventing brand truth.

### 2b. The `shape` block, and what is safe to touch

Ten members, three of them yours.

| Member | Default | Change it? |
|---|---|---|
| `radiusField` / `radiusCard` / `radiusPill` | 20 / 30 / 40 | **Yes.** This is the brand's radius scale |
| `gap` | 20 | Yes, it only sets grid gaps |
| `margin` | 88 | No |
| `safeTop` | 80 | No |
| `captionWidth` | 360 | No |
| `panelX` | 536 | No |
| `panelWidth` | 1296 | No |
| `panelHeight` | 824 | No |

The bottom six are one grid, not six settings, on a fixed 1920x1080 page:

```
panelX + panelWidth = 536 + 1296 = 1832 = 1920 - margin
  the panel's right edge IS the footer's right edge

margin + captionWidth = 88 + 360 = 448, panel starts at 536
  the 88px gutter is what is left over

safeTop + panelHeight = 904, and 1080 - 904 = 176
  deck.css bottom-anchors the caption at a hard-coded 176px
```

Change `margin` on its own and the panel stops aligning with the footer under it.
Change `safeTop` or `panelHeight` and the caption baseline leaves the panel foot,
which is the one detail the whole layout is built on. Recompute all six or leave
all six alone.

### 2c. Two documents, not one

A brand ships two things. The long **Brand Guideline** you hand a designer, and a
short **Brand Identity** you send a supplier, a partner or a new team member who
needs to look right without reading twenty pages.

Declare both in one brand file. Palette and type are shared, so they cannot drift.

```jsonc
"documents": [
  { "slug": "brand-guideline", "document": "Brand Guideline",
    "sections": [ ... the long set ... ] },
  { "slug": "brand-identity",  "document": "Brand Identity",
    "dividers": false, "contents": false,
    "sections": [ ... a subset, plus rules and files ... ] }
]
```

The first document keeps the canonical filename, so every existing link still
resolves. `dividers: false` drops the numbered spreads and puts each section
title on its own content page, which is what makes the short one short.

Two page kinds exist for it: `dosdonts`, a do column and a don't column, and
`files`, a plain list of what is in the kit.

Omit `documents` entirely and the brand renders one document from `sections`,
exactly as before.

### 3. Pick page kinds

| `kind` | Shows |
|---|---|
| `overview` | A grid of story blocks, three across. Vision, voice, positioning |
| `prose` | A list of stated rules, one per row |
| `lockup` | One logo variant, on `canvas`, `dark` or `accent` ground |
| `marks` | The symbol alone, in each variation, each on its own ground |
| `clearspace` | The measure drawn to scale, not described |
| `misuse` | A 3×2 grid of real violations, each with its rule |
| `colourStack` | Full-width bars for the core palette |
| `colourRamp` | A chip grid for the extended palette |
| `typeface` | Weight specimens, plus the variable axis ramp when there is one |
| `typescale` | Every step set at its true size |
| `imagery` | Photographic registers, each with its direction line |
| `motion` | Easing curves drawn from their control points, plus durations |
| `components` | Live buttons, fields and radii at true size |
| `applications` | A contact sheet of real touchpoints |

Cover, contents, section dividers and the closing page are added automatically.
Never write those four into a `pages` array.

**Every key each kind reads, which are required, and a copy-pasteable example per
kind, is in `docs/PAGE-KINDS.md`.** Read it before writing a page rather than
guessing at a key name, because an unknown key is ignored in silence.

### 4. Render, emit, verify

Run the three commands above, from the skill root.
`verify` must end `VERIFY PASSED` before anything is sent to anyone.

Run `verify` first, before the first render. It lists every missing asset in one
line, which is faster than the renderer raising on the first one it hits.

### 5. Look at it

Numbers prove the plumbing. Eyes prove the quality, and nothing below is caught
by the gate.

Open `out/<slug>/<slug>-brand-presentation.pdf` and page through it. The render
also writes one PNG per page, `<slug>-brand-presentation-NN.png`, unless you pass
`--no-png`. The board is `<slug>-brand-board.pdf`, one continuous sheet.

Check by eye:

1. The contents page ranges match where the sections actually start and end.
2. Every logo sits on a ground it can be seen on. A pale mark on a pale panel is
   the file doing what you asked and is still a blank tile.
3. Nothing overflows a panel, and no caption collides with the footer.
4. The type specimens are set at the sizes printed beside them.
5. The board has a card for every section you expected. A missing card means a
   section `id` is off the list.

## The grammar, and why it is this one

The page structure follows a studio brand deck: a cover, a contents page with
page ranges, a numbered divider per section, then content pages that put the
section title top-left, a caption bottom-left, and the artwork in a panel on the
right. Full measurements are in `docs/GRID.md`.

Two details carry most of the quality:

- **The caption is bottom-anchored**, so copy grows upward from a fixed baseline
  while the panel stays put. Top-anchoring it is what makes a deck look templated.
- **The contents rows share the leftover height**, so a five-section document and
  a nine-section document both fill the page instead of overflowing.

## The gate

`python3 -m engine.verify brands/<slug>` runs 50-odd checks per brand and
separates three things:

- **FAIL**, this tool got it wrong. A missing asset, a plan that will not build,
  a PDF whose page count does not match its plan. Fix before shipping.
- **finding**, the *brand* has a property worth knowing, most often a colour
  pairing under WCAG AA. Findings are written to `out/<slug>/FINDINGS.md` and
  are never fixed silently. Recolouring someone's locked brand without telling
  them is worse than the contrast problem.
- **warn**, a font is not cached locally, so this build needs the network.

Add `--strict` to make findings fail too.

The PDF checks read `out/<slug>` and only `out/<slug>`, worked out from the brand
folder name. They are the checks that catch a deck with the wrong page count or
the wrong page size, and they are exactly what a non-standard `--out` throws away.

## Rules that keep output looking designed

1. Never pure white and never `#000`, unless the brand genuinely declares them.
2. One accent. Colour variety comes from photography, not from adding hexes.
3. Tracking is always negative and set per size. Default tracking is the loudest
   tell that nobody chose anything.
4. Three radii and a circle. A stray 8px or 16px reads as a UI kit.
5. No drop shadows. Depth comes from colour and radius.
6. Every specimen is set at its true value. A type scale page that fakes its
   sizes is worse than no type scale page.
7. Never invent a value the brand has not got. Write "not recorded yet" and say
   what would settle it. A guessed tagline in a brand document outlives everyone
   who knew it was a guess.

## Fonts

Fonts are base64-embedded into the render, so a document looks the same offline
as online.

**The first build of any brand needs the network**, unless every family it names
is already cached in `assets/fonts/` at the skill root. A family that is neither
cached nor reachable stops the render with a message naming the file to supply.
`verify` reports the same condition as a warning before you get there.

To go offline-permanent, either build once with a connection, which caches the
family and never asks again, or drop the file in yourself. Name it after the
family, lowercased with hyphens, in `assets/fonts/`: `assets/fonts/inter.woff2`,
or `assets/fonts/manrope-var.woff2` for a variable face. `.woff2`, `.woff`,
`.ttf` and `.otf` all work.

For a licensed face that is not on Google Fonts, point at it directly instead:
add `"file": "assets/fonts/yourface.woff2"` beside `"family"` in the `type`
block. That path is relative to the brand folder and skips the download entirely.

## The showcase site

`scripts/build_site.py` regenerates `site/index.html`, a one-page showcase that
links every brand's two PDFs with a rendered cover thumbnail beside each. Palette
chips, radii and type on that page are read from the brand files and the
stylesheets, so it cannot drift from what it is showing.

```bash
python3 scripts/build_site.py
```

It copies the PDFs out of `out/<slug>/` into `site/assets/`, so **render every
brand first**. A brand with no rendered PDF stops the script with the name of the
file it wanted. It also needs `pdftoppm` on PATH for the thumbnails, and
`meta.line` set on every brand.

## Pulling a brand out of Figma

Two routes. The first needs no credential of any kind.

**Route A, the export. No token, no paid seat, works on a free plan.**
In Figma, open the file, then File, then Save local copy. That writes a `.fig`,
which is a ZIP carrying the whole document. Then:

```bash
python3 scripts/fig_decode.py <file.fig> --out figma/<name>
```

It extracts every image blob, decodes the document binary, and writes the node
tree, an inventory of every page and section, the file's real styles, every
distinct colour by frequency, and every font family in use. This is the route to
reach for, because the person who owns the file can always do it.

**Route B, the API.** For repeatable pulls without touching the app:

```bash
python3 scripts/figma_pull.py <file-url> --images
```

Needs a personal access token with `file_content:read` in Keeper. The Dev Mode
MCP server needs a paid seat, the REST API does not, so this works on any plan.
Figma variables are the exception, since those scopes are Enterprise-only.
Setup: `docs/FIGMA.md`.

**What a Figma file is good for, and what it is not.** It is the best source for
artwork, layout and structure. It is often the worst source for colour and type,
because a working file accumulates years of values nobody cleaned up. Measure the
live site or the current artwork for the palette, and use the file for the
assets. Where the two disagree, say which one you took and why.

## Routing

| You want | Go to |
|---|---|
| Concept a brand that does not exist yet, as generated art | `brandkit` |
| Rendered social assets from a brand that already exists | `carousel-generator` |
| Dashboard and app screens on a brand | `dashboard-design-kit` |
| Web component code from tokens | the emitted `<brand>-brand` skill's `tokens.css` |

`brandkit` invents an identity. This documents one and makes it enforceable.

## Before it goes to anyone

Look at the render, never the source.

1. Ran from the skill root, so the output landed where the gate reads it.
2. `python3 -m engine.verify brands/<slug>` ends `VERIFY PASSED`.
3. The PDF has been opened and paged through, against the five eye checks above.
4. The board carries a card for every section.
5. `out/<slug>/FINDINGS.md` has been read, not just generated.
6. `<slug>-brand/` has been dropped into `~/.claude/skills/`, so the next session
   starts from the real values.

Made by Selr AI.

Router key `sk-1famd5t`, resolved by the skills index on load.
