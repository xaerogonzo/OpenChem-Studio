"""The atom diagram, checked by painting it.

`repaint()` and `update()` are both no-ops on a widget that was never
shown, so a test that calls them and asserts nothing crashed has exercised
no painter at all. `conftest.painted()` renders into a QImage, which does.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from conftest import ink, painted
from openchem.ui.widgets.atom_diagram import AtomDiagram, OrbitalBoxes, ShellDiagram


def _dispose(widget) -> None:
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def diagram(qapp):
    widget = AtomDiagram()
    yield widget
    _dispose(widget)


# --- what it says -----------------------------------------------------------


def test_it_shows_the_configuration_of_a_neutral_atom(diagram):
    diagram.set_element("Fe")

    assert diagram.title.text() == "Fe"
    assert diagram.configuration_label.text() == "[Ar] 3d6 4s2"


def test_the_nucleus_line_names_the_isotope_it_counted(diagram):
    """**A neutron count is not a property of an element.** Silicon does
    not have 14 neutrons; Si-28 does, and the line has to say so or the
    number reads as intrinsic."""
    diagram.set_element("Si")

    text = diagram.nucleus_label.text()

    assert "Protons: 14" in text
    assert "Neutrons: 14" in text
    assert "Si-28" in text
    assert "most abundant" in text


def test_a_curated_configuration_and_a_derived_one_are_labelled_differently(diagram):
    """The provenance line is the whole reason the +/- buttons are safe to
    offer: a reader can tell a measured ground state from this app's own
    arithmetic."""
    diagram.set_element("Fe")
    assert "ground-state reference" in diagram.provenance_label.text()

    diagram.set_element("Fe", charge=2)
    assert "general ionisation rule" in diagram.provenance_label.text()


def test_isoelectronic_is_reported_only_when_it_is_true(diagram):
    """Na+ really does share Ne's configuration. Fe2+ has 24 electrons,
    the same as chromium, and is isoelectronic with no noble gas -- a
    count-only implementation would claim otherwise."""
    diagram.set_element("Na", charge=1)
    assert "isoelectronic with Ne" in diagram.provenance_label.text()

    diagram.set_element("Fe", charge=2)
    assert "isoelectronic" not in diagram.provenance_label.text()


# --- the buttons ------------------------------------------------------------


def test_removing_an_electron_makes_a_cation(diagram):
    diagram.set_element("Fe")

    diagram.remove_button.click()
    diagram.remove_button.click()

    assert diagram.charge() == 2
    assert diagram.title.text() == "Fe2+"
    assert diagram.configuration_label.text() == "[Ar] 3d6"


def test_adding_an_electron_makes_an_anion(diagram):
    diagram.set_element("F")

    diagram.add_button.click()

    assert diagram.charge() == -1
    assert diagram.title.text() == "F−"
    assert diagram.configuration_label.text() == "[He] 2s2 2p6"


def test_stripping_past_the_last_electron_refuses_and_keeps_the_display(diagram):
    """Reaching the end of an element is the user exploring, not an error
    to punish them with -- the previous state stays on screen."""
    diagram.set_element("H")
    diagram.remove_button.click()  # H+, a bare proton

    assert diagram.charge() == 1
    assert not diagram.remove_button.isEnabled()

    diagram._try_charge(2)  # impossible

    assert diagram.charge() == 1  # unchanged


def test_neutral_resets(diagram):
    diagram.set_element("Fe", charge=3)

    diagram.reset_button.click()

    assert diagram.charge() == 0
    assert diagram.configuration_label.text() == "[Ar] 3d6 4s2"


# --- that it actually draws -------------------------------------------------


def test_the_shell_diagram_draws_more_for_a_bigger_atom(qapp):
    """Compared against the SAME widget with a smaller atom rather than
    against a fixed number: the background and nucleus already account for
    most pixels, so "some ink exists" would pass on an empty painter."""
    from openchem.chem.electron_shells import neutral_configuration, nucleus

    widget = ShellDiagram()
    widget.set_atom(neutral_configuration("H").shells(), nucleus("H"))
    small = ink(widget)

    widget.set_atom(neutral_configuration("Kr").shells(), nucleus("Kr"))
    large = ink(widget)

    assert large > small
    _dispose(widget)


def test_the_boxes_draw_more_for_more_subshells(qapp):
    from openchem.chem.electron_shells import neutral_configuration

    widget = OrbitalBoxes()
    widget.set_configuration(neutral_configuration("He"))
    small = ink(widget)

    widget.set_configuration(neutral_configuration("Fe"))
    large = ink(widget)

    assert large > small
    _dispose(widget)


def test_an_empty_box_view_says_why_it_is_empty(qapp):
    """It used to draw a blank rectangle. Four different situations look
    identical when they are all blank, which is the failure the project's
    empty-state work exists to prevent."""
    widget = OrbitalBoxes()
    widget.set_configuration(None)

    assert ink(widget) > 0
    _dispose(widget)


def test_a_bare_nucleus_is_reported_as_a_result_not_as_missing_data(qapp):
    """H+ genuinely has no electrons. That is the ANSWER, so the wording
    must not imply something failed to load -- and the second line still
    names the one action that changes it."""
    from openchem.chem.electron_shells import ion_configuration

    widget = OrbitalBoxes()
    widget.set_configuration(ion_configuration("H", 1).configuration)

    assert ink(widget) > 0
    _dispose(widget)


def test_the_whole_diagram_paints(diagram):
    diagram.set_element("N")

    image = painted(diagram, 640, 360)

    assert not image.isNull()
    assert ink(diagram, 640, 360) > 0


# --- where it lives ---------------------------------------------------------


def test_the_periodic_table_shows_a_diagram_for_the_selected_element(qapp):
    """The dialog already displayed the configuration as a string; this is
    the same information as a picture, which is why it sits beside it
    rather than at the bottom of everything else."""
    from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog

    dialog = PeriodicTableDialog()

    dialog.select("Fe")

    assert dialog._diagram.title.text() == "Fe"
    assert dialog._diagram.configuration_label.text() == "[Ar] 3d6 4s2"
    _dispose(dialog)


def test_choosing_a_new_element_returns_to_neutral(qapp):
    """Carrying a charge across would answer a question about a different
    species than the one just clicked."""
    from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog

    dialog = PeriodicTableDialog()
    dialog.select("Fe")
    dialog._diagram.remove_button.click()
    assert dialog._diagram.charge() == 2 - 1

    dialog.select("O")

    assert dialog._diagram.charge() == 0
    assert dialog._diagram.title.text() == "O"
    _dispose(dialog)



def test_the_facts_table_says_its_configuration_is_the_neutral_atom(qapp):
    """The diagram above can be showing an ion. Iron beside Fe2+ reads as
    a contradiction -- [Ar] 3d6 4s2 against [Ar] 3d6 -- unless the table
    says which species it describes."""
    from openchem.ui.dialogs.periodic_table_dialog import describe
    from openchem.chem.element_reference import facts_for

    text = describe(facts_for("Fe"))

    assert "Electron configuration (neutral atom)" in text


# --- A1: the orbital view must never drop a subshell ------------------------
#
# It used to. `paintEvent` packed rows against `self.height()` and broke
# out when it ran out, so polonium's panel stopped at `5s` -- 22 of its 84
# electrons absent from the drawing while the line above it printed the
# full `[Xe] 4f14 5d10 6s2 6p4`. Measured against the shipped geometry:
# Po needs 160 px at width 420 and the old panel had about 130, which
# leaves exactly the 4 subshells the screenshot was missing.


def test_every_element_lays_out_every_subshell_at_every_width(qapp):
    """All 118, at four widths. **This is the test that did not exist.**

    `test_the_boxes_draw_more_for_more_subshells` compares two SMALL
    elements, and both of them fit -- so the whole heavy end of the table
    could drop rows with the suite green. The population is the point
    here: the defect only appears once a configuration is taller than the
    widget, which begins around period 5.
    """
    from openchem.chem.electron_shells import neutral_configuration
    from openchem.chem.element_reference import all_symbols

    widget = OrbitalBoxes()
    for symbol in all_symbols():
        configuration = neutral_configuration(symbol)
        widget.set_configuration(configuration)
        expected = [subshell.label for subshell in configuration.in_writing_order()]
        for width in (200, 300, 420, 900):
            drawn = [placed.subshell.label for placed in widget._layout_rows(width)]
            assert drawn == expected, f"{symbol} at width {width}"
    _dispose(widget)


def test_the_widget_asks_for_the_height_its_rows_need(qapp):
    """The invariant the scroll area then has to honour.

    **THE FIRST VERSION OF THIS WAS VACUOUS AND A MUTATION SAID SO.** An
    unshown `OrbitalBoxes` is 640x480, and polonium laid out across 640 px
    needs 112 -- under the 120 px placeholder floor. So `minimumHeight()
    >= required_height()` held on a widget that had computed nothing, and
    neutering `_apply_required_height` changed no test in the file.

    The width is narrowed FIRST, which makes the requirement (256) exceed
    the floor. `resize()` before `show()` moves `width()` and delivers no
    `resizeEvent` -- measured in this project at 0 calls -- so this also
    pins that `set_configuration` does the work rather than the event.
    """
    from openchem.chem.electron_shells import neutral_configuration

    widget = OrbitalBoxes()
    widget.resize(300, 60)
    widget.set_configuration(neutral_configuration("Po"))

    assert widget.required_height(300) > 120, "fixture is degenerate again"
    assert widget.minimumHeight() >= widget.required_height(300)
    assert widget.missing_row_count(300, widget.minimumHeight()) == 0
    _dispose(widget)


def test_a_taller_configuration_asks_for_more_height_than_a_short_one(qapp):
    """Otherwise the requirement could be a constant and still pass above."""
    from openchem.chem.electron_shells import neutral_configuration

    widget = OrbitalBoxes()
    widget.set_configuration(neutral_configuration("He"))
    small = widget.required_height(420)
    widget.set_configuration(neutral_configuration("U"))
    large = widget.required_height(420)

    assert large > small
    _dispose(widget)


def test_the_incomplete_predicate_can_say_NO(qapp):
    """A guard is worth what its ability to report a violation is worth.

    `missing_row_count` is asserted directly rather than reached through
    the widget, because `_apply_required_height` makes it unreachable in
    the running application -- this project's rule that an unreachable
    branch is a question about where to assert, not automatically dead
    code. The 130 px arm is the geometry the OLD panel had.
    """
    from openchem.chem.electron_shells import neutral_configuration

    widget = OrbitalBoxes()
    widget.set_configuration(neutral_configuration("Po"))

    assert widget.missing_row_count(420, 130) == 4
    assert widget.missing_row_count(420, widget.required_height(420)) == 0
    _dispose(widget)


def _labels_drawn_by(widget, monkeypatch) -> list[str]:
    """Every string the widget hands to `QPainter.drawText` during a grab.

    `grab()` paints the WHOLE widget rather than an exposed viewport
    rect, which is what lets a deliberately short widget be the setup
    rather than the obstacle.

    Monkeypatching a C++-backed Qt type is not a given -- measured on
    this PySide6 build, assigning `QPainter.drawText` works.
    """
    from PySide6.QtGui import QPainter

    drawn: list[str] = []
    original = QPainter.drawText

    def spy(self, *args):
        if args and isinstance(args[-1], str):
            drawn.append(args[-1])
        return original(self, *args)

    monkeypatch.setattr(QPainter, "drawText", spy)
    try:
        widget.grab()
    finally:
        monkeypatch.undo()
    return drawn


def test_the_boxes_really_paint_every_subshell_label(qapp, monkeypatch):
    """**The rendered guard, because the defect was a rendering defect.**

    A `_layout_rows` test can pass while the painter still clips: the
    arithmetic and the paint used to be one loop, and splitting them is
    exactly the change that could put them back out of step. So this
    spies on the real `QPainter.drawText` through a real `grab()` and
    asks what reached the screen. Po and U are the two heaviest layouts
    in the table.
    """
    from openchem.chem.electron_shells import neutral_configuration

    for symbol in ("Po", "U"):
        configuration = neutral_configuration(symbol)
        widget = OrbitalBoxes()
        widget.resize(300, 60)
        widget.set_configuration(configuration)

        drawn = _labels_drawn_by(widget, monkeypatch)

        expected = {subshell.label for subshell in configuration.in_writing_order()}
        assert expected <= set(drawn), f"{symbol}: {sorted(expected - set(drawn))} never drawn"
        assert not any("incomplete" in text for text in drawn), (
            f"{symbol}: cried incomplete on a widget that had the room"
        )
        _dispose(widget)


class _DeniedItsHeight(OrbitalBoxes):
    """An `OrbitalBoxes` that never asks for the height it needs.

    **THE INVARIANT TURNED OUT TO BE SELF-RESTORING, which is why this
    class exists.** Two earlier versions of the test below tried to
    construct the violated state through the public API and could not:
    `resize()` is clamped to the widget's own minimum, and dropping the
    minimum first does not help either, because delivering the resize
    runs `resizeEvent`, which puts the minimum straight back and Qt grows
    the widget again. Measured: `grab()` on a widget resized to 120
    returned a 256-px image.

    That is the fix working. It also means the banner is unreachable in
    the running application, so the only honest way to exercise it is to
    model the one thing that could ever cause it -- a future layout that
    denies the widget the height it asks for.
    """

    def _apply_required_height(self) -> None:
        pass


def test_a_widget_denied_its_height_draws_everything_anyway_and_says_so(qapp, monkeypatch):
    """The violated invariant, on a widget that cannot heal itself.

    Two assertions, and they are different claims. Every label is still
    offered to the painter, which is what "there is no truncation branch"
    means -- restore one and the rows below the fold vanish from this
    list. And the banner appears, which is what stops a clipped drawing
    reading as a complete one.
    """
    from openchem.chem.electron_shells import neutral_configuration

    configuration = neutral_configuration("Po")
    widget = _DeniedItsHeight()
    widget.resize(300, 120)
    widget.set_configuration(configuration)

    assert widget.height() == 120, "the widget healed itself; the fixture proves nothing"
    assert widget.missing_row_count(300, 120) > 0, "fixture no longer violates anything"

    drawn = _labels_drawn_by(widget, monkeypatch)

    expected = {subshell.label for subshell in configuration.in_writing_order()}
    assert expected <= set(drawn), f"{sorted(expected - set(drawn))} never drawn"
    assert any("incomplete" in text for text in drawn), "clipped silently"
    _dispose(widget)


def _laid_out_widgets(layout) -> list:
    """Every widget a layout places, recursively through sub-layouts."""
    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            found.append(item.widget())
        elif item.layout() is not None:
            found.extend(_laid_out_widgets(item.layout()))
    return found


def test_the_orbital_view_is_in_something_that_can_scroll(qapp):
    """The half of the fix that lives outside `OrbitalBoxes`.

    A widget correctly asking for 256 px, inside a layout unwilling to
    give it any, is clipped rather than truncated -- the same picture for
    the reader.

    **ASKING THE LAYOUT, not the scroll area.** The first version checked
    `boxes_scroll.widget() is boxes`, which stays true when the scroll
    area is built and then never added to anything -- so putting the raw
    widget back in the layout SURVIVED. What has to hold is which of the
    two the layout actually places.
    """
    diagram = AtomDiagram()
    diagram.set_element("U")

    placed = _laid_out_widgets(diagram.layout())
    assert diagram.boxes_scroll in placed
    assert diagram.boxes not in placed, "the boxes bypass their scroll area"
    assert diagram.boxes_scroll.widget() is diagram.boxes
    assert diagram.boxes_scroll.widgetResizable()
    _dispose(diagram)


# --- A2: a synthetic element is drawn, not left blank -----------------------


def test_an_element_with_no_natural_isotope_says_why_it_has_no_neutron_count(diagram):
    """It used to say "Electrons: 84" and nothing else -- a fact about
    polonium stated as though the rest had failed to load."""
    diagram.set_element("Po")

    text = diagram.nucleus_label.text()
    assert "Protons: 84" in text
    assert "Electrons: 84" in text
    assert "no naturally occurring isotope" in text
    assert "Neutrons" not in text


def test_an_element_with_a_natural_isotope_still_names_it(diagram):
    """The control. Without it, deleting the neutron count everywhere
    would satisfy the test above."""
    diagram.set_element("Br")

    text = diagram.nucleus_label.text()
    assert "Neutrons: 44" in text
    assert "Br-79" in text


def test_the_shell_diagram_really_draws_a_nucleus_for_a_synthetic_element(qapp, monkeypatch):
    """**Asked of the PAINTER, because the defect was a blank centre.**

    The caption above is a different claim from what the drawing does:
    the label lives on `AtomDiagram` and the circle is painted by
    `ShellDiagram`, which received `None` and drew nothing at all. Ink
    alone cannot see this -- the rings and the background dominate -- so
    this asks which text the nucleus painted.
    """
    from openchem.chem.electron_shells import neutral_configuration, nucleus

    widget = ShellDiagram()
    widget.set_atom(neutral_configuration("Po").shells(), nucleus("Po"))

    drawn = _labels_drawn_by(widget, monkeypatch)

    assert "84p" in drawn, f"no nucleus was drawn; painter saw {drawn}"
    assert not any("n" in text and text != "84p" for text in drawn), (
        "a neutron count was drawn for an element that has none"
    )
    _dispose(widget)


#: Pixels of clear space required between two electrons on one ring.
#: Under the shipped worst case (uranium's N shell, 3.8 px) and well
#: over what a fixed-radius dot leaves there (0.5 px).
_MIN_ELECTRON_CLEARANCE = 2.0


# --- A5: a 32-electron shell must not draw as a solid band ------------------
#
# THREE DENSITY REGIMES, not "a heavy element". Hydrogen has one dot on
# one ring, bromine peaks at 18, and uranium at 32 across seven rings.
# One case cannot show that a scaling rule is a rule -- it can only show
# that a constant happened to suit it.

import pytest


@pytest.mark.parametrize("symbol", ["H", "Br", "Po", "U"])
def test_electrons_never_touch_on_any_ring(qapp, symbol):
    """Measured at the widget's OWN MINIMUM SIZE, which is the worst case.

    A fixed 5 px radius left uranium's N shell with 0.5 px between dots --
    touching, which is what "the rings read as a solid band" means. The
    check is on the arc each electron has to itself, because that is what
    decides whether two of them meet: a big ring with many electrons can
    be roomier than a small ring with few.
    """
    import math

    from openchem.chem.electron_shells import neutral_configuration
    from openchem.ui.widgets.atom_diagram import electron_radius

    shells = neutral_configuration(symbol).shells()
    span = 220 / 2 - 16  # ShellDiagram's minimum size, less its margin
    rings = len(shells)

    for index, (_, electrons) in enumerate(sorted(shells.items()), start=1):
        radius = span * index / rings
        arc = 2 * math.pi * radius / electrons
        gap = arc - 2 * electron_radius(radius, electrons)
        # **A REAL GAP, not merely "not overlapping".** A fixed 5 px dot
        # leaves uranium's N shell 0.5 px of daylight, which satisfies
        # `2r < arc` and reads on screen as a solid band -- measured, that
        # mutation survived this test until the bound was a clearance
        # rather than an inequality. The shipped worst case is 3.8 px.
        assert gap >= _MIN_ELECTRON_CLEARANCE, (
            f"{symbol} shell {index}: {electrons} electrons at r={radius:.1f} "
            f"leave only {gap:.1f} px between them"
        )


def test_a_crowded_ring_gets_smaller_dots_than_an_empty_one(qapp):
    """The control for the test above, which a constant would also pass
    if the constant were merely small enough."""
    from openchem.ui.widgets.atom_diagram import (
        MAX_ELECTRON_RADIUS,
        electron_radius,
    )

    assert electron_radius(60.0, 32) < electron_radius(60.0, 8)
    assert electron_radius(60.0, 2) == MAX_ELECTRON_RADIUS


@pytest.mark.parametrize("symbol", ["H", "Br", "U"])
def test_every_shell_count_is_drawn(qapp, monkeypatch, symbol):
    """**NEVER SKIPPED**, which the first version was not.

    It dropped any label whose gap fell inside the nucleus disc -- the
    innermost shell of every element -- silently, in the one branch of
    this codebase written against silent omissions. A ring with no room
    inside it is labelled just outside instead.
    """
    from openchem.chem.electron_shells import neutral_configuration, nucleus

    shells = neutral_configuration(symbol).shells()
    widget = ShellDiagram()
    widget.resize(300, 300)
    widget.set_atom(shells, nucleus(symbol))

    drawn = _labels_drawn_by(widget, monkeypatch)

    for electrons in shells.values():
        assert str(electrons) in drawn, f"{symbol}: shell of {electrons} went unlabelled"
    _dispose(widget)


def test_the_ring_counts_are_the_shell_occupancies_and_not_something_else(qapp, monkeypatch):
    """Uranium is 2, 8, 18, 32, 21, 9, 2 -- a set distinctive enough that
    drawing the wrong quantity (shell numbers, say) cannot coincide."""
    from openchem.chem.electron_shells import neutral_configuration, nucleus

    widget = ShellDiagram()
    widget.resize(300, 300)
    widget.set_atom(neutral_configuration("U").shells(), nucleus("U"))

    drawn = _labels_drawn_by(widget, monkeypatch)

    assert {"2", "8", "18", "32", "21", "9"} <= set(drawn)
    _dispose(widget)
