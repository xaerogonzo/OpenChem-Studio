"""Everything computed for one molecule, as one embeddable widget.

**THE READER IS A WIDGET, NOT A WINDOW, AND THAT IS THE WHOLE POINT OF
THIS MODULE EXISTING.** All of this lived in `MergedResultsDialog` and was
therefore a dialog: something you open, read and close. A reader that
FOLLOWS the selection cannot be a dialog -- it is a dock, and the same
content also has to be able to sit in a pop-out window -- so the reader
moved out of the window and the window became a shell around it.

**ONE CLASS, HOWEVER MANY FORMATS.** A docked reader and a popped-out one
that were two classes would drift the moment one grew a control, and this
project has paid for two implementations of one idea four times over
(`is_stripped_residue`, `filter_altlocs`, `is_symmetry_generated`,
`normalise_element_symbols`). `PopOutHost` MOVES this widget between a
dock and a window rather than copying it, so focus, filter and scroll
travel with it by construction rather than by being kept in step.

**THE EXTRACTION IS BEHAVIOUR-NEUTRAL BY CONSTRUCTION**, which is the same
move `ui/widgets/zoomable_svg_view.py` made out of the Lewis dialog:
`MergedResultsDialog` keeps its whole surface as delegations and ALIASES
onto these same objects, so its tests are unmoved rather than rewritten.
A refactor whose correctness rests on re-testing is a refactor whose
correctness rests on the tests having been complete.

**THE COMPLAINT THIS EXISTS FOR.** "Details..." opened one calculator's
report, so running Substance & Bonding and then Lewis Sites replaced the
first window with the second -- and `FactView`'s search box, depth filter
and copy, all built for a hundred facts, were being handed four. The
filter was useless because there was nothing to filter.

**IT IS THE SAME SURFACE, FOCUSED, NOT A SECOND ONE.** Every existing
"Details..." button still reaches this reader; it arrives focused on the
report whose button was pressed, with that report's facts in view and its
chart drawn. A second parallel Details implementation is exactly what this
change exists to end.

**LIVE, AND NEVER MODAL.** The old dialog used `exec()`, which blocks the
panel -- so with a modal window you could never run the second calculator
whose results this exists to accumulate. Keyed by molecule UUID rather
than by object identity (a rebuilt model must not read as a different
molecule), refreshed as results arrive.

**STALE RESULTS ARE MARKED, NEVER DISCARDED.** A report describing an
older revision of the structure is still a record of what was computed.
Silently serving one and silently blanking one are the two ways this goes
wrong, and they look identical from outside.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.common import CacheState, describe_failure
from openchem.domain.merged_results import MergedResults, merge_reports
from openchem.domain.reader_state import (
    NO_MOLECULE,
    NOTHING_COMPUTED,
    ReaderView,
    reader_state,
)
from openchem.domain.report import FactLink
from openchem.domain.result_ordering import grouped_reports, matching_reports
from openchem.domain.structure_issue import Severity
from openchem.domain.visualization_index import declared_visualizations
from openchem.ui.result_summary import summary_of_merge
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

logger = logging.getLogger("openchem.ui")

#: Which viewer opens the whole of a summarised result, what the button
#: calls it, and -- because this table IS the vocabulary -- which kinds get
#: a button at all.
#:
#: The label names the DESTINATION rather than the action. "Open" says
#: nothing about where you land, and a reader choosing between a summary and
#: the whole thing is choosing which surface to read it on.
#:
#: **A KIND ABSENT FROM IT OFFERS NO BUTTON.**
#: `ir_view` is deliberately not here. `IrViewWidget` is a TAB inside the
#: Quantum Chemistry panel rather than a viewer a result can be handed to, so
#: there is nothing to route to -- and offering a button that reports "unknown
#: target" is worse than offering none, which is a different claim from 0g's
#: rule that a link somebody DECLARED must never be a silent no-op.
#:
#: Measured: no registry calculator produces a vibrational spectrum at all
#: (60 results on aspirin, and the kinds are report, per_atom, structure_set,
#: ph_curve, alert, spectrum, trajectory), so this costs nothing today. WHAT
#: WOULD LIFT IT: an IR viewer a single result can be opened in, or an
#: `ir_view` route that reveals the panel owning it -- the shape `nmr_view`
#: already degrades to when no spectrum is named.
#:
#: **PROTOTYPES WITH LITERAL TARGETS, NOT A COMPUTED ONE, AND THE SUITE
#: REFUSED THE COMPUTED FORM.** The obvious shape is
#: `FactLink(target=target, ...)` with the focused entry's declared viewer in
#: a variable -- and `test_no_producer_computes_a_link_target` rejects it,
#: correctly: `test_every_emitted_link_target_has_a_handler` walks the source
#: for emitted targets and is what found four dead buttons, so a target it
#: cannot read statically shrinks that guard's universe without failing it.
#: The green-suite-and-a-smaller-universe failure, caught before it shipped.
#:
#: Each entry carries its own `target` as a literal and its own label; the
#: report id is filled in per use with `replace`, since `FactLink` is frozen.
_VIEWER_ACTIONS: dict[str, FactLink] = {
    "calculator_inspector": FactLink(
        target="calculator_inspector", label="Open in Calculator Inspector"
    ),
    "nmr_view": FactLink(target="nmr_view", label="Open in NMR view"),
}

#: Which annotation an Open button means, carried on the button itself.
#:
#: `setProperty` plus a bound method reading `sender()` -- the shape this
#: codebase settled on after a self-capturing lambda leaked a widget per
#: calculator in five files.
_VISUAL_INDEX_PROPERTY = "openchem_visual_index"
#: Which report that annotation belongs to.
_VISUAL_REPORT_PROPERTY = "openchem_visual_report"

#: What an Open button beside a visualization means. ONE contract however
#: many rows are drawn -- "show this picture properly" is one concept, and a
#: contract per row would be the sixty-tick-boxes split refused elsewhere.
_VISUAL_OPEN_HELP = HelpTooltip(
    text=(
        "Draw this on a 3D model of the molecule, in its own window.\n\n"
        "A vector, a cone or a set of axes is drawn on a conformer rather "
        "than in a list, so it opens beside the values instead of among "
        "them. The window shows the same facts, search and export underneath "
        "the picture.\n\n"
        "It draws the molecule's stored conformer, which is the frame the "
        "annotation's coordinates are in. It computes nothing and re-runs "
        "nothing."
    ),
    tier=2,
    help_id="results.open_visualization",
    topic="facts",
)

#: The link that opens one declared PICTURE on a 3D model.
#:
#: A literal target for the reason the table above carries literals: a source
#: walk is what checks every emitted target has a handler, and a computed one
#: shrinks that guard's universe without failing it. `params` names which
#: report and which annotation, filled in per use with `replace`.
_SPATIAL_ACTION = FactLink(target="spatial_view", label="Open")

#: What the result-level action means. ONE contract for every viewer it
#: can offer: "open the whole thing" means the same wherever it lands,
#: and a contract per destination would be one concept wearing several.
_OPEN_HELP = HelpTooltip(
    text=(
        "Open the whole result this summary describes, in the viewer that "
        "owns it.\n\n"
        "A per-atom table, a curve, a spectrum, a set of structures and a "
        "trajectory each reach this window as a SUMMARY -- a count, a range, "
        "and whatever total the calculator declared. This opens the result "
        "itself, which is where every value lives.\n\n"
        "It computes nothing and re-runs nothing. If the result is no longer "
        "held -- the molecule changed, or its results were cleared -- the "
        "status bar says so rather than the button doing nothing."
    ),
    tier=1,
    help_id="results.open_full_result",
    topic="facts",
)

#: What the selector search means. Deliberately NOT the same concept as
#: `FactView`'s search box, and it carries its own `help_id` for that reason:
#: one narrows which RESULT you are reading, the other the VALUES inside it,
#: and giving them one id would be two concepts wearing one -- the mirror of
#: the split `test_one_concept_is_not_split_across_many_help_ids` refuses.
_SELECTOR_SEARCH_HELP = HelpTooltip(
    text=(
        "Narrow the list of results by name or section.\n\n"
        "This filters WHICH result you are looking at. The search box below "
        "the list filters the VALUES within the one you have chosen -- two "
        "different questions, so they are two different boxes.\n\n"
        "It matches a result's name and the section it sits under, so "
        "\"solubility\" finds everything filed there whatever each one is "
        "called. Sections with nothing left in them disappear. It hides rows: "
        "it computes nothing, discards nothing, and re-runs nothing, and the "
        "result you are currently reading always stays in the list."
    ),
    tier=1,
    help_id="results.filter_result_list",
    topic="facts",
)

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

#: What an empty reader says, per `reader_state`.
#:
#: **TWO MESSAGES, BECAUSE THERE ARE TWO EMPTY STATES.** "Pick a molecule"
#: and "nothing has been computed for this one yet" send a reader to two
#: different places, and this window rendered only the second -- it is
#: opened for a molecule, so the first has had no route through the
#: application. A reader that FOLLOWS the selection has one, which is why
#: the text exists before the dock does.
EMPTY_MESSAGES = {
    NO_MOLECULE: (
        "No molecule is selected.\n\n"
        "Choose one and everything computed for it appears here."
    ),
    NOTHING_COMPUTED: (
        "Nothing has been computed for this molecule yet.\n\n"
        "Run a calculator and its results appear here."
    ),
}

#: The data a group heading carries.
#:
#: **NOT an empty string, and not "no data at all".** `_sync_focus_box`
#: restores the selection with `findData(self._focus)`, and `""` is a REAL
#: value there -- it is what ALL_RESULTS carries -- so a heading holding it
#: would be found first and the box would restore onto an unselectable row.
#: An INTEGER keeps the two apart by construction: every `report_id` is a
#: string, so no heading can ever compare equal to one, and it needs no
#: escape sequence to write down. The first attempt used a string with a NUL
#: in it and put a real NUL BYTE into this source file -- the shell-heredoc
#: backslash trap this repository records twice, sprung a third time by
#: somebody who had read both entries.
GROUP_HEADING = -1


class ResultsView(QWidget):
    """One molecule's accumulated results, focusable by calculator.

    Embeddable rather than a window: a dialog holds one today, a dock and
    its pop-out window hold one next. Nothing here knows which.
    """

    #: A request to open something -- a fact's own cross-link, or the WHOLE
    #: result the focused entry is a summary of.
    #:
    #: **ONE SIGNAL FOR BOTH, BECAUSE THEY ARE ONE QUESTION.** Both carry a
    #: `FactLink`, both are answered by `FactLinkRouter`, and both have the
    #: same three outcomes -- opened, known but unavailable, unknown target.
    #: A second signal would be a second place for a target to go unrouted,
    #: which is the defect 0g exists to remove.
    #:
    #: This window does NOT open anything itself. Routing lives in the window
    #: that owns the dialogs, so this stays constructible in a test with no
    #: application around it -- the same split `AtomInspectorPanel` already
    #: makes with `link_activated`.
    link_activated = Signal(object)

    def __init__(
        self,
        molecule_uuid: str = "",
        parent: QWidget | None = None,
        display_order_of=None,
    ) -> None:
        super().__init__(parent)
        # DEFAULTED, because a reader that follows the selection starts
        # before anything is selected. `reader_state` already has a name for
        # that state and this window had no route into it -- it was opened
        # FOR a molecule, so "no molecule" was unreachable here.
        self._molecule_uuid = molecule_uuid
        self._merged = MergedResults(reports=(), facts=())
        self._focus = ""
        # Where each calculator sits in the registry -- the ONE ordering term
        # a report cannot answer about itself. Injected rather than looked up
        # here, so this window needs no registry and the ordering stays
        # testable without one. Absent, the order is still total and still
        # stable; it just cannot honour the editorial order WITHIN a section.
        self._display_order_of = display_order_of
        # Where this molecule's reader was, if anything is keeping track.
        # Optional, so a window built without one behaves exactly as before.
        self._memory = None

        self._focus_box = QComboBox(self)
        self._focus_box.currentIndexChanged.connect(self._on_focus_changed)
        apply_help_tooltip(self._focus_box, _FOCUS_HELP)

        # **THE SECOND SEARCH, AND IT IS A DIFFERENT QUESTION FROM THE FIRST.**
        # Measured after 1a: a molecule with everything run puts 60 entries and
        # 20 headings into that combo, 81 rows with "All results" -- a
        # scrolling problem rather than a reading one. `FactView`'s box below
        # narrows the VALUES inside one report and cannot narrow the list.
        self._selector_search = QLineEdit(self)
        self._selector_search.setPlaceholderText("Filter results by name or section")
        self._selector_search.setClearButtonEnabled(True)
        self._selector_search.textChanged.connect(self._on_selector_search_changed)
        apply_help_tooltip(self._selector_search, _SELECTOR_SEARCH_HELP)

        focus_row = QWidget(self)
        row = QHBoxLayout(focus_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Showing:", focus_row))
        row.addWidget(self._focus_box, 1)

        # **THE RESULT-LEVEL ACTION, WHICH A FACT ROW CANNOT CARRY.** Measured
        # over the registry on aspirin: 60 entries reach the reader and 30 of
        # them declare a viewer, which is exactly the half that arrives as a
        # summary. "The first fact carries the link" would strip the viewer
        # from precisely those, because a summary's facts are projections and
        # none of them is the result.
        self._open_button = QPushButton("", focus_row)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._open_button.setVisible(False)
        apply_help_tooltip(self._open_button, _OPEN_HELP)
        row.addWidget(self._open_button)

        # **EVERY PICTURE THE FOCUSED RESULT DECLARES, AS PEERS.** They were
        # peers in the model already -- all producer-declared annotations,
        # validated fail-closed -- and not on screen: charts and depictions
        # rendered inside the reader while a spatial annotation could only be
        # seen in a separate MODAL window the reader was no part of.
        self._visuals = QWidget(self)
        self._visuals_layout = QVBoxLayout(self._visuals)
        self._visuals_layout.setContentsMargins(0, 0, 0, 0)
        self._visuals_heading = QLabel("Visualizations", self._visuals)
        self._visuals_heading.setStyleSheet("font-weight: bold;")
        self._visuals_layout.addWidget(self._visuals_heading)
        self._visuals.setVisible(False)

        self._view = FactView(self)
        self._view.filter_changed.connect(self._remember)
        # **DEAD IN THIS WINDOW UNTIL NOW.** `FactView` builds a `>` button
        # per linked fact and emits this; the Atom Inspector routes it and
        # this reader never connected it, so a link here rendered a control
        # and did nothing -- the same silent no-op 0g removed one surface
        # along. Measured, no registry result carries a `FactLink` today, so
        # this is defence rather than a live fix; it is asserted on the
        # WIRING for that reason.
        self._view.link_activated.connect(self.link_activated)
        self._empty = QLabel(EMPTY_MESSAGES[NOTHING_COMPUTED], self)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._selector_search)
        layout.addWidget(focus_row)
        layout.addWidget(self._visuals)
        layout.addWidget(self._view, 1)
        layout.addWidget(self._empty, 1)

        # **RENDER THE INITIAL STATE RATHER THAN ASSUMING IT**, and the guard
        # for it failed on its first run. `self._empty` is built with the
        # nothing-computed message, and until this call the widget SHOWED
        # that whatever it was holding -- true by construction while this was
        # a dialog, because a dialog is opened FOR a molecule and the other
        # empty state was unreachable. A reader that follows the selection
        # starts with no molecule, where that message names the wrong
        # problem: "nothing has been computed for this molecule" when there
        # is no molecule sends somebody looking for a calculator to run.
        self._render()

    # --- what it is showing --------------------------------------------------

    def set_structure_resolver(self, resolver) -> None:
        """Forward the render context to the view that draws depictions.

        **NOTHING IN PRODUCTION SUPPLIED ONE UNTIL THIS EXISTED**, and the
        consequence was not subtle: `lewis_site_depiction` builds a complete
        `DepictionAnnotation` with role colours and a caption, and
        `compute_lewis_sites` attaches it -- so the Lewis-site diagram was
        fully built, tested, and could never draw. A depiction carries atom
        indices and no geometry, so without a resolver it has nothing to draw
        ON. The only caller was the drive harness.

        The resolver takes the REPORT, and that is a safety property rather
        than a signature detail -- see `FactView.set_structure_resolver` and
        `domain/structure_resolution.py`.
        """
        self._view.set_structure_resolver(resolver)

    def molecule_uuid(self) -> str:
        return self._molecule_uuid

    def set_molecule(self, molecule_uuid: str) -> None:
        """Read a different molecule, holding none of the last one's results.

        **THE CONTENT IS DROPPED HERE RATHER THAN LEFT FOR THE CALLER**, and
        that is a safety property rather than tidiness. A reader that changed
        its uuid and kept its reports would render the PREVIOUS molecule's
        results under the new molecule's name -- every value plausible, every
        one about something else. It is the same failure class as a stale
        depiction drawn on the current structure, one level up, and nothing
        downstream could detect it.

        **IT RECORDS NOTHING.** `_remember` has already written this reader's
        position on every move that made it, so the outgoing molecule's
        position is safe; and writing the incoming molecule's EMPTY state here
        would overwrite the very position the host is about to restore. Same
        rule `apply_view` follows, and the reason it does not call `_remember`
        either.
        """
        if molecule_uuid == self._molecule_uuid:
            return
        self._molecule_uuid = molecule_uuid
        self._merged = MergedResults(reports=(), facts=())
        self._focus = ""
        self._rebuild_focus_box()
        self._render()

    # --- where the reader is ------------------------------------------------

    def set_reader_memory(self, memory) -> None:
        """Record this reader's position, as it moves.

        **RECORDED ON EVERY CHANGE, NOT SAVED ON CLOSE.** A save-on-close hook
        would work here -- `finished` covers the X, `close()` and Escape alike,
        which `PopOutWindow` already relies on -- and it settles nothing for
        the surface this behaviour is being settled FOR: a persistent reader
        never closes. So the position is written as the reader moves it, and
        the memory is never behind.
        """
        self._memory = memory

    def view(self) -> ReaderView:
        """What this window is showing: the focused report and the filter."""
        search, everything = self._view.filter_state()
        return ReaderView(
            report_id=self._focus,
            search=search,
            everything=everything,
            selector_search=self._selector_search.text(),
        )

    def apply_view(self, view: ReaderView) -> None:
        """Put the window where `view` says, without recording that as a move.

        The filter first, then the focus -- `set_focus` renders, so setting
        them the other way round renders the new report through the OLD filter
        and then again through the new one.
        """
        self._view.set_filter_state(view.search, view.everything)
        # SIGNALS BLOCKED, for the same reason `set_filter_state` blocks its
        # own: this is a host RESTORING a position, and letting the handler
        # fire would call `_remember` and write the restore back -- which the
        # note below is about, and which `_apply_focus` is careful not to do.
        blocked = self._selector_search.blockSignals(True)
        self._selector_search.setText(view.selector_search)
        self._selector_search.blockSignals(blocked)
        self._apply_focus(view.report_id)
        # NOT a `_remember`. A host restoring a position must not write it
        # back: with a memory whose recall FELL BACK -- the focused report is
        # gone -- recording the restore would overwrite the remembered id with
        # the empty one, so a report that came back later could never be
        # restored again.

    def _remember(self) -> None:
        if self._memory is not None:
            self._memory.remember(self._molecule_uuid, self.view())

    def set_reports(self, reports, structure_version: int = 0) -> None:
        """Replace what this window shows.

        Called both when the window opens and whenever another result
        arrives for this molecule -- the window is live, so the second
        calculator's facts land in the open window rather than needing it
        reopened.
        """
        self._merged = merge_reports(
            reports,
            structure_version=structure_version,
            display_order_of=self._display_order_of,
        )
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
        self._apply_focus(report_id)
        # A HOST ACTING FOR A READER -- pressing "Details..." beside a
        # calculator is choosing that report, and it is where the reader
        # should be when they come back. `apply_view` deliberately does NOT
        # come through here; see its own note.
        self._remember()

    def _apply_focus(self, report_id: str) -> None:
        # `is not None`. A refused calculator's report has no facts, and
        # truthiness here made it unfocusable -- it appeared in the selector
        # and choosing it fell back to All results, silently.
        self._focus = report_id if self._merged.report_for(report_id) is not None else ""
        self._sync_focus_box()
        self._render()

    # --- rendering -----------------------------------------------------------

    def _rebuild_focus_box(self) -> None:
        """Rebuild the "Showing" list: headings, then their entries.

        **GROUPED THE WAY THE PROPERTIES PANEL IS**, and by the same
        `category_label`, so one section cannot end up with two names. The
        list was flat and arrival-ordered, which for a molecule with
        everything run is 30 entries in whatever order the runs happened to
        finish.

        **A HEADING IS ONLY EVER EMITTED FOR A GROUP THAT HAS SOMETHING IN
        IT** -- `grouped_reports` guarantees that, so this loop cannot leave
        seventeen empty headings behind for somebody who has run three
        calculators.
        """
        blocked = self._focus_box.blockSignals(True)
        self._focus_box.clear()
        self._focus_box.addItem(ALL_RESULTS, "")
        # FILTERED BEFORE GROUPING, which is what makes the empty-heading
        # behaviour free: `grouped_reports` never emits a group with nothing
        # in it, so a search that empties a section removes its heading with
        # no rule here. Its docstring says so, written before this existed.
        listed = matching_reports(
            self._merged.reports, self._selector_search.text(), always=self._focus
        )
        for group in grouped_reports(listed, self._display_order_of):
            self._add_group_heading(group.label)
            for report in group.entries:
                label = self._merged.name_for(report.report_id)
                if self._merged.is_stale(report):
                    label += STALE_MARK
                self._focus_box.addItem(label, report.report_id)
        self._focus_box.blockSignals(blocked)
        self._sync_focus_box()

    def _add_group_heading(self, label: str) -> None:
        """A row that names a section and cannot be chosen.

        **DISABLED, NOT MERELY STYLED.** Qt skips a disabled row for keyboard
        navigation and refuses to make it current, so the heading cannot
        become the focus -- which is what would otherwise happen the moment
        somebody arrows through the list. Bold rather than indented for the
        opposite reason: a closed combo box paints the CURRENT entry's own
        text, so indenting the entries would show the indent in the collapsed
        control.
        """
        self._focus_box.addItem(label, GROUP_HEADING)
        model = self._focus_box.model()
        item = model.item(self._focus_box.count() - 1) if hasattr(model, "item") else None
        if item is None:
            return
        item.setEnabled(False)
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    def _sync_focus_box(self) -> None:
        index = self._focus_box.findData(self._focus)
        if index < 0:
            index = 0
            self._focus = ""
        blocked = self._focus_box.blockSignals(True)
        self._focus_box.setCurrentIndex(index)
        self._focus_box.blockSignals(blocked)

    def _sync_visualizations(self, report) -> None:
        """List what `report` can show, each row saying WHAT it is.

        **A TYPE LABEL, BECAUSE "Open" SAYS NOTHING ABOUT WHAT ARRIVES.** A
        stick chart of an isotope pattern, a 2D structure with sites marked
        on it and a vector drawn on a 3D conformer are three different things
        to look at, and they cost very different amounts to open -- a 3D
        overlay is a QtWebEngine process, which this project has measured
        accumulating to 116 and hanging the suite.

        **A BUTTON ONLY WHERE THERE IS SOMETHING TO OPEN.** An inline picture
        is already drawn a few rows below; giving it an Open button would
        imply a second copy somewhere else. It is still LISTED, so the answer
        to "what can this result show me" is in one place rather than split
        between a list and a scroll.
        """
        while self._visuals_layout.count() > 1:
            item = self._visuals_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        found = declared_visualizations(report) if report is not None else ()
        self._visuals.setVisible(bool(found))
        for visual in found:
            self._visuals_layout.addWidget(self._visual_row(visual, report))

    def _visual_row(self, visual, report) -> QWidget:
        row = QWidget(self._visuals)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.addWidget(QLabel(visual.title, row), 1)
        layout.addWidget(QLabel(f"[{visual.kind}]", row))
        if visual.inline:
            # Named rather than left blank: a row with nothing on the right
            # reads as a control that failed to draw, which is the
            # empty-state confusion this reader already had to separate once.
            layout.addWidget(QLabel("shown below", row))
            return row
        button = QPushButton("Open", row)
        button.setProperty(_VISUAL_INDEX_PROPERTY, visual.index)
        button.setProperty(_VISUAL_REPORT_PROPERTY, str(getattr(report, "report_id", "") or ""))
        # A BOUND METHOD reading `sender()`, never a lambda capturing self:
        # PySide6 holds a plain callable strongly, and this codebase has paid
        # for that in five files.
        button.clicked.connect(self._on_visual_open_clicked)
        apply_help_tooltip(button, _VISUAL_OPEN_HELP)
        layout.addWidget(button)
        return row

    def _on_visual_open_clicked(self) -> None:
        button = self.sender()
        if button is None:
            return
        self.link_activated.emit(
            replace(
                _SPATIAL_ACTION,
                params={
                    "report_id": button.property(_VISUAL_REPORT_PROPERTY),
                    "annotation_index": button.property(_VISUAL_INDEX_PROPERTY),
                },
            )
        )

    def _on_selector_search_changed(self, _text: str) -> None:
        """Rebuild the list, and remember what was typed.

        The FOCUS is untouched: filtering narrows what you can pick, never
        what you are reading. `matching_reports` keeps the focused entry in
        the list whether or not it matches, so the control still names what
        it is currently doing -- a box that hid the current selection would
        show one report and name another.
        """
        self._rebuild_focus_box()
        self._remember()

    def _on_focus_changed(self, _index: int) -> None:
        self._focus = str(self._focus_box.currentData() or "")
        self._render()
        # A READER moving the control, which is the case the memory is for.
        self._remember()

    def _viewer_for(self, report) -> str:
        """Which viewer opens the whole of `report`, or "".

        **ASKED OF THE ENTRY, NEVER RE-DERIVED FROM ITS TYPE.** A summary
        carries the adapter's own answer; a `ReportResult` is already the
        whole thing and declares none, which is why `getattr` with an empty
        default is the right shape rather than a lookup that would have to
        decide what a report's viewer is.
        """
        return str(getattr(report, "rich_view", "") or "")

    def _on_open_clicked(self) -> None:
        """Ask for the whole result behind the focused summary.

        The link names the report rather than a fact, which is the difference
        between the two things this signal carries: a fact link says "where
        did this VALUE come from", and this says "show me the result this is
        a summary OF".
        """
        report = self._merged.report_for(self._focus) if self._focus else None
        if report is None:
            return
        target = self._viewer_for(report)
        if target not in _VIEWER_ACTIONS:
            return
        self.link_activated.emit(
            replace(_VIEWER_ACTIONS[target], params={"report_id": report.report_id})
        )

    def _sync_open_button(self, report) -> None:
        """Show the button only where there is something to open.

        Hidden rather than disabled: a disabled control invites a reader to
        wonder what would enable it, and for an entry that IS the whole
        result -- every `ReportResult` -- the honest answer is that nothing
        would. The "All results" view shows none either, because it is
        several producers at once and no one viewer owns it.
        """
        target = self._viewer_for(report) if report is not None else ""
        # **`in _VIEWER_ACTIONS`, NOT merely truthy.** A kind can declare a
        # viewer this window has no way to reach -- see the note on that
        # table -- and `bool(target)` would draw a button for it, labelled by
        # a fallback and answered by the router with "unknown target". A
        # control that cannot work is worse than an absent one.
        self._open_button.setVisible(target in _VIEWER_ACTIONS)
        if target in _VIEWER_ACTIONS:
            self._open_button.setText(_VIEWER_ACTIONS[target].label)

    def _render(self) -> None:
        state = reader_state(self._molecule_uuid, len(self._merged.reports))
        if state in EMPTY_MESSAGES:
            # NOT an empty FactView. "Nothing has been computed" and
            # "everything ran and had nothing to say" are different
            # statements, and an empty report makes the second one -- and
            # "no molecule is selected" is a third, which a reader that
            # follows the selection can be in and this window could not.
            self._empty.setText(EMPTY_MESSAGES[state])
            self._sync_open_button(None)
            self._sync_visualizations(None)
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
            self._sync_open_button(report)
            self._sync_visualizations(report)
            # **A FOCUSED REPORT OPENS OPEN, AND ALL RESULTS DOES NOT.**
            # `DEFAULT_EXPANDED` exists because "a hundred-odd facts
            # rendered flat is a wall" -- true of every producer at once,
            # and false of the one somebody just asked for. Focused on
            # Topology Analysis the reader showed a name and a folded
            # `Topology (27)`: the answer, one click away and invisible.
            #
            # Found by driving the app, exactly as the formulation report's
            # identical defect was, and fixed with the override written for
            # that one -- `set_report`'s own docstring already describes
            # this failure, which is what makes this a call site rather
            # than a mechanism.
            self._view.set_report(
                report,
                title,
                self._summary_for(report),
                expanded={fact.category for fact in report.facts},
            )
            return
        self._sync_open_button(None)
        self._sync_visualizations(None)
        self._view.set_report(
            summary_of_merge(self._merged, self._molecule_uuid),
            "All results",
            self._summary(),
        )

    def _summary(self) -> str:
        names = [
            self._merged.name_for(report.report_id) + (
                STALE_MARK if self._merged.is_stale(report) else ""
            )
            for report in self._merged.reports
        ]
        # **"result(s)", NOT "calculator(s)".** The always-on descriptor
        # aggregate is one of these entries and is explicitly NOT a
        # calculator -- it has no `calculator_id`, is never offered as
        # something to run, and never enters a cache key. Now that it sorts
        # first, the old wording named it as a calculator in the very first
        # thing a reader sees. Found by driving the app and reading the shot.
        return f"{len(names)} result(s): " + ", ".join(names)

    def _summary_for(self, report) -> str:
        """What to say above a focused report's facts.

        **A REPORT WITH NO FACTS NOW REACHES THIS WINDOW, AND "0 facts." IS
        NOT AN EXPLANATION.** `merge_reports` used to refuse one, so a refused
        Lewis Sites result -- `matched=[]`, `cache_state=FAILED` -- appeared
        here as nothing at all. Admitting it is only half the fix: without a
        reason it now appears as a calculator that ran and had nothing to say,
        which is a different and equally wrong statement.

        Status first, staleness after, and BOTH when both apply: a failed
        result computed against an older structure is two facts about it, and
        showing one would leave a reader to discover the other by surprise.
        """
        parts = [
            text
            for text in (
                self._status_line(report),
                self._verdict_line(report),
                self._empty_line(report),
                self._stale_line(report),
            )
            if text
        ]
        return " ".join(parts)

    def _empty_line(self, report) -> str:
        """Say that a SUCCESSFUL result produced nothing, rather than nothing.

        **"IT RAN AND FOUND NOTHING" AND "IT NEVER RAN" MUST NOT LOOK THE
        SAME**, and once the Properties panel stops rendering values this is
        where that distinction has to live. Measured: a clean catalogue
        reaches this window through `report_from_alert` with **no facts, no
        matched lines and no limitations** -- so focusing it showed a title
        and blankness, which is the "0 facts. is not an explanation" case
        this method's own docstring names, reached from a second direction.

        **IT DOES NOT SAY "CLEAN", AND `_verdict_line` DOES.** That is a
        verdict, and only a catalog is entitled to give one -- the rule
        `AlertResult.severity` exists to keep. This says what a reader can
        see for themselves is true of ANY successful result with nothing in
        it, and leaves the chemistry to whoever knows it; a catalog has a
        better sentence and takes it instead, which is why this stands aside
        when that one speaks.

        Nothing here fires for a failure or a refusal: those already have a
        status line saying more, and two sentences where one is enough is how
        a summary stops being read.
        """
        if self._status_line(report) or self._verdict_line(report):
            return ""
        if getattr(report, "facts", ()) or getattr(report, "charts", ()):
            return ""
        return "This ran and produced no values."

    def _verdict_line(self, report) -> str:
        """A CATALOG's verdict -- and only a catalog gets to give one.

        **THE SEVERITY USED TO STOP AT THE PANEL**, and once Properties
        stopped painting alerts this was the only renderer left. Measured
        before it was carried: a clean PAINS and an elemental analysis with
        no lines reached here BYTE-IDENTICAL -- no facts, no severity, no
        limitations -- so `_empty_line` said the same neutral sentence over
        both. That is precisely the confusion `AlertResult.severity` was
        introduced to end one layer along: its own docstring says the field
        exists so a renderer can tell "contains a PAINS substructure" from
        "weighs 43.025".

        **A MATCH COUNT, NEVER A RE-READING OF THE MATCHES.** The facts are
        rendered in full below this line; restating them here would be the
        third copy of one answer, which is the whole reason the panel's rows
        went. The count is a deterministic projection of declared data, and
        the verdict is the producer's, not this widget's.

        Silent for a failure or a refusal: those are not verdicts about the
        molecule, and `_status_line` already says more than this could.
        """
        if self._status_line(report):
            return ""
        # Declared, never guessed from the id -- `is_catalog`'s rule, applied
        # to the report the alert was converted into.
        if getattr(report, "severity", Severity.INFO) is Severity.INFO:
            return ""
        matches = len(getattr(report, "facts", ()))
        if not matches:
            return "Checked, nothing flagged."
        return f"{matches} alert(s) matched."

    def _status_line(self, report) -> str:
        """The failure or refusal, in the reader's own words.

        `describe_failure` owns which string is the short form and which is
        the full one, so this does not re-decide it -- the HOVER form is right
        here, because a summary line above a report has room for a sentence
        where a 120 px table cell does not. The Properties panel's spanning
        row used to make the same call for the same reason; 2c removed it,
        and this is now the only surface in the application with room for
        the long form.

        **A REFUSAL IS NOT A FAULT**, and the existing `inapplicable` field is
        what separates them rather than a second vocabulary invented here: the
        method not covering this molecule is a correct, permanent answer, and
        painting it as a crash is what made two working calculators read as
        broken.
        """
        if getattr(report, "cache_state", None) is not CacheState.FAILED:
            return ""
        _cell, reason = describe_failure(
            getattr(report, "error", None), getattr(report, "error_summary", None)
        )
        lead = "Not applicable" if getattr(report, "inapplicable", False) else "This did not run"
        return f"{lead}: {reason}"

    def _stale_line(self, report) -> str:
        return (
            "Computed for an earlier version of this structure -- re-run it "
            "to refresh."
            if self._merged.is_stale(report)
            else ""
        )
