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
from functools import lru_cache
from typing import Any

#: What the status bar says. Kept here beside the states they describe, so
#: the overlay, the status bar and the Atom Inspector cannot drift into
#: three vocabularies for one answer.
NO_PAIRS_MESSAGE = "No lone pairs."
UNAVAILABLE_PREFIX = "Lone-pair analysis unavailable: "
#: Said when the arithmetic applies to NO atom in the structure -- a bare
#: metal ion, say. Distinct from a refusal, which is about the whole
#: molecule, and distinct from zero, which is an answer.
NOTHING_DETERMINED = (
    "no atom here has a definite non-bonding count "
    "(a metal's valence is undefined, and its non-bonding electrons are "
    "frequently unpaired rather than paired)"
)


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
    #: Atoms the arithmetic does not apply to -- metals, whose valence is
    #: undefined. Carried rather than merely omitted from `counts`, so the
    #: difference between "none" and "cannot say" survives into what is
    #: said out loud.
    undetermined: tuple[int, ...] = ()

    @property
    def any_pairs(self) -> bool:
        return any(count > 0 for count in self.counts.values())

    def status_message(self) -> str:
        """What to say out loud. Empty when there is nothing to say.

        A molecule with pairs to draw says nothing: the dots are on
        screen and a line of prose repeating them is noise. Every other
        state says something precisely because it draws nothing.

        **THE UNDETERMINED CASE WAS A BUG, FOUND BY LOOKING AT IT.** An
        earlier version had three states and four situations: iron(III)
        draws no dots, is not refused, and has no atom with a definite
        count -- and the status bar cheerfully said "No lone pairs.",
        which is the one thing the analysis had declined to claim. The
        test that should have caught it asserted that message as the
        expected behaviour, so the bug was in the guard as much as in the
        code.
        """
        if self.refused:
            return f"{UNAVAILABLE_PREFIX}{self.reason}"
        if self.any_pairs:
            return ""
        if not self.counts:
            return f"{UNAVAILABLE_PREFIX}{NOTHING_DETERMINED}"
        if self.undetermined:
            return (
                f"No lone pairs on the atoms this can speak for; "
                f"{len(self.undetermined)} it cannot."
            )
        return NO_PAIRS_MESSAGE

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
        counts: dict[int, int] = {}
        undetermined: list[int] = []
        for atom in mol.GetAtoms():
            pairs = lone_pairs(atom)
            if pairs is None:
                undetermined.append(atom.GetIdx())
            else:
                counts[atom.GetIdx()] = pairs
    except Exception as exc:  # noqa: BLE001 - an unreadable structure is a normal outcome
        return ElectronOverlay(refused=True, reason=f"this structure could not be read ({exc})")

    return ElectronOverlay(counts=counts, undetermined=tuple(undetermined))


def for_molblock(molblock: str | None) -> ElectronOverlay:
    """The counts for a drawing, from its molblock.

    The entry point for the UI, which holds molblocks rather than RDKit
    molecules -- `tests/test_layering.py` forbids a `ui/` module importing
    RDKit at all, so the parse belongs on this side of the line.

    An unparseable drawing is a REFUSAL rather than an empty answer: the
    canvas would look identical either way, and "this structure could not
    be read" is a different thing to say than "no lone pairs".
    """
    if not molblock:
        return ElectronOverlay(refused=True, reason="there is no structure to analyse")
    from rdkit import Chem

    try:
        mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    except Exception:  # noqa: BLE001 - an unreadable drawing is a normal outcome
        mol = None
    if mol is None:
        return ElectronOverlay(refused=True, reason="this structure could not be read")
    return build(mol)


def _tidy(reason: str) -> str:
    """`analyse`'s reasons are paragraphs; a status bar gets one sentence.

    The first sentence, lower-cased to sit after "Lone-pair analysis
    unavailable: ". The full text stays reachable in the Atom Inspector,
    which is where somebody asking "why" is already looking -- so this
    shortens rather than replaces it.

    **AN ELEMENT SYMBOL IS NOT A SENTENCE OPENER.** Ferrocene's reason
    begins "Fe is bonded directly to carbon", which the blanket
    lower-casing turned into "fe" -- a chemistry app writing an element
    wrong, in the one message whose whole job is to name the offending
    atom. Checked against RDKit's own periodic table rather than a list
    kept here, so it cannot fall out of step with what the app perceives.
    """
    sentence = reason.strip().split(". ")[0].strip().rstrip(".")
    if not sentence:
        return "no reason was given"
    if not sentence[0].isupper():
        return sentence
    first = sentence.split(",")[0].split()[0].strip(",;:")
    if _is_element_symbol(first):
        return sentence
    return sentence[0].lower() + sentence[1:]


@lru_cache(maxsize=1)
def _element_symbols() -> frozenset[str]:
    """Every symbol RDKit knows, built once.

    **NOT `GetAtomicNumber` in a try/except**, which is the obvious way
    and writes to stderr: it raises for an unknown symbol AND prints
    `Element 'A' not found` from C++ first, so a caught exception still
    leaves a line in the log. Most reasons begin with an ordinary word,
    so that would be noise on nearly every call.
    """
    from rdkit import Chem

    table = Chem.GetPeriodicTable()
    symbols = set()
    for number in range(1, 119):
        try:
            symbols.add(table.GetElementSymbol(number))
        except Exception:  # noqa: BLE001 - past the end of this build's table
            break
    return frozenset(symbols)


def _is_element_symbol(word: str) -> bool:
    """Whether a word is an element symbol, as RDKit spells them.

    Case-SENSITIVE, so an ordinary word only collides when it is spelled
    exactly as the element -- "In" does, and stays capitalised as a
    result. That is the conservative direction: a capital where a
    lower-case would read better is a blemish, and "fe" is an error.
    """
    return word in _element_symbols()
