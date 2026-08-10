from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.common import CacheState
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


#: Amber, which is not on the diverging red/blue scale the per-atom
#: layers use -- so a transient hover cannot be mistaken for data.
_HIGHLIGHT_COLOUR = "#ffb300"


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
    #: The 2D drawing should be redrawn from the conformer on screen.
    #:
    #: Carries the molblock rather than an index, so the receiver does not
    #: have to reach back in and re-derive which conformer was showing --
    #: the same reason `FactLink` carries its parameters.
    conformer_adopted = Signal(str)

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

        self._backend: ViewerBackend = backend or Mol3DViewerBackend(self)
        self._backend.atoms_selected.connect(self._on_atoms_selected)

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

        self._prev_button = QPushButton("<", self)
        self._prev_button.clicked.connect(self._show_previous_conformer)
        self._next_button = QPushButton(">", self)
        self._next_button.clicked.connect(self._show_next_conformer)
        self._status_label = QLabel("No conformers", self)
        self._measurement_label = QLabel("", self)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Style:"))
        toolbar.addWidget(self._style_combo)
        toolbar.addWidget(QLabel("Surface:"))
        toolbar.addWidget(self._surface_combo)
        toolbar.addWidget(self._generate_button)
        toolbar.addWidget(self._use_button)
        toolbar.addStretch()
        toolbar.addWidget(self._prev_button)
        toolbar.addWidget(self._status_label)
        toolbar.addWidget(self._next_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._backend.widget())
        layout.addWidget(self._measurement_label)

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
        if self._molecule and self._conformer_index > 0:
            self._conformer_index -= 1
            self._refresh_view()

    def _show_next_conformer(self) -> None:
        if self._molecule and self._conformer_index < len(self._molecule.conformers) - 1:
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
        """Hand the conformer on screen back to whoever owns the project.

        The widget does not apply it itself: redrawing the molecule has
        to be undoable, and the undo stack belongs to the window. Same
        split as the periodic table's insert.

        **The conformer ON SCREEN, which is `_conformer_index` and not
        the first one.** Sending `conformers[0]` would work perfectly for
        anyone who never pressed `>`, and silently redraw the wrong
        geometry for anyone who did.
        """
        if self._molecule is None or not self._molecule.conformers:
            return
        conformer = self._molecule.conformers[self._conformer_index]
        self.conformer_adopted.emit(conformer.molblock)

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
