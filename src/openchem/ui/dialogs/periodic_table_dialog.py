"""The periodic table: one of them, that answers questions AND draws.

**THERE USED TO BE TWO, AND THAT WAS THE BUG.** Ketcher ships its own,
and the split looked principled -- Ketcher's inserts atoms and belongs to
the canvas, this one is a reference under Tools. In the product it read
as a single table that had lost half its features, depending which door
you came through: the editor's `PT` button gave a plain grid with no
facts, and reported as "the periodic table reverted to vanilla".

The editor's button is intercepted now (`tools/ketcher-host/src/main.jsx`)
and answered with this dialog, so there is one table however you reach
it. It gained "Insert into drawing" in the same move, because taking a
button over without taking its job over is just breaking the button.

What Ketcher's could do and this cannot is QUERY atoms -- any-atom, and
list/not-list. That is named on the dialog itself rather than quietly
dropped; the editor's own tools still draw them.

The detail pane is the reason this table exists at all -- selecting an
element shows its configuration, radii, electronegativity, the oxidation
states it is actually found in, and its naturally occurring isotopes with
abundances. That last one is the part Marvin's own table does not really
do, and it came free: RDKit's periodic table carries the full abundance
data.

**IT IS TABBED, because those facts were being squeezed off the bottom.**
Grid, legend, a 240 px atom drawing, the electron controls and the facts
table shared one vertical stack, and the facts are what gave way. Facts
and Atom are separate tabs now and neither can take the other's height.
The grid stays outside them: it is the navigation, and switching what you
are reading should not move what you click.

Colour marks category, and never carries a fact on its own -- the category
is written out in the detail pane and in every cell's tooltip, because a
grid distinguishing ten categories by hue alone is unreadable to a fair
number of people.

Where something is not known it says so. Oganesson has been made a few
atoms at a time; "common oxidation states: not established" is the true
answer and a blank row would read as a bug.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.atom_diagram import AtomDiagram
from openchem.ui.widgets.collapsible_section import WrappedLabel
from openchem.chem import element_palettes as palettes
from openchem.chem import nuclides as nuclide_data
from openchem.chem.decay import decay_tree, format_branching, format_mode
from openchem.chem.decay_svg import legend_lines, render_decay_svg
from openchem.ui.widgets.zoomable_svg_view import ZoomableSvgView
from openchem.chem.element_reference import ElementFacts, all_symbols, facts_for, grid_position

#: Category -> (fill, human label). Muted fills so black symbol text stays
#: legible on every one of them.
_CATEGORY_STYLE: dict[str, tuple[str, str]] = {
    "nonmetal": ("#cfe8cf", "Nonmetal"),
    "noble_gas": ("#d9d2e9", "Noble gas"),
    "halogen": ("#ffe9b3", "Halogen"),
    "alkali": ("#f4c7c3", "Alkali metal"),
    "alkaline_earth": ("#f8ddb0", "Alkaline earth metal"),
    "metalloid": ("#cfe2f3", "Metalloid"),
    "transition": ("#dfe3e6", "Transition metal"),
    "post_transition": ("#e6e0d4", "Post-transition metal"),
    "lanthanide": ("#f6d9ec", "Lanthanide"),
    "actinide": ("#f2ccd6", "Actinide"),
}

#: Fills for the discrete palettes. Muted, so black symbol text stays
#: legible on every one of them.
_BLOCK_STYLE: dict[str, tuple[str, str]] = {
    "s": ("#f4c7c3", "s-block"),
    "p": ("#cfe8cf", "p-block"),
    "d": ("#cfe2f3", "d-block"),
    "f": ("#f6d9ec", "f-block"),
}

_STATE_STYLE: dict[str, tuple[str, str]] = {
    "solid": ("#e6e0d4", "Solid"),
    "liquid": ("#cfe2f3", "Liquid"),
    "gas": ("#f8ddb0", "Gas"),
    "sublimes": ("#dfd0ea", "Sublimes"),
    "not established": (_UNSET_FILL := "#efefef", "Not established"),
}

#: **RED FOR "no stable isotope", WHICH IS WHAT ALEX ASKED FOR** -- and
#: the third class is grey rather than a paler red, because "nobody has
#: established this" is not a weaker version of "radioactive".
_STABILITY_STYLE: dict[str, tuple[str, str]] = {
    palettes.STABLE_CLASS: ("#d7ead7", "Has a stable isotope"),
    "radioactive only": ("#f0b3b3", "No stable isotope"),
    palettes.UNESTABLISHED_CLASS: ("#efefef", "Not established"),
}

#: **THE ONE DISCRETE MODE THAT PRINTS ITS CLASS IN THE CELL**, and the
#: reason is the colours: this is the only mode whose whole content is a
#: RED/GREEN binary, which is the canonical failure case for the
#: commonest forms of colour blindness. Every other discrete mode spreads
#: its classes over four or ten hues, where confusing two of them costs a
#: reader one element rather than the entire picture.
#:
#: "stable" and "decays" rather than "stable" and "unstable": at 9 px two
#: words differing by two leading letters are a misreading waiting to
#: happen, and the pair has to be legible at exactly the size that makes
#: the colour unreliable.
_STABILITY_CELL_TEXT: dict[str, str] = {
    palettes.STABLE_CLASS: "stable",
    "radioactive only": "decays",
    palettes.UNESTABLISHED_CLASS: "—",
}

#: The half-life ramp's terminal swatches. The stable one is the SAME
#: green the stability mode uses, so switching between the two modes
#: reads as one question asked two ways rather than as two unrelated
#: pictures.
_HALF_LIFE_TERMINAL: dict[str, str] = {
    palettes.STABLE_CLASS: "#d7ead7",
    palettes.UNESTABLISHED_CLASS: "#efefef",
}

#: The two ends of every heatmap ramp. Light throughout, because the
#: symbol and the value are printed in black on top of it -- a ramp that
#: reaches a dark end would make its own labels unreadable exactly where
#: the value is largest.
_RAMP_LOW = (250, 250, 232)
_RAMP_HIGH = (86, 141, 190)

#: A half-life that is a bound, an estimate or an approximation.
_QUALIFIED_COLOUR = QColor("#8a5a00")
_MUTED_NOTE = "color: #666666; font-size: 9px;"

_UNKNOWN = "not established"

#: Qt property carrying which element a grid cell stands for.
_SYMBOL_PROPERTY = "openchem_element_symbol"


class PeriodicTableDialog(QDialog):
    """The table, plus everything known about whichever element is selected."""

    #: An element was chosen for the drawing canvas. Carries the symbol
    #: rather than acting, so this dialog needs to know nothing about the
    #: editor -- `MainWindow` owns that wiring, and the dialog stays
    #: constructible in a test with no editor anywhere.
    insert_requested = Signal(str)

    #: An isotope was chosen for the SELECTED atom. Carries the element,
    #: the mass number and whether the write covers every atom of that
    #: element. Like `insert_requested` it acts on nothing itself --
    #: `MainWindow` owns the write, so this dialog stays constructible in
    #: a test with no editor anywhere.
    isotope_requested = Signal(str, int, bool)

    #: A nuclide was picked off the decay chart. `insert_requested`
    #: fires first with the bare element, so a window that knows
    #: nothing about isotopes still does the useful half.
    nuclide_insert_requested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Periodic Table")
        self.setModal(False)
        self._selected: str = ""
        self._buttons: dict[str, QToolButton] = {}
        self._palette_key: str = palettes.PALETTE_ORDER[0]

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_palette_row())
        layout.addWidget(self._build_grid())
        layout.addWidget(self._build_legend())
        self._repaint_cells()

        # **THE DETAIL IS TABBED, AND THE FACTS TABLE IS WHY.** The grid,
        # the legend, a 240 px atom drawing, the electron controls and the
        # facts all used to compete for one vertical stack about 970 px
        # tall, and the facts lost: `Radii`, `Naturally occurring
        # isotopes` and `Found in` were below the fold in both of the
        # screenshots this branch came from.
        #
        # The GRID stays outside the tabs because it is the navigation --
        # switching what you are reading about an element should not move
        # the thing you click to choose one.
        self._diagram = AtomDiagram(self)
        self._diagram.setMinimumHeight(240)

        # **A PLAIN `QLabel` HERE CLIPS THE LAST ROW, and the tab is what
        # made it visible.** A wrapped QLabel reports a ONE-LINE minimum
        # however much text it holds, and a `setWidgetResizable` scroll
        # area sizes its child to `max(viewport, minimum)` -- so the label
        # was handed the viewport height and the overflow was simply not
        # reachable. Measured the moment the facts got room to breathe:
        # 373 px of viewport against a 382 px table, with the scrollbar
        # showing nothing to scroll.
        #
        # `WrappedLabel` is this project's existing cure and its docstring
        # describes this exact situation -- a wrapped label inside a
        # resizable scroll area. Reused rather than paralleled, which is
        # this codebase's most repeatable mistake.
        self._detail = WrappedLabel("Select an element.", self)
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.TextFormat.RichText)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._detail_area = QScrollArea(self)
        self._detail_area.setWidgetResizable(True)
        self._detail_area.setWidget(self._detail)
        self._detail_area.setMinimumHeight(190)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._detail_area, "Facts")
        self._tabs.addTab(self._diagram, "Atom")
        self._tabs.addTab(self._build_isotopes_tab(), "Isotopes")
        self._tabs.addTab(self._build_decay_tab(), "Decay")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        # A QDialog gets neither by default, so a window that opened too
        # tall could not be shrunk, moved back or maximised -- reported as
        # "there is no way to adjust the size of the periodic table
        # popup", alongside the buttons being off the bottom.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setSizeGripEnabled(True)
        self._fit_to_screen()
        layout.addWidget(self._tabs, 1)

        # THIS IS NOW THE ONLY PERIODIC TABLE THE PRODUCT OFFERS, so it
        # has to be able to draw as well as explain. The editor's own `PT`
        # button is intercepted and answered with this dialog (see
        # `tools/ketcher-host/src/main.jsx`), which means the previous
        # arrangement -- a reference table here, an insertion table there,
        # and a line of text pointing from one to the other -- is gone.
        #
        # It was a reasonable split and it did not survive contact: two
        # tables that look alike and know different things read as one
        # table that has lost half its features.
        #
        # Insertion ARMS THE CANVAS rather than placing an atom
        # immediately, because that is the gesture Ketcher's own table
        # performs and the one the canvas is built around -- pick an
        # element, then click where it goes. Inserting at some chosen
        # coordinate would be a second way for an atom to appear.
        buttons = QHBoxLayout()
        self._insert_button = QPushButton("Insert into drawing", self)
        self._insert_button.setToolTip(
            "Arm the 2D editor with this element, then click the canvas to place it."
        )
        self._insert_button.clicked.connect(self._insert_symbol)
        buttons.addWidget(self._insert_button)
        self._copy_button = QPushButton("Copy symbol", self)
        self._copy_button.clicked.connect(self._copy_symbol)
        buttons.addWidget(self._copy_button)
        # QUERY ATOMS ARE NOT HERE AND THE TABLE SAYS SO. Ketcher can draw
        # a list/not-list query atom and this dialog has no way to express
        # one (measured: `atomList` appears 149 times in the vendored
        # bundle, "Not List" twice). Naming the gap is the honest half of
        # taking the button over -- silently dropping a capability is how
        # a consolidation turns into a regression.
        buttons.addWidget(
            QLabel("For query atoms (any-atom, lists), use the 2D editor's own tools.", self)
        )
        buttons.addStretch(1)
        close = QPushButton("Close", self)
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.select("C")

    # --- construction -------------------------------------------------------

    def _build_grid(self) -> QWidget:
        container = QWidget(self)
        grid = QGridLayout(container)
        grid.setSpacing(2)

        for symbol in all_symbols():
            facts = facts_for(symbol)
            if facts is None:
                continue
            position = grid_position(symbol)
            if position is not None:
                row, column = position
                grid.addWidget(self._cell(facts), row - 1, column - 1)

        # The f-block, in its own two rows below the table. This placement
        # is a drawing convention rather than a property of the elements,
        # which is why `grid_position` declines to invent a column for it.
        for offset, category in ((0, "lanthanide"), (1, "actinide")):
            series = [s for s in all_symbols() if facts_for(s).category == category]
            for column, symbol in enumerate(series):
                grid.addWidget(self._cell(facts_for(symbol)), 8 + offset, column + 2)

        grid.addWidget(QLabel(""), 7, 0)  # a blank row before the f-block
        return container

    def _cell(self, facts: ElementFacts) -> QToolButton:
        button = QToolButton(self)
        # Tall enough for a third line, permanently: a cell that changed
        # size with the colour mode would jump the whole grid on every
        # switch, and the value line only exists in the heatmap modes.
        button.setFixedSize(46, 50)
        button.setCheckable(True)
        # A bound method, never a lambda capturing `self`: PySide6 holds a
        # connected plain callable strongly and a QObject's bound method
        # weakly, so the lambda form roots this object for the life of the
        # process -- past refcounting AND past the cyclic collector. See
        # property_panel._section_for for the measurement.
        button.setProperty(_SYMBOL_PROPERTY, facts.symbol)
        button.clicked.connect(self._on_cell_clicked)
        self._buttons[facts.symbol] = button
        return button

    #: What the dialog's MINIMUM size may be. Measured, not chosen: the
    #: element grid alone demands 880x502 and the tallest tab page (Atom)
    #: another 238, which with the palette row, the legend and the action
    #: row comes to 902x922.
    #:
    #: **A 1366x768 LAPTOP STILL CANNOT SHOW ALL OF IT**, and that is a
    #: stated limit rather than a fixed one: getting under ~728 means
    #: shrinking or scrolling the periodic grid itself, which is the
    #: primary content. It is pre-existing -- this dialog was ~880 tall
    #: before the Decay tab existed -- and the regression that made the
    #: action row unreachable on a 1032 px screen is what this bound
    #: guards against returning.
    #: Height only: width is a claim about the font, and this suite's
    #: `offscreen` platform measures the same dialog at 1288 px against
    #: 902 in the running application.
    MAX_MINIMUM_HEIGHT = 960

    def _fit_to_screen(self) -> None:
        """Open no larger than the screen can actually show.

        **THE CAP COMES FROM THE SCREEN, NOT FROM `self.size()`**, which
        during construction is Qt's pre-show default rather than anything
        real -- the same trap `initial_right_dock_width` records.

        This is a convenience; the CORRECTNESS is that the MINIMUM size
        fits, because `resize()` is clamped to it. A dialog whose minimum
        exceeds the screen cannot be rescued by resizing, which is exactly
        how the action row ended up unreachable.

        The arithmetic is in `fit_within` for the same reason
        `initial_right_dock_width` is a pure function: `offscreen` reports
        an 800x800 screen, so under the suite this call and its deletion
        are indistinguishable by outcome. Deleting the CALL is the one
        mutation nothing catches, and that is written into the guard
        rather than papered over.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - no display
            return
        available = screen.availableGeometry()
        hint = self.sizeHint()
        self.resize(
            *fit_within(
                hint.width(), hint.height(), available.width(), available.height()
            )
        )

    # --- the isotopes ---------------------------------------------------------

    #: What each column holds. The header is the contract.
    _ISOTOPE_COLUMNS = ("Isotope", "Abundance", "Half-life", "Decay modes", "Spin/parity")

    def _build_isotopes_tab(self) -> QWidget:
        """Every ground state of the selected element, in a declared order.

        **THIS IS THE PART MARVIN'S OWN TABLE DOES NOT REALLY DO**, and
        the reason the whole nuclide table was worth shipping: setting an
        isotope used to mean typing a mass number into Ketcher's Atom
        Properties with nothing on screen to say whether it exists, how
        long it lasts, or how much of it is out there.
        """
        container = QWidget(self)
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)

        self._isotope_table = QTableWidget(0, len(self._ISOTOPE_COLUMNS), container)
        self._isotope_table.setHorizontalHeaderLabels(self._ISOTOPE_COLUMNS)
        self._isotope_table.verticalHeader().setVisible(False)
        self._isotope_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._isotope_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._isotope_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._isotope_table.itemSelectionChanged.connect(self._refresh_isotope_button)
        # The decay column absorbs the slack: it is the widest and the
        # most informative, and letting Spin/parity stretch instead would
        # give three characters the whole pane.
        header = self._isotope_table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        column.addWidget(self._isotope_table, 1)

        # **A MEASURED VALUE AND A BOUND MUST NOT READ ALIKE**, so the
        # note says what the marks mean rather than leaving `> 4.6 zs` to
        # be read as a number somebody measured.
        self._isotope_note = QLabel(
            "&gt; and &lt; are bounds, ~ is approximate, and (estimated) means the "
            "value comes from systematics rather than measurement. A branching "
            "marked (unconfirmed) is a decay nobody has quantified.",
            container,
        )
        self._isotope_note.setWordWrap(True)
        self._isotope_note.setStyleSheet("font-size: 9px; color: #444444;")
        column.addWidget(self._isotope_note)

        row = QHBoxLayout()
        self._isotope_button = QPushButton("Apply to selected atom", container)
        self._isotope_button.clicked.connect(self._request_isotope)
        row.addWidget(self._isotope_button)
        # **ONE ATOM IS THE DEFAULT AND THE OPT-IN IS EXPLICIT.** Labelling
        # a single position is the ordinary case -- a tracer, one
        # deuterium -- and "every carbon in the molecule" is a different
        # enough thing to be asked for rather than assumed. It is still
        # ONE undo entry either way.
        self._isotope_all = QCheckBox("all atoms of this element", container)
        row.addWidget(self._isotope_all)
        self._isotope_hint = QLabel("", container)
        self._isotope_hint.setStyleSheet(_MUTED_NOTE)
        row.addWidget(self._isotope_hint)
        row.addStretch(1)
        column.addLayout(row)

        self._isotope_all.toggled.connect(self._refresh_isotope_button)
        self._selected_atom: tuple[str, int] | None = None
        self._refresh_isotope_button()
        return container

    def set_selected_atom(self, symbol: str | None, index: int = -1) -> None:
        """Tell the table which atom, if any, a write would land on.

        **The dialog does not go looking.** It is non-modal and reachable
        with no molecule open at all, so the window that owns the editor
        pushes this in -- the same reason `insert_requested` carries a
        symbol rather than touching a canvas.
        """
        self._selected_atom = (symbol, index) if symbol else None
        self._refresh_isotope_button()

    def selected_isotope(self) -> int | None:
        """The mass number of the highlighted row, or None."""
        rows = self._isotope_table.selectionModel()
        if rows is None or not rows.selectedRows():
            return None
        item = self._isotope_table.item(rows.selectedRows()[0].row(), 0)
        return None if item is None else int(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_isotope_button(self) -> None:
        """Enabled only when every part of the question has an answer.

        **DISABLED WITH A REASON, never guessing a target.** Three
        different things can be missing and they need three sentences: no
        atom picked on the canvas, no row picked here, or -- the one that
        matters -- a row belonging to a DIFFERENT element from the atom.

        That last case is a trap this table would otherwise set. The
        periodic table is a browsing tool, so somebody can easily be
        reading carbon's isotopes with an oxygen selected; pressing the
        button then took the element from the atom and the mass number
        from the table and quietly offered O-14, which is a real nuclide
        and not the one on screen. Requiring them to agree makes that
        unexpressible rather than merely validated later.
        """
        mass_number = self.selected_isotope()
        if self._selected_atom is None:
            self._isotope_button.setEnabled(False)
            self._isotope_hint.setText("Select an atom in the 2D editor first.")
            return
        symbol, _index = self._selected_atom
        self._isotope_all.setText(f"all {symbol} atoms")
        if symbol != self._selected:
            self._isotope_button.setEnabled(False)
            self._isotope_hint.setText(
                f"Showing {self._selected}; the selected atom is {symbol}. "
                f"Choose {symbol} in the table above."
            )
            return
        if mass_number is None:
            self._isotope_button.setEnabled(False)
            self._isotope_hint.setText("Choose an isotope above.")
            return
        self._isotope_button.setEnabled(True)
        scope = f"every {symbol}" if self._isotope_all.isChecked() else "the selected atom"
        self._isotope_hint.setText(f"Will apply {symbol}-{mass_number} to {scope}.")

    def _request_isotope(self, _checked: bool = False) -> None:
        """**THE ELEMENT COMES FROM THE SELECTED ATOM, not from this
        table.** Somebody can be reading carbon's isotopes with an oxygen
        selected, and applying C-13 to every oxygen is the mistake that
        rule exists to prevent."""
        mass_number = self.selected_isotope()
        if self._selected_atom is None or mass_number is None:
            return
        symbol, _index = self._selected_atom
        if symbol != self._selected:
            return
        self.isotope_requested.emit(symbol, mass_number, self._isotope_all.isChecked())

    def _refresh_isotopes(self) -> None:
        table = self._isotope_table
        table.clearContents()
        found = nuclide_data.isotope_order(nuclide_data.nuclides_for(self._selected))
        table.setRowCount(len(found))
        for row, entry in enumerate(found):
            half_life = nuclide_data.format_half_life(entry.half_life)
            decays = ", ".join(
                f"{format_mode(d.mode)} {format_branching(d.branching, d.qualifier)}".strip()
                for d in entry.decays
            )
            abundance = (
                f"{entry.abundance:g}%" if entry.abundance is not None else "—"
            )
            cells = (entry.name, abundance, half_life, decays or "—", entry.jpi or "—")
            for index, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.a)
                table.setItem(row, index, item)
            if entry.half_life.is_qualified:
                # Reinforcement only: the text already carries the mark,
                # which is this table's rule that colour never says
                # anything on its own.
                table.item(row, 2).setForeground(_QUALIFIED_COLOUR)
                table.item(row, 2).setToolTip(
                    "Not an exact measurement -- see the note below the table."
                )
        table.resizeColumnsToContents()
        self._refresh_isotope_button()

    # --- the decay chain ------------------------------------------------------

    def _build_decay_tab(self) -> QWidget:
        """Where the selected isotope ends up, drawn on the chart of the
        nuclides.

        "this wouldn't be so much for practical uses, but it would just be
        fun to look at, and educational too" -- so the layout is the one
        every textbook uses (neutrons across, protons up), which makes an
        alpha step a fixed diagonal and a beta step a fixed short hop.
        The uranium-238 series comes out as the staircase it is drawn as
        in books, rather than as whatever a graph layout settled on.
        """
        container = QWidget(self)
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)

        # **A MINIMUM IS A FLOOR, NOT A PREFERRED SIZE**, and copying the
        # Lewis dialog's 520x360 was the regression. There that view is
        # the entire content of its own window; here it sits under a
        # 502 px element grid, and `QTabWidget` takes the MAXIMUM over its
        # pages -- so one tab's comfort became the whole dialog's floor
        # and pushed the action row 105 px below the bottom of a 1032 px
        # screen, with no maximise button and no size grip to get it back.
        #
        # The chart zooms and scrolls, so it loses nothing by being
        # allowed to get small; the dialog OPENS far larger than this.
        self._decay_view = ZoomableSvgView(container, minimum_size=(320, 140))
        column.addWidget(self._decay_view, 1)

        self._decay_status = QLabel("", container)
        self._decay_status.setWordWrap(True)
        column.addWidget(self._decay_status)

        self._decay_legend = QLabel("", container)
        self._decay_legend.setWordWrap(True)
        self._decay_legend.setStyleSheet("font-size: 9px; color: #444444;")
        column.addWidget(self._decay_legend)

        row = QHBoxLayout()
        self._decay_insert = QPushButton("Insert this nuclide into drawing", container)
        self._decay_insert.clicked.connect(self._insert_decay_nuclide)
        row.addWidget(self._decay_insert)
        self._decay_hint = QLabel("", container)
        self._decay_hint.setStyleSheet(_MUTED_NOTE)
        row.addWidget(self._decay_hint)
        row.addStretch(1)
        column.addLayout(row)

        self._decay_focus: tuple[int, int] | None = None
        self._decay_diagram = None
        self._decay_view._view.installEventFilter(self)
        return container

    def _on_tab_changed(self, _index: int) -> None:
        """Re-fit the chart when its tab is actually shown.

        **A ZOOM COMPUTED AGAINST AN UNSHOWN VIEWPORT IS NOT A FIT.**
        `_refresh_decay` runs from `select`, which happens while another
        tab is current, so `zoom_to_fit` measured a viewport Qt had not
        laid out and clamped to the 25% floor -- a 2320 px chart drawn a
        quarter size in a 1265 px pane, which is exactly the "squeezed
        into whatever was left" the zoom view exists to prevent.
        """
        if self._tabs.tabText(self._tabs.currentIndex()) == "Decay":
            self._decay_view.zoom_to_fit()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt's name
        """A click on the chart selects the nuclide under it.

        **HIT-TESTED AGAINST THE RENDERER'S OWN PLACED BOXES**, scaled by
        the current zoom -- never against a second layout computed here.
        Two implementations of one layout is where a click starts landing
        on the wrong thing, which this project has already paid for once
        in Ketcher's pool ids.
        """
        if (
            self._decay_diagram is not None
            and watched is self._decay_view._view
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            zoom = self._decay_view.zoom() or 1.0
            position = event.position()
            node = self._decay_diagram.node_at(position.x() / zoom, position.y() / zoom)
            if node is not None:
                self._focus_decay_node(node.z, node.a)
                return True
        return super().eventFilter(watched, event)

    def decay_focus(self) -> tuple[int, int] | None:
        """(Z, A) of the nuclide the chain is currently describing."""
        return self._decay_focus

    def _refresh_decay(self) -> None:
        """Redraw for the element's longest-lived isotope.

        **THE LONGEST-LIVED ONE, not the most abundant**, because a stable
        nuclide has no chain to draw and picking it would answer every
        ordinary element with an empty picture. Carbon opens on C-14.
        """
        found = nuclide_data.nuclides_for(self._selected)
        radioactive = nuclide_data.longest_radioactive_isotope(self._selected)
        start = radioactive or (found[0] if found else None)
        if start is None:
            self._decay_view.set_content_visible(False)
            self._decay_status.setText(
                f"No nuclide of {self._selected} is in the table."
            )
            self._decay_legend.setText("")
            self._decay_focus = None
            self._decay_diagram = None
            self._refresh_decay_button()
            return
        self._focus_decay_node(start.z, start.a)

    def _focus_decay_node(self, z: int, a: int) -> None:
        start = nuclide_data.nuclide(z, a)
        if start is None:  # pragma: no cover - only a stale click could
            return
        tree = decay_tree(start)
        diagram = render_decay_svg(tree)
        self._decay_diagram = diagram
        self._decay_focus = (z, a)
        self._decay_view.set_content_visible(True)
        self._decay_view.load(diagram.svg)
        self._decay_view.zoom_to_fit()

        # **"ENDS AT" WAS THE WRONG QUESTION, and the rendered chart is
        # what showed it.** `leaves()` answers "which nodes have nothing
        # leading out of them", and for uranium-238 that gave Hg-200,
        # Hg-202 and Tl-205 -- omitting Pb-206, which is where every
        # textbook says the series ends.
        #
        # The cause is a real wrinkle in NUBASE rather than a bug here:
        # Pb-204, Pb-206, Pb-208 and Hg-204 are marked `stbl` AND carry a
        # predicted decay nobody has ever observed (`A ?`, `2B- ?`), so
        # they are stable and have an outgoing edge at the same time. The
        # useful statement is which stable nuclides the chain REACHES.
        stable = sorted(n.name for n in tree.nodes.values() if n.is_stable)
        reaches = (
            f"reaches {len(stable)} stable: {', '.join(stable)}"
            if stable
            else "reaches no stable nuclide"
        )
        self._decay_status.setText(
            f"{start.name} - {nuclide_data.format_half_life(start.half_life)} - "
            f"{tree.size} nuclides reachable, {reaches}. "
            "Click any box to follow the chain from there."
        )
        # Rich text, so each family is shown IN its own colour -- a legend
        # that names the encoding without demonstrating it leaves the
        # reader matching words to lines by guesswork.
        families = " \u00b7 ".join(
            f'<span style="color:{colour}">&#9644; {_escape_html(words)}</span>'
            for colour, words in legend_lines(diagram)
        )
        self._decay_legend.setText(
            "Neutrons across, protons up \u2014 the chart of the nuclides. "
            "Line weight is the branching ratio. " + families
            + ". <b>Ground states only</b>, so a chain that runs through an "
            "isomer is not drawn."
        )
        self._refresh_decay_button()

    def _refresh_decay_button(self) -> None:
        if self._decay_focus is None:
            self._decay_insert.setEnabled(False)
            self._decay_hint.setText("")
            return
        z, _a = self._decay_focus
        nuclide = nuclide_data.nuclide(*self._decay_focus)
        symbol = nuclide.symbol if nuclide is not None else ""
        self._decay_insert.setEnabled(bool(symbol))
        self._decay_hint.setText(
            f"Adds {nuclide.name} to the canvas." if nuclide is not None else ""
        )

    def _insert_decay_nuclide(self, _checked: bool = False) -> None:
        """**"You could obviously click one and paste it in the 2D
        editor"** -- a decay product is an element with a mass number, and
        that is exactly what a molfile can express.

        It reuses `insert_requested` rather than inventing a second door:
        the window already knows how to put an element on the canvas, and
        the isotope goes through the picker's own path afterwards.
        """
        nuclide = None if self._decay_focus is None else nuclide_data.nuclide(*self._decay_focus)
        if nuclide is None:
            return
        self.insert_requested.emit(nuclide.symbol)
        self.nuclide_insert_requested.emit(nuclide.symbol, nuclide.a)

    # --- colour modes -------------------------------------------------------

    def _fill_and_note(self, symbol: str) -> tuple[str, str, str]:
        """(fill, tooltip note, extra cell line) for the active mode."""
        key = self._palette_key
        if key in palettes.DISCRETE:
            group = palettes.class_for(key, symbol) or ""
            table = {
                "category": _CATEGORY_STYLE,
                "block": _BLOCK_STYLE,
                "state": _STATE_STYLE,
                "stability": _STABILITY_STYLE,
            }[key]
            fill, label = table.get(group, ("#eeeeee", group or _UNKNOWN))
            extra = _STABILITY_CELL_TEXT.get(group, "") if key == "stability" else ""
            return fill, label, extra

        if key in palettes.HYBRID:
            return self._half_life_cell(symbol)

        spec = palettes.CONTINUOUS[key]
        position = palettes.position_for(spec, palettes.value_for(key, symbol))
        shown = palettes.display_value(key, symbol)
        if position is None:
            # **NEVER THE BOTTOM OF THE SCALE.** Several elements have no
            # accepted electronegativity and fifteen no measured melting
            # point; colouring those "very low" would be the table
            # inventing data.
            return _UNSET_FILL, f"{spec.label}: {_UNKNOWN}", "—"
        return _ramp(position), f"{spec.label}: {shown} {spec.units}".strip(), shown

    def _half_life_cell(self, symbol: str) -> tuple[str, str, str]:
        """A ramp position OR a terminal swatch, never a blend of the two.

        **A QUALIFIED VALUE KEEPS ITS MARK.** Five of the thirty-eight
        elements on this ramp carry an ESTIMATED half-life -- moscovium,
        meitnerium, nihonium, nobelium and rutherfordium -- and the colour
        cannot say so, because the whole point of the ramp is that a
        colour means a magnitude. So the cell prints NUBASE's own trailing
        `#` and the tooltip spells it out, which is this table's existing
        rule that colour never carries a fact alone.
        """
        shading = palettes.half_life_shading(symbol)
        note = shading.note
        if shading.qualified:
            note += " - not an exact measurement"
        if shading.terminal is not None:
            return _HALF_LIFE_TERMINAL[shading.terminal], note, shading.display
        return _ramp(shading.position), note, shading.display

    def _repaint_cells(self) -> None:
        for symbol, button in self._buttons.items():
            facts = facts_for(symbol)
            fill, note, extra = self._fill_and_note(symbol)
            text = f"{facts.atomic_number}\n{facts.symbol}"
            if extra:
                text += f"\n{extra}"
            button.setText(text)
            button.setToolTip(f"{facts.name} — {note}")
            button.setStyleSheet(
                f"QToolButton {{ background: {fill}; border: 1px solid #999; "
                f"font-size: 9px; color: #111; }}"
                f"QToolButton:checked {{ border: 2px solid #000; font-weight: bold; }}"
            )

    def _on_palette_changed(self, index: int) -> None:
        """Recolour, and NOTHING ELSE.

        The selected element, the open tab and the detail text are all
        untouched: a colour mode says what the grid means, not what you
        are looking at. Tabs and modes are where accidental state coupling
        appears, so this is asserted rather than assumed.
        """
        self._palette_key = palettes.PALETTE_ORDER[index]
        self._repaint_cells()
        self._legend.setText(palettes.legend_for(self._palette_key))

    def _build_palette_row(self) -> QWidget:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel("Colour by:", container))
        self._palette_combo = QComboBox(container)
        for key in palettes.PALETTE_ORDER:
            self._palette_combo.addItem(palettes.label_for(key), key)
        self._palette_combo.currentIndexChanged.connect(self._on_palette_changed)
        row.addWidget(self._palette_combo)
        row.addStretch(1)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return container

    def _build_legend(self) -> QWidget:
        """One line, and it is SELF-CONTAINED.

        Property, range, transform, units and the not-established swatch
        are spelled out, so a screenshot of this table is readable without
        remembering which combo entry was active.
        """
        self._legend = QLabel(palettes.legend_for(self._palette_key), self)
        self._legend.setWordWrap(True)
        self._legend.setStyleSheet("font-size: 9px; color: #444444;")
        self._legend.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return self._legend

    # --- selection ----------------------------------------------------------

    def selected_symbol(self) -> str:
        return self._selected

    def select(self, symbol: str) -> None:
        facts = facts_for(symbol)
        if facts is None:
            return
        for other, button in self._buttons.items():
            button.setChecked(other == symbol)
        self._selected = symbol
        self._detail.setText(describe(facts))
        self._refresh_isotopes()
        self._refresh_decay()
        # Always back to neutral on a new element. Carrying a charge
        # across would silently answer a question about a different
        # species than the one just clicked.
        self._diagram.set_element(symbol, charge=0)

    def _on_cell_clicked(self, _checked: bool = False) -> None:
        button = self.sender()
        if button is not None:
            self.select(button.property(_SYMBOL_PROPERTY))

    def _copy_symbol(self) -> None:
        if self._selected:
            QGuiApplication.clipboard().setText(self._selected)

    def _insert_symbol(self, _checked: bool = False) -> None:
        """Hand the chosen element to whoever owns the canvas.

        The dialog stays OPEN. Somebody placing three heteroatoms should
        not have to reopen the table between each, and this window is
        non-modal precisely so it can be read while working.
        """
        if self._selected:
            self.insert_requested.emit(self._selected)


def _escape_html(text: str) -> str:
    """A legend built as rich text must not be able to carry markup.

    The words come from a table in `decay_svg`, so nothing hostile can
    reach here today -- but a label that silently interprets its input as
    HTML is the kind of thing that stops being true quietly.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


#: How much of the screen the table may claim when it opens. Not the
#: whole of it: a window flush against every edge is hard to move, and
#: the height leaves room for a title bar the geometry does not include.
_SCREEN_FRACTION = (0.95, 0.92)


def fit_within(
    width: int, height: int, available_width: int, available_height: int
) -> tuple[int, int]:
    """An opening size that fits the screen, as a pure function.

    Pure so it can be tested at all: the suite's `offscreen` platform
    reports an 800x800 screen, where this dialog's own minimum is larger
    still, so nothing observable distinguishes calling it from not.
    """
    return (
        min(width, int(available_width * _SCREEN_FRACTION[0])),
        min(height, int(available_height * _SCREEN_FRACTION[1])),
    )


def _ramp(position: float) -> str:
    """A light two-stop ramp, as a hex fill.

    Light at BOTH ends on purpose: the symbol and its value are printed
    in black on top, so a ramp reaching a dark end would hide its own
    labels exactly where the value is largest.
    """
    low, high = _RAMP_LOW, _RAMP_HIGH
    channels = [round(a + (b - a) * position) for a, b in zip(low, high)]
    return "#" + "".join(f"{c:02x}" for c in channels)


def describe(facts: ElementFacts) -> str:
    """The detail pane's text.

    A plain function so it can be tested without a dialog, and so what the
    table claims about an element is checkable against the element.
    """
    _, category_label = _CATEGORY_STYLE.get(facts.category, ("", facts.category))
    group = "f-block series" if facts.group is None else f"group {facts.group}"

    rows = [
        f"<h3>{facts.name} ({facts.symbol}) &mdash; {facts.atomic_number}</h3>",
        f"<p><b>{category_label}</b> &middot; {group} &middot; period {facts.period} "
        f"&middot; {facts.block}-block</p>",
        "<table cellpadding='3'>",
        # "(neutral atom)" because the diagram above can be showing an ION.
        # Iron beside Fe2+ reads as a contradiction otherwise -- [Ar] 3d6
        # 4s2 here against [Ar] 3d6 there -- when both are right about
        # different species. Saying so in the label keeps this table
        # independent of whatever the diagram is currently displaying,
        # which is better than teaching the two to talk to each other.
        _row("Electron configuration (neutral atom)", facts.electron_configuration),
        # .6g, not .4g: four significant figures renders uranium as "238"
        # and iron as "55.84", which is a reference table losing the
        # digits somebody opened it for.
        _row("Relative atomic mass", f"{facts.atomic_weight:.6g}"),
        _row("Outer electrons", str(facts.outer_electrons)),
        _row(
            "Electronegativity",
            f"{facts.electronegativity} (Pauling)"
            if facts.electronegativity is not None
            else "no accepted value",
        ),
        _row("Valence states RDKit will fill", _valence_text(facts)),
        _row(
            "Common oxidation states",
            ", ".join(_signed(state) for state in facts.common_oxidation_states)
            if facts.has_established_oxidation_states
            else _UNKNOWN,
        ),
        _row(
            "Radii",
            f"van der Waals {facts.van_der_waals_radius} &Aring;, "
            f"covalent {facts.covalent_radius} &Aring;",
        ),
        _row("Naturally occurring isotopes", _isotope_text(facts)),
    ]
    if facts.examples:
        rows.append(_row("Found in", ", ".join(facts.examples)))
    rows.append("</table>")
    return "".join(rows)


def _row(label: str, value: str) -> str:
    return f"<tr><td valign='top'><b>{label}</b></td><td>{value}</td></tr>"


def _signed(state: int) -> str:
    return "0" if state == 0 else f"{state:+d}"


#: The categories for which "no defined valence" is ordinary chemistry
#: rather than an absence of data.
_METALLIC = frozenset(
    {"alkali", "alkaline_earth", "transition", "post_transition", "lanthanide", "actinide"}
)


#: Said under the valence row, on every element. Verbose, and deliberately
#: so: without it the number reads as curated chemistry.
_VALENCE_CAVEAT = (
    "Used for implicit-hydrogen and valence checking, not a curated "
    "chemistry reference &mdash; see the oxidation states below."
)


def _valence_text(facts: ElementFacts) -> str:
    """RDKit's DEFAULT-VALENCE list, and why it is sometimes empty.

    **THIS ROW USED TO BE CALLED "Typical valences", WHICH IS A CLAIM THE
    NUMBER CANNOT SUPPORT.** It is `GetValenceList`, RDKit's model for
    deciding how many hydrogens an atom implies, and read as chemistry it
    is inconsistent across a group. Measured:

        Cl [1]      Br [1]      I [1, 3, 5]
        N  [3]      S  [2, 4, 6]     Xe [0, 2, 4, 6]

    So the table told a reader bromine has one typical valence and iodine
    three, when both do 1/3/5/7. The row is kept, because the
    application's own valence checker acts on this same list and a
    reference table that agrees with the checker is worth having -- but
    it is labelled as what it is, with the caveat attached rather than
    left to a softened noun.

    75 elements report none. For 73 of them -- every transition metal,
    both f-block series -- that is a real statement about metals, and the
    same one the valence checker acts on when it declines to do octet
    arithmetic on iron oxides. The other two are tennessine and
    oganesson, where nothing is tabulated because almost nothing is
    known, and calling those "normal for a metal" would be wrong twice
    over.
    """
    if facts.valences:
        listed = ", ".join(str(v) for v in facts.valences)
    elif facts.category in _METALLIC:
        listed = "no defined valence (normal for a metal)"
    else:
        listed = "no defined valence is tabulated for this element"
    return f"{listed}<br><span style='color:#666666'>{_VALENCE_CAVEAT}</span>"


def _isotope_text(facts: ElementFacts) -> str:
    """Abundances, or the reason there are none.

    "None" would be ambiguous between "we did not look" and "this element
    has no stable isotopes". Technetium and every element past bismuth are
    the second, and that is worth a sentence.
    """
    if not facts.isotopes:
        return "none &mdash; this element has no naturally occurring isotopes"
    return ", ".join(
        f"<sup>{isotope.mass_number}</sup>{facts.symbol} {isotope.abundance:.4g}%"
        for isotope in facts.isotopes
    )
