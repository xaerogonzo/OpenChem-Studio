"""Everything known about one atom, in one place.

A view over `AtomReport`, and only a view. The report is the deliverable
and this is its first consumer; the panel adds navigation, grouping and
export, and no chemistry.

**It never starts a calculation.** Results arrive by event and are
remembered; opening the panel, clicking an atom and switching molecules
are all free. An inspector that launches ORCA when you click an atom is a
calculator launcher, and people stop trusting it -- so the guarantee is
asserted in the tests rather than described here.

The atom TABLE is the primary navigation, not the 3D viewer. Clicking in
3D works and is wired below, but a molecule you have just drawn has no
conformer, which is exactly when somebody wants to look at an atom. The
2D editor cannot report a selection at all -- vendored Ketcher exposes
`load_molblock`, `set_render_option`, `trigger_toolbar_action` and
`get_molblock`, and nothing for selection -- so depending on either viewer
would leave the panel unusable in the common case.
"""

from __future__ import annotations

import csv
import io
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.atom_report import build_atom_report
from openchem.chem.bond_report import bond_label, build_bond_report
from openchem.chem.molecule_report import build_molecule_report
from openchem.chem.engine import ChemistryEngine
from openchem.domain.bond_report import BondReport
from openchem.domain.molecule_report import MoleculeReport
from openchem.domain.atom_report import (
    CATEGORY_LABELS,
    DEFAULT_EXPANDED,
    AtomFact,
    AtomReport,
    FactLink,
)
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import (
    MoleculeSelected,
    PerAtomDataComputed,
    SpectrumComputed,
    StructureChecked,
)
from openchem.ui.widgets.collapsible_section import CollapsibleSection, WrappedLabel

_ATOM_COLUMNS = ("#", "Element", "Facts")
_BOND_COLUMNS = ("#", "Bond", "Facts")

#: What the report is ABOUT. A molecule has exactly one subject, so it
#: has no table -- selecting it hides the list rather than showing a
#: one-row table that cannot be interacted with.
_SUBJECTS = ("Atom", "Bond", "Molecule")

_INTRO = (
    "Everything already known about the selected atom. Nothing here runs a "
    "calculation -- a property you have not computed is absent rather than "
    "wrong, and appears as soon as its calculator has run."
)

_COPY_FORMATS = ("Markdown", "Plain text", "JSON", "CSV")


class AtomInspectorPanel(QWidget):
    """Pick an atom; see every fact any part of the app knows about it."""

    #: Emitted when the user follows a fact's cross-link. MainWindow owns
    #: the destinations -- the panel knows a link exists, not how to open a
    #: dialog, which keeps it testable without a window.
    link_activated = Signal(object)
    #: Emitted when the selected atom changes, so viewers can highlight it.
    atom_selected = Signal(int)

    def __init__(
        self,
        engine: ChemistryEngine,
        event_bus: EventBus,
        atom_fact_service=None,
        structure_check_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._event_bus = event_bus
        self._atom_fact_service = atom_fact_service
        self._structure_check_service = structure_check_service

        self._project: ProjectModel | None = None
        self._molecule_uuid: str | None = None
        self._atom_index: int | None = None
        self._bond_index: int | None = None
        self._subject = "Atom"

        #: molecule uuid -> everything that has arrived by event for it.
        self._context: dict[str, dict] = {}
        #: (molecule uuid, structure version, subject, index) -> report.
        #: One cache for all three kinds: the key already had to carry
        #: the version, and adding the subject to it is cheaper than
        #: three dicts that can fall out of step on invalidation.
        self._cache: dict[tuple[str, int, str, int], object] = {}
        self._sections: dict[str, CollapsibleSection] = {}

        self._atom_table = QTableWidget(0, len(_ATOM_COLUMNS), self)
        self._atom_table.setHorizontalHeaderLabels(_ATOM_COLUMNS)
        header = self._atom_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._atom_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._atom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._atom_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # One line per row and no wrapping: the Interactions panel shipped a
        # table whose wrapped cells made every row taller than the viewport,
        # so it rendered correct data as blank lines.
        self._atom_table.setWordWrap(False)
        self._atom_table.setSortingEnabled(True)
        self._atom_table.verticalHeader().setVisible(False)
        self._atom_table.setMaximumHeight(220)
        self._atom_table.itemSelectionChanged.connect(self._on_row_selected)

        self._subject_combo = QComboBox(self)
        self._subject_combo.addItems(_SUBJECTS)
        self._subject_combo.currentTextChanged.connect(self._on_subject_changed)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Filter facts (element, lewis, ring...)")
        self._search.textChanged.connect(self._render_facts)

        self._copy_format = QComboBox(self)
        self._copy_format.addItems(_COPY_FORMATS)
        self._copy_button = QPushButton("Copy report", self)
        self._copy_button.clicked.connect(self._on_copy_clicked)

        self._title = QLabel("No atom selected", self)
        self._title.setStyleSheet("font-weight: bold;")
        self._status = WrappedLabel("", self)

        self._facts_container = QWidget(self)
        self._facts_layout = QVBoxLayout(self._facts_container)
        self._facts_layout.setContentsMargins(0, 0, 0, 0)
        self._facts_layout.addStretch(1)
        self._facts_area = QScrollArea(self)
        self._facts_area.setWidget(self._facts_container)
        self._facts_area.setWidgetResizable(True)

        intro = WrappedLabel(_INTRO, self)
        intro.setStyleSheet("color: #666666; font-style: italic;")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Show:", self))
        controls.addWidget(self._subject_combo)
        controls.addWidget(self._search, 1)
        controls.addWidget(self._copy_format)
        controls.addWidget(self._copy_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self._atom_table)
        layout.addWidget(self._title)
        layout.addLayout(controls)
        layout.addWidget(self._facts_area, 1)
        layout.addWidget(self._status)

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(PerAtomDataComputed, self._on_per_atom_data)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum)
        event_bus.subscribe(StructureChecked, self._on_structure_checked)

    # --- project and events ------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._rebuild_atom_table()

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._molecule_uuid = event.molecule_uuid
        self._atom_index = None
        self._rebuild_atom_table()

    def _context_for(self, molecule_uuid: str) -> dict:
        return self._context.setdefault(
            molecule_uuid, {"per_atom": {}, "spectra": {}, "issues": ()}
        )

    def _on_per_atom_data(self, event: PerAtomDataComputed) -> None:
        dataset = event.dataset
        self._context_for(dataset.molecule_uuid)["per_atom"][dataset.property_id] = dataset
        self._invalidate(dataset.molecule_uuid)

    def _on_spectrum(self, event: SpectrumComputed) -> None:
        spectrum = event.spectrum
        self._context_for(spectrum.molecule_uuid)["spectra"][spectrum.spectrum_type] = spectrum
        self._invalidate(spectrum.molecule_uuid)

    def _on_structure_checked(self, event: StructureChecked) -> None:
        result = event.result
        self._context_for(result.molecule_uuid)["issues"] = tuple(result.issues)
        self._invalidate(result.molecule_uuid)

    def _invalidate(self, molecule_uuid: str) -> None:
        """Drop cached reports for one molecule and redraw if it is showing.

        New knowledge arriving is exactly as much a reason to rebuild as an
        edit is -- a cached report that predates a calculation would show
        "not computed" for something that now exists.
        """
        self._cache = {key: report for key, report in self._cache.items() if key[0] != molecule_uuid}
        if molecule_uuid == self._molecule_uuid:
            self._render_facts()

    # --- the atom table ----------------------------------------------------

    def _molecule(self):
        if self._project is None or self._molecule_uuid is None:
            return None, None
        model = next((m for m in self._project.molecules if m.uuid == self._molecule_uuid), None)
        if model is None:
            return None, None
        try:
            return model, self._engine.mol_from_model(model)
        except Exception:  # noqa: BLE001 - an unreadable structure is a status, not a crash
            return model, None

    def _rebuild_atom_table(self) -> None:
        model, mol = self._molecule()
        self._atom_table.setSortingEnabled(False)
        self._atom_table.setRowCount(0)
        if mol is None:
            self._title.setText("No atom selected")
            self._render_facts()
            self._atom_table.setSortingEnabled(True)
            return

        if self._subject == "Molecule":
            # One subject, so no list. Hidden rather than shown as a single
            # inert row that invites a click doing nothing.
            self._atom_table.setSortingEnabled(True)
            return

        if self._subject == "Bond":
            self._atom_table.setHorizontalHeaderLabels(_BOND_COLUMNS)
            self._atom_table.setRowCount(mol.GetNumBonds())
            for row in range(mol.GetNumBonds()):
                number = QTableWidgetItem()
                number.setData(Qt.ItemDataRole.DisplayRole, row + 1)
                number.setData(Qt.ItemDataRole.UserRole, row)
                self._atom_table.setItem(row, 0, number)
                self._atom_table.setItem(row, 1, QTableWidgetItem(bond_label(mol, row)))
                count = QTableWidgetItem()
                count.setData(
                    Qt.ItemDataRole.DisplayRole, len(self._report_for(row).facts)
                )
                self._atom_table.setItem(row, 2, count)
            self._atom_table.setSortingEnabled(True)
            return

        self._atom_table.setHorizontalHeaderLabels(_ATOM_COLUMNS)
        self._atom_table.setRowCount(mol.GetNumAtoms())
        for row, atom in enumerate(mol.GetAtoms()):
            index = atom.GetIdx()
            # 1-based for display, 0-based in the data -- the whole app
            # shows atoms 1-based and stores them 0-based.
            number = QTableWidgetItem()
            number.setData(Qt.ItemDataRole.DisplayRole, index + 1)
            number.setData(Qt.ItemDataRole.UserRole, index)
            self._atom_table.setItem(row, 0, number)
            self._atom_table.setItem(row, 1, QTableWidgetItem(atom.GetSymbol()))
            count = QTableWidgetItem()
            count.setData(Qt.ItemDataRole.DisplayRole, len(self._report_for(index).facts))
            self._atom_table.setItem(row, 2, count)
        self._atom_table.setSortingEnabled(True)

    def _report_for(self, index: int):
        """The report for one subject, cached by structure version.

        The version comes from `StructureCheckService`, the counter that
        already exists and already increments on every structure change.
        Reusing it means a report cannot outlive the structure it
        describes, and means there is one such mechanism rather than two.

        One function for all three kinds because the caching, the version
        and the provider list are identical for each -- only the builder
        differs, and branching on that is smaller than three copies of the
        surrounding logic.
        """
        model, mol = self._molecule()
        if mol is None or model is None:
            return AtomReport(molecule_uuid="", atom_index=index)

        version = 0
        if self._structure_check_service is not None:
            version = self._structure_check_service.current_version(model.uuid)

        key = (model.uuid, version, self._subject, index)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        providers = ()
        if self._atom_fact_service is not None:
            providers = self._atom_fact_service.providers()
        context = self._context_for(model.uuid)
        common = {
            "molecule_uuid": model.uuid,
            "structure_version": version,
            "context": context,
            "providers": providers,
        }
        if self._subject == "Bond":
            report = build_bond_report(mol, index, **common)
        elif self._subject == "Molecule":
            report = build_molecule_report(
                mol, **{**common, "context": {**context, "display_name": model.display_name}}
            )
        else:
            report = build_atom_report(mol, index, **common)
        self._cache[key] = report
        return report

    def _on_row_selected(self) -> None:
        items = self._atom_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        cell = self._atom_table.item(row, 0)
        if cell is None:
            return
        index = cell.data(Qt.ItemDataRole.UserRole)
        if self._subject == "Bond":
            self._bond_index = index
        else:
            self._atom_index = index
            # Only atoms drive the viewers' highlight. Emitting a bond row
            # as an atom index would highlight an unrelated atom, which is
            # worse than highlighting nothing.
            self.atom_selected.emit(index)
        self._render_facts()

    def select_atom(self, atom_index: int) -> None:
        """Select an atom from outside -- the 3D viewer's click lands here.

        Finds the ROW holding that atom rather than assuming row == index,
        because the table is sortable and the two stop matching the moment
        somebody sorts by element.
        """
        self._select_row_for(atom_index)

    def select_bond(self, bond_index: int) -> None:
        """Select a bond from outside, by index rather than by row.

        Same reason as `select_atom`, and it is not hypothetical here: a
        test that assumed row 0 held bond 0 got bond 16, because the table
        keeps whatever sort order was last applied.
        """
        self._select_row_for(bond_index)

    def _select_row_for(self, index: int) -> None:
        for row in range(self._atom_table.rowCount()):
            cell = self._atom_table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == index:
                self._atom_table.selectRow(row)
                return

    def _selected_index(self) -> int | None:
        """Which subject is showing, or None when nothing is selected.

        A molecule always has one, so it needs no selection -- returning 0
        here is what lets the render path stay identical for all three.
        """
        if self._subject == "Molecule":
            return 0 if self._molecule()[1] is not None else None
        if self._subject == "Bond":
            return self._bond_index
        return self._atom_index

    def _on_subject_changed(self, subject: str) -> None:
        self._subject = subject
        # A molecule has one subject, so the row list is meaningless for it
        # and is hidden rather than shown holding a single inert row.
        self._atom_table.setVisible(subject != "Molecule")
        self._rebuild_atom_table()
        self._render_facts()

    # --- rendering ---------------------------------------------------------

    def _clear_sections(self) -> None:
        for section in self._sections.values():
            section.setParent(None)
            section.deleteLater()
        self._sections.clear()

    def _render_facts(self) -> None:
        self._clear_sections()
        index = self._selected_index()
        if index is None:
            noun = self._subject.lower()
            self._title.setText(f"No {noun} selected")
            self._status.setText(f"Select a {noun} above to see what is known about it.")
            return

        report = self._report_for(index)
        if isinstance(report, MoleculeReport):
            name = report.display_name or report.formula or "Molecule"
            self._title.setText(f"{name} — {report.formula}")
        elif isinstance(report, BondReport):
            self._title.setText(f"Bond {report.bond_index + 1} — {report.label}")
        else:
            self._title.setText(f"Atom {report.atom_index + 1} — {report.symbol}")

        needle = self._search.text()
        # By identity, NOT by hashing. `AtomFact` is a frozen dataclass and
        # so looks hashable, but a fact carrying a `FactLink` holds a dict
        # of link parameters, and hashing one raises TypeError. Found by
        # opening the panel: every fact with a cross-link is exactly the
        # kind that has one.
        visible = {id(fact) for fact in report.find(needle)}
        shown = 0
        for category, facts in report.by_category().items():
            matching = [fact for fact in facts if id(fact) in visible]
            if not matching:
                continue
            shown += len(matching)
            # Expanded when filtering: a search that hides its own results
            # behind a collapsed header is worse than no search.
            expanded = bool(needle.strip()) or category in DEFAULT_EXPANDED
            section = CollapsibleSection(
                f"{CATEGORY_LABELS[category]} ({len(matching)})", expanded, self._facts_container
            )
            for fact in matching:
                self._add_fact_row(section, fact)
            self._facts_layout.insertWidget(self._facts_layout.count() - 1, section)
            self._sections[category.value] = section

        self._status.setText(self._status_text(report, shown, needle))

    def _add_fact_row(self, section: CollapsibleSection, fact: AtomFact) -> None:
        value = WrappedLabel(fact.display_value, section.content)
        tooltip = "\n".join(
            [f"Source: {fact.source}", f"Basis: {fact.basis.value}", *fact.evidence, *fact.limitations]
        )
        value.setToolTip(tooltip)
        if fact.link is None:
            section.content_layout().addRow(fact.label, value)
            return

        row = QWidget(section.content)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(value, 1)
        open_button = QPushButton(">", row)
        open_button.setToolTip(fact.link.label or "Open the tool this came from")
        open_button.setMaximumWidth(28)
        # The payload rides on the button and a bound method reads it back
        # through sender(). A lambda capturing self is held STRONGLY by
        # PySide6 and would root this panel for the life of the process.
        open_button.setProperty("fact_link", fact.link)
        open_button.clicked.connect(self._on_link_clicked)
        row_layout.addWidget(open_button)
        section.content_layout().addRow(fact.label, row)

    def _on_link_clicked(self) -> None:
        button = self.sender()
        if button is None:
            return
        link = button.property("fact_link")
        if isinstance(link, FactLink):
            self.link_activated.emit(link)

    def _status_text(self, report: AtomReport, shown: int, needle: str) -> str:
        if needle.strip() and shown != len(report.facts):
            return f"{shown} of {len(report.facts)} facts match {needle.strip()!r}."
        parts = [f"{len(report.facts)} facts."]
        parts.extend(report.limitations)
        return " ".join(parts)

    # --- export ------------------------------------------------------------

    def _on_copy_clicked(self) -> None:
        if self._atom_index is None:
            self._status.setText("Select an atom first.")
            return
        report = self._report_for(self._atom_index)
        text = format_report(report, self._copy_format.currentText())
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self._status.setText(
            f"Copied {len(report.facts)} facts as {self._copy_format.currentText()}."
        )


def report_header(report) -> str:
    """How a report names its own subject.

    One function so a title, a Markdown heading and a plain-text banner
    cannot disagree about what the report is about.
    """
    if isinstance(report, MoleculeReport):
        name = report.display_name or report.formula or "Molecule"
        return f"{name} ({report.formula})" if report.formula else name
    if isinstance(report, BondReport):
        return f"Bond {report.bond_index + 1} ({report.label})"
    return f"Atom {report.atom_index + 1} ({report.symbol})"


def _subject_fields(report) -> dict:
    """The identity keys for JSON, which differ per subject.

    Kept separate from the fact serialisation because the facts are the
    same shape for all three and only the subject is not -- "anything else
    that grows a report" was the stated reason these formats were a module
    function, and this is that."""
    if isinstance(report, MoleculeReport):
        return {
            "subject": "molecule",
            "display_name": report.display_name,
            "formula": report.formula,
            "atom_count": report.atom_count,
            "bond_count": report.bond_count,
        }
    if isinstance(report, BondReport):
        return {
            "subject": "bond",
            "bond_index": report.bond_index,
            "label": report.label,
            "begin_atom_index": report.begin_atom_index,
            "end_atom_index": report.end_atom_index,
        }
    return {"subject": "atom", "atom_index": report.atom_index, "symbol": report.symbol}


def format_report(report, fmt: str) -> str:
    """One report as text, whatever its subject.

    Four formats because the destinations differ: Markdown for an issue or
    a notebook, plain text for an email, JSON for a script or an LLM, CSV
    for a spreadsheet. A module-level function rather than a method so the
    formats are testable without constructing a panel -- and so anything
    else that grows a report can reuse them.
    """
    header = report_header(report)
    grouped = report.by_category()

    if fmt == "JSON":
        return json.dumps(
            {
                "molecule_uuid": report.molecule_uuid,
                **_subject_fields(report),
                "structure_version": report.structure_version,
                "facts": [
                    {
                        "category": fact.category.value,
                        "label": fact.label,
                        "display_value": fact.display_value,
                        "source": fact.source,
                        "basis": fact.basis.value,
                        "units": fact.units,
                        "evidence": list(fact.evidence),
                    }
                    for fact in report.facts
                ],
                "assumptions": list(report.assumptions),
                "limitations": list(report.limitations),
            },
            indent=1,
        )

    if fmt == "CSV":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["category", "label", "value", "units", "source", "basis"])
        for fact in report.facts:
            writer.writerow([
                fact.category.value, fact.label, fact.display_value,
                fact.units, fact.source, fact.basis.value,
            ])
        return buffer.getvalue()

    if fmt == "Markdown":
        lines = [f"## {header}", ""]
        for category, facts in grouped.items():
            lines.append(f"### {CATEGORY_LABELS[category]}")
            lines.append("")
            lines.append("| Fact | Value | Source | Basis |")
            lines.append("| --- | --- | --- | --- |")
            for fact in facts:
                lines.append(
                    f"| {fact.label} | {fact.display_value} | {fact.source} | {fact.basis.value} |"
                )
            lines.append("")
        for text in report.limitations:
            lines.append(f"> {text}")
        return "\n".join(lines).rstrip() + "\n"

    lines = [header, "=" * len(header), ""]
    for category, facts in grouped.items():
        lines.append(f"{CATEGORY_LABELS[category]}:")
        for fact in facts:
            lines.append(f"  {fact.label}: {fact.display_value}  [{fact.basis.value}]")
        lines.append("")
    for text in report.limitations:
        lines.append(f"Limitation: {text}")
    return "\n".join(lines).rstrip() + "\n"
