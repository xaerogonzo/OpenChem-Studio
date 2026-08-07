"""`AlertResult` lines as facts, for results nobody has migrated.

Not a temporary shim: `AlertResult` stays in the plugin API, so a
third-party calculator will still be producing one long after the
built-in fifteen have moved.
"""

from __future__ import annotations

from openchem.chem.report_adapter import (
    category_for,
    facts_from_alert,
    is_catalog,
    report_from_alert,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import FactCategory
from openchem.domain.scientific_result import AlertResult
from openchem.domain.structure_issue import Basis, Severity


def _alert(**overrides) -> AlertResult:
    defaults = dict(
        alert_id="geometry_analysis",
        name="Geometry",
        molecule_uuid="m1",
        matched=[],
        category="geometry",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
    defaults.update(overrides)
    return AlertResult(**defaults)


def test_a_measurement_line_becomes_a_labelled_fact_with_units():
    """The shape most report lines already have. Recovering the label and
    the units is what lets a migrated and an unmigrated calculator sit in
    the same list without looking different."""
    facts = facts_from_alert(_alert(matched=["Max radius (from centroid): 2.35 A"]))

    assert len(facts) == 1
    assert facts[0].label == "Max radius (from centroid)"
    assert facts[0].display_value == "2.35 A"
    assert facts[0].units == "A"


def test_a_line_with_no_units_still_splits():
    facts = facts_from_alert(_alert(matched=["Atom count: 4"]))
    assert facts[0].label == "Atom count"
    assert facts[0].display_value == "4"
    assert facts[0].units == ""


def test_prose_is_left_whole_rather_than_split_at_its_colon():
    """THE CONSERVATIVE HALF, and the reason the pattern demands a number.

    Splitting every `": "` would turn a limitation into a fact labelled
    "Note", and a caveat dressed up as a measurement is worse than an
    unsplit line -- this project ships caveats precisely so they are read.
    """
    line = "Note: simple Huckel treats every pi centre as an identical carbon"
    facts = facts_from_alert(_alert(matched=[line]))

    assert len(facts) == 1
    assert facts[0].display_value == line
    assert facts[0].label == "Geometry", "an unsplittable line is labelled by its source"


def test_a_negative_or_exponent_value_still_reads_as_a_measurement():
    facts = facts_from_alert(_alert(matched=[
        "Total pi energy: -8.0000 beta",
        "Exact mass: 4.3005814e1",
    ]))
    assert facts[0].display_value == "-8.0000 beta"
    assert facts[1].label == "Exact mass"


def test_every_fact_says_it_is_heuristic():
    """Honest rather than pessimistic: the producer did not state a basis
    and this cannot know one. A migrated calculator states its own, which
    is one of the concrete things the migration buys."""
    facts = facts_from_alert(_alert(matched=["Atom count: 4", "Some prose here"]))
    assert all(fact.basis is Basis.HEURISTIC for fact in facts)


def test_the_category_maps_onto_the_fact_vocabulary():
    """`alert.category` is free text chosen by the producer; a `Fact` needs
    one of nine values."""
    assert category_for("geometry") is FactCategory.GEOMETRY
    assert category_for("charge") is FactCategory.ELECTRONIC
    assert category_for("nmr") is FactCategory.SPECTROSCOPY


def test_an_unknown_category_is_filed_rather_than_dropped():
    """A fact under the wrong heading is recoverable; a missing one is
    not. So an unrecognised category becomes STRUCTURE."""
    assert category_for("something_a_plugin_invented") is FactCategory.STRUCTURE


def test_a_failed_alert_becomes_a_report_that_still_carries_its_reason():
    """The whole point of the Phase 0 fix, preserved through the adapter:
    geometry with no conformer must not render as an empty success."""
    report = report_from_alert(_alert(
        matched=[],
        cache_state=CacheState.FAILED,
        error="This calculation needs a 3D conformer.",
    ))

    assert report.cache_state is CacheState.FAILED
    assert "3D conformer" in report.error
    assert report.facts == ()


def test_the_report_keeps_the_identity_the_panel_files_it_under():
    report = report_from_alert(_alert(matched=["Atom count: 4"]))
    assert report.report_id == "geometry_analysis"
    assert report.name == "Geometry"
    assert report.category == "geometry"
    assert report.molecule_uuid == "m1"


def test_a_catalog_is_told_apart_from_a_report_by_its_declared_severity():
    """Guessing from the id would be a heuristic; the producer knows.
    Counted when severity was introduced: 5 of 25 alert_ids are catalogs."""
    assert is_catalog(_alert(alert_id="pains", severity=Severity.WARNING))
    assert not is_catalog(_alert(alert_id="elemental_analysis"))
