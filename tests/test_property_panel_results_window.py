"""The merged results window, driven through the panel that owns it.

**LIFECYCLE, NOT MERGING.** `test_merged_results_dialog.py` holds the
window's own behaviour; this file holds the things only the panel can be
wrong about -- which window exists, when it is fed, and what happens when
it closes. An ordinary Qt lifetime bug is exactly the class the merge
being correct cannot catch, and this repository has paid for the
self-capturing-lambda form of it four times.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.merged_results_dialog import STALE_MARK
from openchem.ui.panels.property_panel import PropertyPanel
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


def _report(report_id: str, name: str, label: str, uuid: str, version: int = 0):
    return ReportResult(
        molecule_uuid=uuid,
        report_id=report_id,
        name=name,
        facts=(_fact(label),),
        structure_version=version,
    )


class _Versions:
    """A stand-in for `StructureCheckService.current_version`.

    A callable rather than the service, which is what the panel takes --
    so a fixture does not have to build a checker to have a version."""

    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    versions = _Versions()
    widget = PropertyPanel(
        bus,
        CalculatorRegistry(),
        DescriptorService(bus, engine, calculator_registry=CalculatorRegistry()),
        engine,
        structure_version_of=versions,
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    project = ProjectModel(molecules=[molecule])
    widget.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    yield widget, bus, molecule, project, versions
    dispose(widget)


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def test_one_window_per_molecule_and_asking_twice_reuses_it(panel):
    """**KEYED ON THE UUID, NOT ON OBJECT IDENTITY.** Two windows for one
    molecule is how a reader ends up comparing a result with itself, and
    only one of them would be receiving updates."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    first = widget._results_window
    widget._open_results_window()
    assert widget._results_window is first
    first.close()


def test_a_second_molecule_gets_a_second_window(panel):
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    first = widget._results_window
    assert first.molecule_uuid() == molecule.uuid

    other = MoleculeModel()
    ChemistryEngine().set_structure_from_smiles(other, "CCC")
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    _land(bus, _report("a", "A", "Formula", other.uuid))
    widget._open_results_window()
    second = widget._results_window
    assert second is not None
    assert second.molecule_uuid() == other.uuid
    second.close()


def test_a_result_arriving_updates_the_OPEN_window(panel):
    """**THE FEATURE, NOT THE MERGE.** Proving a freshly-opened window can
    merge is easy and is not the complaint: the window has to accumulate
    while it is open, which is why it is modeless in the first place."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    assert [f.label for f in window.merged().facts] == ["Formula"]

    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid))
    assert [f.label for f in window.merged().facts] == ["Formula", "Donor sites"]
    window.close()


def test_the_stale_marks_follow_the_structure_in_an_open_window(panel):
    widget, bus, molecule, _project, versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid, version=0))
    widget._open_results_window()
    window = widget._results_window
    assert STALE_MARK not in window._focus_box.itemText(1)

    versions.version = 3
    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid, version=3))
    labels = [window._focus_box.itemText(i) for i in range(window._focus_box.count())]
    assert "Elemental Analysis" + STALE_MARK in labels
    assert "Lewis Sites" in labels
    window.close()


def test_closing_the_window_disconnects_it(panel):
    """**A CLOSED WINDOW MUST NOT KEEP RECEIVING RESULTS.** Writing into a
    deleted widget is the ordinary Qt lifetime bug that correctness of the
    merge cannot catch -- and the handle has to be dropped, or the next
    open would raise on a dead C++ object."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    window.close()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    assert widget._results_window is None

    # Another result lands with no window open: nothing to write into, and
    # nothing may raise.
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    assert widget._results_window is None


def test_reopening_after_a_close_gives_a_live_window_and_not_a_duplicate(panel):
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    widget._results_window.close()
    QCoreApplication.processEvents()

    widget._open_results_window()
    reopened = widget._results_window
    assert reopened is not None
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    assert len(reopened.merged().facts) == 2
    reopened.close()


def test_selecting_another_molecule_closes_a_window_that_no_longer_describes_it(panel):
    """A window left open would show the previous molecule's results under
    the new molecule's name."""
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    assert widget._results_window is not None

    other = MoleculeModel()
    ChemistryEngine().set_structure_from_smiles(other, "CCC")
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    assert widget._results_window is None


def test_the_window_is_modeless_so_the_panel_stays_usable(panel):
    """The old dialog used `exec()`, which blocks -- and with the panel
    blocked you could never run the second calculator whose results the
    window exists to accumulate."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    assert not window.isModal()
    window.close()


def test_an_alert_derived_report_is_not_born_stale(panel):
    """**FOUND BY DRIVING THE APP, WITH EVERY TEST GREEN.**
    `_CalculationTask` stamps a `ReportResult` on the way out of a
    calculation -- but an `AlertResult` is not one, has no version field to
    carry, and is reconstructed into a report by the panel at arrival. Left
    unstamped it defaults to 0 and reads as stale the moment the structure
    is on any version above that.

    On screen that was `Functional Groups` wearing a stale badge alone,
    from the first molecule, forever -- while every registry calculator
    beside it read current. Every test in this suite passed throughout,
    because they all construct reports with an explicit version.
    """
    from openchem.domain.scientific_result import AlertResult
    from openchem.events.events import AlertComputed

    widget, bus, molecule, _project, versions = panel
    versions.version = 4
    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="functional_groups",
                name="Functional Groups",
                molecule_uuid=molecule.uuid,
                matched=["Carboxylic acid: 1"],
                category="substructure",
            )
        )
    )
    QCoreApplication.processEvents()

    widget._open_results_window()
    window = widget._results_window
    assert window.merged().stale_report_ids() == (), (
        "a report that has just arrived describes the structure it arrived for"
    )
    window.close()


# --- the auto-descriptors reach the reader -------------------------------
#
# They are `DescriptorValue`s rather than `ScientificResult`s, so before the
# aggregate existed they reached the reader's fact model NOT AT ALL -- the
# single largest thing computed for a molecule that this window could not
# show. See `domain/descriptor_aggregate.py` for why it holds the originals.


def _descriptor(bus, molecule, descriptor_id, **kwargs):
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.events.events import DescriptorComputed

    defaults = dict(
        descriptor_id=descriptor_id,
        name=descriptor_id.replace("_", " ").title(),
        units="",
        category="physicochemical",
        provider="rdkit",
        molecule_uuid=molecule.uuid,
        cache_state=CacheState.COMPLETED,
    )
    defaults.update(kwargs)
    bus.publish(DescriptorComputed(descriptor=DescriptorValue(**defaults)))
    QCoreApplication.processEvents()


def test_the_descriptors_reach_the_results_window_as_one_entry(panel):
    """ONE entry, not forty-one. The window's selector is the surface this
    would otherwise flood."""
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", units="g/mol", value=46.07)
    _descriptor(bus, molecule, "tpsa", name="TPSA", units="A^2", value=20.23)
    widget._open_results_window()

    merged = widget._results_window.merged()
    ids = [r.report_id for r in merged.reports]
    assert ids.count(DESCRIPTOR_AGGREGATE_ID) == 1, f"expected one aggregate, got {ids}"
    labels = {f.label for f in merged.facts}
    assert {"Molecular Weight", "TPSA"} <= labels
    dispose(widget._results_window)


def test_a_failed_descriptor_keeps_its_own_state_in_the_window(panel):
    """The reason the aggregate is a container. A molecule drawn flat fails
    the ten shape descriptors while the other thirty-one succeed, and one
    report-level `cache_state` cannot say that."""
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", units="g/mol", value=46.07)
    _descriptor(
        bus, molecule, "spherocity_index", name="Spherocity Index", category="shape",
        cache_state=CacheState.FAILED,
        error="Needs a real 3D conformer - generate one first",
        error_summary="Needs a 3D conformer",
    )
    widget._open_results_window()

    aggregate = widget._results_window.merged().report_for(DESCRIPTOR_AGGREGATE_ID)
    states = {d.descriptor_id: d.cache_state for d in aggregate.descriptors}
    assert states["mol_wt"] is CacheState.COMPLETED
    assert states["spherocity_index"] is CacheState.FAILED
    assert [d.descriptor_id for d in aggregate.failed()] == ["spherocity_index"]
    dispose(widget._results_window)


def test_a_running_placeholder_is_replaced_rather_than_accumulated(panel):
    """Every descriptor arrives TWICE -- `DescriptorService` publishes a
    RUNNING placeholder before `compute()` runs. Keyed by id, so the result
    replaces the placeholder instead of sitting beside it."""
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", cache_state=CacheState.RUNNING)
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", value=46.07)
    widget._open_results_window()

    aggregate = widget._results_window.merged().report_for(DESCRIPTOR_AGGREGATE_ID)
    assert len(aggregate.descriptors) == 1
    assert aggregate.descriptors[0].cache_state is CacheState.COMPLETED
    dispose(widget._results_window)


def test_switching_molecule_does_not_carry_the_descriptors_over(panel):
    """A leftover set would appear under the new molecule's name with nothing
    saying otherwise -- the same rule the reports and the open window follow."""
    widget, bus, molecule, project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", value=46.07)
    assert widget._descriptor_values

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    assert not widget._descriptor_values


def test_no_aggregate_appears_before_any_descriptor_has_landed(panel):
    """The narrow half. An empty "Molecular Properties" entry would be a
    heading promising values nothing has computed yet."""
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    ids = [r.report_id for r in widget._results_window.merged().reports]
    assert DESCRIPTOR_AGGREGATE_ID not in ids
    dispose(widget._results_window)


def test_the_aggregate_is_shown_above_every_calculator(panel):
    """**THE ONE ENTRY THAT IS ALWAYS THERE MUST NOT BE AT THE BOTTOM.** It
    was appended last, so the 41 always-computed descriptors sat below every
    calculator that happened to have run -- and its 41 descriptors span ten
    categories, so no section is true of it either. It declares the always-on
    band and sorts above the sections.
    """
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", value=46.07)
    assert widget._descriptor_values, "fixture is degenerate: no descriptors landed"
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    ids = [r.report_id for r in widget._results_window.merged().reports]
    assert ids[0] == DESCRIPTOR_AGGREGATE_ID, ids
    dispose(widget._results_window)


# --- the ordering the panel is the only thing that can supply -------------


def _definition(calculator_id: str, display_name: str, category: str):
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=display_name,
        category=category,
        description=f"{display_name}. Runs nothing in this fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
    )


def test_the_results_window_orders_by_the_registrys_own_order(qapp):
    """**THE WIRING, END TO END, AND THE FIXTURE HAS TO CONTRADICT THE
    FALLBACK.**

    The panel is the only object holding the registry, so it is the only one
    that can tell the window where a calculator sits in its section. Drop the
    argument and the window still orders -- by name -- which is a plausible
    list that silently disagrees with the buttons above it. Measured on the
    shipped registry, that is the arrangement that puts Hansen Solubility
    Parameters ahead of Solubility.

    So the two calculators here are registered in the order that INVERTS
    their names: nothing but the registry position can produce the expected
    list, and the `panel` fixture's empty registry could not have shown it.
    """
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_definition("zulu", "Zulu", "solubility"))
    registry.register(_definition("alpha", "Alpha", "solubility"))
    widget = PropertyPanel(
        bus,
        registry,
        DescriptorService(bus, engine, calculator_registry=registry),
        engine,
        structure_version_of=_Versions(),
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    widget.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    assert registry.display_order("zulu") == 0
    assert registry.display_order("alpha") == 1, "the fixture must invert the names"

    _land(bus, _report("alpha", "Alpha", "A", molecule.uuid))
    _land(bus, _report("zulu", "Zulu", "Z", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    ids = [
        r.report_id
        for r in window.merged().reports
        if r.report_id in ("zulu", "alpha")
    ]
    assert ids == ["zulu", "alpha"], ids
    dispose(window)
    dispose(widget)


# --- where each molecule's reader was left --------------------------------


def _open(widget, focus: str = ""):
    widget._open_results_window(focus=focus)
    return widget._results_window


def test_reopening_restores_the_report_that_was_being_read(panel):
    """**A WINDOW KEYED ON A MOLECULE IS THROWN AWAY, SO ITS POSITION HAD TO
    BE.** Closing and reopening handed the reader "All results" and an empty
    box, whatever they had been looking at a second earlier."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))

    window = _open(widget)
    window.set_focus("b")
    window.close()
    QCoreApplication.processEvents()

    assert _open(widget).focus() == "b"
    dispose(widget._results_window)


def test_reopening_restores_the_filter_too(panel):
    """The search text is a reading position as much as the report is."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))

    window = _open(widget)
    window._view.search_box().setText("form")
    window.close()
    QCoreApplication.processEvents()

    reopened = _open(widget)
    assert reopened._view.filter_state() == ("form", False)
    dispose(reopened)


def test_an_explicit_details_press_beats_the_remembered_position(panel):
    """Pressing "Details..." beside a calculator is asking for THAT report.
    A memory that overrode it would make the button do something other than
    what it says."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))

    window = _open(widget)
    window.set_focus("b")
    window.close()
    QCoreApplication.processEvents()

    assert _open(widget, focus="a").focus() == "a"
    dispose(widget._results_window)


def test_a_stale_report_is_restored_rather_than_jumped_away_from(panel):
    """**THE RULE THIS WIRING EXISTS FOR.** A stale result is a record of what
    was computed, and this project refuses to discard one everywhere else;
    jumping away from a stale selection discards it in the one place somebody
    is looking.

    The memory is never told about staleness -- it restores whatever still
    EXISTS -- so the rule lives in what the panel OFFERS, and this is the
    guard for that. Filtering the offer to current results would silently
    reinstate exactly the behaviour the rule forbids.
    """
    widget, bus, molecule, _project, versions = panel
    _land(bus, _report("bbb_score", "BBB Score", "Score", molecule.uuid, version=1))
    versions.version = 1

    window = _open(widget)
    window.set_focus("bbb_score")
    window.close()
    QCoreApplication.processEvents()

    # The structure moves under it: the report is now stale, and still there.
    versions.version = 2
    reopened = _open(widget)
    assert reopened.merged().stale_report_ids() == ("bbb_score",), (
        "fixture is degenerate: the report must really be stale, or this "
        "guard passes against a memory that only ever restores current ones"
    )
    assert reopened.focus() == "bbb_score"
    dispose(reopened)


def test_a_report_that_is_gone_falls_back_and_the_filter_survives(panel):
    """Selecting another molecule clears this one's results, so returning
    finds the remembered report genuinely absent. Falling back to all results
    is right; clearing the search box with it is not -- the filter is about
    what somebody is looking FOR, and the memory is per molecule, so nothing
    inherits another's."""
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")
    window._view.search_box().setText("form")

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()

    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    reopened = _open(widget)
    assert reopened.merged().report_for("a") is None, (
        "fixture is degenerate: the remembered report must really be gone"
    )
    assert reopened.focus() == ""
    assert reopened._view.filter_state() == ("form", False)
    dispose(reopened)


def test_a_position_is_filed_under_the_window_s_molecule_not_the_panel_s(panel):
    """**THE ORDER `_on_molecule_selected` DOES THINGS IN IS A TRAP.** It sets
    the panel's uuid FIRST and closes the window after, so anything reading
    the PANEL's uuid to record a position would file the old molecule's
    reading position under the new molecule's name.

    The window records under its own `molecule_uuid()`, which cannot be wrong
    about which molecule it was showing. This asserts that rather than trusting
    the ordering to stay as it is.
    """
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()

    memory = widget._reader_memory
    assert memory.recall(molecule.uuid, ["a"]).report_id == "a"
    assert memory.recall(other.uuid, ["a"]).report_id == "", (
        "the other molecule inherited a position it never had"
    )


def test_a_new_project_starts_every_reader_fresh(panel):
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")
    assert len(widget._reader_memory) == 1

    widget.set_project(ProjectModel(molecules=[]))
    assert len(widget._reader_memory) == 0
    dispose(window)
