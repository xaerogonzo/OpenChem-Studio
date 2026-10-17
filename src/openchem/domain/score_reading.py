"""The user-defined scores of the selected molecule, as the assistant may read them (`docs/DERIVED_SCORES_DESIGN.md` section 9, slice 4).

**A SCORE IS NOT STORED, SO `read_results` CANNOT SEE ONE; THIS IS ITS READ.** It evaluates the project's score definitions against the turn's frozen results, the same
`ScoreValue` the Results reader and the project table are built from (`score_value.evaluate_score`), so the model is told exactly what a person looking at Results is.

**BOTH HALVES ARE FROZEN AT SEND.** The turn holds the molecule's classified results (`turn_snapshot.TurnContext.entries`) and, since this slice, the project's score
definitions (`TurnContext.scores`): a person who edits a formula or finishes a calculation while the reply is streaming does not change the evidence behind its first sentence.

**THE MODEL CAN READ A SCORE AND CANNOT WRITE ONE.** A formula authored by a model is an agent-authored predictor, which is a decision for its own review (design record section 9),
so there is no tool that creates, edits or deletes a definition, and this module has none. A model may suggest formula text in conversation, for a person to enter in the
Derived Scores window.

**NOTHING IS GUESSED.** A score with an input nobody calculated, that was calculated for an earlier structure, that a calculator declined or whose unit is not the approved one has no
value, and says which input and why; it is never a zero. A name that matches no score is reported as not found, never matched loosely.

Pure: no Qt, no chemistry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from openchem.domain.score_value import ScoreValue, evaluate_score
from openchem.domain.turn_snapshot import TurnContext

#: The most scores one read returns, whatever the project holds (`score_definition_store.MAX_DEFINITIONS` is 100): a reply is read in full on every later request.
DEFAULT_READ_LIMIT = 40


@dataclass(frozen=True)
class ScoresView:
    """What `read_scores` hands back: the scores asked for, evaluated against the turn, and the names that matched none."""

    turn_id: str
    molecule_uuid: str
    values: tuple[ScoreValue, ...]
    #: Requested names (ids or labels) that no score of the project has.
    not_found: tuple[str, ...] = ()
    #: How many matching scores were left out to respect the limit.
    truncated: int = 0
    #: How many scores the project had when the turn began, matched or not.
    defined: int = 0


def _names(value_id: str, label: str) -> set[str]:
    """Every spelling a request may use for one score: its id, its label, and the label as it is shown (`<label> (user-defined, unvalidated)`)."""
    return {value_id.casefold(), label.casefold(), f"{label} (user-defined, unvalidated)".casefold()}


def read_scores(turn: TurnContext, names: Iterable[str] | None = None, *, limit: int = DEFAULT_READ_LIMIT) -> ScoresView:
    """The turn's scores for its molecule, optionally only those named (by id or by label; case does not matter).

    With no `names` every score is read, in the order they were defined. A name matching none is `not_found`. The molecule is the turn's: a request cannot name another.
    """
    definitions = turn.scores
    wanted = [str(name).strip() for name in names] if names is not None else None
    if wanted is None:
        chosen = list(definitions)
        missing: list[str] = []
    else:
        wanted = list(dict.fromkeys(name for name in wanted if name))
        chosen, missing = [], []
        for name in wanted:
            matched = [d for d in definitions if name.casefold() in _names(d.score_id, d.label)]
            if not matched:
                missing.append(name)
            chosen.extend(d for d in matched if d not in chosen)
    limit = max(0, limit)
    shown = chosen[:limit]
    return ScoresView(
        turn_id=turn.turn_id,
        molecule_uuid=turn.molecule_uuid,
        values=tuple(evaluate_score(definition, turn.entries, turn.conformer_count) for definition in shown),
        not_found=tuple(missing),
        truncated=max(0, len(chosen) - limit),
        defined=len(definitions),
    )
