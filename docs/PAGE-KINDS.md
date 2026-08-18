# Page kinds, every key the renderer reads

Derived from `engine/pages.py`, `engine/plan.py`, `engine/theme.py` and `engine/board.py`.
Nothing here is documented that the code does not read, and every key the code reads is here.

A page is an object inside a section's `pages` array. It always has `kind`. Anything not
listed under its kind is ignored, which is what makes `_comment` keys safe.

Paths are relative to the brand folder, the one holding `brand.json`. Missing files raise
rather than rendering a blank space, so `python3 -m engine.verify brands/<slug>` is the
cheapest way to find them.

---

## The file above the pages

### `meta`

| Key | Required | Notes |
|---|---|---|
| `slug` | yes in practice | Names every output file. **Must equal the brand folder name**, because `verify` looks for `out/<folder>/<slug>-brand-presentation.pdf`. A mismatch reports a missing PDF that is sitting right there. Falls back to the folder name if absent |
| `name` | yes | Cover headline and document title. `verify` fails without it |
| `wordmark` | yes | Footer, left side. `verify` fails without it |
| `year` | yes | Footer copyright. `verify` fails without it |
| `document` | no | Cover subtitle, default `Brand Guideline` |
| `legal` | no | Footer, default `All rights reserved` |
| `closing` | no | The last page's word, default `Thank you` |
| `coverMark` | no | Image path, sits bottom right on the cover |
| `boardMark` | no | Image path for the board header, falls back to `coverMark` |
| `boardTitle` | no | Board header line 2, default `Brand Board` |
| `line` | no for render | One sentence across the board header. **Required by `scripts/build_site.py`**, which crashes without it |
| `order` | no | Sort position on the showcase site only, default 100 |

### `palette`

Every key optional, each falling back to a default in `engine/theme.py`. Recognised keys:
`canvas`, `surface`, `ink`, `inkMuted`, `accent`, `accentPressed`, `groundDark`,
`inkOnDark`, `inkOnDarkMuted`, `inkOnAccent`.

`verify` reads **every value in this object** and requires a `#rgb` or `#rrggbb` hex.
That is the one place a `_comment` key breaks the build. Put comments outside `palette`.

`inkOnDarkMuted` accepts an `rgba()` string in the default, but a value you supply is hex
checked, so keep yours hex.

### `type`

Two optional faces, `display` and `body`. Each takes:

| Key | Required | Notes |
|---|---|---|
| `family` | yes | Any Google Fonts family name. Fetched on first build and cached into `assets/fonts/` at the skill root |
| `variable` | no | `true` only for a face that ships a weight axis. Drives the ramp on a `typeface` page |
| `weight` | no | The shipping weight, default 600 display / 400 body |
| `weightXL` | no | Display only. The weight the giant one-word display drops to, default `weight` |
| `weights` | no | Array of ints, used to request the right static weights and to set the embedded font-face weight range |
| `file` | no | Path to a local `.woff2`, `.woff`, `.ttf` or `.otf`. Skips the download entirely |

### `shape`

All ten members are optional. Six of them are one interlocking grid.

| Key | Default | Safe to change |
|---|---|---|
| `radiusField` | 20 | **Yes** |
| `radiusCard` | 30 | **Yes** |
| `radiusPill` | 40 | **Yes** |
| `gap` | 20 | Yes, it only sets grid gaps |
| `margin` | 88 | No |
| `safeTop` | 80 | No |
| `captionWidth` | 360 | No |
| `panelX` | 536 | No |
| `panelWidth` | 1296 | No |
| `panelHeight` | 824 | No |

The coupling, on a fixed 1920 x 1080 page:

```
panelX + panelWidth  = 536 + 1296 = 1832 = 1920 - margin
   the panel's right edge is the footer's right edge. Change margin alone and
   the panel stops lining up with the footer above it.

margin + captionWidth = 88 + 360 = 448, and the panel starts at 536
   the 88px gutter between the caption column and the panel is what is left over.
   Widen captionWidth past 448 and the caption runs under the panel.

safeTop + panelHeight = 80 + 824 = 904, and 1080 - 904 = 176
   deck.css bottom-anchors the caption block at a hard-coded 176px. That number
   is not read from shape, so moving safeTop or panelHeight unpicks the one
   detail the layout is built on: the caption baseline sitting on the panel foot.
```

Change any of the six and you have to recompute all six. The three radii are the block's
only free values, and `verify` checks that a `radii` component page only shows numbers on
that scale.

Omitting `shape` entirely is a real option. The documents then use their own defaults and
the emitted skill says a radius system is not recorded, instead of asserting one.

### `sections`

| Key | Required | Notes |
|---|---|---|
| `title` | yes | Divider word, contents row, and the default `section` on every page inside |
| `id` | no, but see below | Selects the board card |
| `summary` | no | The contents page description, two lines |
| `pages` | no | The page array. An empty section still gets a divider |

`id` is not decoration. The brand board builds one card per section and looks the id up in
a fixed table: `overview`, `logo`, `colour`, `color`, `typography`, `imagery`, `motion`,
`components`, `applications`. Any other id renders normally in the PDF and is **silently
absent from the board**. Falls back to the lowercased `title` when `id` is missing.

---

## Keys every content page shares

| Key | Required | Notes |
|---|---|---|
| `kind` | yes | One of the kinds below. An unknown kind raises and names the known set |
| `section` | no | The title printed top left. Filled in from the parent section automatically |
| `captionTitle` | no | Bottom left, 20px |
| `caption` | no | Bottom left under the title, 17px muted, wrapping inside 360px |

`cover`, `toc`, `divider` and `closing` are generated by `engine/plan.py`. Never write them
into a `pages` array.

---

## overview

Two text columns across the sheet, no card. Story blocks: vision, voice, positioning.

| Key | Required | Notes |
|---|---|---|
| `blocks` | yes | Array |
| `blocks[].title` | yes | Card-size heading |
| `blocks[].body` | yes | Body copy, measure capped at 34em |

The board's Overview card and the emitted skill's "What it is" section both read these
blocks, so this is the page that teaches a future model what the business is.

```json
{
  "kind": "overview",
  "captionTitle": "Overview",
  "caption": "Where nothing has been decided, the block says so.",
  "blocks": [
    { "title": "What it is", "body": "One plain sentence naming the product and its buyer." },
    { "title": "Voice", "body": "Not written yet. Nothing has been approved." }
  ]
}
```

## prose

A list of stated rules, one per row, each on a hairline. The emitted Claude skill lifts
every item verbatim into "The brand's own hard rules", so write them as instructions.

| Key | Required | Notes |
|---|---|---|
| `items` | yes | Array of plain strings. No objects |

```json
{
  "kind": "prose",
  "captionTitle": "Hard rules",
  "items": [
    "Never recolour the logo. Pick the variant that suits the ground.",
    "One accent colour. Variety comes from photography."
  ]
}
```

## lockup

One logo variant, centred on a panel.

| Key | Required | Notes |
|---|---|---|
| `src` | yes | Image path |
| `ground` | no | `dark` or `accent`. Anything else, or absent, gives the light card |
| `variant` | no | Image alt text, and the tile caption on the board. Default `logo` |

```json
{
  "kind": "lockup",
  "variant": "Reversed",
  "src": "assets/logo/lockup-reversed.svg",
  "ground": "dark",
  "captionTitle": "Reversed",
  "caption": "For dark grounds. The mark never changes colour."
}
```

## marks

The symbol alone, in each variation, each on the ground it is meant to be seen on.

| Key | Required | Notes |
|---|---|---|
| `marks` | yes | Array |
| `marks[].src` | yes | Image path |
| `marks[].label` | yes | Printed under the mark |
| `marks[].ground` | no | `dark` or `accent`, per mark. A pale mark on a pale tile is invisible and correct |

```json
{
  "kind": "marks",
  "captionTitle": "The mark",
  "marks": [
    { "label": "Primary", "src": "assets/logo/mark-primary.svg" },
    { "label": "Reversed", "src": "assets/logo/mark-light.svg", "ground": "dark" }
  ]
}
```

## clearspace

The measure drawn to scale on two edges, not described in prose.

| Key | Required | Notes |
|---|---|---|
| `src` | yes | Image path |
| `markHeight` | no | Pixels the artwork is drawn at, default 200 |
| `ratioValue` | no | Padding as a fraction of `markHeight`, default 0.25. This is what is drawn |
| `ratio` | no | The label printed beside the measure, default `1/4`. This is only text |

`ratio` and `ratioValue` are independent. Keep them in agreement or the page states one
number and draws another.

```json
{
  "kind": "clearspace",
  "src": "assets/logo/lockup-primary.svg",
  "markHeight": 150,
  "ratio": "1/4",
  "ratioValue": 0.25,
  "captionTitle": "Clear space"
}
```

## misuse

A grid of real violations, each struck through and captioned with its rule. The panel is
three columns wide, so six cells give the 3x2 that reads best.

| Key | Required | Notes |
|---|---|---|
| `cells` | yes | Array |
| `cells[].rule` | yes | The caption under the cell |
| `cells[].src` | no | Image path. Without it the cell falls back to `glyph` |
| `cells[].glyph` | no | Text shown when there is no `src`, default empty |
| `cells[].style` | no | Inline CSS on the image. This is how the violation is staged |
| `cells[].bg` | no | Image path used as the cell background, for the "on a busy photo" case |

`style` is the working part. Distort the real logo rather than shipping a second file:

```json
{
  "kind": "misuse",
  "captionTitle": "Misuse",
  "cells": [
    { "rule": "Never stretch it", "src": "assets/logo/lockup-primary.svg",
      "style": "transform:scaleX(1.45);max-height:52px" },
    { "rule": "Never add a shadow", "src": "assets/logo/lockup-primary.svg",
      "style": "filter:drop-shadow(0 8px 10px rgba(0,0,0,.45));max-height:56px" },
    { "rule": "Never place it on a photo", "src": "assets/logo/lockup-primary.svg",
      "style": "max-height:44px", "bg": "assets/imagery/texture.jpg" }
  ]
}
```

## colourStack

Full-width bars for the core palette, the value knocked into the bar. The label colour is
chosen automatically from the bar's luminance, and pale bars get a hairline so they do not
dissolve into the panel.

| Key | Required | Notes |
|---|---|---|
| `colours` | yes | Array |
| `colours[].hex` | yes | `#rgb` or `#rrggbb`. `verify` rejects anything else |
| `colours[].name` | no | Default `HEX` |

```json
{
  "kind": "colourStack",
  "captionTitle": "Core",
  "colours": [
    { "name": "Canvas", "hex": "#F4F3F1" },
    { "name": "Ink", "hex": "#1F1F1F" },
    { "name": "Accent", "hex": "#2455E8" }
  ]
}
```

## colourRamp

A chip grid for the extended palette. Name above, hex below.

| Key | Required | Notes |
|---|---|---|
| `colours` | yes | Same shape as `colourStack` |
| `colours[].hex` | yes | Hex checked by `verify` |
| `colours[].name` | no | Default empty |

Both colour kinds are read by the board's Colour card and by the emitted skill's colour
table. They are separate from the `palette` block, which colours the document itself, and
nothing keeps the two in step for you.

## typeface

Weight specimens, plus the variable axis ramp when there is one. One page per family.

| Key | Required | Notes |
|---|---|---|
| `family` | yes | Must match a family declared in `type`, or the specimen falls back to system |
| `weights` | yes | Array |
| `weights[].name` | yes | Row label |
| `weights[].value` | yes | Integer, drives both `font-weight` and `wght` |
| `showName` | no | Prints the family name above the specimens, default `true` |
| `axis` | no | Object. Only for a variable face |
| `axis.min` | no | Default 200 |
| `axis.max` | no | Default 800 |
| `axis.steps` | no | Default 7 |
| `axis.word` | no | The word climbing the ramp, default the family name |

Shipping weights are forced into the ramp even when they sit off an even hundred, so a 585
appears on the page that exists to prove it. With `axis` present the alphabet rows go to a
single compact line.

```json
{
  "kind": "typeface",
  "family": "Manrope",
  "captionTitle": "The typeface",
  "weights": [
    { "name": "Display 585", "value": 585 },
    { "name": "Body 600", "value": 600 }
  ],
  "axis": { "min": 200, "max": 800, "steps": 7, "word": "Capability" }
}
```

## typescale

Every step set at its true size. The page is the proof, so a wrong number is visible.

| Key | Required | Notes |
|---|---|---|
| `scale` | yes | Array |
| `scale[].px` | yes | Integer, set literally as `font-size` |
| `scale[].role` | yes | Doubles as the specimen text |
| `scale[].tracking` | no | Default `-0.04em` |

The emitted skill derives its tracking law from these values, so a scale with tracking left
off produces a document that claims `-0.04em` at 13px.

```json
{
  "kind": "typescale",
  "captionTitle": "The scale",
  "scale": [
    { "role": "Display", "px": 80, "tracking": "-0.04em" },
    { "role": "Body", "px": 17, "tracking": "-0.03em" },
    { "role": "Meta", "px": 13, "tracking": "-0.025em" }
  ]
}
```

## imagery

Photographic registers, each with its direction line.

| Key | Required | Notes |
|---|---|---|
| `registers` | yes | Array |
| `registers[].src` | yes | Image path, drawn as a cover-fill background |
| `registers[].name` | yes | Bold label |
| `registers[].direction` | yes | One line saying when to use this register |

Columns are automatic: 2 for four registers or fewer, 3 above that. There is no column key
on this kind.

```json
{
  "kind": "imagery",
  "captionTitle": "Registers",
  "registers": [
    { "name": "A. Warm room", "src": "assets/imagery/a-room.jpg",
      "direction": "Trust and presence. Real people, straight photography." }
  ]
}
```

## motion

Easing curves drawn from their control points, plus a duration table.

| Key | Required | Notes |
|---|---|---|
| `curves` | yes | Array |
| `curves[].name` | yes | Curve label |
| `curves[].points` | yes | Exactly four comma separated numbers, `x1,y1,x2,y2`. Parsed as floats, so anything else raises |
| `durations` | no | Array, omitted entirely if absent |
| `durations[].ms` | yes if `durations` | Printed with `ms` appended |
| `durations[].use` | yes if `durations` | What that duration is for |

The panel lays curves out in three columns.

```json
{
  "kind": "motion",
  "captionTitle": "Curves and timing",
  "curves": [
    { "name": "Standard", "points": ".4,0,.2,1" },
    { "name": "Overshoot", "points": ".22,1,.36,1" }
  ],
  "durations": [
    { "ms": 200, "use": "Micro" },
    { "ms": 400, "use": "Structural" }
  ]
}
```

## components

Live buttons, fields and radii rendered at true size on the panel.

| Key | Required | Notes |
|---|---|---|
| `items` | yes | Array. Each item has its own `kind` |

Four item kinds are implemented. An item with any other `kind` is **skipped in silence**,
so a typo here costs you a specimen with no error.

| Item `kind` | Keys | Notes |
|---|---|---|
| `button` | `label` required, `variant` optional, `dot` optional | `variant` is `primary`, `secondary` or `dark`, default `primary`. `dot` defaults `true` |
| `field` | `label` required | Renders as an input at the field radius |
| `radii` | `values` required | Array of `[px, label]` pairs. `verify` fails any px not equal to `radiusField`, `radiusCard` or `radiusPill` |
| `swatchRow` | `colours` required | Array of hex strings, drawn as circles. Note these are **not** hex checked by `verify`, and the board card ignores this item kind |

```json
{
  "kind": "components",
  "captionTitle": "The pieces",
  "items": [
    { "kind": "button", "variant": "primary", "label": "Book a call" },
    { "kind": "button", "variant": "secondary", "label": "See the work" },
    { "kind": "field", "label": "Your email" },
    { "kind": "radii", "values": [[20, "field"], [30, "card"], [40, "pill"]] }
  ]
}
```

## applications

A contact sheet of real touchpoints. Each image is letterboxed onto a tinted ground rather
than cropped, so any aspect ratio is safe. Matching them still looks tidier, but a mixed
set will not be cut. The old advice to crop to a similar
aspect before dropping them in.

| Key | Required | Notes |
|---|---|---|
| `items` | yes | Array |
| `items[].src` | yes | Image path |
| `columns` | no | Integer. Default 2 for four items or fewer, 3 above that |

Rows are computed from the item count, so the grid always fills the panel.

```json
{
  "kind": "applications",
  "captionTitle": "Touchpoints",
  "columns": 3,
  "items": [
    { "src": "assets/applications/website.png" },
    { "src": "assets/applications/social.png" },
    { "src": "assets/applications/card.png" }
  ]
}
```

---

## What each kind gives the other two outputs

The deck renders every kind. The board and the emitted skill read a subset.

| Kind | On the board | In the emitted skill |
|---|---|---|
| `overview` | Full-width story card | The "What it is" section |
| `prose` | Nothing | "The brand's own hard rules", verbatim |
| `lockup` | Tile in the Logo card | Artwork copied to `assets/logo/` |
| `marks` | Chips in the Logo card | Artwork copied to `assets/logo/` |
| `clearspace` | Nothing | Nothing |
| `misuse` | Nothing | Nothing |
| `colourStack` | Chip group in the Colour card | Colour table |
| `colourRamp` | Chip group in the Colour card | Colour table |
| `typeface` | Specimen in the Typography card | Face list |
| `typescale` | Size rows in the Typography card | Size table, and the tracking law |
| `imagery` | Imagery card | Nothing |
| `motion` | Motion card | Nothing |
| `components` | Components card, minus `swatchRow` | Nothing |
| `applications` | Full-width Applications card | Nothing |

A brand with no `prose` page emits a skill with no hard rules in it. That is the single
highest-value page for the machine output.


## `dosdonts`

A do column and a don't column, side by side. The short document uses it to settle
arguments without a paragraph of prose.

```jsonc
{
  "kind": "dosdonts",
  "section": "Logo",
  "captionTitle": "In practice",
  "caption": "The two lists people actually need.",
  "doLabel": "Do",                    // optional, defaults to "Do"
  "dontLabel": "Don't",               // optional, defaults to "Don't"
  "do":   ["Use the reversed lockup on any dark ground.",
           "Keep the clearspace, even in a tight header."],
  "dont": ["Recolour the mark to match a campaign.",
           "Place the logo on a busy photograph."]
}
```

Both arrays are required. Keep each line one sentence: this page is read standing up.

## `files`

A plain list of what is in the kit, so the person receiving it knows what they have.

```jsonc
{
  "kind": "files",
  "section": "Files",
  "captionTitle": "What you have",
  "caption": "Everything in the folder, and when to reach for it.",
  "items": [
    { "name": "lockup-primary.svg",  "what": "The default. Dark artwork, light grounds." },
    { "name": "lockup-reversed.svg", "what": "Light artwork, for dark grounds only." },
    { "name": "tokens.css",          "what": "Drop into a site to inherit the palette." }
  ]
}
```

`items[].name` and `items[].what` are both required.

Made by Selr AI.
