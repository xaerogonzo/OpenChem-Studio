"""Whether the structure on screen is something a calculator takes: covered, covered with a stated limit, or certain to refuse.

Design: `docs/STRUCTURE_COVERAGE_DESIGN.md`.

**A CLAIM IS EITHER MADE BY THE CODE THAT REFUSES, OR NOT MADE.** `CalculatorDefinition.preflight` hands
this module's `Coverage` back (or the older plain reason string), and the hook behind it is the calculator's own
refusal function, never a second rule meant to agree with it. So when a calculator stops refusing something, its
hook stops saying so on the same commit. "No hook", "the hook raised" and "the hook had nothing to say" are all
the same answer here: `None`, and the row looks as it did before there was an indicator.

Pure and Qt-free: the panel draws `chip_label` and the tooltip sentence, and tests read them with no window.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CoverageKind(Enum):
    COVERED = "covered"
    CAVEAT = "caveat"
    REFUSES = "refuses"


@dataclass(frozen=True)
class Coverage:
    """One calculator's answer about the structure it was asked about.

    `reason` is the reader-facing sentence: why it refuses, or what the stated limit is. A COVERED answer
    carries none.
    """

    kind: CoverageKind
    reason: str = ""

    @classmethod
    def covered(cls) -> Coverage:
        return cls(CoverageKind.COVERED)

    @classmethod
    def caveat(cls, reason: str) -> Coverage:
        return cls(CoverageKind.CAVEAT, reason)

    @classmethod
    def refuses(cls, reason: str) -> Coverage:
        return cls(CoverageKind.REFUSES, reason)

    def __post_init__(self) -> None:
        # A refusal or a caveat with no sentence would be a claim with nothing to read.
        if self.kind is not CoverageKind.COVERED and not self.reason.strip():
            raise ValueError(f"a {self.kind.value} coverage needs a reason")


def as_coverage(answer: Any) -> Coverage | None:
    """What a hook returned, as a `Coverage`, or None for no claim.

    The older contract was `mol -> reason`, `""` when nothing is known to stop the calculator. It stays valid:
    a non-empty string is a refusal and an empty one is no claim. Anything else is no claim as well, not an
    error, so a hook that returns None or something odd cannot put a wrong word on a row.
    """
    if isinstance(answer, Coverage):
        return answer
    if isinstance(answer, str) and answer.strip():
        return Coverage.refuses(answer.strip())
    return None


#: What the chip beside a registry row says before any run when the structure is covered. Plain words with no
#: glyph, so the green check stays "Ready", which means a run succeeded. (A refusal is the existing "Not
#: applicable", which the panel's own table draws.)
COVERED_CHIP_LABEL = "Can run"
#: What the chip says before any run when the structure is accepted with a stated limit (the panel adds the amber triangle).
CAVEAT_CHIP_LABEL = "With limits"

#: The leading mark of a row that opens another panel, which has no chip to carry words.
SERVICE_ROW_MARKS = {
    CoverageKind.COVERED: "✓",
    CoverageKind.CAVEAT: "△",
    CoverageKind.REFUSES: "○",
}

#: The sentence every covered or limited tooltip ends with, so a reader does not take "can run" for "will work".
_WHAT_IT_DOES_NOT_SAY = (
    "That is about the drawn structure only: it does not say a tool is set up, a 3D structure exists, or that "
    "the answer will be accurate."
)


def tooltip_sentence(coverage: Coverage) -> str:
    """The sentence appended to a row's tooltip for this answer (situational text after the fixed contract)."""
    if coverage.kind is CoverageKind.REFUSES:
        return f"Not run yet, and known not to apply before running it: {coverage.reason}"
    if coverage.kind is CoverageKind.CAVEAT:
        return f"Not run yet. This structure is accepted, with a limit: {coverage.reason} {_WHAT_IT_DOES_NOT_SAY}"
    return (
        "Not run yet. This structure is inside what the method covers (the same check the calculator makes "
        f"before it refuses). {_WHAT_IT_DOES_NOT_SAY}"
    )
