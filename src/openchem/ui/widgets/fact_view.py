"""One renderer for every report in the application.

Lifted out of `AtomInspectorPanel`, which was its only consumer and had
grown the whole thing inline: sections, search, per-fact basis, tooltips,
cross-links and copy.

Its consumers now: the Atom Inspector (atoms, bonds and molecules), and
the Property panel's "Details..." for every calculator that returns a
`ReportResult` -- sixteen of them, including geometry, regulatory,
topology and Lewis. Without this, each would have arrived with its own
bespoke rendering.

**IT KNOWS NO CHEMISTRY.** It takes a `StructureReport` -- anything with
`facts`, `by_category()` and `find()` -- and renders it. That is the whole
contract. The payoff is that hyperlinks, icons, copy formatting, units,
filtering and the detached window are each ONE widget to change rather
than eight panels, which is the argument for doing this before the
fifteen calculator migrations rather than after.

Two things it deliberately does not do. It never computes: a report is
already the answer to "what do you know", and a view that starts a
calculation is a calculator launcher people stop trusting. And it never
edits: it is a read-only lens, and mutation has undo implications that
belong in their own change.

`AtomInspectorPanel` is its first consumer and its 45 tests pass against
it unchanged, which is the proof the extraction is honest.

**Adopting it was blocked for one commit by a heap corruption**, and the
cause turned out to have nothing to do with this widget: the teardown
`gc.collect()` was destroying MainWindows, which corrupts the heap, and
adding any widget merely shifted the layout enough to change whether the
corruption landed on something fatal. `tests/conftest.py` retains
MainWindows now, and CLAUDE.md has the measurements.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.report import (
    CATEGORY_LABELS,
    DEFAULT_EXPANDED,
    Detail,
    Fact,
    FactLink,
)
from openchem.ui.widgets.collapsible_section import (
    CollapsibleSection,
    ExplicitHeightLabel,
    WrappedLabel,
)
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

COPY_FORMATS = ("Markdown", "Plain text", "JSON", "CSV")

#: Carried on a row so the context menu and the hover handler can find the
#: fact again. Never a lambda closing over `self` -- PySide6 holds a
#: connected plain callable strongly, which rooted a whole window here once.
_FACT_PROPERTY = "openchem_fact"
_LINK_PROPERTY = "fact_link"


class _FactRow(ExplicitHeightLabel):
    """A fact's value, which reports when the pointer is over it.

    A `QLabel` subclass rather than an event filter on each row: the
    filter version needs a dict from widget to fact, and a dict KEYED BY a
    QWidget hashes on the C++ pointer that Qt frees with the parent. That
    exact shape cost this project a heap corruption, so the fact rides on
    the widget as a Qt property instead.
    """

    hovered = Signal(object)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        self.hovered.emit(self.property(_FACT_PROPERTY))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        self.hovered.emit(None)
        super().leaveEvent(event)


#: FOUR CONCEPTS SHARED BY EVERY SURFACE THAT EMBEDS A `FactView` -- the
#: Atom Inspector's atom, bond and molecule reports, the Lewis view and
#: the regulatory screen. One contract each, several renderings, exactly
#: as `CollapsibleSection` does with its section headers: the meaning is
#: a property of this widget rather than of whichever panel built it.
_HELP: dict[str, HelpTooltip] = {
    "search": HelpTooltip(
        text=(
            "Show only facts whose text matches what you type.\n\n"
            "It searches the whole fact -- label, value and evidence -- "
            "not just the name, so \"ring\" finds a fact that merely "
            "mentions one. Filtering hides rows; it computes nothing and "
            "removes nothing."
        ),
        tier=2,
        help_id="facts.search",
        topic="facts",
    ),
    "detail": HelpTooltip(
        text=(
            "How much specialist material to show.\n\n"
            "\"Standard\" hides facts aimed at a specialist reader -- "
            "Fukui indices, the dual descriptor, local softness. They are "
            "real and already computed; they are just not what most "
            "people are looking at. \"Everything\" shows them.\n\n"
            "This is ORTHOGONAL to the category sections above it: depth "
            "says how specialist, a section says what kind."
        ),
        tier=2,
        help_id="facts.detail",
        topic="facts",
    ),
    "copy_format": HelpTooltip(
        text=(
            "What shape the copied report takes.\n\n"
            "Markdown and Plain text are for reading and pasting into a "
            "document; JSON and CSV are for a script. JSON is the only "
            "one that keeps each fact's basis and evidence as separate "
            "fields rather than as prose."
        ),
        tier=2,
        help_id="facts.copy_format",
        topic="facts",
    ),
    "copy": HelpTooltip(
        text=(
            "Copy the facts as they are currently shown.\n\n"
            "It follows the view: anything hidden by the filter or by "
            "\"Standard\" is not copied. Status glyphs are stripped, so "
            "what lands on the clipboard is plain ASCII that survives a "
            "console or a paper."
        ),
        tier=2,
        help_id="facts.copy_report",
        topic="facts",
    ),
}


class FactView(QWidget):
    """Renders one report: grouped, searchable, filterable, copyable."""

    #: A fact's cross-link was followed. Carries the `FactLink`; the host
    #: owns the destinations, so this widget knows a link exists without
    #: knowing how to open a dialog.
    link_activated = Signal(object)
    #: The atoms the pointer is currently over, or `()` on the way out.
    #: The host paints them -- and MUST bounds-check first, since a viewer
    #: carries explicit hydrogens a report usually does not.
    highlight_requested = Signal(tuple)
    #: "Compare with..." was chosen on this report.
    compare_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None, show_controls: bool = True) -> None:
        super().__init__(parent)
        self._report = None
        self._sections: dict[str, CollapsibleSection] = {}
        #: **WITHOUT THE CONTROLS, NOTHING MAY HIDE BEHIND THEM.** The depth
        #: filter and the collapsed headings are both things a reader
        #: undoes with a control; hide the controls and each becomes a dead
        #: end. Found by rendering the solubility curve's stats block and
        #: looking at it: four of its seven facts sat behind a collapsed
        #: "Structure (4)" heading, and the status line advised choosing
        #: "Everything" from a combo box that was not on screen.
        self._compact = not show_controls

        self._title = QLabel("", self)
        self._title.setStyleSheet("font-weight: bold;")

        #: The Summary. Pinned above the sections and never collapsible --
        #: people want formula, weight and a few descriptors immediately,
        #: not after opening a category. Everything else stays behind a
        #: heading, which is the only thing that makes a hundred facts
        #: readable.
        self._summary = WrappedLabel("", self)
        self._summary.setStyleSheet("padding: 2px 0;")

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Filter facts (element, lewis, ring...)")
        self._search.textChanged.connect(self._render)
        apply_help_tooltip(self._search, _HELP['search'])

        # Category and depth are ORTHOGONAL, so they are two controls
        # rather than one five-way list -- see `Detail` for why collapsing
        # them would have baked a confusion into the model.
        self._detail = QComboBox(self)
        self._detail.addItem("Standard", Detail.STANDARD.value)
        self._detail.addItem("Everything", "")
        apply_help_tooltip(self._detail, _HELP['detail'])
        self._detail.currentIndexChanged.connect(self._render)

        self._copy_format = QComboBox(self)
        self._copy_format.addItems(COPY_FORMATS)
        apply_help_tooltip(self._copy_format, _HELP['copy_format'])
        self._copy_button = QPushButton("Copy report", self)
        self._copy_button.clicked.connect(self._on_copy_clicked)
        apply_help_tooltip(self._copy_button, _HELP['copy'])

        self._status = WrappedLabel("", self)

        self._container = QWidget(self)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.addStretch(1)
        self._area = QScrollArea(self)
        self._area.setWidget(self._container)
        self._area.setWidgetResizable(True)

        self._controls = QWidget(self)
        controls = QHBoxLayout(self._controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self._search, 1)
        controls.addWidget(self._detail)
        controls.addWidget(self._copy_format)
        controls.addWidget(self._copy_button)
        self._controls.setVisible(show_controls)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        layout.addWidget(self._summary)
        layout.addWidget(self._controls)
        layout.addWidget(self._area, 1)
        layout.addWidget(self._status)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    # --- what it is showing --------------------------------------------------

    def set_report(self, report, title: str = "", summary: str = "") -> None:
        self._report = report
        self._title.setText(title)
        self._summary.setText(summary)
        self._summary.setVisible(bool(summary))
        self._render()

    def report(self):
        return self._report

    def clear(self, title: str = "", status: str = "") -> None:
        self._report = None
        self._title.setText(title)
        self._summary.setVisible(False)
        self._clear_sections()
        self._status.setText(status)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def status_text(self) -> str:
        return self._status.text()

    def title_text(self) -> str:
        return self._title.text()

    def search_box(self) -> QLineEdit:
        """Exposed so a window-level shortcut can focus it."""
        return self._search

    def visible_fact_labels(self) -> list[str]:
        """What is on screen, read back off the rows.

        Derived from the widgets rather than recomputed, so a test cannot
        pass against a filter that never reached the display.
        """
        labels: list[str] = []
        for section in self._sections.values():
            for row in section.content.findChildren(_FactRow):
                fact = row.property(_FACT_PROPERTY)
                if isinstance(fact, Fact):
                    labels.append(fact.label)
        return labels

    # --- rendering -----------------------------------------------------------

    def _clear_sections(self) -> None:
        for section in self._sections.values():
            section.setParent(None)
            section.deleteLater()
        self._sections.clear()

    def _showing_everything(self) -> bool:
        return self._compact or not self._detail.currentData()

    def _render(self) -> None:
        self._clear_sections()
        report = self._report
        if report is None:
            return

        needle = self._search.text()
        # By identity, NOT by hashing. `Fact` is a frozen dataclass and so
        # looks hashable, but one carrying a `FactLink` holds a dict of
        # link parameters, and hashing that raises TypeError. Found by
        # opening the panel: every fact with a cross-link has one.
        matched = {id(fact) for fact in report.find(needle)}
        everything = self._showing_everything()
        shown = 0
        hidden_by_depth = 0

        for category, facts in report.by_category().items():
            visible = []
            for fact in facts:
                if id(fact) not in matched:
                    continue
                if not everything and getattr(fact, "detail", Detail.STANDARD) is Detail.ADVANCED:
                    hidden_by_depth += 1
                    continue
                visible.append(fact)
            if not visible:
                continue
            shown += len(visible)
            # Expanded while filtering: a search that hides its own results
            # behind a collapsed header is worse than no search.
            expanded = self._compact or bool(needle.strip()) or category in DEFAULT_EXPANDED
            section = CollapsibleSection(
                f"{CATEGORY_LABELS[category]} ({len(visible)})", expanded, self._container
            )
            for fact in visible:
                self._add_row(section, fact)
            self._container_layout.insertWidget(self._container_layout.count() - 1, section)
            self._sections[category.value] = section

        self._status.setText(self._status_text(report, shown, needle, hidden_by_depth))

    def _add_row(self, section: CollapsibleSection, fact: Fact) -> None:
        value = _FactRow(fact.display_value, section.content)
        value.setProperty(_FACT_PROPERTY, fact)
        value.setToolTip(
            "\n".join(
                [
                    f"Source: {fact.source}",
                    f"Basis: {fact.basis.value}",
                    *fact.evidence,
                    *fact.limitations,
                ]
            )
        )
        value.hovered.connect(self._on_row_hovered)
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
        open_button.setProperty(_LINK_PROPERTY, fact.link)
        open_button.clicked.connect(self._on_link_clicked)
        row_layout.addWidget(open_button)
        section.content_layout().addRow(fact.label, row)

    def _status_text(self, report, shown: int, needle: str, hidden_by_depth: int) -> str:
        total = len(report.facts)
        if needle.strip() and shown != total:
            return f"{shown} of {total} facts match {needle.strip()!r}."
        parts = [f"{total} facts."]
        if hidden_by_depth:
            # Says so rather than silently omitting them. A filter that
            # hides without admitting it reads as missing data.
            parts.append(f"{hidden_by_depth} advanced hidden -- choose Everything to show them.")
        parts.extend(report.limitations)
        return " ".join(parts)

    # --- interaction ---------------------------------------------------------

    def _on_row_hovered(self, fact) -> None:
        highlight = getattr(fact, "highlight", ()) if fact is not None else ()
        self.highlight_requested.emit(tuple(highlight))

    def _on_link_clicked(self) -> None:
        button = self.sender()
        if button is None:
            return
        link = button.property(_LINK_PROPERTY)
        if isinstance(link, FactLink):
            self.link_activated.emit(link)

    def _on_context_menu(self, position) -> None:
        """The same three actions on every report in the application.

        Learned once, available everywhere -- which is most of the value of
        having one renderer rather than eight.
        """
        if self._report is None:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Copy report")
        export_action = menu.addAction("Export report...")
        compare_action = menu.addAction("Compare with...")
        menu.addSeparator()
        window_action = menu.addAction("Open in window")
        chosen = menu.exec(self.mapToGlobal(position))
        if chosen is copy_action:
            self._on_copy_clicked()
        elif chosen is export_action:
            self._on_export_clicked()
        elif chosen is compare_action:
            self.compare_requested.emit(self._report)
        elif chosen is window_action:
            self.open_in_window()

    def open_in_window(self) -> QDialog | None:
        """The same report, in its own window.

        Marvin opens each result in a window and it is genuinely useful --
        two reports side by side, or one kept open while you work. The
        detached copy is a second `FactView` on the same report rather
        than a re-implementation, so it cannot drift.
        """
        if self._report is None:
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle(self._title.text() or "Report")
        dialog.resize(520, 640)
        view = FactView(dialog)
        view.set_report(self._report, self._title.text(), self._summary.text())
        view.link_activated.connect(self.link_activated)
        view.compare_requested.connect(self.compare_requested)
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        dialog.show()
        return dialog

    # --- export --------------------------------------------------------------

    def _on_copy_clicked(self, _checked: bool = False) -> None:
        if self._report is None:
            self._status.setText("Nothing selected.")
            return
        from openchem.ui.report_format import format_report

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(format_report(self._report, self._copy_format.currentText()))
        self._status.setText(
            f"Copied {len(self._report.facts)} facts as {self._copy_format.currentText()}."
        )

    def _on_export_clicked(self, _checked: bool = False) -> None:
        from PySide6.QtWidgets import QFileDialog

        from openchem.ui.report_format import format_report

        if self._report is None:
            return
        suffix = {"Markdown": "md", "Plain text": "txt", "JSON": "json", "CSV": "csv"}
        chosen = self._copy_format.currentText()
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export report", f"report.{suffix.get(chosen, 'txt')}"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(format_report(self._report, chosen))
        self._status.setText(f"Exported as {chosen}.")
