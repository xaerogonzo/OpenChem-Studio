"""There is ONE periodic table, and it can draw.

Ketcher ships its own on the editor toolbar; the application has a much
richer one under Tools. Two tables that look alike and know different
things read as one table that has lost half its features depending which
button you pressed -- reported, in those words, as "the periodic table no
longer shows all the atom drawing, it's reverted to vanilla". Neither
table was broken; there were simply two of them.

The editor's button is intercepted in `tools/ketcher-host/src/main.jsx`
and answered with this dialog, which gained "Insert into drawing" in the
same move. Taking a button over without taking its job over is just
breaking the button.

**The interception itself lives in the bundle and cannot be asserted
here.** `test_ketcher_bundle_is_current.py` already covers the half that
is checkable offline -- that `bridgeObject.periodicTableRequested()` in
the JSX has a matching `_Bridge` slot and appears in the committed dist.
The other half was verified in the running app, which is the only place
it can be: clicking the real button opened this dialog while Ketcher's
own stayed shut (`dialogs: 0, modals: 0`), and Insert armed the canvas
(`AtomTool2`).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from openchem.chem import element_palettes as palettes
from openchem.chem import nuclides as nuclide_data
from openchem.ui.widgets.help_tooltip import help_tooltip_for

from openchem.ui.dialogs.periodic_table_dialog import (
    CELL_LARGE,
    CELL_SMALL,
    PeriodicTableDialog,
    cell_size_for,
)
from openchem.ui.widgets.screen_fit import fit_within


@pytest.fixture
def dialog(qapp):
    built = PeriodicTableDialog()
    yield built
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


def test_an_element_cells_live_tooltip_still_carries_its_contract(dialog):
    """**THE FAILURE THIS CATCHES IS SILENT, 118 TIMES OVER.**

    Each cell's tooltip is rewritten on every recolour -- it names the
    element and whatever the current mode is showing -- so a plain
    `setToolTip` there would REPLACE the contract's text while leaving the
    contract attached as a Qt property. The coverage guard would go on
    reporting all 118 cells documented while the user read "Hydrogen --
    Nonmetal" and nothing saying what clicking one does.

    Exactly the failure `test_the_derive_buttons_live_tooltip_still_`
    `carries_its_contract` records for the docking panel, which is why
    the composition is asserted rather than the attachment.

    BOTH SIDES OF THE RECOLOUR, because `_repaint_cells` is the only
    place the composition happens and a heatmap mode builds its live half
    differently from a discrete one.
    """
    contract = help_tooltip_for(dialog._buttons["H"])
    assert contract is not None, "the cell carries no contract at all"

    for palette in ("category", "electronegativity"):
        dialog._palette_combo.setCurrentIndex(palettes.PALETTE_ORDER.index(palette))
        rendered = dialog._buttons["H"].toolTip()

        assert contract.text in rendered, (
            f"in the {palette!r} mode the live tooltip has replaced the "
            f"contract rather than carrying it: {rendered!r}"
        )
        assert "Hydrogen" in rendered, (
            f"the {palette!r} mode dropped the live half of the tooltip, "
            "which is the part that names what the colour is showing"
        )


def test_the_spin_parity_marks_are_explained_where_they_are_printed(dialog):
    """A tooltip is not enough for a mark that appears in the table.

    This project's own finding, one tab along: the half-life legend
    "explained no marks" while five cells printed a trailing `#`, because
    the meaning lived only in a tooltip -- and the legend is the part a
    screenshot carries.

    The spin/parity column prints three of them (1062 `*`, 948 `#`, 1328
    parenthesised, measured over the shipped table), so the note under the
    table has to name them. DERIVED FROM WHAT THE CELLS ACTUALLY PRINT
    rather than from a list: an element whose isotopes stopped carrying a
    mark would make this vacuous, so the marks found are asserted first.
    """
    dialog.select("Tc")
    table = dialog._isotope_table
    printed = {
        mark
        for row in range(table.rowCount())
        for mark in ("*", "#", "(")
        if mark in (table.item(row, 4).text() if table.item(row, 4) else "")
    }
    assert printed, "no spin/parity mark is printed, so this guard is vacuous"

    note = dialog._isotope_note.text()
    for mark, described in (("*", "directly measured"), ("#", "estimated"),
                            ("(", "bracket")):
        if mark in printed:
            assert described in note, (
                f"the table prints {mark!r} in spin/parity and the note "
                f"under it never says what that means: {note!r}"
            )


def test_insert_asks_for_the_selected_element(dialog):
    dialog.select("Na")
    seen: list[str] = []
    dialog.insert_requested.connect(lambda symbol, mass: seen.append(symbol))

    dialog._insert_button.click()

    assert seen == ["Na"]


def test_insert_follows_the_selection_rather_than_the_first_click(dialog):
    """A stale symbol would draw the wrong element, which is the quiet
    kind of wrong -- the canvas gets an atom, just not the one asked
    for. Two selections, so a handler pinned to the first fails."""
    seen: list[str] = []
    dialog.insert_requested.connect(lambda symbol, mass: seen.append(symbol))

    dialog.select("Na")
    dialog._insert_button.click()
    dialog.select("Fe")
    dialog._insert_button.click()

    assert seen == ["Na", "Fe"]


def test_the_dialog_stays_open_after_inserting(dialog):
    """Placing three heteroatoms should not mean reopening the table
    between each. It is non-modal for the same reason."""
    dialog.show()
    dialog.select("O")

    dialog._insert_button.click()

    assert not dialog.isHidden()


def test_the_query_atom_gap_is_named_on_the_dialog(dialog):
    """Ketcher's table can draw list/not-list query atoms and this one
    cannot -- measured, `atomList` appears 149 times in the vendored
    bundle. Consolidating onto this table drops that capability from the
    button, so the dialog SAYS so.

    A gap that is merely absent looks identical to one nobody noticed;
    this is the same reason `catches_composition_order: false` is written
    into the assembly gate rather than left out of it.
    """
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert "query atom" in text.lower()


def test_the_dialog_no_longer_points_at_a_second_table(dialog):
    """It used to say "use the periodic table in the 2D editor's
    toolbar", which is now this same dialog. A sentence sending somebody
    back to where they came from is worse than none."""
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog.findChildren(QLabel)).lower()

    assert "periodic table in the 2d editor" not in text


# --- B1: the detail is tabbed, and the facts stopped being squeezed ---------


def _tab_widgets(dialog) -> dict[str, object]:
    return {
        dialog._tabs.tabText(index): dialog._tabs.widget(index)
        for index in range(dialog._tabs.count())
    }


def test_the_facts_and_the_atom_view_cannot_take_each_others_height(dialog):
    """**THE ACTUAL BUG, stated as a test.**

    Not "a QTabWidget exists" -- that would pass with both panes still
    stacked inside one tab. What broke was that the grid, the legend, a
    240 px atom drawing, the electron controls and the facts table shared
    one vertical stack, and the facts are what gave way: `Radii`,
    `Naturally occurring isotopes` and `Found in` sat below the fold in
    both screenshots this branch came from.

    Two panes in two different tabs cannot compete for one height, which
    is a structural claim and holds at any window size -- unlike a
    measured pixel count, which in this project has disagreed with the
    running application six times.
    """
    tabs = _tab_widgets(dialog)

    # **NOT AN EXACT SET.** This asserted `{"Facts", "Atom"}` until the
    # Isotopes tab arrived, which is over-specification rather than a
    # claim: what matters is that each pane has a tab of its OWN, which
    # is what makes competing for one height impossible. Pinning the
    # whole set would fail for every future tab while catching nothing
    # the three assertions below miss.
    assert {"Facts", "Atom"} <= set(tabs)
    assert tabs["Facts"] is dialog._detail_area
    assert tabs["Atom"] is dialog._diagram
    assert len({id(widget) for widget in tabs.values()}) == len(tabs), (
        "two tabs share a widget, so one of them is not its own pane"
    )


def test_the_grid_is_not_inside_the_tabs(dialog):
    """The grid is the NAVIGATION. Switching what you are reading about an
    element must not move the thing you click to choose one."""
    for widget in _tab_widgets(dialog).values():
        assert not widget.isAncestorOf(next(iter(dialog._buttons.values())))


def test_the_whole_facts_table_is_reachable(dialog):
    """Every row, by scrolling if need be -- which is what a scroll area
    in a tab of its own buys and a squeezed pane did not."""
    dialog.select("Fe")
    dialog.resize(920, 900)
    dialog.show()
    QCoreApplication.processEvents()

    area = dialog._detail_area
    reachable = area.viewport().height() + area.verticalScrollBar().maximum()

    assert area.viewport().height() > 0
    assert reachable >= dialog._detail.sizeHint().height()
    assert "Found in" in dialog._detail.text(), "the last row is not even being built"


def test_selecting_an_element_is_independent_of_the_active_tab(dialog):
    """Tabs are where accidental state coupling appears.

    Switching Facts -> Atom -> Facts must leave polonium selected, and
    must not rebuild its facts into something else on the way back.
    """
    dialog.select("Po")
    before = dialog._detail.text()

    dialog._tabs.setCurrentIndex(1)
    assert dialog.selected_symbol() == "Po"

    dialog._tabs.setCurrentIndex(0)
    assert dialog.selected_symbol() == "Po"
    assert dialog._detail.text() == before


def test_both_tabs_describe_the_same_element(dialog):
    """The control for the test above: if the Atom tab ignored the
    selection entirely, staying on Po would also pass."""
    dialog.select("Fe")

    assert "Iron" in dialog._detail.text()
    assert dialog._diagram.title.text() == "Fe"

    dialog.select("Po")

    assert "Polonium" in dialog._detail.text()
    assert dialog._diagram.title.text() == "Po"


# --- N3: the Isotopes tab ---------------------------------------------------


def _isotope_rows(dialog) -> list[list[str]]:
    table = dialog._isotope_table
    return [
        [
            table.item(row, column).text() if table.item(row, column) else ""
            for column in range(table.columnCount())
        ]
        for row in range(table.rowCount())
    ]


def test_the_isotopes_tab_lists_the_selected_elements_nuclides(dialog):
    """The thing Ketcher's Atom Properties cannot tell you: which mass
    numbers exist, how long each lasts, and how much of it is out there.

    **16 BECAME 20 WHEN THE STATES LANDED**, and the four are carbon's
    isobaric analogue states -- C-11i, C-12i, C-13i, C-14i. They are
    SHOWN rather than filtered: each names itself with the source's own
    suffix and reports an unavailable half-life as unavailable, and
    deciding a reader may not see a state NUBASE lists would be this
    application editing its source. The sort already puts them below
    everything with a measured half-life.
    """
    dialog.select("C")

    rows = _isotope_rows(dialog)

    assert len(rows) == 20
    assert [r[0] for r in rows if r[0].endswith("i")] == [
        "C-11i", "C-12i", "C-13i", "C-14i",
    ]
    assert rows[0][0] == "C-12"
    assert "98.94%" in rows[0][1]
    assert rows[0][2] == "stable"
    assert rows[2][0] == "C-14"
    assert rows[2][2] == "5.7 ky"
    assert "beta-" in rows[2][3]


def test_the_table_follows_the_selection(dialog):
    """The control: a table that ignored the grid would pass the test
    above on whatever element it happened to load with."""
    dialog.select("C")
    assert _isotope_rows(dialog)[0][0] == "C-12"

    dialog.select("Po")
    assert _isotope_rows(dialog)[0][0] == "Po-209"


def test_a_qualified_half_life_is_marked_in_the_table(dialog):
    """**A BOUND AND A MEASUREMENT MUST NOT READ ALIKE.** The text
    carries the mark and the colour only reinforces it, which is this
    table's existing rule that colour never says anything alone."""
    dialog.select("B")

    rows = _isotope_rows(dialog)
    bounded = [index for index, row in enumerate(rows) if row[0] == "B-16"]

    assert bounded, "B-16 is a lower bound and should be listed"
    assert rows[bounded[0]][2].startswith(">")
    assert "bounds" in dialog._isotope_note.text()

    # **THE MARKING, not just the formatter's prefix.** Asserting only
    # the text left the row's own marking untested -- a mutation removing
    # it survived, because the ">" comes from `format_half_life` and
    # would still be there.
    cell = dialog._isotope_table.item(bounded[0], 2)
    assert "not an exact measurement" in cell.toolTip().lower()

    exact = [index for index, row in enumerate(rows) if row[0] == "B-11"]
    assert exact, "B-11 is stable and is the control"
    assert not dialog._isotope_table.item(exact[0], 2).toolTip()


def test_an_element_with_no_abundances_shows_that_rather_than_zeroes(dialog):
    """Technetium has none. A column of `0%` would be a claim nobody
    made."""
    dialog.select("Tc")

    abundances = {row[1] for row in _isotope_rows(dialog)}

    assert abundances == {"—"}


# --- what the button refuses ------------------------------------------------


def test_the_apply_button_is_disabled_with_a_reason_when_nothing_is_selected(dialog):
    dialog.select("C")

    assert not dialog._isotope_button.isEnabled()
    assert "Select an atom" in dialog._isotope_hint.text()


def test_the_apply_button_names_the_missing_half(dialog):
    """Three things can be missing and they need three sentences."""
    dialog.select("C")
    dialog.set_selected_atom("C", 0)

    assert not dialog._isotope_button.isEnabled()
    assert "Choose an isotope" in dialog._isotope_hint.text()


def test_a_mass_number_cannot_cross_elements(dialog):
    """**THE TRAP THIS TABLE WOULD OTHERWISE SET.** The periodic table is
    a browsing tool, so somebody can be reading carbon's isotopes with an
    oxygen selected. Taking the element from the atom and the mass number
    from the table quietly offers O-14 -- a real nuclide, and not the one
    on screen. Requiring them to agree makes it unexpressible.
    """
    emitted = []
    dialog.isotope_requested.connect(
        lambda symbol, mass, every: emitted.append((symbol, mass, every))
    )
    dialog.select("C")
    dialog._isotope_table.selectRow(2)
    dialog.set_selected_atom("O", 3)

    assert not dialog._isotope_button.isEnabled()
    assert "the selected atom is O" in dialog._isotope_hint.text()

    dialog._request_isotope()

    assert emitted == []


def test_a_matching_element_emits_the_isotope(dialog):
    """The control, and the shape `MainWindow` will wire in N6: the
    dialog names an element and a mass number and touches nothing."""
    emitted = []
    dialog.isotope_requested.connect(
        lambda symbol, mass, every: emitted.append((symbol, mass, every))
    )
    dialog.select("O")
    dialog.set_selected_atom("O", 3)
    dialog._isotope_table.selectRow(2)
    dialog._request_isotope()

    assert emitted == [("O", dialog.selected_isotope(), False)]
    assert emitted[0][1] in {n.a for n in __import__(
        "openchem.chem.nuclides", fromlist=["x"]
    ).nuclides_for("O")}


def test_the_new_tab_does_not_disturb_the_selection(dialog):
    """B1's invariant, re-checked with a third tab present."""
    dialog.select("Po")
    for index in range(dialog._tabs.count()):
        dialog._tabs.setCurrentIndex(index)

    assert dialog.selected_symbol() == "Po"
    assert _isotope_rows(dialog)[0][0] == "Po-209"


def test_the_scope_defaults_to_the_selected_atom_alone(dialog):
    """**ONE ATOM IS THE DEFAULT AND THE OPT-IN IS EXPLICIT.** Labelling a
    single position is the ordinary case; "every carbon in the molecule"
    is a different enough request to be asked for rather than assumed.
    """
    emitted = []
    dialog.isotope_requested.connect(
        lambda symbol, mass, every: emitted.append((symbol, mass, every))
    )
    dialog.select("C")
    dialog.set_selected_atom("C", 0)
    dialog._isotope_table.selectRow(1)

    assert not dialog._isotope_all.isChecked()

    dialog._request_isotope()

    assert emitted == [("C", 13, False)]


def test_the_opt_in_carries_through_to_the_signal(dialog):
    emitted = []
    dialog.isotope_requested.connect(
        lambda symbol, mass, every: emitted.append((symbol, mass, every))
    )
    dialog.select("C")
    dialog.set_selected_atom("C", 0)
    dialog._isotope_table.selectRow(1)
    dialog._isotope_all.setChecked(True)

    dialog._request_isotope()

    assert emitted == [("C", 13, True)]


def test_the_hint_says_which_scope_the_button_will_use(dialog):
    """A control whose effect changes under a checkbox has to say so
    where the press happens, not only in the checkbox's own label."""
    dialog.select("C")
    dialog.set_selected_atom("C", 0)
    dialog._isotope_table.selectRow(1)

    assert "the selected atom" in dialog._isotope_hint.text()

    dialog._isotope_all.setChecked(True)

    assert "every C" in dialog._isotope_hint.text()


def test_the_checkbox_names_the_element_it_would_cover(dialog):
    """"all atoms of this element" leaves the reader to work out which
    element that is, with two on screen -- the table's and the canvas's.

    **NO ROW IS SELECTED HERE, DELIBERATELY.** The first version of this
    guard picked one first and so only ever reached the fully-armed path,
    where the label was already right; the rendered dialog showed the
    generic text, because the element was named several lines too late.
    An atom being selected is all it takes to know the element.
    """
    dialog.select("O")
    dialog.set_selected_atom("O", 3)

    assert dialog._isotope_table.selectionModel().selectedRows() == []
    assert dialog._isotope_all.text() == "all O atoms"

    # And it follows the canvas, not the table.
    dialog.set_selected_atom("C", 0)

    assert dialog._isotope_all.text() == "all C atoms"


# --- N4: the Decay tab -----------------------------------------------------


def test_the_decay_tab_opens_on_the_longest_lived_isotope(dialog):
    """**NOT THE MOST ABUNDANT.** Carbon's most abundant nuclide is C-12,
    which does not decay -- opening on it would answer every ordinary
    element with an empty picture. C-14 is the one with a chain.
    """
    dialog.select("C")

    assert dialog.decay_focus() == nuclide_data.NuclideKey(6, 14)
    assert "C-14" in dialog._decay_status.text()


def test_the_chain_follows_the_selection(dialog):
    """The control: a tab that ignored the grid would pass the test above
    on whatever element it happened to load with."""
    dialog.select("C")
    assert dialog.decay_focus() == nuclide_data.NuclideKey(6, 14)

    dialog.select("U")

    assert dialog.decay_focus() == nuclide_data.NuclideKey(92, 238)


def test_the_status_names_the_stable_nuclides_the_chain_reaches(dialog):
    """**"ENDS AT" WAS THE WRONG QUESTION**, and only the rendered chart
    showed it: `leaves()` named Hg-200, Hg-202 and Tl-205 and omitted
    Pb-206, because four of the chain's stable nuclides are marked `stbl`
    in NUBASE while also carrying a decay nobody has ever observed.
    """
    dialog.select("U")
    status = dialog._decay_status.text()

    assert "Pb-206" in status
    assert "37 nuclides reachable" in status
    assert "7 stable" in status


def test_the_legend_shows_each_family_in_its_own_colour(dialog):
    """A legend that names the encoding without demonstrating it leaves
    the reader matching words to lines by guesswork."""
    dialog.select("U")
    legend = dialog._decay_legend.text()

    from openchem.chem.decay_svg import FAMILY_COLOUR

    assert FAMILY_COLOUR["alpha"] in legend
    assert FAMILY_COLOUR["beta_minus"] in legend
    assert "**" not in legend, "QLabel does not render markdown"


def test_the_caption_never_contradicts_the_picture_above_it(dialog):
    """**IT DID, AND ONLY THE SCREEN SHOWED IT.** The caption ended
    "Ground states only, so a chain that runs through an isomer is not
    drawn" -- while the chart directly above it was drawing Ag-108m and
    its stacked ground state. Every test passed; magnifying the shot
    caught it in one look.

    Asserted as a CONTRADICTION rather than as the replacement wording,
    so a future rewrite is free to say it better and is not free to say
    the chart cannot do what it is doing.
    """
    dialog.select("Ag")
    legend = dialog._decay_legend.text().lower()

    assert "ground states only" not in legend
    assert "isomer is not drawn" not in legend
    # ...and the chart really is drawing one, so this is not vacuous.
    assert dialog.decay_focus() == nuclide_data.NuclideKey(47, 108, 1)


def test_the_insert_hint_names_what_is_actually_placed(dialog):
    """**IT SAID "Adds Ag-108m to the canvas" AND ADDED Ag-108.** The
    button emits a mass number, which is all a molfile can record, so on
    an isomer the hint was naming a different nuclide from the one that
    would appear.

    The ground-state arm is the control: without it a hint that gave up
    and said nothing would pass the first half.
    """
    dialog.select("Ag")

    hint = dialog._decay_hint.text()
    assert "Ag-108" in hint
    assert "Adds Ag-108m" not in hint, "it does not add the isomer"
    assert "mass number" in hint, "and it says why"

    dialog.select("U")
    assert dialog._decay_hint.text() == "Adds U-238 to the canvas."


def test_clicking_a_box_follows_the_chain_from_there(dialog):
    """The whole point of the picture being clickable.

    **A REAL MOUSE EVENT THROUGH THE FILTER, not `_focus_decay_node`.**
    The first version of this called the handler directly, so a mutation
    that made the filter swallow the click without acting on it survived
    -- the picture would have been inert and every test green.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    dialog.select("U")
    dialog._decay_view.set_zoom(1.0)
    radium = next(n for n in dialog._decay_diagram.nodes if n.name == "Ra-226")

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(radium.x + radium.width / 2, radium.y + radium.height / 2),
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handled = dialog.eventFilter(dialog._decay_view._view, press)

    assert handled
    assert dialog.decay_focus() == nuclide_data.NuclideKey(88, 226)
    assert "Ra-226" in dialog._decay_status.text()
    assert not any(n.name == "U-238" for n in dialog._decay_diagram.nodes)


def test_a_click_on_empty_chart_space_changes_nothing(dialog):
    """The control: the filter must hit-test rather than treat any press
    as a selection."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    dialog.select("U")
    dialog._decay_view.set_zoom(1.0)

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(2.0, 2.0),
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    dialog.eventFilter(dialog._decay_view._view, press)

    assert dialog.decay_focus() == nuclide_data.NuclideKey(92, 238)


def test_a_click_is_hit_tested_at_the_CURRENT_zoom(dialog):
    """The chart is scaled by the zoom, so a click's pixel position is not
    a diagram position. Without dividing by the zoom, every click at
    anything but 100% lands on the wrong nuclide -- which on a chart of
    the nuclides is a plausible neighbour rather than an obvious miss."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    dialog.select("U")
    dialog._decay_view.set_zoom(2.0)
    radium = next(n for n in dialog._decay_diagram.nodes if n.name == "Ra-226")

    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(
            (radium.x + radium.width / 2) * 2.0,
            (radium.y + radium.height / 2) * 2.0,
        ),
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    dialog.eventFilter(dialog._decay_view._view, press)

    assert dialog.decay_focus() == nuclide_data.NuclideKey(88, 226)


def test_a_nuclide_can_be_sent_to_the_canvas(dialog):
    """"You could obviously click one and paste it in the 2D editor" -- a
    decay product is an element with a mass number, which is exactly what
    a molfile can express."""
    elements, nuclides = [], []
    dialog.insert_requested.connect(lambda symbol, mass: elements.append(symbol))
    dialog.nuclide_insert_requested.connect(lambda s, a: nuclides.append((s, a)))
    dialog.select("U")

    dialog._insert_decay_nuclide()

    assert elements == ["U"]
    assert nuclides == [("U", 238)]


def test_the_chart_is_refitted_when_its_tab_is_shown(dialog):
    """**A ZOOM COMPUTED AGAINST AN UNSHOWN VIEWPORT IS NOT A FIT.**
    `_refresh_decay` runs from `select`, which happens while another tab
    is current -- so `zoom_to_fit` measured a viewport Qt had not laid out
    and clamped to the 25% floor. Measured in the running app: a 2320 px
    chart drawn a quarter size in a 1265 px pane.
    """
    dialog.resize(1200, 900)
    dialog.select("U")
    dialog._tabs.setCurrentIndex(0)
    dialog._decay_view.set_zoom(4.0)

    dialog._tabs.setCurrentIndex(dialog._tabs.count() - 1)

    assert dialog._tabs.tabText(dialog._tabs.currentIndex()) == "Decay"
    assert dialog._decay_view.zoom() < 4.0


def test_switching_to_another_tab_refits_nothing(dialog):
    """The control: the handler must key on WHICH tab, not merely on the
    fact that one changed.

    **IT HAS TO MOVE TO A DIFFERENT TAB TO BE A CONTROL AT ALL.** The
    first version switched to index 0, which was already current, so
    `currentChanged` never fired and a mutation that refitted on ANY tab
    change passed straight through it.
    """
    dialog.select("U")
    dialog._tabs.setCurrentIndex(0)
    dialog._decay_view.set_zoom(4.0)

    dialog._tabs.setCurrentIndex(1)

    assert dialog._tabs.currentIndex() == 1, "the fixture must actually move"
    assert dialog._decay_view.zoom() == 4.0


def test_every_element_can_draw_a_chain(dialog):
    """A tab that raises on one element is a tab nobody can trust to
    browse with, which is what this table is for."""
    from openchem.chem.element_reference import all_symbols

    for symbol in all_symbols():
        dialog.select(symbol)

        assert dialog.decay_focus() is not None, symbol
        assert dialog._decay_status.text()


# --- the dialog has to fit on a screen -------------------------------------


def test_the_dialogs_minimum_fits_a_real_screen(dialog):
    """**THE REGRESSION THIS BRANCH SHIPPED, AND WHAT IT COST.** Adding
    the Decay tab took the dialog's minimum height to 1142 px against a
    1032 px screen, so Qt clamped it and the whole action row -- Insert
    into drawing, Copy symbol, Close -- sat 105 px BELOW the bottom edge.
    Reported as "I cannot select an element and place it on the actual
    editor": the buttons were not broken, they were unreachable.

    The cause is the one already recorded for the main window's WIDTH,
    vertically: `QTabWidget` takes the MAXIMUM over its pages, so one
    tab's comfortable floor became the whole dialog's, and a minimum
    larger than the screen cannot be rescued by resizing.

    **HEIGHT ONLY, AND THE WIDTH IS DELIBERATELY NOT ASSERTED.** A
    geometry claim about real fixed text is a claim about the FONT, and
    this suite runs `offscreen`, whose default is far wider than anything
    a user sees: measured, the same dialog is 1288 px wide there against
    902 in the running application. Height is driven by row counts rather
    than by glyph widths -- 898 offscreen against 922 real -- so it is
    the half that means the same thing on both.
    """
    minimum = dialog.minimumSizeHint()

    assert minimum.height() <= PeriodicTableDialog.MAX_MINIMUM_HEIGHT, (
        f"{minimum.height()} px tall"
    )


def test_no_tab_page_imposes_a_floor_taller_than_the_grid(dialog):
    """The structural form, which catches the NEXT tab rather than this
    one. A page is free to want more room; it is not free to make the
    window unusable on the way to getting it, because every page here
    already scrolls or zooms internally.
    """
    for index in range(dialog._tabs.count()):
        page = dialog._tabs.widget(index)

        assert page.minimumSizeHint().height() <= 280, dialog._tabs.tabText(index)


def test_the_action_row_is_inside_the_dialog_at_its_MINIMUM_size(dialog):
    """**THE SYMPTOM, not the measurement behind it.** A bound on the
    minimum can be satisfied while a layout still puts the buttons past
    the edge, so this squeezes the dialog to the smallest size it admits
    to and asks where the buttons actually are.

    It asserts the dialog really BECAME that size first -- `resize()` is
    clamped to the minimum, which is precisely how the original defect
    hid: the window simply grew past the screen instead of refusing.
    """
    from PySide6.QtWidgets import QPushButton

    minimum = dialog.minimumSizeHint()
    dialog.resize(minimum)
    dialog.show()
    QCoreApplication.processEvents()

    assert dialog.height() <= minimum.height() + 2, "the dialog did not shrink"

    labelled = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() in ("Insert into drawing", "Copy symbol", "Close")
    ]

    assert len(labelled) == 3, "the fixture must find the real action row"
    for button in labelled:
        bottom = button.mapTo(dialog, button.rect().bottomLeft()).y()

        assert bottom <= dialog.height(), f"{button.text()} is {bottom - dialog.height()} px past the edge"


def test_the_window_can_be_resized_and_maximised(dialog):
    """A QDialog gets neither a maximise button nor a size grip by
    default, so a window that opened too tall could not be shrunk, moved
    back into view or maximised -- reported alongside the buttons, as
    "there is no way to adjust the size of the periodic table popup".
    """
    from PySide6.QtCore import Qt

    assert dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert dialog.isSizeGripEnabled()


@pytest.mark.parametrize(
    "hint,screen,expected",
    [
        # A dialog smaller than the screen opens at its own size.
        ((902, 700), (1920, 1032), (902, 700)),
        # Alex's screen: the height is what gets capped.
        ((902, 999), (1920, 1032), (902, 949)),
        # A small laptop caps both.
        ((902, 999), (1366, 768), (902, 706)),
        # And it never asks for the whole screen, so the window stays
        # movable and the title bar has somewhere to be.
        ((4000, 4000), (1920, 1032), (1824, 949)),
    ],
)
def test_the_opening_size_is_capped_against_the_screen(hint, screen, expected):
    """**THE CAP COMES FROM THE SCREEN, NOT FROM `self.size()`** -- during
    construction that is Qt's pre-show default rather than anything real,
    the trap `initial_right_dock_width` already records.

    **AND THE SUITE CANNOT SEE THE CALL SITE**, which is why this tests
    the arithmetic directly. `offscreen` reports an 800x800 screen and
    this dialog's minimum is larger than that, so `resize()` is clamped
    either way: applying the cap and deleting it are indistinguishable by
    outcome. Deleting the CALL in `_fit_to_screen` is the one mutation
    nothing here catches, and it is written down rather than papered over
    with a second implementation.

    The first version of this guard was worse than useless: it asserted
    `dialog.width() <= available.width()` on a dialog the fixture never
    shows, so it passed on Qt's pre-show default and could not fail.
    """
    assert fit_within(*hint, *screen) == expected


# --- P1: clicking an element arms the canvas -------------------------------


def test_clicking_a_cell_arms_the_canvas(dialog):
    """**"it should be two clicks: click the element, then place it."**"""
    armed = []
    dialog.element_armed.connect(lambda symbol, mass: armed.append((symbol, mass)))

    dialog._buttons["Na"].click()

    assert armed == [("Na", 0)]
    assert dialog.selected_symbol() == "Na"


def test_a_chosen_isotope_rides_along(dialog):
    """Picking C-13 and clicking the canvas must place carbon-13."""
    armed = []
    dialog.element_armed.connect(lambda symbol, mass: armed.append((symbol, mass)))
    dialog.select("C")
    dialog._isotope_table.selectRow(1)

    assert dialog.isotope_for_placement() == 13
    assert armed and armed[-1] == ("C", 13)


def test_an_isotope_row_does_not_follow_you_to_another_element(dialog):
    """A carbon-13 row left highlighted must not place O-13 when somebody
    clicks oxygen -- a real nuclide, and not the one they asked for.

    **AND TODAY THAT IS PROTECTED BY A SIDE EFFECT, WHICH IS WHY THE
    GUARD BELOW ASSERTS THE PREDICATE DIRECTLY.** Measured: `select()`
    repopulates the isotope table, which drops the row selection, and it
    updates `_isotope_selection_element` in the same call -- so the two
    can never disagree through this route and the element check cannot
    fire. A mutation deleting it survived this test, correctly.
    """
    dialog.select("C")
    dialog._isotope_table.selectRow(1)
    assert dialog.isotope_for_placement() == 13

    dialog.select("O")

    assert dialog.isotope_for_placement() is None
    assert dialog.selected_isotope() is None, (
        "the row selection is dropped by the refresh, which is what makes "
        "the element check unreachable from here"
    )


def test_the_element_check_refuses_a_stale_isotope_row(dialog):
    """The element check, asserted where it can actually fail.

    **AN UNREACHABLE BRANCH IS A QUESTION ABOUT WHERE TO ASSERT**, not
    automatically dead code: `isotope_for_placement`'s contract is "the
    mass number for the element being SHOWN", which is meaningful on its
    own terms, and what protects it today is an incidental side effect of
    repopulating a table. The day somebody preserves the row selection
    across a refresh -- a perfectly reasonable thing to want -- this
    becomes the only thing standing between a carbon-13 row and an O-13
    atom.
    """
    dialog.select("C")
    dialog._isotope_table.selectRow(1)
    assert dialog.isotope_for_placement() == 13

    # The disagreement the UI cannot currently produce.
    dialog._isotope_selection_element = "O"

    assert dialog.selected_isotope() == 13, "the row is still selected"
    assert dialog.isotope_for_placement() is None


def test_the_insert_button_carries_the_isotope_too(dialog):
    """The button is the other door to the same call, and Alex hit the
    bug through it."""
    asked = []
    dialog.insert_requested.connect(lambda symbol, mass: asked.append((symbol, mass)))
    dialog.select("C")
    dialog._isotope_table.selectRow(1)

    dialog._insert_symbol()

    assert asked == [("C", 13)]


# --- P2: the grid shrinks so the dialog fits a laptop ----------------------


@pytest.mark.parametrize(
    "screen,expected",
    [
        # Alex's machine: unchanged, which is half the requirement.
        ((1920, 1032), CELL_LARGE),
        ((1600, 852), (44, 48)),
        # The reported case.
        ((1366, 728), CELL_SMALL),
        # Smaller still: clamped at the floor rather than shrinking to
        # something unreadable.
        ((1280, 680), CELL_SMALL),
        ((1024, 600), CELL_SMALL),
    ],
)
def test_the_cell_size_follows_the_screen(screen, expected):
    """**A 1920 SCREEN MUST GET EXACTLY WHAT SHIPPED.** A change that
    makes small screens work by making every screen worse is not the fix
    somebody asked for.

    Pure, for the reason `fit_within` is: `offscreen` reports an 800x800
    screen, so a call site that reads the real one cannot be told apart
    from its own deletion through the window.
    """
    assert cell_size_for(*screen) == expected


def test_a_narrow_screen_is_considered_even_though_height_binds_today():
    """The signature takes both dimensions because the constraint is "it
    fits the available geometry" -- an 18-column grid of 46 px cells is
    880 px wide, so width is a real term even if no common screen
    reaches it. Encoding "height is the only determinant" would make an
    accidental observation into a law.
    """
    assert cell_size_for(500, 2000)[0] < CELL_LARGE[0]


def test_the_cell_never_shrinks_below_the_legible_floor():
    assert cell_size_for(200, 200) == CELL_SMALL


def test_the_dialog_fits_the_screen_it_was_reported_broken_on(dialog):
    """**BOTH DIMENSIONS, NOT MERELY "HEIGHT DECREASED".** The goal is
    that it fits a laptop.

    Measured with real fonts at each cell size: 1920 gives 902x852,
    1600 gives 866x834, and 1366 gives 686x726 against about 728 usable.
    Asserted here at whatever `offscreen` renders, which is why the bound
    is derived from the cell size rather than written as a constant --
    that platform's font makes this dialog 1288 px wide where the running
    application is 902.
    """
    from openchem.ui.dialogs.periodic_table_dialog import _DIALOG_CHROME, _GRID_ROWS

    minimum = dialog.minimumSizeHint()

    assert minimum.height() <= _GRID_ROWS * dialog._cell_size[1] + _DIALOG_CHROME + 25


def test_the_chrome_constant_is_re_derived_rather_than_trusted(dialog):
    """`_DIALOG_CHROME` decides WHEN to shrink, so a stale value shrinks
    the cells too early or too late.

    **IT WAS GUESSED AT 420 AND MEASURES 366**, which is why this exists:
    the guess made a 1366-wide screen give up 40 px of grid it did not
    need to. Re-derived from a built dialog so it cannot drift again.
    """
    from openchem.ui.dialogs.periodic_table_dialog import _DIALOG_CHROME, _GRID_ROWS

    measured = dialog.minimumSizeHint().height() - _GRID_ROWS * dialog._cell_size[1]

    assert abs(measured - _DIALOG_CHROME) <= 60, (
        f"chrome measures {measured} against a declared {_DIALOG_CHROME}"
    )


def test_every_cell_in_one_grid_agrees(dialog):
    """The cheap half: one size across the whole grid."""
    sizes = {(b.width(), b.height()) for b in dialog._buttons.values()}

    assert len(sizes) == 1
    assert sizes == {dialog._cell_size}


def test_the_screen_is_read_ONCE_rather_than_per_cell(qapp, monkeypatch):
    """**THE HALF THE TEST ABOVE CANNOT SEE.** Reading the screen inside
    `_cell()` gives the same answer 118 times in a stable environment, so
    every cell still agrees and the guard passes -- a mutation doing
    exactly that survived.

    What separates them is a screen that answers differently between
    calls, which is not exotic: a laptop docked or undocked mid-session
    changes `availableGeometry`, and a construction that straddled it
    would produce a ragged table.
    """
    from openchem.ui.dialogs import periodic_table_dialog as module

    answers = iter([(46, 50)] + [(34, 36)] * 400)
    monkeypatch.setattr(
        module.PeriodicTableDialog, "_screen_cell_size", lambda self: next(answers)
    )
    built = module.PeriodicTableDialog()
    try:
        sizes = {(b.width(), b.height()) for b in built._buttons.values()}

        assert sizes == {(46, 50)}, "the screen was re-read while building the grid"
    finally:
        built.setParent(None)
        built.deleteLater()


def test_the_two_floors_that_set_the_dialogs_height_stay_down(dialog):
    """**ASSERTED ON THE FLOORS THEMSELVES, not on the total they make.**

    `QTabWidget` takes the maximum over its pages, so these two explicit
    minimums decided how short the whole window could be -- and the
    AtomDiagram's 240 was the binder, which is why lowering the
    ShellDiagram inside it changed nothing at all.

    The total cannot police them: measured, restoring the Facts floor from
    120 to 190 moves the dialog by 6 px, because the Atom page is 184 and
    stays the maximum either way. And a bound expressed against
    `_DIALOG_CHROME` cannot be tight on both platforms -- that chrome is
    366 with real fonts and 322 under `offscreen`. These are constants
    this file sets, so this file asserts them.
    """
    assert dialog._diagram.minimumHeight() <= 160, "the AtomDiagram floor came back"
    assert dialog._detail_area.minimumHeight() <= 130, "the Facts floor came back"


def _stacked_tc99_diagram():
    """A chart with a ground state and its isomer sharing a cell.

    **THE SHIPPED TABLE HOLDS NO ISOMER**, so this is built directly --
    the "move the threshold rather than hunt an input" rule. A second
    element (Ru-99, one proton up) is in it deliberately: without a
    second Z ROW the row pitch has nothing to push apart, and a guard
    built on Tc alone cannot see a pitch that ignores the stack.
    """
    from openchem.chem.decay import DecayTree
    from openchem.chem.decay_svg import render_decay_svg

    ground = nuclide_data.nuclide(43, 99)
    below = nuclide_data.nuclide(42, 98)  # same N = 56, one Z down
    metastable = nuclide_data.Nuclide(
        43, 99, "Tc", nuclide_data.HalfLife(21624.0, nuclide_data.EXACT),
        state_index=1, state_label="m",
    )
    tree = DecayTree(root=metastable.key)
    tree.nodes = {
        metastable.key: metastable,
        ground.key: ground,
        below.key: below,
    }
    tree.edges = {k: [] for k in tree.nodes}
    return render_decay_svg(tree)


def test_a_click_carries_the_nodes_OWN_key_and_not_a_rebuilt_one(dialog):
    """**A GROUND STATE AND ITS ISOMER SHARE A CELL**, so rebuilding the
    identity from `(node.z, node.a)` picks the ground state whichever box
    was clicked -- and looks perfectly correct until an isomer is on
    screen. Same shape as this project's Ketcher pool-id bug: a
    reassembled index is right until the two spaces diverge.

    **DRIVEN THROUGH THE EVENT FILTER, not by calling the handler.** An
    earlier version of this test called `_focus_decay_node(node.key)`
    itself and the rebuild mutation walked straight through it -- testing
    a helper is not testing the wiring, which is a lesson this branch has
    now paid for twice.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    diagram = _stacked_tc99_diagram()
    boxes = {n.name: n for n in diagram.nodes}
    assert boxes["Tc-99"].x == boxes["Tc-99m"].x, "the setup must stack them"

    asked: list = []
    dialog.select("Tc")
    dialog._decay_view.set_zoom(1.0)
    dialog._decay_diagram = diagram
    dialog._focus_decay_node = asked.append

    isomer = boxes["Tc-99m"]
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(isomer.x + isomer.width / 2, isomer.y + isomer.height / 2),
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert dialog.eventFilter(dialog._decay_view._view, press)

    assert asked == [nuclide_data.NuclideKey(43, 99, 1)]


def test_a_stack_never_reaches_into_the_row_below_it(dialog):
    """**THE ROW PITCH IS WHAT KEEPS THE STACK INSIDE ITS OWN ROW.** An
    isomer is offset by a whole box height, which is more than the gap
    between two Z rows -- so a pitch that ignores the stack puts Tc-99m
    on top of the Ru-99 above it and a click on one lands on the other.

    A ONE-ROW FIXTURE CANNOT SEE THIS, which is why this one carries a
    second element.
    """
    diagram = _stacked_tc99_diagram()
    boxes = list(diagram.nodes)

    assert len({n.key.z for n in boxes}) == 2, "the setup needs two Z rows"
    columns = {n.key.a - n.key.z for n in boxes}
    assert columns == {56}, "all three must share a column or nothing collides"
    for one in boxes:
        for other in boxes:
            if one is other:
                continue
            assert not (
                one.x < other.x + other.width
                and other.x < one.x + one.width
                and one.y < other.y + other.height
                and other.y < one.y + one.height
            ), f"{one.name} overlaps {other.name}"


def test_an_isomer_row_disables_apply_and_says_why(dialog):
    """**THE ROW STAYS SELECTED AND ITS DATA STAYS ON SCREEN.** Only
    Apply is refused, because the half-life and decay modes of Tc-99m are
    exactly what somebody opened the tab to read.

    The shipped table holds no isomer, so the row is written directly --
    which is also the only way to reach the branch at all.
    """
    from openchem.chem.isotopes import IsotopeRefusal, REFUSAL_TEXT
    from PySide6.QtCore import Qt

    dialog.set_selected_atom("Tc", 0)
    dialog.select("Tc")
    table = dialog._isotope_table
    item = table.item(0, 0)
    item.setData(
        Qt.ItemDataRole.UserRole, nuclide_data.NuclideKey(43, 99, 1)
    )
    table.selectRow(0)
    dialog._refresh_isotope_button()

    assert dialog.selected_isotope_key() == nuclide_data.NuclideKey(43, 99, 1)
    assert not dialog._isotope_button.isEnabled()
    assert dialog._isotope_hint.text() == REFUSAL_TEXT[
        IsotopeRefusal.ISOMER_NOT_IN_MOLFILE
    ]
    # ...and the placement path refuses it for the same reason.
    assert dialog.isotope_for_placement() is None


def test_a_ground_state_row_still_applies(dialog):
    """The control. Without it, a refusal that disabled Apply for every
    row would pass the test above while breaking the whole feature."""
    from PySide6.QtCore import Qt

    dialog.set_selected_atom("Tc", 0)
    dialog.select("Tc")
    table = dialog._isotope_table
    table.item(0, 0).setData(
        Qt.ItemDataRole.UserRole, nuclide_data.NuclideKey(43, 97)
    )
    table.selectRow(0)
    dialog._refresh_isotope_button()

    assert dialog._isotope_button.isEnabled()
    assert dialog.selected_isotope() == 97


def test_an_isomer_row_carries_ITS_OWN_key_and_names_itself(dialog, monkeypatch):
    """**THE ROW IS WHERE THE STATE ENTERS THE UI**, so storing
    `NuclideKey(entry.z, entry.a)` instead of `entry.key` is invisible
    until an isomer is listed -- and then Tc-99m's row claims to be
    Tc-99 and Apply happily writes it.

    **THE SHIPPED TABLE HOLDS NO ISOMER**, so `nuclides_for` is
    substituted. Its own setup is asserted: without two rows sharing a
    mass number there is nothing a dropped state index could get wrong.
    """
    from openchem.ui.dialogs import periodic_table_dialog as module

    ground = nuclide_data.nuclide(43, 99)
    metastable = nuclide_data.Nuclide(
        43, 99, "Tc", nuclide_data.HalfLife(21624.0, nuclide_data.EXACT),
        state_index=1, state_label="m",
    )
    monkeypatch.setattr(
        module.nuclide_data, "nuclides_for", lambda symbol: (ground, metastable)
    )

    dialog.select("Tc")
    table = dialog._isotope_table
    keys = [
        table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        for row in range(table.rowCount())
    ]
    names = [table.item(row, 0).text() for row in range(table.rowCount())]

    assert len({k.a for k in keys}) == 1, "the setup needs one mass number"
    assert keys == [
        nuclide_data.NuclideKey(43, 99),
        nuclide_data.NuclideKey(43, 99, 1),
    ]
    # And the row NAMES the state, from the source's own suffix, so a
    # reader is never shown two rows both called Tc-99.
    assert names == ["Tc-99", "Tc-99m"]


def test_an_isomeric_transition_is_shown_in_words_not_as_a_token(dialog):
    """**`IT` IS THE SECOND COMMONEST MODE IN THE TABLE, at 1,471 rows**,
    and it shipped rendering as its raw NUBASE token beside "beta+" and
    "electron capture" -- exactly the cryptic-token problem `_MODE_NAMES`
    exists to solve. The whole suite was green; the magnified Isotopes
    tab showed "beta+ 91.3%, IT 8.7%" in one look.
    """
    dialog.select("Ag")
    rows = _isotope_rows(dialog)

    metastable = next(r for r in rows if r[0] == "Ag-108m")

    assert "isomeric transition" in metastable[3]
    assert not metastable[3].startswith("IT")
