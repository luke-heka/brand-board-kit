# Completeness

A folder of generated assets reads as a finished brand. It usually is not, and
nothing in the folder says so. `engine.gaps` is the part that says so: it
compares a brand against what a complete brand of this kind has, and reports
every difference with the action that closes it.

Nothing is ever fabricated to fill a gap. A placeholder that looks finished is
worse than an empty slot that says what it needs.

## Run

```bash
python3 -m engine.gaps brands/<slug>/brand.json           # print the report
python3 -m engine.gaps brands/<slug>/brand.json --write   # also write out/<slug>/PENDING.md
python3 -m engine.gaps brands/<slug>/brand.json --json    # the whole audit, machine-readable
```

The path can be the `brand.json` or the folder holding it. `--out` moves the
output root, the same way `engine.verify` takes it.

## What it checks

29 expectations across seven parts of a brand. Each one is read off the brand
file and off what is really on disk, a logo path that points at nothing does
not count as a logo.

| Part | Expectations |
|---|---|
| Logo | primary lockup, dark-ground version, accent-ground version, standalone mark, favicon-sized mark |
| Colour | canvas, ink, muted ink, accent, pressed accent, the dark-ground trio, a secondary set big enough to build an interface |
| Type | display face, body face, the weights each face needs, a written scale |
| Imagery | one photograph, then a second one doing a different job |
| Voice | the positioning line, and a message set so every asset does not say the same thing |
| Documents | the long guideline, the short identity |
| Assets | social, ads, email, print, digital, covers, and the email signature specifically |

Two of these come from the engine rather than from a list here. The palette keys
are `theme.PALETTE_DEFAULTS`, and the asset families are the template registry's
own groups collapsed one level, so adding a template family raises the bar
without anybody editing `gaps.py`.

The score is a flat count: expectations met over expectations checked, unweighted.
A weighting is an opinion, and this number has to survive being read by someone
who did not write it.

## Reading the report

```
Bondi Bakehouse — 27 of 29 things a complete brand has (93%)

Imagery     0/2
   GAP    Photography — With no photograph, the deck and every social asset can
          only be type on a colour, which is why a brand ends up looking like a slide.
          fix: Drop a JPG into assets/imagery/, then add it to the imagery section
          of brand.json as a register: the file, plus one line saying when to use it.
```

What is present is listed too. A report of only failures hides the progress and
reads as a punishment.

`PENDING.md` is the same information written for a person: grouped by part, each
gap saying what is missing and what to do about it, then a closing list of what
is already there.

## Using it from code

```python
from .gaps import gaps, audit

for g in gaps(brand, brand_dir):      # only what is missing, in section order
    card(g["title"], g["why"], g["fix"])
```

Every record carries `id`, `section`, `group`, `title`, `why`, `fix`, `detail`
and `have`. `audit()` returns the same records plus `present`, `missing` and
`score`, which is what the hero count on the brand page is built from. The full
contract, field by field, is at the top of `engine/gaps.py`.

## Where the bar comes from

The expectations are what it takes for a brand to survive contact with real
work: something to sign a dark slide with, a second text colour so a caption can
be quieter than a heading, a photograph so the deck is not type on a colour, a
signature so mail does not go out unsigned.

Deliberately not checked: motion, components, grid, clear space, misuse pages,
and the radius scale. They are all real parts of a brand system and every one of
them is renderable, but a brand missing them is under-specified rather than
unusable, and padding the count with items nobody is blocked on makes the score
worth less. Contrast is not checked here either, `engine.verify` already
measures it, and reports it as a finding against the brand's own values.
