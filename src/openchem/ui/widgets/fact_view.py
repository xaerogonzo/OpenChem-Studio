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

import dataclasses
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.visualization_index import kind_of_annotation
from openchem.domain.report import (
    CATEGORY_LABELS,
    COMPLETE_RENDERINGS,
    DEFAULT_EXPANDED,
    INVALID_RENDERINGS,
    Detail,
    Fact,
    FactLink,
    chart_in_rendering,
    default_rendering,
    facts_in_rendering,
    rendering_state,
)
from openchem.domain.structure_resolution import ResolvedStructure
from openchem.ui.widgets.collapsible_section import (
    ClampedLabel,
    CollapsibleSection,
    ExplicitHeightLabel,
    WrappedLabel,
)
from openchem.ui.fact_help import contract_for
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.chart_widgets import CHART_WIDGET_TYPES, chart_widget_for
from openchem.ui.widgets.stick_chart_widget import StickChartWidget
from openchem.ui.widgets.widget_disposal import discard_widget

logger = logging.getLogger("openchem.ui")

COPY_FORMATS = ("Markdown", "Plain text", "JSON", "CSV")

#: Carried on a row so the context menu and the hover handler can find the
#: fact again. Never a lambda closing over `self` -- PySide6 holds a
#: connected plain callable strongly, which rooted a whole window here once.
_FACT_PROPERTY = "openchem_fact"
#: The default file name a chart's picture saves under, carried ON the
#: widget so one connection can serve every chart without a closure.
_PICTURE_STEM = "openchem_picture_stem"
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
    "rendering": HelpTooltip(
        text=(
            "Which unit to read this result in.\n\n"
            "Every unit was computed when the calculator ran; switching shows "
            "a different one and runs nothing. The chart, the facts below it, "
            "Copy report and a saved picture all follow the choice.\n\n"
            "Offered only when the result declares its units completely -- "
            "an older result, or one whose units do not hold together, is "
            "shown in the unit it was computed in."
        ),
        tier=1,
        help_id="facts.rendering",
        topic="facts",
    ),
    "more": HelpTooltip(
        text=(
            "Show the rest of this note, or fold it back to three lines.\n\n"
            "Long notes are folded so the facts between them stay readable in "
            "a narrow or short panel. Nothing is removed: Copy report carries "
            "the whole text either way."
        ),
        tier=1,
        help_id="facts.more",
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


#: Lines a pinned note shows before it folds. Three keeps a one-sentence
#: staleness or refusal line whole and folds the "35 result(s): ..." list
#: that squeezed the facts to two rows.
NOTE_LINES = 3

#: Fact rows the scroll area keeps however little room the panel has: the
#: facts are what is being read, so they are the LAST thing to give way.
#: Converted to pixels from the font, never a hard-coded height.
MIN_VISIBLE_FACT_ROWS = 3

#: The narrowest the filter box may get before the controls take two rows,
#: in average character widths -- enough for "Filter facts" to be legible.
_SEARCH_MIN_CHARS = 18

#: Pixels between rows in compact mode, against the style's own (6 on the
#: Windows style this ships on). See `FactView.set_compact`.
_COMPACT_SPACING = 2


class _ClampedNote(QWidget):
    """A pinned note that folds to `NOTE_LINES` lines, with More/Less.

    The label API the host already used -- `setText`, `text` -- is kept, so
    every existing reader of `_summary` and `_status` is unchanged. The fold
    state belongs to the NOTE, not the text, so it survives the note being
    rewritten on every search keystroke: somebody who opened it keeps it
    open.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = ClampedLabel("", self, max_lines=NOTE_LINES)
        self.toggle = QPushButton("More", self)
        self.toggle.setFlat(True)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet("color: palette(link); padding: 0 4px; text-align: right;")
        self.toggle.clicked.connect(self._on_toggle)
        apply_help_tooltip(self.toggle, _HELP["more"])
        self.toggle.setVisible(False)
        # BESIDE the text, not under it: under it, the control costs a whole
        # line in exactly the short panel the fold exists for.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignBottom)

    def setText(self, text: str) -> None:  # noqa: N802 - the QLabel name it stands in for
        self.label.setText(text)
        self._sync_toggle()

    def text(self) -> str:
        return self.label.text()

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802 - Qt's own casing
        self.label.setStyleSheet(sheet)

    def is_truncated(self) -> bool:
        return self.label.is_truncated()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        super().resizeEvent(event)
        self._sync_toggle()

    def _on_toggle(self, _checked: bool = False) -> None:
        self.label.set_expanded(not self.label.is_expanded())
        self._sync_toggle()

    def _sync_toggle(self) -> None:
        """Offer the control only when it does something.

        Expanded, it always shows ("Less"); folded, only if text is cut. A
        "More" under a note that is already whole is a button that lies.
        """
        expanded = self.label.is_expanded()
        self.toggle.setText("Less" if expanded else "More")
        self.toggle.setVisible(bool(self.label.text()) and (expanded or self.label.is_truncated()))
        self.label.updateGeometry()


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
    #: The search text or the depth control moved.
    #:
    #: **NOT emitted by `set_report`, and not by `set_filter_state`.** Those
    #: are a host putting the view somewhere; this is a READER moving it, and
    #: a host that recorded its own restore would write the position it just
    #: read back over the one it came from.
    filter_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        show_controls: bool = True,
        show_charts: bool = True,
    ) -> None:
        super().__init__(parent)
        self._report = None
        #: How to resolve `molecule_uuid` to a molblock, set by a host that
        #: has a project. None until one does; see `set_structure_resolver`.
        self._structure_resolver = None
        self._sections: dict[str, CollapsibleSection] = {}
        #: **THE CHART SECTIONS LIVE APART FROM `_sections` ON PURPOSE.**
        #: `_render` runs `_clear_sections` on every search keystroke, so a
        #: chart built in there would be destroyed and rebuilt per
        #: character -- losing its expanded state, and rebuilding a painted
        #: widget for a filter that does not apply to it. A chart is not a
        #: fact: `find()` searches facts, and hiding a picture because its
        #: producer's LABEL did not match the needle would be filtering on
        #: something the reader cannot see.
        self._chart_sections: list[CollapsibleSection] = []
        #: A surface with its own visualisation opts out --
        #: `CalculatorInspectorDialog` already draws the result it is
        #: showing, and a second copy above the facts is not a second view.
        self._show_charts = show_charts
        #: **WITHOUT THE CONTROLS, NOTHING MAY HIDE BEHIND THEM.** The depth
        #: filter and the collapsed headings are both things a reader
        #: undoes with a control; hide the controls and each becomes a dead
        #: end. Found by rendering the solubility curve's stats block and
        #: looking at it: four of its seven facts sat behind a collapsed
        #: "Structure (4)" heading, and the status line advised choosing
        #: "Everything" from a combo box that was not on screen.
        self._compact = not show_controls
        #: Set by `set_report`; None means "use `DEFAULT_EXPANDED`".
        self._expanded_override: frozenset | None = None

        self._title = QLabel("", self)
        self._title.setStyleSheet("font-weight: bold;")

        #: The Summary. Pinned above the sections and never behind a heading
        #: -- people want formula, weight and a few descriptors immediately,
        #: not after opening a category. FOLDED past `NOTE_LINES`, though:
        #: pinned and unbounded, it is what squeezed the facts. See
        #: `_ClampedNote`.
        self._summary = _ClampedNote(self)
        self._summary.setStyleSheet("padding: 2px 0;")

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Filter facts (element, lewis, ring...)")
        self._search.textChanged.connect(self._on_filter_changed)
        apply_help_tooltip(self._search, _HELP['search'])

        # Category and depth are ORTHOGONAL, so they are two controls
        # rather than one five-way list -- see `Detail` for why collapsing
        # them would have baked a confusion into the model.
        self._detail = QComboBox(self)
        self._detail.addItem("Standard", Detail.STANDARD.value)
        self._detail.addItem("Everything", "")
        apply_help_tooltip(self._detail, _HELP['detail'])
        self._detail.currentIndexChanged.connect(self._on_filter_changed)

        #: The report as handed in. `_report` is what is SHOWN: this, in the
        #: chosen rendering. Everything that renders, copies or exports reads
        #: `_report`, so all of it follows the choice by construction.
        self._source_report = None
        #: report_id -> the rendering key last chosen for it, so returning to
        #: a result reopens it in the unit it was being read in.
        self._rendering_choice: dict[str, str] = {}
        #: Why a declared set of renderings is not offered, or "".
        self._rendering_problem = ""
        self._rendering_widget = QWidget(self)
        rendering_row = QHBoxLayout(self._rendering_widget)
        rendering_row.setContentsMargins(0, 0, 0, 0)
        rendering_row.addWidget(QLabel("Units:", self._rendering_widget))
        self._rendering_box = QComboBox(self._rendering_widget)
        apply_help_tooltip(self._rendering_box, _HELP["rendering"])
        self._rendering_box.currentIndexChanged.connect(self._on_rendering_chosen)
        rendering_row.addWidget(self._rendering_box)
        self._rendering_widget.setVisible(False)

        self._copy_format = QComboBox(self)
        self._copy_format.addItems(COPY_FORMATS)
        apply_help_tooltip(self._copy_format, _HELP['copy_format'])
        self._copy_button = QPushButton("Copy report", self)
        self._copy_button.clicked.connect(self._on_copy_clicked)
        apply_help_tooltip(self._copy_button, _HELP['copy'])

        self._status = _ClampedNote(self)

        self._container = QWidget(self)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.addStretch(1)
        self._area = QScrollArea(self)
        self._area.setWidget(self._container)
        self._area.setWidgetResizable(True)
        # THE FACTS GIVE WAY LAST. A floor in ROWS, converted from the font,
        # so it means the same thing at any DPI or font size.
        self._area.setMinimumHeight(
            self.fontMetrics().lineSpacing() * MIN_VISIBLE_FACT_ROWS + 2 * self._area.frameWidth()
        )

        self._controls = QWidget(self)
        self._controls_layout = QGridLayout(self._controls)
        self._controls_layout.setContentsMargins(0, 0, 0, 0)
        #: "wide" (one row) or "stacked" (the filter on its own row). See
        #: `_arrange_controls`.
        self._controls_arrangement = ""
        self._arrange_controls(stacked=False)
        self._controls.setVisible(show_controls)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        layout.addWidget(self._summary)
        layout.addWidget(self._controls)
        layout.addWidget(self._area, 1)
        layout.addWidget(self._status)
        self._layout = layout
        #: The style's own spacing, restored when compact mode ends.
        self._normal_spacing = layout.spacing()

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    # --- the controls row ------------------------------------------------------

    def _arrange_controls(self, stacked: bool) -> None:
        """Filter, depth, format and Copy -- on one row, or the filter alone
        above the other three.

        **A ROW OF FOUR SQUEEZES THE ONE CONTROL THAT STRETCHES.** At the
        width Results takes beside Properties the filter box was cut to
        "Filter f..." while three fixed-width controls kept every pixel. Two
        rows only when one cannot fit, and never `flow_row`: that wraps
        per item and reserves lines by width, which the lesson on it records
        costing visible space for a row this short.
        """
        arrangement = "stacked" if stacked else "wide"
        if arrangement == self._controls_arrangement:
            return
        self._controls_arrangement = arrangement
        grid = self._controls_layout
        others = (self._rendering_widget, self._detail, self._copy_format, self._copy_button)
        for widget in (self._search, *others):
            grid.removeWidget(widget)
        for column in range(5):
            grid.setColumnStretch(column, 0)
        if stacked:
            grid.addWidget(self._search, 0, 0, 1, 5)
            for column, widget in enumerate(others):
                grid.addWidget(widget, 1, column)
            grid.setColumnStretch(4, 1)
        else:
            grid.addWidget(self._search, 0, 0)
            for column, widget in enumerate(others, start=1):
                grid.addWidget(widget, 0, column)
            grid.setColumnStretch(0, 1)

    def _controls_need_two_rows(self, width: int) -> bool:
        fixed = sum(
            widget.sizeHint().width()
            for widget in (self._rendering_widget, self._detail, self._copy_format, self._copy_button)
            if not widget.isHidden()
        )
        spacing = max(0, self._controls_layout.horizontalSpacing()) * 4
        search = self.fontMetrics().averageCharWidth() * _SEARCH_MIN_CHARS
        return width < fixed + spacing + search

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt's own casing
        super().resizeEvent(event)
        self._arrange_controls(stacked=self._controls_need_two_rows(event.size().width()))

    def controls_are_stacked(self) -> bool:
        """Whether the filter box has its own row, for a guard to read."""
        return self._controls_arrangement == "stacked"

    # --- what it is showing --------------------------------------------------

    def set_report(
        self, report, title: str = "", summary: str = "", expanded=None
    ) -> None:
        """Show `report`. `expanded` overrides which categories start open.

        **`DEFAULT_EXPANDED` IS A DEFAULT FOR A LARGE REPORT, AND A SMALL
        ONE IS NOT A SMALLER VERSION OF THAT.** Its own docstring gives
        the reason it exists -- *"a hundred-odd facts rendered flat is a
        wall"* -- and an atom report really is that. A report whose whole
        content is six facts is not, and collapsing two thirds of it
        leaves the reader a heading where the answer should be.

        Found the same way the `_compact` rule above was, and in the same
        heading: the formulation report renders its composite formula,
        pressure, velocity and heat of detonation as `STRUCTURE`, so the
        window opened on a name, a component list and a folded
        "Structure (4)" -- with every test green, because nothing asserts
        what a section's initial state is. `_compact` does not cover it:
        that fires when the CONTROLS are hidden, and here they are shown.

        None keeps `DEFAULT_EXPANDED`, so every existing caller is
        unchanged.
        """
        self._source_report = report
        self._expanded_override = (
            None if expanded is None else frozenset(expanded)
        )
        self._title.setText(title)
        self._summary.setText(summary)
        self._summary.setVisible(bool(summary))
        self._sync_renderings()
        # BEFORE `_render`, which inserts the category sections at the end
        # of the container -- so the charts sit above the facts, which is
        # where a picture of the result belongs.
        self._rebuild_charts()
        self._render()

    def report(self):
        """The report as it was handed in -- every rendering, not just the
        one on screen, so a caller opening it elsewhere can still switch."""
        return self._source_report

    # --- renderings (units) ---------------------------------------------------

    def rendering(self) -> str:
        """The rendering key on screen, or "" for a report with none."""
        data = self._rendering_box.currentData()
        return data if self._rendering_widget.isVisibleTo(self) and isinstance(data, str) else ""

    def rendering_problem(self) -> str:
        return self._rendering_problem

    def set_rendering(self, key: str) -> None:
        """Choose a rendering by KEY, as a reader picking it would."""
        index = self._rendering_box.findData(key)
        if index >= 0:
            self._rendering_box.setCurrentIndex(index)

    def _sync_renderings(self) -> None:
        """Offer the report's units -- only when its declaration holds.

        **A DECLARATION THAT DOES NOT HOLD IS READ IN ITS DEFAULT FORM, AND
        SAYS WHY.** An old result has no renderings and gets no control; one
        whose chart changes its x grid between units gets no control either,
        because switching would change the curve rather than its unit, and
        the status line names the reason instead of the control silently
        vanishing.
        """
        report = self._source_report
        state, reason = rendering_state(report) if report is not None else ("none", "")
        self._rendering_problem = reason if state == INVALID_RENDERINGS else ""
        blocked = self._rendering_box.blockSignals(True)
        self._rendering_box.clear()
        if state == COMPLETE_RENDERINGS:
            for rendering in report.renderings:
                self._rendering_box.addItem(rendering.label, rendering.key)
            wanted = self._rendering_choice.get(getattr(report, "report_id", ""), "")
            index = self._rendering_box.findData(wanted)
            self._rendering_box.setCurrentIndex(index if index >= 0 else 0)
        self._rendering_box.blockSignals(blocked)
        self._rendering_widget.setVisible(state == COMPLETE_RENDERINGS)
        self._report = self._in_chosen_rendering(report, state)
        self._arrange_controls(stacked=self._controls_need_two_rows(self.width()))

    def _in_chosen_rendering(self, report, state: str):
        if report is None or state != COMPLETE_RENDERINGS:
            return report
        key = self._rendering_box.currentData() or default_rendering(report)
        return dataclasses.replace(
            report,
            facts=facts_in_rendering(report.facts, key),
            charts=tuple(chart_in_rendering(chart, key) for chart in report.charts),
        )

    def _on_rendering_chosen(self, _index: int) -> None:
        report = self._source_report
        if report is None:
            return
        key = self._rendering_box.currentData()
        if isinstance(key, str):
            self._rendering_choice[getattr(report, "report_id", "")] = key
        self._report = self._in_chosen_rendering(report, rendering_state(report)[0])
        self._rebuild_charts()
        self._render()
        self.filter_changed.emit()

    def clear(self, title: str = "", status: str = "") -> None:
        self._report = None
        self._source_report = None
        self._rendering_widget.setVisible(False)
        self._title.setText(title)
        self._summary.setVisible(False)
        self._clear_sections()
        self._clear_charts()
        self._status.setText(status)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def status_text(self) -> str:
        return self._status.text()

    def title_text(self) -> str:
        return self._title.text()

    def set_title_shown(self, shown: bool) -> None:
        """Whether the bold title LINE is drawn. Its text is kept either way.

        For a host whose own control already names what is showing -- the
        Results reader's "Showing" box carries the same name, stale mark
        included, so the line repeated it at the cost of a row. `title_text`
        and `open_in_window` still read the text, so nothing that uses the
        title as a name loses it.
        """
        self._title.setVisible(shown)

    def set_compact(self, compact: bool) -> None:
        """Tighter spacing between the rows, for a host that is short.

        Spacing only -- no row is removed and the fact floor is untouched, so
        compact changes how much air there is, never what can be read.
        """
        self._layout.setSpacing(_COMPACT_SPACING if compact else self._normal_spacing)

    def is_compact(self) -> bool:
        return self._layout.spacing() == _COMPACT_SPACING and self._normal_spacing != _COMPACT_SPACING

    def summary_text(self) -> str:
        """The pinned line above the sections -- what `set_report`'s `summary`
        argument put there.

        **NOT `status_text`, and the two are easy to confuse.** `_status` is
        this widget's OWN sentence about what it is showing, recomputed on
        every render ("12 facts. 6 advanced hidden..."), so a caller cannot
        put anything in it that survives a keystroke in the search box. The
        summary is the HOST's sentence about the report -- staleness, a
        refusal's reason -- and it is the one a caller sets.

        Exposed because a host that writes it had no way to read it back, so
        a guard on what the reader says about a failed result had to reach
        into `_summary` directly.
        """
        return self._summary.text()

    def search_box(self) -> QLineEdit:
        """Exposed so a window-level shortcut can focus it."""
        return self._search

    def filter_state(self) -> tuple[str, bool]:
        """What the two filter CONTROLS hold: the search text, and whether
        the depth filter is off.

        **THE CONTROLS, NOT THE RENDERED ANSWER.** `_showing_everything`
        also returns True in compact mode, where the controls are HIDDEN --
        that is a rendering decision, and recording it as the reader's
        position would save a filter nobody set and restore it into a view
        where the controls are visible.

        A bool rather than the combo's own data, because "Everything" is
        stored as the EMPTY STRING there -- it is the absence of a depth
        filter rather than a `Detail` member -- and an empty string means
        "nothing recorded" everywhere a position is saved.
        """
        return self._search.text(), not self._detail.currentData()

    def set_filter_state(self, search: str, everything: bool) -> None:
        """Put the two controls back where they were.

        One `_render` at the end rather than one per control: setting them
        separately renders an intermediate state -- the old depth with the
        new search -- which for a large report is visible work nobody asked
        for.
        """
        blocked_search = self._search.blockSignals(True)
        blocked_detail = self._detail.blockSignals(True)
        self._search.setText(search)
        index = self._detail.findData("" if everything else Detail.STANDARD.value)
        if index >= 0:
            self._detail.setCurrentIndex(index)
        self._search.blockSignals(blocked_search)
        self._detail.blockSignals(blocked_detail)
        self._render()

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

    def _clear_charts(self) -> None:
        for section in self._chart_sections:
            # Not `setParent(None)` alone -- see `widget_disposal`.
            discard_widget(section)
        self._chart_sections.clear()

    def _rebuild_charts(self) -> None:
        """One collapsible section per declared chart, above the facts.

        **INSIDE THE SCROLL AREA, NOT ABOVE IT.** A fixed-height chart in
        the layout above `self._area` -- which is a `QScrollArea` with
        `setWidgetResizable(True)` -- is the height-for-width fight this
        project has now lost three times, and the Atom Inspector renders
        this widget in a 280 px dock. Inside the area it cannot arise: the
        chart is one more thing to scroll past.

        **READ WITH `getattr`, BECAUSE NOT EVERY REPORT HAS THE FIELD.**
        `charts` is on `ReportResult`; `StructureReport`, `AtomReport` and
        `BondReport` have no such attribute, and `report.charts` would
        raise in the Atom Inspector. The file already reads `highlight` and
        `detail` off a fact the same way, for the same reason.

        **NOTHING HERE DERIVES A CHART FROM THE FACTS.** An empty tuple is
        the producer's statement that this result has no picture -- and
        elemental analysis emits "C: 55.34%" as facts, so a view that
        parsed those into bars would have invented a picture the producer
        never claimed. A picture reads as a result.
        """
        self._clear_charts()
        if not self._show_charts or self._report is None:
            return
        charts = getattr(self._report, "charts", ()) or ()
        # ONCE, not per chart: resolving is a project lookup, and two charts
        # on one report describe one structure by construction.
        resolved = self._structure_for_report()
        for index, chart in enumerate(charts):
            # The FIRST one open, the rest folded. `set_report`'s own
            # docstring records why a small report is not a smaller version
            # of a large one: a result whose whole point is its picture must
            # not open on a heading where the picture should be. Several
            # charts at once is the batch case, and five expanded plots is a
            # wall of the same kind.
            # **THE HEADING SAYS WHAT KIND OF PICTURE IT IS**, derived from
            # the annotation TYPE by the same question `chart_widget_for`
            # asks below, so the label and the widget cannot disagree about
            # what an annotation is. "Isotope pattern" and "Lewis sites" are
            # a plot and a structure drawing, and a reader scrolling past a
            # folded heading has no other way to tell.
            kind = kind_of_annotation(chart)
            section = CollapsibleSection(
                f"{chart.title or f'Chart {index + 1}'} [{kind}]",
                index == 0,
                self._container,
            )
            # DISPATCH BY TYPE, in one place. A second kind cost a `|` on
            # the union and an entry in the factory; a `chart.kind ==`
            # string ladder here would be a weaker vocabulary beside the
            # types the domain already has, and its typos fail open.
            widget = chart_widget_for(
                chart,
                section.content,
                molblock=resolved.molblock,
                refusal=resolved.refusal,
            )
            # **THE PICTURE CAN BE TAKEN AWAY, FROM WHEREVER IT IS BEING
            # READ.** Installed on the widget the reader just built, so the
            # docked reader, the popped-out one and a copy in its own window
            # offer it identically by construction rather than by three
            # implementations agreeing -- which is most of the value of
            # having one renderer. Before this, exporting a drawing existed
            # in exactly one dialog and every other picture was read-only.
            self._install_picture_menu(widget, chart.title or f"chart-{index + 1}")
            # `add_calculator_widget` puts it full-width above the form
            # rows rather than into the label/field grid -- a plot has no
            # caption column, and a form row would give it half the width.
            section.add_calculator_widget(widget)
            self._container_layout.insertWidget(index, section)
            self._chart_sections.append(section)

    def _install_picture_menu(self, widget, stem: str) -> None:
        """Right-click a chart or a depiction to copy or save it.

        A context menu rather than a button per section: the Atom Inspector
        renders this widget in a 280 px dock, and a control beside every
        chart is the width this whole line of work spent three rounds
        reclaiming. The actions are built when the menu OPENS, so a
        depiction that refused to draw offers no "Copy as SVG" -- see
        `picture_export.add_picture_actions`.
        """
        from openchem.ui.picture_export import file_stem

        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # **A BOUND METHOD, NEVER A CLOSURE CAPTURING `self`.** PySide6
        # holds a connected plain callable strongly, so a closure's captured
        # `self` survives refcounting AND the cyclic collector -- recorded
        # twice in `app/main_window.py`, where it leaked whole windows. Here
        # it would pin this view from a chart widget it owns, and this
        # project ties that leak class to the disposal crashes.
        #
        # The stem travels on the WIDGET rather than in a capture, which is
        # the same trick `_add_editor_action` uses to carry a test id on a
        # QAction.
        widget.setProperty(_PICTURE_STEM, file_stem(stem))
        widget.customContextMenuRequested.connect(self._on_picture_menu)

    def _on_picture_menu(self, position) -> None:
        """Right-clicked a chart -- offer what THAT chart can produce.

        The widget comes from `sender()` rather than from a capture, so one
        connection serves every chart and nothing holds a reference to this
        view. `sender()` is the emitting widget because the connection was
        made on it.
        """
        from openchem.ui.picture_export import add_picture_actions

        widget = self.sender()
        if widget is None:  # pragma: no cover - defensive
            return
        menu = QMenu(widget)
        add_picture_actions(menu, widget, self, str(widget.property(_PICTURE_STEM) or "picture"))
        menu.exec(widget.mapToGlobal(position))

    def set_structure_resolver(self, resolver) -> None:
        """Supply how to resolve a REPORT to coordinates, or None.

        **THE RENDER CONTEXT, INJECTED.** A declared depiction carries
        atom indices and no geometry -- deliberately, since an annotation
        holding an RDKit molecule would put a toolkit object in `domain/`
        and give the report a second copy of the structure. So the host
        that already has the project supplies the resolution, and a host
        that has no project supplies nothing.

        A view with no resolver still renders every other chart kind: a
        plot on axes needs no structure. Only the depiction says it cannot
        draw, which is a different fact from having nothing to draw.

        **IT TAKES THE REPORT, NOT A `molecule_uuid`, AND THAT IS THE SAFETY
        PROPERTY.** A uuid resolver can only answer with the CURRENT
        structure, and a stale result's atom indices describe the one it was
        computed on -- so `atom 7` becomes atom 7 of a different molecule and
        the picture looks entirely normal while pointing at the wrong atoms.
        Only the report carries the version and the geometry provenance that
        decide whether drawing it is safe, so only the report can be asked.
        See `domain/structure_resolution.py`.

        The resolver returns a `ResolvedStructure` -- coordinates, or a reason
        they were withheld. A bare "" could not tell those apart, and a reader
        shown an empty frame with no reason is the failure being prevented.
        """
        self._structure_resolver = resolver
        self._rebuild_charts()

    def _structure_for_report(self) -> ResolvedStructure:
        """Coordinates for this report's depiction, or why there are none.

        The report is handed over whole rather than its uuid -- see
        `set_structure_resolver` for why that is a correctness property and
        not a convenience.
        """
        resolver = getattr(self, "_structure_resolver", None)
        # `is not None`, NOT truthiness: a factless report is a real report
        # (a refusal, a picture-only result) and must still resolve a structure.
        if resolver is None or self._report is None:
            return ResolvedStructure()
        try:
            resolved = resolver(self._report)
        except Exception:
            # A host whose resolver raises gets a message rather than a
            # traceback out of a paint path -- and the chart section still
            # appears, so the declaration stays visible.
            logger.exception("structure resolver raised; refusing the depiction")
            return ResolvedStructure.refused(
                "Visualization unavailable -- this structure could not be resolved."
            )
        # A host that hands back a bare molblock is accepted rather than
        # crashing the paint path, but it is NOT the contract: such a host
        # cannot refuse, so `test_a_resolver_must_be_able_to_refuse` asserts
        # every production one returns the value type.
        if isinstance(resolved, str):
            return ResolvedStructure.of(resolved)
        return resolved or ResolvedStructure()

    def chart_widgets(self) -> list[QWidget]:
        """The charts currently on screen, read back off the sections.

        Derived from the widgets rather than from the report, so a test
        cannot pass against charts that never reached the display -- the
        same reason `visible_fact_labels` reads the rows.

        **EVERY KIND THE FACTORY CAN PRODUCE, not one class.** Filtering
        on `StickChartWidget` was right while that was the only kind and
        became a silent undercount the moment a second arrived: a line
        chart, or the label saying a kind cannot be drawn, would simply
        not appear -- so a guard reading this would report "no chart" for
        a chart that is plainly on screen.

        The types come from `CHART_WIDGET_TYPES` beside the factory, so
        the two cannot disagree about what a chart widget is.
        """
        widgets: list[QWidget] = []
        for section in self._chart_sections:
            for kind in CHART_WIDGET_TYPES:
                widgets.extend(section.content.findChildren(kind))
        return widgets

    def _clear_sections(self) -> None:
        for section in self._sections.values():
            # Not `setParent(None)` alone: that opened each section as a
            # white window when renders arrived faster than the event loop.
            # See `widget_disposal`.
            discard_widget(section)
        self._sections.clear()

    def _on_filter_changed(self) -> None:
        """Re-render, and say that the filter moved.

        **A SIGNAL RATHER THAN A SAVE-ON-CLOSE HOOK.** A reader's position
        has to be recorded as it CHANGES, not when its window shuts: a
        persistent dock never closes, so a `finished`-driven save settles
        nothing for the surface it is being settled for.
        """
        self._render()
        self.filter_changed.emit()

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
            open_by_default = (
                DEFAULT_EXPANDED
                if self._expanded_override is None
                else self._expanded_override
            )
            expanded = self._compact or bool(needle.strip()) or category in open_by_default
            section = CollapsibleSection(
                f"{CATEGORY_LABELS[category]} ({len(visible)})", expanded, self._container
            )
            for fact in visible:
                self._add_row(section, fact)
            self._container_layout.insertWidget(self._container_layout.count() - 1, section)
            self._sections[category.value] = section

        self._status.setText(self._status_text(report, shown, needle, hidden_by_depth))

    def _caption(self, section: CollapsibleSection, fact: Fact, provenance: str) -> QLabel:
        """The fact's NAME, carrying what the fact MEANS.

        **THE CAPTION IS WHAT A READER HOVERS, AND IT HAD NO TOOLTIP AT
        ALL.** `addRow(str, widget)` has Qt build the label for you, and a
        label Qt built carries nothing -- so the provenance went on the
        value and the question people actually ask, "what IS this", was
        answered nowhere. That is the complaint the whole help layer started
        from: somebody asked what the docking table's "RMSD l.b." column
        meant and the application had no answer.

        **MEANING HERE, PROVENANCE ON THE VALUE.** Two different questions,
        and folding both into one tooltip makes the long one unreadable. The
        name says what the quantity is; the number says where it came from.

        A fact with no contract falls back to the provenance rather than to
        nothing: a dead hover on the thing a reader points at first is worse
        than a repeated one, and for a calculator's own facts the evidence
        and limitations really are the whole answer.
        """
        caption = QLabel(fact.label, section.content)
        contract = contract_for(fact.help_id)
        if contract is not None:
            apply_help_tooltip(caption, contract)
        elif provenance:
            caption.setToolTip(provenance)
        return caption

    def _add_row(self, section: CollapsibleSection, fact: Fact) -> None:
        provenance = "\n".join(
            [
                f"Source: {fact.source}",
                f"Basis: {fact.basis.value}",
                *fact.evidence,
                *fact.limitations,
            ]
        )
        value = _FactRow(fact.value_with_units, section.content)
        value.setProperty(_FACT_PROPERTY, fact)
        value.setToolTip(provenance)
        value.hovered.connect(self._on_row_hovered)
        if fact.link is None:
            section.content_layout().addRow(
                self._caption(section, fact, provenance), value
            )
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
        section.content_layout().addRow(self._caption(section, fact, provenance), row)

    def _status_text(self, report, shown: int, needle: str, hidden_by_depth: int) -> str:
        text = self._status_text_for_facts(report, shown, needle, hidden_by_depth)
        if self._rendering_problem:
            text += f" Units cannot be switched: {self._rendering_problem}."
        return text

    def _status_text_for_facts(self, report, shown: int, needle: str, hidden_by_depth: int) -> str:
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
        view = FactView(dialog, show_charts=self._show_charts)
        view.set_report(self._source_report, self._title.text(), self._summary.text())
        view.set_rendering(self.rendering())
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
