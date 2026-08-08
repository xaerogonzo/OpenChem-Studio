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


def test_an_empty_box_view_draws_nothing_but_background(qapp):
    widget = OrbitalBoxes()
    widget.set_configuration(None)

    assert ink(widget) == 0
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
