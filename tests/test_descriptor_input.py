"""A conformer does not change what the drawing's structure-level properties are.

Reported (2026-10-14): draw aspirin, let the always-on descriptors compute, generate a
conformer -- and the Results reader's Synthetic Accessibility went from 1.58 to 6.445, Bertz
CT from 343.2 to 609 and H-bond acceptors from 3 to 4. `MainWindow._on_conformers_changed`
asked for the descriptors on `GEOMETRY`, the service ran EVERY provider output on the
explicit-hydrogen conformer, and the results replaced the drawing's because they share an id.

**THE RULE THE FIX HOLDS:** a result is computed on a geometry only if it is MEASURED from
coordinates, and the provider says which (`DescriptorProvider.geometric_descriptor_ids`); every
other descriptor, every alert catalogue and every per-atom dataset is a property of the
structure graph and is computed on the drawing. Measured over the 29-molecule census panel
(`tools/survey_descriptor_inputs.py`): the ten shape descriptors are refused on the flat
drawing and vary between two embeddings of one molecule; nine others move between the drawing
and the conformer and never between two conformers (an artefact of how the hydrogens are
written); two alert catalogues moved; the per-atom datasets came back describing a different
set of atoms.

**THROUGH THE SERVICE, NOT BY IMPORT.** Each assertion reads what `DescriptorService` publishes
and applies the rule the Properties panel applies -- the latest value per id wins -- because a
descriptor that is right when computed and replaced on its way to the reader is the defect.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool

from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.descriptor_providers import (
    RDKitDescriptorProvider,
    geometric_descriptor_ids_of,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    AutomaticPartFinished,
    DescriptorComputed,
    PerAtomDataComputed,
    ResultRecorded,
)
from openchem.plugins.interfaces import DescriptorProvider
from openchem.services.descriptor_service import DescriptorService, _GeometryClaims

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import calculator_census as census_tool  # noqa: E402
import survey_descriptor_inputs as survey_tool  # noqa: E402

#: Census rows on which a structure-level result MOVED when the service ran on the conformer, one
#: per kind of movement: aspirin (SA score, Bertz CT, H-bond acceptors), RDX and TATB (rotatable
#: bonds), the C12E6 surfactant (BRENK's long-chain alert), ferrocene (fragment counts).
_MOVERS = ("aspirin", "rdx", "tatb", "surfactant_c12e6", "ferrocene")


def _smiles_of(row_id: str) -> str:
    return next(row.smiles for row in census_tool.load_corpus() if row.id == row_id)


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(60000)
    for _ in range(iterations):
        qapp.processEvents()


def _molecule(engine: ChemistryEngine, smiles: str, *, conformer: bool = False) -> MoleculeModel:
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, smiles)
    if conformer:
        mol, _energy = RDKitConformerProvider().generate_conformers(
            engine.mol_from_model(model), num_conformers=1, optimize=False
        )[0]
        model.conformers.append(ConformerModel(molblock=engine.mol_to_molblock(mol), energy=-1.0))
    return model


class _Reader:
    """What a reader holds: the LATEST descriptor per id, the latest alert and per-atom dataset.

    The same rule `PropertyPanel` applies (`_descriptor_values` is keyed by id, `_reports` by alert
    id), at one structure version -- so this is the question "what would the reader show", not
    "what did the service compute".
    """

    def __init__(self, bus: EventBus) -> None:
        self.descriptors: dict[str, DescriptorValue] = {}
        self.alerts: dict[str, tuple[str, ...]] = {}
        self.per_atom: dict[str, dict[int, float]] = {}
        self.descriptor_events: list[DescriptorValue] = []
        self.alert_events = 0
        self.per_atom_events = 0
        self.recorded: list = []
        self.parts_finished = 0
        bus.subscribe(DescriptorComputed, self._descriptor)
        bus.subscribe(AlertComputed, self._alert)
        bus.subscribe(PerAtomDataComputed, self._per_atom)
        bus.subscribe(ResultRecorded, lambda e: self.recorded.append(e.stored))
        bus.subscribe(AutomaticPartFinished, lambda e: setattr(self, "parts_finished", self.parts_finished + 1))

    def _descriptor(self, event: DescriptorComputed) -> None:
        self.descriptors[event.descriptor.descriptor_id] = event.descriptor
        self.descriptor_events.append(event.descriptor)

    def _alert(self, event: AlertComputed) -> None:
        self.alert_events += 1
        self.alerts[event.alert.alert_id] = tuple(sorted(event.alert.matched))

    def _per_atom(self, event: PerAtomDataComputed) -> None:
        self.per_atom_events += 1
        self.per_atom[event.dataset.property_id] = dict(event.dataset.values)

    def settled(self) -> dict[str, tuple]:
        """`id -> (state, value)` for every descriptor, to compare before with after."""
        return {i: (d.cache_state, d.value) for i, d in self.descriptors.items()}


def _service(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    return bus, engine, DescriptorService(bus, engine), _Reader(bus)


# --- the declaration is the measured fact, not a list somebody keeps ------------------


def test_the_declared_geometric_descriptors_are_exactly_the_ones_a_flat_drawing_refuses(qapp):
    """Declared geometric <=> refused on the drawing and computed on a conformer.

    Both directions, because each is a different mistake: a structure-level descriptor declared
    geometric would be recomputed on the conformer's hydrogens again (the defect), and a shape
    descriptor left out would stay "Needs a 3D conformer" for ever.
    """
    engine = ChemistryEngine()
    provider = RDKitDescriptorProvider()
    model = _molecule(engine, "CC(=O)Oc1ccccc1C(=O)O", conformer=True)
    flat = engine.mol_from_model(model)
    conformer = engine.mol_from_molblock(model.conformers[0].molblock)

    refused_flat = {v.descriptor_id for v in provider.compute(flat, "m") if v.cache_state is CacheState.FAILED}
    refused_3d = {v.descriptor_id for v in provider.compute(conformer, "m") if v.cache_state is CacheState.FAILED}

    declared = provider.geometric_descriptor_ids()
    assert declared == refused_flat, "a descriptor is geometric exactly when a flat drawing cannot give it"
    assert not (declared & refused_3d), "a geometric descriptor must compute on a real conformer"
    assert len(declared) == 10


def test_a_provider_that_declares_nothing_is_structure_level():
    class Plain(DescriptorProvider):
        provider_id = "plain"

        def descriptor_ids(self) -> list[str]:
            return ["a"]

        def compute(self, mol, molecule_uuid):
            return []

    assert Plain().geometric_descriptor_ids() == frozenset()
    assert geometric_descriptor_ids_of(Plain()) == frozenset()


def test_a_declaration_of_something_the_provider_does_not_emit_scopes_nothing():
    class Typo(DescriptorProvider):
        provider_id = "typo"

        def descriptor_ids(self) -> list[str]:
            return ["a"]

        def compute(self, mol, molecule_uuid):
            return []

        def geometric_descriptor_ids(self) -> frozenset[str]:
            return frozenset({"not_a_descriptor"})

    assert geometric_descriptor_ids_of(Typo()) == frozenset()


# --- what a result varies with is what decides where it may be computed ---------------

#: Flexible and rigid, with and without a hydrogen-sensitive descriptor: the survey's evidence in miniature.
_SURVEYED = ("aspirin", "ibuprofen", "haloperidol", "rdx", "tatb", "surfactant_c12e6")


@pytest.fixture(scope="module")
def surveyed():
    rows = [row for row in census_tool.load_corpus() if row.id in _SURVEYED]
    assert len(rows) == len(_SURVEYED)
    return survey_tool.survey(rows)


def test_nothing_the_provider_leaves_undeclared_varies_with_the_coordinates(surveyed):
    """**THE GUARD FOR A FUTURE 3D DESCRIPTOR ADDED WITHOUT BEING DECLARED.**

    A result that differs between two embeddings of one molecule is a function of coordinates. If the
    provider has not declared it geometric it would be computed on the drawing, where a flat structure
    gives it a number that means nothing (or refuses it), and the conformer would never be asked.
    `tools/survey_descriptor_inputs.py` is the measurement the declaration rests on.
    """
    declared = {f"descriptor:rdkit:{i}" for i in RDKitDescriptorProvider().geometric_descriptor_ids()}
    varying = {i for i, seen in surveyed.items() if seen.varied_between_conformers}
    assert varying == declared, (
        f"varies with the coordinates but is not declared: {sorted(varying - declared)}; "
        f"declared but never varied here: {sorted(declared - varying)}"
    )
    for result_id, seen in surveyed.items():
        assert seen.pairs >= len(_SURVEYED) - 1, f"{result_id}: the survey compared too few embeddings to mean anything"


def test_every_geometric_descriptor_is_one_the_drawing_refuses(surveyed):
    declared = {f"descriptor:rdkit:{i}" for i in RDKitDescriptorProvider().geometric_descriptor_ids()}
    assert all(surveyed[i].needed_geometry >= len(_SURVEYED) - 1 for i in declared)
    undeclared = [i for i, seen in surveyed.items() if i not in declared and seen.needed_geometry]
    assert not undeclared, f"the drawing refuses these but they are not declared geometric: {undeclared}"


# --- the reader invariant, through the service ----------------------------------------


@pytest.mark.parametrize("row_id", _MOVERS)
def test_a_conformer_leaves_every_structure_level_result_as_the_drawing_made_it(qapp, row_id):
    bus, engine, service, reader = _service(qapp)
    model = _molecule(engine, _smiles_of(row_id))
    service.request_descriptors(model)
    _drain(qapp)
    drawn = reader.settled()
    drawn_alerts, drawn_atoms = dict(reader.alerts), {k: dict(v) for k, v in reader.per_atom.items()}
    assert drawn_alerts and drawn_atoms, "setup: the drawing run produced no alerts or per-atom data"

    # The conformer arrives, exactly as `MainWindow._on_conformers_changed` asks.
    mol, _energy = RDKitConformerProvider().generate_conformers(
        engine.mol_from_model(model), num_conformers=1, optimize=False
    )[0]
    model.conformers.append(ConformerModel(molblock=engine.mol_to_molblock(mol), energy=-1.0))
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    after = reader.settled()
    moved = {i: (drawn[i], after[i]) for i in drawn if i not in geometric and drawn[i] != after[i]}
    assert not moved, f"{row_id}: the conformer replaced the drawing's values: {moved}"
    assert reader.alerts == drawn_alerts, f"{row_id}: an alert catalogue was replaced by the conformer's"
    assert reader.per_atom == drawn_atoms, f"{row_id}: a per-atom dataset was replaced by the conformer's"
    # And the conformer DID answer what only it can -- exactly what the provider gives on that conformer (for a
    # single-component molecule a real number; ferrocene's parent has no conformer, and its shape stays refused).
    on_conformer = {
        v.descriptor_id: (v.cache_state, v.value)
        for v in RDKitDescriptorProvider().compute(engine.mol_from_molblock(model.conformers[0].molblock), model.uuid)
        if v.descriptor_id in geometric
    }
    assert {i: after[i] for i in geometric} == on_conformer
    if row_id != "ferrocene":
        assert all(state is CacheState.COMPLETED and value is not None for state, value in on_conformer.values())


def test_a_geometry_request_speaks_for_the_geometric_descriptors_only(qapp):
    """Not published, not recorded, not vouched for: no other descriptor, alert, per-atom dataset or part."""
    bus, engine, service, reader = _service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    assert {d.descriptor_id for d in reader.descriptor_events} == geometric
    assert reader.alert_events == 0 and reader.per_atom_events == 0
    assert reader.parts_finished == 0, "a geometry run must not vouch for the always-on set"
    assert {stored.result.descriptor_id for stored in reader.recorded} == geometric
    assert {stored.identity.calculation_input for stored in reader.recorded} == {GEOMETRY}


def test_removing_the_conformers_takes_the_shape_descriptors_back_to_needing_one(qapp):
    """The other direction of `_on_conformers_changed`: no conformer, so GEOMETRY resolves to the drawing."""
    bus, engine, service, reader = _service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)
    service.request_descriptors(model)
    _drain(qapp)  # a selection, then a conformer seconds later: not two tasks racing in one pool
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)
    assert reader.descriptors["pmi1"].cache_state is CacheState.COMPLETED
    kept = {i: v for i, v in reader.settled().items() if i not in RDKitDescriptorProvider().geometric_descriptor_ids()}

    model.conformers.clear()
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    assert reader.descriptors["pmi1"].cache_state is CacheState.FAILED
    assert reader.descriptors["pmi1"].error_summary == "Needs a 3D conformer"
    assert {i: v for i, v in reader.settled().items() if i in kept} == kept


def test_every_structure_level_descriptor_is_recorded_under_the_drawing_only(qapp):
    """The store keeps one slot per input: nothing structure-level may sit under GEOMETRY, or a replay puts it on top."""
    bus, engine, service, reader = _service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)
    service.request_descriptors(model)
    _drain(qapp)
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    under_geometry = {s.identity.result_id for s in reader.recorded if s.identity.calculation_input == GEOMETRY}
    assert under_geometry == {f"descriptor:rdkit:{i}" for i in geometric}
    assert any(s.identity.calculation_input == DRAWING and s.identity.result_id == "pains" for s in reader.recorded)


# --- a provider that is not the built-in one -----------------------------------------


class _Recording(DescriptorProvider):
    """Two descriptors, the second geometric; counts how often it is run and on what."""

    provider_id = "recording"

    def __init__(self, declares: frozenset[str] | None, raises: bool = False) -> None:
        self.declares = declares
        self.raises = raises
        self.computed: list[int] = []

    def descriptor_ids(self) -> list[str]:
        return ["graph_thing", "coordinate_thing"]

    def geometric_descriptor_ids(self) -> frozenset[str]:
        if self.raises:
            raise RuntimeError("a plugin bug")
        return self.declares if self.declares is not None else frozenset()

    def compute(self, mol, molecule_uuid):
        self.computed.append(mol.GetNumAtoms())
        return [
            DescriptorValue(descriptor_id=i, name=i, units="", category="x", provider=self.provider_id,
                            molecule_uuid=molecule_uuid, value=float(mol.GetNumAtoms()), cache_state=CacheState.COMPLETED)
            for i in self.descriptor_ids()
        ]


def test_a_plugin_provider_that_declares_nothing_is_never_run_on_a_geometry(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    plugin = _Recording(declares=None)
    service = DescriptorService(bus, engine, providers=[plugin])
    reader = _Reader(bus)
    model = _molecule(engine, "CCO", conformer=True)

    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)
    assert plugin.computed == [] and not reader.descriptor_events

    service.request_descriptors(model)
    _drain(qapp)
    assert plugin.computed == [3], "on the drawing it is run, with the heavy atoms only"


def test_a_plugin_provider_that_declares_one_is_scoped_to_it_even_if_compute_returns_more(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    plugin = _Recording(declares=frozenset({"coordinate_thing"}))
    service = DescriptorService(bus, engine, providers=[plugin])
    reader = _Reader(bus)
    model = _molecule(engine, "CCO", conformer=True)

    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    assert {d.descriptor_id for d in reader.descriptor_events} == {"coordinate_thing"}
    assert reader.descriptors["coordinate_thing"].value == 9.0, "computed on the conformer, hydrogens included"
    assert plugin.computed == [9]


def test_a_plugin_that_cannot_say_what_is_geometric_does_not_break_the_conformer_request(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    plugin = _Recording(declares=None, raises=True)
    service = DescriptorService(bus, engine, providers=[plugin, RDKitDescriptorProvider()])
    reader = _Reader(bus)
    model = _molecule(engine, "CCO", conformer=True)

    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    assert plugin.computed == []
    assert reader.descriptors["pmi1"].cache_state is CacheState.COMPLETED, "the other providers still ran"


# --- a molecule that ALREADY holds a conformer when it is selected -----------------------
#
# Reported 2026-10-14: a molecule selected with a usable conformer and no stored results (a project
# saved before results were kept, a set from another build, an import) showed all ten shape
# descriptors as FAILED "Needs a 3D conformer" until its conformers next changed, because the only
# GEOMETRY request was `MainWindow._on_conformers_changed`. The obvious fix -- a GEOMETRY request next
# to the DRAWING one -- LOSES: both tasks go to one pool, both write the same reader id, the reader
# keeps the latest, and the geometry run (ten descriptors) finishes before the drawing run (the whole
# provider), so the drawing's refusal arrived last in 37 of 40 measured runs. The fix gives each id
# one owner instead, so these tests pick the finishing order rather than hoping for one.


class _ManualPool:
    """Holds the tasks `DescriptorService` starts, so a test decides when and in what order they run."""

    def __init__(self) -> None:
        self.tasks: list = []

    def start(self, task) -> None:
        self.tasks.append(task)

    def task(self, calculation_input: str):
        return next(t for t in self.tasks if t._calculation_input == calculation_input)

    def task_for(self, calculation_input: str, molecule_uuid: str):
        return next(t for t in self.tasks
                    if t._calculation_input == calculation_input and t._model.uuid == molecule_uuid)

    def run(self, *calculation_inputs: str) -> None:
        for calculation_input in calculation_inputs:
            self.task(calculation_input).run()


def _manual_service(qapp):
    bus, engine, service, reader = _service(qapp)
    pool = _ManualPool()
    service._pool = pool
    return bus, engine, service, reader, pool


@pytest.mark.parametrize("order", [(DRAWING, GEOMETRY), (GEOMETRY, DRAWING)], ids=["drawing-first", "geometry-first"])
def test_a_selection_answers_the_shape_descriptors_whichever_run_finishes_last(qapp, order):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)

    service.request_descriptors(model)
    assert sorted(task._calculation_input for task in pool.tasks) == [DRAWING, GEOMETRY]
    pool.run(*order)
    qapp.processEvents()

    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    assert all(
        reader.descriptors[i].cache_state is CacheState.COMPLETED and reader.descriptors[i].value is not None
        for i in geometric
    ), {i: reader.descriptors[i].cache_state for i in geometric}
    refused = [d.descriptor_id for d in reader.descriptor_events
               if d.descriptor_id in geometric and d.cache_state is CacheState.FAILED]
    assert not refused, "the drawing run showed a refusal for an id the geometry run owns"
    # And the structure-level ones are still the drawing's.
    drawn = {d.descriptor_id: d.value for d in RDKitDescriptorProvider().compute(
        engine.mol_from_model(model), model.uuid) if d.descriptor_id not in geometric}
    assert {i: reader.descriptors[i].value for i in drawn} == drawn


def test_the_two_runs_split_the_ids_between_them_at_every_state(qapp):
    """The invariant behind the order test: an id has ONE publisher, queued, running and finished alike."""
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)

    service.request_descriptors(model)
    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    assert pool.task(DRAWING)._unshown == geometric
    assert pool.task(GEOMETRY)._only == geometric and not pool.task(GEOMETRY)._unshown

    pool.run(DRAWING, GEOMETRY)
    qapp.processEvents()
    for state in (CacheState.QUEUED, CacheState.RUNNING, CacheState.COMPLETED):
        announced = [d.descriptor_id for d in reader.descriptor_events if d.cache_state is state]
        assert len(announced) == len(set(announced)), f"an id was announced as {state.value} by both runs"


def test_the_drawing_run_still_records_the_shape_descriptors_so_the_manifest_does_not_depend_on_a_conformer(qapp):
    """RECORDED, NOT SHOWN: the always-on part names the same results with or without a conformer.

    `bundle_state` looks a part up by the DRAWING fingerprint alone. If the drawing run recorded fewer
    results when a conformer happened to be present, deleting the conformer would leave a COMPLETE part
    that never held the shape descriptors' refusal, and nothing would show "Needs a 3D conformer".
    """
    parts: dict[bool, tuple[str, ...]] = {}
    for with_conformer in (False, True):
        bus, engine, service, reader, pool = _manual_service(qapp)
        finished = []
        bus.subscribe(AutomaticPartFinished, lambda e, f=finished: f.append(e.part))
        model = _molecule(engine, _smiles_of("aspirin"), conformer=with_conformer)
        service.request_descriptors(model)
        pool.run(DRAWING)
        qapp.processEvents()
        (part,) = [p for p in finished if p.part_id == "rdkit"]
        parts[with_conformer] = tuple(sorted(part.result_ids))
        assert not part.failed
    assert parts[True] == parts[False]
    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    assert {f"descriptor:rdkit:{i}" for i in geometric} <= set(parts[True])


def test_a_molecule_with_no_conformer_is_still_answered_by_the_drawing_run_alone(qapp):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"))

    service.request_descriptors(model)

    assert [task._calculation_input for task in pool.tasks] == [DRAWING]
    pool.run(DRAWING)
    qapp.processEvents()
    assert reader.descriptors["pmi1"].cache_state is CacheState.FAILED
    assert reader.descriptors["pmi1"].error_summary == "Needs a 3D conformer"


def test_a_plugin_that_declares_nothing_gets_no_geometry_run_with_its_selection(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine, providers=[_Recording(declares=None)])
    pool = _ManualPool()
    service._pool = pool
    model = _molecule(engine, "CCO", conformer=True)

    service.request_descriptors(model)

    assert [task._calculation_input for task in pool.tasks] == [DRAWING]
    assert pool.tasks[0]._unshown == frozenset()


def _recorded_geometry(qapp, model):
    """The GEOMETRY-input results a geometry run records for `model`, as a replay would hand them back."""
    bus, engine, service, reader, pool = _manual_service(qapp)
    service.request_descriptors(model, GEOMETRY)
    pool.run(GEOMETRY)
    qapp.processEvents()
    return [s for s in reader.recorded if s.identity.calculation_input == GEOMETRY]


def test_the_shape_descriptors_a_replay_did_not_bring_back_are_asked_for(qapp):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)

    assert service.request_missing_geometric_descriptors(model, []) is True
    assert [(t._calculation_input, t._only) for t in pool.tasks] == [
        (GEOMETRY, RDKitDescriptorProvider().geometric_descriptor_ids())
    ]


def test_nothing_is_asked_for_when_the_replay_already_holds_them_or_the_provider_is_being_run(qapp):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"), conformer=True)
    held = _recorded_geometry(qapp, model)
    assert held, "setup: the geometry run recorded nothing"

    assert service.request_missing_geometric_descriptors(model, held) is False
    assert service.request_missing_geometric_descriptors(model, [], skip_providers={"rdkit"}) is False
    assert pool.tasks == [], "a dispatch was made that should not have been"


def test_nothing_is_asked_for_when_the_molecule_has_no_conformer(qapp):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"))

    assert service.request_missing_geometric_descriptors(model, []) is False
    assert pool.tasks == []


def test_a_recorded_refusal_counts_as_an_answer_so_it_is_not_retried_on_every_selection(qapp):
    """A 'conformer' that is not 3D makes the geometry run fall back to the drawing and be refused; that is held."""
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"))
    model.conformers.append(ConformerModel(molblock=model.molblock, energy=-1.0))  # flat: not 3D

    held = _recorded_geometry(qapp, model)

    assert held and all(s.result.cache_state is CacheState.FAILED for s in held)
    assert service.request_missing_geometric_descriptors(model, held) is False


# --- the conformer lands while an EARLIER drawing run is still running -----------------------
#
# The tests above cover a DRAWING request that sees the conformer. This is the other order: the
# selection dispatched a drawing run with no conformer to see (so it owns the shape descriptors and
# will publish "Needs a 3D conformer" for them), the conformer lands, `_on_conformers_changed` asks
# for GEOMETRY, and the drawing run is still running or still waiting in the pool. The geometry run
# (ten descriptors) usually finishes first and the late refusal beat its values: with the conformer
# landing 0-10 ms after the selection, 263 of 300 runs on aspirin and 235 of 300 on C12E6 ended
# FAILED. A GEOMETRY dispatch now CLAIMS the geometric ids from every drawing run started before it.


def _conformer_of(engine, smiles: str) -> ConformerModel:
    return _molecule(engine, smiles, conformer=True).conformers[0]


@pytest.mark.parametrize("order", [(GEOMETRY, DRAWING), (DRAWING, GEOMETRY)], ids=["geometry-first", "drawing-first"])
def test_a_conformer_that_lands_while_a_drawing_run_is_waiting_still_wins(qapp, order):
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"))
    conformer = _conformer_of(engine, _smiles_of("aspirin"))

    service.request_descriptors(model)  # the selection: no conformer yet
    assert [task._calculation_input for task in pool.tasks] == [DRAWING]
    model.conformers.append(conformer)  # the search finishes
    service.request_descriptors(model, GEOMETRY)  # MainWindow._on_conformers_changed
    assert sorted(task._calculation_input for task in pool.tasks) == [DRAWING, GEOMETRY]

    pool.run(*order)
    qapp.processEvents()

    geometric = RDKitDescriptorProvider().geometric_descriptor_ids()
    assert all(
        reader.descriptors[i].cache_state is CacheState.COMPLETED and reader.descriptors[i].value is not None
        for i in geometric
    ), {i: reader.descriptors[i].cache_state for i in geometric}
    refused = [d.descriptor_id for d in reader.descriptor_events
               if d.descriptor_id in geometric and d.cache_state is CacheState.FAILED]
    assert not refused, "a drawing run that started before the conformer showed its refusal after it"
    # The drawing run still RECORDED them: the always-on manifest does not depend on this timing.
    recorded = {s.result.descriptor_id for s in reader.recorded
                if s.identity.calculation_input == DRAWING and isinstance(s.result, DescriptorValue)}
    assert geometric <= recorded


def test_a_drawing_run_that_finished_before_the_conformer_is_left_alone(qapp):
    """The claim reaches only runs that have not published yet: the ordinary sequence is unchanged."""
    bus, engine, service, reader, pool = _manual_service(qapp)
    model = _molecule(engine, _smiles_of("aspirin"))

    service.request_descriptors(model)
    pool.run(DRAWING)
    qapp.processEvents()
    assert reader.descriptors["pmi1"].error_summary == "Needs a 3D conformer"

    model.conformers.append(_conformer_of(engine, _smiles_of("aspirin")))
    service.request_descriptors(model, GEOMETRY)
    pool.run(GEOMETRY)
    qapp.processEvents()
    assert reader.descriptors["pmi1"].cache_state is CacheState.COMPLETED


class _LandsMidRun(_Recording):
    """A provider whose `compute` is where the conformer lands, as when a search ends during a run."""

    def __init__(self, on_compute) -> None:
        super().__init__(declares=frozenset({"coordinate_thing"}))
        self._on_compute = on_compute

    def compute(self, mol, molecule_uuid):
        hook, self._on_compute = self._on_compute, None
        if hook is not None:
            hook()
        return super().compute(mol, molecule_uuid)


def test_a_conformer_that_lands_in_the_middle_of_a_drawing_run_takes_the_ids_from_it(qapp):
    """The claim arrives AFTER the run has started and BEFORE it publishes: the narrowest interleaving."""
    bus = EventBus()
    engine = ChemistryEngine()
    model = _molecule(engine, "CCO")
    conformer = _conformer_of(engine, "CCO")
    holder: dict = {}

    def lands() -> None:
        model.conformers.append(conformer)
        holder["service"].request_descriptors(model, GEOMETRY)

    service = DescriptorService(bus, engine, providers=[_LandsMidRun(lands)])
    holder["service"] = service
    reader = _Reader(bus)
    pool = _ManualPool()
    service._pool = pool

    service.request_descriptors(model)
    pool.run(DRAWING)  # the claim is made inside this run's compute()
    pool.run(GEOMETRY)
    qapp.processEvents()

    assert [d.value for d in reader.descriptor_events if d.descriptor_id == "coordinate_thing" and d.value is not None] == [9.0], (
        "the drawing run's 3.0 (heavy atoms only) reached the reader"
    )
    assert reader.descriptors["coordinate_thing"].value == 9.0
    assert reader.descriptors["graph_thing"].value == 3.0, "an id the geometry run does not own was taken too"
    recorded = {s.result.descriptor_id: s.result.value for s in reader.recorded if s.identity.calculation_input == DRAWING}
    assert recorded["coordinate_thing"] == 3.0, "the drawing run stopped recording what it no longer shows"


def test_a_claim_does_not_reach_another_molecule_or_a_later_drawing_run(qapp):
    bus, engine, service, reader, pool = _manual_service(qapp)
    claimed = _molecule(engine, _smiles_of("aspirin"))
    bystander = _molecule(engine, _smiles_of("ibuprofen"))
    service.request_descriptors(bystander)
    claimed.conformers.append(_conformer_of(engine, _smiles_of("aspirin")))
    service.request_descriptors(claimed, GEOMETRY)

    pool.task_for(DRAWING, bystander.uuid).run()
    qapp.processEvents()
    assert reader.descriptors["pmi1"].error_summary == "Needs a 3D conformer", "a claim for one molecule hid another's refusal"

    # The conformer goes away again (an undo), and the selection recomputes: that drawing run was
    # dispatched AFTER the claim, so it owns the ids and its refusal is the right answer.
    claimed.conformers.clear()
    service.request_descriptors(claimed)
    pool.task_for(DRAWING, claimed.uuid).run()
    qapp.processEvents()
    shown = [d for d in reader.descriptor_events if d.descriptor_id == "pmi1" and d.molecule_uuid == claimed.uuid]
    assert shown and shown[-1].cache_state is CacheState.FAILED, "a drawing run started after the claim was silenced"


def test_a_claim_cannot_land_between_a_runs_check_and_its_emit():
    """The check and the emit are one step: otherwise the refusal can still out-race the values."""
    claims = _GeometryClaims()
    stamp = claims.stamp()
    inside, claimed = threading.Event(), threading.Event()
    landed_during_emit: list[bool] = []

    def send() -> None:
        inside.set()
        time.sleep(0.2)  # long enough for the other thread to try, short enough not to slow the suite
        landed_during_emit.append(claimed.is_set())

    def claimant() -> None:
        inside.wait(5)
        claims.claim("m", "p", frozenset({"x"}))
        claimed.set()

    thread = threading.Thread(target=claimant)
    thread.start()
    assert claims.publish("m", "p", "x", stamp, send) is True
    thread.join(5)

    assert landed_during_emit == [False], "a claim was made while a drawing run was in the middle of emitting"
    assert claims.publish("m", "p", "x", stamp, lambda: None) is False, "and once made it must hold"
