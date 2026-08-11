from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.common import CacheState
from openchem.ui.widgets.flow_layout import flow_row
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersChanged
from openchem.services.conformer_service import ConformerService
from openchem.services.measurement_service import MeasurementService
from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import (
    SURFACE_REPRESENTATION_LABELS,
    SURFACE_REPRESENTATIONS,
    SurfaceLayer,
    VisualizationLayer,
)
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend


logger = logging.getLogger("openchem.ui")

#: Gallery layouts, label -> (rows, cols).
#:
#: **The ceiling is legibility, not performance.** Measured against the
#: real bundle: the whole grid shares ONE WebGL context at every size, and
#: redraw costs 1 ms at 12 cells and 5 ms at 100. Building is linear and
#: small (4 cells 91 ms, 12 cells 175 ms, 100 cells 1481 ms). What breaks
#: down is the picture -- 100 cells in a 1000x700 pane is 100x70 px each,
#: which nobody can compare shapes in. So this stops at 12 and pages.
_GALLERY_SIZES = {
    "2 x 2": (2, 2),
    "2 x 3": (2, 3),
    "3 x 3": (3, 3),
    "3 x 4": (3, 4),
}

#: 2 x 3. The complaint was about COMPARING, so the default favours cells
#: big enough to compare in over the largest number of thumbnails.
_DEFAULT_GALLERY_SIZE = "2 x 3"

#: Amber, which is not on the diverging red/blue scale the per-atom
#: layers use -- so a transient hover cannot be mistaken for data.
_HIGHLIGHT_COLOUR = "#ffb300"

#: Colours for superimposed conformers. Qualitative and colour-blind safe
#: (Okabe-Ito), because the whole point is telling several structures
#: apart at a glance.
_ENSEMBLE_COLOURS = (
    "#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9",
)


class MoleculeViewer3DWidget(QWidget):
    """Hosts a ViewerBackend (3Dmol.js today) for the active molecule's
    conformers, plus a small toolbar for style/navigation/generation and a
    click-two-atoms distance measurement readout.

    Never touches RDKit directly: generation goes through ConformerService;
    turning the result into a persisted, undoable change is MainWindow's
    job via SetConformersCommand — this widget only calls the service and
    reacts to events, matching how the other panels stay thin.

    Deliberately has no per-property colouring of its own (Phase 23): the
    old "Color by" dropdown here predated `CalculatorRegistry` and
    hardcoded exactly two properties, which the registry-driven Calculator
    Inspector now supersedes generically — every calculator gets a real
    2D+3D projection there instead of two of them getting one here.
    """

    #: One atom, each time the user clicks one in the 3D view. The
    #: backend already reported clicks for the distance measurement;
    #: this exposes them to anything else that wants them, without
    #: a second consumer having to reach for the private backend.
    atom_clicked = Signal(int)

    #: An index into the CRYSTAL scene's atom list, when a unit cell is
    #: what is on screen. **A separate signal on purpose**: a crystal
    #: atom and a molecular atom that share index 7 are not the same
    #: object, and the consumers differ -- the Atom Inspector wants a
    #: molecule's report, a crystal click wants a coordination shell.
    #: Routing one into the other is the class of bug that crashed on a
    #: hydrogen click; see `_atom_is_in_report` in the inspector.
    crystal_site_clicked = Signal(int)
    #: The 2D drawing should be redrawn from what is on screen: the
    #: display-aligned molblock, and the camera state it is drawn under
    #: (3Dmol's `getView()` array, or None when there is no camera).
    #:
    #: Both, and captured together: the orientation is only meaningful
    #: against the frame it was read for. Carrying the molblock rather
    #: than an index also means the receiver does not have to re-derive
    #: which conformer was showing -- the same reason `FactLink` carries
    #: its parameters.
    conformer_adopted = Signal(str, object)

    def __init__(
        self,
        conformer_service: ConformerService,
        measurement_service: MeasurementService,
        event_bus: EventBus,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conformer_service = conformer_service
        self._measurement_service = measurement_service
        self._molecule: MoleculeModel | None = None
        self._conformer_index = 0
        self._selected_atoms: list[int] = []
        # The unit cell currently on screen, or None when this is showing
        # a molecule. It is what tells a click which index space it is in;
        # the two are NOT interchangeable.
        self._crystal_scene: dict | None = None
        #: Gallery mode: several conformers at once, each independently
        #: rotatable. False means the single-conformer view.
        self._gallery = False
        #: Index of the first conformer on the current gallery page.
        self._page_start = 0
        #: Conformers ticked for superimposition. A SET rather than a
        #: list because ticking is idempotent and order means nothing.
        self._superimposed: set[int] = set()

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)
        self._backend.atoms_selected.connect(self._on_atoms_selected)
        self._backend.grid_cell_clicked.connect(self._on_grid_cell_clicked)
        self._backend.grid_cell_toggled.connect(self._on_grid_cell_toggled)
        self._backend.grid_failed.connect(self._on_grid_failed)

        self._style_combo = QComboBox(self)
        self._style_combo.addItems(["stick", "ballstick", "sphere", "line"])
        self._style_combo.currentTextChanged.connect(self._backend.set_style)

        # Phase 25b. "None" first so the default view is unchanged -- a
        # surface is opt-in, and an opaque shell over the sticks is not
        # what someone opening the 3D tab expects to see by default.
        self._surface_combo = QComboBox(self)
        self._surface_combo.addItem("None", "")
        for representation in SURFACE_REPRESENTATIONS:
            self._surface_combo.addItem(SURFACE_REPRESENTATION_LABELS[representation], representation)
        self._surface_combo.currentIndexChanged.connect(self._on_surface_changed)

        self._generate_button = QPushButton("Generate Conformers...", self)
        self._generate_button.clicked.connect(self._on_generate_clicked)

        # THE WAY BACK. Structures went one way -- "Send to 3D Viewer Tab"
        # exists and nothing returned -- so a conformer you had generated
        # and picked could not become the structure you were working on.
        self._use_button = QPushButton("Use in 2D Editor", self)
        self._use_button.setToolTip(
            "Redraw the 2D structure to match this conformer's geometry, and switch "
            "to the editor.\n"
            "The drawing keeps its implicit hydrogens, and the conformers are kept."
        )
        self._use_button.clicked.connect(self._on_use_clicked)
        self._use_button.setEnabled(False)

        # THE GALLERY. "all separate images possible... you could check
        # several ones to be visible at a time if wanted, and on the screen
        # at the same time, yet independently rotatable."
        self._gallery_check = QCheckBox("Gallery", self)
        self._gallery_check.setToolTip(
            "Show several conformers at once, each rotatable on its own."
        )
        self._gallery_check.toggled.connect(self._on_gallery_toggled)

        self._size_combo = QComboBox(self)
        for label, (rows, cols) in _GALLERY_SIZES.items():
            self._size_combo.addItem(label, (rows, cols))
        self._size_combo.setCurrentText(_DEFAULT_GALLERY_SIZE)
        self._size_combo.currentIndexChanged.connect(self._refresh_view)

        self._lock_check = QCheckBox("Lock views", self)
        self._lock_check.setToolTip(
            "Turn every conformer together, so they stay in the same "
            "orientation. Off, each one turns on its own."
        )
        self._lock_check.toggled.connect(self._refresh_view)

        self._match_button = QPushButton("Match all to selected", self)
        self._match_button.setToolTip(
            "Point every conformer the way the selected one is pointing, "
            "then leave them free to turn separately again."
        )
        self._match_button.clicked.connect(self._on_match_clicked)

        self._superimpose_button = QPushButton("Superimpose ticked", self)
        self._superimpose_button.setToolTip(
            "Draw the ticked conformers in one frame, each a different colour."
        )
        self._superimpose_button.clicked.connect(self._on_superimpose_clicked)

        self._prev_button = QPushButton("<", self)
        self._prev_button.clicked.connect(self._show_previous_conformer)
        self._next_button = QPushButton(">", self)
        self._next_button.clicked.connect(self._show_next_conformer)
        self._status_label = QLabel("No conformers", self)
        self._measurement_label = QLabel("", self)

        # **THIS ROW WRAPS, AND THE WHOLE WINDOW DEPENDED ON IT.** As a
        # `QHBoxLayout` these fourteen controls made this widget's minimum
        # width the SUM of them -- measured, 1252 px of controls plus
        # thirteen gaps = 1330. The central `QStackedWidget` inherited
        # that, and the main window's minimum became 1877-2055 px against
        # a 1920 px screen: it could not be made to fit, the panel rail
        # hung 135 px off the right edge, and switching right-hand panels
        # changed the window's width. `FlowLayout.minimumSize` returns the
        # widest SINGLE control instead, so the row costs ~143 px and
        # wraps onto a second line when it must.
        #
        # `QToolBar` was measured first and is wrong: its overflow button
        # exists only inside a QMainWindow toolbar area, so as a plain
        # child it drops what does not fit with no way to reach it -- 8
        # controls at 320 px left 1 visible. See `flow_layout.py`.
        toolbar = flow_row(self)
        for control in (
            QLabel("Style:", toolbar),
            self._style_combo,
            QLabel("Surface:", toolbar),
            self._surface_combo,
            self._generate_button,
            self._use_button,
            self._gallery_check,
            self._size_combo,
            self._lock_check,
            self._match_button,
            self._superimpose_button,
            self._prev_button,
            self._status_label,
            self._next_button,
        ):
            toolbar.layout().addWidget(control)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(toolbar, 0)
        # **STRETCH 1 ON THE VIEW, and it is not cosmetic.** A
        # QWebEngineView and a QLabel both report a `Preferred` vertical
        # policy, so QVBoxLayout split the spare height EVENLY between
        # them: measured in the running app, a 698 px pane gave the 3D
        # view 330 px and the one-line measurement readout the other 330.
        # The viewer had been half the size it should be for as long as
        # that label has existed, which is invisible until you put six
        # conformers in the space and find each cell half as tall as it
        # should be.
        #
        # Same shape as the `WrappedLabel` finding in the Properties
        # panel: a one-line status claiming a panel's vertical stretch.
        layout.addWidget(self._backend.widget(), 1)
        layout.addWidget(self._measurement_label, 0)

        event_bus.subscribe(ConformersChanged, self._on_conformers_changed)
        event_bus.subscribe(ConformerJobStateChanged, self._on_job_state_changed)

    def set_molecule(self, molecule: MoleculeModel | None) -> None:
        """Show a molecule, replacing any unit cell that was on screen.

        Clearing `_crystal_scene` is the other half of `show_crystal`
        setting it. Without it a molecule loaded after a crystal would
        keep routing clicks as crystal-site clicks, into a scene that is
        no longer being drawn -- the same confusion in mirror image.
        """
        self._crystal_scene = None
        self._molecule = molecule
        self._conformer_index = 0
        # The ticks and the page belong to the molecule that was showing;
        # carrying them over would superimpose conformer indices that mean
        # something else now.
        self._superimposed.clear()
        self._page_start = 0
        self._selected_atoms.clear()
        self._measurement_label.setText("")
        self._refresh_view()

    def _on_surface_changed(self, _index: int) -> None:
        representation = self._surface_combo.currentData()
        if not representation:
            self._backend.apply_surface(None)
            return
        # No atom_colors here: this is the quick-glance shape-only view,
        # same spirit as the style dropdown next to it. Property-coloured
        # surfaces come from the Calculator Inspector, which has the
        # per-atom data and a legend to explain it.
        self._backend.apply_surface(
            SurfaceLayer(name="Surface", representation=representation, atom_colors=None)
        )

    def _on_generate_clicked(self) -> None:
        self.generate_conformers()

    def generate_conformers(self) -> None:
        """Ask for conformers, from wherever the user started.

        **PUBLIC because this is not the only way in.** Conformer
        generation used to live behind this widget's button alone, and
        four separate messages elsewhere in the app told people to come
        here for it -- reported as "I still low key am not much of a fan
        having to go into a 3d viewer to even generate conformers still.
        With Marvin, it was a calculator like any other."

        The Structure menu calls this, and the command palette reads the
        menu, so all three routes are one implementation rather than one
        service with three callers that can drift apart.
        """
        if self._molecule is None:
            return
        dialog = ConformerOptionsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._conformer_service.request_conformers(
            self._molecule,
            dialog.conformers_to_keep(),
            optimize=True,
            num_embeddings=dialog.embeddings_to_try(),
            options=dialog.options(),
        )

    def _on_conformers_changed(self, event: ConformersChanged) -> None:
        if self._molecule is not None and event.molecule_uuid == self._molecule.uuid:
            self._conformer_index = 0
            self._refresh_view()

    def _on_job_state_changed(self, event: ConformerJobStateChanged) -> None:
        if self._molecule is None or event.molecule_uuid != self._molecule.uuid:
            return
        if event.state == CacheState.RUNNING:
            self._status_label.setText(event.message or "Generating...")
        elif event.state == CacheState.FAILED:
            self._status_label.setText(f"Failed: {event.message}")

    def _show_previous_conformer(self) -> None:
        if self._molecule is None:
            return
        if self._gallery:
            if self._page_start > 0:
                self._page_start = max(0, self._page_start - self._page_size())
                self._refresh_view()
            return
        if self._conformer_index > 0:
            self._conformer_index -= 1
            self._refresh_view()

    def _show_next_conformer(self) -> None:
        """One conformer forward, or one PAGE forward in the gallery.

        The buttons keep their meaning -- "show me the next thing" -- and
        what "thing" means follows what is on screen. Stepping one
        conformer at a time through a gallery would move the highlight
        without changing the picture for five presses out of six.
        """
        if self._molecule is None:
            return
        if self._gallery:
            if self._page_start + self._page_size() < len(self._molecule.conformers):
                self._page_start += self._page_size()
                self._refresh_view()
            return
        if self._conformer_index < len(self._molecule.conformers) - 1:
            self._conformer_index += 1
            self._refresh_view()

    def _on_atoms_selected(self, indices: list[int]) -> None:
        # **A crystal click leaves here immediately.** The viewer holds
        # whatever molecule was last loaded, and `show_crystal` does not
        # clear it, so without this the measurement below happily
        # measured a distance in the MOLECULE using indices that came
        # from the unit cell -- correct arithmetic on the wrong object,
        # reported as a plain number. The inspector was spared only by
        # `_atom_is_in_report` refusing out-of-range indices, which is
        # luck rather than design.
        if self._crystal_scene is not None:
            for index in indices:
                self.crystal_site_clicked.emit(index)
            return

        # Re-emitted BEFORE the measurement logic and regardless of whether
        # a conformer exists, because the two uses of a click do not
        # conflict and no mode switch is needed to keep them apart: the
        # inspector wants each atom as it is clicked, the measurement wants
        # consecutive pairs. Clicking two atoms shows the second in the
        # inspector and completes a distance, which is a reasonable reading
        # of what the user asked for rather than a collision.
        for index in indices:
            self.atom_clicked.emit(index)

        if self._molecule is None or not self._molecule.conformers:
            return
        self._selected_atoms.extend(indices)
        if len(self._selected_atoms) < 2:
            return
        atom_1, atom_2 = self._selected_atoms[-2], self._selected_atoms[-1]
        self._selected_atoms.clear()
        conformer = self._molecule.conformers[self._conformer_index]
        try:
            distance = self._measurement_service.bond_length(conformer.molblock, atom_1, atom_2)
        except Exception:  # noqa: BLE001 - a bad atom index pair should not crash the widget
            self._measurement_label.setText(f"Could not measure atoms {atom_1}-{atom_2}")
            return
        self._measurement_label.setText(f"Distance atoms {atom_1}-{atom_2}: {distance:.3f} Å")

    def show_crystal(self, scene: dict) -> None:
        """Draw one unit cell of a periodic solid.

        Takes an already-built scene rather than a `Crystal`, so this
        widget -- like every other in `ui/` -- computes nothing chemical.
        Backends that predate crystals simply do not have the method, and
        saying so beats an AttributeError from inside a signal handler.
        """
        loader = getattr(self._backend, "load_crystal", None)
        if loader is None:
            raise NotImplementedError(
                f"{type(self._backend).__name__} cannot display a crystal structure."
            )
        # Set BEFORE the load, so a click that arrives while the page is
        # still drawing is already routed as a crystal click.
        self._crystal_scene = scene
        self._selected_atoms.clear()
        self._measurement_label.setText("")
        loader(scene)

    def highlight_atoms(self, indices: tuple[int, ...]) -> None:
        """Light up some atoms; an empty tuple puts it back.

        Used by the Atom Inspector while the pointer is over a fact --
        hover "Charge -0.42" and that atom lights up, hover "Ring system"
        and the ring does.

        Safe to drive from a hover because this viewer applies no atom
        colouring of its own: there is no "Color by" layer here to
        clobber and then fail to restore. If one is ever added, this must
        remember and reinstate it rather than clearing.
        """
        if not indices:
            self._backend.apply_visualization(None)
            return
        self._backend.apply_visualization(
            VisualizationLayer(
                name="Hovered fact",
                atom_colors={int(index): _HIGHLIGHT_COLOUR for index in indices},
            )
        )

    def _on_use_clicked(self, _checked: bool = False) -> None:
        """Hand what is on screen back to whoever owns the project.

        The widget does not apply it itself: redrawing the molecule has
        to be undoable, and the undo stack belongs to the window. Same
        split as the periodic table's insert.

        **The conformer ON SCREEN, which is `_conformer_index` and not
        the first one.** Sending `conformers[0]` would work perfectly for
        anyone who never pressed `>`, and silently redraw the wrong
        geometry for anyone who did.

        **The DISPLAY-ALIGNED copy, not the retained conformer**, because
        the camera orientation composes with the frame that is actually
        drawn. The retained conformer sits in its own arbitrary embedding
        frame; rotating that by the camera would produce a structure at
        some unrelated angle while looking entirely plausible.

        **ONE SNAPSHOT.** Reading the camera is a round trip into a web
        page, and the user can press `>` while it is in flight -- which
        would adopt conformer 4 with conformer 3's camera, a wrong answer
        that nothing downstream could detect. The index and the structure
        key are captured first and re-checked when the view arrives, and
        the button is disabled meanwhile so the gesture cannot be repeated
        into the gap.
        """
        if self._molecule is None or not self._molecule.conformers:
            return
        index = self._conformer_index
        key = self._structure_key()
        molblocks = self._conformer_service.display_molblocks(self._molecule)
        molblock = (
            molblocks[index]
            if index < len(molblocks)
            else self._molecule.conformers[index].molblock
        )
        self._use_button.setEnabled(False)

        def with_view(view: list[float] | None) -> None:
            self._use_button.setEnabled(True)
            if self._conformer_index != index or self._structure_key() != key:
                logger.info(
                    "The selection moved while the camera was being read; "
                    "not adopting a conformer nobody is looking at."
                )
                return
            self.conformer_adopted.emit(molblock, view)

        self._backend.current_view(with_view)

    def geometry_on_screen(self, molecule) -> str | None:
        """The conformer this viewer is showing for `molecule`, or None.

        Exists so the 2D editor's rotation mode can pick up the geometry
        somebody is already looking at -- "a conformer is selected, rotate
        that one" -- without the window reaching into `_conformer_index`
        and reimplementing the display-aligned lookup that
        `_use_in_editor` already does.

        **The conformer ON SCREEN, not the first one**, for the same
        reason as that method: `conformers[0]` is right for anyone who
        never pressed `>` and silently wrong for everyone who did.

        **Answers None for a DIFFERENT molecule** rather than whatever it
        happens to be showing. The viewer trails the selection through an
        event, so the two can briefly disagree, and handing one
        molecule's coordinates to another's drawing is correct arithmetic
        on the wrong object -- the shape of two bugs this project has
        already shipped.
        """
        if (
            self._molecule is None
            or molecule is None
            or self._molecule.uuid != molecule.uuid
            or not self._molecule.conformers
        ):
            return None
        index = self._conformer_index
        molblocks = self._conformer_service.display_molblocks(self._molecule)
        if index < len(molblocks):
            return molblocks[index]
        if index < len(self._molecule.conformers):
            return self._molecule.conformers[index].molblock
        return None

    def _refresh_view(self) -> None:
        if self._molecule is None or not self._molecule.conformers:
            self._backend.clear()
            self._status_label.setText("No conformers")
            self._status_label.setToolTip("")
            # Enabled only when there is something to adopt. A button that
            # is present but does nothing is the failure this whole line
            # of work keeps finding.
            self._use_button.setEnabled(False)
            return
        if self._gallery and hasattr(self._backend, "load_conformer_grid"):
            self._refresh_gallery()
            self._use_button.setEnabled(True)
            return
        conformer = self._molecule.conformers[self._conformer_index]
        # THE DISPLAY-ALIGNED COPY, not the retained conformer. Every
        # conformer is embedded in its own arbitrary frame, so stepping
        # between them otherwise changes the orientation as much as the
        # shape -- which is what made comparing them impossible. The
        # retained coordinates are untouched; see
        # `ConformerService.display_molblocks`.
        display = self._conformer_service.display_molblocks(self._molecule)
        molblock = (
            display[self._conformer_index]
            if self._conformer_index < len(display)
            else conformer.molblock
        )
        self._backend.load_conformer(molblock, structure_key=self._structure_key())
        self._use_button.setEnabled(True)
        self._status_label.setText(self._conformer_label(conformer))
        self._status_label.setToolTip(
            f"Absolute energy {conformer.energy:.4f} kcal/mol"
            if conformer.energy is not None
            else "This conformer has no computed energy."
        )

    # --- the gallery ---------------------------------------------------

    def _gallery_shape(self) -> tuple[int, int]:
        return self._size_combo.currentData() or _GALLERY_SIZES[_DEFAULT_GALLERY_SIZE]

    def _page_size(self) -> int:
        rows, cols = self._gallery_shape()
        return rows * cols

    def _on_gallery_toggled(self, on: bool) -> None:
        self._gallery = on
        self._page_start = 0
        if not on:
            leave = getattr(self._backend, "leave_grid", None)
            if leave is not None:
                leave()
        self._refresh_view()

    def _on_grid_cell_clicked(self, index: int) -> None:
        """A cell click chooses which conformer `<`, `>` and "Use in 2D
        Editor" act on. It does NOT tick it -- ticking is for
        superimposition and is a separate gesture, reported separately."""
        absolute = self._page_start + index
        if self._molecule and 0 <= absolute < len(self._molecule.conformers):
            self._conformer_index = absolute
            self._status_label.setText(
                self._conformer_label(self._molecule.conformers[absolute])
            )

    def _on_grid_cell_toggled(self, index: int, checked: bool) -> None:
        absolute = self._page_start + index
        if checked:
            self._superimposed.add(absolute)
        else:
            self._superimposed.discard(absolute)

    def _on_grid_failed(self, message: str) -> None:
        """`createViewerGrid` would not build here.

        **NOT "a second WebGL context was refused"**, which is what this
        said and is measurably wrong: under Qt's `offscreen` platform
        twelve bare contexts and six independent 3Dmol viewers all
        succeed, while a grid of even ONE cell throws. Why the grid call
        specifically fails is not established -- see the ladder in
        `tests/test_mol3d_viewer_backend.py`.

        Reachable on software rendering or a remote session too, where
        the pane would otherwise be left empty and read as the feature
        being broken rather than unavailable. Going back to the single
        view and saying so is the honest answer -- and the checkbox is
        unticked, so the state on screen matches the state of the
        control.
        """
        self._gallery = False
        self._gallery_check.blockSignals(True)
        self._gallery_check.setChecked(False)
        self._gallery_check.blockSignals(False)
        self._measurement_label.setText(
            "The gallery needs a second 3D drawing surface, which this display "
            "did not provide. Showing one conformer at a time instead."
        )
        self._refresh_view()

    def _on_match_clicked(self, _checked: bool = False) -> None:
        match = getattr(self._backend, "match_grid_views", None)
        if match is not None:
            match(self._conformer_index - self._page_start)

    def _on_superimpose_clicked(self, _checked: bool = False) -> None:
        """Draw the ticked conformers in one frame, each its own colour.

        Reuses `load_ensemble`, which the Alignment panel already drives --
        superimposing structures in one coordinate frame is the same
        operation whether they are different molecules or conformers of
        one, and the display alignment has already put these in a common
        frame.
        """
        if self._molecule is None or len(self._superimposed) < 2:
            self._measurement_label.setText(
                "Tick two or more conformers in the gallery to superimpose them."
            )
            return
        molblocks = self._conformer_service.display_molblocks(self._molecule)
        entries = [
            (molblocks[index], _ENSEMBLE_COLOURS[position % len(_ENSEMBLE_COLOURS)])
            for position, index in enumerate(sorted(self._superimposed))
            if index < len(molblocks)
        ]
        loader = getattr(self._backend, "load_ensemble", None)
        if loader is None or not entries:
            return
        self._gallery_check.setChecked(False)
        loader(entries)
        self._measurement_label.setText(
            f"{len(entries)} conformers superimposed."
        )

    def _refresh_gallery(self) -> None:
        molblocks = self._conformer_service.display_molblocks(self._molecule)
        total = len(molblocks)
        rows, cols = self._gallery_shape()
        size = rows * cols
        self._page_start = max(0, min(self._page_start, max(0, total - 1)))
        page = list(range(self._page_start, min(self._page_start + size, total)))
        # **THE SELECTION MUST LAND ON THIS PAGE.** The page resets its own
        # selected cell to the first one whenever the grid is rebuilt, so
        # a `_conformer_index` left pointing at another page would take
        # the camera from cell 0 and the conformer from somewhere else --
        # a structure at an angle nobody looked at, which is the same
        # class of mismatch the adoption snapshot exists to prevent.
        if page and self._conformer_index not in page:
            self._conformer_index = page[0]
        entries = [
            (molblocks[index], self._cell_label(index))
            for index in page
        ]
        self._backend.load_conformer_grid(
            entries,
            rows,
            cols,
            linked=self._lock_check.isChecked(),
            selected=[i - self._page_start for i in sorted(self._superimposed) if i in page],
        )
        last = page[-1] + 1 if page else 0
        self._status_label.setText(
            f"Conformers {self._page_start + 1}-{last} of {total}"
        )
        self._status_label.setToolTip("")

    def _cell_label(self, index: int) -> str:
        conformer = self._molecule.conformers[index]
        energies = [c.energy for c in self._molecule.conformers if c.energy is not None]
        if conformer.energy is None or not energies:
            return f"{index + 1}"
        relative = conformer.energy - min(energies)
        if relative < 0.005:
            return f"{index + 1} - lowest"
        return f"{index + 1} - +{relative:.2f}"

    def _structure_key(self) -> tuple | None:
        """What the viewer treats as "still the same thing on screen".

        Camera retention hangs off this, so it has to mean "another
        conformer of the same batch of the same molecule" and nothing
        looser. The batch is identified by the conformers' timestamps --
        `_ConformerGenerationTask` stamps one `Provenance` across a whole
        run, so a regenerated set has different ones and correctly re-fits
        the camera, and a conformer appended later (ORCA, via
        `AddConformerCommand`) changes the tuple rather than slipping in
        unnoticed.

        NOT the molblock and NOT the model object: the first would let an
        imported structure with the same graph inherit an unrelated
        camera, and the second cannot survive the model being rebuilt.
        """
        if self._molecule is None or not self._molecule.conformers:
            return None
        return (
            self._molecule.uuid,
            tuple(conformer.timestamp for conformer in self._molecule.conformers),
        )

    def _conformer_label(self, conformer) -> str:
        """`Conformer 2/11 - +0.55 kcal/mol`.

        **RELATIVE TO THE LOWEST, not the raw force-field number.** The
        absolute MMFF energy of a conformer is not a quantity anybody
        compares against anything -- `70.95` and `71.50` differ by an
        amount the reader has to work out, and the interesting figure is
        the 0.55. The absolute value moves to the tooltip rather than
        being dropped, because it is what a force-field log would show.
        """
        total = len(self._molecule.conformers)
        position = f"Conformer {self._conformer_index + 1}/{total}"
        energies = [c.energy for c in self._molecule.conformers if c.energy is not None]
        if conformer.energy is None or not energies:
            return f"{position} - energy n/a"
        relative = conformer.energy - min(energies)
        # "lowest" rather than "+0.00", so the reference is named rather
        # than left to be inferred from a zero.
        if relative < 0.005:
            return f"{position} - lowest energy"
        return f"{position} - +{relative:.2f} kcal/mol"
