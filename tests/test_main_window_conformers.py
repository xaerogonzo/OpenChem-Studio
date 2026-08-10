from __future__ import annotations

from PySide6.QtCore import QThreadPool

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import ConformersReady, DescriptorComputed


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


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
    window = _track(MainWindow(services, settings, session))
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


def _molecule_with_real_conformer(services, smiles: str = "CCCCCCO") -> MoleculeModel:
    molecule = MoleculeModel(display_name="Hexanol")
    services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
    conf_mol, energy = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformers(
        services.chemistry_engine.mol_from_model(molecule), num_conformers=1, optimize=True
    )[0]
    molecule.conformers = [
        ConformerModel(
            molblock=services.chemistry_engine.mol_to_molblock(conf_mol), energy=energy
        )
    ]
    return molecule


def test_adopting_a_conformer_reloads_the_editor_explicitly(qapp, tmp_path):
    """THE LOAD-BEARING LINE OF THE WHOLE FEATURE.

    `MoleculeEditorWidget._on_molecule_changed` compares CANONICAL
    SMILES before reloading the canvas, deliberately, so that an edit
    does not yank the drawing out from under whoever made it. Adopting a
    conformer changes coordinates and nothing else -- by design, since
    explicit hydrogens in the drawing would change what eight
    calculators report -- so that comparison correctly declines, and
    without an explicit reload the redrawn structure never reaches the
    canvas at all.

    That failure is silent: the model updates, the undo stack grows, the
    status bar says it worked, and the drawing does not move. So the
    assertion is on the EDITOR being told, not on the model.
    """
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule_with_real_conformer(services)
    window.add_molecule(molecule)
    _drain(qapp)

    loaded: list[object] = []
    window._editor.set_molecule = lambda m: loaded.append(m)

    window._adopt_conformer(molecule.conformers[0].molblock)

    assert loaded == [molecule]


def test_undoing_an_adopted_conformer_reaches_the_canvas_too(qapp, tmp_path):
    """THE HALF THAT WAS MISSING, found by driving the real app.

    With the reload done once at the call site, adopting redrew the
    canvas and Ctrl+Z reverted the model while the canvas went on showing
    the adopted drawing -- first atom at 17.6739, -6.2560 in both states.
    The model and the picture disagreed, with the picture winning.

    Redo as well as undo, because neither comes back through
    `_adopt_conformer` and a fix that covers one direction looks
    identical to a fix that covers both until it is tried.
    """
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule_with_real_conformer(services)
    window.add_molecule(molecule)
    _drain(qapp)

    # BEFORE the adopt, because the command captures the callback when it
    # is constructed -- patching afterwards leaves it holding the real
    # method and the undo silently goes unobserved. That cost a run.
    loaded: list[object] = []
    window._editor.set_molecule = lambda m: loaded.append(m)

    window._adopt_conformer(molecule.conformers[0].molblock)
    _drain(qapp)
    assert loaded == [molecule], "the adopt itself did not reload the canvas"

    window._undo_stack.undo()
    _drain(qapp)
    assert loaded == [molecule] * 2, "undo did not reload the canvas"

    window._undo_stack.redo()
    _drain(qapp)
    assert loaded == [molecule] * 3, "redo did not reload the canvas"


def test_adopting_a_conformer_is_one_undoable_step(qapp, tmp_path):
    """One step, and it really reverses.

    A redraw that cannot be undone is a change the user cannot refuse,
    and this one is reachable from a single click in a panel they may
    have been only browsing.
    """
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule_with_real_conformer(services)
    window.add_molecule(molecule)
    _drain(qapp)
    before = molecule.molblock
    depth = window._undo_stack.index()

    window._adopt_conformer(molecule.conformers[0].molblock)
    _drain(qapp)
    redrawn = molecule.molblock

    assert window._undo_stack.index() == depth + 1
    assert redrawn != before, "nothing changed, so the undo below would prove nothing"

    window._undo_stack.undo()
    _drain(qapp)

    assert molecule.molblock == before


def test_adopting_a_conformer_shows_the_editor(qapp, tmp_path):
    """A button labelled "Use in 2D Editor" that leaves you on the 3D tab
    is the navigation-claims-one-thing problem the panel rail exists to
    avoid. Starts on the viewer, so a test against a window that happened
    to be on the editor already cannot pass by default."""
    window, services = _build_window(qapp, tmp_path)
    molecule = _molecule_with_real_conformer(services)
    window.add_molecule(molecule)
    _drain(qapp)
    window._center_tabs.setCurrentWidget(window._viewer3d)

    window._adopt_conformer(molecule.conformers[0].molblock)
    _drain(qapp)

    assert window._center_tabs.currentWidget() is window._editor
