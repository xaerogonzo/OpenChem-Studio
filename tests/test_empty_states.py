"""Every blank surface must say why it is blank.

There was **no empty-state text anywhere in `ui/`** before this: a search
for any placeholder string across the whole package matched two files,
neither a panel. So a tab with no data for the current job showed nothing,
and "not run yet", "ran and found nothing", "failed" and "not applicable
to this calculation" were all rendered identically as emptiness.

THESE TESTS ITERATE OVER WHAT THE PANEL ACTUALLY BUILDS, never over a
list of tabs kept alongside it. That direction is the whole point: a list
can only check the tabs somebody remembered to add to it, and the two
panels that shipped with no help topic were invisible to two guards for
exactly that reason -- both walked the map instead of the docks.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QTableWidget, QTabWidget, QWidget

from openchem.ui.widgets.empty_state import empty_state, empty_state_text, is_empty_state

import conftest


def _dispose(widget) -> None:
    """Destroy a widget deterministically, per CLAUDE.md.

    A test that builds a panel and walks away leaves it to be collected at
    an arbitrary later moment -- inside an unrelated test, from within
    Qt's event dispatch -- which is a Windows access violation. Flushed
    per widget, never with the global `sendPostedEvents(None, ...)` form,
    which drains deletes other files queued.
    """
    conftest.dispose(widget)


@pytest.fixture
def quantum_panel(qapp):
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container
    from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

    container = build_service_container()
    # `Settings` is constructed inside bootstrap rather than published on
    # the container, so the panel's own caller builds one. The autouse
    # `isolated_settings` fixture keeps it off the real registry.
    panel = QuantumChemistryPanel(
        container.quantum_chemistry_service,
        container.chemistry_engine,
        Settings(container.event_bus),
        container.event_bus,
    )
    yield panel
    _dispose(panel)


def test_every_tab_the_quantum_panel_builds_explains_itself(quantum_panel):
    """The seven tabs Alex found blank: 1D Signals, IR, Surfaces, Hybrid,
    HSQC, HMBC, COSY. One ESP single point lights up Surfaces and leaves
    the other six untouched, which is correct behaviour that looked
    exactly like breakage.

    Asks the panel what each tab SHOWS, which it derives from its own
    widgets -- so a tab carrying its message in a placeholder label, in
    an existing summary label, or painted into a plot all count, and a
    tab showing nothing fails whichever mechanism it was meant to use.
    """
    tabs = quantum_panel.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() >= 7, f"expected the seven correlation tabs, found {tabs.count()}"

    for index in range(tabs.count()):
        message = quantum_panel.empty_message_for_tab(index)
        assert message.strip(), (
            f'the "{tabs.tabText(index)}" tab says nothing when it is empty -- '
            "it will render as a blank rectangle with no explanation"
        )


def test_an_empty_state_says_what_to_do_not_just_that_it_is_empty(quantum_panel):
    """"No data" tells the reader something they can already see. The
    second sentence is the one that earns the words their place."""
    tabs = quantum_panel.findChild(QTabWidget)
    for index in range(tabs.count()):
        message = quantum_panel.empty_message_for_tab(index)
        assert len(message.split()) >= 8, (
            f'the "{tabs.tabText(index)}" tab says "{message}" but not what '
            "would fill it"
        )


def test_a_deferred_tab_swaps_its_placeholder_for_the_content(quantum_panel):
    """Only the three deferred tabs carry a placeholder WIDGET, and it is
    retired when their real content arrives.

    Asserted with `isHidden()`, not `isVisible()`. **`isVisible()` is
    False for every child of a parent that was never shown**, so it gives
    the same answer in both arms and the test could not fail -- the same
    blindness as a `repaint()` on a widget that was never shown.
    """
    tabs = quantum_panel.findChild(QTabWidget)
    surfaces = next(
        tabs.widget(i) for i in range(tabs.count()) if tabs.tabText(i) == "Surfaces"
    )
    state = next(w for w in surfaces.findChildren(QWidget) if is_empty_state(w))

    assert not state.isHidden(), "the placeholder should start visible"
    quantum_panel._fill_tab(surfaces)
    assert state.isHidden()
    quantum_panel._reset_empty_states()
    assert not state.isHidden()


def test_a_correlation_plot_says_so_when_it_has_no_peaks(qapp):
    """The correlation tabs paint their message instead of adding a
    placeholder widget -- axes drawn around nothing read as broken."""
    from openchem.ui.widgets.nmr_correlation_plot_widget import NmrCorrelationPlotWidget

    plot = NmrCorrelationPlotWidget()
    plot.set_empty_message("No HSQC cross peaks yet.")
    assert "HSQC" in plot.empty_message()
    _dispose(plot)


def test_set_message_updates_both_lines(qapp):
    from openchem.ui.widgets.empty_state import set_empty_state_message

    state = empty_state("first", "then")
    set_empty_state_message(state, "changed", "differently")
    assert "changed" in empty_state_text(state)
    assert "differently" in empty_state_text(state)
    _dispose(state)


def test_a_headline_with_html_characters_is_not_swallowed(qapp):
    """These render as rich text, and a chemical name can legitimately
    contain `<` or `&`. Unescaped, everything after the `<` disappears."""
    state = empty_state("No data for (E)-but-2-ene <or> anything else", "")
    assert "<or>" in empty_state_text(state)
    assert "&lt;or&gt;" in state.text()
    _dispose(state)


# --- the log must not outrank the results -----------------------------------


def test_the_log_is_the_last_tab_not_the_biggest_widget(quantum_panel):
    """`_output_log` is a `QPlainTextEdit`, whose default Expanding policy
    took the largest share of the panel -- so a finished calculation showed
    a wall of scrolling SCF iterations above a cramped band of the numbers
    somebody ran it for.

    It is a tab now, and LAST -- "results outrank the log" is an ordering
    claim as much as a layout one.
    """
    tabs = quantum_panel.findChild(QTabWidget)
    assert tabs.tabText(tabs.count() - 1) == "Log"
    assert tabs.widget(tabs.count() - 1) is quantum_panel._output_log

    layout = quantum_panel.layout()
    direct = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert quantum_panel._output_log not in direct, (
        "the log is back in the panel's own layout, where its Expanding "
        "policy outranks the results"
    )


def test_the_log_is_shown_while_a_job_runs_and_the_results_sit_above_it(quantum_panel):
    """A panel that sits silent through a ten-minute ORCA run reads as a
    hang, so the log is what you are looking at while there is nothing
    else -- and is not what you are left staring at once there is."""
    from openchem.events.events import QuantumChemistryJobStateChanged

    class _State:
        def __init__(self, value):
            self.value = value

    tabs = quantum_panel.findChild(QTabWidget)
    quantum_panel._pending_molecule_uuid = "m1"

    quantum_panel._on_job_state_changed(
        QuantumChemistryJobStateChanged(molecule_uuid="m1", state=_State("running"), message="")
    )
    assert tabs.currentWidget() is quantum_panel._output_log

    # Nothing is forced on success. The numbers land in `_results_label`,
    # which is ABOVE the tabs and always visible, and each result handler
    # selects its own tab when it has something -- being yanked to a tab
    # reading "no NMR signals yet" after an ESP run would be worse than
    # staying put.
    quantum_panel._on_job_state_changed(
        QuantumChemistryJobStateChanged(molecule_uuid="m1", state=_State("completed"), message="")
    )
    layout = quantum_panel.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order.index(quantum_panel._results_label) < order.index(tabs)


def test_a_failed_job_leaves_you_on_the_log(quantum_panel):
    """The log is where the reason is, and every other tab is empty for a
    job that produced nothing."""
    from openchem.events.events import QuantumChemistryJobStateChanged

    class _State:
        def __init__(self, value):
            self.value = value

    tabs = quantum_panel.findChild(QTabWidget)
    quantum_panel._pending_molecule_uuid = "m1"
    quantum_panel._on_job_state_changed(
        QuantumChemistryJobStateChanged(molecule_uuid="m1", state=_State("failed"), message="boom")
    )
    assert tabs.currentWidget() is quantum_panel._output_log
