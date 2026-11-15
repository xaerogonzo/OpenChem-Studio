"""A structure template: identity and metadata, no coordinates toolkit.

Shipped catalogs and the user's library both become these objects. Chemistry
turns a SMILES or molblock into a drawable 2D molblock; this module does not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class TemplateOrigin(Enum):
    """Who owns the category. User JSON cannot set `shipped`."""

    SHIPPED = "shipped"
    USER = "user"


class TemplateKind(Enum):
    """How the structure is meant to be used.

    V1 ships only complete molecules. A dummy-atom fragment is a different
    kind, and bonding to `*` does not consume an attachment point.
    """

    COMPLETE_MOLECULE = "complete_molecule"


#: The only shipped kind: a complete molecule, never a dummy-atom fragment.
SHIPPED_KIND = TemplateKind.COMPLETE_MOLECULE

#: User category ids, including My Templates, start with this.
USER_ID_PREFIX = "user:"

#: Stable id of the built-in user category the person can save into.
MY_TEMPLATES_ID = "user:my_templates"
#: Display title of that category.
MY_TEMPLATES_TITLE = "My Templates"

#: Version of the user's library.json schema.
LIBRARY_VERSION = 1

#: How the Template Library tree is grouped. Each shipped category id appears
#: once. Display order is this table, not `_SHIPPED_FILES`. A leftover id lands
#: under Other so a new catalog cannot vanish from the dialog.
SHIPPED_CATEGORY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Scaffolds", ("rings", "cycloalkanes", "heterocycles", "polycycles")),
    (
        "Building blocks",
        (
            "amino_acids",
            "nucleobases",
            "sugars",
            "functional_groups",
            "peptide_building_blocks",
        ),
    ),
    ("Laboratory", ("solvents_reagents",)),
    (
        "Natural products",
        ("alkaloids", "flavonoids", "vitamins", "cofactors", "terpenoids_steroids"),
    ),
    ("Elements", ("allotropes", "reactive_species")),
)


def nested_category_groups(
    categories: Sequence[TemplateCategory],
) -> tuple[tuple[str, tuple[TemplateCategory, ...]], ...]:
    """Headings and the categories under them, for the dialog tree."""
    by_id = {category.id: category for category in categories}
    used: set[str] = set()
    groups: list[tuple[str, tuple[TemplateCategory, ...]]] = []
    for title, ids in SHIPPED_CATEGORY_GROUPS:
        present = tuple(by_id[cid] for cid in ids if cid in by_id)
        if present:
            groups.append((title, present))
            used.update(category.id for category in present)
    leftover = tuple(
        category
        for category in categories
        if category.origin is TemplateOrigin.SHIPPED and category.id not in used
    )
    if leftover:
        groups.append(("Other", leftover))
    mine = tuple(category for category in categories if category.origin is TemplateOrigin.USER)
    if mine:
        groups.append(("Mine", mine))
    return tuple(groups)


class TemplateError(ValueError):
    """A template or category that cannot be used, with a reason."""


@dataclass(frozen=True)
class TemplateEntry:
    """One drawable structure in a category."""

    id: str
    name: str
    category_id: str
    smiles: str | None = None
    molblock: str | None = None
    description: str = ""
    tags: tuple[str, ...] = ()
    source: str = ""
    kind: TemplateKind = TemplateKind.COMPLETE_MOLECULE
    provenance: dict[str, str] | None = None

    def __post_init__(self) -> None:
        has_smiles = bool(self.smiles and self.smiles.strip())
        has_molblock = bool(self.molblock and self.molblock.strip())
        if has_smiles == has_molblock:
            raise TemplateError(
                f"{self.id}: a template needs exactly one of smiles or molblock"
            )
        if not self.id.strip():
            raise TemplateError("a template needs an id")
        if not self.name.strip():
            raise TemplateError(f"{self.id}: a template needs a name")
        if not self.category_id.strip():
            raise TemplateError(f"{self.id}: a template needs a category")

    def matches(self, query: str) -> bool:
        """Whether a library search should list this entry."""
        needle = query.strip().casefold()
        if not needle:
            return True
        haystacks = [self.name, self.description, *self.tags, self.id]
        return any(needle in piece.casefold() for piece in haystacks if piece)


@dataclass(frozen=True)
class TemplateCategory:
    """A named group of templates."""

    id: str
    title: str
    origin: TemplateOrigin
    description: str = ""
    entries: tuple[TemplateEntry, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise TemplateError("a category needs an id")
        if self.origin is TemplateOrigin.USER and not self.id.startswith(USER_ID_PREFIX):
            raise TemplateError(
                f"{self.id}: a user category id must start with {USER_ID_PREFIX!r}"
            )
        if self.origin is TemplateOrigin.SHIPPED and self.id.startswith(USER_ID_PREFIX):
            raise TemplateError(f"{self.id}: a shipped category cannot use the user id prefix")
        for entry in self.entries:
            if entry.category_id != self.id:
                raise TemplateError(
                    f"{entry.id}: category_id {entry.category_id!r} does not match {self.id!r}"
                )


def parse_origin(raw: object) -> TemplateOrigin:
    """A stored origin, or refuse. User files cannot claim shipped."""
    if raw == TemplateOrigin.USER.value:
        return TemplateOrigin.USER
    if raw == TemplateOrigin.SHIPPED.value:
        return TemplateOrigin.SHIPPED
    raise TemplateError(f"unknown template origin: {raw!r}")


def parse_kind(raw: object) -> TemplateKind:
    if raw is None or raw == "":
        return TemplateKind.COMPLETE_MOLECULE
    if raw == TemplateKind.COMPLETE_MOLECULE.value:
        return TemplateKind.COMPLETE_MOLECULE
    raise TemplateError(f"unknown template kind: {raw!r}")
