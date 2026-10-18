"""Which molecule a calculation is actually handed.

THE POLICY LIVES HERE AND NOWHERE ELSE. Six places had reimplemented
`conformers[0] if conformers else the drawing` inline -- `main_window`,
`property_panel`, `docking_panel`, `quantum_chemistry_panel`,
`batch_service`, and `io_backends.mol_for_export`. Six copies is not six
bugs today, it is one bug the day the policy changes: the moment
"lowest-energy conformer" becomes "the conformer the user is looking at",
five of them are wrong and nothing points at them.

Pure by design -- a model and a policy in, a molecule out, no services
and no UI. That is what makes the whole no-conformer / one-conformer /
many-conformer matrix testable without constructing half the
application, which is the difference between that matrix existing and
being skipped.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import logging
from collections.abc import Sequence
from typing import NamedTuple

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, ENSEMBLE, GEOMETRY
from openchem.domain.common import Provenance
from openchem.domain.conformer import (
    OPTIMIZED_FROM_ID,
    OPTIMIZED_FROM_SLOT,
    QUANTUM_OPTIMIZED_METHODS,
    ConformerModel,
    is_quantum_optimized,
    quantum_level_of_theory,
)
from openchem.domain.molecule import MoleculeModel

logger = logging.getLogger("openchem.chemistry")


def canonical_conformer(model: MoleculeModel) -> ConformerModel | None:
    """The conformer a calculation should use, or None.

    **1. A GEOMETRY A QUANTUM OPTIMIZATION PRODUCED, THE NEWEST ONE.** A
    person who optimizes a molecule in ORCA and then asks for anything else
    -- an NMR, a hardness, a descriptor, a docking -- means the optimized
    geometry. Before this rule an ORCA-optimized conformer was stored
    without an energy, sorted last, and was never chosen while any
    force-field conformer had one: measured 2026-10-12, the next job ran on
    the force-field conformer. Newest rather than lowest, because an ORCA
    energy and an MMFF energy are not on one scale and two optimizations at
    different levels of theory are not comparable by energy either: the
    most recent one is what the person last asked for. Undoing the
    optimization removes the conformer, and the rule below applies again.

    **2. OTHERWISE, THE LOWEST MMFF94 ENERGY AMONG THE CONFORMERS RETAINED BY
    WHATEVER SAMPLING RUN PRODUCED THEM.** Never "the lowest-energy conformer"
    unqualified -- that is a claim about the molecule, and this is a
    claim about one random search under one force field. The provenance
    on each conformer carries the force field, the counts and the
    de-duplication parameters so the weaker claim stays checkable.

    ENERGYLESS CONFORMERS SORT LAST RATHER THAN CRASHING. A project saved
    before energies were recorded, or one generated with `optimize=False`,
    contains them; geometry is perfectly usable without an energy and only
    the ORDERING needs one. They are selected only when nothing has an
    energy at all, in which case list order is the only information there
    is.
    """
    if not model.conformers:
        return None
    optimized = [
        (position, c)
        for position, c in enumerate(model.conformers)
        if c.method in QUANTUM_OPTIMIZED_METHODS and c.molblock
    ]
    if optimized:
        # List position breaks a tie in the timestamps: the one appended last is the newest.
        return max(optimized, key=lambda pair: (pair[1].timestamp, pair[0]))[1]
    energised = [c for c in model.conformers if c.energy is not None and c.molblock]
    if energised:
        return min(energised, key=lambda c: c.energy)
    usable = [c for c in model.conformers if c.molblock]
    return usable[0] if usable else None


def select_calculation_input(
    engine: ChemistryEngine, model: MoleculeModel, calculation_input: str = DRAWING
) -> Chem.Mol:
    """The molecule to hand a calculator declaring `calculation_input`.

    See `resolve_calculation_input`, which this is the molecule half of.
    """
    return resolve_calculation_input(engine, model, calculation_input).mol


class ResolvedInput(NamedTuple):
    """The molecule a calculation is handed, and a fingerprint OF THAT INPUT.

    **ONE RESOLUTION PRODUCES BOTH, AND THAT IS THE POINT.** A retained
    result is reusable only while the input it was computed on is still the
    input a rerun would get. If the fingerprint were worked out separately
    -- "hash the molblock, add the conformer id for geometry" -- it would
    agree with this function until the day the fallback rules below change,
    and then a result would read as fresh while the calculator would be
    handed different coordinates. So the key is produced by the same
    branches that pick the molecule.

    `mol` is None when only the fingerprint was asked for.

    `used` is the input the molecule actually CAME FROM -- DRAWING or
    GEOMETRY -- which is not always the one asked for: a GEOMETRY request
    with no usable 3D conformer is handed the drawing. Stated rather than
    left to be inferred from the fingerprint matching the drawing's, which
    is true by construction today and would stay silently true as a test
    of fallback if the fingerprint rules below ever changed.
    """

    mol: Chem.Mol | None
    fingerprint: str
    used: str


def geometry_fingerprint(conformer: ConformerModel) -> str:
    """The `GEOMETRY` fingerprint of ONE stored conformer: kind, id and exact molblock.

    The one place it is built, so `resolve_calculation_input` and anything that has to find
    the conformer a result was computed on from its fingerprint cannot disagree.
    """
    return _fingerprint(GEOMETRY, conformer.conformer_id, conformer.molblock or "")


def with_source_atom_map(
    optimized: ConformerModel,
    conformers: Sequence[ConformerModel],
    source_fingerprint: str,
    engine: ChemistryEngine,
) -> ConformerModel:
    """`optimized` carrying the drawing-atom map of the conformer it was optimized FROM.

    **AN OPTIMIZATION KEEPS THE ATOM ORDER, SO THE MAP STILL HOLDS, AND NOTHING COPIED IT.** The
    ORCA engine writes the final Cartesian block back onto the molecule it was handed, atom
    for atom, but builds a new `ConformerModel` that knows nothing of `drawing_atom_ids`. That
    was harmless while the optimized geometry was never used as an input; now that
    `canonical_conformer` prefers it, every per-atom 3D result computed on it would have lost
    its recorded way back to the drawing, and `chem.atom_identity` would fall back to matching
    the structures, which refuses a symmetric molecule whose equivalent atoms differ.

    The source is found by the fingerprint the job was submitted with. It is left alone (and
    the map stays "not recorded", never guessed) when the source is gone, was never mapped, or
    has a different atom count.
    """
    if not source_fingerprint or optimized.drawing_atom_ids is not None:
        return optimized
    located = find_source_conformer(conformers, source_fingerprint)
    source = located[1] if located is not None else None
    if source is None or source.drawing_atom_ids is None or source.drawing_fingerprint is None:
        return optimized
    if len(source.drawing_atom_ids) != engine.mol_from_molblock(optimized.molblock).GetNumAtoms():
        return optimized
    return dataclasses.replace(
        optimized,
        drawing_atom_ids=list(source.drawing_atom_ids),
        drawing_fingerprint=source.drawing_fingerprint,
    )


def find_source_conformer(
    conformers: Sequence[ConformerModel], source_fingerprint: str
) -> tuple[int, ConformerModel] | None:
    """The conformer (and its zero-based slot) a job was submitted on, or None.

    Found by the `GEOMETRY` fingerprint, which holds the conformer's id AND its exact molblock, so a
    list that was regenerated since the job started does not contain it and the answer is None. An
    empty fingerprint (a result with no single source) finds nothing.
    """
    if not source_fingerprint:
        return None
    return next(
        ((slot, c) for slot, c in enumerate(conformers) if geometry_fingerprint(c) == source_fingerprint), None
    )


def with_optimization_origin(
    optimized: ConformerModel, source_id: str, source_slot: int
) -> ConformerModel:
    """`optimized` with where it came from written into its provenance (MERGED, never replaced).

    Records the source's `conformer_id` and `source_slot`, its ONE-BASED slot WHEN RUN WAS PRESSED
    (`domain.conformer.OPTIMIZED_FROM_SLOT`): the input the calculation used, not wherever the
    replacement ends up. A slot of 0 means the caller did not know it and NOTHING is written for it
    (never the landing slot in its place, which would describe something else). The provenance the
    job's own landing already carries (`orca_version`, the run's method and basis) is kept; a
    conformer with no provenance gets one rather than losing the record.
    """
    origin: dict[str, object] = {OPTIMIZED_FROM_ID: source_id}
    if source_slot > 0:
        origin[OPTIMIZED_FROM_SLOT] = source_slot
    provenance = optimized.provenance
    if provenance is None:
        provenance = Provenance(created_by="core", method=optimized.method, parameters=origin)
    else:
        provenance = dataclasses.replace(provenance, parameters={**provenance.parameters, **origin})
    return dataclasses.replace(optimized, provenance=provenance)


def with_kept_quantum_optimized(
    generated: Sequence[ConformerModel], existing: Sequence[ConformerModel], keep: bool
) -> list[ConformerModel]:
    """The conformer list after a regeneration: the new ones, then the ORCA-optimized ones that were there.

    **WHAT "KEEP" PROMISES, EXACTLY.** The quantum-optimized conformers survive, in their original
    relative order, AFTER the generated ones. They are the same objects, so their ids, provenance and
    atom maps are untouched. It does NOT promise their slot numbers: "7 of 20 stays 7 of 20" holds
    while an optimization replaces its source; after a regeneration the kept geometries follow the new
    conformers. Off (`keep` False) is the old behaviour: the generated set replaces everything.

    An optimized conformer whose molblock is empty is dropped, as nothing could use it.
    """
    kept = (
        [c for c in existing if c.method in QUANTUM_OPTIMIZED_METHODS and c.molblock] if keep else []
    )
    return [*generated, *kept]


def _fingerprint(*parts: str) -> str:
    """SHA-256 over the EXACT stored text, not a canonical form.

    Deliberately not canonicalised: the claim is "this is the input the
    calculation received", and a cosmetic re-save of a molblock costing one
    recompute is a far cheaper mistake than two different inputs sharing a
    key because a normaliser judged them equivalent.
    """
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def input_fingerprint(
    engine: ChemistryEngine, model: MoleculeModel, calculation_input: str = DRAWING
) -> str:
    """The fingerprint the resolver for `calculation_input` would give, for comparing.

    DRAWING needs no parse. GEOMETRY does, because whether the conformer is
    used at all depends on it parsing into something 3D -- and that decision
    is part of the input. ENSEMBLE needs none either: a run over the set is
    refused rather than degraded when a member is unusable, so the stored
    text alone names the input.

    **AN UNKNOWN KIND RAISES.** This used to hash anything that was not
    GEOMETRY as the drawing, so a result stamped with a kind this function
    did not know would have been compared against the DRAWING and could
    read as fresh. A comparison that cannot be made must not pass.
    """
    if calculation_input == DRAWING:
        return _fingerprint(DRAWING, model.molblock or "")
    if calculation_input == GEOMETRY:
        return resolve_calculation_input(engine, model, calculation_input).fingerprint
    if calculation_input == ENSEMBLE:
        return _ensemble_fingerprint(model.conformers)
    raise ValueError(f"Unknown calculation input {calculation_input!r}")


def _ensemble_fingerprint(conformers: list[ConformerModel]) -> str:
    """SHA-256 over every conformer's id and exact molblock, IN STORED ORDER.

    **ORDER IS PART OF THE IDENTITY, ON PURPOSE.** Reordering the same
    conformers changes this and marks a result over them stale. That costs a
    recompute in a case where the average would not have moved, and it is
    the conservative side: sorting here would make the fingerprint claim
    something about the chemistry (that order cannot matter to any consumer)
    which nothing has checked. Pinned by a test so an "optimisation" that
    sorts ids fails loudly.

    Ids are part of it as well as geometry: two conformers with identical
    coordinates and different ids are different records, and a result names
    records.
    """
    parts: list[str] = [ENSEMBLE, str(len(conformers))]
    for conformer in conformers:
        parts.extend((conformer.conformer_id, conformer.molblock or ""))
    return _fingerprint(*parts)


class ResolvedEnsemble(NamedTuple):
    """Every conformer a set-valued run is handed, and the fingerprint of that set.

    The same rule as `ResolvedInput`: one read of `model.conformers` produces
    both, so what is submitted and what is fingerprinted cannot drift apart
    -- which they could if the fingerprint were taken again when the result
    arrives, because the conformer list can change while a job runs.
    """

    mols: tuple[Chem.Mol, ...]
    fingerprint: str


def resolve_ensemble(engine: ChemistryEngine, model: MoleculeModel) -> ResolvedEnsemble:
    """Every stored conformer as a 3D molecule, in stored order, or a refusal.

    **REFUSES RATHER THAN SKIPPING.** A run over "the conformers" that
    quietly dropped an unusable one would carry a fingerprint naming a set it
    was not computed over, or a fingerprint over fewer conformers than the
    project holds -- either way a name that does not match the input. So a
    member with no molblock, one that will not parse, or one that is not 3D
    raises `ValueError` naming it, and the caller says so.
    """
    conformers = list(model.conformers)
    if not conformers:
        raise ValueError("The molecule has no conformers to average over.")
    mols = []
    for position, conformer in enumerate(conformers, start=1):
        if not conformer.molblock:
            raise ValueError(f"Conformer {position} has no structure.")
        try:
            mol = engine.mol_from_molblock(conformer.molblock)
        except Exception as exc:  # noqa: BLE001 - reported to the caller, not swallowed
            raise ValueError(f"Conformer {position} cannot be read: {exc}") from exc
        if mol.GetNumConformers() == 0 or not mol.GetConformer().Is3D():
            raise ValueError(f"Conformer {position} has no 3D coordinates.")
        mols.append(mol)
    return ResolvedEnsemble(tuple(mols), _ensemble_fingerprint(conformers))


def resolve_calculation_input(
    engine: ChemistryEngine, model: MoleculeModel, calculation_input: str = DRAWING
) -> ResolvedInput:
    """The molecule to hand a calculator declaring `calculation_input`.

    `DRAWING` returns the drawn structure unchanged -- byte-for-byte what
    every calculator received before this policy existed, whether or not
    the molecule has conformers. That is not a fallback, it is the
    default: eight of the 49 registered calculators return a different
    number when handed a conformer purely because it carries explicit
    hydrogens, and they are not wrong today.

    `GEOMETRY` returns a validated 3D conformer when one exists and the
    drawing when none does. Validated means: the conformer has a
    molblock, it parses, and `Conformer.Is3D()` is true -- because a
    molblock from the 2D editor always parses into exactly one conformer
    with flat z, so `GetNumConformers() > 0` is true and useless as a
    check.

    A conformer that will not parse falls back to the drawing with a log
    line rather than failing the calculation, which is what
    `batch_service` already did for the same case.
    """
    if calculation_input == GEOMETRY:
        return resolve_conformer_input(engine, model, canonical_conformer(model))
    return _drawing_input(engine, model)


def resolve_conformer_input(
    engine: ChemistryEngine, model: MoleculeModel, conformer: ConformerModel | None
) -> ResolvedInput:
    """The molecule to hand a calculation that runs on ONE named conformer.

    **The same validation `resolve_calculation_input` applies to the canonical conformer, for any
    conformer**, so a job started on the one a person picked can neither be handed an unusable
    geometry nor stamped with an identity that does not describe what it received. A conformer that
    will not parse, or is not 3D, falls back to the drawing exactly as the canonical one does; the
    caller can tell from `used`, and must not present the fallback as the conformer it asked for.

    `conformer` None (a molecule with none) is the drawing.
    """
    if conformer is not None:
        try:
            mol = engine.mol_from_molblock(conformer.molblock)
        except Exception:  # noqa: BLE001 - the drawing remains a valid answer
            logger.exception(
                "Conformer %s of molecule %s is unusable; using the drawn structure",
                conformer.conformer_id,
                model.uuid,
            )
        else:
            if mol.GetNumConformers() > 0 and mol.GetConformer().Is3D():
                return ResolvedInput(mol, geometry_fingerprint(conformer), GEOMETRY)
            logger.info(
                "Conformer %s of molecule %s is not 3D; using the drawn structure",
                conformer.conformer_id,
                model.uuid,
            )
    return _drawing_input(engine, model)


def _drawing_input(engine: ChemistryEngine, model: MoleculeModel) -> ResolvedInput:
    """The drawing, fingerprinted as the DRAWING.

    The DRAWING fingerprint for a geometry request that fell back, on purpose: the calculator really
    was handed the drawing, so a result computed that way is the same input as a drawing-policy one.
    """
    molblock = model.molblock or ""
    return ResolvedInput(engine.mol_from_model(model), _fingerprint(DRAWING, molblock), DRAWING)


#: Every key `geometry_provenance` adds carries this prefix.
#:
#: **IT IS NOT COSMETIC.** These keys are merged into a provenance the
#: CALCULATOR also writes, and the two describe different things that
#: want the same words: this layer records what the calculator was
#: HANDED, the calculator records what it DID. Unprefixed, two collided
#: on the 49 registered calculators:
#:
#:     steric_analysis     geometry_source = "free_ligand_mmff"
#:                         (how its cone-angle scan built its OWN
#:                          conformers, not which stored one it was given)
#:     molecular_dynamics  force_field = "MMFF94"
#:                         (what it ran the trajectory with, not what the
#:                          conformer was minimised with)
#:
#: Only one of those was found by reading the code; the other came out of
#: a sweep over every calculator, which is why the guard in
#: `tests/test_calculation_input.py` iterates the whole registry rather
#: than checking the names anybody happened to notice.
#:
#: Prefixing rather than renaming case by case means a calculator may use
#: any parameter name it likes without this layer having to know.
INPUT_PREFIX = "input_"

#: The key that says how many separate pieces the conformer a result was computed on is made of (`geometry_provenance`). The domain reads it by this literal
#: (`score_value.FRAGMENTS_KEY`, which cannot import this layer), and a test holds the two together.
FRAGMENTS_KEY = f"{INPUT_PREFIX}fragments"

#: The key that says what made the conformer a result was computed on (`ConformerModel.method`: `mmff94`, `orca_opt`...). The domain reads it by this literal (`score_value.CONFORMER_METHOD_KEY`), and a test holds the two together.
CONFORMER_METHOD_KEY = f"{INPUT_PREFIX}conformer_method"

#: The key that names the level of theory of a quantum-optimized conformer (`"B3LYP def2-SVP"`); absent when it was not recorded. Read by the domain as `score_value.LEVEL_OF_THEORY_KEY`.
LEVEL_OF_THEORY_KEY = f"{INPUT_PREFIX}level_of_theory"


#: What a recorded parameter value may be. **JSON-safe scalars only**, and
#: that is a persistence constraint rather than fastidiousness:
#: `Provenance.to_dict` puts `parameters` straight into the saved project,
#: so one unserialisable value breaks saving for the whole project rather
#: than for the calculator that produced it.
_RECORDABLE = (str, int, float, bool, type(None))


def recordable_parameters(parameters: dict[str, object] | None) -> dict[str, object]:
    """`parameters` reduced to what can be persisted and replayed.

    **A result is only reproducible if it says what it was computed
    with**, and until this existed nothing recorded that: the routing
    layer noted which CONFORMER a calculator was handed and never which
    settings it ran under. Anything replaying a calculation -- the 3D
    overlay recomputing for the conformer on screen, a future "rerun
    this" -- would silently have used today's defaults instead, which is
    a different calculation wearing the original's label.

    **Values that cannot be persisted are DROPPED, not stringified.** A
    `repr()` is not a parameter: it cannot be fed back to `compute()`,
    and storing one would turn "I cannot replay this" into a value that
    looks replayable. A caller that finds a parameter missing must refuse
    to replay rather than substitute a default -- see the overlay's
    origin resolution.

    Lists and tuples of scalars are kept (flattened to lists, since JSON
    has no tuple) because a range or a set of thresholds is an ordinary
    parameter shape; anything nested deeper is dropped rather than walked,
    because no registered calculator takes one and a recursive validator
    nobody needs is a place for bugs to live.
    """
    if not parameters:
        return {}
    kept: dict[str, object] = {}
    for name, value in parameters.items():
        if isinstance(value, _RECORDABLE):
            kept[str(name)] = value
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, _RECORDABLE) for item in value
        ):
            kept[str(name)] = list(value)
        else:
            logger.debug(
                "Parameter %r is not persistable (%s); it will not be recorded",
                name,
                type(value).__name__,
            )
    return kept


@functools.lru_cache(maxsize=256)
def fragment_count(molblock: str) -> int | None:
    """How many separate pieces the structure in `molblock` is made of (a salt is two, a hydrate two), or None when it cannot be read.

    Unsanitised on purpose: this counts bonded components and nothing else, so a metal complex that sanitisation would refuse is still counted.
    """
    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False) if molblock else None
    return len(Chem.GetMolFrags(mol)) if mol is not None and mol.GetNumAtoms() else None


def geometry_provenance(model: MoleculeModel, calculation_input: str) -> dict[str, object]:
    """What to record about which geometry a result was computed on.

    Every key is prefixed (see `INPUT_PREFIX`) because these are merged
    into the calculator's own provenance and the two vocabularies
    overlap.

    THE ID, NOT ONLY THE INDEX. Index 0 today is index 3 tomorrow -- the
    list is re-sorted whenever conformers are regenerated -- so a result
    that cites only a position cannot be traced back to a geometry. The
    index is kept alongside because it is what the viewer shows, and
    "conformer 1 of 23" is how a person will describe it.

    THE FRAGMENT COUNT is the number of separate pieces of that conformer. Where one piece sits
    relative to another in 3D is not a property of the compound (the embedder packs them together at
    an arbitrary offset), so a derived score declines a number a calculator measured on the WHOLE
    structure when it has more than one (`score_value.not_applicable_reason`). Left out when the
    count cannot be read, which that rule treats as unknown and refuses.
    """
    if calculation_input != GEOMETRY:
        return {f"{INPUT_PREFIX}source": "drawing"}
    conformer = canonical_conformer(model)
    if conformer is None:
        return {
            f"{INPUT_PREFIX}source": "drawing",
            f"{INPUT_PREFIX}reason": "no conformer available",
        }
    stamp: dict[str, object] = {
        f"{INPUT_PREFIX}source": "automatic_lowest_energy",
        f"{INPUT_PREFIX}conformer_id": conformer.conformer_id,
        f"{INPUT_PREFIX}conformer_index": model.conformers.index(conformer),
        f"{INPUT_PREFIX}conformer_energy": conformer.energy,
        f"{INPUT_PREFIX}force_field": (
            conformer.provenance.parameters.get("force_field") if conformer.provenance else None
        ),
    }
    # What made the geometry, because a number that reads bond lengths means something different on a force-field conformer (the force field's own lengths) than on a measured one: the level of
    # theory is named for a quantum-optimized conformer, and left out when it was not recorded (a project saved before the run's method was written into the conformer).
    stamp[CONFORMER_METHOD_KEY] = conformer.method
    if is_quantum_optimized(conformer):
        level = quantum_level_of_theory(conformer)
        if level:
            stamp[LEVEL_OF_THEORY_KEY] = level
    fragments = fragment_count(conformer.molblock)
    if fragments is not None:
        stamp[FRAGMENTS_KEY] = fragments
    return stamp
