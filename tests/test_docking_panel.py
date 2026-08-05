from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.docking_service import DockingService
from openchem.ui.panels.docking_panel import DockingPanel


class _RecordingDockingService(DockingService):
    """Stands in for the real DockingService -- captures request_docking's
    kwargs instead of actually scheduling a QThreadPool job, so tests can
    inspect exactly what ligand Mol the panel built without needing a real
    Vina backend."""

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.requests: list[dict] = []

    def request_docking(self, **kwargs) -> None:  # noqa: D102 - test double
        self.requests.append(kwargs)


def _make_panel():
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    docking_service = _RecordingDockingService(bus)
    panel = DockingPanel(docking_service, engine, settings, bus)
    return panel, engine, docking_service


def _project_with_receptor_and_ligand(ligand: MoleculeModel) -> ProjectModel:
    project = ProjectModel(name="Test project")
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text="HEADER\nATOM\nEND\n", source_format="pdb"
    )
    project.macromolecules.append(receptor)
    project.molecules.append(ligand)
    return project


def _has_nonzero_z_coordinate(mol) -> bool:
    conf = mol.GetConformer()
    return any(abs(conf.GetAtomPosition(i).z) > 1e-6 for i in range(mol.GetNumAtoms()))


def test_dock_click_prefers_3d_conformer_over_flat_2d_molblock(qapp):
    """Regression test: docking used to build the ligand Mol straight from
    the molecule's own (possibly 2D, all-zero-z) molblock via
    mol_from_model -- QuantumChemistryPanel already preferred a stored 3D
    conformer, and DockingPanel needed the identical fix (docking a flat
    structure against a 3D receptor is scientifically meaningless).

    `Chem.MolFromMolBlock` removes explicit Hs by default, so atom count
    alone can't distinguish the two sources once both are re-parsed -- the
    real, reliable signal is that the 2D editor's molblock has z=0 for
    every atom, while an embedded 3D conformer (essentially) never does.
    """
    panel, engine, docking_service = _make_panel()

    ligand = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ligand, "CCO")  # flat molblock, no conformer
    assert not _has_nonzero_z_coordinate(engine.mol_from_molblock(ligand.molblock))

    mol_3d = Chem.AddHs(engine.mol_from_smiles("CCO"))
    AllChem.EmbedMolecule(mol_3d, randomSeed=1)
    assert _has_nonzero_z_coordinate(mol_3d)
    ligand.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol_3d)))

    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    panel._on_dock_clicked()

    assert len(docking_service.requests) == 1
    used_mol = docking_service.requests[0]["ligand_mol"]
    assert _has_nonzero_z_coordinate(used_mol)


def test_dock_click_refuses_a_ligand_with_no_structure_at_all(qapp):
    panel, _, docking_service = _make_panel()
    ligand = MoleculeModel(display_name="Blank")  # no molblock, no conformers

    panel.set_project(_project_with_receptor_and_ligand(ligand))
    panel._receptor_combo.setCurrentIndex(0)
    panel._ligand_combo.setCurrentIndex(0)

    panel._on_dock_clicked()

    assert docking_service.requests == []
    assert "no structure" in panel._status_label.text().lower()


def test_the_panel_strips_the_ligand_that_defined_the_box():
    """A catalogue receptor records `ligand_code` in its metadata precisely
    so this can happen without the user knowing which residue defined the
    site. See `pose_analysis.is_stripped_residue` for the measurement."""
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.ui.panels.docking_panel import _box_defining_ligand_codes

    catalogue = MacromoleculeModel(metadata={"ligand_code": "MK1"})
    assert _box_defining_ligand_codes(catalogue) == ["MK1"]


def test_a_user_imported_receptor_has_nothing_stripped():
    """No catalogue entry means nothing knows which residue defined the
    box, and guessing would delete part of somebody's receptor."""
    from openchem.domain.macromolecule import MacromoleculeModel
    from openchem.ui.panels.docking_panel import _box_defining_ligand_codes

    assert _box_defining_ligand_codes(MacromoleculeModel()) == []
    assert _box_defining_ligand_codes(MacromoleculeModel(metadata={"ligand_code": " "})) == []
