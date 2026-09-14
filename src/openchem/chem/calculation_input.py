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

import hashlib
import logging
from typing import NamedTuple

from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, ENSEMBLE, GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel

logger = logging.getLogger("openchem.chemistry")


def canonical_conformer(model: MoleculeModel) -> ConformerModel | None:
    """The conformer a calculation should use, or None.

    THE LOWEST MMFF94 ENERGY AMONG THE CONFORMERS RETAINED BY WHATEVER
    SAMPLING RUN PRODUCED THEM. Never "the lowest-energy conformer"
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
        conformer = canonical_conformer(model)
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
                    return ResolvedInput(
                        mol,
                        _fingerprint(GEOMETRY, conformer.conformer_id, conformer.molblock or ""),
                        GEOMETRY,
                    )
                logger.info(
                    "Conformer %s of molecule %s is not 3D; using the drawn structure",
                    conformer.conformer_id,
                    model.uuid,
                )
    # The DRAWING fingerprint for a geometry request that fell back, on
    # purpose: the calculator really was handed the drawing, so a result
    # computed that way is the same input as a drawing-policy one.
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
    """
    if calculation_input != GEOMETRY:
        return {f"{INPUT_PREFIX}source": "drawing"}
    conformer = canonical_conformer(model)
    if conformer is None:
        return {
            f"{INPUT_PREFIX}source": "drawing",
            f"{INPUT_PREFIX}reason": "no conformer available",
        }
    return {
        f"{INPUT_PREFIX}source": "automatic_lowest_energy",
        f"{INPUT_PREFIX}conformer_id": conformer.conformer_id,
        f"{INPUT_PREFIX}conformer_index": model.conformers.index(conformer),
        f"{INPUT_PREFIX}conformer_energy": conformer.energy,
        f"{INPUT_PREFIX}force_field": (
            conformer.provenance.parameters.get("force_field") if conformer.provenance else None
        ),
    }
