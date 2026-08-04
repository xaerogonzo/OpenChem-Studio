"""Candidate rules for choosing between the lookup and the calculation.

WHY THESE ARE FUNCTIONS IN A DICT and not a `SelectionStrategy` class
hierarchy: every strategy is one pure decision -- given both candidates for
one molecule, say which source wins each atom and why. There is no state to
carry and no partial behaviour to share, so a base class would add a layer
without removing one. It also matches how this codebase already handles
pluggable behaviour (`_VISUALIZATION_ADAPTERS` keyed by type,
`CALCULATOR_DEFINITIONS` as a list of data). Adding a seventh rule is one
entry in `STRATEGIES`.

SELECTION IS NOT CONFIDENCE. Each strategy returns, per atom, the source it
picked AND the expected error it believed at the time. Whether that belief
was right is measured afterwards against experiment by the scorer -- the
two must not be conflated, because a rule can pick well for bad reasons and
badly for good ones, and only the benchmark can tell them apart.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.nmr_hybrid import LOOKUP_EXPECTED_ERROR  # noqa: E402

LOOKUP = "lookup"
ORCA = "orca"


@dataclass(frozen=True)
class AtomChoice:
    """One atom's outcome under one strategy."""

    source: str
    value: float
    expected_error: float | None
    #: Set when the strategy wants the atom shown but distrusted. Advisory
    #: only -- a flag never changes which source was chosen, because
    #: disagreement says the two differ, not which one is right.
    flagged: bool = False
    reason: str = ""


@dataclass(frozen=True)
class MoleculeInput:
    """Everything a strategy may look at. Deliberately excludes the
    experimental shifts -- a rule that could see the answer would not be a
    rule, it would be the answer."""

    name: str
    lookup: dict[int, float]
    orca: dict[int, float]
    quality: dict[int, str]
    #: The calibration's residual RMS: ORCA's error averaged over the whole
    #: install, not this molecule.
    global_error: float


def _observed_orca_error(data: MoleculeInput) -> tuple[float | None, int]:
    """How far the calculation sits from the lookup on the atoms the lookup
    predicts best -- a per-molecule estimate of ORCA's accuracy, free.

    `good` atoms carry a held-out MAE near 1.1 ppm, so treating them as a
    yardstick costs little. Returns None when there are too few to mean
    anything; two atoms would produce a number, not an estimate.
    """
    shared = [i for i in data.lookup if i in data.orca and data.quality.get(i) == "good"]
    if len(shared) < 3:
        return None, len(shared)
    deltas = [data.orca[i] - data.lookup[i] for i in shared]
    return (sum(d * d for d in deltas) / len(deltas)) ** 0.5, len(shared)


def _pick(data: MoleculeInput, orca_error: float | None, note: str) -> dict[int, AtomChoice]:
    """Lowest expected error wins; unknown never beats measured."""
    out: dict[int, AtomChoice] = {}
    for index in set(data.lookup) | set(data.orca):
        lookup_error = LOOKUP_EXPECTED_ERROR.get(data.quality.get(index, ""))
        options = []
        if index in data.lookup:
            options.append((LOOKUP, data.lookup[index], lookup_error))
        if index in data.orca:
            options.append((ORCA, data.orca[index], orca_error))
        known = [o for o in options if o[2] is not None]
        source, value, error = (
            min(known, key=lambda o: o[2]) if known else options[0]
        )
        out[index] = AtomChoice(source=source, value=value, expected_error=error, reason=note)
    return out


def hard_gate(data: MoleculeInput) -> dict[int, AtomChoice] | None:
    """What ships today: refuse the whole merge when the calculation sits
    too far from trusted values. Returning None means refused."""
    from openchem.chem.nmr_hybrid import check_calibration

    trusted = {i: v for i, v in data.lookup.items() if data.quality.get(i) == "good"}
    check = check_calibration(trusted, data.orca, "C", data.global_error)
    if check is not None and not check.passed:
        return None
    return _pick(data, data.global_error, "hard_gate")


def warn_only(data: MoleculeInput) -> dict[int, AtomChoice]:
    """`hard_gate`'s statistic, downgraded from a veto to a note."""
    from openchem.chem.nmr_hybrid import check_calibration

    trusted = {i: v for i, v in data.lookup.items() if data.quality.get(i) == "good"}
    check = check_calibration(trusted, data.orca, "C", data.global_error)
    note = "warn_only" + ("" if check is None or check.passed else " (calibration warning)")
    return _pick(data, data.global_error, note)


def global_error(data: MoleculeInput) -> dict[int, AtomChoice]:
    """No gate at all; ORCA is trusted at its install-wide accuracy."""
    return _pick(data, data.global_error, "global_error")


def per_molecule_error(data: MoleculeInput) -> dict[int, AtomChoice]:
    """No gate; ORCA is trusted at the accuracy it is DEMONSTRATING on this
    molecule. A bad calculation then loses atoms on its own merits instead
    of needing a separate veto."""
    observed, n = _observed_orca_error(data)
    return _pick(data, observed if observed is not None else data.global_error,
                 f"per_molecule_error (n={n})")


def shrunk_error(data: MoleculeInput) -> dict[int, AtomChoice]:
    """As above, pulled toward the install-wide figure.

    Seven `good` atoms is a small sample, and an unluckily tight one would
    make a mediocre calculation look excellent. Shrinking by n/(n+k) with
    k=5 means a molecule needs real evidence before its own estimate
    overrides the calibration's.
    """
    observed, n = _observed_orca_error(data)
    if observed is None:
        return _pick(data, data.global_error, "shrunk_error (no estimate)")
    k = 5.0
    weight = n / (n + k)
    blended = weight * observed + (1 - weight) * data.global_error
    return _pick(data, blended, f"shrunk_error (n={n}, w={weight:.2f})")


def flagged(data: MoleculeInput) -> dict[int, AtomChoice]:
    """`per_molecule_error`, plus marking atoms where the two methods
    disagree by more than their errors can explain.

    The flag is ADVISORY. Verified by hand on quinine that it must be:
    the same rule flags C-5' (where the lookup is right) and C-2' (where
    ORCA is right and supplies the biggest single gain), so a flag that
    silently fell back to either source would be wrong half the time.
    """
    observed, n = _observed_orca_error(data)
    error = observed if observed is not None else data.global_error
    picked = _pick(data, error, f"flagged (n={n})")
    out: dict[int, AtomChoice] = {}
    for index, choice in picked.items():
        if index in data.lookup and index in data.orca:
            lookup_error = LOOKUP_EXPECTED_ERROR.get(data.quality.get(index, ""), 0.0)
            combined = (lookup_error**2 + error**2) ** 0.5
            disagreement = abs(data.orca[index] - data.lookup[index])
            if disagreement > combined:
                out[index] = AtomChoice(
                    choice.source, choice.value, choice.expected_error, True,
                    f"{choice.reason}; methods differ by {disagreement:.1f} ppm "
                    f"against {combined:.1f} explainable",
                )
                continue
        out[index] = choice
    return out


def disagreement_defers(data: MoleculeInput) -> dict[int, AtomChoice]:
    """`per_molecule_error`, but a surprise breaks toward the better
    track record.

    The case this exists for is a PER-ATOM failure, which no
    molecule-level error estimate can see: quinine's C-5' is one carbon
    where the calculation is ~11 ppm out while being fine everywhere else,
    so its molecule-wide accuracy still looks good and it wins the atom.

    When the two methods differ by more than their errors can explain, one
    of them has failed beyond its stated accuracy and the disagreement
    itself cannot say which. What CAN say is the prior: the lookup's
    `good` and `medium` bands are measured at 1.1 and 3.4 ppm and rarely
    blunder, while its `rough` band is measured at 10 ppm and blunders
    routinely. So on a surprise, back the source with the better record --
    lookup on `good`/`medium`, calculation on `rough`.

    Checked against both quinine cases before being written: it keeps the
    lookup at C-5' (medium, where the lookup is right) AND keeps ORCA at
    C-2' (rough, disagreement 18 ppm, where ORCA is right and supplies the
    biggest single gain). A rule that always deferred to the lookup would
    get the second one wrong.
    """
    observed, n = _observed_orca_error(data)
    error = observed if observed is not None else data.global_error
    picked = _pick(data, error, f"disagreement_defers (n={n})")
    out: dict[int, AtomChoice] = {}
    for index, choice in picked.items():
        both = index in data.lookup and index in data.orca
        band = data.quality.get(index, "")
        if both and choice.source == ORCA and band in ("good", "medium"):
            combined = (LOOKUP_EXPECTED_ERROR.get(band, 0.0) ** 2 + error**2) ** 0.5
            disagreement = abs(data.orca[index] - data.lookup[index])
            if disagreement > combined:
                out[index] = AtomChoice(
                    LOOKUP, data.lookup[index], LOOKUP_EXPECTED_ERROR.get(band), True,
                    f"methods differ by {disagreement:.1f} ppm against {combined:.1f} "
                    f"explainable; deferring to the better-evidenced {band} lookup",
                )
                continue
        out[index] = choice
    return out


#: Every rule the benchmark compares. `hard_gate` may return None (refused);
#: the scorer treats that as "the lookup alone", which is what a user sees.
STRATEGIES = {
    "hard_gate": hard_gate,
    "warn_only": warn_only,
    "global_error": global_error,
    "per_molecule_error": per_molecule_error,
    "shrunk_error": shrunk_error,
    "flagged": flagged,
    "disagreement_defers": disagreement_defers,
}

#: Reference points, not strategies -- the two inputs on their own. Scoring
#: them through the same code keeps the comparison honest.
BASELINES = {
    "lookup_only": lambda d: {i: AtomChoice(LOOKUP, v, None) for i, v in d.lookup.items()},
    "orca_only": lambda d: {i: AtomChoice(ORCA, v, None) for i, v in d.orca.items()},
}
