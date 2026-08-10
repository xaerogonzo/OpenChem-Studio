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


def test_a_trajectory_does_not_open_an_inspector_it_has_no_view_for(panel, bus, monkeypatch):
    """`_RESULT_VIEW_FACTORIES` has no `TrajectoryResult` entry, so the
    inspector would fall back to the per-atom molecular view and depict a
    trajectory as an empty structure. The row is deliberately the whole
    of it until a trajectory view exists -- asserted so the omission
    reads as a decision rather than as something forgotten."""
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

    assert opened == []
    # ...and the pending id is cleared, so the NEXT explicit run is not
    # answered by a stale one.
    assert panel._pending_calculator_id is None
