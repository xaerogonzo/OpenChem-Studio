"""A window around the results reader.

**THE READER MOVED OUT AND THIS IS WHAT WAS LEFT.** Everything this module
used to be is now `ui/widgets/results_view.ResultsView`, because a reader
that FOLLOWS the selection cannot be a dialog: a dialog is something you
open, read and close, and a dock is never closed. What stays here is the
window -- a title, a size, and the modeless lifetime -- which is the part a
dock does not want.

**IT DELEGATES AND ALIASES RATHER THAN REIMPLEMENTING.** Every public
method forwards to the view, and the widgets its callers reach for are the
view's own objects under the same names. So the extraction is
behaviour-neutral BY CONSTRUCTION rather than by re-testing, which is the
move `ui/widgets/zoomable_svg_view.py` already made out of the Lewis
dialog -- 43 tests unmoved there, 31 here.

The constants are re-exported for the same reason: `STALE_MARK`,
`ALL_RESULTS`, `GROUP_HEADING` and `EMPTY_MESSAGES` are imported from this
module by tests and by the drive harness, and an extraction that quietly
moved them would be an extraction with a diff nobody could read.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from openchem.domain.reader_state import ReaderView
from openchem.ui.widgets.results_view import (
    ALL_RESULTS,
    EMPTY_MESSAGES,
    GROUP_HEADING,
    STALE_MARK,
    ResultsView,
)

__all__ = [
    "ALL_RESULTS",
    "EMPTY_MESSAGES",
    "GROUP_HEADING",
    "STALE_MARK",
    "MergedResultsDialog",
]


class MergedResultsDialog(QDialog):
    """One molecule's results, in a window of their own.

    A shell: the reading happens in the `ResultsView` inside it.
    """

    #: Forwarded from the view. Routing lives in the window that owns the
    #: dialogs, so this stays constructible in a test with no application
    #: around it -- the same split `AtomInspectorPanel` makes.
    link_activated = Signal(object)

    def __init__(
        self,
        molecule_uuid: str,
        molecule_name: str = "",
        parent: QWidget | None = None,
        display_order_of=None,
    ) -> None:
        super().__init__(parent)
        self._results = ResultsView(molecule_uuid, self, display_order_of=display_order_of)
        self._results.link_activated.connect(self.link_activated)

        # **ALIASES, NOT COPIES.** These are the view's own widgets under the
        # names callers already use -- the drive harness reads `_focus_box`,
        # and the tests reach for `_view`, `_empty`, `_selector_search`,
        # `_open_button` and `_visuals`. Rebinding them is what would make
        # this a rewrite; pointing at the same objects is what makes it a
        # move, and it is why none of those tests had to be touched.
        self._view = self._results._view
        self._focus_box = self._results._focus_box
        self._selector_search = self._results._selector_search
        self._open_button = self._results._open_button
        self._visuals = self._results._visuals
        self._visuals_layout = self._results._visuals_layout
        self._empty = self._results._empty

        self.setWindowTitle(f"Results - {molecule_name}" if molecule_name else "Results")
        self.resize(560, 680)

        layout = QVBoxLayout(self)
        # NO MARGINS: the view drew straight into the dialog before this
        # split, so adding the layout's default padding here would move
        # every control a few pixels and make a pure extraction visible.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._results)

    # --- everything below forwards -------------------------------------------

    def results_view(self) -> ResultsView:
        """The reader inside this window."""
        return self._results

    def set_structure_resolver(self, resolver) -> None:
        self._results.set_structure_resolver(resolver)

    def molecule_uuid(self) -> str:
        return self._results.molecule_uuid()

    def set_reader_memory(self, memory) -> None:
        self._results.set_reader_memory(memory)

    def view(self) -> ReaderView:
        return self._results.view()

    def apply_view(self, view: ReaderView) -> None:
        self._results.apply_view(view)

    def set_reports(self, reports, structure_version: int = 0) -> None:
        self._results.set_reports(reports, structure_version)

    def merged(self):
        return self._results.merged()

    def focus(self) -> str:
        return self._results.focus()

    def set_focus(self, report_id: str) -> None:
        self._results.set_focus(report_id)
