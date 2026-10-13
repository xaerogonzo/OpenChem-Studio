"""What a window says about a recipe run: one row per job, one choice per ambiguity, one sentence for the whole.

The view model of `docs/RECIPES_DESIGN.md` section 8 (Stage A): the run has been evaluated over stored runs, and what
is left is to tell a person, job by job, what supplied it and what would. Pure: no Qt, no RDKit, no ORCA. A window
renders these and decides nothing; every sentence a gap is explained by is the binder's own, carried on the run, so a
window cannot say something the evaluation did not.

**A JOB IS A ROW BECAUSE A PERSON RUNS THEM ONE AT A TIME.** Nothing here starts ORCA, and a row for a job that is
still to be done carries what that job would take (`Requirement`, the vocabulary the assistant's service preview
already uses: what it needs, whether it is there NOW, and what to do when it is not) and where to run it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from openchem.domain.calculation_bridge import Requirement
from openchem.domain.lewis import EVIDENCE_CALC_TYPES
from openchem.domain.lewis_binder import where
from openchem.domain.recipe import MOLECULE_INPUT, Origin, Recipe, StepKind
from openchem.domain.recipe_run import BindingState, RecipeRun, RecipeRunStatus, StepState

#: The calculation types a job is, in a sentence.
_CALC_NAMES = {"sp": "single point", "delta_scf": "delta-SCF job"}
#: What each job gives, in a sentence.
_GIVES = {"sp": "HOMO and LUMO energies", "delta_scf": "hardness"}


@dataclass(frozen=True)
class JobRow:
    """One of the jobs the plan would need, and where it stands."""

    step_id: str
    #: "Single point on CO: HOMO and LUMO energies".
    title: str
    #: `COMPLETED` (a stored run supplied it) or `BLOCKED` (nothing did).
    state: StepState
    #: What supplied it, or the gap in the binder's words.
    note: str
    #: The slot the job is on ("first" or "second"), the molecule in it, and the calculation type to run.
    slot: str
    molecule_uuid: str
    calc_type: str
    #: What the job would run with, for a job still to be done; "" when a stored run supplied it.
    would_run_with: str = ""
    #: What the job needs and whether it is there now. Empty for a job a stored run supplied.
    requirements: tuple[Requirement, ...] = ()

    @property
    def to_do(self) -> bool:
        return self.state is not StepState.COMPLETED

    @property
    def ready_to_run(self) -> bool:
        """Every requirement is met on this machine right now."""
        return all(r.ok for r in self.requirements)


@dataclass(frozen=True)
class PickChoice:
    """A place where several runs could be meant and nothing says which: the person chooses one, by run id."""

    slot: str
    molecule_name: str
    calc_type: str
    #: "Delta-SCF jobs of CO", for the label of the chooser.
    what: str
    #: Run ids, newest first.
    candidates: tuple[str, ...]
    #: Why the choice is needed, in the binder's words.
    reason: str


#: How many characters of a run id a person is shown. The full id stays in the record and in the evidence facts.
SHORT_ID_LENGTH = 8


def short_id(run_id: str) -> str:
    """The first characters of a run id, which is what a person reads and compares. Never used to LOOK a run up."""
    return run_id[:SHORT_ID_LENGTH]


def short_ids(run_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Short forms of `run_ids`, falling back to the whole id for any two that would collide."""
    shorts = [short_id(r) for r in run_ids]
    return tuple(s if shorts.count(s) == 1 else full for s, full in zip(shorts, run_ids))


def shorten_ids_in(text: str, run_ids: tuple[str, ...]) -> str:
    """`text` with each of `run_ids` that it names replaced by its short form. The record keeps the sentence as the
    binder wrote it, with the full ids; this is only what a person is shown."""
    for full, short in zip(run_ids, short_ids(run_ids)):
        text = text.replace(full, short)
    return text


def _sentence(text: str) -> str:
    """`text` with its first letter capitalised and nothing else changed (`str.capitalize` lowers "SCF")."""
    return text[:1].upper() + text[1:]


def _need(what: str, ok: bool, how_to_fix: str) -> Requirement:
    """A requirement that is met carries no hint (see `Requirement`): the hint is only for what is missing."""
    return Requirement(what, ok, "" if ok else how_to_fix)


def _slot_of(step) -> str:
    """The slot a job works on, read from the plan: the source of its `molecule` binding."""
    for binding in step.bindings:
        if binding.target == MOLECULE_INPUT and binding.source.origin is Origin.SLOT:
            return binding.source.name
    raise ValueError(f"step {step.step_id!r} has no molecule slot")


def job_rows(
    run: RecipeRun,
    recipe: Recipe,
    *,
    names: Mapping[str, str],
    formal_charges: Mapping[str, int],
    conformer_counts: Mapping[str, int],
    orca_configured: bool,
) -> tuple[JobRow, ...]:
    """One row per job of the plan, in the plan's order.

    `names`, `formal_charges` and `conformer_counts` are by molecule uuid; the host reads them from the project, and
    nothing here looks anything up. `orca_configured` is whether the executable is set NOW.
    """
    inputs = {i.slot: i for i in run.inputs}
    records = {s.step_id: s for s in run.steps}
    parameters = dict(run.parameters)
    level = where(parameters.get("method_basis", ""), parameters.get("solvent", ""))
    rows: list[JobRow] = []
    for step in recipe.steps:
        if step.kind is not StepKind.SERVICE:
            continue
        slot = _slot_of(step)
        uuid = inputs[slot].molecule_uuid
        name = names.get(uuid) or slot
        record = records[step.step_id]
        done = record.state is StepState.COMPLETED
        targets = {f"{slot}_{kind}" for kind, calc in EVIDENCE_CALC_TYPES.items() if calc == step.action}
        mentioned = tuple(sorted({c for b in run.bindings if b.target in targets for c in b.candidates}))
        note = shorten_ids_in(record.reason, mentioned)
        if done:
            # The record keeps the full run ids; a person is shown the short forms of the runs behind THIS job's numbers.
            ids = tuple(sorted({b.evidence.run_id for b in run.bindings if b.target in targets and b.evidence}))
            if ids:
                note = "from stored run " + ", ".join(short_ids(ids))
        title = f"{_sentence(_CALC_NAMES[step.action])} on {name}: {_GIVES[step.action]}"
        requirements: tuple[Requirement, ...] = ()
        would_run_with = ""
        if not done:
            would_run_with = (
                f"{level}, charge {formal_charges.get(uuid, 0):+d}; "
                "the multiplicity is the usual one for the molecule unless you set another"
            )
            requirements = (
                _need(
                    f"a 3D conformer for {name}", conformer_counts.get(uuid, 0) > 0,
                    "generate conformers first, from the Conformers tools",
                ),
                _need("the ORCA executable", orca_configured, "set its path in Tools > External Tools"),
            )
        rows.append(JobRow(
            step_id=step.step_id, title=title, state=record.state, note=note, slot=slot,
            molecule_uuid=uuid, calc_type=step.action, would_run_with=would_run_with, requirements=requirements,
        ))
    return tuple(rows)


def pick_choices(run: RecipeRun, *, names: Mapping[str, str]) -> tuple[PickChoice, ...]:
    """Every ambiguity in `run` that choosing a run id would settle.

    One choice per molecule and calculation type: the HOMO and the LUMO come from the same single point, so one
    choice serves both and listing them twice would ask the same question twice.
    """
    inputs = {i.slot: i for i in run.inputs}
    seen: set[tuple[str, str]] = set()
    choices: list[PickChoice] = []
    for record in run.bindings:
        if record.state is not BindingState.AMBIGUOUS or not record.candidates:
            continue
        slot, kind = record.target.split("_", 1)
        calc = EVIDENCE_CALC_TYPES[kind]
        if (slot, calc) in seen:
            continue
        seen.add((slot, calc))
        name = names.get(inputs[slot].molecule_uuid) or slot
        choices.append(PickChoice(
            slot=slot, molecule_name=name, calc_type=calc,
            what=f"{_sentence(_CALC_NAMES[calc])}s of {name}", candidates=record.candidates,
            reason=shorten_ids_in(record.reason, record.candidates),
        ))
    return tuple(choices)


def headline(run: RecipeRun) -> str:
    """The whole run in one sentence, and never a sentence that makes a partial answer sound complete."""
    if run.status is RecipeRunStatus.COMPLETED:
        return "Complete. Every job is satisfied by a stored run, and every number the lines use came from one."
    if run.status is RecipeRunStatus.PARTIAL:
        if run.result is None:
            return "Partial. Some jobs are satisfied, but no line of evidence could be evaluated yet."
        return (
            "Partial. The lines the stored runs support are below, and each gap says what would supply "
            "the rest. This is not a complete answer."
        )
    if run.status is RecipeRunStatus.BLOCKED:
        return "Blocked. Nothing could be evaluated: the stored runs supply none of what a line needs."
    if run.status is RecipeRunStatus.FAILED:
        return "Failed. A step broke; the row for it says why."
    return run.status.value.capitalize() + "."
