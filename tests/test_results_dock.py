"""Results as a panel: the dock, and a reader that follows the selection.

**THE DIFFERENCE FROM `test_property_panel_results_window.py` IS THE
LIFETIME.** That file holds a reader opened FOR a molecule and closed when
the selection moves. This one holds a reader that is never closed, so the
molecule change is the interesting event rather than the terminal one --
carry across, drop the old molecule's results, restore where this molecule
was last read.
"""

from __future__ import annotations

import tempfile

import pytest
from PySide6.QtCore import QCoreApplication

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.pop_out_host import PopOutHost
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose


def _fact(label: str) -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )


def _report(report_id: str, name: str, uuid: str):
    return ReportResult(
        molecule_uuid=uuid,
        report_id=report_id,
        name=name,
        facts=(_fact(f"{name} value"),),
    )


class _Versions:
    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


# --- the wiring, which only the window can be wrong about --------------------


@pytest.fixture(scope="module")
def qapp_module():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(qapp_module):
    """ONE window for the file -- three QWebEngineViews apiece.

    Deliberately not closed: `tests/conftest.py` retains every MainWindow
    for the session because collecting one corrupts the heap.
    """
    services = build_service_container()
    settings = Settings(services.event_bus)
    with tempfile.TemporaryDirectory() as scratch:
        settings.set("plugins/project_directory", f"{scratch}/none")
        settings.set("plugins/user_directory", f"{scratch}/none")
        return MainWindow(services, settings, SessionManager())


def test_the_dock_holds_the_very_reader_the_panel_feeds(window):
    """**TESTING THE PIECES IS NOT TESTING THE WIRING**, which this
    repository has now recorded seven times. A `ResultsView` that works and
    a `PropertyPanel` that feeds one prove nothing about the dock showing
    the SAME object -- and a second, unfed reader in the dock renders an
    empty panel for a molecule with results in it, with every unit test
    green.
    """
    dock = next(d for d in window._right_docks if d.objectName() == "Results")
    hosts = dock.findChildren(PopOutHost)
    assert len(hosts) == 1, "the Results dock should hold exactly one pop-out host"
    readers = dock.findChildren(ResultsView)
    assert len(readers) == 1, f"expected one reader in the dock, found {len(readers)}"
    assert readers[0] is window._property_panel._attached_reader
    assert hosts[0].content() is readers[0]


def test_the_application_tells_the_reader_where_each_calculator_SITS(window):
    """The half `test_the_reader_orders_by_the_registrys_own_order` cannot see.

    That test proves the reader honours a registry position when it is given
    one. Nothing there notices if the APPLICATION stops giving it: the reader
    would fall back to ordering by display name, which is a plausible list
    that silently disagrees with the buttons in Properties -- on the shipped
    registry, Hansen Solubility Parameters ahead of Solubility.

    The supplier moved when the reader stopped being built by the panel, so
    this is asserted where it now happens.
    """
    registry = window._property_panel._calculator_registry
    assert window._results_view._display_order_of == registry.display_order


def test_the_dock_is_a_panel_in_the_analysis_group(window):
    """Beside Properties rather than in a group of its own: starting a
    calculation and reading one are the same task seen from two ends."""
    assert window._panel_rail.panel_ids().count("Results") == 1
    _title, group = window._panel_rail._panels["Results"]
    assert group == "analysis"


# --- following the selection, which is the panel's half ----------------------


@pytest.fixture
def wired(qapp):
    """A panel with a reader attached, and two molecules to move between."""
    bus = EventBus()
    engine = ChemistryEngine()
    versions = _Versions()
    panel = PropertyPanel(
        bus,
        CalculatorRegistry(),
        DescriptorService(bus, engine, calculator_registry=CalculatorRegistry()),
        engine,
        structure_version_of=versions,
    )
    first = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(first, "CCO")
    second = MoleculeModel(display_name="Benzene")
    engine.set_structure_from_smiles(second, "c1ccccc1")
    panel.set_project(ProjectModel(molecules=[first, second]))

    reader = ResultsView()
    panel.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=first.uuid))
    QCoreApplication.processEvents()
    yield panel, bus, reader, first, second
    dispose(reader)
    dispose(panel)


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def _select(bus, molecule):
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()


def test_a_result_reaches_the_dock_without_anyone_opening_it(wired):
    """The dock is not opened, so nothing can open it. It is fed."""
    panel, bus, reader, first, _second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    assert [r.report_id for r in reader.merged().reports] == ["a"]


def test_changing_molecule_carries_the_reader_across_rather_than_closing_it(wired):
    """**THE OPPOSITE OF WHAT THE WINDOW DOES, AND THE REASON THE TWO ARE
    NOT ONE CODE PATH.** `_on_molecule_selected` closes the per-molecule
    window; a dock cannot be closed, so it moves.
    """
    panel, bus, reader, first, second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    _select(bus, second)
    assert reader.molecule_uuid() == second.uuid
    # And the previous molecule's results are GONE rather than relabelled:
    # rendering them under this molecule's name is the same failure class as
    # a stale depiction drawn on the current structure.
    assert [r.report_id for r in reader.merged().reports] == []


def test_a_reader_arriving_at_a_populated_panel_restores_the_reading_position(wired):
    """0i's rule, asserted where it is reachable today.

    **THE REPORT CAN ONLY BE RESTORED WHILE IT EXISTS**, and that is the
    whole subtlety -- so the case is exercised where results are present at
    the moment the reader moves onto the molecule. Attaching a reader to a
    panel that already holds results is exactly that, and it is a real
    path rather than a contrivance: it is what happens whenever a reader
    is attached to a panel mid-session.

    The sibling test below records why the molecule-switch route cannot
    show this yet.
    """
    panel, bus, reader, first, _second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    _land(bus, _report("b", "Beta", first.uuid))
    reader.set_focus("b")

    arriving = ResultsView()
    panel.attach_reader(arriving)
    assert arriving.molecule_uuid() == first.uuid
    assert arriving.focus() == "b"
    dispose(arriving)


def test_coming_back_restores_the_filter_at_once_and_the_report_when_it_returns(wired):
    """**THE RESTORE CANNOT HAPPEN AT THE MOMENT OF THE SWITCH, AND THAT IS
    WHY IT IS NOT WRITTEN THAT WAY.**

    `_on_molecule_selected` calls `self._reports.clear()`, so coming back to
    a molecule finds its calculator results gone rather than stale: at that
    instant there is no report for the memory to restore and `recall`
    correctly falls back. A restore gated on "the molecule moved" therefore
    fires exactly once, at the one moment it cannot succeed -- which is
    dead, and mutation said so by changing no test at all.

    So the position stays outstanding until the remembered report is
    reachable. The FILTER comes back immediately, because 0i's fallback
    keeps it -- what somebody was searching FOR is not invalidated by a
    report going away.
    """
    panel, bus, reader, first, second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    _land(bus, _report("b", "Beta", first.uuid))
    reader.set_focus("b")
    reader._selector_search.setText("bet")

    _select(bus, second)
    assert reader.focus() == ""

    _select(bus, first)
    # Nothing has been recomputed yet, so the report genuinely is not there.
    assert [r.report_id for r in reader.merged().reports] == []
    assert reader.focus() == ""
    # The filter is back already.
    assert reader.view().selector_search == "bet"

    # ...and the report comes back the moment it exists again.
    _land(bus, _report("a", "Alpha", first.uuid))
    assert reader.focus() == ""
    _land(bus, _report("b", "Beta", first.uuid))
    assert reader.focus() == "b"


def test_the_restore_stops_asking_once_it_has_landed(wired):
    """The narrow half, and the only way to see it is to count the asking.

    Restoring on every arriving result gives the same ANSWER -- the memory
    tracks every move, so re-applying is idempotent -- and costs something
    no assertion on the outcome can detect: `apply_view` rewrites the fact
    search box, and `setText` puts the cursor at the end of a half-typed
    search. So the claim here is that it stops, not that it agrees.
    """
    panel, bus, reader, first, second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    reader.set_focus("a")
    _select(bus, second)
    _select(bus, first)
    _land(bus, _report("a", "Alpha", first.uuid))
    assert reader.focus() == "a", "setup: the restore should have landed by now"

    asked = []
    real = reader.apply_view
    reader.apply_view = lambda view: (asked.append(view), real(view))[1]
    _land(bus, _report("b", "Beta", first.uuid))
    _land(bus, _report("c", "Gamma", first.uuid))
    assert asked == [], f"the restore is still asking: {asked}"


def test_the_docked_readers_links_reach_the_panel_that_can_route_them(wired):
    """Both ends of this chain are guarded and the middle was not.

    `ResultsView` has tests saying it EMITS `link_activated`, and
    `main_window` has tests saying it ROUTES one. Nothing asserted that the
    docked reader's signal is connected to anything -- so every viewer
    action and every visualization Open button in the dock could be a
    silent no-op with the whole suite green. That is the defect 0g exists
    to remove, arriving through the one surface 0g did not have.

    Found by mutation rather than by review: deleting the connect passed
    132 tests.
    """
    panel, _bus, reader, _first, _second = wired
    seen = []
    panel.link_activated.connect(seen.append)
    sentinel = object()
    reader.link_activated.emit(sentinel)
    assert seen == [sentinel]


def test_a_result_landing_does_not_drag_the_reader_off_what_it_is_showing(wired):
    """The narrow half of the restore, and the one that keeps it usable.

    Every arriving result syncs the reader. Restoring a remembered position
    on each of those would move somebody who is reading, every time a
    calculator finished -- so the restore is gated on the molecule really
    having changed.
    """
    panel, bus, reader, first, _second = wired
    _land(bus, _report("a", "Alpha", first.uuid))
    _land(bus, _report("b", "Beta", first.uuid))
    reader.set_focus("a")
    _land(bus, _report("c", "Gamma", first.uuid))
    assert reader.focus() == "a"


def test_a_panel_with_no_reader_attached_is_completely_unmoved(qapp):
    """The dock belongs to the window, so the panel has to work without one
    -- in a test, and in any application that does not build it."""
    bus = EventBus()
    engine = ChemistryEngine()
    panel = PropertyPanel(
        bus,
        CalculatorRegistry(),
        DescriptorService(bus, engine, calculator_registry=CalculatorRegistry()),
        engine,
        structure_version_of=_Versions(),
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    panel.set_project(ProjectModel(molecules=[molecule]))
    assert panel._attached_reader is None
    _select(bus, molecule)
    _land(bus, _report("a", "Alpha", molecule.uuid))
    # The reports are still held, and nothing raised on the way.
    assert "a" in panel._reports
    dispose(panel)


def test_a_long_reason_in_the_reader_does_not_widen_the_window(window, qapp_module):
    """**THE LONG-VALUE PROBLEM MOVED HERE, AND FOUR GUARDS DID NOT.**

    The Properties panel had four tests on its spanning row -- it takes the
    whole width, across the dock's whole range, without pushing short values
    onto two lines. 2c removes that row, so the reader's summary line is the
    only surface in the application that renders a long value, and nothing
    had ever asked this question of it.

    Measured before writing this, on a 1366x768 window with a 275-character
    refusal focused: window minimum 1024 and results-dock minimum 182,
    IDENTICAL empty and loaded. It is the `_wrap_scrollable` from 2b that
    holds it -- the same wrapper added when the bare dock widened the window
    to 1474 px, 108 px past the smallest display this ships on.

    So this pins a property that already holds rather than reporting a bug,
    which is the honest reason to write it: four guards went away and this
    is what replaces them.
    """
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import AlertResult
    from openchem.events.events import AlertComputed

    reason = (
        "No pkasolver environment configured. Set the interpreter path under "
        "Tools > External Tools. The bundled environment was not found and no "
        "override is set, so the microspecies distribution cannot be computed "
        "for this structure. See the documentation for the supported versions."
    )
    # **THE WINDOW'S OWN STARTER MOLECULE, NOT A NEW ONE.** `add_molecule`
    # starts the real descriptor batch, and this file's window is
    # module-scoped and deliberately never closed -- so the batch outlives
    # the test and publishes into a deleted bus, which surfaces as
    # `RuntimeError: Signal source has been deleted` inside whichever
    # unrelated test is pumping events. Measured: adding one here turned a
    # clean file into a red one at teardown.
    molecule_uuid = window._property_panel._selected_molecule_uuid
    assert molecule_uuid, "setup: the window has no molecule selected"
    window.resize(1366, 768)
    QCoreApplication.processEvents()

    before_window = window.minimumSizeHint().width()
    before_dock = window._results_dock.minimumSizeHint().width()

    window._services.event_bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pka", name="pKa", molecule_uuid=molecule_uuid, matched=[],
                category="pka", cache_state=CacheState.FAILED, error=reason,
                provenance=Provenance(created_by="core", method="pkasolver"),
            )
        )
    )
    QCoreApplication.processEvents()
    window._results_view.set_focus("pka")
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()

    # THE CONTROL. A reader that never received the reason cannot be widened
    # by it, and would pass this happily.
    shown = window._results_view._summary_for(
        window._results_view.merged().report_for("pka")
    )
    assert reason in shown, f"the reason never reached the reader: {shown[:120]!r}"

    assert window.minimumSizeHint().width() == before_window, (
        f"a {len(reason)}-character reason moved the window's minimum from "
        f"{before_window} to {window.minimumSizeHint().width()}"
    )
    assert window._results_dock.minimumSizeHint().width() == before_dock
