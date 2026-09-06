"""Docking N ligands into one receptor, in order, and ranking them.

`DockingService` docks ONE ligand into ONE receptor. Virtual screening is
that N times, and the only genuinely new thing it needs is a queue --
which is not a detail. Handing N requests to `DockingService` at once
would start N Vina processes on the thread pool simultaneously; measured
runtimes for a single ligand are seconds to minutes, so a 50-ligand screen
would launch 50 concurrent Vina runs and compete for every core on the
machine at once. This runs them one at a time.

SEQUENCED BY LISTENING, NOT BY BLOCKING. The next ligand is submitted from
the handler for the previous one's terminal event, so nothing here holds a
thread waiting. `EventBus.publish` is a queued Qt signal, so those handlers
run on the GUI thread even though the docking task that published them ran
on a worker -- which is exactly where the next `request_docking` should be
made from.

WHY THE RECEPTOR IS ONE AND THE LIGANDS ARE MANY. That asymmetry is the
whole point of a screen and it is also what makes the result comparable:
every score comes from the same receptor, the same box and the same
scoring function, so the RANKING means something even though the absolute
kcal/mol do not. This project has already been bitten by the opposite --
a docking result and its analysis reading different receptors -- so the
receptor is captured once, at request time, and never re-resolved per
ligand.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

from openchem.chem.engine import ChemistryEngine
from openchem.domain.affinity_range import (
    SEPARATION_ALPHA,
    AffinityRange,
    dominance_rank,
    separation_p_value,
)
from openchem.domain.common import CacheState
from openchem.domain.docking import DockingBox, DockingReplicate, DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import Event, EventBus
from openchem.events.events import DockingJobStateChanged, DockingResultReady
from openchem.services.docking_service import (
    DEFAULT_NUM_POSES,
    DEFAULT_REPLICATES,
    DockingService,
)
from openchem.services.job_manager import JobManager

logger = logging.getLogger("openchem.chemistry")

SCREENING_JOB_KIND = "screening"
SCREENING_JOB_KEY = "project"


@dataclass(frozen=True, kw_only=True)
class ScreeningEntry:
    """One ligand's outcome.

    `best_affinity_kcal_mol` is the MINIMUM over the poses, because Vina
    reports affinities as negative numbers where more negative is better --
    a max would rank the worst pose of each ligand, which is a mistake that
    produces a plausible-looking and exactly inverted table.

    A failed ligand keeps its row with an `error`. A screen where 3 of 50
    ligands failed to prepare is a normal outcome, and dropping them would
    make the screen look like it covered a library it did not.
    """

    molecule_uuid: str
    display_name: str
    best_affinity_kcal_mol: float | None = None
    pose_count: int = 0
    error: str | None = None
    #: Every run behind this ligand's score, empty when the screen ran one
    #: search per ligand or when the result predates replicates.
    #:
    #: A DEFAULTED FIELD ON A `kw_only` DATACLASS, so every existing
    #: construction site is unmoved -- the same additive shape
    #: `DockingResultModel.replicates` has one layer down.
    replicates: tuple[DockingReplicate, ...] = ()

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def spread(self) -> AffinityRange | None:
        """The scores this ligand produced, or None if it produced none.

        ONE VALUE IS A HONEST RANGE AND NOT A SYNTHESISED RECORD. A ligand
        docked once has exactly one score, and `AffinityRange((best,))` says
        so: n = 1, `width` None, and every pair involving it comes back
        `NOT_ASSESSED`. That is a different act from `DockingResultModel.
        from_dict` refusing to manufacture a replicate SET for a legacy
        result -- that would be a stored claim about how a run was performed,
        where this is a transient statement about how many scores are in hand.
        """
        values = tuple(
            replicate.best_affinity_kcal_mol
            for replicate in self.replicates
            if replicate.best_affinity_kcal_mol is not None
        )
        if values:
            return AffinityRange(values)
        if self.best_affinity_kcal_mol is None:
            return None
        return AffinityRange((self.best_affinity_kcal_mol,))


@dataclass(frozen=True, kw_only=True)
class ScreeningProtocol:
    """How a screen was run, resolved -- so it can be run again.

    A screen docks N ligands under ONE protocol, which is what makes its
    ranking mean anything, so this is recorded once for the screen rather
    than once per ligand. Same asymmetry the module docstring already draws
    around the receptor.

    **NOTHING HERE IS DEFAULTED TO A LITERAL, AND THAT IS THE WHOLE POINT.**
    `_DockingTask` once filled `scoring_function="vina"`, `exhaustiveness=8`
    and `seed=None` with literals that were true only by coincidence, and
    this project's own note on it is that a stored result naming settings it
    did not use is WORSE than one naming none -- nothing distinguishes it
    from a measurement. So:

        requested_*   what the caller asked for. None means "not asked",
                      not "asked for the default".
        engine, engine_version, scoring_function, exhaustiveness
                      RESOLVED FROM THE FIRST RESULT, because only the
                      provider knows which Vina backend answered, what
                      version it is, and what it fell back to when the
                      caller specified nothing.

    `protocol_seed` is the seed the caller PINNED, and is deliberately not
    the seed Vina received: seeds are derived per (protocol_seed, ligand)
    so that two ligands' replicate values are independent samples. The
    per-run seeds live on each entry's replicates, where they belong.
    """

    receptor_macromolecule_uuid: str = ""
    receptor_display_name: str = ""
    num_poses: int = DEFAULT_NUM_POSES
    replicates: int = DEFAULT_REPLICATES
    #: What the caller asked for. None means the caller specified nothing.
    requested_exhaustiveness: int | None = None
    requested_scoring_function: str | None = None
    #: "" is a real value here -- the caller explicitly chose no rescore --
    #: and None means the caller never mentioned it.
    rescore_with: str | None = None
    protocol_seed: int | None = None
    receptor_prep_options: dict[str, Any] = field(default_factory=dict)
    #: Filled in from the first completed result, empty until one lands.
    engine: str = ""
    engine_version: str = ""
    scoring_function: str = ""
    exhaustiveness: int | None = None

    @property
    def resolved(self) -> bool:
        """True once a result has told us what actually ran.

        A caller rendering this before then must say so rather than print
        the requested values as though they were the performed ones.
        """
        return bool(self.engine)

    def resolved_against(self, result: "DockingResultModel") -> "ScreeningProtocol":
        """This protocol with the run's own answers filled in.

        Called on every result and not only the first, so it is idempotent
        by construction: a screen runs one protocol, so the second result
        writes the same values the first did. If it ever did not, the
        replacement is the honest record of what the LAST run did rather
        than a stale claim from the first.
        """
        return replace(
            self,
            engine=result.engine,
            engine_version=result.engine_version,
            scoring_function=result.scoring_function,
            exhaustiveness=result.exhaustiveness,
        )


@dataclass(frozen=True)
class ScreeningProgress(Event):
    """How far a screen has got, and every result so far, best first."""

    state: CacheState
    completed: int
    total: int
    receptor_macromolecule_uuid: str = ""
    message: str = ""
    entries: list[ScreeningEntry] = field(default_factory=list)
    error: str | None = None
    #: How the screen was run. None only for a progress event constructed
    #: without one -- the service always sets it, so a caller seeing None
    #: is looking at a fixture rather than a screen.
    protocol: ScreeningProtocol | None = None


class ScreeningService:
    """One screen at a time, tracked through the shared `JobManager`."""

    def __init__(
        self,
        event_bus: EventBus,
        docking_service: DockingService,
        engine: ChemistryEngine,
        job_manager: JobManager | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._docking_service = docking_service
        self._engine = engine
        self._job_manager = job_manager if job_manager is not None else JobManager()
        self._queue: list[MoleculeModel] = []
        self._names: dict[str, str] = {}
        self._entries: list[ScreeningEntry] = []
        self._receptor: MacromoleculeModel | None = None
        self._box: DockingBox | None = None
        self._num_poses = DEFAULT_NUM_POSES
        self._replicates = DEFAULT_REPLICATES
        self._prep_options: dict[str, Any] = {}
        self._search_options: dict[str, Any] = {}
        self._protocol: ScreeningProtocol | None = None
        self._total = 0
        self._current_uuid: str | None = None
        self._cancelled = False
        event_bus.subscribe(DockingResultReady, self._on_docking_result)
        event_bus.subscribe(DockingJobStateChanged, self._on_docking_state)

    def is_running(self) -> bool:
        return self._job_manager.is_active(SCREENING_JOB_KIND, SCREENING_JOB_KEY)

    def request_screen(
        self,
        ligands: list[MoleculeModel],
        receptor: MacromoleculeModel,
        box: DockingBox,
        num_poses: int = DEFAULT_NUM_POSES,
        receptor_prep_options: dict[str, Any] | None = None,
        search_options: dict[str, Any] | None = None,
        replicates: int = DEFAULT_REPLICATES,
    ) -> None:
        """Dock every ligand into one receptor, in order.

        `search_options` reaches `request_docking` unchanged. Until it
        existed a screen ran at whatever the provider defaulted to and
        **could not be pinned even in principle**, while a single dock
        could -- so a screen was the one operation this application offers
        for RANKING and the one that could not be reproduced.
        """
        if not ligands:
            self._reject("No ligands selected to screen.")
            return
        if not self._job_manager.try_start(
            SCREENING_JOB_KIND, SCREENING_JOB_KEY, cancel_callback=self.cancel
        ):
            self._reject("A virtual screen is already in progress.")
            return
        self._queue = list(ligands)
        self._names = {molecule.uuid: molecule.display_name for molecule in ligands}
        self._entries = []
        self._receptor = receptor
        self._box = box
        self._num_poses = num_poses
        self._replicates = max(1, int(replicates))
        self._prep_options = dict(receptor_prep_options or {})
        self._search_options = dict(search_options or {})
        # BUILT FROM WHAT WAS ASKED, never from the provider's defaults --
        # see ScreeningProtocol. `.get` returns None for a key the caller
        # omitted, which is exactly the distinction the record needs.
        self._protocol = ScreeningProtocol(
            receptor_macromolecule_uuid=receptor.uuid,
            receptor_display_name=receptor.display_name,
            num_poses=num_poses,
            replicates=self._replicates,
            requested_exhaustiveness=self._search_options.get("exhaustiveness"),
            requested_scoring_function=self._search_options.get("scoring_function"),
            rescore_with=self._search_options.get("rescore_with"),
            protocol_seed=self._search_options.get("seed"),
            receptor_prep_options=dict(self._prep_options),
        )
        self._total = len(ligands)
        self._cancelled = False
        self._publish(CacheState.QUEUED, f"{self._total} ligands against {receptor.display_name}")
        self._submit_next()

    def cancel(self) -> None:
        """Stop after the ligand currently in Vina.

        Best-effort, and the limit is inherited rather than introduced:
        `VinaDockingProvider` checks for cancellation at its own phase
        boundaries, and the search itself is one blocking call neither Vina
        backend interrupts. So a cancelled screen stops submitting; it does
        not kill the run already in flight.
        """
        self._cancelled = True
        self._queue.clear()

    # -- the queue --------------------------------------------------------

    def _submit_next(self) -> None:
        if self._cancelled or not self._queue:
            self._finish()
            return
        molecule = self._queue.pop(0)
        self._current_uuid = molecule.uuid
        # Checked before calling, not caught afterwards: `mol_from_model`
        # raises `InvalidStructureError("Molecule <uuid> has no molblock")`,
        # and a uuid is not something to show a user who simply has not
        # drawn the molecule yet.
        if not molecule.molblock:
            self._record(molecule.uuid, molecule.display_name, error="This molecule has no structure yet.")
            self._submit_next()
            return
        try:
            mol = self._engine.mol_from_model(molecule)
        except Exception as exc:  # noqa: BLE001 - one bad ligand must not end the screen
            logger.exception("Screening could not read ligand %s", molecule.uuid)
            self._record(molecule.uuid, molecule.display_name, error=f"Could not read this structure: {exc}")
            self._submit_next()
            return
        self._publish(
            CacheState.RUNNING,
            f"{len(self._entries) + 1}/{self._total}: docking {molecule.display_name}",
        )
        self._docking_service.request_docking(
            ligand_molecule_uuid=molecule.uuid,
            ligand_mol=mol,
            receptor_macromolecule_uuid=self._receptor.uuid,
            receptor_structure_text=self._receptor.structure_text,
            receptor_source_format=self._receptor.source_format,
            box=self._box,
            num_poses=self._num_poses,
            receptor_prep_options=self._prep_options,
            # THE WHOLE POINT OF THIS BRANCH. Without this line the dialog's
            # exhaustiveness, scoring function, seed and rescore are computed,
            # displayed, recorded in the protocol -- and discarded here, which
            # is `BatchRequest.molecule_uuids` in another costume: a field
            # written by every caller and read by nothing.
            search_options=self._search_options,
            # N MULTIPLIES THE WHOLE SCREEN -- 50 ligands x 5 replicates is 250
            # Vina runs -- which is why the dialog defaults it to 1 and states
            # the product before the run rather than after it.
            replicates=self._replicates,
        )

    def _on_docking_result(self, event: DockingResultReady) -> None:
        if not self._is_ours(event.result.ligand_molecule_uuid):
            return
        poses = event.result.poses
        best = min((pose.binding_affinity_kcal_mol for pose in poses), default=None)
        # The poses are the MEDIAN replicate's, so `best` is the median run's
        # best score -- the same number the Docking panel prints as the centre.
        # Taking the minimum over all replicates here would rank ligands by a
        # best-of-N, which drifts more negative as the replicate count rises.
        replicates = event.result.replicates
        # RESOLVED FROM THE RUN, not assumed. Only the provider knows which
        # Vina backend answered, its version, and what it used when the
        # caller specified nothing.
        if self._protocol is not None:
            self._protocol = self._protocol.resolved_against(event.result)
        self._record(
            event.result.ligand_molecule_uuid,
            self._name_of(event.result.ligand_molecule_uuid),
            best_affinity_kcal_mol=best,
            pose_count=len(poses),
            error=None if poses else "Docking produced no poses.",
            replicates=tuple(replicates.replicates) if replicates is not None else (),
        )

    def _on_docking_state(self, event: DockingJobStateChanged) -> None:
        """Advance the queue on a terminal docking state.

        COMPLETED is where the queue moves, not `DockingResultReady`:
        the result event fires first and carries the poses, but only the
        state event is guaranteed for BOTH outcomes. Advancing on the
        result alone would leave a screen wedged forever on the first
        ligand Vina refused.
        """
        if not self._is_ours(event.ligand_molecule_uuid):
            return
        if event.state is CacheState.FAILED:
            if not self._already_recorded(event.ligand_molecule_uuid):
                self._record(
                    event.ligand_molecule_uuid,
                    self._name_of(event.ligand_molecule_uuid),
                    error=event.message or "Docking failed.",
                )
            self._current_uuid = None
            self._submit_next()
        elif event.state is CacheState.COMPLETED:
            self._current_uuid = None
            self._submit_next()

    def _is_ours(self, ligand_uuid: str) -> bool:
        """Only react to the docking job THIS screen submitted.

        `DockingService` is shared, and a user is free to run a one-off
        docking from the Docking panel while a screen is going. Without
        this check that unrelated result would be recorded into the screen
        and would advance its queue, skipping a ligand.
        """
        return self.is_running() and ligand_uuid == self._current_uuid

    def _already_recorded(self, molecule_uuid: str) -> bool:
        return any(entry.molecule_uuid == molecule_uuid for entry in self._entries)

    def _name_of(self, molecule_uuid: str) -> str:
        """Captured at request time, not looked up later.

        The docking events carry only uuids, and the service holds no
        project -- so the names have to be taken when the ligands are
        handed in or they are not recoverable at all, and a results table
        of uuids is not a results table.
        """
        return self._names.get(molecule_uuid, molecule_uuid)

    def _record(self, molecule_uuid: str, display_name: str, **fields) -> None:
        self._entries.append(
            ScreeningEntry(molecule_uuid=molecule_uuid, display_name=display_name, **fields)
        )

    def _finish(self) -> None:
        self._job_manager.finish(SCREENING_JOB_KIND, SCREENING_JOB_KEY)
        state = CacheState.FAILED if self._cancelled else CacheState.COMPLETED
        message = (
            f"Cancelled after {len(self._entries)} of {self._total} ligands."
            if self._cancelled
            else f"{len(self._entries)} ligands screened."
        )
        self._current_uuid = None
        self._publish(state, message)

    def _publish(self, state: CacheState, message: str) -> None:
        self._job_manager.update_message(SCREENING_JOB_KIND, SCREENING_JOB_KEY, message)
        self._event_bus.publish(
            ScreeningProgress(
                state=state,
                completed=len(self._entries),
                total=self._total,
                receptor_macromolecule_uuid=self._receptor.uuid if self._receptor else "",
                message=message,
                entries=rank(self._entries),
                # EVERY progress event, not only the terminal one. A screen
                # that is cancelled or fails halfway still ran the ligands it
                # ran under a protocol, and a reader looking at a partial
                # table needs to know which one.
                protocol=self._protocol,
            )
        )

    def _reject(self, message: str) -> None:
        self._event_bus.publish(
            ScreeningProgress(
                state=CacheState.FAILED, completed=0, total=0, message=message, error=message
            )
        )


def ranking_is_assessed(entries: list[ScreeningEntry]) -> bool:
    """Whether ANY pair in this table has enough runs to be ordered at all.

    THE TABLE'S ABSENT STATE HAS TO BE VISIBLE. With one run per ligand every
    pair is `NOT_ASSESSED`, so every dominance rank is 1 -- three ligands with
    clearly different scores all render "1", which is correct and looks exactly
    like a broken rank column. This is what lets the dialog say why instead.

    Computed over pairs rather than from a count, because the gate is
    `2/comb(n_a+n_b, n_a)` and unequal counts behave non-obviously: 2 runs
    against 8 clears 0.05 while 2 against 5 does not, so "does any ligand have
    4" is the wrong question.
    """
    spreads = [entry.spread for entry in entries]
    spreads = [spread for spread in spreads if spread is not None]
    return any(
        separation_p_value(a.n, b.n) <= SEPARATION_ALPHA
        for index, a in enumerate(spreads)
        for b in spreads[index + 1 :]
    )


def dominance_ranks(entries: list[ScreeningEntry]) -> list[int | None]:
    """A rank per entry: 1 + however many entries are separated below it.

    NOT A TIE-GROUPING OVER OVERLAPPING PAIRS, which was this design's first
    answer and destroys real findings. "Not separated" is not an equivalence
    relation -- with A = [-9.0, -8.5], B = [-8.6, -7.0], C = [-7.2, -6.0], A
    overlaps B and B overlaps C while A and C are DISJOINT. Grouping by overlap
    renders 1, 1, 1 and loses a genuine separation; the dominance rank renders
    1, 1, 2.

    `None` for a ligand that produced no score, because numbering a failure
    puts it in an ordering it is not part of -- which the dialog already did
    for the sorted position and must keep doing here.

    The arithmetic itself is `domain/affinity_range.dominance_rank`; this only
    decides which entries are IN the ordering.
    """
    scored = [(index, entry.spread) for index, entry in enumerate(entries)]
    scored = [(index, spread) for index, spread in scored if spread is not None]
    ranks = dominance_rank([spread for _index, spread in scored])
    answer: list[int | None] = [None] * len(entries)
    for (index, _spread), value in zip(scored, ranks, strict=True):
        answer[index] = value
    return answer


def rank(entries: list[ScreeningEntry]) -> list[ScreeningEntry]:
    """Best binder first; failures last, in the order they were attempted.

    "Best" is the most NEGATIVE affinity. Sorting these ascending is the
    correct ranking and reads as backwards, which is why it is one function
    with one comment rather than a `sorted()` at each call site.
    """
    scored = [entry for entry in entries if entry.best_affinity_kcal_mol is not None]
    unscored = [entry for entry in entries if entry.best_affinity_kcal_mol is None]
    return sorted(scored, key=lambda entry: entry.best_affinity_kcal_mol) + unscored
