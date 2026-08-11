"""What the canvas overlay is told, and nothing about where it draws.

The 2D editor cannot draw lone pairs -- `lonePair` appears zero times in
the vendored Ketcher bundle -- so they are drawn in an overlay OpenChem
owns. This module is the chemistry half of that: it answers
"how many non-bonding pairs does each atom have", and it computes no
pixels. Placement lives in the page, which is the only thing that knows
the viewport.

**THREE STATES, AND SILENCE IS NOT ONE OF THEM.**

    2 pairs               a carbonyl oxygen      dots
    0 pairs               an ammonium nitrogen   no dots -- AND THAT IS AN ANSWER
    analysis unavailable  ferrocene, a carbene   no dots -- and a stated REASON

The middle and the last look identical on a canvas, and they are
completely different claims. A count of 0 is carried explicitly for
exactly that reason: an atom missing from `counts` means "no definite
answer for this atom", never "none".

Every refusal comes from `chem/lewis.py` unchanged rather than being
re-derived here -- metals, whose valence is undefined and whose
non-bonding electrons are frequently unpaired, and any structure carrying
an unpaired electron on a main-group atom, where a singlet carbene has a
donor pair and the triplet has two lone electrons and a drawing does not
say which.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: What the status bar says. Kept here beside the states they describe, so
#: the overlay, the status bar and the Atom Inspector cannot drift into
#: three vocabularies for one answer.
NO_PAIRS_MESSAGE = "No lone pairs."
UNAVAILABLE_PREFIX = "Lone-pair analysis unavailable: "


@dataclass(frozen=True)
class ElectronOverlay:
    """Per-atom lone-pair counts, or one reason why not.

    `counts` is keyed by MOLFILE POSITION, which is what the rest of the
    application means by an atom index. The page translates to Ketcher's
    pool ids on arrival -- they diverge the moment anything is deleted,
    and that translation is the page's job because it is the only thing
    that knows Ketcher exists.
    """

    counts: dict[int, int] = field(default_factory=dict)
    refused: bool = False
    reason: str = ""

    @property
    def any_pairs(self) -> bool:
        return any(count > 0 for count in self.counts.values())

    def status_message(self) -> str:
        """What to say out loud. Empty when there is nothing to say.

        A molecule with pairs to draw says nothing: the dots are on
        screen and a line of prose repeating them is noise. The other two
        states say something precisely because they draw nothing.
        """
        if self.refused:
            return f"{UNAVAILABLE_PREFIX}{self.reason}"
        if not self.any_pairs:
            return NO_PAIRS_MESSAGE
        return ""

    def to_payload(self) -> dict[str, Any]:
        """The JSON the page receives. Positions become strings in JSON,
        so they are written as strings here rather than discovered to be
        strings on the far side."""
        return {
            "counts": {str(index): count for index, count in sorted(self.counts.items())},
            "refused": self.refused,
            "reason": self.reason,
        }


def build(mol: Any) -> ElectronOverlay:
    """Lone-pair counts for one molecule, from `LewisAnalysis`.

    **Not from `lewis.lone_pairs` alone.** That helper answers `1` for a
    carbene, which is right for the singlet and wrong for the triplet;
    `analyse` refuses the whole molecule instead, and going through it is
    what makes this inherit that judgement rather than route around it.

    **A LEWIS SITE IS NOT REQUIRED.** `analyse` builds a site only for
    atoms that donate or accept, so an ammonium nitrogen -- which does
    neither, precisely because it has no lone pair -- has no site at all.
    Reading counts from sites alone would leave it absent, which this
    module's whole contract says means "no definite answer". The count
    comes from the arithmetic directly, guarded by the refusal above, the
    same shape `chem/atom_report.py` already uses for the same reason.
    """
    from openchem.chem.lewis import analyse, lone_pairs

    if mol is None:
        return ElectronOverlay(refused=True, reason="there is no structure to analyse")

    try:
        # `UpdatePropertyCache` explicitly rather than leaning on
        # `analyse` doing it: `lone_pairs` reads `GetTotalValence`, which
        # raises without a cache, and inheriting that from a side effect
        # of another function is the kind of dependency that breaks
        # silently the day that function is reordered.
        mol.UpdatePropertyCache(strict=False)
        result = analyse(mol)
        if result.refused:
            return ElectronOverlay(refused=True, reason=_tidy(result.reason))
        counts = {
            atom.GetIdx(): pairs
            for atom in mol.GetAtoms()
            if (pairs := lone_pairs(atom)) is not None
        }
    except Exception as exc:  # noqa: BLE001 - an unreadable structure is a normal outcome
        return ElectronOverlay(refused=True, reason=f"this structure could not be read ({exc})")

    return ElectronOverlay(counts=counts)


def _tidy(reason: str) -> str:
    """`analyse`'s reasons are paragraphs; a status bar gets one sentence.

    The first sentence, lower-cased to sit after "Lone-pair analysis
    unavailable: ". The full text stays reachable in the Atom Inspector,
    which is where somebody asking "why" is already looking -- so this
    shortens rather than replaces it.
    """
    sentence = reason.strip().split(". ")[0].strip().rstrip(".")
    if not sentence:
        return "no reason was given"
    return sentence[0].lower() + sentence[1:] if sentence[0].isupper() else sentence
