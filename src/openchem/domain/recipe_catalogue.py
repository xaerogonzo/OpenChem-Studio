"""The recipes this build ships, and which versions of them it has.

A module of its own because the list has to import every recipe, and a recipe imports `domain.recipe`: keeping the
list in `domain.recipe` was an import cycle waiting for the first recipe. `recipe_run.ProjectView` reads
`shipped_versions` as its default, so the question "does THIS build have that version" has one answer that no
host has to remember to hand in.

`tests/test_recipe_model.py` validates whatever is listed here against the real calculator registry, so a recipe that
is not well formed is a failing test, not a recipe that runs and refuses.
"""

from __future__ import annotations

from collections.abc import Iterable

from openchem.domain.lewis_pairing import LEWIS_PAIRING
from openchem.domain.recipe import Recipe

#: Every recipe this build ships, in the order a list shows them.
SHIPPED_RECIPES: tuple[Recipe, ...] = (LEWIS_PAIRING,)


def shipped_versions(recipes: Iterable[Recipe] | None = None) -> dict[str, frozenset[str]]:
    """recipe id -> the versions this build has. What a stored run's version is compared against."""
    found: dict[str, set[str]] = {}
    for recipe in SHIPPED_RECIPES if recipes is None else recipes:
        found.setdefault(recipe.recipe_id, set()).add(recipe.version)
    return {recipe_id: frozenset(versions) for recipe_id, versions in found.items()}

