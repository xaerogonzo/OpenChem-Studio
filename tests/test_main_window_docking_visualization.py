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


# --- the search box overlay --------------------------------------------------


_SITE_PDB = (
    "HEADER    TEST\n"
    "HETATM    1 C1   LIG A 500      18.000   0.000   0.000  1.00 20.00           C\n"
    "HETATM    2 C2   LIG A 500      22.000   0.000   0.000  1.00 20.00           C\n"
    "HETATM    3 N1   LIG A 500      20.000   2.000   0.000  1.00 20.00           N\n"
    "HETATM    4 O1   LIG A 500      20.000  -2.000   0.000  1.00 20.00           O\n"
    "HETATM    5 CA   ALA A   1      20.000   0.000   4.000  1.00 20.00           C\n"
    "END\n"
)


def _with_receptor(tmp_path, qapp):
    """A window showing the Docking panel with a boxable receptor."""
    window, services, session = _window(tmp_path)
    window.add_macromolecule(
        MacromoleculeModel(
            display_name="Receptor with a site",
            structure_text=_SITE_PDB,
            source_format="pdb",
            metadata={"ligand_code": "LIG"},
        )
    )
    window._on_panel_chosen("Docking")
    qapp.processEvents()
    return window, services, session


def _box_calls(window) -> list[tuple]:
    """Record what the window ASKS THE VIEWER FOR.

    Recorded at the backend's own methods rather than at `runJavaScript`,
    deliberately: the viewer is created asynchronously, so before it is ready
    the backend correctly queues instead of emitting JS, and a JS-level spy
    sees nothing and reads as "the window drew no box". What the window is
    responsible for is calling the viewer correctly; whether the call is
    queued or issued belongs to the backend and is covered by
    `tests/test_molstar_viewer_backend.py`.
    """
    calls: list[tuple] = []
    viewer = window._macromolecule_viewer
    show, clear = viewer.show_search_box, viewer.clear_search_box
    viewer.show_search_box = lambda c, s: (calls.append(("show", tuple(c), tuple(s))), show(c, s))[1]
    viewer.clear_search_box = lambda: (calls.append(("clear",)), clear())[1]
    return calls


def _shows(calls) -> list[tuple]:
    return [c for c in calls if c[0] == "show"]


def test_showing_the_docking_panel_draws_the_box_and_hiding_it_clears(qapp, tmp_path):
    """The box follows the workflow it belongs to.

    Interaction analysis and structure checking put the same receptor on
    screen; a search region painted over it there describes a job the user
    is not doing.

    **Asserted through `isHidden()`, never `isVisible()`** -- the latter is
    False for every child of a window that has not been shown, so a test
    written with it would pass against a window that never drew anything.
    """
    window, _, _ = _with_receptor(tmp_path, qapp)
    assert not window._dock_by_panel_id("Docking").isHidden(), "setup: Docking is showing"

    fired = _box_calls(window)
    window._on_panel_chosen("Properties")
    qapp.processEvents()

    assert window._dock_by_panel_id("Docking").isHidden()
    assert ("clear",) in fired, "hiding Docking must clear the box"

    fired.clear()
    window._on_panel_chosen("Docking")
    qapp.processEvents()

    assert _shows(fired), "showing it again must redraw"


def test_editing_a_spinbox_redraws_the_overlay(qapp, tmp_path):
    window, _, _ = _with_receptor(tmp_path, qapp)
    fired = _box_calls(window)

    window._docking_panel._center_x.setValue(3.0)
    qapp.processEvents()

    assert _shows(fired), "a spinbox edit must redraw"
    assert _shows(fired)[-1][1][0] == 3.0, "and redraw with the NEW value"


def test_a_receptor_with_no_site_leaves_no_box_drawn(qapp, tmp_path):
    """No receptor selected means nothing to draw a box on."""
    window, _, _ = _window(tmp_path)
    window._on_panel_chosen("Docking")
    qapp.processEvents()
    fired = _box_calls(window)

    window._sync_docking_box_overlay()
    qapp.processEvents()

    assert ("clear",) in fired
    assert not _shows(fired)


def test_docking_box_has_one_authoritative_geometry_end_to_end(qapp, tmp_path):
    """THE central integrity invariant of this feature.

    The six spinboxes, `displayed_box()`, the box in the docking request and
    the geometry sent to the viewer must all be the same six numbers. They
    come from one accessor precisely so the box a user SEES, the box that
    RUNS and the box that is DRAWN cannot diverge -- `_box_source` is
    provenance and appears nowhere in the chain.

    Mutating `_sync_docking_box_overlay` to send an altered box fails here,
    which is what says the last link is really carrying the geometry rather
    than both sides reading the same fixture.
    """
    window, _, session = _with_receptor(tmp_path, qapp)
    panel = window._docking_panel

    displayed = panel.displayed_box()
    spinboxes = (
        (panel._center_x.value(), panel._center_y.value(), panel._center_z.value()),
        (panel._size_x.value(), panel._size_y.value(), panel._size_z.value()),
    )
    assert (displayed.center, displayed.size) == spinboxes

    fired = _box_calls(window)
    window._sync_docking_box_overlay()
    qapp.processEvents()
    drawn = _shows(fired)
    assert drawn, "setup: the overlay was drawn"
    _, center, size = drawn[-1]
    assert center == displayed.center
    assert size == displayed.size
