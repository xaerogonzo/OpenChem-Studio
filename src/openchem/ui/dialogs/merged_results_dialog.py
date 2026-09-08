"""Everything computed for one molecule, in one window.

**THE COMPLAINT THIS EXISTS FOR.** "Details..." opened one calculator's
report, so running Substance & Bonding and then Lewis Sites replaced the
first window with the second -- and `FactView`'s search box, depth filter
and copy, all built for a hundred facts, were being handed four. The
filter was useless because there was nothing to filter.

**IT IS THE SAME SURFACE, FOCUSED, NOT A SECOND ONE.** Every existing
"Details..." button still opens this window; it arrives focused on the
report whose button was pressed, with that report's facts in view and its
chart drawn. A second parallel Details implementation is exactly what this
change exists to end.

**MODELESS, AND LIVE.** The old dialog used `exec()`, which blocks the
panel -- so with a modal window you could never run the second calculator
whose results this exists to accumulate. One window per molecule, keyed by
UUID rather than by object identity (a rebuilt model must not open a
second window for the same molecule), refreshed as results arrive.

**STALE RESULTS ARE MARKED, NEVER DISCARDED.** A report describing an
older revision of the structure is still a record of what was computed.
Silently serving one and silently blanking one are the two ways this goes
wrong, and they look identical from outside.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.merged_results import MergedResults, merge_reports
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

logger = logging.getLogger("openchem.ui")

#: What the focus control means. ONE contract, however many calculators
#: populate the list -- the same rule `CollapsibleSection`'s toggle
#: follows, and the reason a per-calculator contract would be sixty
#: renderings of one concept.
_FOCUS_HELP = HelpTooltip(
    text=(
        "Show one calculator's results, or all of them together.\n\n"
        "Everything computed for this molecule is in this window; this "
        "narrows it to one producer. It hides rows -- it computes "
        "nothing, discards nothing, and does not re-run anything.\n\n"
        "A result marked stale was computed for an earlier version of "
        "this structure. It is kept and labelled rather than removed, "
        "because a stale answer and a missing one are different things."
    ),
    tier=2,
    help_id="results.focus_calculator",
    topic="facts",
)

#: Shown for every result the structure has moved on from.
STALE_MARK = " (stale)"

#: The focus entry that narrows to nothing -- i.e. shows every calculator.
#: A real entry rather than an empty string, so the control always names
#: what it is currently doing.
ALL_RESULTS = "All results"


class MergedResultsDialog(QDialog):
    """One molecule's accumulated results, focusable by calculator."""

    def __init__(
        self,
        molecule_uuid: str,
        molecule_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._molecule_uuid = molecule_uuid
        self._merged = MergedResults(reports=(), facts=())
        self._focus = ""

        self.setWindowTitle(f"Results - {molecule_name}" if molecule_name else "Results")
        self.resize(560, 680)

        self._focus_box = QComboBox(self)
        self._focus_box.currentIndexChanged.connect(self._on_focus_changed)
        apply_help_tooltip(self._focus_box, _FOCUS_HELP)

        focus_row = QWidget(self)
        row = QHBoxLayout(focus_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Showing:", focus_row))
        row.addWidget(self._focus_box, 1)

        self._view = FactView(self)
        self._empty = QLabel(
            "Nothing has been computed for this molecule yet.\n\n"
            "Run a calculator and its results appear here.",
            self,
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(focus_row)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._empty, 1)

    # --- what it is showing --------------------------------------------------

    def molecule_uuid(self) -> str:
        return self._molecule_uuid

    def set_reports(self, reports, structure_version: int = 0) -> None:
        """Replace what this window shows.

        Called both when the window opens and whenever another result
        arrives for this molecule -- the window is live, so the second
        calculator's facts land in the open window rather than needing it
        reopened.
        """
        self._merged = merge_reports(reports, structure_version=structure_version)
        self._rebuild_focus_box()
        self._render()

    def merged(self) -> MergedResults:
        return self._merged

    def focus(self) -> str:
        """The `report_id` currently focused, or "" for all of them."""
        return self._focus

    def set_focus(self, report_id: str) -> None:
        """Show one report's facts and its chart.

        **BY `report_id`, NEVER BY POSITION.** Once several calculators can
        contribute a chart or a 3D annotation, "the first one" stops being
        an answer to anything.
        """
        self._focus = report_id if self._merged.report_for(report_id) else ""
        self._sync_focus_box()
        self._render()

    # --- rendering -----------------------------------------------------------

    def _rebuild_focus_box(self) -> None:
        blocked = self._focus_box.blockSignals(True)
        self._focus_box.clear()
        self._focus_box.addItem(ALL_RESULTS, "")
        for report in self._merged.reports:
            label = self._merged.name_for(report.report_id)
            if self._merged.is_stale(report):
                label += STALE_MARK
            self._focus_box.addItem(label, report.report_id)
        self._focus_box.blockSignals(blocked)
        self._sync_focus_box()

    def _sync_focus_box(self) -> None:
        index = self._focus_box.findData(self._focus)
        if index < 0:
            index = 0
            self._focus = ""
        blocked = self._focus_box.blockSignals(True)
        self._focus_box.setCurrentIndex(index)
        self._focus_box.blockSignals(blocked)

    def _on_focus_changed(self, _index: int) -> None:
        self._focus = str(self._focus_box.currentData() or "")
        self._render()

    def _render(self) -> None:
        if not self._merged.reports:
            # NOT an empty FactView. "Nothing has been computed" and
            # "everything ran and had nothing to say" are different
            # statements, and an empty report makes the second one.
            self._view.setVisible(False)
            self._empty.setVisible(True)
            self._view.clear()
            return

        self._empty.setVisible(False)
        self._view.setVisible(True)
        report = self._merged.report_for(self._focus) if self._focus else None
        if report is not None:
            title = self._merged.name_for(report.report_id)
            if self._merged.is_stale(report):
                title += STALE_MARK
            self._view.set_report(report, title, self._summary_for(report))
            return
        self._view.set_report(
            _AllResults(self._merged), "All results", self._summary()
        )

    def _summary(self) -> str:
        names = [
            self._merged.name_for(report.report_id) + (
                STALE_MARK if self._merged.is_stale(report) else ""
            )
            for report in self._merged.reports
        ]
        return f"{len(names)} calculator(s): " + ", ".join(names)

    def _summary_for(self, report) -> str:
        return (
            "Computed for an earlier version of this structure -- re-run it "
            "to refresh."
            if self._merged.is_stale(report)
            else ""
        )


class _AllResults:
    """Every merged fact and every chart, as one thing `FactView` renders.

    **A VIEW OVER `MergedResults`, NOT A COPY OF IT.** `FactView`'s
    contract is anything with `facts`, `by_category()` and `find()`, plus
    the optional `charts`/`limitations` it reads with `getattr` -- so this
    is that surface and nothing more. Building a real `ReportResult` here
    instead would flatten several producers into one `report_id` and one
    `structure_version`, which is precisely what `MergedResults` exists to
    avoid.
    """

    def __init__(self, merged: MergedResults) -> None:
        self._merged = merged
        self.facts = merged.facts
        self.charts = tuple(chart for _report_id, chart in merged.charts())
        self.limitations = merged.limitations()
        self.assumptions = merged.assumptions()

    def by_category(self):
        from openchem.domain.report import CATEGORY_ORDER

        grouped: dict = {}
        for fact in self.facts:
            grouped.setdefault(fact.category, []).append(fact)
        return {
            category: tuple(grouped[category])
            for category in CATEGORY_ORDER
            if category in grouped
        }

    def find(self, text: str):
        needle = text.strip().lower()
        if not needle:
            return self.facts
        return tuple(
            fact
            for fact in self.facts
            if needle in fact.label.lower()
            or needle in fact.display_value.lower()
            or needle in fact.origin.lower()
            or any(needle in item.lower() for item in fact.evidence)
        )
