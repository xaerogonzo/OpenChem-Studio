"""One evaluation of a recipe, and everything needed to read its answer later.

The record half of `docs/RECIPES_DESIGN.md` (sections 3, 6 and 7), following `quantum_chemistry_run.py` point for
point. Pure: no Qt, no RDKit, no ORCA.

**A SEPARATE, DURABLE COLLECTION -- NOT A RESULT IN `SessionResultStore`, AND NOT A COPY OF ONE.** That store keeps
one result per molecule, per calculator, per input fingerprint, and drops a result whose fingerprint no longer
matches the molecule when a project is saved. A recipe's answer involves two molecules, and the moment a person most
needs to read it is the one the store would delete it in: "stale, because the structure was edited". So a run lives
here, retained unconditionally, in a block of its own in the project file with an envelope version of its own. It is
never also in the result store, so there is no second copy to disagree with the first.

**THE EVIDENCE IS COPIED IN.** A run keeps, for each number it consumed, the value, its unit, and which
quantum-chemistry run, method, basis, charge, multiplicity, solvent and input it came from. The numbers stay readable
after the run they came from is deleted, which is also what lets `assess` say "that run is gone" without losing the
answer.

**STALENESS IS DERIVED WHEN IT IS READ, NEVER STORED.** A stored flag rots; a comparison of what the run recorded
with the project as it is now cannot. `assess` does that comparison from a `ProjectView` the host builds, because
whether two structures are the same molecule needs the chemistry layer and this module has none. A newer compatible
run is NOT staleness: it is an offer, made elsewhere, and the recorded answer is left as it was recorded.

**A RUN WITH GAPS IS NEVER COMPLETED.** `RecipeRun` refuses to be built `COMPLETED` while any step is unfinished or
any binding is not `BOUND`; the partial status exists for exactly that, and `classify` is the one function that
decides it.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid as uuid_module
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from openchem.domain import result_codec

logger = logging.getLogger("openchem.recipe_run")

#: The on-disk block's own layout version, independent of every other collection's. A newer block is ignored with
#: a warning, as a newer quantum-chemistry run block is.
ENVELOPE_VERSION = 1


def new_run_id() -> str:
    return uuid_module.uuid4().hex


class BindingState(str, enum.Enum):
    """How one binding ended. Eight states, and the reason is always kept beside the state."""

    #: A value of the declared type was found and passed every compatibility rule.
    BOUND = "bound"
    #: Nothing in the project matches. Not zero and not unknown: absent.
    MISSING = "missing"
    #: The producer declined (a limit, a missing input). Its kind and text are kept.
    REFUSED = "refused"
    #: The producer broke.
    FAILED = "failed"
    #: The evidence describes a structure the molecule no longer has.
    STALE = "stale"
    #: The record lacks what a comparison needs (no fingerprint, no molblock). Never called fresh.
    UNVERIFIABLE = "unverifiable"
    #: Values exist but may not be combined: a different method, solvent or descriptor family. The rule is named.
    INCOMPATIBLE = "incompatible"
    #: More than one record could be meant and nothing says which. The candidates are named.
    AMBIGUOUS = "ambiguous"

    def blocks(self, optional: bool) -> bool:
        """Whether a step that reads this binding cannot run.

        **OPTIONAL RELAXES EVERY STATE, BECAUSE THE VALUE PASSED ON IS `None` IN EACH.** The Lewis lines are
        independent evidence and `predict` already means "not available" by `None`; a stale or incompatible number is
        never handed over in place of it, and the state is still recorded, so a present-but-wrong binding is never
        reported as an absent one. A required binding blocks in every state but `BOUND`.
        """
        return self is not BindingState.BOUND and not optional


class StepState(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    REFUSED = "refused"
    FAILED = "failed"
    #: Not needed for this evaluation; not a gap.
    SKIPPED = "skipped"


#: Step states that mean the step is done and the answer from it exists, or never needed to.
_FINISHED = frozenset({StepState.COMPLETED, StepState.SKIPPED})


class RecipeRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    #: Something was computed and something was not. Shown as partial, never as complete with the gaps hidden.
    PARTIAL = "partial"
    #: Nothing could be computed; the gaps say why.
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def persisted_states(cls) -> frozenset["RecipeRunStatus"]:
        """A project file never records RUNNING: nothing could reconnect to what was in flight when it closed."""
        return frozenset({cls.COMPLETED, cls.PARTIAL, cls.BLOCKED, cls.FAILED, cls.CANCELLED})


@dataclass(frozen=True)
class SlotInput:
    """What a slot held when the run was made."""

    slot: str
    molecule_uuid: str
    #: The molecule's constitution at the time, as the host computes it (see `ProjectView`). "" when it could not be.
    constitution_key: str
    #: The DRAWING input fingerprint at the time.
    drawing_fingerprint: str = ""


@dataclass(frozen=True)
class Evidence:
    """One number a run consumed, copied from the quantum-chemistry run it came from."""

    molecule_uuid: str
    #: The `QuantumChemistryRun` it came from. Compared with the project by `assess`.
    run_id: str
    descriptor_id: str
    value: float
    unit: str
    calc_type: str
    method_basis: str
    charge: int
    multiplicity: int
    input_fingerprint: str
    solvent: str = ""


@dataclass(frozen=True)
class BindingRecord:
    step_id: str
    #: The step input this was for.
    target: str
    state: BindingState
    #: In words, for any state but `BOUND`: what is wrong and what would fix it.
    reason: str = ""
    evidence: Evidence | None = None
    #: For `AMBIGUOUS` (and for a gap that names runs): the run ids that could be meant. For `BOUND`: the repeats of
    #: the same job that were considered and NOT used, so the one that was used is not the only one a reader can see.
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepRecord:
    step_id: str
    state: StepState
    reason: str = ""
    #: A `RefusalKind` value, for a refused step; "" otherwise.
    refusal_kind: str = ""


def has_gaps(steps: tuple[StepRecord, ...], bindings: tuple[BindingRecord, ...]) -> bool:
    return any(s.state not in _FINISHED for s in steps) or any(b.state is not BindingState.BOUND for b in bindings)


def classify(steps: tuple[StepRecord, ...], bindings: tuple[BindingRecord, ...]) -> RecipeRunStatus:
    """The status a finished evaluation has. The one place it is decided.

    Nothing finished: `FAILED` if a step broke, else `BLOCKED`. Something finished: `COMPLETED` only with no gap
    at all, else `PARTIAL`.
    """
    finished = any(s.state is StepState.COMPLETED for s in steps)
    if not finished:
        return RecipeRunStatus.FAILED if any(s.state is StepState.FAILED for s in steps) else RecipeRunStatus.BLOCKED
    return RecipeRunStatus.PARTIAL if has_gaps(steps, bindings) else RecipeRunStatus.COMPLETED


@dataclass(frozen=True)
class RecipeRun:
    """One evaluation of one recipe version, immutable: a rerun is a new run, never a change to this one."""

    run_id: str
    recipe_id: str
    recipe_version: str
    status: RecipeRunStatus
    inputs: tuple[SlotInput, ...] = ()
    #: The recipe parameters chosen, as (name, code) pairs.
    parameters: tuple[tuple[str, str], ...] = ()
    steps: tuple[StepRecord, ...] = ()
    bindings: tuple[BindingRecord, ...] = ()
    #: The answer: a report from `domain.report`, encoded with `result_codec`. None when nothing was computed.
    result: Any = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.status is RecipeRunStatus.COMPLETED and has_gaps(self.steps, self.bindings):
            raise ValueError("a run with an unfinished step or a binding that is not BOUND is partial, not completed")
        if self.status is RecipeRunStatus.PARTIAL and not any(s.state is StepState.COMPLETED for s in self.steps):
            raise ValueError("a run with no finished step is blocked or failed, not partial")

    def is_terminal(self) -> bool:
        return self.status in RecipeRunStatus.persisted_states()

    def molecule_uuids(self) -> tuple[str, ...]:
        return tuple(i.molecule_uuid for i in self.inputs)

    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(b.evidence for b in self.bindings if b.evidence is not None)

    # --- the file ----------------------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "recipe_id": self.recipe_id,
            "recipe_version": self.recipe_version,
            "status": self.status.value,
            "created_at": self.created_at,
            "inputs": [
                {"slot": i.slot, "molecule_uuid": i.molecule_uuid, "constitution_key": i.constitution_key,
                 "drawing_fingerprint": i.drawing_fingerprint}
                for i in self.inputs
            ],
            "parameters": {name: value for name, value in self.parameters},
            "steps": [
                {"step_id": s.step_id, "state": s.state.value, "reason": s.reason, "refusal_kind": s.refusal_kind}
                for s in self.steps
            ],
            "bindings": [
                {"step_id": b.step_id, "target": b.target, "state": b.state.value, "reason": b.reason,
                 "candidates": list(b.candidates), "evidence": _evidence_to_dict(b.evidence)}
                for b in self.bindings
            ],
            "result": None if self.result is None else result_codec.encode(self.result),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecipeRun | None":
        """`None` on anything unreadable -- one damaged run must not break loading every other run, the contract
        `QuantumChemistryRun.from_dict` keeps. The reason is logged, and `RecipeRunStore.from_dict` reports it."""
        try:
            status = RecipeRunStatus(data["status"])
            if status not in RecipeRunStatus.persisted_states():
                logger.warning("Dropping a recipe run saved with a non-terminal status %r", data.get("status"))
                return None
            raw_result = data.get("result")
            return cls(
                run_id=str(data["run_id"]),
                recipe_id=str(data["recipe_id"]),
                recipe_version=str(data["recipe_version"]),
                status=status,
                created_at=float(data.get("created_at", 0.0)),
                inputs=tuple(
                    SlotInput(str(i["slot"]), str(i["molecule_uuid"]), str(i.get("constitution_key", "")),
                              str(i.get("drawing_fingerprint", "")))
                    for i in data.get("inputs") or []
                ),
                parameters=tuple((str(k), str(v)) for k, v in (data.get("parameters") or {}).items()),
                steps=tuple(
                    StepRecord(str(s["step_id"]), StepState(s["state"]), str(s.get("reason", "")),
                               str(s.get("refusal_kind", "")))
                    for s in data.get("steps") or []
                ),
                bindings=tuple(
                    BindingRecord(
                        str(b["step_id"]), str(b["target"]), BindingState(b["state"]), str(b.get("reason", "")),
                        _evidence_from_dict(b.get("evidence")), tuple(str(c) for c in b.get("candidates") or []),
                    )
                    for b in data.get("bindings") or []
                ),
                result=None if raw_result is None else result_codec.decode(raw_result),
            )
        except (KeyError, TypeError, ValueError, AttributeError, result_codec.CodecError) as exc:
            logger.warning("Unreadable saved recipe run: %s", exc)
            return None


def _evidence_to_dict(evidence: Evidence | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    return {
        "molecule_uuid": evidence.molecule_uuid, "run_id": evidence.run_id, "descriptor_id": evidence.descriptor_id,
        "value": evidence.value, "unit": evidence.unit, "calc_type": evidence.calc_type,
        "method_basis": evidence.method_basis, "charge": evidence.charge, "multiplicity": evidence.multiplicity,
        "input_fingerprint": evidence.input_fingerprint, "solvent": evidence.solvent,
    }


def _evidence_from_dict(data: dict[str, Any] | None) -> Evidence | None:
    if data is None:
        return None
    return Evidence(
        molecule_uuid=str(data["molecule_uuid"]), run_id=str(data["run_id"]),
        descriptor_id=str(data["descriptor_id"]), value=float(data["value"]), unit=str(data["unit"]),
        calc_type=str(data["calc_type"]), method_basis=str(data["method_basis"]), charge=int(data["charge"]),
        multiplicity=int(data["multiplicity"]), input_fingerprint=str(data["input_fingerprint"]),
        solvent=str(data.get("solvent", "")),
    )


@dataclass
class RecipeRunStore:
    """Every terminal recipe run in one project.

    **UNCONDITIONAL PERSISTENCE**, like `QuantumChemistryRunStore`: nothing is dropped on save because a molecule has
    changed since. That comparison is `assess`'s, made when the run is read.
    """

    project_uuid: str
    _runs: dict[str, RecipeRun] = field(default_factory=dict)
    #: What `from_dict` could not read, one sentence each: a newer block, another project's block, a damaged run.
    #: Not saved. The load path reports it, so nothing is dropped silently.
    load_problems: list[str] = field(default_factory=list)

    def record(self, run: RecipeRun) -> None:
        """Store a run. Only a TERMINAL run is kept, as for a quantum-chemistry run."""
        if not run.is_terminal():
            logger.warning("Refusing to store non-terminal recipe run %s (status=%s)", run.run_id, run.status)
            return
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RecipeRun | None:
        return self._runs.get(run_id)

    def all_runs(self) -> list[RecipeRun]:
        """Newest first."""
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def runs_for_molecule(self, molecule_uuid: str) -> list[RecipeRun]:
        """Every run in which `molecule_uuid` filled a slot, newest first."""
        return [r for r in self.all_runs() if molecule_uuid in r.molecule_uuids()]

    def runs_of(self, recipe_id: str) -> list[RecipeRun]:
        return [r for r in self.all_runs() if r.recipe_id == recipe_id]

    def delete(self, run_id: str) -> bool:
        return self._runs.pop(run_id, None) is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_version": ENVELOPE_VERSION,
            "project_uuid": self.project_uuid,
            "runs": [run.to_dict() for run in self._runs.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, project_uuid: str) -> "RecipeRunStore":
        store = cls(project_uuid)
        if not data:
            return store

        def problem(message: str) -> None:
            logger.warning(message)
            store.load_problems.append(message)

        version = data.get("envelope_version", 0)
        if not isinstance(version, int) or version > ENVELOPE_VERSION:
            problem(f"Saved recipe runs use envelope v{version}; this build reads up to v{ENVELOPE_VERSION}, so they were ignored")
            return store
        if data.get("project_uuid") not in (None, project_uuid):
            problem(f"Saved recipe runs belong to project {data.get('project_uuid')}, not {project_uuid}; ignored")
            return store
        for raw in data.get("runs") or []:
            run = RecipeRun.from_dict(raw) if isinstance(raw, dict) else None
            if run is None:
                problem("A saved recipe run could not be read and was skipped")
                continue
            store.record(run)
        return store


# --- staleness, derived at read ---------------------------------------------------------------------------


class StaleCause(str, enum.Enum):
    #: A slot's molecule is no longer the constitution the run recorded.
    STRUCTURE_EDITED = "structure_edited"
    #: A slot's molecule is no longer in the project.
    MOLECULE_REMOVED = "molecule_removed"
    #: A quantum-chemistry run the answer consumed is no longer in the project. The recorded numbers stay on
    #: screen as recorded.
    EVIDENCE_REMOVED = "evidence_removed"
    #: This build has no such recipe version. The run is shown as recorded and is never re-evaluated: a reopened
    #: project must not reinterpret an old answer with newer methods.
    RECIPE_VERSION_UNKNOWN = "recipe_version_unknown"


def _this_builds_recipe_versions() -> Mapping[str, Collection[str]]:
    """`recipe_catalogue.shipped_versions()`, imported when it is called and not when this module loads.

    The catalogue imports every recipe, a recipe's evidence types (`domain.lewis`) import this module's
    `BindingState` and `Evidence`, and so a module-level import here closes a cycle. The dependency is real and
    points the right way at call time: asking "does this build have that version" needs the catalogue.
    """
    from openchem.domain.recipe_catalogue import shipped_versions

    return shipped_versions()


@dataclass(frozen=True)
class ProjectView:
    """What `assess` needs to know about the project today. The host builds it; this module does no chemistry."""

    #: molecule uuid -> its constitution key now. `None` means the host could not compute one (the comparison is
    #: then unverifiable, not a difference). A uuid that is absent means the molecule is no longer in the project.
    constitution_keys: Mapping[str, str | None]
    #: The ids of the quantum-chemistry runs that exist now.
    qc_run_ids: Collection[str]
    #: recipe id -> the versions this build ships. **DEFAULTS TO THIS BUILD'S OWN CATALOGUE**
    #: (`recipe_catalogue.shipped_versions`), because the question it answers, "does THIS build have that version", has one
    #: right answer, and a host that had to remember to hand it in is the "somebody remembers" failure. A test
    #: passes its own.
    recipe_versions: Mapping[str, Collection[str]] = field(default_factory=_this_builds_recipe_versions)


@dataclass(frozen=True)
class Assessment:
    causes: tuple[StaleCause, ...] = ()
    #: One sentence per finding, naming the slot, molecule or run.
    details: tuple[str, ...] = ()
    #: Slots that could not be compared: the run or the host had no constitution key. Never read as "unchanged".
    unverifiable_slots: tuple[str, ...] = ()
    #: The same findings as DATA, for a reader that names molecules where `details` names slots (the Results entry,
    #: `recipe_answer.py`): the slots whose structure differs now, the slots whose molecule is gone, and the consumed
    #: quantum-chemistry runs that were deleted.
    edited_slots: tuple[str, ...] = ()
    removed_slots: tuple[str, ...] = ()
    removed_run_ids: tuple[str, ...] = ()

    @property
    def stale(self) -> bool:
        return bool(self.causes)

    @property
    def can_reevaluate(self) -> bool:
        return StaleCause.RECIPE_VERSION_UNKNOWN not in self.causes


def assess(run: RecipeRun, view: ProjectView) -> Assessment:
    """Whether `run` still describes the project, and if not, every reason.

    Causes are reported in a fixed order, and all of them: fixing one must not reveal another a rerun would trip
    on. Nothing here is stored.
    """
    causes: list[StaleCause] = []
    details: list[str] = []
    unverifiable: list[str] = []

    if run.recipe_version not in view.recipe_versions.get(run.recipe_id, ()):
        causes.append(StaleCause.RECIPE_VERSION_UNKNOWN)
        details.append(
            f"recipe {run.recipe_id!r} version {run.recipe_version!r} is not one this build has; "
            "shown as recorded and not re-evaluated"
        )

    edited: list[str] = []
    removed: list[str] = []
    removed_slots: list[str] = []
    for slot in run.inputs:
        if slot.molecule_uuid not in view.constitution_keys:
            removed.append(f"{slot.slot} (molecule {slot.molecule_uuid})")
            removed_slots.append(slot.slot)
            continue
        now = view.constitution_keys[slot.molecule_uuid]
        if not slot.constitution_key or now is None:
            unverifiable.append(slot.slot)
        elif now != slot.constitution_key:
            edited.append(slot.slot)
    if edited:
        causes.append(StaleCause.STRUCTURE_EDITED)
        details.append(f"the structure in slot {', '.join(edited)} was edited since this run")
    if removed:
        causes.append(StaleCause.MOLECULE_REMOVED)
        details.append(f"the molecule in slot {', '.join(removed)} is no longer in the project")

    gone = sorted({e.run_id for e in run.evidence() if e.run_id and e.run_id not in view.qc_run_ids})
    if gone:
        causes.append(StaleCause.EVIDENCE_REMOVED)
        details.append(f"quantum-chemistry run(s) {', '.join(gone)} behind this answer were deleted")

    return Assessment(
        tuple(causes), tuple(details), tuple(unverifiable),
        edited_slots=tuple(edited), removed_slots=tuple(removed_slots), removed_run_ids=tuple(gone),
    )
