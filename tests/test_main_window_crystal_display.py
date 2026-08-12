"""The deferred crystal draw, and what it is allowed to close over.

Both crystal display paths defer their draw by one event-loop turn so the
viewer tab is current before 3Dmol is asked to draw. Both used to do it
with `QTimer.singleShot(0, lambda: self._viewer3d.show_crystal(scene))`,
which is wrong twice over -- a bare single shot outlives the window, and
a lambda capturing `self` is held strongly by PySide6.

**THE CANCEL-ON-DESTRUCTION HALF CANNOT BE TESTED HERE, and that is a
property of this suite rather than an omission.** `conftest.py` retains
every MainWindow for the whole session on purpose: destroying one
corrupts the C++ heap (0xc0000374, measured), and CLAUDE.md records two
separate attempts to destroy abandoned windows that both made the suite
crash more. So there is no way to build a window, kill it and watch a
pending shot not fire -- the killing is the thing that is forbidden.
`PropertyPanel._reveal_pending_result` has that behavioural guard, in
`test_property_panel_result_rows.py`, because a panel CAN be disposed.

What is left is the structural check below, which is this project's
usual answer for a property that cannot be reached behaviourally (see
`test_a_selection_is_never_forwarded_as_a_raw_ketcher_id`), plus the
live-payload test, which is a real behaviour change and testable.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.crystal import CrystalModel
from openchem.events.events import CrystalSelected

_FIXTURES = Path(__file__).parent / "fixtures" / "cif"
_SOURCE = Path(__file__).resolve().parents[1] / "src" / "openchem" / "app" / "main_window.py"

_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    """Closed, never destroyed -- see the module docstring and the
    retainer in `conftest.py`."""
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _make_window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    return _track(MainWindow(services, settings, SessionManager()))


def _add_crystal(window, cif_name: str) -> CrystalModel:
    model = CrystalModel(
        display_name=cif_name,
        cif_text=(_FIXTURES / cif_name).read_text(encoding="utf-8"),
        source_name=cif_name,
    )
    window._session.project.crystals.append(model)
    return model


def test_the_superseded_crystal_is_never_drawn(qapp, tmp_path, monkeypatch):
    """Two selections in one turn must draw the SECOND crystal, never the
    first.

    The draw is deferred, so with the payload captured at schedule time
    the first shot drew a crystal the user had already navigated away
    from. That is not merely a wasted frame: `_on_crystal_site_clicked`
    answers clicks against `_crystal_scene`, so in that window the viewer
    shows one cell while a click on it is resolved against another -- the
    index-space mismatch this project has been bitten by more than once.
    Reading the attribute at fire time closes it.

    Both crystals are asserted to produce DIFFERENT scenes first. Two
    fixtures that happened to give the same atom count would make the
    assertion below vacuous.
    """
    window = _make_window(tmp_path)
    first = _add_crystal(window, "1004002.cif")
    second = _add_crystal(window, "1511792.cif")

    drawn: list[int] = []
    monkeypatch.setattr(
        window._viewer3d, "show_crystal", lambda scene: drawn.append(len(scene["atoms"]))
    )

    # Selected without turning the event loop between them, which is what
    # puts two shots in flight at once.
    window._on_crystal_selected(CrystalSelected(crystal_uuid=first.uuid))
    first_scene_atoms = len(window._crystal_scene["atoms"])
    window._on_crystal_selected(CrystalSelected(crystal_uuid=second.uuid))
    second_scene_atoms = len(window._crystal_scene["atoms"])
    assert first_scene_atoms != second_scene_atoms, "the two fixtures are indistinguishable"

    QCoreApplication.processEvents()

    assert drawn, "nothing was drawn at all, so this proves nothing"
    assert first_scene_atoms not in drawn, "a superseded crystal reached the viewer"
    assert set(drawn) == {second_scene_atoms}


def test_the_crystal_draw_is_never_scheduled_with_a_lambda(qapp):
    """The half that cannot be tested by destroying a window.

    A `QTimer.singleShot` given a bare callable is tied to nothing, so it
    fires against a freed `_viewer3d` when the window dies inside the
    one-turn deferral; and a lambda capturing `self` is held STRONGLY by
    PySide6, rooting the window (see `tests/test_qt_object_disposal.py`).
    The three-argument form fixes both: Qt disconnects a context-bound
    shot when the context object is destroyed, and a bound method is held
    weakly.

    Asserts over EVERY `QTimer.singleShot` in the window rather than the
    two known sites, so a third one added later has to make the same
    choice deliberately.
    """
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    shots = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "singleShot"
    ]

    assert len(shots) >= 2, "the crystal draws vanished; this guard is now testing nothing"
    for shot in shots:
        where = f"main_window.py:{shot.lineno}"
        assert not any(isinstance(arg, ast.Lambda) for arg in shot.args), (
            f"{where}: a lambda capturing self is held strongly by PySide6"
        )
        assert len(shot.args) == 3, (
            f"{where}: pass `self` as the context object, or the shot outlives the window"
        )
        context = shot.args[1]
        assert isinstance(context, ast.Name) and context.id == "self", (
            f"{where}: the context object must be the window itself"
        )
