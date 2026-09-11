"""Copyable renderings of calculator results.

Tabular results are checked for TAB separation specifically: that is what
makes a paste land in Excel as columns instead of as one ruined column,
and it is invisible to the eye, so nothing but a test will catch it
regressing to spaces.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.scientific_result import (
    AlertResult,
    NMRSpectrumResult,
    PerAtomDataset,
    PhCurveResult,
    StructureEntry,
    StructureSetResult,
)
from openchem.ui.result_clipboard import result_to_text


def test_a_report_result_copies_its_name_and_every_line():
    result = AlertResult(
        alert_id="elemental",
        name="Elemental Analysis",
        molecule_uuid="m",
        matched=["Formula: C9H8O4", "Mass: 180.159"],
    )

    assert result_to_text(result) == "Elemental Analysis\nFormula: C9H8O4\nMass: 180.159"


def test_a_per_atom_result_copies_as_tab_separated_rows_in_atom_order():
    result = PerAtomDataset(
        property_id="charge",
        name="Partial Charge",
        units="e",
        method="gasteiger",
        molecule_uuid="m",
        # Deliberately out of order -- a spreadsheet paste is unreadable
        # if the rows arrive in dict-insertion order.
        values={2: -0.35, 0: 0.12, 1: 0.04},
    )

    lines = result_to_text(result).splitlines()

    assert lines[0] == "Partial Charge"
    assert lines[1] == "Atom\tPartial Charge (e)"
    assert lines[2:] == ["0\t0.12", "1\t0.04", "2\t-0.35"]


def test_a_spectrum_copies_its_element_column_via_the_subclass():
    """`NMRSpectrumResult` subclasses `SpectrumResult`, so exact-type
    lookup misses it -- without the isinstance fallback the NMR result
    would copy as nothing but its name."""
    result = NMRSpectrumResult(
        spectrum_type="nmr_1h",
        name="1H NMR",
        units="ppm",
        method="orca",
        molecule_uuid="m",
        values={0: 1.22, 3: 3.70},
        elements={0: "H", 3: "H"},
    )

    lines = result_to_text(result).splitlines()

    assert lines[1] == "Atom\tElement\tShift (ppm)"
    assert lines[2:] == ["0\tH\t1.22", "3\tH\t3.7"]


def test_a_ph_curve_copies_one_column_per_series():
    result = PhCurveResult(
        curve_id="microspecies",
        name="Microspecies",
        method="dimorphite",
        molecule_uuid="m",
        ph_values=[1.0, 2.0],
        series={"HA": [90.0, 50.0], "A-": [10.0, 50.0]},
        x_label="pH",
        y_label="%",
    )

    lines = result_to_text(result).splitlines()

    assert lines[1] == "pH\tHA\tA-"
    assert lines[2] == "1\t90\t10"
    assert lines[3] == "2\t50\t50"


def test_a_structure_set_copies_one_smiles_per_row_keeping_stereo():
    """The stereoisomer case Alex actually uses: if the copy dropped the
    @/@@ every isomer would be the same string and the whole result would
    be useless."""
    engine = ChemistryEngine()
    entries = [
        StructureEntry(
            molblock=Chem.MolToMolBlock(Chem.MolFromSmiles(smiles)), label=f"Isomer {index}"
        )
        for index, smiles in enumerate(["C[C@H](F)Cl", "C[C@@H](F)Cl"], start=1)
    ]
    result = StructureSetResult(
        set_id="stereoisomers", name="Stereoisomers", method="rdkit", molecule_uuid="m", entries=entries
    )

    lines = result_to_text(result).splitlines()

    assert lines[1] == "#\tLabel\tSMILES\tEnergy\tScore"
    smiles_column = [line.split("\t")[2] for line in lines[2:]]
    assert smiles_column == ["C[C@H](F)Cl", "C[C@@H](F)Cl"]
    assert smiles_column[0] != smiles_column[1]


def test_one_unconvertible_entry_does_not_lose_the_rest():
    result = StructureSetResult(
        set_id="s",
        name="Set",
        method="rdkit",
        molecule_uuid="m",
        entries=[
            StructureEntry(molblock="not a molblock", label="bad"),
            StructureEntry(
                molblock=Chem.MolToMolBlock(Chem.MolFromSmiles("CCO")), label="good"
            ),
        ],
    )

    lines = result_to_text(result).splitlines()

    assert lines[2].split("\t")[2] == ""
    assert lines[3].split("\t")[2] == "CCO"


def test_a_failed_result_copies_its_error_rather_than_an_empty_string():
    result = PerAtomDataset(
        property_id="p",
        name="Broken",
        units="",
        method="m",
        molecule_uuid="m",
        values={},
        cache_state=CacheState.FAILED,
        error="No conformer available.",
    )

    # PerAtomDataset has its own adapter, so it still renders as a (empty)
    # table -- the fallback error path is for result types with none.
    assert "Broken" in result_to_text(result)


def test_molblock_to_smiles_keeps_stereochemistry():
    engine = ChemistryEngine()
    molblock = Chem.MolToMolBlock(Chem.MolFromSmiles("C[C@H](F)Cl"))

    assert engine.molblock_to_smiles(molblock) == "C[C@H](F)Cl"


# --- a declared chart's numbers reach the clipboard ----------------------
#
# Found by merging `solubility_curve` into `Solubility` in stage 3:
# `PhCurveResult` serialised its points as a pasteable table and
# `ReportResult` serialised its declared charts not at all, so the merged
# result exported the facts and dropped 57 rows. General rather than
# solubility-specific -- measured, a mass spectrum's stick chart was
# equally unexportable.


def _line_chart(title="Solubility vs pH"):
    from openchem.domain.report import LineChartAnnotation, LineSeries

    return LineChartAnnotation(
        series=(LineSeries(points=((0.0, -2.1), (7.0, 0.74)), name="Solubility"),),
        x_label="pH",
        y_label="logS",
        x_descending=False,
        title=title,
    )


def _report_with(chart):
    from openchem.domain.report import Basis, Fact, FactCategory, ReportResult

    return ReportResult(
        molecule_uuid="m",
        report_id="probe",
        name="Probe",
        facts=(
            Fact(
                category=FactCategory.IDENTITY, label="Category", value="High",
                display_value="High", source="core", basis=Basis.HEURISTIC,
            ),
        ),
        charts=(chart,),
    )


def test_a_declared_line_chart_exports_its_points():
    """A copy that drops the curve says less than the screen shows."""
    from openchem.ui.result_clipboard import result_to_text

    text = result_to_text(_report_with(_line_chart()))
    assert "Category" in text, "the facts must survive too"
    assert "pH\tSolubility" in text, text
    assert "7\t0.74" in text, text
    assert "Solubility vs pH" in text


def test_a_declared_stick_chart_exports_its_sticks():
    """The other drawable kind, and it carries its numbers differently --
    sticks with an optional label rather than named series of pairs. A
    consumer guessing from attribute names is the probe-for-a-field-nobody-
    has failure this project already paid for across nine calculators."""
    from openchem.domain.report import Stick, StickChartAnnotation
    from openchem.ui.result_clipboard import result_to_text

    chart = StickChartAnnotation(
        sticks=(Stick(180.0, 1.0, "M"), Stick(181.0, 0.0998, "M+1")),
        x_label="m/z", y_label="Relative abundance", x_descending=False,
        title="Mass spectrum",
    )
    text = result_to_text(_report_with(chart))
    assert "m/z\tRelative abundance\tlabel" in text, text
    assert "180\t1\tM" in text, text


def test_a_DEPICTION_exports_no_table_because_it_has_none():
    """The negative, and it is the half that keeps the rule honest: a
    picture of a structure has no numbers to paste, and inventing a table
    for it would be the UI deriving data nobody declared."""
    from openchem.ui.report_format import chart_rows

    class _Depiction:
        title = "Lewis sites"

    assert chart_rows(_Depiction()) == []


def test_an_empty_chart_exports_nothing_rather_than_a_bare_header():
    """A header row with no data under it reads as a table that lost its
    contents."""
    from openchem.domain.report import LineChartAnnotation
    from openchem.ui.report_format import chart_rows

    empty = LineChartAnnotation(
        series=(), x_label="pH", y_label="logS", x_descending=False
    )
    assert chart_rows(empty) == []
