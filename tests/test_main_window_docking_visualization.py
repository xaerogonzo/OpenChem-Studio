from __future__ import annotations

import time

from rdkit import Chem
from rdkit.Chem import AllChem

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.common import Provenance
from openchem.domain.docking import DockingBox, DockingPoseModel, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.events.events import DockingResultReady

_RECEPTOR_PDB = (
    "ATOM      1  N   TYR A 652      11.104  13.207   2.845  1.00 20.00           N\n"
    "ATOM      2  CA  TYR A 652      11.999  12.040   2.945  1.00 20.00           C\n"
    "ATOM      3  N   PHE A 656      18.104  13.207   2.845  1.00 20.00           N\n"
    "END\n"
)


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _wait_until(qapp, predicate, timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    return _track(MainWindow(services, settings, session)), services, session


def _pose(metadata: dict) -> DockingPoseModel:
    ligand = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(ligand, randomSeed=1)
    return DockingPoseModel(
        pose_molblock=Chem.MolToMolBlock(ligand),
        binding_affinity_kcal_mol=-7.5,
        rmsd_lb=0.0,
        rmsd_ub=0.0,
        metadata=metadata,
    )


def _publish_result(qapp, services, session, metadata: dict) -> list[str]:
    receptor = MacromoleculeModel(
        display_name="Receptor", structure_text=_RECEPTOR_PDB, source_format="pdb"
    )
    session.project.macromolecules.append(receptor)
    result = DockingResultModel(
        ligand_molecule_uuid="lig",
        receptor_macromolecule_uuid=receptor.uuid,
        box=DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0)),
        poses=[_pose(metadata)],
        provenance=Provenance(created_by="core", method="vina"),
        engine="vina",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=8,
        seed=None,
    )
    return result


def test_docking_result_colours_the_binding_site(qapp, tmp_path):
    """The payoff for residue-target layers: a finished docking run colours
    the receptor residues the ligand actually interacts with, using the
    interaction analysis pose_analysis already recorded in pose.metadata."""
    window, services, session = _window(tmp_path)
    viewer = window._macromolecule_viewer

    fired: list[str] = []
    original = viewer._page.runJavaScript
    viewer._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    result = _publish_result(
        qapp, services, session,
        {"hbonds": [{"receptor_residue": "TYR652"}], "clashes": [{"receptor_residue": "PHE656"}]},
    )
    services.event_bus.publish(DockingResultReady(result=result))

    assert _wait_until(qapp, lambda: any("applyResidueColors" in js for js in fired))
    colouring = [js for js in fired if "applyResidueColors" in js][-1]
    assert '"TYR652": "#1976d2"' in colouring  # hydrogen bond -> blue
    assert '"PHE656": "#d32f2f"' in colouring  # steric clash -> red


def test_a_pose_with_no_interactions_clears_rather_than_leaving_stale_colours(qapp, tmp_path):
    """A clean pose must actively clear, not silently leave the previous
    pose's binding site still highlighted."""
    window, services, session = _window(tmp_path)
    viewer = window._macromolecule_viewer

    fired: list[str] = []
    original = viewer._page.runJavaScript
    viewer._page.runJavaScript = lambda js, *a, **k: (fired.append(js), original(js, *a, **k))[1]

    result = _publish_result(qapp, services, session, {"hbonds": [], "clashes": []})
    services.event_bus.publish(DockingResultReady(result=result))

    assert _wait_until(qapp, lambda: any("ResidueColors" in js for js in fired))
    assert any("clearResidueColors" in js for js in fired)
