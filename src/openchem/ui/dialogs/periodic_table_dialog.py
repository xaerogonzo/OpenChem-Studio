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

Colour marks category, and never carries a fact on its own -- the category
is written out in the detail pane and in every cell's tooltip, because a
grid distinguishing ten categories by hue alone is unreadable to a fair
number of people.

Where something is not known it says so. Oganesson has been made a few
atoms at a time; "common oxidation states: not established" is the true
answer and a blank row would read as a bug.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.atom_diagram import AtomDiagram
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Periodic Table")
        self.setModal(False)
        self._selected: str = ""
        self._buttons: dict[str, QToolButton] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_grid())
        layout.addWidget(self._build_legend())

        # The drawing sits ABOVE the facts table rather than below it: the
        # configuration string in that table is the same information, and
        # a picture that explains a line of text belongs beside it rather
        # than after everything else.
        self._diagram = AtomDiagram(self)
        self._diagram.setMinimumHeight(240)
        layout.addWidget(self._diagram)

        self._detail = QLabel("Select an element.", self)
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.TextFormat.RichText)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_area = QScrollArea(self)
        detail_area.setWidgetResizable(True)
        detail_area.setWidget(self._detail)
        detail_area.setMinimumHeight(190)
        layout.addWidget(detail_area, 1)

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
        fill, label = _CATEGORY_STYLE.get(facts.category, ("#eeeeee", facts.category))
        button = QToolButton(self)
        button.setText(f"{facts.atomic_number}\n{facts.symbol}")
        button.setFixedSize(46, 42)
        button.setToolTip(f"{facts.name} — {label}")
        button.setStyleSheet(
            f"QToolButton {{ background: {fill}; border: 1px solid #999; "
            f"font-size: 9px; color: #111; }}"
            f"QToolButton:checked {{ border: 2px solid #000; font-weight: bold; }}"
        )
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

    def _build_legend(self) -> QWidget:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        for category, (fill, label) in _CATEGORY_STYLE.items():
            swatch = QLabel(f" {label} ", container)
            swatch.setStyleSheet(f"background: {fill}; border: 1px solid #999; font-size: 9px;")
            row.addWidget(swatch)
        row.addStretch(1)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return container

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
        _row("Typical valences", _valence_text(facts)),
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


def _valence_text(facts: ElementFacts) -> str:
    """Why there is no valence list, which differs by element.

    75 elements report none. For 73 of them -- every transition metal, both
    f-block series -- that is a real statement about metals, and the same
    one the valence checker acts on when it declines to do octet arithmetic
    on iron oxides. The other two are tennessine and oganesson, where
    nothing is tabulated because almost nothing is known, and calling those
    "normal for a metal" would be wrong twice over.
    """
    if facts.valences:
        return ", ".join(str(v) for v in facts.valences)
    if facts.category in _METALLIC:
        return "no defined valence (normal for a metal)"
    return "no defined valence is tabulated for this element"


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
