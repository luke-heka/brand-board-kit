"""Self-test for the pure functions. Run it after touching the engine.

    python3 -m engine.selftest

Every case here is a bug that shipped once. They are cheap to keep and they are
the difference between "the deck renders" and "the deck is right".
"""

from __future__ import annotations

import sys

from .pages import contrast, readable_on, _aspect  # noqa: F401
from .theme import _legible_on, check_palette

FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def main() -> int:
    # A pale swatch on a light-on-dark brand. ink and inkOnDark are the same
    # colour there, so a two-way choice offers no dark option and the label
    # disappeared into its own swatch.
    dark_brand = ("#F2EDE3", "#F2EDE3", "#16140F", "#0B0A07")
    check(readable_on("#F6F1E8", *dark_brand) == "#0B0A07",
          "pale swatch on a light-on-dark brand must take a dark label")
    check(readable_on("#141118", *dark_brand) == "#F2EDE3",
          "dark swatch on a light-on-dark brand must take a light label")

    # The original failure: branching on luminance assumed ink was the dark one.
    light_brand = ("#242424", "#FFFFFA", "#F7F5EF", "#242424")
    check(readable_on("#F7F5EF", *light_brand) == "#242424",
          "pale swatch on a dark-on-light brand must take ink")
    check(readable_on("#6736E2", *light_brand) == "#FFFFFA",
          "accent swatch must take the light ink")

    check(readable_on("#FFFFFF", "#123456") == "#123456",
          "a single candidate is returned as is")
    check(readable_on("#FFFFFF", "", None) == "#000000", "no candidate falls back safely")

    # Captions on a coloured tile pick from the brand's own two, never a new hue.
    check(_legible_on("#FF5A1F", "#141118", "#F6F1E8") == "#141118",
          "ember tiles must caption in ink")
    check(_legible_on("#6736E2", "#242424", "#FFFFFA") == "#FFFFFA",
          "purple tiles must caption in the light ink")

    check(round(contrast("#000000", "#FFFFFF"), 1) == 21.0, "black on white is 21:1")
    check(round(contrast("#FFFFFF", "#FFFFFF"), 1) == 1.0, "a colour on itself is 1:1")

    # A value like "#12" is not a colour. Chromium drops it and the render used
    # to exit zero over a deck with a white ground it was never designed for.
    for bad in ("#12", "amber", "#GGGGGG", 42, None):
        try:
            check_palette({"palette": {"canvas": bad}})
            FAILURES.append(f"check_palette accepted {bad!r}")
        except ValueError:
            pass
    try:
        check_palette({"palette": {"canvas": "#F7F5EF", "ink": "#242"}})
    except ValueError:
        FAILURES.append("check_palette rejected a valid 3-digit hex")

    for f in FAILURES:
        print(f"  FAIL  {f}")
    print(f"\n{'SELFTEST FAILED' if FAILURES else 'SELFTEST PASSED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
