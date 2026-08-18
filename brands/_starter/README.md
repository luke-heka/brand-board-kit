# Starter brand

Copy this whole folder to `brands/<your-slug>/`, then work through `brand.json` top to bottom.
Give it a name with no leading underscore: folders starting with `_` are templates and are
skipped by the gate and the showcase site. Keys named `_comment` explain the file and are
ignored by the engine. Delete them when done.

## Drop these files in first

| Path | What it is |
|---|---|
| `assets/logo/lockup-primary.svg` | Name and symbol together, dark artwork for a light ground |
| `assets/logo/lockup-reversed.svg` | The same lockup in light artwork, for a dark ground |
| `assets/logo/mark-primary.svg` | The symbol alone, no wordmark |
| `assets/applications/website.png` | Four real touchpoints, shown in a 2x2 grid. |
| `assets/applications/social.png` | Any aspect works: they are letterboxed, not cropped. |
| `assets/applications/card.png` | Screenshots are fine. |
| `assets/applications/signage.png` | |

SVG is preferred for logos and stays crisp at any size. PNG works too: drop the file in
and change the extension in `brand.json` to match.

## Do not want to find artwork first?

Generate stand-ins in your own colours and render the whole document today:

```bash
python3 scripts/make_placeholders.py brands/<your-slug>/brand.json
python3 -m engine.render brands/<your-slug>/brand.json
```

Every placeholder says on its face which file replaces it, so none of them can be
shipped by accident. Swap them one at a time and re-render.

## Change these fields first

1. `meta.slug` to your folder name, then `meta.name` and `meta.wordmark`.
2. `palette` to your real colours. Sample them off the live site, do not recall them.
3. `type.display.family` and `type.body.family` to your real fonts.
4. Every `caption`, `body` and `items` string. They are prompts, not copy.

From the skill root, `python3 -m engine.verify brands/<your-slug>` lists anything still missing.
