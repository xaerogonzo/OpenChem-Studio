"""A kept recipe answer, as the Results reader holds it (`docs/RECIPES_DESIGN.md` sections 6, 7 and 12; slice 3b).

**A PROJECTION OF THE `RecipeRun`, NEVER A SECOND COPY OF IT.** The answer is kept in `RecipeRunStore`, in a block of its
own in the project file, and the design's decision (section 6) was that it is NOT also a result in `SessionResultStore`:
that store's key is one molecule, one calculator and one fingerprint, a recipe has two molecules, and it drops a result
whose fingerprint no longer matches, which is exactly when a person needs to read "stale, because the structure was
edited". So the reader is handed these entries built from the runs at the moment it asks, the way it is handed the
descriptor aggregate, and nothing here is ever stored.

**IT SHOWS UNDER EVERY MOLECULE THAT TOOK PART**, re-stamped with the molecule being looked at: the reader drops anything
stamped with another molecule, and a pairing of BH3 with CO is as much a fact about one as the other.

**STALENESS IS DERIVED HERE, EVERY TIME, FROM `assess`.** The reader has one rule for a stale result, a structure version
that is not the current one, and a recipe answer is not about one molecule's version counter: it is stale when EITHER
molecule was edited, when one was removed, when a run it consumed was deleted. So the answer is stamped with the current
version when `assess` finds nothing, and with `STALE_STAMP` when it does, and the reader's own rule then marks it. The
cause travels with it as `stale_note`, because the reader's generic line says "an earlier version of this structure",
which is wrong for a deleted run.

A slot that could not be compared is neither current nor stale. It is said in the answer's limitations, and the entry is
not marked stale, because "could not check" is a different statement from "changed".
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from openchem.domain.lewis_binder import where
from openchem.domain.recipe_preview import short_id, short_ids
from openchem.domain.recipe_run import Assessment, RecipeRun, RecipeRunStatus, StaleCause
from openchem.domain.report import ReportResult

#: The structure version of an answer the project has moved on from. The counter starts at 0 and only rises, so no
#: real structure ever has this one, and the reader's single staleness rule (`structure_resolution.is_stale`) reads any
#: entry stamped with it as stale. It is a stamp and not a claim about a version: nothing prints it, because an answer
#: with a picture drawn on one molecule's structure would need its own decision, and the pairing declares none.
STALE_STAMP = -1

#: What a slot is called in a sentence when its molecule is no longer in the project, and so has no name to give.
GONE_MOLECULE = "a molecule that is no longer in the project"


@dataclass(frozen=True, kw_only=True)
class RecipeAnswer(ReportResult):
    """A kept recipe answer, read as a report. Every `ReportResult` rule applies to it (ordering, search, copy, export).

    Never encoded: it is built to be read and discarded, and the project file holds the `RecipeRun` it came from.
    """

    #: The kept run it describes. A pairing kept twice is two answers, told apart by this.
    run_id: str = ""
    #: Why it is stale, in words naming molecules and runs; "" when it is not. Derived, not stored.
    stale_note: str = ""


def report_id_of(run: RecipeRun) -> str:
    """The id an answer is filed under: the recipe and the run, so two kept runs never share one."""
    return f"{run.recipe_id}:{run.run_id}"


def project_answers(
    runs: Sequence[RecipeRun],
    *,
    viewing: str,
    assessments: Mapping[str, Assessment],
    names: Mapping[str, str],
    structure_version: int,
) -> tuple[RecipeAnswer, ...]:
    """The kept answers `viewing` took part in, as reader entries, newest run first.

    `assessments` is by run id and `names` by molecule uuid, both read by the host from the project as it is now.
    A run with no result has nothing to show and is left out; a run `viewing` was not part of is left out. Every
    run shown needs an assessment (a `KeyError` otherwise): an answer nobody checked must not read as current.
    """
    shown = [r for r in runs if r.result is not None and viewing in r.molecule_uuids()]
    titles = [_title(r, names) for r in shown]
    answers: list[RecipeAnswer] = []
    for run, title in zip(shown, titles):
        if titles.count(title) > 1:
            # The same pair kept twice at one level (a new geometry in between) reads as two entries with one name.
            title += f" [{short_id(run.run_id)}]"
        answers.append(
            _answer(run, title, viewing, assessments[run.run_id], names, structure_version)
        )
    return tuple(answers)


def _title(run: RecipeRun, names: Mapping[str, str]) -> str:
    parameters = dict(run.parameters)
    molecules = " + ".join(names.get(i.molecule_uuid) or GONE_MOLECULE for i in run.inputs)
    level = where(parameters.get("method_basis", ""), parameters.get("solvent", ""))
    return f"{run.result.name}: {molecules} at {level}"


def _answer(
    run: RecipeRun, title: str, viewing: str, assessment: Assessment, names: Mapping[str, str], structure_version: int
) -> RecipeAnswer:
    own = {f.name: getattr(run.result, f.name) for f in dataclasses.fields(ReportResult)}
    limitations = tuple(run.result.limitations)
    if run.status is not RecipeRunStatus.COMPLETED:
        limitations += (
            "This answer is partial: some of the evidence it needs was missing when it was evaluated, and each gap "
            "in the facts says what would supply it.",
        )
    unverifiable = _called(run, assessment.unverifiable_slots, names)
    if unverifiable:
        limitations += (
            f"Could not check whether the structure of {unverifiable} was edited since, so this answer is not known "
            "to be current.",
        )
    own.update(
        report_id=report_id_of(run),
        name=title,
        molecule_uuid=viewing,
        structure_version=STALE_STAMP if assessment.stale else structure_version,
        limitations=limitations,
    )
    return RecipeAnswer(**own, run_id=run.run_id, stale_note=_stale_note(run, assessment, names))


def _stale_note(run: RecipeRun, assessment: Assessment, names: Mapping[str, str]) -> str:
    if not assessment.stale:
        return ""
    sentences: list[str] = []
    if StaleCause.STRUCTURE_EDITED in assessment.causes:
        sentences.append(
            f"The structure of {_called(run, assessment.edited_slots, names)} was edited after this answer was made."
        )
    if StaleCause.MOLECULE_REMOVED in assessment.causes:
        many = len(assessment.removed_slots) > 1
        sentences.append(
            ("Molecules this answer was made from are" if many else "A molecule this answer was made from is")
            + " no longer in the project."
        )
    if StaleCause.EVIDENCE_REMOVED in assessment.causes:
        gone = assessment.removed_run_ids
        sentences.append(
            f"The quantum-chemistry run{'s' if len(gone) > 1 else ''} behind its numbers "
            f"({', '.join(short_ids(gone))}) {'were' if len(gone) > 1 else 'was'} deleted; the numbers shown are the "
            "ones recorded."
        )
    if StaleCause.RECIPE_VERSION_UNKNOWN in assessment.causes:
        sentences.append(
            f"This build has no version {run.recipe_version} of the recipe, so the answer is shown as recorded and "
            "is never evaluated again."
        )
    if assessment.can_reevaluate:
        sentences.append("Evaluate it again from the Tools menu to bring it up to date.")
    return " ".join(sentences)


def _called(run: RecipeRun, slots: Sequence[str], names: Mapping[str, str]) -> str:
    """The molecules in `slots`, named, joined for a sentence. "" for no slots."""
    by_slot = {i.slot: i.molecule_uuid for i in run.inputs}
    called = [names.get(by_slot.get(slot, "")) or GONE_MOLECULE for slot in slots]
    return " and ".join(called)
