"""The HOSE-code shift index.

Built here from a small synthetic SDF written in nmrshiftdb2's real
property format, so the whole pipeline -- parse, index, look up, predict
-- is exercised without needing the 158 MB distribution. The format
itself was confirmed against the real file; these tests pin what the code
does with it.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.nmr_database import (
    MIN_MATCHES,
    ShiftPrediction,
    build_index,
    connect,
    create_schema,
    is_populated,
    lookup,
    predict_spectrum,
)
from openchem.chem.nmr_database import _parse_assignments


def _sdf_record(smiles: str, properties: dict[str, str]) -> str:
    mol = Chem.MolFromSmiles(smiles)
    block = Chem.MolToMolBlock(mol)
    lines = [block]
    for key, value in properties.items():
        lines.append(f"> <{key}>\n{value}\n")
    lines.append("$$$$\n")
    return "\n".join(lines)


def _write_sdf(path, records: list[tuple[str, dict[str, str]]]):
    path.write_text("".join(_sdf_record(s, p) for s, p in records), encoding="utf-8")
    return path


# --- Parsing the real format ---------------------------------------------


def test_the_real_property_format_parses():
    """Verbatim from the distribution."""
    raw = "17.6;0.0Q;10|18.3;0.0T;0|22.6;0.0Q;12|"

    assert _parse_assignments(raw, 20) == [(10, 17.6), (0, 18.3), (12, 22.6)]


def test_repeated_atom_indices_are_all_kept():
    """Three protons on one carbon, verbatim from a real 1H record. A
    dict would have kept 1.42 and silently discarded the other two."""
    raw = "0.99;0.0;14|1.15;0.0;14|1.42;0.0;14|"

    assert _parse_assignments(raw, 20) == [(14, 0.99), (14, 1.15), (14, 1.42)]


def test_an_index_outside_the_molecule_is_rejected_not_clamped():
    """Guessing would attach a real measurement to the wrong atom, and
    nothing downstream could detect it."""
    assert _parse_assignments("10.0;0.0;99|20.0;0.0;1|", 3) == [(1, 20.0)]


def test_malformed_entries_are_skipped():
    assert _parse_assignments("nonsense|10.0;0.0;1|;;|", 5) == [(1, 10.0)]


# --- Building and looking up ---------------------------------------------


def _benzene_records(count: int, shift: float) -> list[tuple[str, dict[str, str]]]:
    """`count` benzenes, every carbon assigned the same shift."""
    entries = "|".join(f"{shift};0.0D;{i}" for i in range(6))
    return [("c1ccccc1", {"Spectrum 13C 0": entries + "|"}) for _ in range(count)]


def test_building_an_index_aggregates_matching_environments(tmp_path):
    sdf = _write_sdf(tmp_path / "in.sd", _benzene_records(2, 128.4))
    database = tmp_path / "index.sqlite"

    stats = build_index(sdf, database)

    assert stats.molecules == 2
    assert stats.measurements == 12  # 6 carbons x 2 molecules
    assert is_populated(database)


def test_a_looked_up_shift_is_the_mean_of_its_measurements(tmp_path):
    sdf = _write_sdf(
        tmp_path / "in.sd", _benzene_records(2, 128.0) + _benzene_records(2, 129.0)
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database)

    connection = connect(database)
    try:
        from openchem.chem.hose_codes import hose_codes

        mol = Chem.MolFromSmiles("c1ccccc1")
        prediction = lookup(connection, hose_codes(mol, 0, 4), "C", 4)
    finally:
        connection.close()

    assert prediction is not None
    assert prediction.shift == pytest.approx(128.5)
    assert prediction.match_count == 24
    assert prediction.spread == pytest.approx(0.5, abs=0.05)


def test_an_environment_with_too_few_measurements_is_not_reported(tmp_path):
    """One atom in one molecule is an anecdote. Reporting it as a
    prediction would look identical to a well-supported one."""
    sdf = _write_sdf(tmp_path / "in.sd", [("CCO", {"Spectrum 13C 0": "18.0;0.0Q;0|"})])
    database = tmp_path / "index.sqlite"
    build_index(sdf, database)

    connection = connect(database)
    try:
        from openchem.chem.hose_codes import hose_codes

        prediction = lookup(connection, hose_codes(Chem.MolFromSmiles("CCO"), 0, 4), "C", 4)
    finally:
        connection.close()

    assert prediction is None


def test_lookup_widens_the_sphere_when_the_specific_one_is_unsupported(tmp_path):
    """The fallback that makes the index usable: an unseen deep
    environment should still predict from the shallower one it shares
    with the database, rather than returning nothing."""
    connection = connect(tmp_path / "index.sqlite")
    try:
        create_schema(connection)
        # Only the 2-sphere code is populated.
        from openchem.chem.hose_codes import hose_code

        mol = Chem.MolFromSmiles("CCO")
        connection.execute(
            "INSERT INTO shift_environments VALUES (?, ?, ?, ?, ?, ?)",
            (hose_code(mol, 0, 2), 2, "C", 40, 18.2, 0.4),
        )
        connection.commit()

        from openchem.chem.hose_codes import hose_codes

        prediction = lookup(connection, hose_codes(mol, 0, 4), "C", 4)
    finally:
        connection.close()

    assert prediction is not None
    assert prediction.spheres == 2
    assert prediction.shift == pytest.approx(18.2)


# --- The quality rating ---------------------------------------------------


def test_quality_is_earned_from_the_evidence():
    """The first prediction-quality rating in this project that is
    computed rather than asserted -- it exists only because there are now
    real measurements to disagree with each other."""
    plenty_and_tight = ShiftPrediction(
        shift=128.4, spread=1.0, match_count=40, spheres=4, element="C"
    )
    enough_but_loose = ShiftPrediction(
        shift=128.4, spread=7.0, match_count=12, spheres=4, element="C"
    )
    barely_anything = ShiftPrediction(
        shift=128.4, spread=20.0, match_count=3, spheres=2, element="C"
    )

    assert plenty_and_tight.quality == "good"
    assert enough_but_loose.quality == "medium"
    assert barely_anything.quality == "rough"


def test_the_proton_spread_threshold_is_tighter_than_carbon():
    """A 5 ppm disagreement is unremarkable for 13C and enormous for 1H,
    so one threshold cannot serve both."""
    proton = ShiftPrediction(shift=7.2, spread=1.0, match_count=40, spheres=4, element="H")
    carbon = ShiftPrediction(shift=128.4, spread=1.0, match_count=40, spheres=4, element="C")

    assert proton.quality == "rough"
    assert carbon.quality == "good"


# --- Predicting a whole spectrum -----------------------------------------


def test_predicting_without_a_database_says_so_rather_than_failing_silently(tmp_path):
    result = predict_spectrum(
        Chem.MolFromSmiles("c1ccccc1"), "mol-1", "C", database_path=tmp_path / "absent.sqlite"
    )

    assert not result.values
    assert "No experimental shift database" in result.error


def test_predicting_an_uncovered_molecule_calls_it_a_coverage_gap(tmp_path):
    sdf = _write_sdf(tmp_path / "in.sd", _benzene_records(2, 128.4))
    database = tmp_path / "index.sqlite"
    build_index(sdf, database)

    result = predict_spectrum(
        Chem.MolFromSmiles("FC(F)(F)S(=O)(=O)F"), "mol-1", "C", database_path=database
    )

    assert not result.values
    assert "coverage gap" in result.error


def test_a_real_prediction_carries_its_evidence_per_atom(tmp_path):
    sdf = _write_sdf(
        tmp_path / "in.sd", _benzene_records(3, 128.0) + _benzene_records(3, 128.8)
    )
    database = tmp_path / "index.sqlite"
    build_index(sdf, database)

    result = predict_spectrum(
        Chem.MolFromSmiles("c1ccccc1"), "mol-1", "C", database_path=database
    )

    assert len(result.values) == 6
    assert all(value == pytest.approx(128.4) for value in result.values.values())
    assert result.units == "ppm"
    # Per atom, not one headline number that would hide a weak atom among
    # strong ones.
    per_atom = result.provenance.parameters["per_atom"]
    assert len(per_atom) == 6
    assert per_atom["0"]["matches"] == 36
    assert per_atom["0"]["quality"] in ("good", "medium", "rough")
    assert result.provenance.parameters["reference_source"].startswith("nmrshiftdb2")


def test_min_matches_is_what_gates_a_prediction():
    assert MIN_MATCHES >= 3, "one or two measurements is not a reference value"


def test_a_shallow_fallback_is_never_rated_good():
    """Measured on the real index: chlorobenzene's para carbon falls back
    to three spheres, pools 5176 measurements of "some para CH", agrees
    with itself closely, and is 2.1 ppm wrong. Evidence volume and tight
    spread alone called that the best prediction in the set."""
    generic = ShiftPrediction(
        shift=128.5, spread=1.0, match_count=5176, spheres=3, element="C"
    )
    specific = ShiftPrediction(
        shift=125.5, spread=1.0, match_count=6, spheres=6, element="C"
    )

    assert generic.quality != "good"
    assert specific.quality == "good"


def test_the_rating_bands_are_ordered_by_the_evidence_they_require():
    """Not a measurement of accuracy -- that is the held-out benchmark in
    the module docstring -- but a guard that the bands cannot invert."""
    good = ShiftPrediction(shift=1.0, spread=0.5, match_count=50, spheres=6, element="C")
    medium = ShiftPrediction(shift=1.0, spread=6.0, match_count=50, spheres=6, element="C")
    rough = ShiftPrediction(shift=1.0, spread=30.0, match_count=50, spheres=6, element="C")

    assert (good.quality, medium.quality, rough.quality) == ("good", "medium", "rough")


def test_the_registered_calculator_reports_a_missing_database_clearly(tmp_path, monkeypatch):
    """The calculator must be usable before the index is built -- saying
    what to do, not raising."""
    from openchem.chem import nmr_database

    monkeypatch.setattr(
        nmr_database, "default_database_path", lambda: tmp_path / "absent.sqlite"
    )
    result = nmr_database.compute_database_nmr(Chem.MolFromSmiles("CCO"), "mol-1", {})

    assert not result.values
    assert "database" in result.error.lower()
