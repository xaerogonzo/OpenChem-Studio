"""Two or more molecules, side by side, on everything already computed.

The engine for this existed and was reachable from exactly one place: a
tab inside `BatchAnalysisDialog`, behind building a batch table first. So
"how do these two differ" -- the question somebody asks constantly --
required a workflow nobody would guess at.

**IT NEVER COMPUTES.** Values arrive by event and are remembered, the same
contract the Atom Inspector keeps. Opening this panel, adding a molecule
and switching the reference are all free, and a molecule with nothing
computed shows blank cells rather than starting forty calculators. A
comparison view that silently launches work is one people stop opening.

**DIFFERENCES ONLY is the feature, not a filter.** Aspirin and salicylic
acid agree on most of a long table; the handful of rows where they do not
are the answer, and finding them by eye is exactly the work the table was
supposed to save.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from openchem.chem.comparison import (
    CompareCell,
    ValueRow,
    compare_values,
    differing_rows,
    direction,
    finite_number,
    summary_sentence,
)
from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID, descriptor_help_id
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    DescriptorComputed,
    MoleculeSelected,
    ReportComputed,
    SettingsChanged,
)
from openchem.ui.fact_help import plain_for
from openchem.ui import theme
from openchem.ui.table_export import install_table_export
from openchem.ui.widgets.collapsible_section import WrappedLabel
from openchem.ui.widgets.empty_state import empty_state, empty_state_text, is_empty_state
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

_INTRO = (
    "Molecules side by side, on whatever has already been computed for them. "
    "Nothing here starts a calculation -- a blank cell means that molecule has "
    "not had that calculator run, not that it has no value."
)


#: TIER 2, and the qualifier is the behavioural one: an ABSENT value
#: counts as a difference and stays on screen. Hiding it would be the more
#: misleading of the two choices -- "this molecule has no value for that"
#: is usually the interesting row.
_DIFFERENCES_ONLY_HELP = HelpTooltip(
    text=(
        "Hide every row where the ticked molecules agree.\n\n"
        "Two related structures share most of a long table, and the rows "
        "that differ are the answer -- aspirin against salicylic acid is "
        "15 differing rows out of 29.\n\n"
        "A property one molecule has and another does not counts as a "
        "difference and stays visible."
    ),
    tier=2,
    help_id="compare.differences_only",
    topic="compare",
)

_CALCULATE_HELP = HelpTooltip(
    text=(
        "Work out the everyday properties (mass, LogP, polar surface area, ring and bond counts...) "
        "for the ticked molecules, so there is something to compare.\n\n"
        "Needs two or more molecules ticked. Results already held are reused, not recalculated, and "
        "only the ticked molecules are touched. Values appear as they finish."
    ),
    tier=2,
    help_id="compare.calculate_basics",
    topic="compare",
)

_SHOW_IN_RESULTS_HELP = HelpTooltip(
    text=(
        "Open the selected value in the Results panel, for the molecule whose column it is in. "
        "Double-clicking a value, or pressing Enter on it, does the same.\n\n"
        "On the Property column it opens the first molecule that has a value. Opening a value "
        "selects that molecule; your ticks here do not change."
    ),
    tier=2,
    help_id="compare.show_in_results",
    topic="compare",
)

#: Says what a BLANK cell means, because the export carries them and a
#: reader of the pasted table has no panel text to explain them.
_COPY_TABLE_HELP = HelpTooltip(
    text=(
        "Copy the table as it is shown, as tab-separated text.\n\n"
        "What is copied follows the current view, so \"Differences "
        "only\" narrows the export too. A blank cell means that "
        "calculator has not been run for that molecule -- this panel "
        "never starts a calculation -- rather than a value of nothing."
    ),
    tier=2,
    help_id="compare.copy_table",
    topic="compare",
)


#: Marks the highest value of a row. A plain triangle and not a colour or a tick: higher is not
#: better, and the tooltip says so.
_HIGHEST_MARK = "\u25b2"

#: What a cell's text is for copying, kept apart from what is drawn (the mark is not data).
_RAW_ROLE = Qt.ItemDataRole.UserRole

#: Narrowest a column gets, so many molecules scroll sideways rather than shrink to nothing.
_MIN_COLUMN = 110
#: The most the Property column takes, however long a name is.
_MAX_PROPERTY = 260
#: What a cell adds around its text (margins and the grid line).
_CELL_PADDING = 24


class ComparisonPanel(QWidget):
    """Tick molecules; see their values in columns."""

    #: A cell was asked to be shown in Results: (molecule uuid, report id, fact label).
    #: The window answers it (selects the molecule, reveals the reader); this panel
    #: knows nothing about docks.
    fact_activated = Signal(str, str, str)
    #: "Calculate basic properties" was pressed: the uuids of the ticked molecules. The
    #: window answers it with the same replay-or-compute a selection does, so Compare itself
    #: still never starts anything.
    calculate_requested = Signal(list)

    def __init__(self, event_bus: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: ProjectModel | None = None
        #: molecule uuid -> {row key: cell}. Plain data, accumulated from events;
        #: never widgets and never a molecule object, so nothing here can outlive a
        #: project. A cell keeps the report and fact it came from, which is what lets
        #: a double-click open it in Results.
        self._event_bus = event_bus
        self._settings = None
        #: Whether the plain-English layer (meaning line, highest marker, summary) is shown.
        self._plain_english = True
        self._values: dict[str, dict[str, CompareCell]] = {}
        #: The rows the table shows right now, in table order (set by `_render`).
        self._shown_rows: list[ValueRow] = []
        self._chosen: list[str] = []

        self._molecules = QListWidget(self)
        self._molecules.setMaximumHeight(140)
        self._molecules.itemChanged.connect(self._on_selection_changed)

        self._differences_only = QCheckBox("Differences only", self)
        apply_help_tooltip(self._differences_only, _DIFFERENCES_ONLY_HELP)
        self._differences_only.toggled.connect(self._render)

        self._copy_button = QPushButton("Copy table", self)
        apply_help_tooltip(self._copy_button, _COPY_TABLE_HELP)
        self._copy_button.clicked.connect(self._on_copy_clicked)

        self._calculate_button = QPushButton("Calculate basic properties", self)
        apply_help_tooltip(self._calculate_button, _CALCULATE_HELP)
        self._calculate_button.clicked.connect(self._on_calculate_clicked)
        #: Molecules asked to calculate that have not reported a value yet.
        self._calculating: set[str] = set()
        self._calculating_total = 0
        self._progress = ""
        self._base_status = ""

        self._show_button = QPushButton("Show in Results", self)
        apply_help_tooltip(self._show_button, _SHOW_IN_RESULTS_HELP)
        self._show_button.clicked.connect(self._on_show_clicked)

        self._table = QTableWidget(0, 1, self)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # One line per row and no wrapping: the Interactions panel shipped
        # a table whose wrapped cells made every row taller than the
        # viewport, so it rendered correct data as blank lines.
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)
        # A value that does not fit its column is elided and carries the whole of it in a
        # tooltip. Selection is for COPYING: Ctrl+C takes the highlighted cells, tab-separated,
        # and right-click offers the table as CSV like every other table in the application.
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        install_table_export(self._table, "comparison")
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.currentCellChanged.connect(self._on_current_cell_changed)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self._table, self._activate_current).setContext(
                Qt.ShortcutContext.WidgetShortcut
            )
        QShortcut(QKeySequence.StandardKey.Copy, self._table, self.copy_selection).setContext(
            Qt.ShortcutContext.WidgetShortcut
        )

        self._status = WrappedLabel("", self)
        self._summary = WrappedLabel("", self)
        self._summary.setObjectName("compareSummary")
        self._meaning = WrappedLabel("", self)
        self._meaning.setObjectName("compareMeaning")
        self._empty = empty_state(
            "Nothing to compare yet.",
            "Tick two or more molecules above. Their values appear as "
            "columns as soon as any calculator has run for them.",
            self,
        )

        intro = WrappedLabel(_INTRO, self)
        theme.style(intro, "color: #666666; font-style: italic;")

        controls = QHBoxLayout()
        controls.addWidget(self._differences_only)
        controls.addStretch(1)
        controls.addWidget(self._calculate_button)
        controls.addWidget(self._show_button)
        controls.addWidget(self._copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(QLabel("Molecules:", self))
        layout.addWidget(self._molecules)
        layout.addLayout(controls)
        layout.addWidget(self._summary)
        layout.addWidget(self._empty, 1)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._meaning)
        layout.addWidget(self._status)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor)
        event_bus.subscribe(ReportComputed, self._on_report)
        event_bus.subscribe(AlertComputed, self._on_alert)
        event_bus.subscribe(SettingsChanged, self._on_setting_changed)

        self._render()

    # --- project wiring -----------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._rebuild_molecule_list()
        self._render()

    def _rebuild_molecule_list(self) -> None:
        """Rebuilt wholesale rather than diffed -- there are a handful of
        molecules, and a diff is a second source of truth about what is on
        screen. Ticks survive by uuid, so renaming one does not clear it.
        """
        chosen = set(self._chosen)
        self._molecules.blockSignals(True)
        self._molecules.clear()
        for molecule in (self._project.molecules if self._project else []):
            item = QListWidgetItem(molecule.display_name, self._molecules)
            item.setData(Qt.ItemDataRole.UserRole, molecule.uuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if molecule.uuid in chosen else Qt.CheckState.Unchecked
            )
        self._molecules.blockSignals(False)

    def _on_molecule_selected(self, _event: MoleculeSelected) -> None:
        # Deliberately does NOT change the ticks. The comparison is a
        # deliberate choice of several molecules, and reshuffling it
        # because somebody clicked something else in the tree would
        # silently change what the table on screen describes -- the same
        # reason the Interactions panel's two combos do not follow.
        self._rebuild_molecule_list()

    # --- remembering what other things computed -----------------------------

    def _remember(self, uuid: str, cell: CompareCell) -> None:
        self._values.setdefault(uuid, {})[cell.row_key] = cell
        if uuid in self._chosen:
            self._render()
        # After the render, which rewrites the status line.
        if uuid in self._calculating:
            self._calculating.discard(uuid)
            self._say_progress()

    def _on_descriptor(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if descriptor.value is None:
            return
        display = (
            f"{descriptor.value:.4g}"
            if isinstance(descriptor.value, float)
            else str(descriptor.value)
        )
        self._remember(
            descriptor.molecule_uuid,
            CompareCell(
                display=display,
                units=descriptor.units,
                numeric_value=finite_number(descriptor.value),
                row_key=f"{DESCRIPTOR_AGGREGATE_ID}::{descriptor.descriptor_id}",
                report_id=DESCRIPTOR_AGGREGATE_ID,
                fact_label=descriptor.name,
                help_id=descriptor_help_id(descriptor.descriptor_id),
            ),
        )

    def _remember_fact(self, uuid: str, report_id: str, fact) -> None:
        """One report fact, filed under the report it arrived in (so another report's
        fact of the same wording stays a different row)."""
        origin = fact.origin or report_id
        self._remember(
            uuid,
            CompareCell(
                display=fact.display_value,
                units=fact.units,
                numeric_value=finite_number(fact.value),
                row_key=f"{origin}::{fact.label}",
                report_id=origin,
                fact_label=fact.label,
                help_id=fact.help_id,
                link=fact.link,
            ),
        )

    def _on_report(self, event: ReportComputed) -> None:
        for fact in event.report.facts:
            self._remember_fact(event.report.molecule_uuid, event.report.report_id, fact)

    def _on_alert(self, event: AlertComputed) -> None:
        """An unmigrated calculator, or a plugin's.

        Routed through the same adapter the Property panel uses, so a
        third-party result compares alongside a built-in one rather than
        being absent from the table for a reason nobody could see.
        """
        from openchem.chem.report_adapter import facts_from_alert

        for fact in facts_from_alert(event.alert):
            self._remember_fact(event.alert.molecule_uuid, event.alert.alert_id, fact)

    # --- rendering ----------------------------------------------------------

    def _on_selection_changed(self, _item: QListWidgetItem) -> None:
        self._chosen = [
            self._molecules.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._molecules.count())
            if self._molecules.item(row).checkState() == Qt.CheckState.Checked
        ]
        self._render()

    def compare_with(self, uuids: list[str]) -> None:
        """Tick exactly these molecules.

        Called by "Compare with..." on a report, so the comparison opens
        already showing what the reader was looking at rather than an
        empty table they have to reconstruct.
        """
        self._chosen = [u for u in uuids if u]
        self._rebuild_molecule_list()
        self._render()

    def rows(self) -> list[ValueRow]:
        """What the table is showing, derived rather than stored.

        A test reading this cannot pass against a filter that never
        reached the display.
        """
        if len(self._chosen) < 2:
            return []
        names = {m.uuid: m.display_name for m in (self._project.molecules if self._project else [])}
        columns = [(names.get(uuid, uuid), self._values.get(uuid, {})) for uuid in self._chosen]
        rows = compare_values(columns)
        return differing_rows(rows) if self._differences_only.isChecked() else rows

    def _render(self) -> None:
        rows = self.rows()
        self._shown_rows = rows
        enough_chosen = len(self._chosen) >= 2
        self._calculate_button.setEnabled(enough_chosen)
        enough = len(self._chosen) >= 2
        self._empty.setVisible(not enough or not rows)
        self._table.setVisible(enough and bool(rows))
        if not enough:
            self._set_status("")
            self._summary.setVisible(False)
            self._meaning.setVisible(False)
            return

        names = {m.uuid: m.display_name for m in (self._project.molecules if self._project else [])}
        headers = ["Property", *[names.get(u, u) for u in self._chosen]]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(rows))
        labels: list[str] = []
        for index, row in enumerate(rows):
            label = f"{row.label} ({row.units})" if row.units else row.label
            labels.append(label)
            self._table.setItem(index, 0, self._cell(label))
            found = direction(row) if self._plain_english else None
            for column, value in enumerate(row.values, start=1):
                marked = found is not None and (column - 1) in found.highest
                self._table.setItem(index, column, self._cell(value, found if marked else None))
        self._size_columns(len(headers), labels)
        self._show_summary(names)
        self._show_meaning()

        total = len(compare_values(
            [(names.get(u, u), self._values.get(u, {})) for u in self._chosen]
        ))
        if not rows:
            self._empty_message(total)
            return
        if self._differences_only.isChecked():
            self._set_status(f"{len(rows)} of {total} properties differ.")
        else:
            differing = sum(1 for row in rows if row.differs)
            self._set_status(f"{total} properties, {differing} of them differing.")

    @staticmethod
    def _cell(text: str, highest=None) -> QTableWidgetItem:
        """A cell that can be read in full even where the column cuts it off.

        The drawn text may carry the highest-value mark; the RAW text is kept apart so a copy never
        picks the mark up.
        """
        if highest is None or not text:
            item = QTableWidgetItem(text)
            item.setToolTip(text)
        else:
            item = QTableWidgetItem(f"{text}  {_HIGHEST_MARK}")
            tip = f"{text}\nHighest of the ticked molecules"
            if highest.factor is not None:
                tip += f" (about {highest.factor:.2g} times the lowest)"
            item.setToolTip(tip + ". A higher number is not better or worse by itself.")
        item.setData(_RAW_ROLE, text)
        return item

    def _size_columns(self, count: int, labels: list[str]) -> None:
        """Property column to its names (capped); the molecules SHARE what is left.

        **THE OLD SIZING LET ONE LONG VALUE DECIDE EVERYTHING.** Every molecule column was
        `ResizeToContents` and the Property column took what remained, so one IUPAC name made
        its column 700 px wide, squeezed "Chain atom count" to "Chain atom co...", and pushed
        the second molecule off the right edge (measured with two molecules at 640 px: columns
        100 / 706 / 379 px). A value too long for its column is now elided, with the whole of
        it in the tooltip and in Copy table.
        """
        header = self._table.horizontalHeader()
        header.setMinimumSectionSize(_MIN_COLUMN)
        metrics = self._table.fontMetrics()
        widest = max((metrics.horizontalAdvance(text) for text in labels), default=0)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(0, min(max(widest + _CELL_PADDING, _MIN_COLUMN), _MAX_PROPERTY))
        for column in range(1, count):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

    # --- opening a value in Results ------------------------------------------

    def target_at(self, row: int, column: int) -> tuple[str, str, str] | None:
        """(molecule uuid, report id, fact label) a cell stands for, or None.

        A molecule's own cell answers for that molecule. The Property column answers for the
        first molecule that HAS a value (`ValueRow.source_cell`): the first column's cell may be
        blank, and opening a fact that molecule does not have would be the wrong answer.
        """
        if not 0 <= row < len(self._shown_rows):
            return None
        value_row = self._shown_rows[row]
        if column >= 1:
            index = column - 1
            cell = value_row.cells[index] if index < len(value_row.cells) else None
        else:
            found = value_row.source_cell()
            index, cell = found if found is not None else (0, None)
        if cell is None or not cell.display or not cell.report_id or index >= len(self._chosen):
            return None
        return self._chosen[index], cell.report_id, cell.fact_label

    def activate(self, row: int, column: int) -> bool:
        """Ask for a cell to be shown in Results. The ONE route every gesture takes."""
        target = self.target_at(row, column)
        if target is None:
            self.set_notice(
                "There is no value there to show. A blank cell means that calculator has not "
                "been run for that molecule."
            )
            return False
        self.fact_activated.emit(*target)
        return True

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        self.activate(row, column)

    def _activate_current(self) -> None:
        self.activate(self._table.currentRow(), max(self._table.currentColumn(), 0))

    def _on_show_clicked(self, _checked: bool = False) -> None:
        self._activate_current()

    def _on_calculate_clicked(self, _checked: bool = False) -> None:
        self._progress = ""
        self._calculating = set(self._chosen)
        self._calculating_total = len(self._chosen)
        self._say_progress()
        self.calculate_requested.emit(list(self._chosen))

    def calculation_skipped(self, uuids: list[str]) -> None:
        """Molecules the window could not start (no structure): they will never report."""
        self._calculating.difference_update(uuids)
        self._say_progress()

    def _say_progress(self) -> None:
        if not self._calculating_total:
            return
        done = self._calculating_total - len(self._calculating)
        finished = False
        if self._calculating:
            self._progress = (
                f"Calculating basic properties... {done} of {self._calculating_total} "
                "molecules have values so far."
            )
        else:
            self._progress = "Basic properties are in for every ticked molecule that has a structure."
            self._calculating_total = 0
            finished = True
        self._set_status(self._base_status)
        if finished:
            # Said once; the next render goes back to the table's own line.
            self._progress = ""

    def _set_status(self, text: str) -> None:
        """The table's own status line, with any calculation progress after it.

        Progress is kept apart because every arriving value re-renders the table, and a status
        line that was overwritten each time would flash the count and lose it.
        """
        self._base_status = text
        self._status.setText(f"{text}  {self._progress}".strip() if self._progress else text)

    # --- plain English ---------------------------------------------------------------

    def attach_settings(self, settings) -> None:
        """Follow the Plain English preference, now and whenever it changes."""
        from openchem.app.settings import PLAIN_ENGLISH

        self._settings = settings
        self.set_plain_english(bool(settings.preference(PLAIN_ENGLISH)))

    def _on_setting_changed(self, event: SettingsChanged) -> None:
        from openchem.app.settings import PLAIN_ENGLISH

        if event.key == PLAIN_ENGLISH.key and self._settings is not None:
            self.set_plain_english(bool(self._settings.preference(PLAIN_ENGLISH)))

    def set_plain_english(self, enabled: bool) -> None:
        if enabled == self._plain_english:
            return
        self._plain_english = enabled
        self._render()
        if not enabled:
            self._summary.setText("")
            self._meaning.setText("")

    def _show_summary(self, names: dict[str, str]) -> None:
        text = ""
        if self._plain_english and len(self._chosen) == 2:
            text = summary_sentence([names.get(u, u) for u in self._chosen], self._shown_rows)
        self._summary.setText(text)
        self._summary.setVisible(bool(text))

    def _on_current_cell_changed(self, row: int, _column: int, _old_row: int, _old_col: int) -> None:
        self._show_meaning()

    def _show_meaning(self) -> None:
        """What the selected row means, and who has the highest value, in everyday words."""
        row = self._table.currentRow()
        text = ""
        if self._plain_english and 0 <= row < len(self._shown_rows):
            value_row = self._shown_rows[row]
            help_id = next((c.help_id for c in value_row.cells if c is not None and c.help_id), "")
            meaning = plain_for(help_id)
            if meaning:
                text = f"{value_row.label}: {meaning}"
                found = direction(value_row)
                if found is not None:
                    names = {m.uuid: m.display_name for m in (self._project.molecules if self._project else [])}
                    who = ", ".join(names.get(self._chosen[i], "?") for i in found.highest)
                    text += f"  Highest here: {who}."
        self._meaning.setText(text)
        self._meaning.setVisible(bool(text))

    def set_notice(self, text: str) -> None:
        """Say something under the table (replaced by the next render's own status)."""
        self._status.setText(text)

    def selection_text(self) -> str:
        """The highlighted cells as tab-separated text, rows in table order.

        Whole values, not what the column shows: a cut-off cell copies in full.
        """
        cells = sorted(
            (i.row(), i.column(), self._table.item(i.row(), i.column()))
            for i in self._table.selectedIndexes()
        )
        rows: dict[int, list[str]] = {}
        for row, _column, item in cells:
            rows.setdefault(row, []).append(
                (item.data(_RAW_ROLE) if item.data(_RAW_ROLE) is not None else item.text())
                if item is not None
                else ""
            )
        return "\n".join("\t".join(values) for values in rows.values())

    def copy_selection(self) -> None:
        text = self.selection_text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _empty_message(self, total: int) -> None:
        """Two different empty states, because they mean opposite things.

        Nothing computed yet is "go and run something". Everything
        agreeing is a RESULT -- these molecules are identical on every
        property known -- and showing the same "nothing here" message for
        both would hide it.
        """
        from openchem.ui.widgets.empty_state import set_empty_state_message

        if total:
            set_empty_state_message(
                self._empty,
                "These molecules agree on everything computed so far.",
                f"All {total} properties match. Untick "
                '"Differences only" to see them, or run more calculators.',
            )
            self._set_status(f"0 of {total} properties differ.")
        else:
            set_empty_state_message(
                self._empty,
                "Nothing to compare yet.",
                "Tick two or more molecules above. Their values appear as "
                "columns as soon as any calculator has run for them -- or press "
                '"Calculate basic properties".',
            )
            self._set_status("")

    def empty_message(self) -> str:
        return empty_state_text(self._empty) if is_empty_state(self._empty) else ""

    # --- export -------------------------------------------------------------

    def _on_copy_clicked(self, _checked: bool = False) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.as_text())

    def as_text(self) -> str:
        """The table as tab-separated text, for a spreadsheet or a message.

        Tabs rather than the four formats `FactView` offers: this is a
        grid, and a grid pastes into a spreadsheet cleanly only as TSV.
        """
        rows = self.rows()
        if not rows:
            return ""
        names = {m.uuid: m.display_name for m in (self._project.molecules if self._project else [])}
        lines = ["\t".join(["Property", *[names.get(u, u) for u in self._chosen]])]
        for row in rows:
            label = f"{row.label} ({row.units})" if row.units else row.label
            lines.append("\t".join([label, *row.values]))
        return "\n".join(lines)
