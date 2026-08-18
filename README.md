# Brand Board

Turn what your business already has into a real brand system. A logo, some colours,
a website. That is enough to start.

You get three things out of it:

| What | Why you want it |
|---|---|
| **Brand presentation** | The landscape PDF you hand a designer, a printer or a new hire |
| **Brand board** | One sheet with the whole system on it, for looking at rather than reading |
| **A Claude skill** | Drop it in and every future thing Claude builds for you starts on brand |

All three come from one file. Change a colour in that file and all three change together.
That is the whole idea. No Figma. No designer. No subscription.

## Install

You need Python 3.10 or newer. Everything else installs itself.

```bash
bash install.sh
```

That copies the skill into `~/.claude/skills/brand-board`, builds an isolated Python
environment inside it, and downloads the browser it uses to render pages. It touches
nothing else on your machine and needs no admin password. Run it again any time to update.

The browser download is about 150MB and happens once per machine, not once per brand.

## Make your first brand

Open Claude Code and say it in plain English:

> Build a brand board for my business. The site is example.com.

Claude reads your site, takes the real colours and fonts off the rendered page, writes
the brand file, renders both PDFs and tells you what is still missing.

If you would rather drive it yourself, everything is one command at a time:

```bash
cd ~/.claude/skills/brand-board
source .venv/bin/activate

cp -R brands/_starter brands/your-brand
python3 -m engine.verify brands/your-brand    # what is still missing
python3 -m engine.render brands/your-brand/brand.json
```

Your files land in `out/your-brand/`.

## What good looks like

Run the gate before you send anything to anybody:

```bash
python3 -m engine.verify brands/your-brand
```

It runs about 780 checks and separates two different things. A **FAIL** means this tool
got something wrong, and you should not ship until it is fixed. A **finding** means your
*brand* has a property worth knowing, most often two colours that are hard to read
against each other. Findings are never fixed silently, because quietly recolouring
somebody's brand is worse than telling them the truth about it.

Then open the PDF and page through it. The gate proves the plumbing. Only your eyes
prove the quality.

## Already have a Figma file?

You do not need a paid seat or a token. In Figma choose File, then Save local copy,
then:

```bash
python3 scripts/fig_decode.py yourfile.fig --out figma/yours
```

That reads the whole document: every image, the node tree, the real styles, every
colour by how often it is used, and every font family in the file.

One warning worth having. A working Figma file is the best source for artwork and
layout, and often the worst source for colour, because years of values pile up in it
that nobody ever cleaned out. Measure your live site for the palette. Use the file
for the assets.

## When something breaks

Ask Claude to run it again and read the error. The skill is written to self heal, and
the gate names the exact file it wanted. Every command prints what it is looking for
rather than failing silently.

Made by Selr AI.
