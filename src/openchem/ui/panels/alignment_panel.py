"""Superimpose several of the project's molecules in one 3D frame.

Marvin's 3D Alignment plugin compares two or more structures; the
registry calculator built alongside it can only take one molecule plus a
typed-in reference SMILES, because `CalculatorRegistry.compute` receives
exactly one molecule and no project handle. This panel is where the
multi-molecule case lives, for the same reason docking has its own panel.

The result is shown in an embedded 3D view rather than the structure
GRID the other `StructureSetResult` calculators use: a grid of 2D
depictions cannot show a superposition, which is the entire output here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import AlignmentJobStateChanged, EnsembleAlignmentReady
from openchem.services.alignment_service import AlignmentService
from openchem.ui.molecule_combo import repopulate
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.flow_layout import flow_row
from openchem.ui.widgets.pop_out_host import PopOutHost
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: The results table is capped rather than free: an ensemble of ten would
#: otherwise push the 3D view -- this panel's entire output -- back down to
#: a strip. Below the cap it shrinks to its rows and the overlay gets the
#: difference.
_TABLE_MAX_HEIGHT = 160
_TABLE_MIN_HEIGHT = 64

_RESULT_COLUMNS = (
    "Show",
    "Molecule",
    "Score",
    "RMSD (A)",
    "Core",
    "Tail",
    "Paired atoms",
    "Geometry",
)

# Deliberately not a gradient: these identify structures, so neighbouring
# entries have to be told apart at a glance. Colour-blind-safe ordering
# (Okabe-Ito), with the reference's grey first so it reads as the fixed
# frame everything else was moved onto.
_ENSEMBLE_COLORS = (
    "#888888",
    "#0072b2",
    "#d55e00",
    "#009e73",
    "#cc79a7",
    "#e69f00",
    "#56b4e9",
    "#f0e442",
)

_METHOD_NOTE = (
    "Extended atom types pairs atoms by MMFF type (Open3DAlign). Common scaffold fixes the "
    "pairing from the 2D maximum common substructure first, then refines everything else "
    "around it. Score is an overlap quality where HIGHER is better; RMSD is a distance in "
    "angstroms where LOWER is better -- they are not the same measure."
)


#: THREE OF THESE ARE TIER 3, AND EACH FOR A DIFFERENT WAY OF BEING
#: CONFIDENTLY WRONG. `Score` and `RMSD (A)` run in OPPOSITE directions
#: and are not the same measure -- the panel's own note already says so,
#: and the note is above the table rather than on it. `Paired atoms` is
#: the denominator both of them are quietly relative to.
_HELP: dict[str, HelpTooltip] = {
    "flexibility": HelpTooltip(
        text=(
            "Whether the molecule being aligned may change its "
            "conformation to fit.\n\n"
            "FLEXIBLE builds it with its shared atoms pinned to the "
            "reference's own coordinates, so a substituent on a rotatable "
            "bond can swing into place. RIGID keeps the geometry it was "
            "given and only rotates and translates it.\n\n"
            "The alignment itself is a rigid superposition either way, so "
            "on RIGID a flexible side chain lands wherever its starting "
            "conformer happened to put it -- the shared core will still "
            "overlay perfectly and the score will still look healthy. "
            "Compare the Core and Tail columns rather than the single "
            "RMSD. Default: Flexible."
        ),
        tier=3,
        help_id="alignment.flexibility",
        topic="alignment",
    ),
    "color_mode": HelpTooltip(
        text=(
            "What the colours in the 3D view mean.\n\n"
            "BY MOLECULE gives each structure one colour, which answers "
            "'which of these is this atom in'. BY ELEMENT uses the usual "
            "element colours, which answers 'what is it'. Neither "
            "replaces the other; the overlay is the same either way."
        ),
        tier=1,
        help_id="alignment.overlay_color_mode",
        topic="alignment",
    ),
    "Show": HelpTooltip(
        text=(
            "Hide or show this structure in the 3D view.\n\n"
            "Hiding one removes it from the picture only -- it is still "
            "aligned, its numbers are unchanged, and its colour is kept "
            "so showing it again does not renumber anything. Useful for "
            "comparing two of a larger overlay."
        ),
        tier=1,
        help_id="alignment.entry_visible",
        topic="alignment",
    ),
    "Core": HelpTooltip(
        text=(
            "RMSD in angstroms over the RIGID part of the shared "
            "substructure, after alignment. Lower is better.\n\n"
            "'Rigid' is derived: the largest fused ring system of the "
            "shared substructure, plus everything reachable from it "
            "without crossing a rotatable bond.\n\n"
            "It is normally the smaller of the two numbers, because a "
            "rigid superposition can always fit a rigid fragment. A LARGE "
            "core RMSD means the two structures were not really "
            "superimposed at all."
        ),
        tier=3,
        help_id="alignment.core_rmsd",
        topic="alignment",
    ),
    "Tail": HelpTooltip(
        text=(
            "RMSD in angstroms over the FLEXIBLE part of the shared "
            "substructure, after alignment. Lower is better.\n\n"
            "Everything separated from the rigid core by at least one "
            "rotatable bond. Measured over the same atom correspondence "
            "as Core, so the two are directly comparable -- what "
            "separates them is flexibility, not which atoms matched.\n\n"
            "**THIS IS THE NUMBER THE SINGLE RMSD CANNOT SHOW YOU.** A "
            "result can report a small RMSD while a side chain sits an "
            "angstrom out of place, because the reported figure is "
            "dominated by the rigid core. A Tail much larger than the "
            "Core means the substituent did not overlay; try Flexible.\n\n"
            "Blank when the shared substructure has no flexible part."
        ),
        tier=3,
        help_id="alignment.flexible_rmsd",
        topic="alignment",
    ),
    "Geometry": HelpTooltip(
        text=(
            "Where this molecule's 3D coordinates came from.\n\n"
            "PROJECT -- a conformer already stored for it.\n"
            "GENERATED -- one built for this alignment.\n"
            "CONSTRAINED -- built for this alignment with its shared "
            "atoms pinned to the reference's coordinates.\n\n"
            "It matters because results begun from different geometries "
            "are not comparable. A Flexible run that reports GENERATED "
            "means pinning was not geometrically possible for this pair "
            "and it fell back."
        ),
        tier=3,
        help_id="alignment.geometry_source",
        topic="alignment",
    ),
    "reference": HelpTooltip(
        text=(
            "The molecule everything else is moved onto. It is not "
            "moved itself.\n\n"
            "Every score and RMSD below is measured against THIS "
            "structure, so changing it re-frames the whole table rather "
            "than adding to it."
        ),
        tier=2,
        help_id="alignment.reference",
        topic="alignment",
    ),
    "method": HelpTooltip(
        text=(
            "How atoms are paired up before the overlay is "
            "optimised.\n\n"
            "\"Extended atom types\" pairs by MMFF atom type "
            "(Open3DAlign), which encodes element, hybridisation and "
            "environment. \"Common scaffold (MCS)\" fixes the pairing "
            "from the 2D maximum common substructure first and refines "
            "the rest around it, which is the one to reach for when two "
            "molecules share a core you care about keeping superimposed."
        ),
        tier=2,
        help_id="alignment.method",
        topic="alignment",
    ),
    "accuracy": HelpTooltip(
        text=(
            "How hard to search: how many starting conformers are tried, "
            "and how long the scaffold search may run.\n\n"
            "Fast 1 conformer / 5 s, Normal 5 / 15 s, Accurate 20 / 60 s. "
            "Default Normal. Cost is roughly linear in the conformer "
            "count. More conformers is a better CHANCE of finding the "
            "pose that really overlays, not a more precise measurement of "
            "one -- an alignment that already found its best pose does "
            "not improve."
        ),
        tier=2,
        help_id="alignment.accuracy",
        topic="alignment",
    ),
    "align": HelpTooltip(
        text=(
            "Align every ticked molecule onto the reference and show them "
            "together.\n\n"
            "The alignment is for DISPLAY and comparison: the stored "
            "structures are not moved, so nothing downstream sees "
            "different coordinates."
        ),
        tier=2,
        help_id="alignment.run",
        topic="alignment",
    ),
    "style": HelpTooltip(
        text=(
            "How the overlaid structures are drawn in the viewer "
            "below.\n\n"
            "Display only; it changes no result in the table."
        ),
        tier=1,
        help_id="alignment.display_style",
        topic="alignment",
    ),
    "Molecule": HelpTooltip(
        text=(
            "Which molecule this row's alignment is for.\n\n"
            "The reference itself has no row: it is what the others were "
            "measured against."
        ),
        tier=1,
        help_id="alignment.subject",
        topic="alignment",
    ),
    "Score": HelpTooltip(
        text=(
            "Open3DAlign's overlap quality. HIGHER is better, and it has "
            "no units.\n\n"
            "It is not a distance and does not run in the same direction "
            "as RMSD -- a molecule can score well and still sit further "
            "away than one that scores worse.\n\n"
            "IT IS ALSO NOT COMPARABLE ACROSS ROWS THAT WERE TYPED "
            "DIFFERENTLY. MMFF typing is used where it can be, and "
            "Crippen typing is the fallback for elements MMFF cannot type "
            "-- selenium and platinum among them -- and the two scales are "
            "unrelated. Nothing in this column says which one a row used."
        ),
        tier=3,
        help_id="alignment.score",
        topic="alignment",
    ),
    "RMSD (A)": HelpTooltip(
        text=(
            "Root-mean-square distance in angstroms between the paired "
            "atoms after alignment. LOWER is better.\n\n"
            "Measured against the REFERENCE MOLECULE in this project, "
            "never against an experimental structure, so it says how "
            "alike two computed poses are and nothing about whether "
            "either is right.\n\n"
            "It is an average over the PAIRED atoms only. A low value "
            "over few pairs is a good overlay of a small common part, not "
            "a better overlay -- read it with \"Paired atoms\"."
        ),
        tier=3,
        help_id="alignment.rmsd",
        topic="alignment",
    ),
    "Paired atoms": HelpTooltip(
        text=(
            "How many atoms the method managed to pair between this "
            "molecule and the reference.\n\n"
            "This is the denominator the other two columns are relative "
            "to. Two molecules that share little structure pair few "
            "atoms, and both their Score and their RMSD then describe "
            "only that small shared part."
        ),
        tier=3,
        help_id="alignment.paired_atoms",
        topic="alignment",
    ),
}


class AlignmentPanel(QWidget):
    """Pick a reference and any number of molecules to align onto it."""

    def __init__(
        self,
        alignment_service: AlignmentService,
        event_bus: EventBus,
        parent: QWidget | None = None,
        settings: object = None,
    ) -> None:
        super().__init__(parent)
        self._alignment_service = alignment_service
        self._event_bus = event_bus
        self._project: ProjectModel | None = None
        self._entries: list[EnsembleEntry] = []
        # Row index -> shown. Kept apart from the colour map so hiding an
        # entry never renumbers a colour: the whole point of the overlay is
        # that a structure keeps the colour the table says it has.
        self._visible: dict[int, bool] = {}
        self._colors: dict[int, str] = {}
        self._suspend_visibility = False

        self._reference_combo = QComboBox(self)
        self._reference_combo.currentIndexChanged.connect(self._on_reference_changed)
        apply_help_tooltip(self._reference_combo, _HELP['reference'])

        self._probe_list = QListWidget(self)
        self._probe_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._probe_list.setMaximumHeight(140)

        self._method_combo = QComboBox(self)
        from openchem.chem.alignment import ACCURACY_LEVELS, ALIGNMENT_METHODS

        self._method_combo.addItems(list(ALIGNMENT_METHODS))
        apply_help_tooltip(self._method_combo, _HELP['method'])
        self._accuracy_combo = QComboBox(self)
        self._accuracy_combo.addItems(list(ACCURACY_LEVELS))
        self._accuracy_combo.setCurrentText("Normal")
        apply_help_tooltip(self._accuracy_combo, _HELP['accuracy'])

        from openchem.chem.alignment import DEFAULT_FLEXIBILITY, FLEXIBILITY_MODES

        self._flexibility_combo = QComboBox(self)
        self._flexibility_combo.addItems(list(FLEXIBILITY_MODES))
        self._flexibility_combo.setCurrentText(
            next(k for k, v in FLEXIBILITY_MODES.items() if v == DEFAULT_FLEXIBILITY)
        )
        apply_help_tooltip(self._flexibility_combo, _HELP['flexibility'])

        self._align_button = QPushButton("Align", self)
        self._align_button.clicked.connect(self._on_align_clicked)
        apply_help_tooltip(self._align_button, _HELP['align'])
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)

        self._result_table = QTableWidget(0, len(_RESULT_COLUMNS), self)
        self._result_table.setHorizontalHeaderLabels(_RESULT_COLUMNS)
        # On the header ITEMS -- QTableWidgetItems, not widgets; see
        # `docking_panel.py` for why the distinction matters to the walk.
        for column, name in enumerate(_RESULT_COLUMNS):
            item = self._result_table.horizontalHeaderItem(column)
            if item is not None:
                apply_help_tooltip(item, _HELP[name])
        self._result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._result_table.setMaximumHeight(_TABLE_MAX_HEIGHT)
        self._result_table.itemChanged.connect(self._on_visibility_changed)

        self._viewer = Mol3DViewerBackend(self)
        self._style_combo = QComboBox(self)
        self._style_combo.addItems(["stick", "ballstick", "sphere", "line"])
        self._style_combo.currentTextChanged.connect(self._viewer.set_style)
        apply_help_tooltip(self._style_combo, _HELP['style'])

        self._color_mode_combo = QComboBox(self)
        self._color_mode_combo.addItem("By molecule", "molecule")
        self._color_mode_combo.addItem("By element", "element")
        self._color_mode_combo.currentIndexChanged.connect(self._on_color_mode_changed)
        apply_help_tooltip(self._color_mode_combo, _HELP['color_mode'])

        note = QLabel(_METHOD_NOTE, self)
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Reference:", self._reference_combo)
        form.addRow("Align onto it:", self._probe_list)
        form.addRow("Method:", self._method_combo)
        # ACCURACY AND FLEXIBILITY SHARE ONE ROW, and that is not tidiness.
        # This panel's reported problem is vertical space -- the settings
        # box, the note, the table and the style row are all fixed height
        # and the overlay gets what is left, which in a 420 px dock is a
        # strip about 90 px tall. Adding Flexibility as a form row of its
        # own would have made the thing that was complained about worse.
        #
        # `flow_row` rather than a QHBoxLayout, because a horizontal
        # layout's minimum width is the SUM of its children and this panel
        # has already set the whole window's minimum once that way. It
        # wraps to two lines when the dock is narrow, which costs the
        # height back only where there is no width to spend instead.
        options = flow_row(self)
        options.layout().addWidget(QLabel("Accuracy:", self))
        options.layout().addWidget(self._accuracy_combo)
        options.layout().addWidget(QLabel("Flexibility:", self))
        options.layout().addWidget(self._flexibility_combo)
        form.addRow(options)

        settings_box = QGroupBox("Alignment", self)
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addLayout(form)
        settings_layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addWidget(self._align_button)
        buttons.addStretch(1)
        settings_layout.addLayout(buttons)
        settings_layout.addWidget(self._status_label)

        # THE STYLE ROW BECOMES THE HOST'S HEADER rather than a row of its
        # own. This panel's whole problem is vertical space -- the group
        # box, the table and this row are all fixed height and the viewer
        # gets whatever is left, which in a 420 px dock is a strip about
        # 90 px tall -- so the pop-out button joins a row that already
        # exists instead of adding another.
        #
        # The header STAYS HERE while the view is detached, deliberately:
        # the backend holds the page and the channel rather than the
        # parent, so `Style:` goes on driving the overlay in its own
        # window from the dock. See `pop_out_host` for why a duplicate
        # control in that window would be worse than none.
        self._viewer_host = PopOutHost(
            self._viewer.widget(),
            title="3D Alignment",
            settings_id="alignment.overlay",
            settings=settings,
            header=[
                QLabel("Style:", self),
                self._style_combo,
                QLabel("Colour:", self),
                self._color_mode_combo,
            ],
            parent=self,
        )

        layout = QVBoxLayout(self)
        layout.addWidget(settings_box)
        layout.addWidget(self._result_table)
        layout.addWidget(self._viewer_host, 1)

        event_bus.subscribe(AlignmentJobStateChanged, self._on_job_state_changed)
        event_bus.subscribe(EnsembleAlignmentReady, self._on_alignment_ready)

    # --- project wiring ---------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        molecules = list(project.molecules) if project is not None else []

        # This panel got the preserve-by-uuid behaviour first; it now lives
        # in ui/molecule_combo.py because the Quantum Chemistry and Docking
        # panels were missing it and silently ran on the wrong molecule.
        # The reference is NOT wired to MoleculeSelected: it is a deliberate
        # pick that the probe list is defined against, so following the tree
        # would reshuffle the checkboxes underneath the user.
        repopulate(self._reference_combo, [(m.display_name, m.uuid) for m in molecules])
        self._rebuild_probe_list()

    def _rebuild_probe_list(self) -> None:
        """Everything except the reference, each with a checkbox.

        Checked state is preserved across rebuilds by uuid -- `set_project`
        is called on every project mutation (see MainWindow's
        `_refresh_project_panels`), and silently clearing the user's
        selection because an unrelated molecule was renamed would be its
        own bug.
        """
        checked = {
            self._probe_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._probe_list.count())
            if self._probe_list.item(row).checkState() == Qt.CheckState.Checked
        }
        reference_uuid = self._reference_combo.currentData()
        self._probe_list.clear()
        molecules = list(self._project.molecules) if self._project is not None else []
        for molecule in molecules:
            if molecule.uuid == reference_uuid:
                continue
            item = QListWidgetItem(molecule.display_name)
            item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if molecule.uuid in checked else Qt.CheckState.Unchecked
            )
            self._probe_list.addItem(item)

    def _on_reference_changed(self) -> None:
        self._rebuild_probe_list()

    # --- running ----------------------------------------------------------

    def _checked_uuids(self) -> list[str]:
        return [
            self._probe_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._probe_list.count())
            if self._probe_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _on_align_clicked(self) -> None:
        if self._project is None:
            return
        reference_uuid = self._reference_combo.currentData()
        by_uuid = {molecule.uuid: molecule for molecule in self._project.molecules}
        reference = by_uuid.get(reference_uuid)
        if reference is None:
            self._status_label.setText("Pick a reference molecule first.")
            return
        probes = [by_uuid[uuid] for uuid in self._checked_uuids() if uuid in by_uuid]
        if not probes:
            self._status_label.setText("Tick at least one molecule to align onto the reference.")
            return

        from openchem.chem.alignment import ALIGNMENT_METHODS

        from openchem.chem.alignment import FLEXIBILITY_MODES

        self._alignment_service.request_alignment(
            reference,
            probes,
            method=ALIGNMENT_METHODS[self._method_combo.currentText()],
            accuracy=self._accuracy_combo.currentText(),
            flexibility=FLEXIBILITY_MODES[self._flexibility_combo.currentText()],
        )

    def _on_job_state_changed(self, event: AlignmentJobStateChanged) -> None:
        running = event.state in (CacheState.QUEUED, CacheState.RUNNING)
        self._align_button.setEnabled(not running)
        self._status_label.setText(event.message or event.state.value)

    def _on_alignment_ready(self, event: EnsembleAlignmentReady) -> None:
        self._entries = event.entries
        # Assigned ONCE and handed to both consumers. A failed entry gets
        # no colour and no model, so the table's row index and the
        # viewer's model index do not line up -- deriving the colour
        # separately in each place is how they would silently disagree
        # about which structure is which, which is the one thing an
        # overlay must not get wrong.
        colors: dict[int, str] = {}
        for position, index in enumerate(
            i for i, entry in enumerate(event.entries) if entry.aligned and entry.molblock
        ):
            colors[index] = _ENSEMBLE_COLORS[position % len(_ENSEMBLE_COLORS)]
        self._colors = colors
        self._visible = {index: True for index in colors}
        self._populate_table(event.entries, colors)
        self._show_ensemble()

    def _populate_table(self, entries: list[EnsembleEntry], colors: dict[int, str]) -> None:
        # `setItem` emits itemChanged, which is the visibility handler --
        # without this the table reloads the overlay once per cell while it
        # is still being filled.
        self._suspend_visibility = True
        try:
            self._result_table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                self._fill_row(row, entry, colors)
        finally:
            self._suspend_visibility = False
        self._fit_table_height()

    def _fill_row(self, row: int, entry: EnsembleEntry, colors: dict[int, str]) -> None:
        show = QTableWidgetItem()
        if row in colors:
            show.setFlags(
                (show.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsSelectable
            )
            show.setCheckState(
                Qt.CheckState.Checked if self._visible.get(row, True) else Qt.CheckState.Unchecked
            )
            apply_help_tooltip(show, _HELP["Show"])
        else:
            # A failed entry has nothing to show, and a tickable box that
            # does nothing is worse than no box.
            show.setFlags(Qt.ItemFlag.NoItemFlags)
        self._result_table.setItem(row, 0, show)

        name = QTableWidgetItem(entry.label)
        if row in colors:
            name.setForeground(QColor(colors[row]))
        self._result_table.setItem(row, 1, name)

        if not entry.aligned:
            # The reason spans the numeric columns -- a failed entry has no
            # score or RMSD, and blank cells would read as zeros rather
            # than as "this one did not align".
            reason = QTableWidgetItem(entry.error or "Alignment failed")
            self._result_table.setItem(row, 2, reason)
            self._result_table.setSpan(row, 2, 1, len(_RESULT_COLUMNS) - 2)
            return

        self._result_table.setSpan(row, 2, 1, 1)
        if entry.score is None:
            # The reference itself: it defines the frame, so it has no
            # score against anything.
            for column in range(2, len(_RESULT_COLUMNS)):
                self._result_table.setItem(row, column, QTableWidgetItem("-"))
            return

        self._result_table.setItem(row, 2, QTableWidgetItem(f"{entry.score:.2f}"))
        self._result_table.setItem(
            row, 3, QTableWidgetItem("-" if entry.rmsd is None else f"{entry.rmsd:.3f}")
        )
        self._result_table.setItem(row, 4, QTableWidgetItem(_number(entry.core_rmsd)))
        self._result_table.setItem(row, 5, QTableWidgetItem(_number(entry.flexible_rmsd)))
        self._result_table.setItem(row, 6, QTableWidgetItem(_paired_atoms(entry)))
        self._result_table.setItem(row, 7, QTableWidgetItem(_geometry_label(entry)))

    def _fit_table_height(self) -> None:
        """Size the results table to its rows, up to the cap.

        A FIXED 160 px FOR TWO ROWS IS 70 px THE OVERLAY DOES NOT GET, and
        this panel's reported problem is exactly that: measured in the
        running app, the settings box takes 414, the table 160, and the 3D
        view is left a 63 px strip -- for a panel whose entire output is
        that picture.

        Capped rather than unbounded, because a ten-molecule ensemble would
        otherwise push the viewer back out. Below the cap the space goes
        where it is worth something.
        """
        rows = self._result_table.rowCount()
        header = self._result_table.horizontalHeader().height()
        body = sum(self._result_table.rowHeight(row) for row in range(rows))
        frame = 2 * self._result_table.frameWidth()
        scrollbar = (
            self._result_table.horizontalScrollBar().height()
            if self._result_table.horizontalScrollBar().isVisible()
            else 0
        )
        self._result_table.setFixedHeight(
            min(_TABLE_MAX_HEIGHT, max(_TABLE_MIN_HEIGHT, header + body + frame + scrollbar))
        )

    def _on_visibility_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_visibility or item.column() != 0:
            return
        self._visible[item.row()] = item.checkState() == Qt.CheckState.Checked
        self._show_ensemble()

    def _on_color_mode_changed(self, _index: int) -> None:
        self._viewer.set_ensemble_color_mode(self._color_mode_combo.currentData())

    def _show_ensemble(self) -> None:
        """Draw the entries that are ticked, in their assigned colours.

        A hidden entry is OMITTED rather than drawn transparent, so the
        cost of hiding is a model the page does not build. Its colour is
        untouched, so ticking it back on restores the same picture.
        """
        self._viewer.load_ensemble(
            [
                (self._entries[index].molblock, color)
                for index, color in sorted(self._colors.items())
                if self._visible.get(index, True)
            ]
        )


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _paired_atoms(entry: EnsembleEntry) -> str:
    """The MCS size when there is one, otherwise O3A's match count.

    TWO DIFFERENT NUMBERS UNDER ONE HEADING WOULD BE THE ORIGINAL BUG.
    The panel used to print `matched_atoms` unconditionally, and on the
    pair this was reported against that read "14 paired atoms" for a
    maximum common substructure of 33. Which one is meaningful depends on
    the method, so the cell says which it is showing.
    """
    if entry.mcs_atom_count:
        return f"{entry.mcs_atom_count} (MCS)"
    return str(entry.matched_atoms)


def _geometry_label(entry: EnsembleEntry) -> str:
    """Rendered from the stored vocabulary, never paraphrased.

    "Generated geometry" for `embedded` would reintroduce exactly the
    rediscovered meaning the field exists to prevent, so the map is the
    producer's and an unknown value shows itself rather than being
    silently blanked.
    """
    from openchem.chem.alignment import GEOMETRY_SOURCE_LABELS

    if not entry.geometry_source:
        return "-"
    return GEOMETRY_SOURCE_LABELS.get(entry.geometry_source, entry.geometry_source)
