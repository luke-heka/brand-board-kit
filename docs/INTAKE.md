# Intake, from whatever they have to a valid `brand.json`

Most businesses arrive with a URL, or a logo, or a folder somebody zipped up
once. Intake reads whatever there is and writes `brands/<slug>/brand.json`,
copies the artwork it found into `brands/<slug>/assets/`, and prints what it
could not find.

```bash
python3 -m engine.intake --name "Acme Roofing" \
    --site https://acme.example \
    --logo ~/Desktop/acme-logo.svg \
    --files ~/Downloads/acme-brand-folder
```

Only `--name` is required. Every other flag is optional and any combination
works, including none of them.

| Flag | What it does |
|---|---|
| `--name` | The business name. The only required input. |
| `--site` | A public URL. Loaded in Chromium and read for its **computed** styles. |
| `--logo` | A logo file, or a folder of them. Repeatable. |
| `--files` | A folder of whatever the business has, images, PDFs, fonts, a `.fig`. |
| `--out` | Where to write. Defaults to `brands/<slug>`. |
| `--slug` | Defaults to a slug of the name. |
| `--force` | Overwrite an existing `brand.json`. Without it, an existing brand is never touched. |

Then, as with any brand:

```bash
python3 -m engine.verify brands/<slug>
python3 -m engine.render brands/<slug>/brand.json
```

## The one rule

**Nothing is invented.** Every value in the file it writes is one of three
things, and the file says which:

- **measured**, taken off something the brand already ships
- **derived**, computed from a measured value, and labelled as a starting point
- **missing**, not found, reported as a gap, and left as a gap

If the accent cannot be found, no accent is claimed. The document runs
monochrome on the brand's own ink and both the report and the brand file say
that no accent exists yet. A plausible colour in that slot would be quoted back
a year later as the brand's own.

The record lives in the `$intake` block at the top of the written `brand.json`,
and every part of the engine ignores it.

## What each source gives

**A website** is the best single source, because it is what the world already
sees. The page is loaded and the **computed** styles are read off the rendered
DOM, never the stylesheet, which says what an author wrote rather than what a
visitor sees.

- the ground, from `body`, or from the largest painted surface if the body is
  transparent
- the card surface, when the page paints one behind the ground
- the ink: among text colours in genuine use, the one that reads hardest against
  the ground. The commonest text colour is usually the body grey, and taking
  that as the ink loses the real one and leaves no muted tone at all
- the muted ink: the most-used softer colour
- the accent: the most common non-neutral colour across buttons, links and
  headings. Greys, near-blacks and near-whites are excluded, so a monochrome
  site correctly reports that it has no accent
- the families actually rendering, with the weights they render at, taken
  separately for headings and for body
- the type scale: headings from the first visible `h1`,`h3`, body and meta from
  the commonest sizes on the page
- the three most common non-zero border radii
- the logo, from the header image, an inline header `<svg>`, `link[rel=icon]`
  and `meta[og:image]`. Everything found is downloaded into `assets/`

A face that is not a fetchable web font, a licensed one, or a self-hosted one
under an obfuscated name, is reported and the document is set in the cached
fallback until the real file is dropped into `assets/fonts/`.

**Logo files** give the palette when there is no site. An SVG's own paint is
read, with `defs`, masks, filters and clip paths excluded: the black and white
rectangles inside a mask are drawing machinery, and counting them turns every
masked logo into a monochrome brand. A raster is sampled pixel by pixel,
ignoring transparent and near-white pixels.

Several files sort themselves into variants by mean lightness, so the
light-ground and dark-ground versions identify themselves without being named.
Filenames are never trusted for this. If every artwork supplied is dark, the
cover, which prints on a dark ground, is left without a logo and the gap is
recorded, because an invisible logo on a page looks like a finished document and
is not one.

**A dropped folder** is classified by what is in it:

- `.fig`, reported, with a note to run `scripts/fig_decode.py` on it and re-run
  intake against what that writes. Intake does not open `.fig` itself
- `.pdf`, page count read and the file copied to `assets/source/`
- images, copied to `assets/applications/`, or to `assets/logo/` when the name
  or the format says logo
- fonts, copied to `assets/fonts/` and noted

**Nothing at all** still writes a valid file: plain paper, plain ink, the cached
fallback face, and every value marked as computed with the gaps listed.

## Contrast

A derived value that fails WCAG AA against its ground is adjusted until it
passes, keeping its hue and saturation, and the report says it was adjusted.

A **measured** value is never adjusted. A measured pairing that fails is a fact
about the brand, so it is reported as a finding and left alone, `verify` will
report it too, and it is the brand owner's call.

## What it will not do

It will not write voice, tagline, positioning or audience. None of that is
measurable from a website, and the overview page it writes says so in each block
rather than filling the space with something that reads well.
