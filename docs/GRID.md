# The grid, measured, not invented

Every number below was measured off a real studio brand deck (20pp, 1920×1080pt)
by rendering its pages at 60dpi (1600×900) and multiplying by 1.2.
Nothing here is recalled or guessed.

## Canvas

```
PAGE      1920 × 1080          landscape, fixed
MARGIN    88px                 left and right, symmetric
SAFE TOP  80px
FOOTER    baseline y = 985     brand name left, © + page number right
```

## The two-column content page, the deck's workhorse

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  Section              ┌──────────────────────────────────────────────┐ │
│  title                │                                              │ │
│  (80px)               │                                              │ │
│                       │              PANEL                           │ │
│                       │              x 536 → 1832                    │ │
│                       │              y  80 →  904                    │ │
│                       │              radius 30, fill #FFFFFA         │ │
│  Caption title (20)   │                                              │ │
│  Caption body  (17)   │                                              │ │
│  bottom-aligned       └──────────────────────────────────────────────┘ │
│  with panel bottom                                                     │
│                                                                        │
│  Brand name                             © 2026 / All rights reserved 06│
└────────────────────────────────────────────────────────────────────────┘
```

| Element | x | y | size | value |
|---|---|---|---|---|
| Section title | 88 | 80 | 80px | display face, wght 585, tracking -0.04em, ink `#242424` |
| Caption title | 88 | bottom-aligned to panel | 20px | body 600, tracking -0.03em, ink `#242424` |
| Caption body | 88 | under title, gap 14 | 17px | body 600, tracking -0.03em, lh 1.5, ink `#616161` |
| Caption column width |, |, | 360px | never wider, the original wraps at ~7 words |
| Panel | 536 | 80 | 1296 × 824 | radius 30, fill `#FFFFFA` on `#F7F5EF` ground, no shadow |
| Footer brand | 88 | 985 | 17px | body 600, ink `#242424` |
| Footer legal | right→1832 | 985 | 13px | ink `#616161` |
| Footer page no. | right edge 1832 | 985 | 13px | body 600, ink `#242424` |

The caption block is **bottom-anchored**, not top-anchored. That single detail is what
makes the original read as designed rather than templated, copy grows upward from a
fixed baseline while the panel stays put.

## The section divider

Full-bleed. The section word set large and low-left, the section numeral to its right at
the same baseline. The original uses `O1`,`O5` with a letter O, not a zero; that is a
typo in the source and is corrected to `01`,`0n` here.

```
word      120px display, wght 500 (big type gets LIGHTER — site law), tracking -0.04em
numeral   120px, ink #616161
position  left 88, baseline 985 (sits on the footer line)
ground    #F7F5EF
```

## The cover

```
brand name    120px display wght 500, left 88, baseline ~560
document type 45px, ink #616161, directly under, gap 20
footer        © line only, left 88, y 985
```

## The table of contents

Rows on a 1px `rgba(36,36,36,.10)` hairline, one rule above each row and one closing rule.

| Column | x | width | style |
|---|---|---|---|
| Number | 88 | 60 | 25px, ink `#616161` |
| Title | 148 | 340 | 30px, wght 585, tracking -0.04em |
| Description | 640 | 620 | 17px, ink `#616161`, lh 1.4, max 2 lines |
| Page range | right → 1832 |, | 17px, ink `#616161` |

Row height 132, first rule at y 160.

## What the panel holds, per page type

| Page type | Panel contents |
|---|---|
| Logo lockup | The logo centred, height capped at 260px, on the variant's own background |
| Logo mark | Three marks in a row, each labelled beneath at 13px |
| Clearspace | The mark centred with a `1/4` measure drawn on two edges |
| Misuse | 2×3 grid of don't-cards, each with a rule caption at 13px |
| Colour | Full-width stacked bars, `HEX` label + value knocked into the bar, bottom-left inset 28 |
| Colour ramp | 4×2 grid of chips, name above, hex below |
| Typeface | Weight rows: label left (120px col), specimen right, alphabet + numerals |
| Type scale | Rows: px value left (90px col, ink muted), specimen right at true size |
| Imagery | Register cards, image + name + one-line direction |
| Motion | Curve cards drawn as inline SVG + duration table |
| Components | Live component renders on the panel, at true size |
| Applications | Contact-sheet grid of touchpoint renders |

## The laws this deck holds to

These are properties of the deck, not of any one brand. The hexes below are the
reference brand's values, shown so the shape of the rule is concrete; yours come
from your own `palette` block.

1. A ground and a card ground, one step apart. Never pure white.
   Reference brand: ground `#F7F5EF`, cards `#FFFFFA`.
2. Two inks, a primary and a muted. Never `#000`.
   Reference brand: `#242424` / `#616161`.
3. One accent. Colour variety comes from photography, not the palette.
4. Display = variable face at **585**; the giant one-word display drops to **500**.
5. Tracking always negative: `-0.04em` ≥25px, `-0.03em` 15-20px, `-0.025em` at 13px.
6. Radii 20 / 30 / 40 or a circle. Nothing else.
7. No shadows, anywhere.
8. Every button carries its 10px dot.

## Corrections made to the 2025 original

| # | Original | Fixed |
|---|---|---|
| 1 | "Tiertiary" (pages 8 and 9) | "Tertiary" |
| 2 | Clearspace printed twice, identical copy (pages 10, 11) | One clearspace page; page 11 becomes **Logo misuse**, which the original lacks |
| 3 | Divider numerals set as `O1`,`O5` (letter O) | `01`,`0n` (digits) |
| 4 | Primary colour `#FFFFFF` / `#0A0A0A` | Site-measured `#F7F5EF` / `#242424`, purple unchanged |
| 5 | Type scale 64/48/32/24/18/16 | Site-measured 120/80/60/45/30/25/20/17/15/13/12 |
| 6 | Manrope shown at six static weights | Variable axis, with 585 and 500 called out as the two that ship |
| 7 | No imagery, motion or component sections | Added, because the brand now has all three |
| 8 | Superseded "luxury AI consultancy" vision, voice and tagline | Current wording, read from `THE-SPINE.md`, never recalled |
