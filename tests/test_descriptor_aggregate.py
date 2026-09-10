"""The 41 auto-descriptors as one reader entry, with their lifecycles intact.

The obvious bridge -- publish them as a single `ReportResult` -- gives forty-one
descriptors ONE `cache_state`, one `error` and one `inapplicable` flag between
them. They genuinely differ: with no 3D conformer the ten shape descriptors
fail while the other thirty-one succeed. These guards pin that the grouping is
a container rather than a conversion.

Guards come in pairs. "Keeps everything" is satisfied by a container that
groups nothing, and "groups them" is satisfied by one that flattens -- so both
halves are asserted.
"""

from __future__ import annotations

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import (
    DESCRIPTOR_AGGREGATE_ID,
    DETERMINISTIC_DESCRIPTORS,
    DescriptorAggregate,
    _display,
    aggregate_descriptors,
)
from openchem.domain.merged_results import is_report_shaped, merge_reports
from openchem.domain.report import Basis, FactCategory


def _descriptor(descriptor_id, **kwargs) -> DescriptorValue:
    defaults = dict(
        descriptor_id=descriptor_id,
        name=descriptor_id.replace("_", " ").title(),
        units="",
        category="physicochemical",
        provider="rdkit",
        molecule_uuid="u",
        cache_state=CacheState.COMPLETED,
    )
    defaults.update(kwargs)
    return DescriptorValue(**defaults)


def _mixed() -> DescriptorAggregate:
    """The state a single flag cannot express: some ok, one failed, one
    inapplicable. This is the shape a flat 2D drawing really produces."""
    return aggregate_descriptors(
        "u",
        [
            _descriptor("mol_wt", name="Molecular Weight", units="g/mol", value=180.16),
            _descriptor("egan_pass", name="Egan Filter", category="medicinal_chemistry", value=True),
            _descriptor(
                "spherocity_index",
                name="Spherocity Index",
                category="shape",
                cache_state=CacheState.FAILED,
                error="Needs a real 3D conformer - generate one first",
                error_summary="Needs a 3D conformer",
            ),
            _descriptor(
                "joback_tb",
                name="Boiling Point",
                cache_state=CacheState.FAILED,
                error="No Joback group for a ring tertiary amine",
                inapplicable=True,
            ),
        ],
        structure_version=3,
    )


# --- the lifecycle survives ----------------------------------------------


def test_each_descriptor_keeps_its_own_state():
    """The whole reason this is a container. One `cache_state` between forty-one
    descriptors cannot say that three failed and thirty-eight did not."""
    aggregate = _mixed()
    states = {d.descriptor_id: d.cache_state for d in aggregate.descriptors}
    assert states["mol_wt"] is CacheState.COMPLETED
    assert states["spherocity_index"] is CacheState.FAILED
    assert {d.descriptor_id for d in aggregate.failed()} == {"spherocity_index", "joback_tb"}


def test_a_refusal_is_kept_apart_from_a_fault():
    """**A REFUSAL IS NOT A FAULT**, and the existing `inapplicable` field is
    what separates them rather than a second vocabulary. Joback has no group
    for a ring tertiary amine -- correct, permanent, and not something the
    user can fix; painting it the same red as a crash is what made two working
    calculators read as broken."""
    aggregate = _mixed()
    assert {d.descriptor_id for d in aggregate.inapplicable()} == {"joback_tb"}
    # And it is in `failed()` too, because it DID fail -- the two are
    # overlapping questions, not a partition.
    assert "joback_tb" in {d.descriptor_id for d in aggregate.failed()}


def test_the_originals_are_reachable_by_id():
    aggregate = _mixed()
    assert aggregate.descriptor_for("mol_wt").value == pytest.approx(180.16)
    assert aggregate.descriptor_for("nothing_here") is None


def test_a_failed_descriptor_still_gets_a_fact():
    """It must not vanish from the flat view. A descriptor that failed is
    exactly the row a reader needs to see -- the same rule `merge_reports`
    now applies to factless reports."""
    facts = {f.label: f for f in _mixed().facts}
    assert "Spherocity Index" in facts
    assert facts["Spherocity Index"].display_value
    assert facts["Spherocity Index"].limitations, "the reason must travel with it"


def test_the_cell_and_the_reason_are_different_strings():
    """`describe_failure` owns that split and this does not re-decide it. The
    cell is short enough for a row; the full sentence -- the half that says
    what to press -- goes to `limitations`."""
    fact = {f.label: f for f in _mixed().facts}["Spherocity Index"]
    assert fact.display_value == "Needs a 3D conformer"
    assert "generate one first" in fact.limitations[0]
    assert fact.display_value not in fact.limitations


# --- it is a reader entry, not a calculator ------------------------------


def test_the_aggregate_satisfies_the_reader_contract():
    """So it passes through the SAME admission door as a report rather than a
    side one -- `is_report_shaped` is the gate `merge_reports` uses."""
    assert is_report_shaped(_mixed())


def test_the_aggregate_is_admitted_by_the_merge():
    merged = merge_reports([_mixed()], structure_version=3)
    assert [r.report_id for r in merged.reports] == [DESCRIPTOR_AGGREGATE_ID]
    assert merged.facts, "its facts must reach the flattened view"


def test_the_report_id_cannot_be_overridden_per_instance():
    """A read-only property rather than a field with a default. An aggregate
    wearing a calculator's id would be focusable AS that calculator while
    containing none of its results."""
    aggregate = _mixed()
    assert aggregate.report_id == DESCRIPTOR_AGGREGATE_ID
    with pytest.raises(AttributeError):
        aggregate.report_id = "mass_spectrum"


def test_the_aggregate_id_is_not_a_registered_calculator():
    """**IT IS A PROJECTION, NOT A CALCULATOR.** It is never offered as
    something to run and never participates in a cache key. A collision with a
    real `calculator_id` would make it both."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registered = {d.calculator_id for d in CALCULATOR_DEFINITIONS}
    assert registered, "fixture is degenerate: no calculators found"
    assert DESCRIPTOR_AGGREGATE_ID not in registered


def test_the_aggregate_carries_no_calculator_identity():
    """Asserted on the type, because the danger is a later convenience field.
    `parameters_key` hashes calculator identity into every retained result, and
    a projection acquiring one would put a thing nobody can run into the
    store."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(DescriptorAggregate)}
    assert "calculator_id" not in fields
    assert "parameters" not in fields


# --- the flat view -------------------------------------------------------


def test_only_this_molecules_descriptors_are_folded_in():
    """The panel holds values for whatever it last computed. A stale one from
    a previous selection would appear under the current molecule's name with
    nothing saying otherwise."""
    aggregate = aggregate_descriptors(
        "u",
        [_descriptor("mol_wt", value=1.0), _descriptor("tpsa", molecule_uuid="OTHER", value=2.0)],
    )
    assert [d.descriptor_id for d in aggregate.descriptors] == ["mol_wt"]


def test_units_stay_in_their_own_field_rather_than_the_label():
    """`Fact.units` belongs to `value`, and `value_with_units` composes them.
    Folding them into the label is what made `report_adapter`'s 223 facts
    export "C: 60.00 % %"."""
    fact = {f.label: f for f in _mixed().facts}["Molecular Weight"]
    assert fact.units == "g/mol"
    assert "g/mol" not in fact.label
    assert "g/mol" not in fact.display_value
    assert fact.value_with_units == "180.2 g/mol"


def test_facts_are_grouped_by_fact_category_not_calculator_category():
    """The two vocabularies stay distinct -- `category_for` bridges them, and
    it is the ONE implementation of that bridge."""
    grouped = _mixed().by_category()
    assert grouped[FactCategory.IDENTITY], "physicochemical maps to IDENTITY"
    assert grouped[FactCategory.GEOMETRY], "shape maps to GEOMETRY"
    assert grouped[FactCategory.STRUCTURE], "medicinal_chemistry maps to STRUCTURE"


def test_the_search_matches_labels_and_values():
    aggregate = _mixed()
    assert [f.label for f in aggregate.find("egan")] == ["Egan Filter"]
    assert len(aggregate.find("")) == len(aggregate.facts)


# --- basis ---------------------------------------------------------------


def test_an_exact_quantity_is_deterministic_and_a_fitted_one_is_not():
    """`Basis`' own line: DETERMINISTIC is "it is right, or the periodic table
    is wrong"; HEURISTIC "depends on a threshold somebody chose"."""
    facts = {f.label: f for f in _mixed().facts}
    assert facts["Molecular Weight"].basis is Basis.DETERMINISTIC
    # A rule filter's thresholds are literally the docstring's example.
    assert facts["Egan Filter"].basis is Basis.HEURISTIC


def test_the_deterministic_set_errs_towards_understating():
    """The narrow half, and the one that matters.

    Mislabelling an exact count as judgement understates it; labelling a
    FITTED model deterministic would OVERSTATE a claim, which is the failure
    this project spends its time removing. So the set is conservative, and no
    model or rule filter may be in it.
    """
    must_not_be_deterministic = {
        "qed", "sa_score", "np_likeness", "esol_logs", "mol_logp",
        "molar_refractivity", "labute_asa", "bbb_permeant",
        "lipinski_pass", "veber_pass", "ghose_pass", "egan_pass",
        "pfizer_375_pass", "gsk_400_pass", "rule_of_three_pass",
    }
    leaked = must_not_be_deterministic & DETERMINISTIC_DESCRIPTORS
    assert not leaked, f"fitted models/rules claimed as deterministic: {sorted(leaked)}"


def test_every_deterministic_descriptor_is_a_real_one():
    """A set naming ids that do not exist would look like coverage and be
    nothing. Derived from the shipped spec tables."""
    from openchem.chem.descriptor_providers import _DESCRIPTOR_SPECS, _SHAPE_DESCRIPTOR_SPECS

    known = {spec[0] for spec in _DESCRIPTOR_SPECS} | {spec[0] for spec in _SHAPE_DESCRIPTOR_SPECS}
    assert known, "fixture is degenerate: no descriptor specs found"
    unknown = DETERMINISTIC_DESCRIPTORS - known
    assert not unknown, f"the deterministic set names descriptors that do not exist: {sorted(unknown)}"


# --- the two renderings agree --------------------------------------------


@pytest.mark.parametrize(
    "value",
    [180.16, 0.0, -3.335, True, False, None, "C15H21NO2", 42],
)
def test_the_two_renderings_of_a_descriptor_value_agree(value):
    """**TWO IMPLEMENTATIONS OF ONE QUESTION, DELIBERATELY**, so this asserts
    they agree rather than trusting a comment.

    `PropertyPanel._format_value` adds a status GLYPH and a Qt stylesheet,
    which `domain/` cannot hold, so they are not one function. What they must
    never disagree on is the plain text -- a descriptor showing 247.3 in the
    panel and 247.34 in the reader is one value with two renderings.
    """
    from openchem.ui.panels.property_panel import _format_value, _without_glyphs

    panel_text, _style = _format_value(value)
    aggregate_text, _limitations = _display(_descriptor("x", value=value))
    assert aggregate_text == _without_glyphs(panel_text)
