"""`docs/CALCULATOR_REFERENCE.md` is generated, and this owns whether it is right.

**THE GENERATOR VALIDATES NOTHING**, deliberately: a tool that also
validated would report a problem in the one place nobody runs. It renders;
this file owns completeness, the relationships and the currency check.

The source is the registry itself. That is the whole reason to generate: a
hand-written reference over 68 calculators is 68 places to forget when one
is added, renamed, re-categorised or retired -- the shape this repository
has paid for four times, most recently a guide that said 51 while the
registry held 53.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from openchem import help as help_docs
from openchem.domain.calculator import RegistryExecution
from openchem.domain.calculator_taxonomy import RETIREMENTS

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "CALCULATOR_REFERENCE.md"

sys.path.insert(0, str(_ROOT / "tools"))
from build_calculator_reference import anchor_for, _result_kind  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def text():
    return _DOC.read_text(encoding="utf-8")


# --- currency, the way `SOURCES.md` already does it ----------------------


def test_the_reference_is_neither_stale_nor_hand_edited():
    """`--check` regenerates in memory and compares byte for byte, which
    catches BOTH failure modes in one pass.

    `build_sources_doc.py` needs a hash as well, because its source is a
    separate file that can move underneath it. Here the source IS the code
    being imported, so there is nothing to get out of step with -- and a
    hand edit and a stale file both simply differ from what the registry
    produces right now.
    """
    done = subprocess.run(
        [sys.executable, str(_ROOT / "tools" / "build_calculator_reference.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_generated_file_says_it_is_generated():
    """A machine-owned file that does not say so invites a hand edit that
    the next regeneration silently discards."""
    first = _DOC.read_text(encoding="utf-8").splitlines()[0]

    assert "GENERATED" in first and "build_calculator_reference.py" in first, first


# --- completeness, in both directions ------------------------------------


def test_every_registered_calculator_has_a_section(registry, text):
    missing = sorted(
        definition.calculator_id
        for category in registry.categories()
        for definition in registry.by_category(category)
        if f"<!-- help:{anchor_for(definition.calculator_id)} -->" not in text
    )

    assert not missing, f"{len(missing)} calculators have no section: {missing}"


def test_every_section_names_a_calculator_that_exists(registry, text):
    """The other direction, so a renamed or retired calculator cannot leave
    a section behind. A stale section is not merely dead: it reads as a
    calculator somebody can go and run."""
    known = {
        anchor_for(definition.calculator_id)
        for category in registry.categories()
        for definition in registry.by_category(category)
    }
    fixed = {"calculator-reference", "always-on-properties", "locant-coverage"}

    anchored = set(re.findall(r"<!--\s*help:([a-z0-9-]+)\s*-->", text))
    orphans = sorted(key for key in anchored - fixed if key not in known)

    assert not orphans, f"sections for calculators that do not exist: {orphans}"


def test_every_always_on_descriptor_is_listed(text):
    """The 41 have no button, so they would be invisible in a reference
    organised by calculator -- which is exactly why the plan asks for a
    section per descriptor family as well as per calculator."""
    from openchem.chem.descriptor_providers import (
        _DESCRIPTOR_SPECS,
        _SHAPE_DESCRIPTOR_SPECS,
    )

    names = [name for _id, name, *_rest in _DESCRIPTOR_SPECS]
    names += [row[1] for row in _SHAPE_DESCRIPTOR_SPECS]
    missing = sorted(name for name in names if f"**{name}**" not in text)

    assert not missing, f"{len(missing)} always-on properties are not listed: {missing}"


# --- a retired calculator stays findable ---------------------------------


@pytest.mark.parametrize("retired_id", sorted(RETIREMENTS))
def test_a_retired_calculator_is_not_registered(registry, retired_id):
    """**RETIRED IS NOT DELETED, AND THIS IS THE HALF THE REGISTRY OWNS.**
    The id is simply not offered, so nothing can start a new calculation
    under it. A stored result stays readable because the reader renders what
    it was handed rather than asking the registry."""
    assert registry.get(retired_id) is None


@pytest.mark.parametrize("retired_id", sorted(RETIREMENTS))
def test_a_retired_calculator_is_listed_under_whatever_replaced_it(
    registry, text, retired_id
):
    """People search for what a thing used to be called. A reference that
    lists only what exists today sends somebody looking for "Solubility vs
    pH" away empty -- the same dead end as a search box that cannot match a
    synonym."""
    retirement = RETIREMENTS[retired_id]

    assert registry.get(retirement.replaced_by) is not None, (
        f"{retired_id} claims to be replaced by {retirement.replaced_by!r}, "
        "which is not registered"
    )
    assert f"**{retirement.display_name}**" in text, (
        f"{retirement.display_name!r} appears nowhere, so searching for it finds nothing"
    )


def test_the_old_name_really_reaches_the_new_calculator():
    """Asserted through `help.search`, not by reading the file: the claim is
    that somebody TYPING the old name arrives at the right section, and the
    file containing the words proves only that the words are in the file."""
    for retirement in RETIREMENTS.values():
        keys = {hit.topic.key for hit in help_docs.search(retirement.display_name)}
        assert anchor_for(retirement.replaced_by) in keys, (
            f"searching {retirement.display_name!r} does not reach "
            f"{retirement.replaced_by!r}; it found {sorted(keys)}"
        )


# --- and the declarations the reference is built from --------------------


def test_every_calculator_declares_what_it_returns(registry):
    """**A DECLARATION NOBODY MADE READS LIKE ONE THAT ROTTED.**

    Measured when this reference was first generated: 12 of 59 calculators
    could not say what they produce. Nine of the twelve had an annotation
    all along and `bootstrap._bind_settings` was eating it -- a bare closure
    keeps none of the wrapped function's metadata, so every sidecar-backed
    calculator presented itself as a nameless `compute`. One more declared
    `-> "PerAtomDataset"` as a string against a `TYPE_CHECKING` import,
    which `get_type_hints` cannot resolve and which therefore looked
    identical to declaring nothing.
    """
    undeclared = sorted(
        definition.calculator_id
        for category in registry.categories()
        for definition in registry.by_category(category)
        if isinstance(definition.execution, RegistryExecution)
        and not _result_kind(definition)
    )

    assert not undeclared, (
        f"{len(undeclared)} calculators do not declare a return type, so the "
        f"reference cannot say what they produce: {undeclared}"
    )


def test_the_settings_binding_keeps_the_wrapped_function_s_identity(registry):
    """The narrow half of the above, at the place that broke it.

    A sidecar-backed calculator is wrapped so the interpreter path can be
    re-read per call. Without `functools.wraps` the wrapper keeps none of
    the original's metadata, and the loss is silent -- nothing raises, the
    calculator works, and every introspecting consumer sees a bare
    `compute`.
    """
    definition = registry.get("solubility")

    assert definition.execution.compute.__name__ == "compute_solubility"
    assert (definition.execution.compute.__doc__ or "").strip(), (
        "the wrapped docstring was lost"
    )


# --- the help system can actually reach it -------------------------------


def test_the_reference_is_registered_with_the_help_system():
    assert "CALCULATOR_REFERENCE.md" in help_docs.HELP_DOCUMENTS


def test_every_anchor_in_the_reference_becomes_a_topic(text):
    """An anchor that is not above a heading is skipped with a warning
    rather than raised, so a broken one is invisible without this."""
    anchored = set(re.findall(r"<!--\s*help:([a-z0-9-]+)\s*-->", text))
    resolved = {
        topic.key
        for topic in help_docs.topics()
        if topic.document == "CALCULATOR_REFERENCE.md"
    }

    assert anchored == resolved, (
        f"anchors that became no topic: {sorted(anchored - resolved)}; "
        f"topics from no anchor: {sorted(resolved - anchored)}"
    )


def test_an_anchor_key_is_the_calculator_id_with_hyphens(registry):
    """A help key is `[a-z0-9-]+` and a calculator id uses underscores, so
    the two differ by separator. One function owns the translation rather
    than a second `.replace()` somewhere else."""
    assert anchor_for("topology_analysis") == "calc-topology-analysis"
    assert anchor_for("docking.vina") == "calc-docking-vina"

    pattern = re.compile(r"^[a-z0-9-]+$")
    for category in registry.categories():
        for definition in registry.by_category(category):
            key = anchor_for(definition.calculator_id)
            assert pattern.match(key), f"{definition.calculator_id} -> {key!r}"


def test_the_locant_coverage_is_recorded_with_its_denominator(text):
    """**A PERCENTAGE WITHOUT ITS POPULATION IS NOT A MEASUREMENT.** The
    number is 34.8%, and what makes it usable is that it is 105 of 181
    molecules from a named corpus -- and that 95 of them name to a retained
    string with no atom indices at all, which is why "None found" is an
    ordinary answer rather than a failure."""
    assert "34.8%" in text
    assert "105 of 181" in text
    assert "benchmarks/naming" in text
