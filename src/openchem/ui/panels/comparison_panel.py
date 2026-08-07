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

from PySide6.QtCore import Qt
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

from openchem.chem.comparison import ValueRow, compare_values, differing_rows
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    DescriptorComputed,
    MoleculeSelected,
    ReportComputed,
)
from openchem.ui.widgets.collapsible_section import WrappedLabel
from openchem.ui.widgets.empty_state import empty_state, empty_state_text, is_empty_state

_INTRO = (
    "Molecules side by side, on whatever has already been computed for them. "
    "Nothing here starts a calculation -- a blank cell means that molecule has "
    "not had that calculator run, not that it has no value."
)


class ComparisonPanel(QWidget):
    """Tick molecules; see their values in columns."""

    def __init__(self, event_bus: EventBus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: ProjectModel | None = None
        #: molecule uuid -> {label: (display_value, units)}. Plain data,
        #: accumulated from events; never widgets and never a molecule
        #: object, so nothing here can outlive a project.
        self._values: dict[str, dict[str, tuple[str, str]]] = {}
        self._chosen: list[str] = []

        self._molecules = QListWidget(self)
        self._molecules.setMaximumHeight(140)
        self._molecules.itemChanged.connect(self._on_selection_changed)

        self._differences_only = QCheckBox("Differences only", self)
        self._differences_only.setToolTip(
            "Hide every row where the molecules agree.\n\n"
            "Two related structures share most of a long table; the rows "
            "that differ are the answer."
        )
        self._differences_only.toggled.connect(self._render)

        self._copy_button = QPushButton("Copy table", self)
        self._copy_button.clicked.connect(self._on_copy_clicked)

        self._table = QTableWidget(0, 1, self)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # One line per row and no wrapping: the Interactions panel shipped
        # a table whose wrapped cells made every row taller than the
        # viewport, so it rendered correct data as blank lines.
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)

        self._status = WrappedLabel("", self)
        self._empty = empty_state(
            "Nothing to compare yet.",
            "Tick two or more molecules above. Their values appear as "
            "columns as soon as any calculator has run for them.",
            self,
        )

        intro = WrappedLabel(_INTRO, self)
        intro.setStyleSheet("color: #666666; font-style: italic;")

        controls = QHBoxLayout()
        controls.addWidget(self._differences_only)
        controls.addStretch(1)
        controls.addWidget(self._copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(QLabel("Molecules:", self))
        layout.addWidget(self._molecules)
        layout.addLayout(controls)
        layout.addWidget(self._empty, 1)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._status)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(DescriptorComputed, self._on_descriptor)
        event_bus.subscribe(ReportComputed, self._on_report)
        event_bus.subscribe(AlertComputed, self._on_alert)

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

    def _remember(self, uuid: str, label: str, display: str, units: str) -> None:
        self._values.setdefault(uuid, {})[label] = (display, units)
        if uuid in self._chosen:
            self._render()

    def _on_descriptor(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if descriptor.value is None:
            return
        display = (
            f"{descriptor.value:.4g}"
            if isinstance(descriptor.value, float)
            else str(descriptor.value)
        )
        self._remember(descriptor.molecule_uuid, descriptor.name, display, descriptor.units)

    def _on_report(self, event: ReportComputed) -> None:
        for fact in event.report.facts:
            self._remember(
                event.report.molecule_uuid, fact.label, fact.display_value, fact.units
            )

    def _on_alert(self, event: AlertComputed) -> None:
        """An unmigrated calculator, or a plugin's.

        Routed through the same adapter the Property panel uses, so a
        third-party result compares alongside a built-in one rather than
        being absent from the table for a reason nobody could see.
        """
        from openchem.chem.report_adapter import facts_from_alert

        for fact in facts_from_alert(event.alert):
            self._remember(
                event.alert.molecule_uuid, fact.label, fact.display_value, fact.units
            )

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
        enough = len(self._chosen) >= 2
        self._empty.setVisible(not enough or not rows)
        self._table.setVisible(enough and bool(rows))
        if not enough:
            self._status.setText("")
            return

        names = {m.uuid: m.display_name for m in (self._project.molecules if self._project else [])}
        headers = ["Property", *[names.get(u, u) for u in self._chosen]]
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        self._table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            label = f"{row.label} ({row.units})" if row.units else row.label
            self._table.setItem(index, 0, QTableWidgetItem(label))
            for column, value in enumerate(row.values, start=1):
                self._table.setItem(index, column, QTableWidgetItem(value))

        total = len(compare_values(
            [(names.get(u, u), self._values.get(u, {})) for u in self._chosen]
        ))
        if not rows:
            self._empty_message(total)
            return
        if self._differences_only.isChecked():
            self._status.setText(f"{len(rows)} of {total} properties differ.")
        else:
            differing = sum(1 for row in rows if row.differs)
            self._status.setText(f"{total} properties, {differing} of them differing.")

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
            self._status.setText(f"0 of {total} properties differ.")
        else:
            set_empty_state_message(
                self._empty,
                "Nothing to compare yet.",
                "Tick two or more molecules above. Their values appear as "
                "columns as soon as any calculator has run for them.",
            )
            self._status.setText("")

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
