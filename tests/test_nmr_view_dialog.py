from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from conftest import synthetic_nmr_spectrum
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.ui.dialogs.nmr_view_dialog import NmrViewDialog

from test_nmr_view_widget import FakeViewerBackend

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


def _molecule_and_spectrum(engine: ChemistryEngine):
    molecule = MoleculeModel(display_name="Ibuprofen")
    engine.set_structure_from_smiles(molecule, IBUPROFEN)
    spectrum = synthetic_nmr_spectrum(
        Chem.AddHs(Chem.MolFromSmiles(IBUPROFEN)), molecule.uuid
    )
    return molecule, spectrum


def _dialog(qapp) -> NmrViewDialog:
    engine = ChemistryEngine()
    molecule, spectrum = _molecule_and_spectrum(engine)
    return NmrViewDialog(engine, molecule, spectrum, None, backend=FakeViewerBackend())


def test_dialog_shows_the_signal_list(qapp):
    engine = ChemistryEngine()
    molecule, spectrum = _molecule_and_spectrum(engine)

    dialog = NmrViewDialog(engine, molecule, spectrum, None, backend=FakeViewerBackend())

    assert len(dialog.view.signals()) == 9
    assert molecule.display_name in dialog.windowTitle()


def test_dialog_loads_a_conformer_into_the_3d_pane_when_one_exists(qapp):
    engine = ChemistryEngine()
    molecule, spectrum = _molecule_and_spectrum(engine)
    conformer = ConformerModel(molblock="fake 3d molblock", method="rdkit_etkdg")
    molecule.conformers.append(conformer)
    backend = FakeViewerBackend()

    NmrViewDialog(engine, molecule, spectrum, conformer.molblock, backend=backend)

    assert backend.loaded_molblocks == [conformer.molblock]


def test_dialog_without_a_conformer_still_shows_the_spectrum(qapp):
    engine = ChemistryEngine()
    molecule, spectrum = _molecule_and_spectrum(engine)
    backend = FakeViewerBackend()

    dialog = NmrViewDialog(engine, molecule, spectrum, None, backend=backend)

    assert backend.loaded_molblocks == []
    assert dialog.view.signals()


def test_copy_signals_gives_tab_separated_columns(qapp):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QPushButton

    dialog = _dialog(qapp)
    next(b for b in dialog.findChildren(QPushButton) if b.text() == "Copy Signals").click()

    lines = QGuiApplication.clipboard().text().splitlines()
    assert lines[0] == "Shift (ppm)\tIntegration\tMultiplicity\tJ (Hz)"
    assert len(lines) == len(dialog.view.signals()) + 1
    # Every row has the same column count as the header, or a spreadsheet
    # paste shears.
    assert {line.count("\t") for line in lines} == {3}


def test_copy_raw_shifts_gives_the_per_nucleus_values_not_the_signals(qapp):
    """The two copies are different data on purpose -- signals are
    grouped, raw shifts are per nucleus."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QPushButton

    dialog = _dialog(qapp)
    next(b for b in dialog.findChildren(QPushButton) if b.text() == "Copy Raw Shifts").click()

    text = QGuiApplication.clipboard().text()
    assert "Atom\tElement\tShift" in text
    assert text != dialog.signals_text()
