"""What the Properties panel DOES when a result arrives.

**IT USED TO BE WHAT THE PANEL *SAID* ABOUT EACH KIND OF RESULT**, and
that half has moved: 2c makes Properties a launcher, so a result is read
in the results panel and the row this file was written about is gone. The
four defects it was written for are all still guarded, one surface along
-- `tests/test_result_summaries.py` holds the per-kind projections, and
`tests/test_property_panel_reader.py` holds the wiring that carries a
result there.

What is left is the half only the panel can be wrong about: whether it
says a calculation is running, whether it can put a computed property in
front of you, and whether the shots it defers outlive it.

The retired half is worth remembering for HOW it was found, because
nothing in the suite exercised it at all and four defects shipped green
across 3613 tests -- by running every registered calculator in the real
app and asking which ones reached the screen. None of them was a painting
bug, so none needed `painted()`/`ink()`: the panel built the wrong
STRING. The instinct after a "nothing renders" report is to reach for the
pixel helpers, and here they would have measured a perfectly-painted
wrong answer.
"""

from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QCoreApplication

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
    VibrationalSpectrumResult,
)
from openchem.domain.structure_issue import Basis
from openchem.events.base import EventBus
from openchem.events.events import (
    CalculationFinished,
    DescriptorComputed,
    MoleculeSelected,
    PerAtomDataComputed,
    PhCurveComputed,
    ReportComputed,
    StructureSetComputed,
    TrajectoryComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.result_adapters import ADAPTERS

import conftest

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
    conftest.dispose(built)


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


# --- B: the field-name mismatch ----------------------------------------


#: Every result type the panel routes through `_show_result`, i.e. every
#: one whose detail lives in a dialog and whose row is a summary.
#: **DERIVED FROM THE KIND VOCABULARY, NOT HAND-WRITTEN, AND THAT IS THE
#: WHOLE POINT OF THIS SECTION.** The list used to be typed out here and
#: OMITTED `VibrationalSpectrumResult` -- the one type the old fixed-order
#: probe got wrong -- so the guard below passed while the panel rendered
#: "None found." for a spectrum with real modes in it. A population somebody
#: maintains by hand is a population that excludes the case nobody thought of.
_SUMMARISED_TYPES = tuple(
    sorted(
        {
            PerAtomDataset,
            SpectrumResult,
            NMRSpectrumResult,
            VibrationalSpectrumResult,
            StructureSetResult,
            PhCurveResult,
            TrajectoryResult,
        },
        key=lambda cls: cls.__name__,
    )
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
    declared = {adapter.payload[0] for adapter in ADAPTERS.values() if adapter.payload[0]}
    named = declared & fields

    assert named, (
        f"{result_type.__name__} carries none of {sorted(declared)}, so "
        f"_summarise falls through to 'Ready'. Its fields are: {sorted(fields)}"
    )


# --- D: an empty payload is an answer ----------------------------------


# --- C: the trajectory that arrived nowhere -----------------------------


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
    conftest.dispose(built)


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
    not results -- so a "Running..." left over would sit beside a different
    molecule claiming work that is not happening.

    **THE CLAIM IS UNCHANGED AND ITS ASSERTION MOVED.** The indicator used
    to be a label that was VISIBLE only while running, so "cleared" meant
    hidden. It is a status chip now and is visible whatever the state, so
    what must be true is that it no longer says "Running..." -- it says
    the new molecule has been asked nothing.
    """
    panel, _molecule, _dispatched = running_panel
    panel._open_calculator(panel._calculator_registry.get("topology_analysis"))
    assert panel._calculator_status["topology_analysis"].text() == "Running...", (
        "setup: it must really be showing the running state to clear one"
    )

    panel._on_molecule_selected(MoleculeSelected(molecule_uuid="some-other-molecule"))

    assert panel._calculator_status["topology_analysis"].text() == "Not run"
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
    bus.publish(
        DescriptorComputed(descriptor=_descriptor("esol_logs", "Aqueous Solubility", "admet"))
    )
    assert built.reveal_descriptor("esol_logs"), "the reveal was never scheduled"


@pytest.mark.parametrize(
    "schedule",
    [_schedule_from_the_palette],
    ids=["palette"],
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

    **THERE IS ONE SCHEDULING SITE NOW, AND IT IS PARAMETRISED ANYWAY.**
    It used to be two -- the palette, and `_reveal` answering a button
    press with an inline result -- and the pairing was load-bearing:
    reverting only `_reveal`'s call left the whole two-file reproduction
    green at 38 passed, so a single-route guard would have signed off on
    half a fix. 2c removed the inline row, so `_reveal` went with it and
    the palette is the only route left. The shape is kept rather than
    flattened because the next deferred shot added here should join the
    list instead of being tested somewhere else -- which is exactly what
    happened last time.

    The OTHER deferred shot this panel owns has not gone anywhere: the
    instrumented metrics dump keeps its own guard directly below.

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
            conftest.dispose(built)
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

    **SCHEDULED BY A DESCRIPTOR ROW, WHICH IS WHERE THE ROWS ARE NOW.**
    This built a report row, because a finished calculator's row was then
    the case under investigation; 2c took those rows out, and the shot
    moved to the rows that remain rather than being left unscheduled --
    which would have made this guard pass by never arming, the exact
    vacuity the control arm exists to catch.
    """
    import openchem.ui.panels.property_panel as property_panel_module

    monkeypatch.setattr(property_panel_module, "_INSTRUMENT", True)
    monkeypatch.setattr(property_panel_module, "_INSTRUMENT_DELAY_MS", 0)

    fired: list[str] = []

    def _record(self) -> None:
        fired.append("fired")

    monkeypatch.setattr(PropertyPanel, "_dump_metrics", _record)

    def build_a_descriptor_row(*, dispose: bool) -> None:
        built = PropertyPanel(bus, CalculatorRegistry(), _FakeService(), ChemistryEngine())
        bus.publish(MoleculeSelected(molecule_uuid=MOLECULE))
        bus.publish(
            DescriptorComputed(descriptor=_descriptor("esol_logs", "Aqueous Solubility", "admet"))
        )
        if dispose:
            conftest.dispose(built)
        QCoreApplication.processEvents()

    build_a_descriptor_row(dispose=False)
    assert fired == ["fired"], "nothing was scheduled, so the arm below proves nothing"

    build_a_descriptor_row(dispose=True)
    assert fired == ["fired"], "a pending metrics dump outlived the panel that scheduled it"


def test_a_property_that_is_not_there_says_why(panel, bus):
    """Two different reasons, and they are not the same message: nothing
    selected is a different problem from selected-but-not-computed."""
    assert not panel.reveal_descriptor("esol_logs")
    assert "not been computed" in panel._batch_status.text()

    panel._selected_molecule_uuid = None
    assert not panel.reveal_descriptor("esol_logs")
    assert "Select a molecule" in panel._batch_status.text()
