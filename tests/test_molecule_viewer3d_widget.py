from __future__ import annotations

from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.services.conformer_service import ConformerService
from openchem.services.measurement_service import MeasurementService
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import VisualizationLayer
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget


class FakeViewerBackend(ViewerBackend):
    """Records calls instead of driving a real QWebEngineView -- the
    widget's own `backend=` constructor parameter exists for exactly this
    kind of fast, isolated test."""

    def __init__(self) -> None:
        super().__init__()
        self.applied_layers: list[VisualizationLayer | None] = []
        self.loaded_molblocks: list[str] = []
        #: One entry per load, so a test can assert whether the camera was
        #: to be kept -- the whole of what makes conformers comparable.
        self.structure_keys: list[object] = []

    def load_conformer(self, molblock: str, structure_key: object = None) -> None:
        self.loaded_molblocks.append(molblock)
        self.structure_keys.append(structure_key)

    def set_style(self, style: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def apply_visualization(self, layer: VisualizationLayer | None) -> None:
        self.applied_layers.append(layer)

    def widget(self) -> QWidget:
        return QWidget()


def _make_widget(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    conformer_service = ConformerService(bus, engine)
    measurement_service = MeasurementService(engine)
    backend = FakeViewerBackend()
    widget = MoleculeViewer3DWidget(conformer_service, measurement_service, bus, backend=backend)
    return widget, backend, bus


def _molecule_with_conformer() -> MoleculeModel:
    model = MoleculeModel(display_name="Test")
    model.conformers = [ConformerModel(molblock="fake molblock", method="rdkit")]
    return model


def test_widget_has_no_color_by_dropdown(qapp):
    """Phase 23: per-property colouring moved out of this widget entirely --
    it predated CalculatorRegistry and hardcoded two properties, which the
    registry-driven Calculator Inspector now supersedes generically. This
    widget is style/navigation/measurement only."""
    widget, _backend, _bus = _make_widget(qapp)

    assert not hasattr(widget, "_color_by_combo")
    assert not hasattr(widget, "_per_atom_datasets")


def test_widget_never_applies_a_visualization_layer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())

    assert backend.applied_layers == []


def test_loading_a_molecule_loads_its_first_conformer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())

    assert backend.loaded_molblocks == ["fake molblock"]


def test_switching_conformer_loads_the_next_molblock(qapp):
    widget, backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)

    widget._show_next_conformer()

    assert backend.loaded_molblocks[-1] == "conf-2"
    assert "2/2" in widget._status_label.text()


def test_switching_back_returns_to_the_previous_conformer(qapp):
    widget, backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)
    widget._show_next_conformer()

    widget._show_previous_conformer()

    assert backend.loaded_molblocks[-1] == "conf-1"


def test_molecule_with_no_conformers_reports_none(qapp):
    widget, backend, _bus = _make_widget(qapp)

    widget.set_molecule(MoleculeModel(display_name="Empty"))

    assert widget._status_label.text() == "No conformers"
    assert backend.loaded_molblocks == []


def test_use_in_2d_editor_offers_the_conformer_that_is_on_screen(qapp):
    """The way back, and the failure mode it has to avoid.

    Emitting `conformers[0]` works perfectly for anyone who never pressed
    `>`, and silently hands over the wrong geometry for anyone who did --
    a redraw that succeeds while describing a different conformer than
    the one on screen. So this navigates first.
    """
    widget, _backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="conf-1", method="rdkit"),
        ConformerModel(molblock="conf-2", method="rdkit"),
    ]
    widget.set_molecule(molecule)
    offered: list[tuple] = []
    widget.conformer_adopted.connect(lambda mb, view: offered.append((mb, view)))

    widget._show_next_conformer()
    widget._use_button.click()

    assert [mb for mb, _view in offered] == ["conf-2"]


def test_use_in_2d_editor_is_disabled_with_nothing_to_use(qapp):
    """A button that is present and does nothing is the failure this
    whole line of work keeps finding -- it is how the duplicated periodic
    table was reported. Both directions, because a gate that never opens
    passes an assertion written one way."""
    widget, _backend, _bus = _make_widget(qapp)

    widget.set_molecule(MoleculeModel(display_name="Empty"))
    assert not widget._use_button.isEnabled()

    widget.set_molecule(_molecule_with_conformer())
    assert widget._use_button.isEnabled()


def test_highlight_atoms_paints_and_clears(qapp):
    """The viewer half of hover-to-highlight.

    Wired to nothing yet -- see `ui/widgets/fact_view.py` for why the panel
    that would drive it is not adopted. Tested now so the API is known to
    work when it is.

    Safe to drive from a hover because this viewer applies no atom
    colouring of its own; there is no "Color by" layer to clobber and then
    fail to restore.
    """
    widget, backend, _bus = _make_widget(qapp)

    widget.highlight_atoms((1, 3))
    assert backend.applied_layers[-1].atom_colors == {1: "#ffb300", 3: "#ffb300"}

    widget.highlight_atoms(())
    assert backend.applied_layers[-1] is None


# --- a crystal is a different index space, and clicks must not cross ---------


class CrystalCapableBackend(FakeViewerBackend):
    """`load_crystal` is optional on a ViewerBackend -- Mol* predates
    crystals and simply does not have it -- so the fake needs its own
    subclass rather than growing the method for everybody."""

    def __init__(self) -> None:
        super().__init__()
        self.loaded_scenes: list[dict] = []

    def load_crystal(self, scene: dict) -> None:
        self.loaded_scenes.append(scene)


_SCENE = {
    "atoms": [
        {"element": "Na", "x": 0.0, "y": 0.0, "z": 0.0, "site": "Na1", "occupancy": 1.0},
        {"element": "Cl", "x": 2.8, "y": 0.0, "z": 0.0, "site": "Cl1", "occupancy": 1.0},
    ],
    "edges": [],
    "axes": [],
    "name": "fixture",
}


def _crystal_widget(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    widget = MoleculeViewer3DWidget(
        ConformerService(bus, engine),
        MeasurementService(engine),
        bus,
        backend=CrystalCapableBackend(),
    )
    return widget, widget._backend


def test_a_crystal_click_never_reaches_the_molecular_measurement(qapp):
    """**This was live.** `show_crystal` did not clear the molecule, so
    two clicks on a unit cell ran the distance measurement against
    whatever conformer happened to be loaded -- correct arithmetic on the
    wrong object, reported as a plain number in the readout."""
    widget, backend = _crystal_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())
    widget.show_crystal(_SCENE)

    backend.atoms_selected.emit([0])
    backend.atoms_selected.emit([1])

    assert widget._measurement_label.text() == ""


def test_a_crystal_click_does_not_reach_the_atom_inspector(qapp):
    """A crystal atom and a molecular atom that share index 7 are not the
    same object. The inspector was spared before this only because
    `_atom_is_in_report` refuses out-of-range indices, which is luck."""
    widget, backend = _crystal_widget(qapp)
    atom_clicks: list[int] = []
    site_clicks: list[int] = []
    widget.atom_clicked.connect(atom_clicks.append)
    widget.crystal_site_clicked.connect(site_clicks.append)
    widget.show_crystal(_SCENE)

    backend.atoms_selected.emit([1])

    assert atom_clicks == []
    assert site_clicks == [1]


def test_a_molecule_loaded_after_a_crystal_gets_its_clicks_back(qapp):
    """The mirror image of the bug above, and the reason `set_molecule`
    clears the scene: a molecule shown after a unit cell must stop
    routing clicks into a scene nobody is drawing."""
    widget, backend = _crystal_widget(qapp)
    atom_clicks: list[int] = []
    site_clicks: list[int] = []
    widget.atom_clicked.connect(atom_clicks.append)
    widget.crystal_site_clicked.connect(site_clicks.append)

    widget.show_crystal(_SCENE)
    widget.set_molecule(_molecule_with_conformer())
    backend.atoms_selected.emit([1])

    assert site_clicks == []
    assert atom_clicks == [1]


def test_showing_a_crystal_drops_a_half_finished_measurement(qapp):
    """One click on a molecule, then a crystal import: the pending atom
    must not pair up with a crystal index on the next click."""
    widget, backend = _crystal_widget(qapp)
    widget.set_molecule(_molecule_with_conformer())
    backend.atoms_selected.emit([0])
    assert widget._selected_atoms == [0]

    widget.show_crystal(_SCENE)

    assert widget._selected_atoms == []


# --- comparing conformers ---------------------------------------------------


def _two_conformers(energies=(70.95, 71.50), stamps=(1.0, 1.0)) -> MoleculeModel:
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock=f"conf-{i}", method="rdkit", energy=e, timestamp=t)
        for i, (e, t) in enumerate(zip(energies, stamps), start=1)
    ]
    return molecule


def test_stepping_between_conformers_keeps_the_camera(qapp):
    """THE DEFECT THIS EXISTS FOR.

    Reported as: "I arranged the first conformer in 1 row, then in the
    second conformer I moved it a certain way, then moved back to the first
    conformer, and it was once again in a different way."

    The backend keeps the camera when consecutive loads carry the SAME
    structure key, so the assertion is that stepping does not change it.
    Asserted as equality across all three loads rather than 'not None',
    which would pass against a key that changed every time.
    """
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_two_conformers())

    widget._show_next_conformer()
    widget._show_previous_conformer()

    assert len(backend.structure_keys) == 3
    assert len(set(backend.structure_keys)) == 1, backend.structure_keys
    assert backend.structure_keys[0] is not None


def test_a_different_molecule_does_not_inherit_the_camera(qapp):
    """The other half, and the reason the key is not simply a constant.

    A key that never changed would keep the camera forever, so an
    unrelated molecule would arrive at whatever angle the last one was
    left at -- with no guarantee it is even in frame.
    """
    widget, backend, _bus = _make_widget(qapp)
    widget.set_molecule(_two_conformers())
    first = backend.structure_keys[-1]

    widget.set_molecule(_two_conformers())

    assert backend.structure_keys[-1] != first


def test_regenerating_conformers_does_not_inherit_the_camera(qapp):
    """Same molecule, new batch. The timestamps are what tell them apart --
    `_ConformerGenerationTask` stamps one `Provenance` across a run, so a
    fresh run carries different ones.

    Without this the key would be the molecule uuid alone, and a
    regenerated set of a DIFFERENT shape would be drawn at the old
    camera, possibly off screen.
    """
    widget, backend, _bus = _make_widget(qapp)
    molecule = _two_conformers(stamps=(1.0, 1.0))
    widget.set_molecule(molecule)
    before = backend.structure_keys[-1]

    molecule.conformers = _two_conformers(stamps=(2.0, 2.0)).conformers
    widget.set_molecule(molecule)

    assert backend.structure_keys[-1] != before


def test_the_energy_shown_is_relative_to_the_lowest(qapp):
    """`70.95` and `71.50` are raw MMFF numbers; nobody compares those to
    anything. The interesting figure is the 0.55 between them, and the
    reader should not have to do the subtraction."""
    widget, _backend, _bus = _make_widget(qapp)
    widget.set_molecule(_two_conformers(energies=(70.95, 71.50)))

    assert "lowest energy" in widget._status_label.text()

    widget._show_next_conformer()

    assert "+0.55 kcal/mol" in widget._status_label.text()
    assert "71.50" not in widget._status_label.text()


def test_the_absolute_energy_is_kept_in_the_tooltip(qapp):
    """Moved, not dropped -- it is what a force-field log would print, and
    somebody reconciling against one needs it."""
    widget, _backend, _bus = _make_widget(qapp)
    widget.set_molecule(_two_conformers(energies=(70.95, 71.50)))

    assert "70.95" in widget._status_label.toolTip()


def test_a_conformer_with_no_energy_says_so_rather_than_computing_a_delta(qapp):
    """A missing energy is not zero, and `+0.00 kcal/mol` would claim it
    is the lowest.

    **The set MIXES energies with a missing one**, which is what makes this
    discriminating. With every energy missing, "is this one None" and "are
    there any energies at all" are the same question, and a version that
    checked only the second passed -- measured, as a surviving mutation.
    Here the second is False and the first is True, so they come apart.
    """
    widget, _backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock="c1", method="rdkit", energy=70.95),
        ConformerModel(molblock="c2", method="rdkit", energy=None),
    ]

    widget.set_molecule(molecule)
    widget._show_next_conformer()

    assert "n/a" in widget._status_label.text()


def test_the_viewer_shows_the_display_aligned_copy_not_the_stored_one(qapp):
    """THE PHASE-1 FIX, asserted where it is observable.

    Every other test in this file uses placeholder molblocks like
    "conf-1", which do not parse -- so the aligner returns them untouched
    and "aligned" and "retained" are the same string. A mutation that
    bypassed alignment entirely passed all of them.

    Real embedded conformers, in their own arbitrary frames, are the only
    thing that tells the two apart: what reaches the backend must differ
    from what is stored, and the stored copy must be unchanged.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCCCCCO"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xC0FFEE
    AllChem.EmbedMultipleConfs(mol, numConfs=2, params=params)
    AllChem.MMFFOptimizeMoleculeConfs(mol)
    molblocks = [Chem.MolToMolBlock(mol, confId=c.GetId()) for c in mol.GetConformers()]

    widget, backend, _bus = _make_widget(qapp)
    molecule = MoleculeModel(display_name="Hexanol")
    molecule.conformers = [
        ConformerModel(molblock=mb, method="rdkit", energy=float(i))
        for i, mb in enumerate(molblocks)
    ]

    widget.set_molecule(molecule)
    widget._show_next_conformer()

    assert backend.loaded_molblocks[-1] != molblocks[1], (
        "the viewer showed the stored conformer, so nothing was aligned"
    )
    assert molecule.conformers[1].molblock == molblocks[1], (
        "the stored conformer was mutated; display alignment must not do that"
    )


# --- the camera travels with the conformer, atomically -----------------------


class DeferredViewBackend(FakeViewerBackend):
    """A backend whose camera read does not answer until told to.

    Reading the camera is a round trip into a web page, so it IS
    asynchronous in production; a fake that answers immediately cannot
    exercise anything that happens in the gap.
    """

    def __init__(self, view=None) -> None:
        super().__init__()
        self.view = view
        self._pending = None

    def current_view(self, callback) -> None:
        self._pending = callback

    def answer(self) -> None:
        callback, self._pending = self._pending, None
        assert callback is not None, "nothing was waiting on the camera"
        callback(self.view)


def _deferred_widget(qapp, view=None):
    bus = EventBus()
    engine = ChemistryEngine()
    backend = DeferredViewBackend(view)
    widget = MoleculeViewer3DWidget(
        ConformerService(bus, engine), MeasurementService(engine), bus, backend=backend
    )
    return widget, backend


def test_the_camera_is_handed_over_with_the_conformer(qapp):
    """The whole of Phase 2: the drawing is made from what is on screen,
    which means the geometry AND the angle it is being viewed at."""
    camera = [0.0, 0.0, 0.0, 0.0, 0.0, 0.7071, 0.0, 0.7071]
    widget, backend = _deferred_widget(qapp, view=camera)
    widget.set_molecule(_two_conformers())
    adopted: list[tuple] = []
    widget.conformer_adopted.connect(lambda mb, v: adopted.append((mb, v)))

    widget._use_button.click()
    backend.answer()

    assert len(adopted) == 1
    assert adopted[0][1] == camera


def test_changing_conformer_while_the_camera_is_read_adopts_nothing(qapp):
    """THE RACE, and it is not detectable downstream.

    Pressing `>` while the camera read is in flight would otherwise adopt
    conformer 2 with conformer 1's camera -- a structure at an angle
    nobody was ever looking at, which is chemically valid and silently
    wrong. The snapshot is re-checked when the answer comes back.
    """
    widget, backend = _deferred_widget(qapp, view=[0.0] * 4 + [0.0, 0.0, 0.0, 1.0])
    widget.set_molecule(_two_conformers())
    adopted: list[tuple] = []
    widget.conformer_adopted.connect(lambda mb, v: adopted.append((mb, v)))

    widget._use_button.click()
    widget._show_next_conformer()
    backend.answer()

    assert adopted == []


def test_the_button_is_disabled_while_the_camera_is_being_read(qapp):
    """So the gesture cannot be repeated into the gap and queue two
    adoptions of the same thing. Re-enabled when the answer arrives,
    which is asserted too -- a button that never comes back is worse."""
    widget, backend = _deferred_widget(qapp)
    widget.set_molecule(_two_conformers())

    widget._use_button.click()
    assert not widget._use_button.isEnabled()

    backend.answer()
    assert widget._use_button.isEnabled()


def test_a_backend_with_no_camera_still_adopts(qapp):
    """`ViewerBackend.current_view` answers None by default, so a viewer
    that cannot report a camera produces an unrotated drawing rather than
    a dead button."""
    widget, _backend, _bus = _make_widget(qapp)
    widget.set_molecule(_two_conformers())
    adopted: list[tuple] = []
    widget.conformer_adopted.connect(lambda mb, v: adopted.append((mb, v)))

    widget._use_button.click()

    assert len(adopted) == 1
    assert adopted[0][1] is None


def test_adoption_hands_over_the_aligned_copy_not_the_stored_one(qapp):
    """The camera composes with the frame that is actually DRAWN.

    The viewer shows the display-aligned copy, so rotating the retained
    conformer -- which sits in its own arbitrary embedding frame -- by the
    on-screen camera would give a structure at some unrelated angle, while
    looking entirely plausible.

    Real embedded conformers, because a placeholder molblock does not
    parse and the aligner returns it untouched: with `"conf-1"` the
    aligned and retained copies are the same string and a mutation
    bypassing alignment passes. That is exactly what happened here.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCCCCCO"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xC0FFEE
    AllChem.EmbedMultipleConfs(mol, numConfs=2, params=params)
    AllChem.MMFFOptimizeMoleculeConfs(mol)
    molblocks = [Chem.MolToMolBlock(mol, confId=c.GetId()) for c in mol.GetConformers()]

    widget, backend = _deferred_widget(qapp)
    molecule = MoleculeModel(display_name="Hexanol")
    molecule.conformers = [
        ConformerModel(molblock=mb, method="rdkit", energy=float(i), timestamp=1.0)
        for i, mb in enumerate(molblocks)
    ]
    widget.set_molecule(molecule)
    adopted: list[tuple] = []
    widget.conformer_adopted.connect(lambda mb, v: adopted.append((mb, v)))

    widget._show_next_conformer()
    widget._use_button.click()
    backend.answer()

    assert len(adopted) == 1
    assert adopted[0][0] != molblocks[1], "the retained conformer was handed over unaligned"


# --- the gallery -------------------------------------------------------------


class GridBackend(FakeViewerBackend):
    """Records what the gallery asks the page to draw."""

    def __init__(self) -> None:
        super().__init__()
        self.grids: list[dict] = []
        self.matched: list[int] = []
        self.ensembles: list[list[tuple[str, str]]] = []
        self.left_grid = 0

    def load_conformer_grid(self, entries, rows, cols, linked=False, selected=None):
        self.grids.append(
            {"entries": list(entries), "rows": rows, "cols": cols,
             "linked": linked, "selected": list(selected or [])}
        )

    def match_grid_views(self, index: int) -> None:
        self.matched.append(index)

    def load_ensemble(self, entries) -> None:
        self.ensembles.append(list(entries))

    def leave_grid(self) -> None:
        self.left_grid += 1


def _gallery_widget(qapp, count: int = 8):
    bus = EventBus()
    engine = ChemistryEngine()
    backend = GridBackend()
    widget = MoleculeViewer3DWidget(
        ConformerService(bus, engine), MeasurementService(engine), bus, backend=backend
    )
    molecule = MoleculeModel(display_name="Test")
    molecule.conformers = [
        ConformerModel(molblock=f"conf-{i}", method="rdkit", energy=70.0 + i * 0.5,
                       timestamp=1.0)
        for i in range(count)
    ]
    widget.set_molecule(molecule)
    return widget, backend, molecule


def test_the_gallery_shows_a_page_of_conformers_at_once(qapp):
    """The ask: "all separate images possible... on the screen at the same
    time". Six by default, because the complaint was about comparing and
    six cells are big enough to compare in."""
    widget, backend, _molecule = _gallery_widget(qapp, count=8)

    widget._gallery_check.setChecked(True)

    assert backend.grids, "nothing was drawn"
    grid = backend.grids[-1]
    assert (grid["rows"], grid["cols"]) == (2, 3)
    assert len(grid["entries"]) == 6


def test_the_gallery_pages_rather_than_stepping_one_at_a_time(qapp):
    """`>` moves a PAGE in the gallery. Stepping one conformer would move
    the highlight without changing the picture five presses out of six."""
    widget, backend, _molecule = _gallery_widget(qapp, count=8)
    widget._gallery_check.setChecked(True)

    widget._show_next_conformer()

    grid = backend.grids[-1]
    assert [label for _mb, label in grid["entries"]][0].startswith("7")
    assert len(grid["entries"]) == 2, "the last page should hold what is left"


def test_paging_stops_at_the_ends(qapp):
    """Both ends, because an off-by-one at either produces an empty grid
    that looks like the gallery breaking."""
    widget, backend, _molecule = _gallery_widget(qapp, count=8)
    widget._gallery_check.setChecked(True)

    widget._show_previous_conformer()
    assert widget._page_start == 0

    widget._show_next_conformer()
    widget._show_next_conformer()
    assert widget._page_start == 6, "paged past the end"


def test_paging_at_an_end_does_not_rebuild_the_gallery(qapp):
    """**A REBUILD RESETS EVERY CELL'S CAMERA**, so pressing `<` on the
    first page must not trigger one -- it would wipe the arrangement the
    user had just made, in response to a key that did nothing.

    `_refresh_gallery` clamps the page as well, so the guard in the
    navigation looks redundant and a mutation removing it survived every
    other test here: the page index ends up identical either way. What
    differs is whether the grid is torn down and rebuilt, which is the
    thing worth asserting.
    """
    widget, backend, _molecule = _gallery_widget(qapp, count=8)
    widget._gallery_check.setChecked(True)
    drawn = len(backend.grids)

    widget._show_previous_conformer()

    assert len(backend.grids) == drawn, "the gallery was rebuilt for a no-op"


def test_lock_views_is_passed_through_and_is_off_by_default(qapp):
    """Independent rotation is the default -- it is what was asked for --
    and locking is the opt-in for comparing."""
    widget, backend, _molecule = _gallery_widget(qapp)
    widget._gallery_check.setChecked(True)
    assert backend.grids[-1]["linked"] is False

    widget._lock_check.setChecked(True)

    assert backend.grids[-1]["linked"] is True


def test_match_all_acts_on_the_selected_cell_in_page_coordinates(qapp):
    """The page holds cells 0..5 whatever conformers they are, so a
    selected conformer on the second page must not ask the page for a
    cell index it does not have."""
    widget, backend, _molecule = _gallery_widget(qapp, count=12)
    widget._gallery_check.setChecked(True)
    widget._show_next_conformer()          # page 2: conformers 6..11
    widget._on_grid_cell_clicked(2)        # the third cell of that page

    widget._match_button.click()

    assert widget._conformer_index == 8, "the click did not select conformer 9"
    assert backend.matched == [2], "match was asked for an absolute index"


def test_ticking_a_cell_is_not_the_same_as_selecting_it(qapp):
    """Two different gestures on one control. Clicking chooses what `<`,
    `>` and "Use in 2D Editor" act on; ticking marks a conformer for
    superimposition. Conflating them would make one impossible."""
    widget, _backend, _molecule = _gallery_widget(qapp)
    widget._gallery_check.setChecked(True)

    widget._on_grid_cell_toggled(1, True)

    assert widget._superimposed == {1}
    assert widget._conformer_index == 0, "ticking moved the selection"


def test_superimposing_ticked_conformers_uses_the_ensemble_path(qapp):
    """Reuses `load_ensemble`, which the Alignment panel already drives --
    superimposing structures in one frame is the same operation whether
    they are different molecules or conformers of one."""
    widget, backend, _molecule = _gallery_widget(qapp)
    widget._gallery_check.setChecked(True)
    widget._on_grid_cell_toggled(0, True)
    widget._on_grid_cell_toggled(2, True)

    widget._superimpose_button.click()

    assert len(backend.ensembles) == 1
    entries = backend.ensembles[0]
    assert len(entries) == 2
    assert len({colour for _mb, colour in entries}) == 2, "both drawn the same colour"


def test_superimposing_fewer_than_two_says_so_rather_than_drawing_nothing(qapp):
    """One structure superimposed on nothing is a blank change that reads
    as the button being broken."""
    widget, backend, _molecule = _gallery_widget(qapp)
    widget._gallery_check.setChecked(True)
    widget._on_grid_cell_toggled(0, True)

    widget._superimpose_button.click()

    assert backend.ensembles == []
    assert "two or more" in widget._measurement_label.text()


def test_leaving_the_gallery_tells_the_page(qapp):
    """The grid has its own container and canvas; without this the single
    viewer stays hidden behind it."""
    widget, backend, _molecule = _gallery_widget(qapp)
    widget._gallery_check.setChecked(True)

    widget._gallery_check.setChecked(False)

    assert backend.left_grid == 1


def test_a_new_molecule_clears_the_ticks_and_the_page(qapp):
    """Conformer indices mean something different for a different
    molecule, so carrying ticks over would superimpose whatever happened
    to sit at those positions."""
    widget, _backend, _molecule = _gallery_widget(qapp, count=12)
    widget._gallery_check.setChecked(True)
    widget._on_grid_cell_toggled(1, True)
    widget._show_next_conformer()

    widget.set_molecule(_two_conformers())

    assert widget._superimposed == set()
    assert widget._page_start == 0


def test_the_3d_view_gets_the_height_not_the_status_label(qapp):
    """THE VIEWER HAD BEEN HALF THE SIZE IT SHOULD BE.

    A QWebEngineView and a QLabel both report a `Preferred` vertical
    policy, so QVBoxLayout split the spare height evenly between them.
    Measured in the running app: a 698 px pane gave the 3D view 330 px and
    the one-line measurement readout the other 330. Nobody noticed until
    six conformers went into that space and every cell came out half as
    tall as it should be.

    Same shape as the `WrappedLabel` finding in the Properties panel: a
    one-line status claiming a panel's vertical stretch.

    **The widget is SHOWN and given a size**, because a layout that was
    never laid out reports nothing -- the same reason `repaint()` on an
    unshown widget paints nothing.
    """
    widget, _backend, _bus = _make_widget(qapp)
    widget.resize(900, 700)
    widget.show()
    qapp.processEvents()
    try:
        view_height = widget._backend.widget().height()
        label_height = widget._measurement_label.height()

        assert view_height > 4 * label_height, (
            f"the 3D view got {view_height} px against the label's {label_height}"
        )
        # Most of what is left after the toolbar. Not a tighter number,
        # because the toolbar's own height depends on the platform's
        # metrics and this fake backend's widget is not a real web view.
        # In the running app the figure is 644 of 698.
        assert view_height > 0.6 * widget.height(), (
            f"the 3D view got {view_height} px of {widget.height()}"
        )
    finally:
        widget.hide()


def test_paging_moves_the_selection_onto_the_new_page(qapp):
    """The page resets its own selected cell to the first one whenever the
    grid is rebuilt. A `_conformer_index` left pointing at another page
    would then take the CAMERA from cell 0 and the CONFORMER from
    somewhere else -- a structure at an angle nobody looked at, which is
    the same class of mismatch the adoption snapshot exists to prevent.
    """
    widget, _backend, _molecule = _gallery_widget(qapp, count=12)
    widget._gallery_check.setChecked(True)
    widget._on_grid_cell_clicked(1)
    assert widget._conformer_index == 1

    widget._show_next_conformer()

    assert widget._page_start == 6
    assert widget._conformer_index == 6, "the selection stayed on the previous page"
