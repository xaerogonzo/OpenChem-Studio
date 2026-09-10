"""Opening the whole result from the reader that shows a summary of it.

Stage 1d. 1a made every result kind reachable AS A SUMMARY, which without
this is a dead end: measured over the registry on aspirin, **60 entries reach
the reader and 30 of them declare a viewer** -- exactly the half that arrives
as a summary rather than as a report.

**THE ACTION BELONGS TO THE RESULT, NOT TO A FACT ROW.** A summary's facts
are projections -- a count, a range, a declared total -- and none of them IS
the result, so "the first fact carries the link" would strip the viewer from
precisely the entries that need it. `FactLink` is still the carrier, because
the outcome vocabulary is the same three answers and there is one router.

**AND THE FACT-LEVEL HALF HAS NO LIVE INSTANCE**, measured: 0 of the reader's
facts carry a `FactLink` today. `FactView` builds the button and emits the
signal, and this window never connected it -- so it is guarded on the WIRING,
which is where an unreachable branch belongs.
"""

from __future__ import annotations

import pytest

from openchem.domain.report import (
    Basis,
    Fact,
    FactCategory,
    FactLink,
    ReportResult,
)
from openchem.ui.dialogs.merged_results_dialog import (
    MergedResultsDialog,
    _VIEWER_ACTIONS,
)
from openchem.ui.result_summary import ResultSummaryView
from tests.conftest import dispose

MOLECULE = "mol-1"


def _fact(label: str, link: FactLink | None = None) -> Fact:
    kwargs = dict(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )
    if link is not None:
        kwargs["link"] = link
    return Fact(**kwargs)


def _report(report_id="elemental_analysis", name="Elemental Analysis", facts=("Formula",)):
    return ReportResult(
        molecule_uuid=MOLECULE,
        report_id=report_id,
        name=name,
        category="identity",
        facts=tuple(_fact(f) for f in facts),
    )


def _summary(report_id="charges", name="Partial Charge", rich_view="calculator_inspector"):
    return ResultSummaryView(
        report_id=report_id,
        name=name,
        category="electronic",
        facts=(_fact("Atoms"),),
        rich_view=rich_view,
        molecule_uuid=MOLECULE,
    )


@pytest.fixture
def window(qapp):
    w = MergedResultsDialog(MOLECULE, "Aspirin")
    yield w
    dispose(w)


# --- the summary carries the adapter's answer ----------------------------


def test_a_summarised_result_carries_the_viewer_that_opens_the_whole_thing():
    """**COPIED ONCE AT PROJECTION TIME, NEVER RE-DERIVED.** A view is not the
    result, so a consumer holding one cannot ask it what kind the result was;
    a second derivation would be a second place for the two to disagree."""
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.ui.result_adapters import CALCULATOR_INSPECTOR, summarise

    result = PerAtomDataset(
        property_id="p", name="P", units="e", method="m",
        molecule_uuid=MOLECULE, values={0: 1.0},
    )
    view = summarise(result, result_id="p", name="P", category="electronic")
    assert view.rich_view == CALCULATOR_INSPECTOR


def test_a_report_declares_no_viewer_because_it_is_already_the_whole_thing():
    """The narrow half. A `ReportResult` passes through `summarise` unchanged
    and is what the reader renders in full, so there is nothing to open --
    and a default of "some viewer" would put a button on all 30 of them."""
    from openchem.ui.result_adapters import summarise

    passed_through = summarise(
        _report(), result_id="elemental_analysis", name="Elemental Analysis",
        category="identity",
    )
    assert not getattr(passed_through, "rich_view", "")


# --- the button appears exactly where it can work ------------------------


def test_the_button_offers_the_viewer_when_the_focused_entry_has_one(window):
    window.set_reports([_summary()])
    window.set_focus("charges")
    assert window._open_button.isVisibleTo(window)
    assert window._open_button.text() == _VIEWER_ACTIONS["calculator_inspector"].label


def test_the_button_is_absent_for_an_entry_that_is_already_the_whole_result(window):
    window.set_reports([_report()])
    window.set_focus("elemental_analysis")
    assert not window._open_button.isVisibleTo(window)


def test_the_button_is_absent_on_all_results_because_no_viewer_owns_a_merge(window):
    """Several producers at once. Opening "all of them" names no destination,
    and picking one of the six would be the window choosing for the reader."""
    window.set_reports([_summary(), _report()])
    window.set_focus("")
    assert not window._open_button.isVisibleTo(window)


def test_the_button_is_absent_when_nothing_has_been_computed(window):
    window.set_reports([])
    assert not window._open_button.isVisibleTo(window)


def test_a_viewer_this_window_cannot_reach_offers_NO_button(window):
    """**THE NARROW HALF, AND IT IS THE LOAD-BEARING ONE.**

    A kind may declare a viewer that is not a destination anything can route
    to -- `ir_view` is one: `IrViewWidget` is a tab inside the Quantum
    Chemistry panel rather than a viewer a single result is handed to. A
    truthiness test on the declared target draws a button for it, labelled by
    a `.get` fallback and answered by the router with "unknown target".

    A control that cannot work is worse than an absent one, and this is a
    different claim from 0g's rule that a link somebody DECLARED must never
    be a silent no-op.
    """
    window.set_reports([_summary(report_id="ir", name="IR", rich_view="ir_view")])
    window.set_focus("ir")
    assert "ir_view" not in _VIEWER_ACTIONS, "the premise of this guard"
    assert not window._open_button.isVisibleTo(window)


# --- what pressing it asks for -------------------------------------------


def test_pressing_it_asks_for_the_REPORT_rather_than_a_fact(window):
    """A fact link says "where did this VALUE come from"; this says "show me
    the result this is a summary OF". One signal, because both are the same
    three outcomes answered by the same router."""
    seen = []
    window.link_activated.connect(seen.append)
    window.set_reports([_summary()])
    window.set_focus("charges")
    window._open_button.click()

    assert len(seen) == 1
    link = seen[0]
    assert isinstance(link, FactLink)
    assert link.target == "calculator_inspector"
    assert link.params == {"report_id": "charges"}


def test_pressing_it_on_an_unreachable_viewer_asks_for_nothing(window):
    """The button is hidden there, so this can only be reached by calling the
    handler -- which must still refuse rather than emit a target the router
    would answer with a diagnostic."""
    seen = []
    window.link_activated.connect(seen.append)
    window.set_reports([_summary(report_id="ir", name="IR", rich_view="ir_view")])
    window.set_focus("ir")
    window._on_open_clicked()
    assert seen == []


# --- the fact-level half, guarded on the wiring --------------------------


def test_a_facts_own_link_reaches_the_window_that_can_route_it(window):
    """**DEAD IN THIS READER UNTIL 1d.** `FactView` builds a `>` button per
    linked fact and emits `link_activated`; the Atom Inspector routes it and
    this window never connected it, so a link here rendered a control and did
    nothing.

    Asserted through the VIEW's signal rather than by clicking, because
    measured over the registry **no result reaching this reader carries a
    `FactLink` today** -- so there is no end-to-end route to drive, and the
    claim worth pinning is that one exists when a producer emits one.
    """
    seen = []
    window.link_activated.connect(seen.append)
    link = FactLink(target="periodic_table", params={"symbol": "C"})
    window._view.link_activated.emit(link)
    assert seen == [link]


# --- and the reader is refused visibly rather than silently --------------


def test_a_result_no_longer_held_is_refused_rather_than_doing_nothing(qapp, tmp_path):
    """`open_retained_result` answers FALSE for an id it does not hold, which
    is what makes the router's UNAVAILABLE outcome a visible message. "This
    molecule's results were cleared" is precisely the state a reader needs
    told about rather than a button that does nothing."""
    from openchem.ui.panels.property_panel import PropertyPanel

    panel = PropertyPanel.__new__(PropertyPanel)
    panel._retained_results = {}
    assert panel.open_retained_result("nothing-here") is False


# --- the five the mutation pass found, and four are one shape ------------
#
# D6, D8, D9, D10 and D11 all SURVIVED a first pass against 189 green tests,
# and not one was an equivalent mutation. Four of them are the same failure:
# the PIECES were tested and the WIRING between them was not, which is the
# lesson this project has recorded five times over. D11 is the other kind --
# a fixture too degenerate to see its own subject.


def _panel(qapp):
    """The cheapest real panel that runs `_show_result`.

    Built here rather than imported from `test_property_panel_result_rows`
    so this file's guards do not depend on another file's fixture, which is
    how a shared fixture change quietly disarms a guard somewhere else.
    """
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeSelected
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.ui.panels.property_panel import PropertyPanel

    class _FakeService:
        def run_calculator(self, model, request) -> None:
            pass

    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
    return bus, panel


def _per_atom_event(molecule_uuid=MOLECULE):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.events.events import PerAtomDataComputed

    return PerAtomDataComputed(
        dataset=PerAtomDataset(
            property_id="charges", name="Partial Charge", units="e", method="gasteiger",
            molecule_uuid=molecule_uuid, values={0: 0.1, 1: -0.1},
            provenance=Provenance(created_by="core", method="gasteiger"),
        )
    )


def test_the_panel_keeps_the_result_behind_the_summary(qapp):
    """**D6.** The reader holds a VIEW, so "open this properly" has to come
    back to whoever kept the result -- and this panel used to open the
    inspector immediately and drop the object, so nothing held it once the
    dialog closed. Asserted through the BUS, which is how a result really
    arrives, rather than by calling `_show_result`."""
    bus, panel = _panel(qapp)
    try:
        bus.publish(_per_atom_event())
        assert "charges" in panel._reports, "the summary, as before"
        assert "charges" in panel._retained_results, "and the result itself"
        assert panel._retained_results["charges"].values == {0: 0.1, 1: -0.1}
    finally:
        dispose(panel)


def test_the_kept_result_is_cleared_with_its_summary(qapp):
    """**D8.** A raw result outliving its molecule is the stale-result
    confusion in a new place: the reader would open the PREVIOUS molecule's
    data under this one's name, and every guard on the summaries would stay
    green because the summaries were cleared correctly."""
    from openchem.events.events import MoleculeSelected

    bus, panel = _panel(qapp)
    try:
        bus.publish(_per_atom_event())
        assert panel._retained_results, "the fixture must retain something first"
        bus.publish(MoleculeSelected(molecule_uuid="a-different-molecule"))
        assert not panel._reports
        assert not panel._retained_results, (
            "a result kept past its molecule opens under the wrong name"
        )
    finally:
        dispose(panel)


def test_switching_back_to_all_results_takes_the_button_down(window):
    """**D11, AND THE FIRST FIXTURE FOR IT WAS DEGENERATE.**

    `test_the_button_is_absent_on_all_results...` sets the focus to "" on a
    window whose button was never shown -- so the assertion holds against a
    render path that does nothing at all, and dropping `_sync_open_button`
    from the all-results branch left it green.

    The discriminating case has to make the button VISIBLE first, which is
    also the only sequence a reader performs: focus a summarised result,
    then go back to everything.
    """
    window.set_reports([_summary(), _report()])
    window.set_focus("charges")
    assert window._open_button.isVisibleTo(window), "setup: the button must be up"

    window.set_focus("")
    assert not window._open_button.isVisibleTo(window)
