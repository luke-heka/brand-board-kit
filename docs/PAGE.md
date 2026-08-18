# The brand page

One permanent link per brand. The owner opens it, scrolls, and every file the
brand has is there to look at and to take. Target and reasoning: `PLAN-BRAND-PAGE.md`.

## Build

```bash
python3 -m engine.render brands/<slug>/brand.json    # deck PDF + per-page PNGs
python3 -m engine.page   brands/<slug>/brand.json    # -> out/<slug>/site/
```

`engine.page` reads the rendered document out of `out/<slug>/`, so run the render
first. Without it the page still builds, minus the Documents section.

Flags: `--out` (default `out/<slug>/site`), `--docs` (default `out/<slug>`).

## What it writes

```
out/<slug>/site/
  index.html                 the page, CSS and fonts inlined, no network calls
  assets/...                 the originals, copied, full resolution
  previews/...               web-size copies, 640px long edge, JPEG q82
  previews/doc/<doc>/NNN.jpg the document's pages, 1600px, for the flip-through
  <slug>-brand-presentation.pdf
  tokens.css  tokens.json
```

Deploy the folder as static files. Every link inside the page is relative, so it
works from any prefix and off a local disk.

Re-running is incremental: unchanged files are skipped, and anything left over
from a previous build that the brand no longer has is deleted, so the page can
never offer a file the brand does not contain.

## How it decides what goes on the page

**Assets.** It walks `brands/<slug>/assets/` and puts every file it finds on the
page, not the selection the deck happens to reference. Top-level folders become
sections, titled from the folder name. One level of nesting becomes a subsection:
`library/social-media-marketing` is Social Media Marketing under Library. Nothing
about the group names is hard-coded, so a brand with a `sound/` folder gets a
Sound section for free.

**Documents.** Any PDF in `out/<slug>/` that has a run of `<stem>-NN.png` pages
beside it becomes a flip-through: a large current page, previous and next, a page
counter, left/right arrow keys, and a PDF download. Two documents sit side by
side; one shows on its own. Rendering a second document is all it takes for it to
appear, no change here.

**Colour.** Every swatch declared in `brand.json`: the named sets from the colour
pages first, then the palette tokens. Click a swatch to copy the hex. `tokens.css`
and `tokens.json` come from `engine.emit_skill`, so they cannot drift from the
skill the same brand emits.

## Previews vs downloads

Cards show a generated preview so a 173MB brand loads quickly. The card itself is
`<a download href="assets/...">` pointing at the untouched original, so the saved
file is always full resolution. SVGs preview as themselves, they are already
small. A file with no image form (a `.md`, say) shows its extension instead of a
picture, so there is never a broken image on the page.

An SVG whose every colour is too pale to survive a light tile is framed on the
brand's dark ground instead, so a reversed mark is visible rather than white on
near-white.

## Style

The page is styled by `templates/page.css` through `theme.stylesheet`, so it
renders in the brand's own colours and type and makes no assumption about whether
the brand is dark-on-light or light-on-dark. Swatch labels pick their colour with
`pages.readable_on`. House rules held here: no drop shadows, no negative tracking,
radii from tokens, images lazy-loaded, and no horizontal scroll at 375px.
