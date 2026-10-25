"""What the small support-stage marker beside a calculator says, with no Qt in it.

A calculator's stage (`calculator_support.SupportStage`) used to be readable in two
places only -- the Calculator Settings dialog and Settings > Calculators -- so
nobody scrolling the Properties list or reading a result could tell how far to
trust it. The marker is the at-a-glance answer, and this module is its whole
meaning; `ui/widgets/stage_marker.py` only draws it.

**ONE SHAPE, THREE FILLS.** A star filled all the way is STABLE, filled halfway is
LIMITED, an outline is EXPERIMENTAL. One symbol to learn, read like a rating.

**A CALCULATOR NOBODY CLASSIFIED GETS NO MARKER, AND THAT IS NOT A SLIP.**
`LEGACY_UNCLASSIFIED` calculators are *treated as* STABLE so nothing changed under
anybody, but nobody has earned that, and a star on them would claim a validation
this project has not made. Absence therefore means "no declared stage", and a star
means a stage somebody declared and reviewed. Measured 2026-10-23: 66 of 73
built-in calculators are unclassified, so the marker is rare, which is what keeps it
quiet.

**THE STAGE SPEAKS FOR THIS APPLICATION'S IMPLEMENTATION, NEVER FOR THE PUBLISHED
METHOD** (`calculator_support`), and the words here keep to that.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openchem.domain.calculator_support import SupportStage, is_classified, support_of


class Fill(str, Enum):
    """How much of the marker's star is filled."""

    FULL = "full"
    HALF = "half"
    EMPTY = "empty"


#: The stage as a person reads it. `SupportStage` values are ids, not display text.
STAGE_LABELS: dict[SupportStage, str] = {
    SupportStage.EXPERIMENTAL: "Experimental",
    SupportStage.LIMITED: "Limited",
    SupportStage.STABLE: "Stable",
}

#: How much of the star each stage fills: all, half, none.
STAGE_FILLS: dict[SupportStage, Fill] = {
    SupportStage.EXPERIMENTAL: Fill.EMPTY,
    SupportStage.LIMITED: Fill.HALF,
    SupportStage.STABLE: Fill.FULL,
}

#: What each stage means, in one sentence, about THIS APPLICATION'S implementation.
STAGE_MEANINGS: dict[SupportStage, str] = {
    SupportStage.EXPERIMENTAL: (
        "this implementation is not yet validated for everyday use; treat the numbers as "
        "exploratory"
    ),
    SupportStage.LIMITED: (
        "validated inside a stated scope that leaves out much of what people draw; outside "
        "it the calculator says so rather than guessing"
    ),
    SupportStage.STABLE: "validated for the scope it declares, and offered to everyone inside it",
}


@dataclass(frozen=True)
class SupportMarker:
    """The marker for one classified calculator."""

    calculator_id: str
    stage: SupportStage
    #: Why it is not STABLE, or why it is hidden by default; empty for a plain STABLE one.
    reason: str = ""
    #: The chemical coverage in a phrase ("C/H/N/O explosives").
    scope_note: str = ""

    @property
    def label(self) -> str:
        return STAGE_LABELS[self.stage]

    @property
    def fill(self) -> Fill:
        return STAGE_FILLS[self.stage]

    @property
    def tooltip(self) -> str:
        """The sentence that is appended to the shared contract for THIS calculator."""
        text = f"This calculator: {self.label} -- {STAGE_MEANINGS[self.stage]}."
        if self.reason.strip():
            text += f"\n\nWhy: {self.reason.strip()}"
        if self.scope_note.strip():
            text += f"\n\nCovers: {self.scope_note.strip()}."
        return text


def marker_for(definition) -> SupportMarker | None:
    """The marker for `definition`, or None when nobody classified it.

    None for a plugin's calculator, a test double and every `LEGACY_UNCLASSIFIED`
    built-in alike: see the module docstring for why a neutral default is not a star.
    """
    if definition is None or not is_classified(definition):
        return None
    support = support_of(definition)
    return SupportMarker(
        calculator_id=str(getattr(definition, "calculator_id", "")),
        stage=support.stage,
        reason=support.support_reason,
        scope_note=support.scope_note,
    )
