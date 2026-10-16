"""`ReplaceConformerCommand`, `AddConformerCommand(show=True)` and the regeneration helper.

The slot is the point: an ORCA optimisation replaces the conformer it started from, so the list keeps its
length and every other conformer keeps its place. Every test builds a list where the source is NOT first,
because a test whose source happens to be slot 0 passes for an implementation that always writes slot 0.
"""

from __future__ import annotations

from PySide6.QtGui import QUndoStack

from openchem.chem.calculation_input import (
    find_source_conformer,
    geometry_fingerprint,
    with_kept_quantum_optimized,
    with_optimization_origin,
)
from openchem.commands.conformer_commands import (
    AddConformerCommand,
    ReplaceConformerCommand,
    SetConformersCommand,
)
from openchem.domain.common import RUN_METHOD_BASIS, Provenance
from openchem.domain.conformer import (
    OPTIMIZED_FROM_ID,
    OPTIMIZED_FROM_SLOT,
    ORCA_OPTIMIZED,
    ConformerModel,
    is_quantum_optimized,
    quantum_level_of_theory,
)
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged


def _twenty() -> list[ConformerModel]:
    return [ConformerModel(molblock=f"mmff-{i}", energy=float(i), method="mmff94") for i in range(20)]


def _orca(molblock: str = "orca") -> ConformerModel:
    return ConformerModel(molblock=molblock, method=ORCA_OPTIMIZED)


def _events(bus: EventBus) -> list[ConformersChanged]:
    seen: list[ConformersChanged] = []
    bus.subscribe(ConformersChanged, seen.append)
    return seen


def test_a_replacement_takes_the_slot_of_its_source_and_nothing_else_moves(qapp):
    bus = EventBus()
    conformers = _twenty()
    before = list(conformers)
    molecule = MoleculeModel(display_name="Test", conformers=conformers)
    seen = _events(bus)
    replacement = _orca()
    stack = QUndoStack()

    stack.push(ReplaceConformerCommand(molecule, before[6], replacement, bus))  # "7 of 20"

    assert len(molecule.conformers) == 20
    assert molecule.conformers[6] is replacement
    assert [c for i, c in enumerate(molecule.conformers) if i != 6] == [c for i, c in enumerate(before) if i != 6]
    assert [e.show_conformer_id for e in seen] == [replacement.conformer_id], "the viewer is told where to land"


def test_undo_puts_the_very_same_original_object_back_in_the_slot(qapp):
    bus = EventBus()
    conformers = _twenty()
    original = conformers[6]
    snapshot = (original.molblock, original.energy, original.method, original.conformer_id)
    molecule = MoleculeModel(display_name="Test", conformers=conformers)
    seen = _events(bus)
    stack = QUndoStack()
    stack.push(ReplaceConformerCommand(molecule, original, _orca(), bus))

    stack.undo()

    assert molecule.conformers[6] is original, "the object itself, not a copy"
    assert (original.molblock, original.energy, original.method, original.conformer_id) == snapshot
    assert seen[-1].show_conformer_id == original.conformer_id, "undo shows the geometry that is current again"

    stack.redo()
    assert molecule.conformers[6].method == ORCA_OPTIMIZED
    assert len(molecule.conformers) == 20


def test_the_source_is_found_by_identity_so_a_reordered_list_is_replaced_at_its_new_slot(qapp):
    bus = EventBus()
    conformers = _twenty()
    source = conformers[6]
    molecule = MoleculeModel(display_name="Test", conformers=conformers)
    stack = QUndoStack()
    command = ReplaceConformerCommand(molecule, source, _orca(), bus)
    molecule.conformers = [source, *[c for c in conformers if c is not source]]  # moved to the front meanwhile

    stack.push(command)

    assert molecule.conformers[0].method == ORCA_OPTIMIZED
    assert len(molecule.conformers) == 20


def test_a_source_that_is_gone_at_redo_is_appended_and_undo_removes_exactly_that(qapp):
    """The fallback is not silent and not a raise: the finished geometry is the user's, so it is added; and
    undo must reverse what redo DID, not what it was built to do."""
    bus = EventBus()
    conformers = _twenty()
    gone = ConformerModel(molblock="regenerated-away", method="mmff94")
    molecule = MoleculeModel(display_name="Test", conformers=list(conformers))
    seen = _events(bus)
    replacement = _orca()
    stack = QUndoStack()

    stack.push(ReplaceConformerCommand(molecule, gone, replacement, bus))

    assert molecule.conformers == [*conformers, replacement]
    assert seen[-1].show_conformer_id == replacement.conformer_id

    stack.undo()
    assert molecule.conformers == conformers, "no original to restore, and none invented"
    assert seen[-1].show_conformer_id == ""

    stack.redo()
    assert molecule.conformers == [*conformers, replacement]


def test_undo_does_nothing_to_a_list_that_no_longer_holds_the_replacement(qapp):
    """A regeneration replaced the list wholesale after the swap. Restoring the original would put a
    conformer into a list it was never part of."""
    bus = EventBus()
    conformers = _twenty()
    molecule = MoleculeModel(display_name="Test", conformers=conformers)
    stack = QUndoStack()
    stack.push(ReplaceConformerCommand(molecule, conformers[6], _orca(), bus))
    fresh = _twenty()
    molecule.conformers = list(fresh)

    stack.undo()

    assert molecule.conformers == fresh


def test_add_with_show_names_the_conformer_and_without_it_does_not(qapp):
    bus = EventBus()
    molecule = MoleculeModel(display_name="Test", conformers=_twenty())
    seen = _events(bus)
    stack = QUndoStack()
    shown, quiet = _orca("shown"), _orca("quiet")

    stack.push(AddConformerCommand(molecule, shown, bus, show=True))
    stack.push(AddConformerCommand(molecule, quiet, bus))

    assert [e.show_conformer_id for e in seen] == [shown.conformer_id, ""]
    stack.undo()
    stack.undo()
    assert seen[-1].show_conformer_id == "", "undo of an add never points at a conformer that is gone"


def test_generating_again_keeps_the_orca_conformers_after_the_new_ones_in_their_order():
    first, second = _orca("first"), _orca("second")
    existing = [*_twenty()[:3], first, *_twenty()[3:5], second]
    generated = [ConformerModel(molblock=f"new-{i}", method="mmff94") for i in range(4)]

    kept = with_kept_quantum_optimized(generated, existing, keep=True)

    assert kept == [*generated, first, second]
    assert kept[4] is first and kept[5] is second, "the same objects: ids, provenance and atom maps untouched"


def test_generating_again_replaces_everything_when_the_choice_is_off():
    existing = [*_twenty()[:3], _orca()]
    generated = [ConformerModel(molblock="new", method="mmff94")]

    assert with_kept_quantum_optimized(generated, existing, keep=False) == generated


def test_a_kept_orca_conformer_without_a_molblock_is_not_kept():
    empty = ConformerModel(molblock="", method=ORCA_OPTIMIZED)
    assert with_kept_quantum_optimized([], [empty, _orca()], keep=True)[0].molblock == "orca"


def test_regeneration_with_kept_conformers_undoes_to_the_exact_previous_list(qapp):
    bus = EventBus()
    orca = _orca()
    previous = [*_twenty()[:5], orca]
    molecule = MoleculeModel(display_name="Test", conformers=list(previous))
    stack = QUndoStack()
    generated = [ConformerModel(molblock="new", method="mmff94")]

    stack.push(
        SetConformersCommand(molecule, with_kept_quantum_optimized(generated, previous, True), bus, kept=1)
    )
    assert molecule.conformers == [*generated, orca]
    assert "keeping 1 ORCA-optimized" in stack.undoText()
    assert "Generate 1 conformer(s)" in stack.undoText()

    stack.undo()
    assert molecule.conformers == previous


def test_find_source_conformer_finds_by_fingerprint_and_reports_the_zero_based_slot():
    conformers = _twenty()
    fingerprint = geometry_fingerprint(conformers[6])

    assert find_source_conformer(conformers, fingerprint) == (6, conformers[6])
    assert find_source_conformer(conformers, "") is None, "a result with no single source finds nothing"
    assert find_source_conformer(conformers, "not-a-fingerprint") is None
    regenerated = [ConformerModel(molblock=c.molblock, method="mmff94") for c in conformers]
    assert find_source_conformer(regenerated, fingerprint) is None, "same text, new ids: not the same conformer"


def test_the_origin_is_merged_into_the_provenance_and_never_replaces_it():
    source = _twenty()[6]
    provenance = Provenance(
        created_by="core", method="orca", parameters={"orca_version": "6.0.1", RUN_METHOD_BASIS: "B3LYP def2-SVP"}
    )
    optimized = ConformerModel(molblock="o", method=ORCA_OPTIMIZED, provenance=provenance)

    stamped = with_optimization_origin(optimized, source.conformer_id, 7)

    assert stamped.provenance.parameters["orca_version"] == "6.0.1"
    assert stamped.provenance.parameters[RUN_METHOD_BASIS] == "B3LYP def2-SVP"
    assert stamped.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert stamped.provenance.parameters[OPTIMIZED_FROM_SLOT] == 7, "the slot the caller says it was at Run, as given"
    assert stamped.conformer_id == optimized.conformer_id, "the run record names this id as its output"
    assert optimized.provenance.parameters.keys() == {"orca_version", RUN_METHOD_BASIS}, "the input is untouched"


def test_an_optimized_conformer_with_no_provenance_gets_one():
    source = _twenty()[0]

    stamped = with_optimization_origin(_orca(), source.conformer_id, 1)

    assert stamped.provenance is not None
    assert stamped.provenance.parameters[OPTIMIZED_FROM_SLOT] == 1


def test_an_unknown_run_slot_records_the_source_and_no_slot_never_a_guess():
    """Zero means the caller did not know it. Substituting where the geometry landed would describe something else."""
    source = _twenty()[6]

    stamped = with_optimization_origin(_orca(), source.conformer_id, 0)

    assert stamped.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert OPTIMIZED_FROM_SLOT not in stamped.provenance.parameters


def test_the_origin_survives_a_save_and_reopen():
    source = _twenty()[6]
    stamped = with_optimization_origin(_orca(), source.conformer_id, 7)

    reloaded = ConformerModel.from_dict(stamped.to_dict())

    assert reloaded.provenance.parameters[OPTIMIZED_FROM_ID] == source.conformer_id
    assert reloaded.provenance.parameters[OPTIMIZED_FROM_SLOT] == 7


def test_the_level_of_theory_is_read_from_the_provenance_and_empty_means_not_recorded():
    provenance = Provenance(created_by="core", method="orca", parameters={RUN_METHOD_BASIS: "HF STO-3G"})

    assert quantum_level_of_theory(ConformerModel(method=ORCA_OPTIMIZED, provenance=provenance)) == "HF STO-3G"
    assert quantum_level_of_theory(ConformerModel(method=ORCA_OPTIMIZED)) == ""
    assert is_quantum_optimized(_orca()) and not is_quantum_optimized(_twenty()[0])
