"""Turning results into table cells.

The parser is the part that can be quietly wrong, so most of this file is
about what it must REFUSE. A column headed "Pi system" holding atom counts
scraped out of "Pi system: 10 atoms, 10 pi electrons" survives being
looked at, which is worse than no column.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.result_reduction import (
    alert_catalog_columns,
    descriptor_cell,
    descriptor_column,
    parse_reported_numbers,
    reduce_result,
)
from openchem.domain.common import CATEGORICAL_SCALE, CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureEntry,
    StructureSetResult,
    TrajectoryResult,
)


# --- what the parser accepts -------------------------------------------


@pytest.mark.parametrize(
    "line,label,value,units",
    [
        ("Randic index: 9.52", "Randic index", 9.52, ""),
        ("Atom count: 21", "Atom count", 21.0, ""),
        ("C: 60.00%", "C", 60.0, "%"),
        ("MMFF94 energy: 18.91 kcal/mol", "MMFF94 energy", 18.91, "kcal/mol"),
        ("Dipole Y: -0.89 Debye", "Dipole Y", -0.89, "Debye"),
        ("HOMO: +0.66 beta", "HOMO", 0.66, "beta"),
        # A unit containing a digit. An earlier rule banned digits outright
        # and silently lost both of these.
        ("Molecular polarizability: 18.11 A^3", "Molecular polarizability", 18.11, "A^3"),
        ("TPSA: 63.60 A^2", "TPSA", 63.6, "A^2"),
        # A trailing qualifier belongs to the story, not to the units.
        ("Polar surface area: 63.60 Ų (as drawn)", "Polar surface area", 63.6, "Ų"),
        # An out-of-N score: the numerator is what someone wants.
        ("CNS MPO score: 4.75 / 5.00", "CNS MPO score", 4.75, ""),
        # The two forms that are not "label: value" at all.
        ("LogP = 1.31", "LogP", 1.31, ""),
        ("pKa 3.65 +/- 0.11 (ensemble spread)", "pKa", 3.65, ""),
    ],
)
def test_a_real_measurement_is_parsed(line, label, value, units):
    assert parse_reported_numbers([line]) == [(label, value, units)]


@pytest.mark.parametrize(
    "line",
    [
        "Formula: C9H8O4",  # not a number at all
        "Pi system: 10 atoms, 10 pi electrons",  # a number, but of what?
        "Orbital energies (beta): +2.14, +1.41, +1.00",  # a list
        "MW: 180.16 -> 1.00",  # two numbers, neither obviously the value
        "LogD: -2.44 -> 1.00",
        "pKa (most basic): unavailable (needs a configured pkasolver environment)",
        "Note: simple Huckel treats every pi centre as an identical carbon.",
        "No stereo elements in this structure.",
        "Hydrogen bond: atoms 2-11 (3.47 Å)",
        "Ionizable centres: 1 acidic, 0 basic",
        "logD = -2.44 at pH 7.4 (Henderson-Hasselbalch)",
    ],
)
def test_an_ambiguous_line_is_refused(line):
    """Refusing is the safe failure: a missing column is visible, a wrong
    one is not. `logD = ...` is the one refusal that costs something real
    -- see the module docstring."""
    assert parse_reported_numbers([line]) == []


def test_a_repeated_label_is_kept_once():
    """`logd` reports "pKa: 3.65" twice in some structures; the second
    would otherwise overwrite the first with no trace."""
    assert parse_reported_numbers(["pKa: 3.65", "pKa: 9.10"]) == [("pKa", 3.65, "")]


def test_the_parser_survives_the_whole_registry():
    """Every report calculator, on a real molecule with a conformer.

    A regression here means either a producer stopped emitting a fact or
    the reduction got looser; both are worth failing on.

    **This used to measure the string PARSER**, because these calculators
    returned `matched` lines and one report had to be re-parsed back into
    labels and numbers. Measured then: 73 numeric columns extracted across
    16 calculators, and **25 lines refused** -- formulas, prose caveats,
    value lists, all correctly refused but all genuinely lost.

    Now they return facts, which were never flattened, so there is nothing
    to recover. Measured on these four: 45 facts giving 43 numeric
    columns, the two non-numeric ones being a formula and a direction
    vector, which are text and always were.
    """
    from rdkit.Chem import AllChem

    from openchem.bootstrap import build_service_container
    from openchem.domain.report import ReportResult

    registry = build_service_container().calculator_registry
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    AllChem.MMFFOptimizeMolecule(mol)

    total = 0
    for calculator_id in ("topology_analysis", "elemental_analysis", "surface_analysis", "dipole_moment"):
        definition = registry.get(calculator_id)
        result = registry.compute(
            calculator_id, mol, "m", {p.name: p.default for p in definition.parameters}
        )
        assert isinstance(result, ReportResult), (
            f"{calculator_id} still returns {type(result).__name__} -- it was migrated"
        )
        columns = reduce_result(result, calculator_id, definition.display_name, None)
        total += sum(1 for column, _cell in columns if column.numeric)

    # Floor well below the 43 measured, so adding one caveat to one
    # calculator does not break the suite.
    assert total >= 35, total


# --- descriptors --------------------------------------------------------


def _descriptor(value, descriptor_id="mol_wt", units="g/mol"):
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name="Molecular Weight",
        units=units,
        category="physicochemical",
        provider="rdkit",
        molecule_uuid="m",
        value=value,
        cache_state=CacheState.COMPLETED,
    )


def test_a_numeric_descriptor_keeps_full_precision():
    cell = descriptor_cell(_descriptor(180.15899999999996))
    assert cell.value == 180.15899999999996


def test_a_boolean_filter_becomes_one_and_zero_but_still_reads_as_yes():
    """The mean of a filter column is then the fraction of the project that
    passes it, which is the number someone actually wants."""
    passed = descriptor_cell(_descriptor(True, "lipinski_pass"))
    failed = descriptor_cell(_descriptor(False, "lipinski_pass"))
    assert (passed.value, passed.text) == (1.0, "Yes")
    assert (failed.value, failed.text) == (0.0, "No")


def test_a_text_descriptor_is_not_offered_as_a_number():
    column = descriptor_column(_descriptor("C9H8O4", "formula", ""))
    assert column.numeric is False
    assert descriptor_cell(_descriptor("C9H8O4", "formula", "")).value is None


def test_a_non_finite_value_becomes_a_gap_rather_than_poisoning_a_mean():
    """3D descriptors reach here as nan on degenerate geometries, and one
    nan makes a whole correlation nan somewhere far from its cause."""
    assert descriptor_cell(_descriptor(float("nan"))).value is None
    assert descriptor_cell(_descriptor(float("inf"))).value is None


def test_a_failed_descriptor_carries_its_reason():
    value = _descriptor(None)
    value.cache_state = CacheState.FAILED
    value.error = "Needs a real 3D conformer"
    cell = descriptor_cell(value)
    assert cell.failed and "conformer" in cell.error


def test_a_descriptor_column_takes_its_units_from_the_value():
    assert descriptor_column(_descriptor(1.0)).header == "Molecular Weight (g/mol)"


# --- calculators --------------------------------------------------------


def test_a_report_becomes_one_column_per_reported_number():
    result = AlertResult(
        alert_id="topology_analysis",
        name="Topology",
        molecule_uuid="m",
        matched=["Wiener index: 850", "Randic index: 9.52", "Note: not a number"],
    )
    pairs = reduce_result(result, "topology_analysis", "Topology Analysis")
    assert [column.label for column, _cell in pairs] == ["Wiener index", "Randic index"]
    assert [cell.value for _column, cell in pairs] == [850.0, 9.52]
    assert all(column.numeric for column, _cell in pairs)


def test_a_report_with_no_numbers_is_text_not_a_line_count():
    """"No stereo elements in this structure." must not become the number
    1 in a numeric column."""
    result = AlertResult(
        alert_id="stereo_descriptors",
        name="Stereo",
        molecule_uuid="m",
        matched=["No stereo elements in this structure."],
    )
    (column, cell), = reduce_result(result, "stereo_descriptors", "Stereo Descriptors")
    assert column.numeric is False
    assert cell.value is None
    assert "No stereo elements" in cell.text


def test_an_alert_catalog_counts_its_matches():
    """Unlike a report, a catalog's length IS the property -- and an empty
    catalog is a zero, not a gap."""
    clean = AlertResult(alert_id="pains", name="PAINS", molecule_uuid="m", matched=[])
    count_column, matched_column = alert_catalog_columns(clean)
    assert count_column[0].numeric and count_column[1].value == 0.0
    assert matched_column[1].text == "none"
    assert matched_column[0].numeric is False


def _per_atom(values, categorical=False, summary="", name="Charge"):
    parameters = {}
    if categorical:
        parameters["scale"] = CATEGORICAL_SCALE
    if summary:
        parameters["summary"] = summary
    return PerAtomDataset(
        property_id="p",
        name=name,
        units="e",
        method="rdkit",
        molecule_uuid="m",
        values=values,
        provenance=Provenance(created_by="core", method="rdkit", parameters=parameters),
    )


@pytest.mark.parametrize(
    "aggregate,expected",
    [("mean", 2.0), ("sum", 6.0), ("min", -1.0), ("max", 4.0), ("max_abs", 4.0)],
)
def test_a_per_atom_dataset_collapses_by_the_requested_aggregate(aggregate, expected):
    (column, cell), = reduce_result(
        _per_atom({0: -1.0, 1: 3.0, 2: 4.0}), "charge", "Charge", per_atom_aggregate=aggregate
    )
    assert cell.value == expected
    # The label states which was taken -- the number is meaningless without it.
    assert aggregate in column.label


def test_categorical_per_atom_data_counts_categories_and_never_aggregates_them():
    """Summing ring-system ids gives 15 for a molecule with two rings. This
    is the same trap the Calculator Inspector's "Overall: N" already had to
    close, arriving by a different route."""
    (_column, cell), = reduce_result(
        _per_atom({0: 1.0, 1: 1.0, 2: 2.0, 3: 2.0, 4: 2.0}, categorical=True, name="Ring Systems"),
        "ring_systems",
        "Ring Systems",
        per_atom_aggregate="sum",
    )
    assert cell.value == 2.0


def test_an_empty_categorical_result_explains_itself():
    """Caffeine detects zero functional groups because its lactam carbonyls
    are ring-embedded. A bare "0" reads as a calculator that did not run."""
    (_column, cell), = reduce_result(
        _per_atom({}, categorical=True, summary="No functional groups matched."),
        "functional_groups",
        "Functional Groups",
    )
    assert cell.value == 0.0
    assert cell.text == "No functional groups matched."


def test_an_empty_numeric_dataset_says_so_rather_than_showing_blank():
    (_column, cell), = reduce_result(_per_atom({}), "charge", "Charge")
    assert cell.value is None
    assert cell.text == "no values"


@pytest.mark.parametrize(
    "result,expected_text",
    [
        (
            StructureSetResult(
                set_id="s", name="Tautomers", method="rdkit", molecule_uuid="m",
                entries=[StructureEntry(molblock="")], total_available=4,
            ),
            "4 structures",
        ),
        (
            SpectrumResult(
                spectrum_type="nmr_1h", name="NMR", units="ppm", method="x",
                molecule_uuid="m", values={0: 1.0, 1: 2.0},
            ),
            "2 shifts",
        ),
        (
            PhCurveResult(
                curve_id="c", name="logD", method="x", molecule_uuid="m",
                ph_values=[1.0, 2.0, 3.0], series={"a": [1.0, 2.0, 3.0]},
            ),
            "1 series over 3 pH points",
        ),
        (
            TrajectoryResult(
                trajectory_id="t", name="MD", method="x", molecule_uuid="m", frames=["", "", ""]
            ),
            "3 frames",
        ),
    ],
)
def test_descriptive_results_are_text_and_never_numeric(result, expected_text):
    """A count of tautomers or NMR peaks describes the CALCULATION, not the
    molecule. Offering it as a numeric column invites someone to correlate
    it against LogP."""
    (column, cell), = reduce_result(result, "c", "Calc")
    assert column.numeric is False
    assert cell.value is None
    assert cell.text == expected_text


def test_a_failed_calculator_still_produces_a_cell_with_its_reason():
    result = AlertResult(
        alert_id="steric_analysis",
        name="Steric",
        molecule_uuid="m",
        matched=[],
        cache_state=CacheState.FAILED,
        error="No donor atom found.",
    )
    (_column, cell), = reduce_result(result, "steric_analysis", "Steric Analysis")
    assert cell.failed
    assert cell.error == "No donor atom found."


def test_the_prediction_basis_travels_onto_every_column_a_calculator_makes():
    """One calculator producing ten columns must not launder its label off
    nine of them."""
    result = AlertResult(
        alert_id="admet_ml",
        name="ADMET",
        molecule_uuid="m",
        matched=["hERG blockade: 0.02", "Ames mutagenicity: 0.08"],
    )
    pairs = reduce_result(result, "admet_ml", "ADMET", prediction_basis="empirical")
    assert {column.prediction_basis for column, _cell in pairs} == {"empirical"}
