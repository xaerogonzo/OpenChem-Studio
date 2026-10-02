"""Tautomer distribution: candidate generation, deterministic 3D embedding,
and population estimation from ORCA-computed electronic energies.

**What this is, precisely.** A gas-phase electronic-energy Boltzmann
population ESTIMATE over one optimized minimum per enumerated tautomer --
not a full equilibrium probability model. There is no vibrational, thermal,
or entropic correction, no solvent model, and no per-tautomer conformer
search (one deterministically-seeded embedded starting geometry, one
optimization, one minimum). `enumerate_tautomers`
(`chem/structure_generators.py`) already flags one tautomer "(canonical)"
using RDKit's own internal empirical scoring rules -- useful, but not a
probability, not an energy, and not validated against anything. This module
is the real thing: real ORCA energies, Boltzmann-weighted
(`chem/boltzmann.py`'s own `boltzmann_weights`, unmodified), with an
explicit, auditable incomplete-run story when not every candidate succeeds.

Orchestrating the actual ORCA jobs (sequential, one logical operation, one
`QuantumChemistryRun`) lives in `services/quantum_chemistry_service.py`,
mirroring its own existing `_BoltzmannRun`/`_finish_conformer_job`
machinery for "N QC jobs over N candidate structures of one molecule, one
Boltzmann-combined result" -- this module only does the chemistry-layer,
Qt-free pieces: which candidates exist, what their stable identity is, how
they get a 3D starting geometry, and what the final numbers mean.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.chem.boltzmann import STANDARD_TEMPERATURE_K, boltzmann_weights
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

#: 1 Hartree in kcal/mol (CODATA) -- the exact constant this project's own
#: Boltzmann tests already use (`tests/test_boltzmann.py`'s `KCAL_PER_MOL`
#: is `1 / this value`). Display-only: `boltzmann_weights` itself keeps
#: taking raw Hartree throughout, never this converted value.
HARTREE_TO_KCAL_PER_MOL = 627.5094740631

#: Matches `structure_generators.DEFAULT_MAX_STRUCTURES` -- the RDKit
#: enumerator's own cap, which is free. The expensive-QC cap below is a
#: separate, much smaller number.
DEFAULT_MAX_CANDIDATES = 200

#: Candidates at or under this count queue without confirmation; above it,
#: the caller must show the user the actual count ("this will run N
#: geometry optimizations with ORCA") before queuing them. This is
#: OpenChem's own expensive-QC-work threshold, not Marvin's unrelated
#: "eight tautomers shown at once" display convention -- chosen to land
#: near it, but justified by cost here, not by what Marvin's viewer shows.
CONFIRMATION_THRESHOLD = 8

#: A population below this is shown as "<0.01%" rather than a bare
#: "0.00%", which would read as exactly zero. Applied at display time only
#: -- the stored `population` value is always the full-precision weight
#: `boltzmann_weights` returned, never pre-rounded.
_SMALL_POPULATION_DISPLAY_FLOOR = 0.0001


def _fingerprint(molblock: str) -> str:
    """A candidate's stable identity: SHA-256 over its EXACT pre-embedding
    molblock text, never a canonicalized form -- the same technique
    `chem.calculation_input._fingerprint` uses, for the same reason (a
    cosmetic difference and a real structural difference must never
    collide). Taken before 3D embedding and never regenerated from the
    optimized geometry: different optimized coordinates for the same
    enumerated tautomer must not become a different candidate."""
    return hashlib.sha256(molblock.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TautomerCandidate:
    """One enumerated tautomer, deduplicated, embedded in 3D, ready for a
    geometry-optimization QC job."""

    fingerprint: str
    mol: Chem.Mol  # embedded: AddHs + a real 3D conformer
    embedding_seed: int


def generate_tautomer_candidates(
    mol: Chem.Mol, max_tautomers: int = DEFAULT_MAX_CANDIDATES, base_seed: int = 0
) -> tuple[list[TautomerCandidate], int]:
    """Enumerates, deduplicates, deterministically orders, and embeds every
    tautomer RDKit's standardizer can reach from `mol`.

    Returns `(candidates, embedding_failures)`. A candidate whose 3D
    embedding fails is dropped and counted, never silently merged into the
    others nor silently absent with no record at all -- the caller is
    expected to surface `embedding_failures` the same way it surfaces a
    failed QC job (see `CandidateStatus.FAILED`).

    Deliberately duplicates `structure_generators.enumerate_tautomers`'s
    own `TautomerEnumerator` setup rather than calling it: that function
    returns 2D-only `StructureEntry` molblocks for the structure grid, and
    must stay unchanged for its own existing callers/tests -- this needs
    raw, 3D-embeddable `Chem.Mol` objects instead.
    """
    enumerator = rdMolStandardize.TautomerEnumerator()
    enumerator.SetMaxTautomers(max_tautomers)
    tautomers = list(enumerator.Enumerate(mol))

    # Deduplicate by the same fingerprint used for candidate identity below
    # -- two enumerator outputs serializing to the same molblock become one
    # candidate, not two -- and sort by it, so queue order is deterministic
    # and independent of the enumerator's own (incidental) ordering.
    by_fingerprint: dict[str, Chem.Mol] = {}
    for tautomer in tautomers:
        molblock = Chem.MolToMolBlock(tautomer, kekulize=False)
        by_fingerprint.setdefault(_fingerprint(molblock), tautomer)

    candidates: list[TautomerCandidate] = []
    embedding_failures = 0
    for index, fingerprint in enumerate(sorted(by_fingerprint)):
        embedded, seed = _embed_candidate(by_fingerprint[fingerprint], base_seed, index)
        if embedded is None:
            embedding_failures += 1
            continue
        candidates.append(TautomerCandidate(fingerprint=fingerprint, mol=embedded, embedding_seed=seed))
    return candidates, embedding_failures


def _embed_candidate(mol: Chem.Mol, base_seed: int, index: int) -> tuple[Chem.Mol | None, int]:
    """One deterministic 3D embedding.

    Seed = `base_seed` offset by this candidate's own position in the
    already fingerprint-sorted list, not one shared seed consumed in
    sequence -- so a candidate's starting geometry stays stable
    independent of another candidate being added or removed. Same
    ETKDGv3 settings and random-coordinates retry
    `conformer_providers.py`'s own `_embed_one` uses, for the same reason:
    some strained/unusual structures fail ETKDG's distance-geometry pass
    on the first attempt.

    `Chem.AddHs` here only fills in currently-implicit hydrogens to match
    each atom's valence -- it does not move the tautomeric proton the
    enumerator already placed, so the candidate's intended protonation
    pattern survives into the embedded structure unchanged.
    """
    seed = base_seed + index
    conf_mol = Chem.AddHs(Chem.Mol(mol))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    conf_id = AllChem.EmbedMolecule(conf_mol, params)
    if conf_id < 0:
        params.useRandomCoords = True
        conf_id = AllChem.EmbedMolecule(conf_mol, params)
    if conf_id < 0:
        return None, seed
    return conf_mol, seed


class CandidateStatus(str, Enum):
    """A candidate's own outcome -- deliberately NOT `RunStatus`
    (`domain/quantum_chemistry_run.py`), which describes a whole run's
    lifecycle and a candidate is not itself a run; and deliberately not an
    added value on the shared `OutputStatus` either, since that enum's
    existing values are used across unrelated output kinds this feature
    has no business extending. A small, new, explicitly-scoped vocabulary
    instead, named closely enough that its meaning is obvious next to
    those two."""

    #: A usable energy was obtained: embedded, optimized, converged, parsed.
    SUCCEEDED = "succeeded"
    #: Attempted (embedding or the QC job) but did not produce a usable
    #: energy -- `failure_reason_code` says which specific way.
    FAILED = "failed"
    #: Enumerated and deduplicated, but never reached before the parent
    #: operation was cancelled.
    NOT_RUN = "not_run"


#: Machine-readable categories for `CandidateResult.failure_reason_code` --
#: easier to test/filter than parsing `failure_reason`'s prose later.
FAILURE_EMBEDDING_FAILED = "embedding_failed"
FAILURE_OPTIMIZATION_NOT_CONVERGED = "optimization_not_converged"
FAILURE_ENERGY_UNPARSEABLE = "energy_unparseable"
FAILURE_JOB_ERROR = "job_error"
FAILURE_CANCELLED = "cancelled"


@dataclass(frozen=True)
class CandidateResult:
    """One candidate's outcome, win or lose -- every deduplicated
    candidate gets one of these, never only the successful ones (an
    omitted failed candidate would make the enumerated set look smaller
    than it was)."""

    fingerprint: str
    molblock: str
    status: CandidateStatus
    embedding_seed: int = 0
    absolute_energy_hartree: float | None = None
    failure_reason: str = ""
    failure_reason_code: str = ""


@dataclass(frozen=True)
class TautomerDistributionOutcome:
    """The result of Boltzmann-combining every successful candidate's
    energy -- or the honest story when that is not possible.

    `relative_energy_kcal_mol` is keyed by fingerprint and computed
    relative to the lowest SUCCESSFUL candidate's energy. **That baseline
    is only the true global minimum when `complete` is True** -- a failed
    candidate could have been lower still, which would shift every
    reported gap. Consumers MUST read `complete` before presenting this
    dict under an unqualified "ΔE" label; see `energy_label` below.

    `populations` (fingerprint -> normalized weight, 0..1) is `None`
    whenever `complete` is False, by construction -- a distribution
    normalized over only the survivors is a different, weaker claim than
    "the distribution," and this type makes that unrepresentable rather
    than merely undocumented.
    """

    candidates: tuple[CandidateResult, ...]
    complete: bool
    relative_energy_kcal_mol: dict[str, float] = field(default_factory=dict)
    populations: dict[str, float] | None = None
    temperature_k: float = STANDARD_TEMPERATURE_K

    @property
    def energy_label(self) -> str:
        if self.complete:
            return "ΔE (kcal/mol)"
        return (
            "ΔE relative to the lowest successful candidate (kcal/mol) "
            "-- incomplete, one or more candidates failed"
        )

    @property
    def succeeded_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.FAILED)

    @property
    def not_run_count(self) -> int:
        return sum(1 for c in self.candidates if c.status is CandidateStatus.NOT_RUN)


def build_outcome(
    candidates: list[CandidateResult], temperature_k: float = STANDARD_TEMPERATURE_K
) -> TautomerDistributionOutcome:
    """Combines every candidate's own outcome into one auditable result.

    Never renormalizes over only the survivors and calls it the
    distribution -- `populations` is populated only when `complete` is
    True (every candidate succeeded). A survivor-relative `
    relative_energy_kcal_mol` is still reported for an incomplete run, so
    the real, measured energies are not hidden just because the set isn't
    complete -- `energy_label` is how a consumer is supposed to find out
    which baseline it's reading.
    """
    succeeded = [c for c in candidates if c.status is CandidateStatus.SUCCEEDED]
    complete = bool(candidates) and len(succeeded) == len(candidates)
    if not succeeded:
        return TautomerDistributionOutcome(candidates=tuple(candidates), complete=False, temperature_k=temperature_k)

    energies_hartree = [c.absolute_energy_hartree for c in succeeded]
    lowest = min(energies_hartree)
    relative = {
        c.fingerprint: (c.absolute_energy_hartree - lowest) * HARTREE_TO_KCAL_PER_MOL for c in succeeded
    }

    populations: dict[str, float] | None = None
    if complete:
        weights = boltzmann_weights(energies_hartree, temperature_k=temperature_k)
        populations = {c.fingerprint: weight for c, weight in zip(succeeded, weights, strict=True)}

    return TautomerDistributionOutcome(
        candidates=tuple(candidates),
        complete=complete,
        relative_energy_kcal_mol=relative,
        populations=populations,
        temperature_k=temperature_k,
    )


def format_population_percent(population: float) -> str:
    """Display formatting only -- `population` itself must already be the
    full-precision, unrounded weight (`build_outcome` never rounds)."""
    if population < 0:
        raise ValueError(f"a population cannot be negative: {population!r}")
    if population < _SMALL_POPULATION_DISPLAY_FLOOR:
        return "<0.01%"
    return f"{population * 100:.2f}%"


#: `StructureSetResult.provenance.parameters`'s own fixed, named keys --
#: not incidental spellings chosen per call site. `model_version` is the
#: single string every other key here feeds into (Design point 8/30):
#: change any one of them and `model_version` changes too, so a stale
#: `validation_branch` can never silently keep authorizing a percentage
#: under a model that has since moved on.
VALIDATION_UNVALIDATED = "unvalidated"
VALIDATION_RANKING_ONLY = "ranking_only"
VALIDATION_VALIDATED = "validated"


def model_version(method_basis: str, embedding_algorithm: str, temperature_k: float) -> str:
    """One short, stable string identifying the exact scientific-computation
    semantics behind a result -- covers computation only, deliberately
    excluding presentation (a label or rounding-policy change must never
    change this, Design point 8). Changing any input here is, by
    definition, a different model: a stored `validation_branch` from a
    different `model_version` must never be trusted for the current one."""
    return f"tautomer-boltzmann-v1|{method_basis}|{embedding_algorithm}|T={temperature_k:g}K"


def build_structure_set_result(
    outcome: TautomerDistributionOutcome,
    molecule_uuid: str,
    method_basis: str,
    run_id: str,
    validation_branch: str = VALIDATION_UNVALIDATED,
    embedding_algorithm: str = "ETKDGv3",
) -> StructureSetResult:
    """The user-facing result: one entry per deduplicated candidate
    (succeeded AND failed -- never only the survivors, which would make
    the enumerated set look smaller than it was), reusing the same
    `StructureSetResult`/`StructureEntry` shape and `StructureGridWidget`
    renderer `enumerate_tautomers`'s own result already uses.

    `StructureEntry.score` carries the normalized population (0..1, the
    field this project's own docstring already earmarks for "a relative
    weight") -- but **only once `validation_branch` is
    `VALIDATION_VALIDATED`**. `StructureGridWidget`'s shared caption
    renders any non-`None` `score` directly (`f"score {entry.score:.2f}"`)
    with no awareness of validation state, so this is the one place that
    gate has to be enforced -- an unvalidated or ranking-only result's
    real population is still computed (point 7) but is retained only in
    `metadata["population_unvalidated"]`, never in the field the shared
    grid actually displays, so nothing that looks like a percentage
    reaches the screen before it has been validated. `StructureEntry.energy`
    carries the relative energy in kcal/mol, labeled by `outcome.
    energy_label` at the result level so a reader knows whether it is the
    complete-set ΔE or a survivor-relative one (Design point 5's trap).
    """
    entries: list[StructureEntry] = []
    for candidate in outcome.candidates:
        mol = Chem.MolFromMolBlock(candidate.molblock) if candidate.molblock else None
        label = Chem.MolToSmiles(mol) if mol is not None else candidate.fingerprint[:12]
        metadata: dict = {
            "status": candidate.status.value,
            "fingerprint": candidate.fingerprint,
            "embedding_seed": candidate.embedding_seed,
        }
        if candidate.status is CandidateStatus.FAILED:
            metadata["failure_reason"] = candidate.failure_reason
            metadata["failure_reason_code"] = candidate.failure_reason_code
            label = f"{label} (failed: {candidate.failure_reason_code})"

        raw_population = None
        if outcome.populations is not None:
            raw_population = outcome.populations.get(candidate.fingerprint)
        # Computed and real, but withheld from the displayed `score` field
        # until the model is actually validated -- see the docstring above.
        population = raw_population if validation_branch == VALIDATION_VALIDATED else None
        if raw_population is not None:
            metadata["population_unvalidated"] = raw_population
        energy = outcome.relative_energy_kcal_mol.get(candidate.fingerprint)

        entries.append(
            StructureEntry(
                molblock=candidate.molblock,
                label=label,
                score=population,
                energy=energy,
                metadata=metadata,
            )
        )

    # Ascending |E| with a stable fingerprint tie-break -- never by
    # RDKit's own "canonical" pick (a separate concept, see this module's
    # own docstring), and a failed candidate (energy=None) sorts after
    # every succeeded one rather than raising or landing arbitrarily.
    entries.sort(key=lambda e: (e.energy is None, e.energy if e.energy is not None else 0.0, e.metadata["fingerprint"]))

    version = model_version(method_basis, embedding_algorithm, outcome.temperature_k)
    provenance = Provenance(
        created_by="core",
        method="orca",
        parameters={
            "population_model": "electronic-energy-boltzmann",
            "temperature_k": outcome.temperature_k,
            "validation_branch": validation_branch,
            "model_version": version,
            "method_basis": method_basis,
            "embedding_algorithm": embedding_algorithm,
            "candidate_count_expected": len(outcome.candidates),
            "candidate_count_succeeded": outcome.succeeded_count,
            "candidate_count_failed": outcome.failed_count,
            "candidate_count_not_run": outcome.not_run_count,
            "parent_run_id": run_id,
            "complete": outcome.complete,
            "energy_label": outcome.energy_label,
        },
    )

    return StructureSetResult(
        set_id="tautomer_distribution",
        name=f"Tautomer distribution ({len(entries)})",
        method="orca",
        molecule_uuid=molecule_uuid,
        entries=entries,
        provenance=provenance,
    )
