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

import logging

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

from openchem.domain.visualization_index import kind_of_annotation
from openchem.domain.report import (
    CATEGORY_LABELS,
    DEFAULT_EXPANDED,
    Detail,
    Fact,
    FactLink,
)
from openchem.domain.structure_resolution import ResolvedStructure
from openchem.ui.widgets.collapsible_section import (
    CollapsibleSection,
    ExplicitHeightLabel,
    WrappedLabel,
)
from openchem.ui.fact_help import contract_for
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.chart_widgets import CHART_WIDGET_TYPES, chart_widget_for
from openchem.ui.widgets.stick_chart_widget import StickChartWidget

logger = logging.getLogger("openchem.ui")

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

        #: The Summary. Pinned above the sections and never collapsible --
        #: people want formula, weight and a few descriptors immediately,
        #: not after opening a category. Everything else stays behind a
        #: heading, which is the only thing that makes a hundred facts
        #: readable.
        self._summary = WrappedLabel("", self)
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
        self._report = report
        self._expanded_override = (
            None if expanded is None else frozenset(expanded)
        )
        self._title.setText(title)
        self._summary.setText(summary)
        self._summary.setVisible(bool(summary))
        # BEFORE `_render`, which inserts the category sections at the end
        # of the container -- so the charts sit above the facts, which is
        # where a picture of the result belongs.
        self._rebuild_charts()
        self._render()

    def report(self):
        return self._report

    def clear(self, title: str = "", status: str = "") -> None:
        self._report = None
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
            section.setParent(None)
            section.deleteLater()
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
            # `add_calculator_widget` puts it full-width above the form
            # rows rather than into the label/field grid -- a plot has no
            # caption column, and a form row would give it half the width.
            section.add_calculator_widget(widget)
            self._container_layout.insertWidget(index, section)
            self._chart_sections.append(section)

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
            section.setParent(None)
            section.deleteLater()
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
