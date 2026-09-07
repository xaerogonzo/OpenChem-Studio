"""`AlertResult` lines as facts, for results nobody has migrated.

Not a temporary shim: `AlertResult` stays in the plugin API, so a
third-party calculator will still be producing one long after the
built-in fifteen have moved.
"""

from __future__ import annotations

import ast
from pathlib import Path

from openchem.chem.report_adapter import (
    category_for,
    facts_from_alert,
    is_catalog,
    report_fields,
    report_from_alert,
    report_from_fields,
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


def test_an_explicitly_signed_value_reads_the_same_either_way():
    """THE SIGN MUST NOT DECIDE WHETHER A LINE IS A MEASUREMENT.

    `chem/dipole.py` formats its components with `f"{v:+.2f}"`, so a
    negative component arrives as `"-1.18"` and a positive one as
    `"+0.16"`. A leading-minus-only pattern accepted the first and refused
    the second, and the panel showed three parsed component rows beside
    one unparsed one -- for no reason but the sign of the number.

    BOTH SIGNS, ONE ASSERTION. Testing only the plus would pass against a
    pattern that had swapped one sign for the other rather than admitting
    both.
    """
    facts = facts_from_alert(_alert(matched=[
        "Dipole X: -1.18 Debye",
        "Dipole Y: 0.00 Debye",
        "Dipole Z: +0.16 Debye",
    ], category="charge"))

    assert [fact.label for fact in facts] == ["Dipole X", "Dipole Y", "Dipole Z"]
    assert [fact.display_value for fact in facts] == [
        "-1.18 Debye", "0.00 Debye", "+0.16 Debye",
    ]
    assert {fact.units for fact in facts} == {"Debye"}


def test_the_positive_sign_survives_into_the_value_rather_than_being_eaten():
    """The `+` is the producer's decision and is kept.

    Stripping it would make the value column disagree with every other
    line the same calculator emits, which is the alignment the `+` format
    exists for in the first place.
    """
    fact = facts_from_alert(_alert(matched=["Dipole Z: +0.16 Debye"]))[0]
    assert fact.value == "+0.16"
    assert fact.display_value.startswith("+0.16")


def test_a_positive_huckel_homo_is_a_measurement_like_its_lumo():
    """The second calculator the sign bug reached, and the worse of the two.

    In the `E = alpha + x*beta` convention a bonding HOMO is POSITIVE and
    an antibonding LUMO negative, so `chem/huckel.py` had its LUMO parsed
    and its HOMO refused on essentially every pi system -- not an edge
    case that needed an unusual molecule to reach.
    """
    facts = facts_from_alert(_alert(matched=[
        "HOMO: +1.00 beta",
        "LUMO: -1.00 beta",
    ], category="quantum"))

    assert [fact.label for fact in facts] == ["HOMO", "LUMO"]
    assert [fact.units for fact in facts] == ["beta", "beta"]


def test_a_value_list_is_labelled_without_becoming_a_number():
    """A LIST GETS ITS LABEL BACK AND MUST NOT GET A VALUE.

    Admitting `+` also admits the line `chem/huckel.py` builds by joining
    signed orbital energies, which was previously refused for its leading
    `+` rather than for being a list. Getting the label back is the
    improvement; the thing to hold still is that it must not read as one
    scalar.

    The comma inside `value` is what does that: `result_reduction`
    declines a value it cannot float, so the batch table gets a text
    column rather than a numeric one claiming a ten-orbital spectrum is
    2.0. Tightening the pattern to a bare number was measured and breaks
    both halves -- it yields 2.0 AND inserts a stray space before the
    comma. `display_value` here must reconstruct the tail exactly.
    """
    from openchem.chem.result_reduction import _as_float

    line = "Orbital energies (beta): +2.00, +1.00, +1.00, -1.00, -1.00, -2.00"
    fact = facts_from_alert(_alert(matched=[line], category="quantum"))[0]

    assert fact.label == "Orbital energies (beta)"
    assert fact.display_value == "+2.00, +1.00, +1.00, -1.00, -1.00, -2.00"
    assert _as_float(fact.value) is None, "a list must not reduce to a number"


def test_a_unit_attached_with_no_space_still_splits():
    """THE GUARD ON THE OBVIOUS WRONG FIX.

    Keeping value lists out by requiring whitespace after the number --
    a `(?=\\s|$)` boundary -- is the first thing anyone reaches for, and
    the sweep over every calculator's real output says it refuses 31
    lines: elemental analysis and percent buried volume both attach their
    unit directly to the digits. Without this guard that mutation looks
    free.
    """
    facts = facts_from_alert(_alert(matched=[
        "C: 23.79%",
        "Percent buried volume: 13.30%",
    ]))

    assert [fact.label for fact in facts] == ["C", "Percent buried volume"]
    assert [fact.units for fact in facts] == ["%", "%"]
    assert [fact.display_value for fact in facts] == ["23.79 %", "13.30 %"]


def test_report_fields_splits_a_signed_line_the_same_way():
    """The entry point every migrated calculator actually calls.

    `chem/dipole.py` reaches the parser through `report_fields`, not
    through `facts_from_alert`, so the guard is worth having at both
    levels -- a fix applied to one path only would leave this green and
    the application broken.
    """
    fields = report_fields(
        alert_id="dipole_moment",
        name="Dipole Moment",
        molecule_uuid="m1",
        matched=["Dipole Z: +0.16 Debye"],
        category="charge",
    )

    assert [fact.label for fact in fields["facts"]] == ["Dipole Z"]
    assert fields["facts"][0].display_value == "+0.16 Debye"


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


_SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def test_report_from_fields_wraps_report_fields_into_a_result():
    report = report_from_fields(
        alert_id="dipole_moment",
        name="Dipole Moment",
        molecule_uuid="m1",
        matched=["Magnitude: 1.85 D"],
        category="electronic",
    )

    assert report.report_id == "dipole_moment"
    assert report.name == "Dipole Moment"
    assert report.molecule_uuid == "m1"
    assert len(report.facts) == 1
    assert report.facts[0].value == "1.85"
    assert report.facts[0].units == "D"


def test_nothing_keeps_a_private_copy_of_the_shared_wrapper():
    """It had thirteen byte-identical copies, and that is what this refuses.

    Every one was `def _report(**fields) -> ReportResult` returning
    `ReportResult(**report_fields(**fields))`, under a module-private name,
    with an identical eleven-line docstring -- `ast_isomorphic` at
    similarity 1.0, 83 body tokens, in `huckel`, `lewis`, `lewis_adduct`,
    `electronic_properties`, `elemental_analysis`, `mpo_scores`,
    `bbb_stereo`, `interaction_analysis`, `dipole`, `surface_analysis`,
    `naming_providers`, `steric` and `topology_analysis`.

    Thirteen copies of a docstring is thirteen places for one contract to
    be described differently after the next edit, which is the drift this
    project has already paid for four times over (`is_stripped_residue`,
    `filter_altlocs`, `is_symmetry_generated`, `normalise_element_symbols`).

    Asked of the SOURCE rather than of behaviour, because thirteen correct
    copies agree on every input -- only their existence differs, so no
    behavioural test can see them. Same reason
    `test_the_screen_and_the_panel_ask_THE_SAME_FUNCTION` is a source check.
    """
    offenders = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [n for n in node.body if not _is_docstring(n)]
            if len(body) != 1 or not isinstance(body[0], ast.Return):
                continue
            call = body[0].value
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                continue
            if call.func.id != "ReportResult":
                continue
            inner = [
                kw.value.func.id
                for kw in call.keywords
                if kw.arg is None
                and isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name)
            ]
            if "report_fields" in inner and path.name != "report_adapter.py":
                offenders.append(f"{path.relative_to(_SRC)}::{node.name}")

    assert not offenders, (
        "these re-implement report_adapter.report_from_fields: " + ", ".join(offenders)
    )


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(
        node.value.value, str
    )


def test_the_shared_wrapper_still_documents_its_contract():
    """The docstring is the contract, and moving code is how one gets lost.

    Deliberately NOT byte-equality against a pinned string: this project
    has a recorded pattern of guards that pin exact prose being weakened or
    deleted the first time somebody improves the wording, and the floor
    here is "the contract survived", not "nobody may edit the sentence".
    The validator owns the shape; a reviewer owns the meaning -- the same
    line `help_tooltip.py` draws.

    The three claims that must survive any rewording are that the keyword
    names are unchanged, that `report_fields` does the translation, and
    that a calculator wanting units/evidence/limitations builds `Fact`s
    directly instead.
    """
    doc = report_from_fields.__doc__
    assert doc is not None and doc.strip()
    assert "report_fields" in doc
    assert "keyword" in doc.lower()
    assert "Fact" in doc
    for keyword in ("alert_id", "name", "matched", "category"):
        assert keyword in doc, f"the docstring stopped naming the {keyword} keyword"
