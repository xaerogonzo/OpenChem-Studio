from __future__ import annotations

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel


def test_add_molecule_adds_to_project_and_selects_it(qapp, tmp_path):
    """Regression/coverage test for the UIRegistry.add_molecule extension
    (context.molecules.add in plugins/context.py) added for Phase 6 plugins
    that need to add a search/prediction result to the project.
    """
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)

    molecule = MoleculeModel(display_name="Aspirin", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O")
    window.add_molecule(molecule)

    assert session.project is not None
    assert session.project.find_molecule(molecule.uuid) is molecule
    assert session.selected_molecule_uuid == molecule.uuid

    window._undo_stack.undo()
    assert session.project.find_molecule(molecule.uuid) is None
