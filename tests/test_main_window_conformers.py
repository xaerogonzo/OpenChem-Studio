from __future__ import annotations

from PySide6.QtCore import QThreadPool

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import ConformersReady, DescriptorComputed


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def _build_window(qapp, tmp_path) -> tuple[MainWindow, object]:
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)
    return window, services


def test_conformers_ready_makes_shape_descriptors_compute_for_real(qapp, tmp_path):
    """Regression test for Phase 14b: generating conformers must let shape
    descriptors see a real 3D structure instead of permanently reporting
    "needs a conformer" against the flat 2D molblock."""
    window, services = _build_window(qapp, tmp_path)

    states: dict[str, CacheState] = {}
    services.event_bus.subscribe(
        DescriptorComputed,
        lambda e: states.__setitem__(e.descriptor.descriptor_id, e.descriptor.cache_state)
        if e.descriptor.descriptor_id == "radius_of_gyration"
        else None,
    )

    molecule = MoleculeModel(display_name="Hexanol")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CCCCCCO")
    window.add_molecule(molecule)
    _drain(qapp)
    assert states.get("radius_of_gyration") == CacheState.FAILED  # flat 2D structure, no conformer yet

    conf_mol, energy = RDKitConformerProvider().generate_conformers(
        services.chemistry_engine.mol_from_model(molecule), num_conformers=1, optimize=True
    )[0]
    conformer = ConformerModel(molblock=services.chemistry_engine.mol_to_molblock(conf_mol), energy=energy)
    services.event_bus.publish(ConformersReady(molecule_uuid=molecule.uuid, conformers=[conformer]))
    _drain(qapp)

    assert states["radius_of_gyration"] == CacheState.COMPLETED
