"""Decision rules for the smina engine pose-ranking test, as pure functions.

`PREREGISTRATION_ENGINE.md` fixes what is counted and what each count means before any
docking is run; this module is that text as code so the runner cannot choose a rule after
seeing a number and `tests/test_engine_core.py` can hold the boundaries.

The question: if the search is run under another scoring function (smina arms), does the
top-ranked pose become correct more often than Vina's, under the same preparation and box?
Nothing here knows about smina, files or the survey runner.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

#: Same cutoff as the prep-and-box survey, restated so a later survey change cannot move
#: this frozen test.
SUCCESS_RMSD = 2.0

#: Pinned seeds in `PREREGISTRATION_ENGINE.md`.
SEEDS = (20261029, 20261030, 20261031)
#: An arm is correct for a receptor when at least this many seeds have a correct top pose.
SEEDS_REQUIRED = 2

#: Candidate arms whose PASS/HARMFUL is tested against `vina` and `smina-default`.
CANDIDATE_ARMS = frozenset({"smina-vinardo", "smina-dkoes_fast", "smina-ad4"})
REFERENCE_ARM = "vina"
CONTROL_ARM = "smina-default"

#: Net receptors needed for PASS or HARMFUL, with the significance level below.
MIN_NET = 3
#: Bonferroni over the three candidate arms.
ALPHA = 0.05 / len(CANDIDATE_ARMS)

#: G1: top-pose assignment RMSD tolerance (A). Survey rows store ``round(rmsd, 2)``.
#: Full-catalog remeasure 2026-11-04 (Vina 1.2.7, seed 20261029): max |Δ| was 0.05 on 7B6W
#: when the top-ranked pose swapped; 5KIR differed by 0.01 at the centi-Å step.
G1_DISTANCE_TOL = 0.05
#: G2: score-only agreement between Vina 1.2.7 and smina default (kcal/mol).
G2_SCORE_TOL = 0.01
#: G2 uses this many receptors from the closed 17-receptor pilot list (first N).
G2_RECEPTOR_COUNT = 5
#: G4: every arm must dock at least this many of the 47 measurable receptors.
G4_MIN_DOCKED = 44
#: G4: more than this many receptors dropped (paired) makes the verdict INCONCLUSIVE.
G4_MAX_DROPPED = 3

#: Arms that run crystal `--score_only` before gained/lost (`PREREGISTRATION_ENGINE.md` G5).
G5_ARMS = (
    "vina",
    "smina-default",
    "smina-vinardo",
    "smina-dkoes_fast",
    "smina-ad4",
)

#: Minimum favourable fraction per arm, pinned from the 17-pilot crystal scores
#: (`engine_g5_probe.py`, 2026-11-03): allow one miss on the pilot except ad4 (15/17).
#: Catalog remeasure 2026-11-04 (47 receptors) passed these pins: vina 47/47, smina
#: Vina-family 46/47 (4PE5), ad4 45/47 (4DKL and 4PE5).
G5_MIN_FRACTION: dict[str, float] = {
    "vina": 16 / 17,
    "smina-default": 16 / 17,
    "smina-vinardo": 16 / 17,
    "smina-dkoes_fast": 16 / 17,
    "smina-ad4": 15 / 17,
}

#: Catalogued receptors in any training-overlap stratum. Reported apart, never counted.
#: Frozen empty 2026-11-04 on the held official indexes (see PREREGISTRATION_ENGINE.md
#: open item 1, resolved): Vina PDBbind 2007 refined (n=1300) ∩ catalog = 0; Vinardo's
#: 122 ⊂ Core 2013 official 195 ∩ catalog = 0; BindingDB CSAR dkoes proxy (746) ∩
#: catalog = 0. PDBbind+ 2020 general PL (14 catalog hits) is not a training set.
TRAINING_OVERLAP: frozenset[str] = frozenset()
#: Empty: every candidate arm's held training index has been intersected. HiQ 343 as a
#: named file is still gone; that does not populate this set (unconfirmed ids stay out).
TRAINING_PROVENANCE_UNRESOLVED: frozenset[str] = frozenset()
#: Two Core 2013 codes in Nature Protocols 2018 Table S3 that DeepChem's 193 omit.
#: 193 ∪ this = 195. Neither is in the catalog.
CORE2013_DEEPCHEM_GAP: frozenset[str] = frozenset({"3ZSO", "3ZSX"})
#: `INDEX.2007.refined.data` from the DGL v2007 redistrib (Trott: Vina trained on the
#: PDBbind refined set). Count pinned so a truncated extract cannot silently look empty.
VINA_PDBBIND_2007_REFINED_COUNT: int = 1300

GateName = Literal["G1", "G2", "G3", "G4", "G5"]


def sign_test_one_sided(wins: int, losses: int) -> float:
    """P(at least `wins` of wins+losses discordant receptors fall one way) under a fair coin."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n


def sign_test_two_sided(changes: int, n: int) -> float:
    """Two-sided exact binomial test for `changes` successes in `n` paired discordant trials."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(changes, n + 1)) / 2**n
    return min(1.0, 2.0 * tail)


def arm_correct(seed_top_correct: Sequence[bool | None]) -> bool | None:
    """Whether an arm meets the 2-of-3-seed rule; None when fewer than three seeds are known."""
    if len(seed_top_correct) != len(SEEDS):
        return None
    known = [v for v in seed_top_correct if v is not None]
    if len(known) < len(SEEDS):
        return None
    return sum(1 for v in known if v) >= SEEDS_REQUIRED


@dataclass(frozen=True)
class ReceptorArm:
    pdb: str
    arm: str
    seed_top_correct: tuple[bool | None, bool | None, bool | None]


@dataclass(frozen=True)
class PairOutcome:
    pdb: str
    before: bool | None
    after: bool | None


def compare_arms(before: ReceptorArm, after: ReceptorArm) -> PairOutcome:
    """Gained/lost for one receptor between two arms under the seed-majority rule."""
    return PairOutcome(before.pdb, arm_correct(before.seed_top_correct), arm_correct(after.seed_top_correct))


@dataclass(frozen=True)
class Tally:
    compared: int
    gained: int
    lost: int
    unchanged: int


def tally_pairs(outcomes: Sequence[PairOutcome]) -> Tally:
    discordant = [o for o in outcomes if o.before is not None and o.after is not None]
    gained = sum(1 for o in discordant if not o.before and o.after)
    lost = sum(1 for o in discordant if o.before and not o.after)
    unchanged = sum(1 for o in discordant if o.before == o.after)
    return Tally(len(discordant), gained, lost, unchanged)


def candidate_verdict(t: Tally) -> str:
    """PASS, HARMFUL or NULL for one candidate against one comparator."""
    net = t.gained - t.lost
    if net >= MIN_NET and sign_test_one_sided(t.gained, t.lost) <= ALPHA:
        return "PASS"
    if -net >= MIN_NET and sign_test_one_sided(t.lost, t.gained) <= ALPHA:
        return "HARMFUL"
    return "NULL"


def control_is_neutral(outcomes: Sequence[PairOutcome], level: float = 0.05) -> bool:
    """Whether `smina-default` differs from `vina` at the two-sided level (search-code backdrop)."""
    discordant = [o for o in outcomes if o.before is not None and o.after is not None and o.before != o.after]
    n = len(discordant)
    if n == 0:
        return True
    changes = sum(1 for o in discordant if o.after and not o.before)
    return sign_test_two_sided(changes, n) > level


@dataclass(frozen=True)
class GateResult:
    name: GateName
    passed: bool
    detail: str


def gate_g1_reproduces_survey(
    recorded: Sequence[tuple[str, float]],
    measured: Sequence[tuple[str, float]],
    *,
    tol: float = G1_DISTANCE_TOL,
) -> GateResult:
    """The vina arm at seed 20261029 reproduces recorded top-pose distances."""
    rec = dict(recorded)

    def delta_centia(recorded_a: float, measured_a: float) -> int:
        """Difference in centi-Å, matching survey ``round(..., 2)`` storage."""
        return abs(int(round(recorded_a * 100)) - int(round(measured_a * 100)))

    limit_centia = int(round(tol * 100))
    bad = [
        f"{pdb} recorded {rec[pdb]:.2f} measured {meas:.2f}"
        for pdb, meas in measured
        if pdb in rec and delta_centia(rec[pdb], meas) > limit_centia
    ]
    missing = sorted(set(rec) - {p for p, _ in measured})
    if missing:
        bad.append(f"missing {len(missing)} receptors")
    return GateResult("G1", not bad, "; ".join(bad) if bad else f"all within {tol} A")


def gate_g2_same_function(
    diffs_kcal: Sequence[float],
    *,
    tol: float = G2_SCORE_TOL,
) -> GateResult:
    """Score-only agreement between Vina and smina-default."""
    if not diffs_kcal:
        return GateResult("G2", False, "no comparisons")
    worst = max(abs(d) for d in diffs_kcal)
    return GateResult(
        "G2",
        worst <= tol,
        f"max |diff| {worst:.4f} kcal/mol" + ("" if worst <= tol else f" exceeds {tol}"),
    )


def gate_g3_reproducible(failures: Sequence[str]) -> GateResult:
    """Byte-identical re-docks for one receptor per arm and seed."""
    return GateResult("G3", not failures, "; ".join(failures) if failures else "all matched")


def gate_g4_coverage(docked_per_arm: dict[str, int], population: int = 47) -> GateResult:
    """Every arm docks enough receptors; paired drops are counted separately by the runner."""
    low = {arm: n for arm, n in docked_per_arm.items() if n < G4_MIN_DOCKED}
    if low:
        parts = ", ".join(f"{arm} {n}/{population}" for arm, n in sorted(low.items()))
        return GateResult("G4", False, f"below {G4_MIN_DOCKED}: {parts}")
    return GateResult("G4", True, f"all arms >= {G4_MIN_DOCKED}/{population}")


def crystal_score_favorable(score: float | None) -> bool:
    """Finite `--score_only` affinity below zero on the app's crystal-ligand pipeline."""
    if score is None:
        return False
    return math.isfinite(score) and score < 0.0


def gate_g5_crystal_scores(
    favorable_fraction: float,
    *,
    min_fraction: float,
) -> GateResult:
    """Crystal-ligand score sanity for one function; threshold fixed at freeze from the pilot."""
    if not math.isfinite(favorable_fraction):
        return GateResult("G5", False, "no favorable_fraction")
    ok = favorable_fraction >= min_fraction
    return GateResult(
        "G5",
        ok,
        f"favorable {favorable_fraction:.3f} need >= {min_fraction:.3f}",
    )


def gate_g5_for_arm(arm: str, favorable_fraction: float) -> GateResult:
    """G5 for one preregistered arm using that arm's pinned `G5_MIN_FRACTION`."""
    min_frac = G5_MIN_FRACTION.get(arm)
    if min_frac is None:
        return GateResult("G5", False, f"{arm}: unknown arm")
    base = gate_g5_crystal_scores(favorable_fraction, min_fraction=min_frac)
    return GateResult("G5", base.passed, f"{arm}: {base.detail}")


def gate_g5_all_arms(favorable_fractions: dict[str, float]) -> list[GateResult]:
    """One G5 result per arm; the runner stops at `first_failed_gate` on this list."""
    return [gate_g5_for_arm(arm, favorable_fractions.get(arm, float("nan"))) for arm in G5_ARMS]


def first_failed_gate(gates: Sequence[GateResult]) -> GateResult | None:
    for gate in gates:
        if not gate.passed:
            return gate
    return None


def overall_verdict(
    gates: Sequence[GateResult],
    candidate_results: dict[str, str],
) -> str:
    """INCONCLUSIVE when any gate fails; else the strongest candidate verdict in fixed order."""
    if first_failed_gate(gates):
        return "INCONCLUSIVE"
    order = {"PASS": 0, "HARMFUL": 1, "NULL": 2}
    if not candidate_results:
        return "NULL"
    return min(candidate_results.values(), key=lambda v: order.get(v, 99))
