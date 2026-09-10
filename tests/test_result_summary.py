"""One canonical reader, and the contract every entry in it must meet.

A trajectory, a per-atom dataset and a fact report are not the same scientific
object; the `ScientificResult` hierarchy exists for that. What they can share
is a READING SURFACE -- which means the surface has to be written down, and it
was written down four names short of what the reader actually reads.

Guards come in pairs. "It satisfies the contract" is satisfied by a contract
that asks for nothing, so the contract's own members are asserted against what
the reader consumes; and "it is not a report" is satisfied by a type that
cannot be read at all, so both halves are here.
"""

from __future__ import annotations

import dataclasses

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import aggregate_descriptors
from openchem.domain.merged_results import is_report_shaped, merge_reports
from openchem.domain.report import (
    Basis,
    Fact,
    FactCategory,
    ReportResult,
    find_facts,
    group_facts_by_category,
)
from openchem.ui.report_format import format_report, names_itself
from openchem.ui.result_summary import ResultSummaryView, summary_of_merge

FORMATS = ("Plain text", "Markdown", "JSON", "CSV")


def _fact(label: str, **overrides) -> Fact:
    defaults = dict(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )
    defaults.update(overrides)
    return Fact(**defaults)


def _report(report_id="elemental_analysis", name="Elemental Analysis", **overrides):
    defaults = dict(
        molecule_uuid="u",
        report_id=report_id,
        name=name,
        facts=(_fact("Formula"),),
    )
    defaults.update(overrides)
    return ReportResult(**defaults)


def _aggregate():
    return aggregate_descriptors(
        "u",
        [
            DescriptorValue(
                descriptor_id="mol_wt",
                name="Molecular Weight",
                units="g/mol",
                category="physicochemical",
                provider="rdkit",
                molecule_uuid="u",
                cache_state=CacheState.COMPLETED,
                value=180.16,
            )
        ],
    )


# --- the contract, and everything that has to meet it --------------------


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_report(), id="ReportResult"),
        pytest.param(_aggregate(), id="DescriptorAggregate"),
        pytest.param(
            summary_of_merge(merge_reports([_report()]), "u"), id="ResultSummaryView"
        ),
    ],
)
def test_every_reader_entry_satisfies_the_reader_contract(entry):
    assert is_report_shaped(entry)


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_report(), id="ReportResult"),
        pytest.param(_aggregate(), id="DescriptorAggregate"),
        pytest.param(
            summary_of_merge(merge_reports([_report()]), "u"), id="ResultSummaryView"
        ),
    ],
)
@pytest.mark.parametrize("fmt", FORMATS)
def test_every_reader_entry_can_be_copied_in_every_format(entry, fmt):
    """**8 OF THESE 12 RAISED**, unhandled, out of the Copy and Export click
    paths: `report_format` dispatched on `isinstance(ReportResult)` and fell
    off the end into the ATOM branch, so the two entries that are not literally
    a `ReportResult` -- the all-results view and Molecular Properties -- died
    on `report.atom_index`.

    Measured before the fix, and the aggregate then failed three of four for a
    SECOND reason: it carried no `limitations`, which `report_format` reads
    for every format but CSV.
    """
    assert format_report(entry, fmt)


def test_the_contract_names_everything_the_reader_actually_reads():
    """**THE CONTRACT WAS FOUR NAMES AND THE READER READ NINE.** A container
    admitted by the short version passed the door and raised in a PAINT path
    instead -- which is how `DescriptorAggregate` shipped unfocusable.

    Derived from a real `ReportResult` rather than restated: every member must
    be something the shipped report has, so a name that is merely aspirational
    cannot sit in the list.
    """
    from openchem.domain.merged_results import _READER_CONTRACT

    report = _report()
    for name in _READER_CONTRACT:
        assert hasattr(report, name), f"the contract asks for {name!r} and no report has it"
    for needed in ("name", "limitations", "assumptions", "molecule_uuid", "structure_version"):
        assert needed in _READER_CONTRACT, (
            f"the reader reads {needed!r} directly; leaving it out of the "
            "contract means a container that lacks it is admitted and then "
            "raises while painting"
        )


def test_a_container_missing_one_contract_member_is_refused_at_the_door():
    """Fail closed. Refusing an entry is visible; admitting one that raises
    two frames into a paint path is not."""

    class _Partial:
        report_id = "x"
        name = "X"
        facts = ()
        molecule_uuid = "u"
        structure_version = 0
        assumptions = ()

        def by_category(self):
            return {}

        def find(self, _text):
            return ()

    assert not is_report_shaped(_Partial()), "no `limitations` -- must be refused"
    assert merge_reports([_Partial()]).reports == ()


# --- it is a VIEW, and must not be mistaken for a report -----------------


def test_a_summary_view_is_not_a_report():
    """The name's whole job. Persisting one would attribute several producers'
    facts -- or, for a single-result summary, presentation-DERIVED facts -- to
    one report."""
    view = summary_of_merge(merge_reports([_report()]), "u")
    assert not isinstance(view, ReportResult)


def test_a_summary_view_carries_no_serialisation():
    """Asserted on the type, because the danger is a later convenience method:
    a project writer that finds a `to_dict` will call it."""
    for name in ("to_dict", "from_dict"):
        assert not hasattr(ResultSummaryView, name), name


def test_a_summary_view_carries_no_calculator_identity():
    """`parameters_key` hashes calculator identity into every retained result,
    and a view acquiring one would put a thing nobody can run into the store --
    the same rule `DescriptorAggregate` is held to."""
    fields = {f.name for f in dataclasses.fields(ResultSummaryView)}
    assert "calculator_id" not in fields
    assert "parameters" not in fields


def test_the_merged_view_names_no_single_producer():
    """An empty `report_id`, deliberately: giving the all-results view one
    would make it focusable as a calculator containing everybody else's
    results."""
    view = summary_of_merge(merge_reports([_report()]), "u")
    assert view.report_id == ""
    assert is_report_shaped(view), "and it still passes the admission door"


def test_the_merged_view_passes_the_producers_facts_through_unchanged():
    """It derives nothing. `merge_reports` has already stamped each fact with
    the origin that says which report it arrived in, and this view does not
    touch them -- which is why it needs no "these facts are derived" caveat
    and a single-result summary will.

    **THE SAME OBJECTS, NOT AN EQUAL COPY.** `is` on the tuple itself is not
    the claim and cannot be: `tuple(t)` returns `t` in CPython, so an arm
    rebuilding the container passed an identity check on it. What must hold is
    that no FACT was rewritten on the way through -- a view that rebuilt them
    with a new `source` would compare equal on nothing that matters and would
    be attributing the producers' facts to itself.
    """
    merged = merge_reports([_report()])
    view = summary_of_merge(merged, "u")
    assert [f.origin for f in view.facts] == ["elemental_analysis"]
    assert all(a is b for a, b in zip(view.facts, merged.facts, strict=True))


def test_the_merged_view_carries_every_producers_chart_and_caveat():
    from openchem.domain.report import Stick, StickChartAnnotation

    chart = StickChartAnnotation(
        sticks=(Stick(1.0, 1.0),),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
        title="Isotope pattern",
    )
    a = _report(charts=(chart,), limitations=("Shared caveat",))
    b = _report("lewis_sites", "Lewis Sites", limitations=("Shared caveat", "Its own"))
    view = summary_of_merge(merge_reports([a, b]), "u")
    assert [c.title for c in view.charts] == ["Isotope pattern"]
    assert view.limitations == ("Shared caveat", "Its own"), "de-duplicated, in order"


# --- one grouping and one search, not three ------------------------------


def test_the_three_readers_group_facts_the_same_way():
    """`StructureReport`, `DescriptorAggregate` and the merged view each had
    their own copy. Three implementations of "what the reader shows" is three
    chances to disagree about it."""
    facts = (_fact("A"), _fact("B", category=FactCategory.GEOMETRY))
    report = _report(facts=facts)
    view = ResultSummaryView(facts=facts)
    assert report.by_category() == group_facts_by_category(facts)
    assert view.by_category() == group_facts_by_category(facts)
    assert _aggregate().by_category() == group_facts_by_category(_aggregate().facts)


def test_the_search_means_the_same_thing_in_every_entry():
    """**THE THREE COPIES DID NOT AGREE, AND IT IS ONE CONTROL.** Measured
    before this: a calculator's report searched label/value/evidence, the
    aggregate searched label/value only, and the merged view searched
    label/value/origin/evidence -- so Molecular Properties silently matched no
    evidence at all.

    **THE FIXTURE HAS TO GIVE EVERY ENTRY AN EVIDENCE-BEARING FACT.** The
    first version of this exercised a report and a summary view and left the
    aggregate out, so restoring its private label/value-only search survived
    the whole file -- the aggregate's own facts carry no evidence today, which
    is exactly why the divergence was invisible in the first place.
    """
    from openchem.domain.descriptor_aggregate import DescriptorAggregate

    facts = (_fact("Ring count", evidence=("aromatic perception",)),)
    entries = (
        _report(facts=facts),
        ResultSummaryView(facts=facts),
        DescriptorAggregate(molecule_uuid="u", facts=facts),
    )
    for entry in entries:
        assert [f.label for f in entry.find("aromatic")] == ["Ring count"], (
            f"{type(entry).__name__} does not search the evidence"
        )


def test_the_shared_search_matches_the_origin_a_merge_stamps():
    """"Show me everything Lewis Sites said" is a question the box can answer,
    and it must stay answerable now that one function serves every entry."""
    merged = merge_reports([_report("lewis_sites", "Lewis Sites")])
    assert [f.label for f in find_facts(merged.facts, "lewis_sites")] == ["Formula"]


def test_matching_the_origin_changes_nothing_for_a_producers_own_facts():
    """The narrow half, and what made unifying on the WIDEST search safe.
    Measured over the real registry: 0 of 164 producer facts carry an origin,
    because the merge stamps its own copies and never the report's."""
    report = _report()
    assert all(f.origin == "" for f in report.facts)
    assert report.find("elemental") == (), "an id nothing carries matches nothing"


def test_an_empty_search_returns_everything():
    facts = (_fact("A"), _fact("B"))
    assert find_facts(facts, "   ") == facts


# --- the format dispatch fails closed ------------------------------------


def test_something_that_is_no_kind_of_subject_is_refused_by_name():
    """The old default was the ATOM branch, so an unrecognised subject died on
    `report.atom_index` -- an error naming a field the reader has never heard
    of, several frames from the dispatch that could not place it."""

    class _Nothing:
        facts = ()
        limitations = ()
        assumptions = ()
        molecule_uuid = "u"
        structure_version = 0

        def by_category(self):
            return {}

    with pytest.raises(TypeError, match="_Nothing"):
        format_report(_Nothing(), "Plain text")


def test_an_atom_report_is_not_mistaken_for_a_result():
    """The narrow half of `names_itself`. `StructureReport` carries neither
    `report_id` nor `name`, so the atom family cannot answer True by accident
    -- and if it ever could, every atom report would lose its header."""
    from openchem.domain.atom_report import AtomReport

    atom = AtomReport(molecule_uuid="u", atom_index=0, symbol="C")
    assert not names_itself(atom)
    assert format_report(atom, "Plain text").startswith("Atom 1 (C)")


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_report(), id="ReportResult"),
        pytest.param(_aggregate(), id="DescriptorAggregate"),
        pytest.param(
            summary_of_merge(merge_reports([_report()]), "u"), id="ResultSummaryView"
        ),
    ],
)
def test_anything_that_names_itself_is_formatted_as_a_result(entry):
    assert names_itself(entry)
