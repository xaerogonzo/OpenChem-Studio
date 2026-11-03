"""The ORCA runs the assistant may read about the selected molecule, frozen with the turn (`docs/AI_CALCULATION_BRIDGE.md`, "Reading the quantum-chemistry runs").

**A RUN IS NOT A STORED RESULT, AND THE ASSISTANT HAD NO WAY TO SEE ONE.** `SessionResultStore` is a bounded cache of the latest value of each calculator; the durable record of every ORCA job a person ran
lives in `QuantumChemistryRunStore` (`domain/quantum_chemistry_run.py`), with the method and basis, how the job ended, what it warned about and every output it produced. Descriptors and per-atom datasets are filed
in BOTH places, so `read_results` already offers an SCF energy; what only the run holds is the job that was FAILED or CANCELLED (a result store has nothing for it), the warnings a completed job came back with, a spectrum, a vibrational analysis, and
which of several runs at different methods a number came from. A question such as "did my NMR job finish?" or "why is there no IR for this molecule?" had no answer.

**A RUN IS FROZEN WITH THE TURN, AS EVERYTHING ELSE IS.** `QuantumChemistryRun` is a mutable dataclass, so `RunEntry` copies what a read needs (its scalar fields, a tuple of warnings, a copy of the output
mapping) and holds the output results themselves, which are frozen. A run finishing, being deleted or a project being replaced while the reply streams changes nothing the model was told.

**FRESHNESS IS THE SAME AXIS AS A RESULT'S, AND ENSEMBLE IS NEVER GUESSED.** A run is `CURRENT` when the input fingerprint it was run on equals the turn's fingerprint for the same kind of input (the drawing or the stored
conformer), `HISTORICAL` when it differs (the molecule was edited, or the conformers regenerated, since), and `UNVERIFIABLE` when there is nothing to compare it with: a run on an ensemble of conformers has no fingerprint in the
turn, and a run that kept none. A historical run is read only when asked for, and never as the answer for the structure now drawn.

**WHAT IS NEVER HERE:** the structure sent to ORCA (`input_molblock`, coordinates), the retained wavefunction's cache key, and ORCA's own output. A run's `warnings` are the application's sentences about what could not be parsed, bounded
by the envelope's caps; they are the one free text a job can carry, and a model that is told "the spectrum could not be parsed" must not be told it was computed.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.domain.turn_snapshot import Freshness

if TYPE_CHECKING:
    from openchem.domain.turn_snapshot import TurnContext


class JobOutcome(str, Enum):
    """What a run says, on a different axis from how fresh it is."""

    #: The job finished and every output it was asked for parsed.
    COMPUTED = "computed"
    #: The job finished with a result and the application reports something that did not come back (a coupling matrix that would not parse).
    COMPUTED_WITH_WARNINGS = "computed_with_warnings"
    #: The core output never parsed: there is no number to offer.
    FAILED = "failed"
    #: A person stopped it.
    CANCELLED = "cancelled"


#: How each way a stored run can end reads as an outcome. A running job is never persisted and is never in the store; if one ever arrived it is read as unfinished (FAILED), never as a result.
_OUTCOME_OF = {
    RunStatus.COMPLETED: JobOutcome.COMPUTED,
    RunStatus.COMPLETED_WITH_WARNINGS: JobOutcome.COMPUTED_WITH_WARNINGS,
    RunStatus.FAILED: JobOutcome.FAILED,
    RunStatus.CANCELLED: JobOutcome.CANCELLED,
    RunStatus.RUNNING: JobOutcome.FAILED,
}


@dataclass(frozen=True)
class RunEntry:
    """One stored ORCA run, as it was when the turn began, classified against the structure the turn began with."""

    run_id: str
    calc_type: str
    method_basis: str
    charge: int
    multiplicity: int
    solvent: str
    provider: str
    #: DRAWING, GEOMETRY or ENSEMBLE (`domain/calculator.py`): which kind of structure it was run on.
    calculation_input: str
    #: The first 16 characters, as a result's `input` block gives them.
    input_fingerprint: str
    started_at: float
    completed_at: float | None
    status: RunStatus
    outcome: JobOutcome
    freshness: Freshness
    #: Why it is not current, when it is not.
    note: str
    warnings: tuple[str, ...]
    #: output key -> why it is or is not there, as the run recorded it.
    output_status: Mapping[str, OutputStatus]
    #: output key -> the result object(s). Frozen dataclasses; a list is held as a tuple.
    outputs: Mapping[str, tuple[Any, ...]]
    #: True when the run added an optimized geometry to the molecule's conformers.
    produced_geometry: bool

    @property
    def usable(self) -> bool:
        """The run holds numbers a person could be told: it finished and computed something."""
        return self.outcome in (JobOutcome.COMPUTED, JobOutcome.COMPUTED_WITH_WARNINGS)


def _classify(run: QuantumChemistryRun, fingerprints: Mapping[str, str]) -> tuple[Freshness, str]:
    current = fingerprints.get(run.calculation_input)
    if not run.input_fingerprint:
        return Freshness.UNVERIFIABLE, "the run carries no input fingerprint"
    if current is None:
        return Freshness.UNVERIFIABLE, f"the molecule has no {run.calculation_input} fingerprint to compare it with"
    if run.input_fingerprint != current:
        return Freshness.HISTORICAL, "run on an earlier structure of this molecule"
    return Freshness.CURRENT, ""


def _held(value: Any) -> tuple[Any, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else (value,)


def entry_of(run: QuantumChemistryRun, fingerprints: Mapping[str, str]) -> RunEntry:
    freshness, note = _classify(run, fingerprints)
    return RunEntry(
        run_id=run.run_id,
        calc_type=run.calc_type,
        method_basis=run.method_basis,
        charge=run.charge,
        multiplicity=run.multiplicity,
        solvent=run.solvent,
        provider=run.provider,
        calculation_input=run.calculation_input,
        input_fingerprint=(run.input_fingerprint or "")[:16],
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        outcome=_OUTCOME_OF[run.status],
        freshness=freshness,
        note=note,
        warnings=tuple(str(w) for w in run.warnings),
        output_status=MappingProxyType(dict(run.output_status)),
        outputs=MappingProxyType({key: _held(value) for key, value in run.results.items()}),
        produced_geometry=bool(run.output_conformer_id),
    )


#: Where each freshness sorts in a list of runs: what still describes the structure first, what cannot be vouched for last.
_FRESHNESS_ORDER = {Freshness.CURRENT: 0, Freshness.HISTORICAL: 1, Freshness.UNVERIFIABLE: 2}


def classify_runs(runs: Iterable[QuantumChemistryRun], fingerprints: Mapping[str, str]) -> tuple[RunEntry, ...]:
    """Every run of the molecule, newest first within each freshness, current first."""
    entries = [entry_of(run, fingerprints) for run in runs]
    entries.sort(key=lambda e: (_FRESHNESS_ORDER[e.freshness], -e.started_at))
    return tuple(entries)


#: The most runs one read lists. A molecule a person has run twenty jobs on is the exception, and each is a header.
DEFAULT_RUN_LIMIT = 10

#: The most runs one read returns WITH their numbers. Measured against the reply budget (`tests/test_ai_assistant_quantum_runs.py`): ten runs asked for by id came to 14,193 characters at the smallest detail
#: step, over the 12,000 a reply may have, because every run carries a header that is never dropped. Three fit with room; the model asks again for the rest, and the reply says how many it left out.
DETAIL_RUN_LIMIT = 3


@dataclass(frozen=True)
class RunsView:
    """What `read_quantum_runs` hands back."""

    turn_id: str
    molecule_uuid: str
    entries: tuple[RunEntry, ...]
    #: A `run_id` that was asked for and is not among this turn's runs.
    not_found: tuple[str, ...] = ()
    #: Matching runs left out to respect the limit.
    truncated: int = 0
    #: Runs that are not current and were not asked for: counted, never listed.
    not_current_left_out: int = 0
    #: True when one run was asked for by id, so its numbers are offered; a list carries headers only.
    detailed: bool = False


def read_runs(
    turn: TurnContext,
    run_ids: Iterable[str] | None = None,
    *,
    include_not_current: bool = False,
    limit: int = DEFAULT_RUN_LIMIT,
) -> RunsView:
    """The turn's runs: a list of headers, or one or more runs in full when named by id.

    A named run is returned whatever its freshness, and carries it, because the person or the model asked for
    exactly that run; a list shows only `CURRENT` runs unless `include_not_current` is set, and counts the others.
    """
    entries, turn_id, molecule_uuid = turn.runs, turn.turn_id, turn.molecule_uuid
    wanted = list(dict.fromkeys(run_ids)) if run_ids is not None else None
    if wanted:
        by_id = {e.run_id: e for e in entries}
        found = tuple(by_id[r] for r in wanted if r in by_id)
        missing = tuple(r for r in wanted if r not in by_id)
        cap = max(0, min(limit, DETAIL_RUN_LIMIT))
        return RunsView(turn_id, molecule_uuid, found[:cap], not_found=missing, truncated=max(0, len(found) - cap), detailed=True)
    shown = tuple(e for e in entries if include_not_current or e.freshness is Freshness.CURRENT)
    limit = max(0, limit)
    return RunsView(
        turn_id,
        molecule_uuid,
        shown[:limit],
        truncated=max(0, len(shown) - limit),
        not_current_left_out=0 if include_not_current else len(entries) - len(shown),
    )
