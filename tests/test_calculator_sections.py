"""How the Properties panel's sections are shaped, derived from the registry.

**26 SECTIONS HELD 49 BUTTONS AND ELEVEN HELD EXACTLY ONE**, so finding a
calculator meant scrolling twenty-six headings, most concealing a single
item. Counted in `docs/NAVIGATION_AUDIT.md` and the strongest single
number behind the report that this had become difficult software to use.

Every guard here reads the LIVE REGISTRY rather than a list kept beside
it. `CalculatorDefinition.category` is deliberately a free string -- its
own docstring says a new category needs no code change -- so a
hand-written list is a blocklist by another name, and this codebase has
already watched one rot (`inapplicable_calculators`, 22 of 49 correct).
"""

from __future__ import annotations

from collections import Counter

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import RegistryExecution
from openchem.ui.panels.property_panel import _CATEGORY_LABELS, _CATEGORY_ORDER

#: The one category that may hold a single calculator, and why.
#:
#: A DECLARED exception, not a threshold. `nmr_database` has no registry
#: sibling -- the ORCA NMR jobs are ServiceExecution and live in their own
#: panel -- and filing a spectroscopic measurement under a structural
#: heading purely to flatten a count would be worse than the count. The
#: entry is by NAME so a second singleton cannot arrive quietly.
_ALLOWED_SINGLETONS = {"nmr"}


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def button_counts(registry) -> Counter:
    """Calculators that actually put a BUTTON in a section.

    ServiceExecution entries (Docking, Quantum Chemistry) are registered
    for discovery and run from their own panels, so they are excluded
    exactly as `_section_for` excludes them.
    """
    counts: Counter = Counter()
    for category in registry.categories():
        counts[category] = sum(
            1
            for definition in registry.by_category(category)
            if isinstance(definition.execution, RegistryExecution)
        )
    return counts


def test_no_category_holds_a_single_calculator(button_counts):
    singletons = {c for c, n in button_counts.items() if n == 1}

    assert singletons <= _ALLOWED_SINGLETONS, (
        f"{sorted(singletons - _ALLOWED_SINGLETONS)} hold exactly one calculator. "
        "A section per calculator is the shape this panel was measured in and "
        "moved away from -- merge it, or declare it in _ALLOWED_SINGLETONS "
        "with the reason."
    )


def test_the_declared_singleton_really_is_one(button_counts):
    """The other half, so the allowlist cannot outlive its reason.

    An entry that has quietly gained a sibling is a stale exception, and a
    stale exception is how a guard starts lying -- the same failure as a
    corpus entry claiming coverage it no longer provides.
    """
    for category in _ALLOWED_SINGLETONS:
        assert button_counts.get(category) == 1, (
            f"{category!r} is allowed to be a singleton but now holds "
            f"{button_counts.get(category)}. Remove it from _ALLOWED_SINGLETONS."
        )


def test_every_section_has_a_heading_somebody_chose(button_counts):
    """`_CATEGORY_LABELS` falls back to `category.title()`, which shipped
    the NMR section as "Nmr" until a documentation sweep caught it. The
    fallback stays -- a plugin category must not crash the panel -- but
    nothing WE ship may rely on it.

    **DESCRIPTORS MAKE SECTIONS TOO, and the first version of this test
    missed them.** It checked only the calculator registry, passed, and
    the running app showed a section headed "Logp" -- because
    `_on_descriptor_computed` files a `DescriptorValue` by ITS category,
    and the descriptor table is a separate list from the registrations.
    Both sources are read here for that reason.
    """
    from openchem.chem.descriptor_providers import _DESCRIPTOR_SPECS

    descriptor_categories = {spec[3] for spec in _DESCRIPTOR_SPECS if spec[3]}
    missing = sorted(
        c for c in set(button_counts) | descriptor_categories if c not in _CATEGORY_LABELS
    )

    assert not missing, (
        f"{missing} would be title-cased into a heading nobody chose. "
        "Add them to _CATEGORY_LABELS."
    )


def test_no_heading_contains_an_ampersand():
    """The section header is a `QToolButton`, which treats `&` as a
    MNEMONIC and swallows it: "Lipophilicity & Refractivity" rendered as
    "Lipophilicity  Refractivity", ampersand gone, with a stray gap where
    it had been. Seen in the running app after a merge every test passed.

    Escaping as `&&` would work and is not the rule, because the next
    person to add a heading will not know that. No ampersands at all.
    """
    offenders = {c: label for c, label in _CATEGORY_LABELS.items() if "&" in label}

    assert not offenders, f"{offenders} -- a QToolButton eats the ampersand"


def test_no_heading_is_long_enough_to_elide():
    """"Identity & Composition" rendered as "Identity ...mposition".

    21 characters is not a taste judgement: it is the longest heading
    MEASURED to fit at the panel's real width in the running app
    ("Electronic Properties" and "Structure Generators", both 20-21, need
    116-120 px against 121-125 available). The ceiling is stated here
    rather than recomputed, because computing it needs the real dock.
    """
    too_long = {c: label for c, label in _CATEGORY_LABELS.items() if len(label) > 21}

    assert not too_long, f"{too_long} will elide in the panel"


def test_every_ordered_category_still_has_a_heading():
    """A stale entry in `_CATEGORY_ORDER` is invisible -- the category is
    never seen, so it sorts nothing and nothing fails. After a merge that
    is exactly what gets left behind.

    **Checked against `_CATEGORY_LABELS`, NOT against the registry.** The
    first version of this test asserted every ordered category was
    registered and failed on `physicochemical`, `medicinal_chemistry` and
    `shape` -- which are real sections that no CALCULATOR registers: they
    come from the descriptor providers and from the alert catalogs. The
    two lists in this panel having the same membership is the invariant
    that actually holds.
    """
    stale = [c for c in _CATEGORY_ORDER if c not in _CATEGORY_LABELS]

    assert not stale, (
        f"{stale} are ordered but have no heading -- left behind by a merge?"
    )


def test_a_calculators_result_lands_in_its_own_section(registry):
    """THE TRAP IN MERGING CATEGORIES, and the reason this file exists.

    A `ReportResult` and an `AlertResult` carry their OWN `category` --
    the panel files them with `report.category`, not with the definition's
    -- while everything else is filed by registry lookup. So moving a
    calculator to a new section without moving the category its result
    carries puts the BUTTON in one section and its ANSWER in another,
    with nothing failing anywhere.

    Checked by running each calculator, because the two values live in
    different files and only agree if somebody kept them in step.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem

    from openchem.domain.common import CacheState

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    # WITH A CONFORMER, or the 3D-dependent calculators all come back
    # FAILED and are skipped -- `interaction_analysis` is one of the
    # categories this merge moved, so without geometry the guard would
    # not cover the very change it was written for.
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)

    mismatched = []
    compared: list[str] = []
    for category in registry.categories():
        for definition in registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                continue
            try:
                result = registry.compute(
                    definition.calculator_id,
                    mol,
                    "uuid",
                    {p.name: p.default for p in definition.parameters},
                )
            except Exception:  # noqa: BLE001 - a calculator that raises is not this test's subject
                continue
            carried = getattr(result, "category", None)
            if carried is None or getattr(result, "cache_state", None) is CacheState.FAILED:
                continue
            compared.append(definition.calculator_id)
            if carried != definition.category:
                mismatched.append(
                    f"{definition.calculator_id}: button in {definition.category!r}, "
                    f"result in {carried!r}"
                )

    assert not mismatched, "\n".join(mismatched)
    # A FLOOR, because a guard that silently compares nothing passes.
    # Every result that fails or carries no category of its own is
    # skipped above, so a change that made them all fail would turn this
    # into an assertion about an empty list -- which is the shape of
    # "an arm that does not run is not an arm", one level up.
    assert len(compared) >= 10, f"only compared {compared}"
