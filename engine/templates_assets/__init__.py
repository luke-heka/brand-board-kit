"""Asset templates. One function per template, one row in REGISTRY.

Each function takes (brand, values, root) and returns the inner HTML of a
canvas already sized by the registry entry. Colour, type and shape come from
CSS variables the renderer injects, so a template never names a hex and works
for any brand, light-on-dark or dark-on-light.
"""

from __future__ import annotations

from . import social, ads, email, print_, digital

REGISTRY: dict[str, dict] = {}
for module in (social, ads, email, print_, digital):
    REGISTRY.update(module.TEMPLATES)

__all__ = ["REGISTRY"]
