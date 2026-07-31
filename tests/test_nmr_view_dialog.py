from __future__ import annotations

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.nmr_empirical_smarts import estimate_shifts_by_smarts_environment
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.ui.dialogs.nmr_view_dialog import NmrViewDialog

from test_nmr_view_widget import FakeViewerBackend

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"


def _molecule_and_spectrum(engine: ChemistryEngine):
    molecule = MoleculeModel(display_name="Ibuprofen")
    engine.set_structure_from_smiles(molecule, IBUPROFEN)
    spectrum = estimate_shifts_by_smarts_environment(
        Chem.AddHs(Chem.MolFromSmiles(IBUPROFEN)), molecule.uuid
    )
    return molecule, spectrum


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
