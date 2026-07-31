from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_generators import enumerate_resonance_forms, enumerate_stereoisomers
from openchem.domain.common import CacheState
from openchem.domain.scientific_result import StructureEntry, StructureSetResult
from openchem.ui.widgets.structure_grid_widget import StructureGridWidget


def _empty_set(**overrides) -> StructureSetResult:
    defaults = dict(set_id="x", name="X", method="rdkit", molecule_uuid="mol-1")
    defaults.update(overrides)
    return StructureSetResult(**defaults)


def test_grid_renders_one_cell_per_entry(qapp):
    result = enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)C(Cl)C"), "mol-1")
    widget = StructureGridWidget(ChemistryEngine(), result)

    assert widget._grid.count() == len(result.entries) == 4


def test_grid_handles_an_empty_result(qapp):
    widget = StructureGridWidget(ChemistryEngine(), _empty_set())
    widget.resize(600, 400)
    widget.grab()

    assert widget._grid.count() == 0


def test_grid_shows_a_failed_results_error(qapp):
    widget = StructureGridWidget(
        ChemistryEngine(), _empty_set(cache_state=CacheState.FAILED, error="no attachment points")
    )
    assert "no attachment points" in widget._summary.text()


def test_summary_distinguishes_shown_from_total_available(qapp):
    """A Markush class of millions showing its first thousand must not read
    as 'this class has a thousand members'."""
    result = _empty_set(
        entries=[StructureEntry(molblock="", label=str(i)) for i in range(3)],
        total_available=38_102_400,
    )
    widget = StructureGridWidget(ChemistryEngine(), result)

    assert "3" in widget._summary.text()
    assert "38,102,400" in widget._summary.text()


def test_resonance_forms_are_all_rendered_despite_identical_smiles(qapp):
    """Acetate's two contributors share a canonical SMILES. The grid must
    show both -- any dedupe would delete half the result."""
    result = enumerate_resonance_forms(Chem.MolFromSmiles("CC(=O)[O-]"), "mol-1")
    widget = StructureGridWidget(ChemistryEngine(), result)

    assert widget._grid.count() == 2


def test_clicking_a_cell_selects_that_entry(qapp):
    result = enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)C(Cl)C"), "mol-1")
    widget = StructureGridWidget(ChemistryEngine(), result)
    received: list[int] = []
    widget.structure_selected.connect(received.append)

    widget._grid.itemAt(2).widget().clicked.emit(2)

    assert received == [2]
    assert widget.selected_index() == 2
    assert widget.selected_entry() is result.entries[2]


def test_an_unrenderable_entry_does_not_blank_the_whole_grid(qapp):
    result = _empty_set(
        entries=[
            StructureEntry(molblock="not a molblock", label="broken"),
            StructureEntry(molblock="", label="also broken"),
        ]
    )
    widget = StructureGridWidget(ChemistryEngine(), result)

    assert widget._grid.count() == 2


def test_setting_a_new_result_replaces_the_previous_cells(qapp):
    widget = StructureGridWidget(
        ChemistryEngine(), enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)C(Cl)C"), "mol-1")
    )
    assert widget._grid.count() == 4

    widget.set_result(enumerate_stereoisomers(Chem.MolFromSmiles("CC(F)CC"), "mol-1"))

    assert widget._grid.count() == 2
