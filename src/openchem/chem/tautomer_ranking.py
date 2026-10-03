"""RDKit's own tautomer preference score, and how it is compared with ORCA.

**THIS IS A HEURISTIC, NOT AN ENERGY AND NOT A PROBABILITY.** RDKit's
`TautomerEnumerator.ScoreTautomer` is a sum of empirical substructure rules
(aromatic rings, conjugated C=O, nitrogen placement, and so on) that
`Canonicalize` already uses, silently, to pick the "(canonical)" tautomer. It
is implementation-defined: a later release may score the same molecule
differently, so every result that shows it records the RDKit version.

Nothing here is a validated quantity, so nothing here may ever feed a
population or the validation gate (`chem.tautomer_distribution`), and nothing
here is shown as a percentage or a bar. It is an instant ordering for when
ORCA has not been run, and an informational cross-check when it has.
"""

from __future__ import annotations

from collections.abc import Sequence

import rdkit
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

#: Energies closer than this are not distinguished by the heuristic-vs-ORCA
#: cross-check. A comparison RESOLUTION for a qualitative statement, not a
#: claim that two such states are physically degenerate. 0.5 kcal/mol is chosen
#: with Fogarasi 2010's benchmark-accuracy goal for tautomer energies as
#: context (J. Mol. Struct. 978, 257); that goal is a methodology target, not a
#: scientifically established threshold for two independently calculated
#: energies being "the same". Frozen before any test was accepted, and not
#: tuned against a run.
ORCA_COMPARISON_TOLERANCE_KCAL = 0.5

#: The RDKit release that produced a score; recorded with every ranking
#: because the score is implementation-defined.
RDKIT_VERSION = rdkit.__version__

#: The four values of the heuristic-vs-ORCA verdict.
#: Both sides are clear and RDKit's top tautomer is ORCA's lowest.
AGREES = "agrees"
#: Both sides are clear and they pick different tautomers.
DIFFERS = "differs"
#: RDKit's scores tie at the top, or ORCA's lowest energies are within the
#: comparison tolerance: the comparison does not distinguish them.
TIED = "tied"
#: Not compared: the ORCA result is incomplete, or a score is missing.
INDETERMINATE = "indeterminate"


def score_tautomer(mol: Chem.Mol) -> int:
    """RDKit's raw preference score (higher = preferred), exactly as returned
    -- never rounded; only display code formats it."""
    return rdMolStandardize.TautomerEnumerator.ScoreTautomer(mol)


def competition_ranks(scores: Sequence[float]) -> list[int]:
    """1224-style ranks, best (highest score) first: scores 10, 10, 5 -> 1, 1,
    3. A tie must never read as a real preference, which an ordinal 1, 2, 3
    would make it."""
    return [1 + sum(1 for other in scores if other > score) for score in scores]


def tied_flags(scores: Sequence[float]) -> list[bool]:
    """True where this score is shared by at least one other tautomer. Derived
    from the raw score, not from the rank, so it survives a change in rank
    semantics."""
    return [sum(1 for other in scores if other == score) > 1 for score in scores]


def cross_check(
    rdkit_scores: dict[str, float | None],
    orca_energy_kcal: dict[str, float],
    orca_complete: bool,
) -> dict:
    """Does RDKit's most-preferred tautomer match ORCA's lowest-energy one?

    Both dicts are keyed by TAUTOMER (never by stereo job): the caller
    aggregates each tautomer to its lowest successful energy first, so a
    tautomer with several stereo jobs is compared once.

    **`agrees` / `differs` are claimed only for a COMPLETE ORCA result** -- an
    incomplete one has no trustworthy ranking to compare against -- and only
    when neither side is tied. The underlying facts are returned separately
    (`rdkit_tie`, `orca_tie`, `orca_incomplete`) so diagnostic detail is not
    thrown away by the single verdict.
    """
    scored = {key: score for key, score in rdkit_scores.items() if score is not None}
    out = {
        "verdict": INDETERMINATE,
        "rdkit_tie": False,
        "orca_tie": False,
        "orca_incomplete": not orca_complete,
        "tolerance_kcal": ORCA_COMPARISON_TOLERANCE_KCAL,
    }
    if not orca_complete or not orca_energy_kcal or len(scored) != len(rdkit_scores):
        return out

    top_score = max(scored.values())
    rdkit_top = sorted(key for key, score in scored.items() if score == top_score)
    lowest = min(orca_energy_kcal.values())
    orca_top = sorted(
        key for key, energy in orca_energy_kcal.items() if energy - lowest <= ORCA_COMPARISON_TOLERANCE_KCAL
    )
    out["rdkit_tie"] = len(rdkit_top) > 1
    out["orca_tie"] = len(orca_top) > 1
    if out["rdkit_tie"] or out["orca_tie"]:
        out["verdict"] = TIED
    elif rdkit_top == orca_top:
        out["verdict"] = AGREES
    else:
        out["verdict"] = DIFFERS
    return out
