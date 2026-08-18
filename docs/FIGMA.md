# Pulling a brand out of Figma

`scripts/figma_pull.py` reads a Figma file and writes down what is in it: every
page and frame, every named style, every colour and type combination, and one
rendered SVG or PNG per frame. It only reads, and needs no paid Figma seat.

## One-time setup

1. In Figma, click your avatar, then **Settings**, then the **Security** tab.
2. Scroll to **Personal access tokens** and click **Generate new token**.
3. Give it read access to **file_content** and **file_dev_resources**. Scopes lock
   when the token is made, so one without those two must be replaced, not edited.
4. Click **Generate token** and copy it. Figma shows it once and never again.
5. Save it in Keeper as a password under the record name `figma-token`.

## Commands

```bash
cd <path-to-this-skill>
python3 scripts/figma_pull.py https://www.figma.com/design/<key>/<name>
python3 scripts/figma_pull.py <key> --node 7774-145 --images
python3 scripts/figma_pull.py <key> --images --format png --scale 2 --out figma/brand
```

Paste the whole Figma URL or just the key. Set `FIGMA_TOKEN` in your environment,
or pass `--record <name>` to read it from a password manager. Output defaults to
`figma/<file-name>/`.

## What you get

| File | What it is for |
|---|---|
| `INVENTORY.md` | Read first. Every page and frame, with size and node id |
| `structure.json` | The raw tree, so nothing is lost and anything can be re-read |
| `styles.json` | Named text, paint and effect styles, resolved to real values |
| `tokens.draft.json` | Every colour and type combination found, by frequency |
| `assets/` | One SVG or PNG per frame, named after the frame plus its node id |

`tokens.draft.json` is a **draft**: it counts what the file holds and names nothing.
A person picks which values are the brand, then writes those into `brand.json`.
