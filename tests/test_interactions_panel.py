"""The Interactions panel: two molecules, evidence, no score.

Every test destroys its panel deterministically -- see the disposal
helper below and the section CLAUDE.md devotes to why. A test that builds
an unparented widget and walks away leaves Python to destroy it at
whatever arbitrary later moment the collector runs, which on Windows is
an access violation inside some unrelated event-driven test.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryResultReady
from openchem.ui.panels.interactions_panel import InteractionsPanel


def dispose(widget) -> None:
    """Destroy one widget now, flushing only ITS deferred delete.

    Never the global `sendPostedEvents(None, DeferredDelete)`: that drains
    every pending delete in the process, including ones other test files
    left queued, which is a double-free.
    """
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def molecule(name: str, smiles: str) -> MoleculeModel:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return MoleculeModel(
        display_name=name,
        molblock=Chem.MolToMolBlock(mol),
        canonical_smiles=Chem.MolToSmiles(mol),
    )


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    widget = InteractionsPanel(ChemistryEngine(), bus)
    yield widget, bus
    dispose(widget)


def select(panel: InteractionsPanel, acid_uuid: str, base_uuid: str) -> None:
    for combo, uuid in ((panel._acid_combo, acid_uuid), (panel._base_combo, base_uuid)):
        index = combo.findData(uuid, Qt.ItemDataRole.UserRole)
        assert index >= 0, uuid
        combo.setCurrentIndex(index)


def table_rows(panel: InteractionsPanel) -> list[list[str]]:
    return [
        [
            panel._table.item(row, column).text()
            for column in range(panel._table.columnCount())
        ]
        for row in range(panel._table.rowCount())
    ]


def quantum_event(uuid: str, **values: float) -> QuantumChemistryResultReady:
    return QuantumChemistryResultReady(
        molecule_uuid=uuid,
        descriptors=[
            DescriptorValue(
                descriptor_id=key,
                name=key,
                units="eV",
                category="quantum_chemistry",
                provider="orca",
                molecule_uuid=uuid,
                value=value,
                cache_state=CacheState.COMPLETED,
                provenance=Provenance(created_by="core", method="orca"),
            )
            for key, value in values.items()
        ],
        conformer=None,
    )


# --- the pair ---------------------------------------------------------------


def test_both_combos_offer_every_molecule(panel):
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))

    assert widget._acid_combo.count() == 2
    assert widget._base_combo.count() == 2


def test_a_parameterised_pair_shows_its_enthalpy(panel):
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))
    select(widget, iodine.uuid, amine.uuid)

    widget._on_predict_clicked()

    rows = {row[0]: row for row in table_rows(widget)}
    # Units ride WITH the value: "12.12 kcal/mol" is how it is read aloud,
    # and a separate column cost a third of the dock's width.
    assert rows["Drago-Wayland enthalpy"][1] == "12.12 kcal/mol"
    assert rows["Drago-Wayland enthalpy"][2] == "deterministic"
    assert "iodine + triethylamine" in widget._status_label.text()


def test_an_unavailable_line_stays_visible_with_its_reason(panel):
    """Dropping the row would read as "this does not apply here" when it
    means "run a quantum job", which are opposite messages."""
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))
    select(widget, iodine.uuid, amine.uuid)

    widget._on_predict_clicked()

    rows = {row[0]: row for row in table_rows(widget)}
    assert len(rows) == 3
    assert rows["Frontier orbital gap"][1] == "--"
    # The reason is NOT a table column -- as a wrapped cell it made rows
    # taller than the whole table and the panel rendered blank. It is on
    # the row's tooltip and in full in the notes pane.
    tooltip = widget._table.item(1, 0).toolTip()
    assert "quantum chemistry job" in tooltip
    assert "quantum chemistry job" in widget._notes.toPlainText()


def test_the_panel_states_its_assumptions_and_limitations(panel):
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))
    select(widget, iodine.uuid, amine.uuid)

    widget._on_predict_clicked()

    notes = widget._notes.toPlainText()
    assert "Assumption:" in notes
    assert "Sterics" in notes


# --- quantum numbers arriving from another panel ---------------------------


def test_a_quantum_run_fills_in_the_orbital_lines(panel):
    """The point of listening for the event: run a job on each molecule
    from the Quantum Chemistry panel and these appear here, with nothing
    wired between the panels by hand."""
    widget, bus = panel
    acid, base = molecule("boron trifluoride", "FB(F)F"), molecule("ammonia", "N")
    widget.set_project(ProjectModel(molecules=[acid, base]))
    select(widget, acid.uuid, base.uuid)

    widget._on_quantum_result(quantum_event(acid.uuid, **{"orca.lumo_energy": 1.0, "orca.hardness": 6.11}))
    widget._on_quantum_result(quantum_event(base.uuid, **{"orca.homo_energy": -6.82, "orca.hardness": 4.16}))
    widget._on_predict_clicked()

    rows = {row[0]: row for row in table_rows(widget)}
    assert rows["Frontier orbital gap"][1] == "7.82 eV"
    assert rows["HSAB hardness match"][1] == "1.95 eV"


def test_delta_scf_hardness_wins_over_koopmans(panel):
    """Koopmans hardness inverts ammonia against phosphine, so a hard/soft
    match built on it can be exactly backwards. When a molecule has both,
    the delta-SCF value is the one used."""
    widget, _bus = panel
    acid, base = molecule("boron trifluoride", "FB(F)F"), molecule("ammonia", "N")
    widget.set_project(ProjectModel(molecules=[acid, base]))
    select(widget, acid.uuid, base.uuid)

    widget._on_quantum_result(
        quantum_event(acid.uuid, **{"orca.hardness": 6.11, "orca.dscf_hardness": 9.00})
    )
    widget._on_quantum_result(
        quantum_event(base.uuid, **{"orca.hardness": 4.16, "orca.dscf_hardness": 7.21})
    )
    widget._on_predict_clicked()

    rows = {row[0]: row for row in table_rows(widget)}
    assert rows["HSAB hardness match"][1] == "1.79 eV"  # |9.00-7.21|, not |6.11-4.16|


def test_quantum_numbers_are_kept_per_molecule(panel):
    """A hardness recorded for the acid must not be read as the base's --
    the two are what the whole HSAB line compares."""
    widget, bus = panel
    acid, base = molecule("boron trifluoride", "FB(F)F"), molecule("ammonia", "N")
    widget.set_project(ProjectModel(molecules=[acid, base]))
    select(widget, acid.uuid, base.uuid)

    widget._on_quantum_result(quantum_event(acid.uuid, **{"orca.hardness": 6.11}))
    widget._on_predict_clicked()

    rows = {row[0]: row for row in table_rows(widget)}
    assert rows["HSAB hardness match"][1] == "--"


# --- refusals and guards ----------------------------------------------------


def test_the_same_molecule_on_both_sides_is_refused(panel):
    """Self-association is real chemistry and is not what this computes.
    Reporting a molecule's parameters against themselves would look like
    an answer."""
    widget, _bus = panel
    iodine = molecule("iodine", "II")
    widget.set_project(ProjectModel(molecules=[iodine]))
    select(widget, iodine.uuid, iodine.uuid)

    widget._on_predict_clicked()

    assert "same molecule" in widget._status_label.text()
    assert widget._table.rowCount() == 0


def test_a_pair_that_cannot_form_an_adduct_says_so_and_clears_the_table(panel):
    """A stale table beside a refusal message would be read as the answer
    to the pair now selected."""
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    methane = molecule("methane", "C")
    widget.set_project(ProjectModel(molecules=[iodine, amine, methane]))

    select(widget, iodine.uuid, amine.uuid)
    widget._on_predict_clicked()
    assert widget._table.rowCount() == 3

    select(widget, methane.uuid, amine.uuid)
    widget._on_predict_clicked()
    assert widget._table.rowCount() == 0
    assert "accept an electron pair" in widget._status_label.text()


def test_predicting_with_no_project_asks_for_a_pair(panel):
    widget, _bus = panel
    widget._on_predict_clicked()
    assert "Pick a Lewis acid" in widget._status_label.text()


# --- naming and shape -------------------------------------------------------


def test_both_subjects_live_under_one_panel(panel):
    """The panel was named "Interactions" rather than "Lewis Adduct" so the
    intramolecular analysis could move in without a rename. It has, and
    adding it really was one line plus its tab -- which is what tabbing
    from the first commit bought."""
    widget, _bus = panel
    assert [widget._tabs.tabText(i) for i in range(widget._tabs.count())] == [
        "Lewis Adduct",
        "Intramolecular",
    ]


def test_neither_combo_follows_the_tree_selection(panel):
    """Both are deliberate picks defining one comparison. Reshuffling
    either because the user clicked something else in the tree would
    silently change what the table on screen describes."""
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    project = ProjectModel(molecules=[iodine, amine])
    widget.set_project(project)
    select(widget, amine.uuid, iodine.uuid)

    # A project mutation elsewhere re-pushes the project; the picks hold.
    widget.set_project(project)

    assert widget._acid_combo.currentData(Qt.ItemDataRole.UserRole) == amine.uuid
    assert widget._base_combo.currentData(Qt.ItemDataRole.UserRole) == iodine.uuid


def test_every_row_fits_inside_the_table(panel):
    """The bug this file exists to stop coming back.

    With `setWordWrap(True)` and `resizeRowsToContents()`, the note column
    made row 0 **481 pixels tall inside a 106-pixel viewport**. Every test
    above passed -- the model held the right strings -- and the panel
    showed three blank lines in the running app. Only opening it caught
    it, so this asserts the GEOMETRY rather than the contents.
    """
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))
    select(widget, iodine.uuid, amine.uuid)
    widget.resize(360, 700)
    widget.show()

    widget._on_predict_clicked()
    QCoreApplication.processEvents()

    heights = [widget._table.rowHeight(r) for r in range(widget._table.rowCount())]
    assert heights, "no rows"
    # A single line of text, not a wrapped paragraph.
    assert max(heights) < 60, heights
    assert sum(heights) <= widget._table.viewport().height()


def test_the_full_note_is_reachable_without_the_column(panel):
    """Dropping the note column only works if the text is still findable.
    It is in two places: the row's tooltip, and the notes pane."""
    widget, _bus = panel
    iodine, amine = molecule("iodine", "II"), molecule("triethylamine", "CCN(CC)CC")
    widget.set_project(ProjectModel(molecules=[iodine, amine]))
    select(widget, iodine.uuid, amine.uuid)

    widget._on_predict_clicked()

    assert "1965 paper" in widget._table.item(0, 0).toolTip()
    assert "1965 paper" in widget._notes.toPlainText()
    # Every cell in a row carries it, so hovering anywhere on the row works.
    tooltips = {widget._table.item(0, c).toolTip() for c in range(widget._table.columnCount())}
    assert len(tooltips) == 1


# --- the intramolecular tab -------------------------------------------------


def _with_conformer(name: str, smiles: str) -> MoleculeModel:
    """A molecule that actually has 3D geometry -- contacts are measured on
    a conformer, and without one there is nothing to measure."""
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) == 0, smiles
    AllChem.MMFFOptimizeMolecule(mol)
    return MoleculeModel(
        display_name=name, molblock=Chem.MolToMolBlock(mol),
        canonical_smiles=Chem.MolToSmiles(mol),
    )


def test_contacts_are_listed_per_kind(panel):
    """Salicylic acid's intramolecular hydrogen bond is the standard case --
    the OH and the carbonyl are held together by the ring."""
    widget, _bus = panel
    model = _with_conformer("salicylic acid", "OC(=O)c1ccccc1O")
    widget.set_project(ProjectModel(molecules=[model]))
    index = widget._contacts_combo.findData(model.uuid, Qt.ItemDataRole.UserRole)
    widget._contacts_combo.setCurrentIndex(index)

    widget._on_find_contacts()

    assert widget._contacts_table.rowCount() > 0
    kinds = {
        widget._contacts_table.item(r, 0).text()
        for r in range(widget._contacts_table.rowCount())
    }
    assert kinds, "no interaction kinds reported"
    assert "contacts across" in widget._contacts_status.text()


def test_a_molecule_with_no_conformer_says_what_is_missing(panel):
    """Not a crash and not an empty table: geometry is the thing absent,
    and the message has to name it or the empty result reads as 'none'."""
    widget, _bus = panel
    flat = molecule("ethanol", "CCO")   # no conformer
    widget.set_project(ProjectModel(molecules=[flat]))
    index = widget._contacts_combo.findData(flat.uuid, Qt.ItemDataRole.UserRole)
    widget._contacts_combo.setCurrentIndex(index)

    widget._on_find_contacts()

    assert widget._contacts_table.rowCount() == 0
    assert widget._contacts_status.text(), "a silent empty table hides the reason"


def test_no_contacts_is_reported_as_a_finding_not_a_failure(panel):
    """"Nothing touches anything" is an answer. The calculator already says
    so explicitly and the panel must not regress to a blank table."""
    widget, _bus = panel
    model = _with_conformer("methane", "C")
    widget.set_project(ProjectModel(molecules=[model]))
    index = widget._contacts_combo.findData(model.uuid, Qt.ItemDataRole.UserRole)
    widget._contacts_combo.setCurrentIndex(index)

    widget._on_find_contacts()

    assert "no intramolecular contacts" in widget._contacts_status.text()


def test_contact_rows_are_single_line(panel):
    """Same geometry guard as the Lewis table -- wrapped cells are what made
    that one render as blank rows."""
    widget, _bus = panel
    model = _with_conformer("salicylic acid", "OC(=O)c1ccccc1O")
    widget.set_project(ProjectModel(molecules=[model]))
    index = widget._contacts_combo.findData(model.uuid, Qt.ItemDataRole.UserRole)
    widget._contacts_combo.setCurrentIndex(index)
    widget.resize(360, 700)
    widget.show()

    widget._on_find_contacts()
    QCoreApplication.processEvents()

    heights = [widget._contacts_table.rowHeight(r) for r in range(widget._contacts_table.rowCount())]
    assert heights
    assert max(heights) < 60, heights
