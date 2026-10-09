"""The idle web views are built on first use, not at launch.

Each `QWebEngineView` is a Chromium renderer (perf census F1: four were built at start,
about half of the process tree's ~1.08 GiB). Mol* (the Macromolecule tab) and the
Alignment panel's 3D view are not needed until a structure or an alignment exists.

**CONSTRUCTIONS ARE COUNTED BY NAME, NOT BY RAW `QWebEngineView` CALLS.** Qt creates views
of its own (pop-out windows, help), so a global count would tie this test to things
that are not the four application viewers. Each application construction site records
which viewer it is. The Qt object census stays supporting evidence in the perf census.

3Dmol's main viewer and Ketcher stay eager on purpose: the editor is the default tab, and
the 3D tab's first-show cost was measured and shown not to move by building it early.
"""

from __future__ import annotations

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.ui.widgets import ketcher_editor_backend, mol3d_viewer_backend, molstar_viewer_backend
from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend
from openchem.ui.visualization import ResidueColorLayer

_PDB = "HEADER\nATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N\nEND\n"

_WINDOWS: list = []


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


@pytest.fixture
def constructions(monkeypatch):
    """The named viewers built so far, in order. A view built from a site not named
    here would not be recorded -- which is why `test_nothing_else_builds_a_view_*`
    also checks the raw count against the named one."""
    events: list[str] = []
    raw: list[str] = []

    def counting(label):
        class Counting(QWebEngineView):
            def __init__(self, *args, **kwargs):
                raw.append(label)
                super().__init__(*args, **kwargs)

        return Counting

    monkeypatch.setattr(ketcher_editor_backend, "QWebEngineView", counting("ketcher"))
    monkeypatch.setattr(molstar_viewer_backend, "QWebEngineView", counting("molstar"))
    monkeypatch.setattr(mol3d_viewer_backend, "QWebEngineView", counting("3dmol"))

    real_init = mol3d_viewer_backend.Mol3DViewerBackend.__init__

    def named_init(self, parent=None):
        # Which application viewer is this? The same backend class serves the main 3D
        # tab and the Alignment panel, so name it by who holds it.
        events.append(f"3dmol:{type(parent).__name__}")
        real_init(self, parent)

    monkeypatch.setattr(mol3d_viewer_backend.Mol3DViewerBackend, "__init__", named_init)
    real_ketcher = ketcher_editor_backend.KetcherEditorBackend.__init__

    def ketcher_init(self, parent=None):
        events.append("ketcher")
        real_ketcher(self, parent)

    monkeypatch.setattr(ketcher_editor_backend.KetcherEditorBackend, "__init__", ketcher_init)
    real_molstar = MolStarViewerBackend.ensure_built

    def molstar_build(self):
        was_built = self.is_built
        real_molstar(self)
        if not was_built and self.is_built:
            events.append("molstar")

    monkeypatch.setattr(MolStarViewerBackend, "ensure_built", molstar_build)
    return events, raw


def _window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    window = MainWindow(services, settings, SessionManager())
    _WINDOWS.append(window)
    return window


# -- the application: what a launch builds -------------------------------------------------


def test_a_launch_builds_the_editor_and_the_3d_viewer_and_nothing_else(qapp, tmp_path, constructions):
    events, raw = constructions
    window = _window(tmp_path)

    assert sorted(events) == ["3dmol:MoleculeViewer3DWidget", "ketcher"], events
    assert not window._macromolecule_viewer.is_built
    assert not window._alignment_panel.viewer_is_built
    # Every view that was really constructed is one of the named two.
    assert sorted(raw) == ["3dmol", "ketcher"], raw


def test_using_the_macromolecule_viewer_builds_it_once(qapp, tmp_path, constructions):
    events, _raw = constructions
    window = _window(tmp_path)
    before = list(events)

    window.add_macromolecule(MacromoleculeModel(display_name="R", structure_text=_PDB, source_format="pdb"))
    window.add_macromolecule(MacromoleculeModel(display_name="R2", structure_text=_PDB, source_format="pdb"))

    assert events[len(before):] == ["molstar"]
    assert window._center_tabs.currentWidget() is window._macromolecule_viewer.widget()


# -- Mol*: one stable container, one construction path -----------------------------------------


def test_the_container_is_stable_and_asking_for_it_builds_nothing(qapp, constructions):
    events, raw = constructions
    backend = MolStarViewerBackend()

    first = backend.widget()
    assert backend.widget() is first
    assert not backend.is_built and raw == [] and events == []
    # The placeholder carries no renderer, page, channel or bridge.
    assert backend._view is None and backend._page is None
    assert not hasattr(backend, "_channel") and not hasattr(backend, "_bridge")
    assert first.layout().count() == 0


def test_state_queued_before_a_view_exists_does_not_build_one(qapp, constructions):
    """`show_search_box` and the residue colouring are called on every Docking show and every
    pose; neither is a reason to start a renderer. They queue in the backend's existing slots."""
    events, raw = constructions
    backend = MolStarViewerBackend()

    backend.show_search_box((1.0, 2.0, 3.0), (10.0, 10.0, 10.0))
    backend.clear_search_box()
    backend.apply_visualizations([ResidueColorLayer(name="H-bonds", residue_colors={"ALA1": "#1976d2"})])
    backend.clear()

    assert not backend.is_built and raw == [], "queueing or clearing must not construct a view"
    assert backend._pending_search_box is molstar_viewer_backend._NOTHING_PENDING
    assert backend._pending_layers is molstar_viewer_backend._NOTHING_PENDING


def test_a_structure_builds_the_view_on_demand_and_the_queues_are_the_existing_ones(qapp, constructions):
    events, raw = constructions
    backend = MolStarViewerBackend()
    backend.show_search_box((1.0, 2.0, 3.0), (10.0, 10.0, 10.0))
    backend.apply_visualizations([ResidueColorLayer(name="H-bonds", residue_colors={"ALA1": "#1976d2"})])

    backend.load_macromolecule(_PDB, "pdb")
    backend.load_additional_structure(_PDB, "pdb", "ligand")

    assert raw == ["molstar"] and backend.is_built
    # Not ready yet, so everything is still held in the backend's own slots, in order,
    # exactly once -- no second queue sits in front of them.
    assert [call[3] for call in backend._pending_calls] == [False, True]
    assert backend._pending_layers == {"ALA1": "#1976d2"}
    assert backend._pending_search_box == ((1.0, 2.0, 3.0), (10.0, 10.0, 10.0))


@pytest.mark.parametrize("order", ["show_then_load", "load_then_show"])
def test_either_first_use_constructs_exactly_one_view(qapp, constructions, order):
    events, raw = constructions
    backend = MolStarViewerBackend()
    container = backend.widget()

    if order == "show_then_load":
        container.show()
        assert backend.is_built and raw == ["molstar"], "showing the container is a first use"
        backend.load_macromolecule(_PDB, "pdb")
    else:
        backend.load_macromolecule(_PDB, "pdb")
        assert raw == ["molstar"], "a structure is a first use"
        container.show()

    assert raw == ["molstar"], "the other trigger must not build a second view"
    view = backend._view
    backend.ensure_built()
    container.hide()
    container.show()
    assert backend._view is view and raw == ["molstar"]
    assert container.layout().count() == 1


def test_a_failed_build_leaves_the_container_valid_and_retryable(qapp, monkeypatch):
    attempts = {"n": 0}
    real = molstar_viewer_backend.QWebEngineView

    class Flaky(real):
        def __init__(self, *args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("no GPU process")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(molstar_viewer_backend, "QWebEngineView", Flaky)
    backend = MolStarViewerBackend()
    container = backend.widget()

    with pytest.raises(RuntimeError):
        backend.ensure_built()
    assert not backend.is_built and container.layout().count() == 0

    backend.ensure_built()
    assert backend.is_built and container.layout().count() == 1, "a retry must not leave two views"
    assert backend.widget() is container


# -- the Alignment panel: built on first SHOW ----------------------------------------------------


def _panel(qapp):
    from openchem.events.base import EventBus
    from openchem.ui.panels.alignment_panel import AlignmentPanel

    class Service:
        def start_alignment(self, *a, **k):
            raise AssertionError("not used here")

        def is_running(self):
            return False

    bus = EventBus()
    return AlignmentPanel(Service(), bus), bus


def test_the_alignment_panel_builds_its_view_on_first_show_only(qapp, constructions):
    events, raw = constructions
    panel, _bus = _panel(qapp)

    assert not panel.viewer_is_built and raw == [], "constructing the panel must not ask for a view"
    assert panel._viewer_container.layout().count() == 0

    panel.show()
    assert panel.viewer_is_built and raw == ["3dmol"]
    assert events == ["3dmol:AlignmentPanel"]
    view = panel._viewer
    panel.hide()
    panel.show()
    assert panel._viewer is view and raw == ["3dmol"], "re-showing must not rebuild"
    panel.close()


def test_an_ensemble_that_arrives_before_the_first_show_is_drawn_at_build(qapp, constructions):
    from openchem.domain.alignment import EnsembleEntry
    from openchem.events.events import EnsembleAlignmentReady

    panel, bus = _panel(qapp)
    bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="u",
            entries=[EnsembleEntry(label="ref", molblock="REF"), EnsembleEntry(label="a", molblock="A", score=1.0, rmsd=0.2)],
            method="mcs",
            accuracy="Fast",
        )
    )
    assert not panel.viewer_is_built, "an arriving result is not a show"

    sent: list = []
    real = mol3d_viewer_backend.Mol3DViewerBackend.load_ensemble
    mol3d_viewer_backend.Mol3DViewerBackend.load_ensemble = lambda self, entries: sent.append(list(entries))
    try:
        panel.show()
    finally:
        mol3d_viewer_backend.Mol3DViewerBackend.load_ensemble = real
    assert [molblock for molblock, _c in sent[0]] == ["REF", "A"], "drawn once, at build"
    assert len(sent) == 1
    panel.close()


def test_style_and_colour_chosen_before_the_first_show_are_applied_at_build(qapp, constructions, monkeypatch):
    panel, _bus = _panel(qapp)
    panel._style_combo.setCurrentText("sphere")
    panel._color_mode_combo.setCurrentIndex(1)
    seen: dict[str, object] = {}
    monkeypatch.setattr(mol3d_viewer_backend.Mol3DViewerBackend, "set_style", lambda self, s: seen.__setitem__("style", s))
    monkeypatch.setattr(
        mol3d_viewer_backend.Mol3DViewerBackend, "set_ensemble_color_mode", lambda self, m: seen.__setitem__("mode", m)
    )

    panel.show()

    assert seen == {"style": "sphere", "mode": "element"}
    panel.close()


def test_the_eager_views_stay_eager(qapp, tmp_path, constructions):
    """A future 'make every web view lazy' pass must not take these two with it."""
    events, _raw = constructions
    _window(tmp_path)
    assert "ketcher" in events and "3dmol:MoleculeViewer3DWidget" in events
