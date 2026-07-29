from __future__ import annotations

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel


class _RecordingQuantumChemistryService(QuantumChemistryService):
    """Stands in for the real service -- captures request_calculation's
    kwargs instead of actually spawning a QProcess, so tests can inspect
    exactly what the panel built without needing a real ORCA backend."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.requests: list[dict] = []

    def request_calculation(self, **kwargs) -> None:  # noqa: D102 - test double
        self.requests.append(kwargs)


def _make_panel():
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    service = _RecordingQuantumChemistryService(bus)
    panel = QuantumChemistryPanel(service, engine, settings, bus)
    return panel, engine, service


def test_run_refuses_a_molecule_with_no_conformer(qapp):
    """Regression test: confirmed live against a real ORCA install that
    running straight off molecule.molblock (from SMILES import or the 2D
    editor) sends a structure with hydrogens stripped down to implicit
    H-count and no 3D positions at all -- for water, this silently computed
    a bare oxygen atom's energy instead of failing loudly. The panel must
    require a real conformer (which RDKitConformerProvider always builds
    with explicit, positioned hydrogens) before running anything.
    """
    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")  # molblock only, no conformer

    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_run_clicked()

    assert service.requests == []
    assert "conformer" in panel._status_label.text().lower()


def test_run_proceeds_once_a_conformer_exists(qapp):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    panel, engine, service = _make_panel()
    molecule = MoleculeModel(display_name="Water")
    engine.set_structure_from_smiles(molecule, "O")

    mol_3d = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=42)
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d), method="rdkit_etkdg"))

    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._method_combo.setCurrentText("HF STO-3G")

    panel._on_run_clicked()

    assert len(service.requests) == 1
    used_mol = service.requests[0]["mol"]
    assert used_mol.GetNumAtoms() == 3  # O + 2 H, not stripped down to just O
