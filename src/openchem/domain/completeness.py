"""Whether a result covers everything it set out to check.

**A PARTIAL "NOTHING FOUND" MUST NOT READ AS A COMPLETE ONE.** A structural
alert pass that looked at nineteen of twenty feature definitions and could not
evaluate the twentieth has not shown the molecule is free of the twentieth --
it has shown nothing about it. Before this, that case was not a case at all:
one definition that raised took the whole pass with it (a nitramine and
`fg:hydrazine`, live), so the failure was loud and total, and the natural
"fix" -- skip what cannot be evaluated and carry on -- would have made it
quiet and PARTIAL, which is worse unless the result says so. A result that
lost an instance and reads as a clean bill of health is the plausible-looking
lie this project spends its time removing.

So a producer that skips something records WHAT it skipped, and a reader is
told before it reads an absence.

**IT TRAVELS IN `provenance.parameters`, NOT AS A FIELD.** The same reason
`domain.refusal_kinds` does: a new dataclass field changes the layout of every
result type that carries it, and `result_codec` refuses a layout it does not
know by design, so a field would need a version bump and a migration for each
of them. Provenance is already persisted, copied and summarised by everything
that handles a result, and `ResultSummaryView` carries it whole.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The key a partial (or explicitly complete) result writes into
#: `provenance.parameters`.
COMPLETENESS_KEY = "completeness"


@dataclass(frozen=True)
class Completeness:
    """What a producer checked and what it could not.

    `partial` is DERIVED from `skipped`, never stored, so the two cannot
    disagree: a producer cannot claim completeness while listing something it
    dropped. A complete result records `Completeness(evaluated=N)` rather than
    nothing -- "checked all N" is a claim, and the absence of a record is only
    the absence of one.
    """

    #: How many units of work were evaluated (feature instances, groups,
    #: increments -- whatever the producer counts, said in `reason`).
    evaluated: int
    #: A human-readable name for each unit that could not be, e.g.
    #: `"fg:hydrazine at atoms [1, 2]"`. Names, not counts, so a reader (and a
    #: census) can say WHICH absence to distrust.
    skipped: tuple[str, ...] = ()
    #: Why they were skipped, in a sentence. Empty for a complete result.
    reason: str = ""

    @property
    def partial(self) -> bool:
        return bool(self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {"evaluated": self.evaluated, "skipped": list(self.skipped), "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Completeness:
        return cls(
            evaluated=int(data.get("evaluated", 0)),
            skipped=tuple(str(item) for item in data.get("skipped", ())),
            reason=str(data.get("reason", "")),
        )


def completeness_parameters(completeness: Completeness) -> dict[str, Any]:
    """The `provenance.parameters` entry for `completeness`. JSON-plain."""
    return {COMPLETENESS_KEY: completeness.to_dict()}


def completeness_of(result: object) -> Completeness | None:
    """The completeness a RESULT recorded, or None if it recorded none.

    None is "no claim", which is not the same as complete; a caller deciding
    whether to warn should ask `is_partial`, and one deciding whether to
    trust an absence should ask for the record.
    """
    provenance = getattr(result, "provenance", None)
    parameters = getattr(provenance, "parameters", None)
    if not isinstance(parameters, dict):
        return None
    raw = parameters.get(COMPLETENESS_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return Completeness.from_dict(raw)
    except (TypeError, ValueError):
        return None


def is_partial(result: object) -> bool:
    """True only when a producer said it skipped something."""
    completeness = completeness_of(result)
    return completeness is not None and completeness.partial
