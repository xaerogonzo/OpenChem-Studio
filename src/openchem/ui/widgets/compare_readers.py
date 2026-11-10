"""One Results reader per compared molecule, kept looking at the same thing.

**NOT A SECOND RESULTS DISPLAY.** Every pane is the application's own `ResultsView`, so a value reads
here exactly as it does in the Results panel (facts, evidence, limits, charts). What this adds is the
coordination: choose a report, type in the fact filter, or double-click a value in Compare, and every
linked pane goes to the same place. For two molecules the panes sit side by side; for more they are
tabs, because five readers abreast are each too narrow to read (either can be chosen).

**FED, NEVER SELECTED.** Each pane is given its entries by `feed(uuid)` (`MainWindow.reader_entries_for`:
the molecule's stored results, built without selecting it and without publishing anything). A pane is
reused for as long as its molecule stays in the group, never re-pointed at another molecule, so the
reader's own guarantee that it never shows one molecule's results under another's name holds.

**WHAT FOLLOWS AND WHAT DOES NOT.** The report shown, the fact filter, the "show advanced" choice and
the picker's search are shared (`ReaderView`); scroll position, splitter sizes and the window's place
are each pane's own. A pane whose molecule has no such report says so in words above it instead of
quietly showing "All results": a missing result is the interesting half of a comparison.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.reader_state import ReaderView
from openchem.ui import theme
from openchem.ui.widgets.collapsible_section import WrappedLabel
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.results_view import ResultsView

#: TIER 2: what linking does, and that a double-click in Compare goes to every pane regardless.
_LINK_HELP = HelpTooltip(
    text=(
        "On (the default): choosing a report, typing in the fact filter or changing what is shown in "
        "one pane does the same in every pane, so the molecules stay on the same value.\n\n"
        "Off: each pane moves on its own. Double-clicking a value in Compare still takes every pane "
        "to it, because that is a request for the whole comparison."
    ),
    tier=2,
    help_id="compare.link_readers",
    topic="compare",
)

#: TIER 1: the layout button, and why two molecules start side by side and more start as tabs.
_LAYOUT_HELP = HelpTooltip(
    text=(
        "Switch between the panes side by side and the panes as tabs. Two molecules start side by "
        "side; more start as tabs, since five readers across are each too narrow to read."
    ),
    tier=1,
    help_id="compare.reader_layout",
    topic="compare",
)

#: How many molecules still start side by side.
SIDE_BY_SIDE_UP_TO = 2

#: Wait this long after a result arrives before re-reading, so a burst is one re-read.
_REFRESH_MS = 150


class _Pane(QWidget):
    """One molecule's reader, with its name and a line saying what it is (not) showing."""

    def __init__(self, uuid: str, name: str, display_order_of, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.uuid = uuid
        self._title = QLabel(name, self)
        theme.style(self._title, "font-weight: bold;")
        self._note = WrappedLabel("", self)
        self._note.setVisible(False)
        self.reader = ResultsView(molecule_uuid=uuid, display_order_of=display_order_of)
        self.reader.setParent(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        layout.addWidget(self._note)
        layout.addWidget(self.reader, 1)

    def set_name(self, name: str) -> None:
        self._title.setText(name)

    def say(self, text: str) -> None:
        self._note.setText(text)
        self._note.setVisible(bool(text))


class CompareReaders(QWidget):
    """See the module docstring."""

    #: The window was closed.
    closed = Signal()
    #: A pane's Open button or fact link. Forwarded so CompareReaders never
    #: opens another molecule's structures itself.
    link_activated = Signal(object)

    def __init__(
        self,
        feed: Callable[[str], tuple[list, int]],
        names: Callable[[str], str],
        display_order_of=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Compare - Results")
        self.resize(980, 640)
        self._feed = feed
        self._names = names
        self._display_order_of = display_order_of
        self._panes: dict[str, _Pane] = {}
        self._order: list[str] = []
        #: Set while WE move the panes, so their own change signals are not read as somebody's move.
        self._applying = False
        self._shared = ReaderView()
        #: The last group command (report id, fact label), so a re-read keeps it.
        self._target: tuple[str, str] | None = None
        self._layout_chosen = False
        self._side_by_side = True

        self._link = QCheckBox("Link readers", self)
        self._link.setChecked(True)
        apply_help_tooltip(self._link, _LINK_HELP)
        self._layout_button = QPushButton("", self)
        apply_help_tooltip(self._layout_button, _LAYOUT_HELP)
        self._layout_button.clicked.connect(self._on_layout_clicked)
        self._status = WrappedLabel("", self)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._tabs = QTabWidget(self)
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._splitter)
        self._stack.addWidget(self._tabs)

        header = QHBoxLayout()
        header.addWidget(self._link)
        header.addStretch(1)
        header.addWidget(self._layout_button)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self._status)
        layout.addWidget(self._stack, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._update_layout_button()

    # --- membership ---------------------------------------------------------------

    def uuids(self) -> list[str]:
        return list(self._order)

    def pane(self, uuid: str) -> _Pane | None:
        return self._panes.get(uuid)

    def set_molecules(self, uuids: list[str]) -> None:
        """Make the group exactly these molecules, keeping the panes that stay.

        A pane whose molecule leaves is disposed of; one that stays keeps its place in the reader
        (it is not rebuilt), and a new one is fed and brought to where the group is.
        """
        wanted = [u for u in dict.fromkeys(uuids) if u]
        for uuid in [u for u in self._order if u not in wanted]:
            self._drop(uuid)
        for uuid in wanted:
            if uuid not in self._panes:
                self._add(uuid)
        self._order = wanted
        if not self._layout_chosen:
            self._side_by_side = len(wanted) <= SIDE_BY_SIDE_UP_TO
        self._arrange()
        self.refresh()

    def _add(self, uuid: str) -> None:
        pane = _Pane(uuid, self._names(uuid), self._display_order_of, self)
        pane.reader.view_changed.connect(self._on_reader_changed)
        pane.reader.link_activated.connect(self.link_activated)
        self._panes[uuid] = pane

    def _drop(self, uuid: str) -> None:
        pane = self._panes.pop(uuid, None)
        if pane is None:
            return
        try:
            pane.reader.view_changed.disconnect(self._on_reader_changed)
        except (RuntimeError, TypeError):
            pass
        try:
            pane.reader.link_activated.disconnect(self.link_activated)
        except (RuntimeError, TypeError):
            pass
        pane.setParent(None)
        pane.deleteLater()

    def _arrange(self) -> None:
        """Put the panes in the splitter or the tabs, in group order."""
        for pane in self._panes.values():
            pane.setParent(None)
        self._tabs.clear()
        for uuid in self._order:
            pane = self._panes[uuid]
            if self._side_by_side:
                self._splitter.addWidget(pane)
            else:
                self._tabs.addTab(pane, self._names(uuid))
            pane.show()
        self._stack.setCurrentWidget(self._splitter if self._side_by_side else self._tabs)
        self._update_layout_button()

    def _on_layout_clicked(self, _checked: bool = False) -> None:
        self._layout_chosen = True
        self._side_by_side = not self._side_by_side
        self._arrange()

    def _update_layout_button(self) -> None:
        self._layout_button.setText("Show as tabs" if self._side_by_side else "Show side by side")

    # --- feeding -------------------------------------------------------------------

    def request_refresh(self) -> None:
        """Re-read soon (a result arrived); a burst of them is one re-read."""
        self._refresh_timer.start()

    def refresh(self) -> None:
        """Feed every pane from the store again, then put the group back where it was."""
        for uuid in self._order:
            pane = self._panes[uuid]
            pane.set_name(self._names(uuid))
            entries, version = self._feed(uuid)
            pane.reader.set_reports(entries, version)
        self._reapply()

    def _reapply(self) -> None:
        """The group's position onto every pane, and each pane's note about what it holds."""
        self._applying = True
        try:
            if self._target is not None:
                for pane in self._panes.values():
                    pane.reader.reveal_fact(*self._target)
            else:
                for pane in self._panes.values():
                    pane.reader.apply_view(self._shared)
        finally:
            self._applying = False
        self._notes()

    def _notes(self) -> None:
        """Say, per pane, when the value being looked at is not there for that molecule."""
        report_id = self._target[0] if self._target is not None else self._shared.report_id
        label = self._target[1] if self._target is not None else ""
        shown_in = []
        for uuid in self._order:
            pane = self._panes[uuid]
            if not report_id:
                pane.say("")
                continue
            reader = pane.reader
            if reader.merged().report_for(report_id) is None:
                pane.say(
                    f"Nothing stored for this molecule under this result, so there is nothing to "
                    f"show. It has not been calculated for {self._names(uuid)}, or it no longer "
                    "matches the structure."
                )
            elif label and label not in reader._view.visible_fact_labels():
                pane.say(f"The result is here, but it has no value called {label}.")
            else:
                pane.say("")
                shown_in.append(uuid)
        if self._target is not None:
            self._status.setText(
                f"{self._target[1]}: shown for {len(shown_in)} of {len(self._order)} molecules."
            )

    # --- coordination ----------------------------------------------------------------

    def show_target(self, report_id: str, label: str) -> None:
        """Take EVERY pane to one value. A group command: it ignores the Link checkbox."""
        self._target = (report_id, label)
        self._reapply()
        # The group now sits wherever the first pane that has it ended up.
        for uuid in self._order:
            reader = self._panes[uuid].reader
            if reader.merged().report_for(report_id) is not None:
                self._shared = reader.view()
                break

    def _on_reader_changed(self, view: ReaderView) -> None:
        """One pane was moved by somebody: bring the others along, if linked."""
        if self._applying:
            return
        self._target = None
        self._status.setText("")
        if not self._link.isChecked():
            self._notes()
            return
        self._shared = view
        self._applying = True
        try:
            for pane in self._panes.values():
                if pane.reader.view() != view:
                    pane.reader.apply_view(view)
        finally:
            self._applying = False
        self._notes()

    def is_linked(self) -> bool:
        return self._link.isChecked()

    def set_linked(self, linked: bool) -> None:
        self._link.setChecked(linked)

    def is_side_by_side(self) -> bool:
        return self._side_by_side

    # --- lifecycle ----------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._refresh_timer.stop()
        for uuid in list(self._order):
            self._drop(uuid)
        self._order = []
        self.closed.emit()
        super().closeEvent(event)
