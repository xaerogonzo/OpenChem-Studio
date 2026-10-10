"""Workflow sections: a workflow hosted in Properties, or said to be in its own tab.

The mechanism (`PropertyPanel.add_workflow`, `WorkflowBody`) is tested here with a
plain widget, so it is the mechanism that is checked and not docking or alignment:

* a section is collapsed, sits above the calculators, and is not a calculator;
* it holds the workflow while the workflow is HERE, and says where it went when it
  is in its tab, with the buttons to bring it back;
* the widget handed in comes back out as the SAME OBJECT, which is what makes a move
  a move and not a rebuild;
* Find finds it by its keywords and puts back what it opened.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QWidget

import conftest
from openchem.bootstrap import build_service_container
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.workflow_body import HOME_PROPERTIES, HOME_TAB


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _properties(services, built) -> PropertyPanel:
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
        structure_version_of=services.structure_check_service.current_version,
    )
    built.append(panel)
    return panel


# --- the section ----------------------------------------------------------------------


def test_a_workflow_is_a_collapsed_section_above_the_calculators(services, built):
    panel = _properties(services, built)

    section = panel.add_workflow("demo", "Demo workflow", keywords="demo")

    assert panel.workflow_section("demo") is section
    assert not section.is_expanded()
    layout = panel._sections_layout
    first = layout.itemAt(0).widget()
    assert first is panel._workflow_header and first.text() == "Workflows"
    assert layout.itemAt(1).widget() is section
    assert any(
        layout.itemAt(i).widget() is s for i in range(2, layout.count()) for s in panel._sections.values()
    )


def test_a_workflow_is_not_a_calculator(services, built):
    """No tick box and no place in "Run selected": a workflow has a Run of its own."""
    panel = _properties(services, built)
    before = set(panel._calculator_ticks)

    panel.add_workflow("demo", "Demo workflow")

    assert set(panel._calculator_ticks) == before
    assert "demo" not in panel._calculator_rows


# --- the two homes ----------------------------------------------------------------------


def test_a_workflow_in_its_tab_says_so_and_offers_the_way_back(services, built):
    panel = _properties(services, built)
    panel.add_workflow("demo", "Demo workflow")
    body = panel.workflow_body("demo")

    assert panel.workflow_home("demo") == HOME_TAB
    assert body.widget() is None
    assert not body._note.isHidden() and "own tab" in body._note.text()
    assert not body._move_here.isHidden() and not body._open_tab.isHidden()
    assert body._move_to_tab.isHidden()


def test_a_workflow_here_holds_its_widget_and_offers_to_leave(services, built):
    panel = _properties(services, built)
    widget = QLabel("the workflow")

    section = panel.add_workflow("demo", "Demo workflow", home=HOME_PROPERTIES, widget=widget)
    body = panel.workflow_body("demo")

    assert panel.workflow_home("demo") == HOME_PROPERTIES
    assert body.widget() is widget
    assert section.isAncestorOf(widget)
    assert body._note.isHidden()
    assert not body._move_to_tab.isHidden()
    assert body._move_here.isHidden() and body._open_tab.isHidden()


def test_the_widget_that_leaves_is_the_widget_that_arrived(services, built):
    """A move, not a rebuild: the same object, so every value it holds comes along."""
    panel = _properties(services, built)
    widget = QLabel("the workflow")
    widget.setProperty("typed", "value the person set")
    panel.add_workflow("demo", "Demo workflow", home=HOME_PROPERTIES, widget=widget)

    released = panel.release_workflow("demo")

    assert released is widget
    assert released.parent() is None
    assert panel.workflow_home("demo") == HOME_TAB
    assert panel.workflow_body("demo").widget() is None

    panel.adopt_workflow("demo", released)

    assert panel.workflow_body("demo").widget() is widget
    assert panel.workflow_home("demo") == HOME_PROPERTIES
    assert widget.property("typed") == "value the person set"


def test_releasing_a_workflow_that_is_not_here_gives_nothing(services, built):
    panel = _properties(services, built)
    panel.add_workflow("demo", "Demo workflow")

    assert panel.release_workflow("demo") is None


def test_a_widget_without_a_parent_is_owned_by_the_section(services, built):
    panel = _properties(services, built)
    widget = QWidget()

    section = panel.add_workflow("demo", "Demo", home=HOME_PROPERTIES, widget=widget)

    assert widget.parent() is not None
    assert section.isAncestorOf(widget)


# --- what the buttons ask for ------------------------------------------------------------


def test_the_buttons_ask_the_window_to_move_the_workflow(services, built):
    panel = _properties(services, built)
    panel.add_workflow("demo", "Demo workflow")
    asked: list[tuple[str, str]] = []
    opened: list[str] = []
    panel.workflow_move_requested.connect(lambda wid, home: asked.append((wid, home)))
    panel.workflow_tab_requested.connect(lambda wid: opened.append(wid))
    body = panel.workflow_body("demo")

    body._move_here.click()
    body._open_tab.click()
    panel.adopt_workflow("demo", QLabel("x"))
    body._move_to_tab.click()

    assert asked == [("demo", HOME_PROPERTIES), ("demo", HOME_TAB)]
    assert opened == ["demo"]


def test_the_panel_asks_and_does_not_move_anything_itself(services, built):
    """The window owns the rail and the docks, so it does the moving."""
    panel = _properties(services, built)
    panel.add_workflow("demo", "Demo workflow")

    panel.workflow_body("demo")._move_here.click()

    assert panel.workflow_home("demo") == HOME_TAB


# --- Find ------------------------------------------------------------------------------


def test_find_matches_a_workflow_by_its_keywords_and_puts_it_back(services, built):
    panel = _properties(services, built)
    section = panel.add_workflow("demo", "Demo workflow", keywords="superimpose overlay")

    panel._find_box.setText("overlay")
    assert not section.isHidden() and section.is_expanded()
    assert not panel._workflow_header.isHidden()

    panel._find_box.setText("zzz-no-such-thing")
    assert section.isHidden()
    assert panel._workflow_header.isHidden()

    panel._find_box.setText("")
    assert not section.isHidden()
    assert not section.is_expanded(), "Find must put back the expansion it found"
    assert not panel._workflow_header.isHidden()


def test_find_for_a_calculator_hides_a_workflow_that_does_not_match(services, built):
    panel = _properties(services, built)
    section = panel.add_workflow("demo", "Demo workflow", keywords="overlay")

    panel._find_box.setText("logp")

    assert section.isHidden()


def test_revealing_a_workflow_opens_it_even_when_find_had_hidden_it(services, built):
    panel = _properties(services, built)
    section = panel.add_workflow("demo", "Demo workflow", keywords="overlay")
    panel._find_box.setText("logp")
    assert section.isHidden()

    panel.reveal_workflow("demo")

    assert not section.isHidden() and section.is_expanded()
    assert panel._find_box.text() == ""
