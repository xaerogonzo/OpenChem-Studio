"""The merge that keeps every producer-owned channel.

`merged_report` proved that folding facts makes batch render like
Properties. It is not evidence that ONE anonymous report can carry several
producers' charts, spatial annotations, provenance and stale state -- a
`ReportResult` has one `report_id`, one `provenance` and one
`structure_version`, and it silently dropped `spatial` entirely.
"""

from __future__ import annotations

from openchem.domain.merged_results import MergedResults, merge_reports
from openchem.domain.report import (
    ArrowAnnotation,
    Basis,
    Fact,
    FactCategory,
    ReportResult,
    Stick,
    StickChartAnnotation,
)
from openchem.domain.scientific_result import PerAtomDataset


def _fact(label: str, source: str = "RDKit") -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source=source,
        basis=Basis.DETERMINISTIC,
    )


def _chart(title: str) -> StickChartAnnotation:
    return StickChartAnnotation(
        sticks=(Stick(1.0, 1.0),),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
        title=title,
    )


def _arrow(label: str) -> ArrowAnnotation:
    return ArrowAnnotation(anchor=(0.0, 0.0, 0.0), vector=(1.0, 0.0, 0.0), units="D", label=label)


def _report(report_id, name, facts, charts=(), spatial=(), version=0, **rest) -> ReportResult:
    return ReportResult(
        molecule_uuid="u",
        report_id=report_id,
        name=name,
        facts=tuple(facts),
        charts=tuple(charts),
        spatial=tuple(spatial),
        structure_version=version,
        **rest,
    )


def _two_reports():
    a = _report(
        "elemental_analysis", "Elemental Analysis", [_fact("Formula", "RDKit")],
        charts=[_chart("Isotope pattern")],
    )
    b = _report(
        "lewis_sites", "Lewis Sites", [_fact("Donor sites", "LewisAnalysis")],
        charts=[_chart("Sites")],
    )
    return a, b


# --- provenance ----------------------------------------------------------


def test_source_survives_the_merge_and_origin_is_added_beside_it():
    """**THE TWO ARE INDEPENDENT DIMENSIONS.** `source` is where the VALUE
    came from -- a fact can honestly be sourced "RDKit" -- and `origin` is
    which calculator run it arrived in. Overwriting the first with the
    second destroys real provenance in order to record different
    provenance."""
    a, b = _two_reports()
    merged = merge_reports([a, b])
    by_label = {fact.label: fact for fact in merged.facts}
    assert by_label["Formula"].source == "RDKit"
    assert by_label["Formula"].origin == "elemental_analysis"
    assert by_label["Donor sites"].source == "LewisAnalysis"
    assert by_label["Donor sites"].origin == "lewis_sites"


def test_an_unmerged_report_carries_no_origin():
    """Defaulted to empty, so every existing producer is untouched."""
    assert _fact("Formula").origin == ""


def test_merging_a_merge_changes_nothing():
    """A fact that already carries an origin keeps it, so the operation is
    idempotent and a nested merge cannot relabel somebody else's fact."""
    a, b = _two_reports()
    once = merge_reports([a, b])
    twice = merge_reports([a, b])
    assert [f.origin for f in once.facts] == [f.origin for f in twice.facts]
    already = merge_reports([_report("x", "X", [_fact("F")])]).facts[0]
    assert already.origin == "x"
    kept = merge_reports([_report("y", "Y", [already])]).facts[0]
    assert kept.origin == "x"


# --- the channels --------------------------------------------------------


def test_each_chart_keeps_the_id_of_the_report_that_owns_it():
    """Once several calculators can contribute one, "the first chart" and
    "the last chart" stop being answers to anything."""
    a, b = _two_reports()
    merged = merge_reports([a, b])
    assert merged.charts() == (
        ("elemental_analysis", a.charts[0]),
        ("lewis_sites", b.charts[0]),
    )


def test_focusing_one_report_never_hands_back_anothers_chart():
    a, b = _two_reports()
    merged = merge_reports([a, b])
    assert merged.charts_for("elemental_analysis") == (a.charts[0],)
    assert merged.charts_for("lewis_sites") == (b.charts[0],)
    assert merged.charts_for("nothing_by_that_name") == ()


def test_spatial_annotations_survive_the_merge_with_their_owners():
    """`merged_report` dropped these on the floor -- measured before this
    existed. A view that offers a 3D model for one result among six has to
    know which one."""
    a = _report("dipole", "Dipole Moment", [_fact("Dipole")], spatial=[_arrow("mu")])
    b = _report("lewis_sites", "Lewis Sites", [_fact("Donor sites")])
    merged = merge_reports([a, b])
    assert merged.spatial() == (("dipole", a.spatial[0]),)
    assert merged.spatial_for("dipole") == (a.spatial[0],)
    assert merged.spatial_for("lewis_sites") == ()


def test_the_original_reports_are_kept_whole():
    """Charts, spatial, provenance and staleness are read OFF these rather
    than copied into a parallel structure -- one representation, so they
    cannot drift."""
    a, b = _two_reports()
    merged = merge_reports([a, b])
    assert merged.reports == (a, b)
    assert merged.report_for("lewis_sites") is b
    assert merged.report_for("absent") is None


def test_a_report_name_is_looked_up_rather_than_derived_from_its_id():
    """A view must never prettify `elemental_analysis` into a display name;
    it asks the container, which asks the report."""
    a, _b = _two_reports()
    merged = merge_reports([a])
    assert merged.name_for("elemental_analysis") == "Elemental Analysis"
    # The fallback is the id, which is at least true where a guess is not.
    assert merged.name_for("never_seen") == "never_seen"


# --- what does not contribute -------------------------------------------


def test_only_results_that_are_reports_contribute():
    """A per-atom dataset has no facts and is reached through its own
    inspector. Without this rule a factless result could smuggle a chart in
    through a door the facts are refused at."""
    dataset = PerAtomDataset(
        property_id="gasteiger_charge",
        name="Partial Charge",
        units="e",
        method="rdkit",
        molecule_uuid="u",
        values={0: 0.1},
    )
    a, _b = _two_reports()
    merged = merge_reports([a, dataset])
    assert merged.reports == (a,)
    assert len(merged.charts()) == 1


def test_a_report_with_no_facts_contributes_nothing_at_all():
    empty = _report("empty", "Empty", [], charts=[_chart("orphan")])
    merged = merge_reports([empty])
    assert merged.reports == ()
    assert merged.charts() == ()
    assert not merged


# --- staleness -----------------------------------------------------------


def test_two_reports_at_different_versions_are_told_apart_and_neither_is_dropped():
    """A stale result is still a record of what was computed. Silently
    serving one and silently blanking one are the two ways this goes wrong,
    and they look identical from outside."""
    old = _report("lewis_sites", "Lewis Sites", [_fact("Donor sites")], version=1)
    new = _report("elemental_analysis", "Elemental Analysis", [_fact("Formula")], version=2)
    merged = merge_reports([old, new], structure_version=2)
    assert merged.is_stale(old)
    assert not merged.is_stale(new)
    assert merged.stale_report_ids() == ("lewis_sites",)
    assert len(merged.reports) == 2, "neither is discarded"
    assert len(merged.facts) == 2


def test_an_unstamped_report_reads_stale_once_the_structure_has_moved():
    """The honest answer for "this one does not say when it was computed",
    and the reason every calculator result is stamped in one place rather
    than left at the default."""
    unstamped = _report("legacy", "Legacy", [_fact("F")], version=0)
    assert merge_reports([unstamped], structure_version=3).is_stale(unstamped)
    assert not merge_reports([unstamped], structure_version=0).is_stale(unstamped)


# --- the other aggregates ------------------------------------------------


def test_limitations_are_de_duplicated_in_order():
    """Several calculators legitimately carry the same caveat, and printing
    it five times buries the four that differ."""
    shared = "Computed on the drawn structure."
    a = _report("a", "A", [_fact("F1")], limitations=(shared, "Only a"))
    b = _report("b", "B", [_fact("F2")], limitations=("Only b", shared))
    merged = merge_reports([a, b])
    assert merged.limitations() == (shared, "Only a", "Only b")


def test_assumptions_are_de_duplicated_the_same_way():
    a = _report("a", "A", [_fact("F1")], assumptions=("Same",))
    b = _report("b", "B", [_fact("F2")], assumptions=("Same", "Different"))
    assert merge_reports([a, b]).assumptions() == ("Same", "Different")


def test_an_empty_merge_is_falsey_and_holds_nothing():
    merged = merge_reports([])
    assert isinstance(merged, MergedResults)
    assert not merged
    assert merged.facts == ()


# --- the stamp, on the path every calculator result takes ----------------


def test_a_calculator_result_records_which_structure_it_describes(qapp):
    """`StructureReport.structure_version` has existed since the report
    types were written -- "what makes a cached report safe to reuse" -- and
    was 0 on EVERY calculator result, because `report_from_fields` never
    set it. Measured before this was wired: the field was there, the
    plumbing was not.

    Stamped once, on the way out of a calculation, for the same reason the
    geometry provenance is: a calculator is handed a molecule and has no
    idea which revision of it that was.
    """
    from openchem.services.descriptor_service import _with_structure_version

    report = _report("elemental_analysis", "Elemental Analysis", [_fact("Formula")])
    assert report.structure_version == 0
    stamped = _with_structure_version(report, lambda _uuid: 7)
    assert stamped.structure_version == 7


def test_a_calculator_that_set_its_own_version_is_left_alone():
    """It knows what it computed; this layer only knows what the counter
    said when the result came back. The same precedence
    `_with_geometry_provenance` uses."""
    from openchem.services.descriptor_service import _with_structure_version

    report = _report("x", "X", [_fact("F")], version=3)
    assert _with_structure_version(report, lambda _uuid: 9).structure_version == 3


def test_a_result_with_no_version_field_is_returned_untouched():
    """A per-atom dataset has no such field and no meaning for one."""
    from openchem.services.descriptor_service import _with_structure_version

    dataset = PerAtomDataset(
        property_id="gasteiger_charge",
        name="Partial Charge",
        units="e",
        method="rdkit",
        molecule_uuid="u",
        values={0: 0.1},
    )
    assert _with_structure_version(dataset, lambda _uuid: 4) is dataset


def test_a_counter_that_raises_never_costs_the_result():
    """Recording where a number came from must not be able to lose the
    number."""
    from openchem.services.descriptor_service import _with_structure_version

    def broken(_uuid):
        raise RuntimeError("no checker")

    report = _report("x", "X", [_fact("F")])
    assert _with_structure_version(report, broken) is report
    assert _with_structure_version(report, None) is report


def test_the_wiring_reaches_a_real_service_container(qapp):
    """A stamping helper nothing calls is a helper. This asserts the
    accessor is actually handed over where the container is built."""
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    assert (
        services.descriptor_service._structure_version_of
        == services.structure_check_service.current_version
    )
