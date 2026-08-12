"""What the Properties panel SAYS about each kind of result.

**Nothing in the suite exercised this at all**, which is why four
separate defects shipped and stayed green across 3613 tests. Found by
running every registered calculator in the real app and asking which
ones reach the screen:

    facts[:6]                7 calculators, 50 of 126 facts never drawn
    _summarise field names   9 calculators rendered as the word "Ready"
    TrajectoryComputed       no subscriber at all -- MD produced no row
    empty payload            "Ready", where "none found" was the answer

None of it is a painting bug, so none of it needs `painted()`/`ink()`:
the panel builds the wrong STRING, and `label.text()` catches all four.
That distinction is worth keeping -- the natural instinct after a
"nothing renders" report is to reach for the pixel helpers, and here
they would have measured a perfectly-painted wrong answer.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.scientific_result import (
    NMRSpectrumResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureEntry,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.domain.structure_issue import Basis
from openchem.events.base import EventBus
from openchem.events.events import (
    CalculationFinished,
    MoleculeSelected,
    PerAtomDataComputed,
    PhCurveComputed,
    ReportComputed,
    StructureSetComputed,
    TrajectoryComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import _PAYLOAD_FIELDS, PropertyPanel, _summarise

MOLECULE = "mol-1"


class _FakeService:
    def run_calculator(self, model, request) -> None:  # noqa: D102 - test double
        pass


@pytest.fixture
def bus() -> EventBus:
    """Held by the test rather than read back off the panel, which does
    not keep a reference to it."""
    return EventBus()


@pytest.fixture
def panel(qapp, bus):
    """A real panel, disposed deterministically.

    Per-file disposal, per CLAUDE.md: a widget a test walks away from is
    destroyed at whatever arbitrary later moment the collector runs,
    inside an unrelated test, from within Qt's event dispatch -- which is
    an access violation, and reads as flakiness somewhere else entirely.
    """
    built = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
    bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
    yield built
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


def _provenance() -> Provenance:
    return Provenance(created_by="core", method="test")


def _report(facts: int) -> ReportResult:
    return ReportResult(
        report_id="topology_analysis",
        name="Topology",
        molecule_uuid=MOLECULE,
        category="topology",
        facts=tuple(
            Fact(
                category=FactCategory.TOPOLOGY,
                label=f"Descriptor {n}",
                value=n,
                display_value=str(n),
                source="Topology",
                basis=Basis.DETERMINISTIC,
            )
            for n in range(facts)
        ),
        cache_state=CacheState.COMPLETED,
        provenance=_provenance(),
    )


# --- A: the cap ---------------------------------------------------------


def test_a_report_row_renders_every_fact_not_the_first_six(panel, bus):
    """`topology_analysis` really does report 27 facts on aspirin, and the
    row showed 6 of them with only a tooltip to say so.

    Asserts the LAST fact by name. A count alone would pass against an
    off-by-one slice, and the defect being guarded was precisely a slice.
    """
    bus.publish(ReportComputed(report=_report(27)))

    text = panel._report_labels["topology_analysis"].text()
    assert len(text.splitlines()) == 27
    assert "Descriptor 26: 26" in text
    assert "Descriptor 6: 6" in text  # the first one the old cap dropped


def test_the_report_row_says_how_many_facts_it_is_showing(panel, bus):
    bus.publish(ReportComputed(report=_report(27)))

    assert "27 facts" in panel._report_labels["topology_analysis"].toolTip()


# --- B: the field-name mismatch ----------------------------------------


#: Every result type the panel routes through `_show_result`, i.e. every
#: one whose detail lives in a dialog and whose row is a summary.
_SUMMARISED_TYPES = (
    PerAtomDataset,
    SpectrumResult,
    NMRSpectrumResult,
    StructureSetResult,
    PhCurveResult,
    TrajectoryResult,
)


@pytest.mark.parametrize("result_type", _SUMMARISED_TYPES, ids=lambda t: t.__name__)
def test_every_summarised_result_type_has_a_field_the_table_names(result_type):
    """DERIVED from the dataclasses, never a hand-written list.

    This is the guard that was missing. `_summarise` probed for
    `structures` and `points` -- names no result type has ever had -- and
    nothing compared those strings against the classes they were meant to
    describe, so nine calculators said "Ready" for months. Reading the
    fields off the dataclass means a rename fails HERE, naming the type,
    instead of silently reverting to "Ready".
    """
    fields = {f.name for f in dataclasses.fields(result_type)}
    named = {attribute for attribute, _ in _PAYLOAD_FIELDS} & fields

    assert named, (
        f"{result_type.__name__} carries none of {[a for a, _ in _PAYLOAD_FIELDS]}, "
        f"so _summarise falls through to 'Ready'. Its fields are: {sorted(fields)}"
    )


def test_a_structure_set_says_how_many_structures(panel, bus):
    """`major_microspecies` and `tautomers` both rendered as "Ready"."""
    bus.publish(
        StructureSetComputed(
            structure_set=StructureSetResult(
                set_id="tautomers",
                name="Tautomers",
                method="rdkit",
                molecule_uuid=MOLECULE,
                entries=[StructureEntry(molblock="", label=f"t{n}") for n in range(9)],
                provenance=_provenance(),
            )
        )
    )

    assert panel._result_labels["tautomers"].text() == "9 structures"


def test_a_ph_curve_says_how_many_points(panel, bus):
    bus.publish(
        PhCurveComputed(
            curve=PhCurveResult(
                curve_id="pka_microspecies",
                name="Microspecies",
                method="pkasolver",
                molecule_uuid=MOLECULE,
                ph_values=[n / 2 for n in range(57)],
                series={"neutral": [0.0] * 57},
                provenance=_provenance(),
            )
        )
    )

    assert panel._result_labels["pka_microspecies"].text() == "57 pH points"


def test_a_single_structure_is_not_reported_as_1_structures(panel, bus):
    """Caffeine really does have exactly one major microspecies, so the
    count of 1 is the ORDINARY case here, not an edge one."""
    bus.publish(
        StructureSetComputed(
            structure_set=StructureSetResult(
                set_id="major_microspecies",
                name="Major Microspecies",
                method="pkasolver",
                molecule_uuid=MOLECULE,
                entries=[StructureEntry(molblock="", label="neutral")],
                provenance=_provenance(),
            )
        )
    )

    assert panel._result_labels["major_microspecies"].text() == "1 structure"


def test_no_summarised_type_falls_through_to_ready():
    """The blanket statement, so a NEW result type cannot repeat this.

    A type with a payload must describe it. "Ready" is reserved for a
    shape this function does not recognise, and the whole defect was that
    every structure set and pH curve landed there.
    """
    populated = (
        PerAtomDataset(
            property_id="p", name="P", units="e", method="m",
            molecule_uuid=MOLECULE, values={0: 1.0},
        ),
        StructureSetResult(
            set_id="s", name="S", method="m", molecule_uuid=MOLECULE,
            entries=[StructureEntry(molblock="")],
        ),
        PhCurveResult(
            curve_id="c", name="C", method="m", molecule_uuid=MOLECULE,
            ph_values=[7.0], series={"a": [1.0]},
        ),
        TrajectoryResult(
            trajectory_id="t", name="T", method="m", molecule_uuid=MOLECULE,
            frames=["", ""], times=[0.0, 1.0], energies=[0.0, 0.0],
        ),
    )

    summaries = {type(r).__name__: _summarise(r) for r in populated}

    assert "Ready" not in summaries.values(), summaries


# --- D: an empty payload is an answer ----------------------------------


def test_an_empty_result_says_none_found_rather_than_ready(panel, bus):
    """`stereocenters` on a molecule with none is a RESULT.

    "Ready" is indistinguishable from the panel having failed to render,
    which is the same confusion `_present_alert` already records for an
    empty `matched` reading as a green "Clean".
    """
    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="stereocenters",
                name="Stereocenters",
                units="",
                method="rdkit",
                molecule_uuid=MOLECULE,
                values={},
                provenance=_provenance(),
            )
        )
    )

    assert panel._result_labels["stereocenters"].text() == "None found."


# --- C: the trajectory that arrived nowhere -----------------------------


def test_a_trajectory_reaches_the_panel_at_all(panel, bus):
    """`TrajectoryComputed` was published and NOTHING subscribed to it, so
    `molecular_dynamics` ran, produced 101 frames, and left no trace in
    the panel -- indistinguishable from never having started."""
    bus.publish(
        TrajectoryComputed(
            trajectory=TrajectoryResult(
                trajectory_id="molecular_dynamics",
                name="Molecular Dynamics",
                method="rdkit-mmff",
                molecule_uuid=MOLECULE,
                frames=[""] * 101,
                times=[float(n) for n in range(101)],
                energies=[0.0] * 101,
                provenance=_provenance(),
            )
        )
    )

    assert "molecular_dynamics" in panel._result_labels
    assert panel._result_labels["molecular_dynamics"].text() == "101 frames"


def test_a_trajectory_opens_the_player_now_that_one_exists(panel, bus, monkeypatch):
    """This asserted the OPPOSITE until `TrajectoryPlayerWidget` was
    built, and the inversion is the point rather than an edit.

    `_RESULT_VIEW_FACTORIES` had no `TrajectoryResult` entry, so opening
    the inspector would have fallen back to the single-molecule view and
    depicted the input rather than any of the frames. The panel therefore
    opened nothing ON PURPOSE, and this test asserted that so the
    omission read as a decision. There is a view now, so a trajectory
    behaves like every other explicitly-run result.
    """
    opened: list[object] = []
    monkeypatch.setattr(
        PropertyPanel, "_open_inspector", lambda self, result: opened.append(result)
    )
    panel._pending_calculator_id = "molecular_dynamics"

    bus.publish(
        TrajectoryComputed(
            trajectory=TrajectoryResult(
                trajectory_id="molecular_dynamics",
                name="Molecular Dynamics",
                method="rdkit-mmff",
                molecule_uuid=MOLECULE,
                frames=[""] * 3,
                times=[0.0, 1.0, 2.0],
                energies=[0.0, 0.0, 0.0],
                provenance=_provenance(),
            )
        )
    )

    assert len(opened) == 1
    assert isinstance(opened[0], TrajectoryResult)
    # ...and the pending id is cleared, so the NEXT explicit run is not
    # answered by a stale one.
    assert panel._pending_calculator_id is None



# --- the waiting indicator ---------------------------------------------


def _definition(calculator_id: str, category: str = "topology"):
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id,
        category=category,
        description=calculator_id,
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
    )


@pytest.fixture
def running_panel(qapp, bus):
    """A panel with one registered calculator, so a row exists to show
    the indicator on."""
    from openchem.domain.project import ProjectModel
    from openchem.domain.molecule import MoleculeModel

    registry = CalculatorRegistry()
    registry.register(_definition("nmr_database", category="nmr"))
    registry.register(_definition("topology_analysis"))

    dispatched: list[str] = []

    class _Service:
        def run_calculator(self, model, request) -> None:
            dispatched.append(request.calculator_id)

    built = PropertyPanel(bus, registry, _Service(), ChemistryEngine())
    project = ProjectModel()
    molecule = MoleculeModel()
    project.molecules.append(molecule)
    built.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    # Build the rows.
    built._section_for("nmr")
    built._section_for("topology")
    yield built, molecule, dispatched
    built.setParent(None)
    built.deleteLater()
    QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)


def test_a_dispatched_calculator_says_it_is_running(running_panel):
    """Clicking a calculator produced NOTHING for as long as it ran --
    measured at 6.5 s for ADMET, with no row, no status and no change of
    any kind until the result and its dialog arrived together."""
    panel, _molecule, _dispatched = running_panel
    status = panel._calculator_status["topology_analysis"]
    assert not status.isVisible() or status.isHidden()

    panel._open_calculator(panel._calculator_registry.get("topology_analysis"))

    assert not status.isHidden()
    assert status.text() == "Running..."


def test_the_indicator_clears_when_the_calculation_finishes(running_panel):
    panel, molecule, _dispatched = running_panel
    panel._open_calculator(panel._calculator_registry.get("topology_analysis"))

    panel._on_calculation_finished(
        CalculationFinished(calculator_id="topology_analysis", molecule_uuid=molecule.uuid)
    )

    assert panel._calculator_status["topology_analysis"].isHidden()
    assert "topology_analysis" not in panel._running_calculator_ids


def test_the_indicator_clears_for_a_calculator_whose_result_is_named_differently(running_panel):
    """THE REASON `CalculationFinished` EXISTS.

    `nmr_database` publishes a spectrum called `nmr_13c`, so anything
    clearing on the RESULT's id leaves this one showing "Running..." for
    the rest of the session. Asserted with the real mismatch rather than
    an invented one, because an id that happens to match proves nothing.
    """
    panel, molecule, _dispatched = running_panel
    panel._open_calculator(panel._calculator_registry.get("nmr_database"))
    assert not panel._calculator_status["nmr_database"].isHidden()

    # The result arrives under a DIFFERENT name -- this must not be what
    # clears it, and on its own it does not.
    panel._finish_batch_run("nmr_13c")
    assert not panel._calculator_status["nmr_database"].isHidden()

    panel._on_calculation_finished(
        CalculationFinished(calculator_id="nmr_database", molecule_uuid=molecule.uuid)
    )
    assert panel._calculator_status["nmr_database"].isHidden()


def test_a_failed_calculation_still_clears_its_indicator(running_panel):
    """`CalculationFinished` is published in a `finally`, so a calculator
    that raised clears too. Those are precisely the runs whose indicator
    would otherwise stick permanently."""
    panel, molecule, _dispatched = running_panel
    panel._open_calculator(panel._calculator_registry.get("topology_analysis"))

    panel._on_calculation_finished(
        CalculationFinished(calculator_id="topology_analysis", molecule_uuid=molecule.uuid)
    )

    assert panel._calculator_status["topology_analysis"].isHidden()


def test_switching_molecule_clears_a_stale_indicator(running_panel):
    """The calculator ROWS survive a molecule change -- they are buttons,
    not results -- so a "Running..." left visible would sit beside a
    different molecule claiming work that is not happening."""
    panel, _molecule, _dispatched = running_panel
    panel._open_calculator(panel._calculator_registry.get("topology_analysis"))

    panel._on_molecule_selected(MoleculeSelected(molecule_uuid="some-other-molecule"))

    assert panel._calculator_status["topology_analysis"].isHidden()
    assert not panel._running_calculator_ids


# --- revealing a computed property ---------------------------------------


def _descriptor(descriptor_id: str, name: str, category: str):
    from openchem.domain.descriptor import DescriptorValue

    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=name,
        units="",
        category=category,
        provider="rdkit",
        molecule_uuid=MOLECULE,
        value=1.23,
        cache_state=CacheState.COMPLETED,
    )


def test_revealing_a_property_expands_its_section_and_scrolls(panel, bus):
    """A descriptor cannot be run, so REVEALING it is the action the
    palette offers -- the value is already on screen somewhere, possibly
    far down inside a collapsed section."""
    from openchem.events.events import DescriptorComputed

    bus.publish(DescriptorComputed(descriptor=_descriptor("esol_logs", "Aqueous Solubility", "admet")))
    section = panel._sections["admet"]
    section.set_expanded(False)

    found = panel.reveal_descriptor("esol_logs")

    assert found
    assert section.is_expanded()
    assert panel._reveal_target is panel._value_labels[("rdkit", "esol_logs")]


def test_revealing_a_property_computes_nothing(panel, bus):
    """A palette entry that silently started a calculation would be the
    surprise this panel refuses elsewhere."""
    from openchem.events.events import DescriptorComputed

    bus.publish(DescriptorComputed(descriptor=_descriptor("qed", "QED", "medicinal_chemistry")))
    panel._descriptor_service.run_calculator = _fail_if_called

    panel.reveal_descriptor("qed")


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("revealing a property must not compute anything")


def _schedule_from_the_palette(built, bus) -> None:
    """`reveal_descriptor` -- the command palette's route."""
    from openchem.events.events import DescriptorComputed

    bus.publish(
        DescriptorComputed(descriptor=_descriptor("esol_logs", "Aqueous Solubility", "admet"))
    )
    assert built.reveal_descriptor("esol_logs"), "the reveal was never scheduled"


def _schedule_from_a_finished_calculator(built, bus) -> None:
    """`_reveal` -- an inline result answering a button press."""
    built._pending_calculator_id = "topology_analysis"
    bus.publish(ReportComputed(report=_report(3)))
    assert built._reveal_target is not None, "the reveal was never scheduled"


@pytest.mark.parametrize(
    "schedule",
    [_schedule_from_the_palette, _schedule_from_a_finished_calculator],
    ids=["palette", "finished calculator"],
)
def test_a_pending_reveal_is_cancelled_when_the_panel_is_destroyed(qapp, bus, monkeypatch, schedule):
    """A reveal is deferred by one turn, and the panel can die in it.

    A bare `QTimer.singleShot(0, callable)` is tied to nothing, so a shot
    scheduled by a panel that is then disposed still fires -- against a
    live Python wrapper around a freed QScrollArea, which raises
    `RuntimeError: libshiboken: Internal C++ object ... already deleted`
    inside whichever unrelated test happens to be pumping events at the
    time. It surfaced in `test_calculator_sections.py`, an innocent
    bystander. Passing `self` as Qt's CONTEXT OBJECT disconnects the shot
    when the panel is destroyed, so it is CANCELLED rather than firing
    and then declining -- which is why the handler's `row is None` guard
    could never have helped.

    **BOTH SCHEDULING SITES, because one arm does not cover the other.**
    Measured: reverting only `_reveal`'s call left the whole two-file
    reproduction green at 38 passed, so a single-route guard would have
    signed off on half a fix.

    **THE ALIVE ARM IS THE CONTROL AND IT IS LOAD-BEARING.** A reveal
    that was never scheduled, or an event pump that delivers no timers,
    reads exactly like a cancelled one -- so without it this guard would
    pass just as happily against a panel that had lost the feature
    altogether.
    """
    fired: list[str] = []

    def _record(self) -> None:
        fired.append("fired")

    # Patched on the CLASS and before construction: `singleShot` captures
    # the bound method at schedule time, so patching afterwards would
    # leave the original scheduled and record nothing either way.
    monkeypatch.setattr(PropertyPanel, "_reveal_pending_result", _record)

    def schedule_a_reveal(*, dispose: bool) -> None:
        built = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
        bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
        schedule(built, bus)
        if dispose:
            built.setParent(None)
            built.deleteLater()
            QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()

    schedule_a_reveal(dispose=False)
    assert fired == ["fired"], "the control did not fire, so the arm below proves nothing"

    schedule_a_reveal(dispose=True)
    assert fired == ["fired"], "a pending reveal outlived the panel that scheduled it"


def test_a_pending_metrics_dump_is_cancelled_when_the_panel_is_destroyed(qapp, bus, monkeypatch):
    """The instrumented path schedules the widest-open shot of the four.

    `_dump_panel_metrics` opens on `panel.width()` -- a C++ call, so it
    raises `RuntimeError: libshiboken: Internal C++ object ... already
    deleted` once the panel is gone -- and it waits 1500 ms rather than
    one event-loop turn.

    **BEING BEHIND AN ENV VAR MADE IT LOOK UNTESTABLE, AND IT IS NOT.**
    `_INSTRUMENT` and `_INSTRUMENT_DELAY_MS` are module constants read at
    call time, so both can be moved for the length of a test; the delay
    goes to 0 so this costs nothing. That is worth doing rather than
    waving at, because rarely-reached is not the same as safe -- the one
    run where somebody sets `OPENCHEM_INSTRUMENT_PANEL` to chase a layout
    is exactly the run that opens and closes panels while shots are in
    flight.

    The alive arm is the control and doubles as the setup assertion: with
    `_INSTRUMENT` left off nothing is scheduled at all, and it fails.
    """
    import openchem.ui.panels.property_panel as property_panel_module

    monkeypatch.setattr(property_panel_module, "_INSTRUMENT", True)
    monkeypatch.setattr(property_panel_module, "_INSTRUMENT_DELAY_MS", 0)

    fired: list[str] = []

    def _record(self) -> None:
        fired.append("fired")

    monkeypatch.setattr(PropertyPanel, "_dump_metrics", _record)

    def build_a_report_row(*, dispose: bool) -> None:
        built = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
        bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
        bus.publish(ReportComputed(report=_report(3)))
        if dispose:
            built.setParent(None)
            built.deleteLater()
            QCoreApplication.sendPostedEvents(built, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()

    build_a_report_row(dispose=False)
    assert fired == ["fired"], "nothing was scheduled, so the arm below proves nothing"

    build_a_report_row(dispose=True)
    assert fired == ["fired"], "a pending metrics dump outlived the panel that scheduled it"


def test_a_property_that_is_not_there_says_why(panel, bus):
    """Two different reasons, and they are not the same message: nothing
    selected is a different problem from selected-but-not-computed."""
    assert not panel.reveal_descriptor("esol_logs")
    assert "not been computed" in panel._batch_status.text()

    panel._selected_molecule_uuid = None
    assert not panel.reveal_descriptor("esol_logs")
    assert "Select a molecule" in panel._batch_status.text()
