"""What a FACT means, and whether the reader says it.

**THE POPULATION `test_tooltip_coverage.py` CANNOT SEE.** That walk is over
controls a user OPERATES -- `_INTERACTIVE` is buttons, combo boxes, spin
boxes, line edits and sliders -- so a value's caption, which is a `QLabel`,
is outside it entirely. Measured while writing this: with a molecule
selected and the reader showing the aggregate, the walk finds 13 controls
inside the `FactView` and every one of them is the search box, a combo, the
copy button or a section toggle. None of the 41 rows is among them.

That is why the recorded hole could not be closed by widening the walk. The
plan called for extending the coverage guard to "runtime-built rows with a
molecule selected"; measured, selecting a molecule adds no UNCONTRACTED
control at all -- 0 before and 0 after -- because 2c deleted the descriptor
rows that were the hole. What replaced them is data, not controls, and data
needs a guard of its own.

The prose floor is the SAME floor: `placeholder_reason` moved into
production so both files ask one function rather than growing two standards.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from openchem.chem.descriptor_providers import (
    _DESCRIPTOR_SPECS,
    _SHAPE_DESCRIPTOR_SPECS,
)
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import (
    DESCRIPTOR_HELP_PREFIX,
    aggregate_descriptors,
    descriptor_help_id,
)
from openchem.ui.fact_help import CONTRACTS, contract_for
from openchem.ui.widgets.help_tooltip import placeholder_reason

_ROOT = Path(__file__).resolve().parent.parent


def _every_descriptor_id() -> set[str]:
    """Read off the spec tables, never typed out here.

    A hand-written list is a list that excludes the descriptor nobody
    thought of -- the failure `_SUMMARISED_TYPES` already records one file
    along, where the omitted type was the one the code got wrong.
    """
    ids = {descriptor_id for descriptor_id, *_rest in _DESCRIPTOR_SPECS}
    ids |= {row[0] for row in _SHAPE_DESCRIPTOR_SPECS}
    return ids


# --- the registry covers what it claims to ------------------------------


def test_every_always_on_descriptor_has_a_contract():
    """**THE RECORDED HOLE, CLOSED WHERE THE VALUE NOW LIVES.** Every
    success branch of the Properties panel's descriptor row ended
    `setToolTip("")`, so hovering one gave you `_ElidingLabel` echoing the
    caption -- the degeneracy this suite refuses everywhere else. The rows
    are gone and the values are read in the results panel; the contract
    follows the value.
    """
    missing = sorted(
        descriptor_id
        for descriptor_id in _every_descriptor_id()
        if contract_for(descriptor_help_id(descriptor_id)) is None
    )
    assert not missing, (
        f"{len(missing)} always-on descriptors have nothing saying what they "
        f"are: {missing}"
    )


def test_the_registry_holds_nothing_that_is_not_rendered():
    """The other direction, so a renamed descriptor cannot leave a contract
    behind that nothing can reach. A stale entry is not merely dead: it
    reads as coverage."""
    ids = {descriptor_help_id(d) for d in _every_descriptor_id()}
    orphans = sorted(key for key in CONTRACTS if key not in ids)
    assert not orphans, f"contracts for descriptors that no longer exist: {orphans}"


def test_the_producer_and_the_registry_agree_on_the_id_scheme():
    """One string, imported, rather than two that can drift.

    `domain/` cannot import `ui/`, so the prefix lives with the producer and
    the registry imports it. Asserting IDENTITY of the derived ids rather
    than equality of two literals: a copied literal compares equal.
    """
    assert DESCRIPTOR_HELP_PREFIX == "descriptor."
    for key in CONTRACTS:
        assert key.startswith(DESCRIPTOR_HELP_PREFIX), key


# --- and each contract is worth reading ---------------------------------


@pytest.mark.parametrize("help_id", sorted(CONTRACTS), ids=lambda k: k.split(".", 1)[-1])
def test_each_contract_is_structurally_valid_and_not_a_placeholder(help_id):
    contract = CONTRACTS[help_id]
    contract.validate()
    assert placeholder_reason(contract) is None, (
        f"{help_id} has {placeholder_reason(contract)}"
    )


@pytest.mark.parametrize("help_id", sorted(CONTRACTS), ids=lambda k: k.split(".", 1)[-1])
def test_no_contract_merely_restates_the_name_it_explains(help_id):
    """**THE DEGENERACY THE WHOLE HELP LAYER EXISTS TO REFUSE.** A tooltip
    reading "Spherocity Index." on a row labelled "Spherocity Index" is
    exactly what the elision tooltip was already doing for free, and the
    length floor alone does not catch a padded restatement.

    Checked as: strip the display name out of the text and something
    substantial must remain. Deliberately not a similarity score -- see
    `DEGENERATE_TEXT`'s own note on why this family of check must stay
    structural.
    """
    names = {
        descriptor_help_id(d): n for d, n, *_rest in _DESCRIPTOR_SPECS
    }
    names.update({descriptor_help_id(r[0]): r[1] for r in _SHAPE_DESCRIPTOR_SPECS})
    name = names[help_id]
    remainder = CONTRACTS[help_id].text.casefold().replace(name.casefold(), "")
    # WORDS, not `split()` tokens. Measured on the mutation that survived
    # this guard's first version: removing "Spherocity Index" from "The
    # Spherocity Index of this conformer, which is the spherocity index.
    # Spherocity Index." leaves seven words and two orphaned full stops, and
    # `split()` counted those stops -- nine tokens against a floor of eight,
    # so a pure restatement passed.
    words = re.findall(r"[a-z0-9]+", remainder)
    assert len(words) >= 8, (
        f"{help_id} says little beyond its own name {name!r} ({len(words)} "
        f"words remain): {CONTRACTS[help_id].text!r}"
    )


def test_a_claimed_source_key_is_in_the_registry():
    """A UI claim citing a source must cite one that exists.

    The motivating case is on record: a Vina scoring error was nearly
    shipped in a tooltip quoted from memory. It happened to be right, which
    is luck rather than method -- an unsourced number in a tooltip acquires
    the application's authority.
    """
    registry = tomllib.loads(
        (_ROOT / "docs" / "sources.toml").read_text(encoding="utf-8")
    )
    keys = {entry["key"] for entry in registry["source"]}
    for help_id, contract in sorted(CONTRACTS.items()):
        if contract.source_key is not None:
            assert contract.source_key in keys, (
                f"{help_id} cites unknown source {contract.source_key!r}"
            )


def test_a_claimed_help_anchor_resolves():
    """Resolved through `openchem.help`, which already owns topic
    discovery, so there is one implementation of "what anchors exist"."""
    from openchem import help as help_docs

    known = {topic.key for topic in help_docs.topics()}
    for help_id, contract in sorted(CONTRACTS.items()):
        if contract.help_anchor is not None:
            assert contract.help_anchor in known, (
                f"{help_id} claims help anchor {contract.help_anchor!r}, which "
                "no document defines"
            )


# --- the wiring, which is the half the registry cannot prove ------------


def _descriptor(descriptor_id, name, category="physicochemical", value=1.0):
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=name,
        units="",
        category=category,
        provider="rdkit",
        molecule_uuid="mol-1",
        value=value,
        cache_state=CacheState.COMPLETED,
    )


def test_the_aggregate_stamps_the_contract_id_on_every_fact():
    """The producer's half. A registry nothing references is a document."""
    aggregate = aggregate_descriptors(
        "mol-1",
        [_descriptor("tpsa", "TPSA"), _descriptor("qed", "QED (Drug-likeness)")],
    )
    assert [f.help_id for f in aggregate.facts] == [
        "descriptor.tpsa",
        "descriptor.qed",
    ]


def test_the_CAPTION_is_what_carries_the_contract(qapp):
    """**TESTING THE REGISTRY IS NOT TESTING THE WIRING**, which this
    repository has now recorded eight times. Driven through a real
    `FactView` rendering a real aggregate, and read back off the widget with
    `help_tooltip_for` -- the same accessor the coverage walk uses, so this
    cannot pass against a tooltip set some other way.

    The CAPTION and not the value: the name is what a reader points at when
    they do not know what something is, and it carried nothing at all.
    """
    from PySide6.QtWidgets import QLabel

    from openchem.ui.widgets.fact_view import FactView
    from openchem.ui.widgets.help_tooltip import help_tooltip_for
    from tests.conftest import dispose

    view = FactView()
    try:
        aggregate = aggregate_descriptors("mol-1", [_descriptor("tpsa", "TPSA")])
        view.set_report(aggregate, "Molecular Properties", "")

        caption = next(
            label for label in view.findChildren(QLabel) if label.text() == "TPSA"
        )
        contract = help_tooltip_for(caption)
        assert contract is not None, "the caption carries no contract"
        assert contract.help_id == "descriptor.tpsa"
        assert caption.toolTip() == contract.text
    finally:
        dispose(view)


def test_a_fact_with_no_contract_falls_back_to_its_provenance(qapp):
    """A dead hover on the thing a reader points at first is worse than a
    repeated one. A calculator's own facts carry no `help_id`, and for them
    the evidence and limitations really are the whole answer."""
    from PySide6.QtWidgets import QLabel

    from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
    from openchem.ui.widgets.fact_view import FactView
    from openchem.ui.widgets.help_tooltip import help_tooltip_for
    from tests.conftest import dispose

    report = ReportResult(
        molecule_uuid="mol-1",
        report_id="r",
        name="R",
        facts=(
            Fact(
                category=FactCategory.IDENTITY,
                label="Szeged index",
                value=12,
                display_value="12",
                source="TopologyAnalysis",
                basis=Basis.DETERMINISTIC,
                limitations=("Defined for connected graphs only.",),
            ),
        ),
    )
    view = FactView()
    try:
        view.set_report(report, "Topology", "")
        caption = next(
            label
            for label in view.findChildren(QLabel)
            if label.text() == "Szeged index"
        )
        assert help_tooltip_for(caption) is None, "setup: this fact has no contract"
        assert "TopologyAnalysis" in caption.toolTip()
        assert "connected graphs" in caption.toolTip()
    finally:
        dispose(view)


def test_the_value_keeps_the_provenance_when_the_caption_takes_the_meaning(qapp):
    """The narrow half. Moving the contract onto the caption must not take
    the provenance off the value -- two different questions, and one tooltip
    holding both is the unreadable answer this split exists to avoid."""
    from PySide6.QtWidgets import QLabel

    from openchem.ui.widgets.fact_view import FactView
    from tests.conftest import dispose

    view = FactView()
    try:
        view.set_report(
            aggregate_descriptors("mol-1", [_descriptor("tpsa", "TPSA")]),
            "Molecular Properties",
            "",
        )
        value = next(
            label
            for label in view.findChildren(QLabel)
            if label.text() == "1" and label.toolTip()
        )
        assert "Source:" in value.toolTip()
        assert "Basis:" in value.toolTip()
    finally:
        dispose(view)


# --- the rule itself, which moved and nearly lost its control -----------


def test_the_placeholder_rule_REJECTS_a_placeholder():
    """**THE CONTROL FOR THE FLOOR, AND MOVING IT LOST IT.**

    `placeholder_reason` came out of `test_tooltip_coverage.py` so that this
    file and that one hold contracts to one standard. What did not come with
    it was a test that it ever says NO: both callers assert `is None`, and a
    mutation disabling the degenerate-text branch changed nothing anywhere.
    Found by running that arm and watching it survive.
    """
    from openchem.ui.widgets.help_tooltip import HelpTooltip

    degenerate = HelpTooltip(text="Options.", tier=1, help_id="probe.degenerate")
    assert placeholder_reason(degenerate) is not None

    too_short = HelpTooltip(text="Poses.", tier=2, help_id="probe.short")
    reason = placeholder_reason(too_short)
    assert reason is not None and "tier 2" in reason

    real = HelpTooltip(
        text=(
            "How many docked poses to keep, at most. More poses cost search "
            "time and are reported in score order."
        ),
        tier=2,
        help_id="probe.real",
    )
    assert placeholder_reason(real) is None


def test_the_tier_floors_are_what_the_rule_applies():
    """A floor nobody can see is a floor nobody maintains. Tier 1 has none
    on purpose -- an action plus its result is legitimately short."""
    from openchem.ui.widgets.help_tooltip import MINIMUM_LENGTH

    assert MINIMUM_LENGTH == {2: 40, 3: 80}
    assert 1 not in MINIMUM_LENGTH
