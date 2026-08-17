from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import logging

from openchem.chem.calculation_input import canonical_conformer
from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.docking import DockingBox
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady, MoleculeSelected
from openchem.services.docking_service import DockingService
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.molecule_combo import repopulate, select

logger = logging.getLogger("openchem.ui")

_POSE_COLUMNS = ("Pose", "Binding Affinity (kcal/mol)", "RMSD l.b.", "RMSD u.b.")

#: What each column MEANS, which the headers alone do not say -- reported
#: as confusing by a user who read the RMSD columns as accuracy against an
#: experimental structure. They are not: both are measured against pose 1.
#:
#: THE SCORING ERROR IS QUOTED WITH ITS SOURCE, AND ONLY BECAUSE IT HAS
#: ONE. It was first written in from memory, removed because nothing in
#: this tree supported it, and restored only after the paper was read:
#: `[source:trott_olson2010]`, "Vina achieves a comparatively low standard
#: error of 2.85 kcal/mol". The remembered figure turned out to be right,
#: which is not a reprieve -- it was unverifiable at the time, and a
#: tooltip is exactly where an unsourced number acquires false authority.
#:
#: ATTRIBUTED, NOT STATED FLATLY. It is the authors' standard error of
#: predicted against experimental binding free energies on THEIR
#: 190-complex set; it is not a universal error bar for any given run.
_POSE_COLUMN_TOOLTIPS = {
    "Pose": "Rank within this run, best score first. Not an identity: pose 1 of one "
    "run is unrelated to pose 1 of another.",
    "Binding Affinity (kcal/mol)": (
        "AutoDock Vina's empirical score, in kcal/mol. Always negative; more negative "
        "is predicted-tighter binding.\n\n"
        "It is NOT a measured binding free energy, and scores are generally not "
        "directly comparable across different receptors, targets or docking protocols "
        "-- the search box, receptor preparation and protonation pH all move the scale.\n\n"
        "For scale: Trott & Olson (2010), who wrote the scoring function, report a "
        "standard error of 2.85 kcal/mol against experimental binding free energies "
        "on their own 190-complex test set. Treat differences smaller than that as "
        "not meaningfully distinguishable."
    ),
    "RMSD l.b.": (
        "Root-mean-square deviation in Angstrom RELATIVE TO POSE 1 of this run -- not "
        "to any experimental structure. Pose 1 is therefore always 0.000.\n\n"
        "The lower bound allows symmetry-equivalent atoms to be matched to each other, "
        "so it is always less than or equal to the upper bound.\n\n"
        "A large value means this pose is geometrically different from pose 1. It does "
        "not establish whether either pose is correct."
    ),
    "RMSD u.b.": (
        "Root-mean-square deviation in Angstrom RELATIVE TO POSE 1 of this run -- not "
        "to any experimental structure. Pose 1 is therefore always 0.000.\n\n"
        "The upper bound matches each atom to itself, ignoring symmetry, so it is "
        "always greater than or equal to the lower bound.\n\n"
        "A large value means this pose is geometrically different from pose 1. It does "
        "not establish whether either pose is correct."
    ),
}

#: What the box resets to when nothing can be derived. Also the value it
#: has always had on a fresh panel -- but it is only defensible as a
#: STARTING point, never as a box to dock with, which is why every path
#: that writes it also says so on the status line.
_DEFAULT_BOX = DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))

#: "STILL NOT HANDLED" READ AS AN OVERSIGHT AND THE TRUTH IS A DECISION.
#: `docs/ARCHITECTURE.md` records missing-residue repair as assessed and
#: deliberately left out, with numbers: zero of 49 curated receptors have a
#: chain break within 10 A of their site, only 3 of 48 have incomplete side
#: chains there, and the repair is a template prediction landing a median
#: 2.3 A from atoms actually observed in sister chains. So the two said
#: different KINDS of thing about the same fact -- one "unfinished, may
#: arrive", the other "measured, declined" -- and a panel note that implies
#: a pending feature is the more misleading of the two.
_LIMITATION_NOTE = (
    "Note: receptor preparation handles pH-correct protonation and "
    "water/cofactor stripping (below), via Open Babel. Missing-residue repair "
    "is deliberately not attempted — it was assessed and declined, because "
    "predicted atoms would be indistinguishable from observed ones in the "
    "result (see ARCHITECTURE.md). Treat results as a starting point, not "
    "production-grade docking prep."
)


def _box_defining_ligand_codes(receptor) -> list[str]:
    """The co-crystallised ligand that defined this receptor's search box.

    A catalogue import records it in `MacromoleculeModel.metadata`
    (`receptor_library_service.entry_metadata`), and the box is derived
    from its coordinates. Leaving it in the pocket it defined means docking
    into an occupied site: measured against real Vina on 1HSG, indinavir
    redocked into its own structure scored -5.34 kcal/mol with the ligand
    present and -9.75 with it removed, and the occupied run was SLOWER.

    Returns empty for a receptor the user imported themselves -- there is
    no catalogue entry, so nothing here knows which residue defined the
    box, and guessing would delete part of somebody's receptor.
    """
    metadata = getattr(receptor, "metadata", None) or {}
    code = str(metadata.get("ligand_code", "") or "").strip()
    return [code] if code else []


class DockingPanel(QWidget):
    """Pick a receptor (macromolecule) + ligand (molecule) from the current
    project, define a search box, and run AutoDock Vina via whichever
    `VinaEngine` is available (chem/vina_engine.py) — the panel itself
    doesn't know or care which one.
    """

    #: The displayed search box changed -- derived, reset or typed over.
    #: `MainWindow` redraws the 3D overlay from it. A signal rather than a
    #: direct call because the panel has no reference to the viewer, which
    #: is the same reason docking RESULTS travel through the window.
    box_changed = Signal()

    def __init__(
        self,
        docking_service: DockingService,
        chemistry_engine: ChemistryEngine,
        settings: Settings,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._docking_service = docking_service
        self._chemistry_engine = chemistry_engine
        self._settings = settings
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._pending_ligand_uuid: str | None = None
        self._pending_receptor_uuid: str | None = None
        #: Which docking result the pose table is showing, so an undo
        #: that removes it can be told apart from a redo that restores it.
        self._displayed_result_uuid: str | None = None

        self._receptor_combo = QComboBox(self)
        # Parsing a receptor is not free (Open Babel reads the whole file),
        # so the summary is computed on demand from the button rather than
        # on every combo change.
        self._contents_button = QPushButton("Contents...", self)
        self._contents_button.setToolTip(
            "List the chains, ligands and waters in the selected receptor"
        )
        self._contents_button.clicked.connect(self._on_contents_clicked)
        # Empty means "no restriction", never "no chains" -- see
        # StructureContentsDialog.keep_chains. Reset whenever the receptor
        # changes, because a chain id names a different thing in a
        # different structure and carrying "keep A" across would silently
        # dock against the wrong subunit.
        self._keep_chains: list[str] = []
        #: Reset with the receptor for the same reason `_keep_chains`
        #: is: an assembly annotation belongs to one deposit, and
        #: carrying "build it" across would apply another structure's
        #: answer to this one.
        self._build_assembly = False
        self._derive_button = QPushButton("Derive from ligand...", self)
        self._derive_button.clicked.connect(self._on_derive_clicked)
        # Enabled by `_place_box_for_receptor` once a receptor with bound
        # ligands is chosen. Disabled is the honest starting state -- there
        # is nothing to derive from yet.
        self._derive_button.setEnabled(False)
        self._derive_button.setToolTip("Select a receptor to derive a search box from it.")
        self._ligand_combo = QComboBox(self)

        #: Where the displayed box came from -- "derived", "manual" or
        #: "none". PROVENANCE ONLY: `displayed_box()` reads the spinboxes,
        #: and nothing may dock from anything else.
        self._box_source = "none"
        #: True while `_write_box` is setting the spinboxes, so its own
        #: `valueChanged` emissions are not mistaken for a user edit.
        self._writing_box = False
        #: Which receptor the displayed box was placed for.
        #:
        #: The box CANNOT be driven by `currentIndexChanged` alone.
        #: `molecule_combo.repopulate` blocks signals deliberately -- a
        #: rebuild must not look like a user changing the selection -- so
        #: the first receptor ever added to a project arrives selected with
        #: no signal at all, and a signal-only implementation leaves its
        #: box at the default. Comparing the uuid catches that, and it is
        #: also what lets a repopulate for an unrelated reason leave a
        #: hand-positioned box alone.
        self._box_receptor_uuid: str | None = None

        self._center_x = self._make_spin(-1000, 1000, 0.0)
        self._center_y = self._make_spin(-1000, 1000, 0.0)
        self._center_z = self._make_spin(-1000, 1000, 0.0)
        self._size_x = self._make_spin(1, 200, 20.0)
        self._size_y = self._make_spin(1, 200, 20.0)
        self._size_z = self._make_spin(1, 200, 20.0)
        for spin in (
            self._center_x, self._center_y, self._center_z,
            self._size_x, self._size_y, self._size_z,
        ):
            spin.valueChanged.connect(self._on_box_edited)
        # Connected only now that the spinboxes exist: the handler writes
        # the box, so a combo signal arriving earlier would reach them
        # before they had been built.
        self._receptor_combo.currentIndexChanged.connect(self._on_receptor_changed)

        self._num_poses_spin = QSpinBox(self)
        self._num_poses_spin.setRange(1, 50)
        self._num_poses_spin.setValue(9)

        self._ph_spin = QDoubleSpinBox(self)
        self._ph_spin.setRange(0.0, 14.0)
        self._ph_spin.setSingleStep(0.1)
        self._ph_spin.setValue(7.4)
        self._strip_waters_check = QCheckBox("Strip waters", self)
        self._strip_waters_check.setChecked(True)
        self._strip_cofactors_check = QCheckBox("Strip cofactors", self)
        self._strip_cofactors_check.setChecked(False)

        self._configure_button = QPushButton("Configure Vina...", self)
        self._configure_button.clicked.connect(self._on_configure_clicked)

        self._dock_button = QPushButton("Dock", self)
        self._dock_button.clicked.connect(self._on_dock_clicked)

        self._status_label = QLabel("", self)
        #: Where the search box is, and whether that is where the receptor
        #: says its site is. SEPARATE from `_status_label` on purpose: that
        #: one carries job state and is rewritten on every
        #: `DockingJobStateChanged`, so a box warning put there is wiped by
        #: the "Queued..." that follows it microseconds later. Caught by
        #: `test_a_far_box_warns_without_blocking_the_run`, which asserted
        #: the message survived the click and found that it did not.
        self._box_status_label = QLabel("", self)
        self._box_status_label.setWordWrap(True)
        self._limitation_label = QLabel(_LIMITATION_NOTE, self)
        self._limitation_label.setWordWrap(True)

        self._table = QTableWidget(0, len(_POSE_COLUMNS), self)
        self._table.setHorizontalHeaderLabels(_POSE_COLUMNS)
        # On the header ITEMS, which are QTableWidgetItems rather than
        # widgets -- so a tooltip audit that walks QWidgets alone cannot
        # see these, and would report the table fully documented.
        for column, name in enumerate(_POSE_COLUMNS):
            item = self._table.horizontalHeaderItem(column)
            if item is not None:
                item.setToolTip(_POSE_COLUMN_TOOLTIPS[name])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        receptor_row = QHBoxLayout()
        receptor_row.addWidget(self._receptor_combo, 1)
        receptor_row.addWidget(self._contents_button)
        receptor_row.addWidget(self._derive_button)

        selection_form = QFormLayout()
        selection_form.addRow("Receptor:", receptor_row)
        selection_form.addRow("Ligand:", self._ligand_combo)

        box_group = QGroupBox("Search box (Å)", self)
        box_form = QFormLayout(box_group)
        center_row = QHBoxLayout()
        center_row.addWidget(self._center_x)
        center_row.addWidget(self._center_y)
        center_row.addWidget(self._center_z)
        size_row = QHBoxLayout()
        size_row.addWidget(self._size_x)
        size_row.addWidget(self._size_y)
        size_row.addWidget(self._size_z)
        box_form.addRow("Center (x, y, z):", center_row)
        box_form.addRow("Size (x, y, z):", size_row)

        prep_group = QGroupBox("Receptor preparation", self)
        prep_form = QFormLayout(prep_group)
        prep_form.addRow("Protonation pH:", self._ph_spin)
        strip_row = QHBoxLayout()
        strip_row.addWidget(self._strip_waters_check)
        strip_row.addWidget(self._strip_cofactors_check)
        prep_form.addRow("", strip_row)

        run_row = QHBoxLayout()
        run_row.addWidget(QLabel("Poses:"))
        run_row.addWidget(self._num_poses_spin)
        run_row.addWidget(self._configure_button)
        run_row.addWidget(self._dock_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_form)
        layout.addWidget(box_group)
        layout.addWidget(self._box_status_label)
        layout.addWidget(prep_group)
        layout.addLayout(run_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._table)
        layout.addWidget(self._limitation_label)

        event_bus.subscribe(DockingJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(DockingResultReady, self._on_result_ready)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    def _make_spin(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._refresh_combos()

    def _refresh_combos(self) -> None:
        macromolecules = self._project.macromolecules if self._project is not None else []
        molecules = self._project.molecules if self._project is not None else []
        repopulate(self._receptor_combo, [(m.display_name, m.uuid) for m in macromolecules])
        repopulate(self._ligand_combo, [(m.display_name, m.uuid) for m in molecules])
        # `repopulate` is deliberately silent, so the box has to be asked
        # for here. It no-ops unless the selected receptor actually moved.
        self._sync_box_with_receptor()

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        """Follow the project tree for the LIGAND only.

        The receptor combo lists macromolecules and is deliberately left
        alone: a `MoleculeSelected` uuid is never in it, and blanking a
        chosen receptor because the user clicked a small molecule would
        throw away the search box that goes with it.
        """
        select(self._ligand_combo, event.molecule_uuid)

    def _on_contents_clicked(self) -> None:
        """Summarise the selected receptor and show its chains.

        Parsed here rather than cached on the model: the summary is a view
        of the structure text, and caching it would give the model a
        second copy of the truth that could go stale the moment the text
        was replaced.
        """
        from openchem.chem.structure_assembly import parse_assembly
        from openchem.chem.structure_summary import summarize_structure
        from openchem.ui.dialogs.structure_contents_dialog import StructureContentsDialog

        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        receptor = (
            self._project.find_macromolecule(receptor_uuid) if receptor_uuid else None
        )
        if receptor is None:
            self._status_label.setText("Select a receptor first.")
            return
        try:
            summary = summarize_structure(receptor.structure_text, receptor.source_format)
        except Exception as exc:  # noqa: BLE001 - surfaced, never a crash
            logger.exception("Failed to summarise receptor")
            self._status_label.setText(f"Could not read that receptor: {exc}")
            return
        dialog = StructureContentsDialog(
            receptor.display_name,
            summary,
            self,
            keep_chains=self._keep_chains or None,
            # Parsed from the SAME text the chains came from -- mmCIF
            # assembly records name label_asym_ids and PDB REMARK 350
            # names author ids, so crossing the two formats would annotate
            # chains that do not exist under those names.
            assembly=parse_assembly(receptor.structure_text, receptor.source_format),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._keep_chains = dialog.keep_chains()
        self._build_assembly = dialog.build_assembly()
        self._update_chain_status()

    def _on_receptor_changed(self, _index: int) -> None:
        self._keep_chains = []
        self._build_assembly = False
        self._update_chain_status()
        self._sync_box_with_receptor()

    def _sync_box_with_receptor(self) -> None:
        """Re-place the box iff the receptor it belongs to has changed.

        Reached from the combo's signal AND from `_refresh_combos`,
        because neither alone is sufficient: `repopulate` blocks signals,
        so the signal misses the first receptor; and a repopulate happens
        on every project mutation, so acting on it unconditionally would
        overwrite a hand-positioned box every time an unrelated molecule
        was renamed.
        """
        current = self._receptor_combo.currentData()
        if current == self._box_receptor_uuid:
            return
        self._box_receptor_uuid = current
        self._place_box_for_receptor()

    # --- the search box ------------------------------------------------------

    def selected_receptor_uuid(self) -> str | None:
        """Which receptor the box belongs to, or None.

        Public because `MainWindow._sync_docking_box_overlay` has to know
        whether there is anything to draw a box ON, and reaching into the
        combo from outside would put a second reader on that state.
        """
        return self._receptor_combo.currentData()

    def _selected_receptor(self):
        if self._project is None:
            return None
        receptor_uuid = self._receptor_combo.currentData()
        return self._project.find_macromolecule(receptor_uuid) if receptor_uuid else None

    def displayed_box(self) -> DockingBox:
        """The box as the six spinboxes currently read it.

        The ONE accessor, used by `_on_dock_clicked` and by the tests that
        check what was sent. `_box_source` records where these numbers came
        from and never substitutes for them: reading the box from anywhere
        else is how the panel would start displaying one thing and docking
        another.
        """
        return DockingBox(
            center=(self._center_x.value(), self._center_y.value(), self._center_z.value()),
            size=(self._size_x.value(), self._size_y.value(), self._size_z.value()),
        )

    def _write_box(self, box: DockingBox, source: str) -> None:
        """Set the six spinboxes without the write counting as a user edit.

        `setValue` emits `valueChanged` exactly as a keystroke does, so
        without this guard every derived box would be marked `manual` the
        instant it was written -- and the panel would then refuse to
        re-derive it. Scoped around the writes rather than inferred from
        whether the values changed, because a value that happens to match
        is still a programmatic write.
        """
        self._writing_box = True
        try:
            for spin, value in zip(
                (self._center_x, self._center_y, self._center_z,
                 self._size_x, self._size_y, self._size_z),
                (*box.center, *box.size),
                strict=True,
            ):
                spin.setValue(value)
        finally:
            self._writing_box = False
        self._box_source = source
        self.box_changed.emit()

    def _on_box_edited(self, _value: float) -> None:
        if self._writing_box:
            return
        self._box_source = "manual"
        self._box_status_label.setText("Search box: manually positioned.")
        self.box_changed.emit()

    def _place_box_for_receptor(self) -> None:
        """Box the receptor's own annotated site, or reset to defaults.

        **A RECEPTOR CHANGE ALWAYS REWRITES THE BOX, and resetting is the
        load-bearing half.** Leaving the previous receptor's coordinates in
        place would present one structure's site as though it belonged to
        another -- the same silently-plausible-wrong-box failure this
        method exists to fix, just moved one step along. `_keep_chains` and
        `_build_assembly` are reset directly above for exactly this reason;
        the box simply never was.

        A hand-tuned box survives everything else: this is reached from the
        receptor combo and from the Derive button, and from nothing that
        merely refreshes the panel.
        """
        receptor = self._selected_receptor()
        if receptor is None:
            self._write_box(_DEFAULT_BOX, "none")
            self._update_derive_button(())
            return

        codes = self._ligand_codes_for(receptor)
        self._update_derive_button(codes)
        preferred = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        if not preferred:
            self._write_box(_DEFAULT_BOX, "none")
            self._box_status_label.setText(
                "No annotated binding site for this receptor, so the search box was reset "
                "to defaults. Use Derive from ligand... to box a bound ligand."
                if codes
                else "No annotated binding site for this receptor, and no bound ligand to "
                "derive one from. Position the search box manually."
            )
            return
        self._derive_box_from(receptor, preferred)

    def _derive_box_from(self, receptor, ligand_code: str) -> None:
        """Place the box on `ligand_code`, or reset and say why.

        Idempotent: the derivation is a pure function of the structure text
        and the code, so pressing Derive twice writes the same six values
        and reports the same thing.
        """
        from openchem.chem.binding_site import BindingSiteError, box_from_ligand

        try:
            site = box_from_ligand(receptor.structure_text, receptor.source_format, ligand_code)
        except (BindingSiteError, Exception) as exc:  # noqa: BLE001 - reported, never crashes
            logger.exception("Could not derive a search box for %s", receptor.display_name)
            self._write_box(_DEFAULT_BOX, "none")
            # Distinguished from "there is no site" deliberately: the
            # metadata said this receptor HAS one, so silence would read as
            # "nothing to box here" when the truth is that something is
            # wrong and the user can act on it.
            self._box_status_label.setText(
                f"This receptor should have a {ligand_code} site, but it could not be "
                f"located: {exc} The search box was reset to defaults."
            )
            return
        self._write_box(site.box, "derived")
        self._box_status_label.setText(f"Binding site: {site.describe()}")

    def _ligand_codes_for(self, receptor) -> tuple[str, ...]:
        from openchem.chem.binding_site import ligand_codes_in

        try:
            return tuple(ligand_codes_in(receptor.structure_text, receptor.source_format))
        except Exception:  # noqa: BLE001 - a listing failure must not block docking
            logger.exception("Could not list ligand codes for %s", receptor.display_name)
            return ()

    def _update_derive_button(self, codes: tuple[str, ...]) -> None:
        """Say whether a box can be derived BEFORE the button is pressed.

        A failed automatic derivation must not make the manual route look
        permanently unavailable -- an imported structure, or a deposit
        revision whose catalogue code has moved, still has ligands in it
        that can define a site.
        """
        self._derive_button.setEnabled(bool(codes))
        self._derive_button.setToolTip(
            "Set the search box to the site defined by a bound ligand: "
            + ", ".join(codes[:6])
            + ("..." if len(codes) > 6 else "")
            if codes
            else "No bound ligand in this receptor to derive a search box from."
        )

    def _on_derive_clicked(self) -> None:
        receptor = self._selected_receptor()
        if receptor is None:
            self._status_label.setText("Select a receptor first.")
            return
        codes = self._ligand_codes_for(receptor)
        if not codes:
            return
        preferred = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        if preferred and preferred.upper() in codes:
            self._derive_box_from(receptor, preferred)
            return
        code, accepted = QInputDialog.getItem(
            self, "Derive search box", "Box the site defined by:", list(codes), 0, False
        )
        if accepted and code:
            self._derive_box_from(receptor, code)

    def _update_chain_status(self) -> None:
        """Say so on the panel when the receptor is being cut down.

        A restriction chosen in a dialog that is then closed is invisible,
        and this one changes what Vina sees -- the user should not have to
        reopen the dialog to find out whether it is in effect.
        """
        if self._keep_chains:
            self._status_label.setText(
                f"Docking against chain(s) {', '.join(self._keep_chains)} only."
            )
        elif self._status_label.text().startswith("Docking against chain"):
            self._status_label.setText("")

    def _on_configure_clicked(self) -> None:
        dialog = ExternalToolsDialog(self._settings, self, focus="vina")
        dialog.exec()

    def _on_dock_clicked(self) -> None:
        if self._project is None:
            return
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        if receptor_uuid is None or ligand_uuid is None:
            self._status_label.setText("Select both a receptor and a ligand first.")
            return
        receptor = self._project.find_macromolecule(receptor_uuid)
        ligand = self._project.find_molecule(ligand_uuid)
        if receptor is None or ligand is None:
            return
        if not ligand.conformers and not ligand.molblock:
            self._status_label.setText("Selected ligand has no structure yet.")
            return

        # The displayed box, always. `_box_source` says where it came from
        # and never decides what is sent -- a user who typed six numbers
        # over a derived box means the numbers.
        box = self.displayed_box()
        self._report_box_placement(receptor, box)
        # Prefer a real 3D conformer over the molecule's own molblock, which
        # for anything drawn in the 2D editor has all-zero z-coordinates --
        # docking a flat structure against a 3D receptor is meaningless, not
        # just lower quality. Mirrors QuantumChemistryPanel._on_run_clicked's
        # identical preference.
        best = canonical_conformer(ligand)
        ligand_molblock = best.molblock if best is not None else ligand.molblock
        ligand_mol = self._chemistry_engine.mol_from_molblock(ligand_molblock)

        self._pending_ligand_uuid = ligand_uuid
        self._pending_receptor_uuid = receptor_uuid
        self._dock_button.setEnabled(False)
        self._table.setRowCount(0)
        self._status_label.setText("Queued...")

        self._docking_service.request_docking(
            ligand_molecule_uuid=ligand_uuid,
            ligand_mol=ligand_mol,
            receptor_macromolecule_uuid=receptor_uuid,
            receptor_structure_text=receptor.structure_text,
            receptor_source_format=receptor.source_format,
            box=box,
            num_poses=self._num_poses_spin.value(),
            receptor_prep_options={
                "ph": self._ph_spin.value(),
                "strip_waters": self._strip_waters_check.isChecked(),
                "strip_cofactors": self._strip_cofactors_check.isChecked(),
                # Travels in the SAME dict the service hands to both the
                # receptor preparation and the interaction analysis, so
                # they cannot be given different receptors.
                "keep_chains": list(self._keep_chains),
                # Same dict, same reason: the service builds the
                # assembly ONCE from this and hands the identical text
                # to both the docking and the interaction analysis.
                "build_assembly": self._build_assembly,
                "strip_ligand_codes": _box_defining_ligand_codes(receptor),
            },
        )

    def _report_box_placement(self, receptor, box: DockingBox) -> None:
        """Say where the box sits before the run, and never block it.

        Warn-never-block is deliberate. `far_from_reference_site` is
        evidence that the run will not sample the annotated site, not a
        verdict that the user is wrong: blind docking and allosteric sites
        are real uses and a distant box is the intended experiment for
        both. The zero-atom case IS refused, but further down, by
        `docking_providers._require_atoms_in_box` against the prepared
        receptor -- see `binding_site.BoxPlacement.atom_count` for why the
        two counts differ and why both exist.
        """
        from openchem.chem.binding_site import describe_box_placement

        code = str((getattr(receptor, "metadata", None) or {}).get("ligand_code", "") or "")
        try:
            placement = describe_box_placement(
                receptor.structure_text, receptor.source_format, box, code or None
            )
        except Exception:  # noqa: BLE001 - a diagnostic must never stop a run
            logger.exception("Could not judge box placement for %s", receptor.display_name)
            return
        self._box_status_label.setText(placement.describe())

    def _is_pending(self, ligand_molecule_uuid: str, receptor_macromolecule_uuid: str) -> bool:
        return (
            ligand_molecule_uuid == self._pending_ligand_uuid
            and receptor_macromolecule_uuid == self._pending_receptor_uuid
        )

    def _on_job_state_changed(self, event: DockingJobStateChanged) -> None:
        if not self._is_pending(event.ligand_molecule_uuid, event.receptor_macromolecule_uuid):
            return
        self._status_label.setText(f"{event.state.value}{': ' + event.message if event.message else ''}")
        if event.state.value in ("completed", "failed"):
            self._dock_button.setEnabled(True)

    def sync_with_project(self, project: ProjectModel | None) -> None:
        """Make the pose table agree with the project's docking results.

        The table was filled from the `DockingResultReady` event and never
        read back from the project, so it only ever reflected what had just
        finished. Undoing a dock removed the result and left the poses on
        screen -- binding affinities, to two decimal places, for a run the
        project no longer contains. Measured: two rows still listed after
        the undo that emptied `project.docking_results`.

        Symmetric on purpose. Clearing on undo without restoring on redo
        would trade one wrong state for another, so this resolves the table
        from the project every time: the newest result for the currently
        selected receptor/ligand pair, or nothing.
        """
        self._table.setRowCount(0)
        self._displayed_result_uuid = None
        result = self._latest_result_for_selection(project)
        if result is not None:
            self._show_result(result)

    def _latest_result_for_selection(self, project: ProjectModel | None):
        if project is None:
            return None
        receptor_uuid = self._receptor_combo.currentData()
        ligand_uuid = self._ligand_combo.currentData()
        matching = [
            result
            for result in project.docking_results
            if result.receptor_macromolecule_uuid == receptor_uuid
            and result.ligand_molecule_uuid == ligand_uuid
        ]
        # Newest wins: re-docking the same pair should show the run just
        # made, not the first one ever made.
        return max(matching, key=lambda r: r.timestamp) if matching else None

    def _show_result(self, result) -> None:
        self._displayed_result_uuid = result.uuid
        self._table.setRowCount(len(result.poses))
        for row, pose in enumerate(result.poses):
            values = (
                str(row + 1),
                f"{pose.binding_affinity_kcal_mol:.2f}",
                f"{pose.rmsd_lb:.3f}",
                f"{pose.rmsd_ub:.3f}",
            )
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))

    def _on_result_ready(self, event: DockingResultReady) -> None:
        result = event.result
        if not self._is_pending(result.ligand_molecule_uuid, result.receptor_macromolecule_uuid):
            return
        self._show_result(result)
