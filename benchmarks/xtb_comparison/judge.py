"""The judge of `PREREGISTRATION.md` (section 8): the same-minimum tolerance from the floor, and the reading rule of each of the three claims over plain records. Pure arithmetic: no engine and no file read, so the
rule is tested without any job (`tests/test_xtb_comparison_judge.py`) and cannot move after a result is seen. Where this file and the preregistration disagree, one of them is defective and is fixed before any run.

Records are dicts. Energies are in Hartree and distances in Angstrom; a missing cell is `None` (or absent where noted), never a pass.

* C1 (geometry): `{"molecule", "heavy_rmsd", "bond_mad"}`, one per judged molecule, `None` for a missing job.
* C2 (relative energies): `{"label", "xtb_kcal", "reference_kcal"}`, one per pair, the end-to-end energy differences in kcal/mol.
* C3 (pre-optimizer): `{"molecule", "cycles_mmff", "cycles_xtb", "energy_mmff", "energy_xtb", "seconds_mmff", "seconds_xtb_total"}`, one per judged molecule.

There is NO overall verdict: each claim is judged on its own (section 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

PASS, PARTIAL, FAIL, NOT_EVALUABLE = "PASS", "PARTIAL", "FAIL", "NOT EVALUABLE"
TIER_A, TIER_B, TIER_C = "TIER A", "TIER B", "TIER C"

HARTREE_TO_MEH = 1000.0
HARTREE_TO_KCAL = 627.509474

#: The share of cells that may be missing (per claim) before it is NOT EVALUABLE.
MISSING_LIMIT = 0.10
#: The ORCA optimizer floor's RMSD above which arm P (and C1's reference) cannot tell two minima from one, Angstrom.
CEILING_RMSD = 0.02
#: The same-minimum tolerance's ceiling, mEh.
CEILING_ENERGY_MEH = 0.5
#: Two final energies are the same minimum within max(FLOOR_FACTOR x the ORCA optimizer energy floor, RESOLUTION_MEH).
FLOOR_FACTOR = 2.0
RESOLUTION_MEH = 0.01

#: C1 thresholds (section 8; decision D3). All Angstrom.
C1_FAIL_MEDIAN = 0.10
C1_FAIL_ANY = 0.30
C1_PASS_MEDIAN = 0.05
C1_PASS_MAX = 0.15
C1_PASS_BOND_MEDIAN = 0.015

#: C2 thresholds: the tier bounds on the mean absolute error (kcal/mol), the reference difference above which a pair counts for the ordering test, and the share that must be ordered the same way.
C2_TIER_A_MAE = 1.0
C2_TIER_B_MAE = 3.0
C2_RANKING_SEPARATION = 1.0
C2_RANKING_NEEDED = 0.90
#: Fewer same-minimum conformer pairs than this across set F make C2 NOT EVALUABLE.
C2_MIN_CONFORMER_PAIRS = 12

#: C3 thresholds.
C3_SAME_MINIMUM_NEEDED = 0.90
C3_RATIO_MAX = 0.80
C3_P_MAX = 0.05
C3_FASTER_SHARE = 0.5


@dataclass(frozen=True)
class Floors:
    """What the ORCA optimizer floor (default `Opt` against `TightOpt`, section 6) gives: the largest change in final energy (mEh) and in structure (Angstrom)."""

    orca_opt_energy_meh: float
    orca_opt_rmsd_angstrom: float

    @property
    def same_minimum_meh(self) -> float:
        """T_E: two final energies within this are the same minimum."""
        return max(FLOOR_FACTOR * self.orca_opt_energy_meh, RESOLUTION_MEH)

    def broken(self) -> str | None:
        """The reason the floors break their ceiling, or None."""
        if self.orca_opt_rmsd_angstrom > CEILING_RMSD:
            return f"the ORCA optimizer-floor RMSD {self.orca_opt_rmsd_angstrom:.4f} A is above the {CEILING_RMSD} A ceiling"
        if self.same_minimum_meh > CEILING_ENERGY_MEH:
            return f"the same-minimum tolerance {self.same_minimum_meh:.3f} mEh is above the {CEILING_ENERGY_MEH} mEh ceiling"
        return None


def floor(differences: list[float]) -> float:
    """The floor of a class: the largest absolute change a harmless setting made (no measurement is an error, not zero)."""
    if not differences:
        raise ValueError("a floor needs at least one measured difference")
    return max(abs(d) for d in differences)


@dataclass(frozen=True)
class Verdict:
    claim: str
    verdict: str
    reason: str
    numbers: dict

    def __str__(self) -> str:
        return f"{self.claim}: {self.verdict} -- {self.reason}"


def _missing_share(values: list[object]) -> float:
    return sum(1 for v in values if v is None) / len(values) if values else 1.0


# --- C1 ---------------------------------------------------------------------------------------------------------------------


def judge_geometry(rows: list[dict], floors: Floors, missing_cells: int = 0, total_cells: int | None = None) -> Verdict:
    """C1. Rows are the judged molecules (a `None` heavy RMSD is a missing job). `missing_cells` and `total_cells` let the runner count a missing REFERENCE job too (a molecule with no ORCA structure has no row at all)."""
    total = total_cells if total_cells is not None else len(rows)
    missing = missing_cells + sum(1 for r in rows if r.get("heavy_rmsd") is None)
    present = [r for r in rows if r.get("heavy_rmsd") is not None]
    numbers: dict = {"judged": len(present), "missing": missing, "cells": total}
    if total == 0 or not present:
        return Verdict("C1", NOT_EVALUABLE, "no molecule has both structures", numbers)
    if missing / total > MISSING_LIMIT:
        return Verdict("C1", NOT_EVALUABLE, f"{missing} of {total} cells are missing (limit {MISSING_LIMIT:.0%})", numbers)
    reason = floors.broken()
    if reason is not None and floors.orca_opt_rmsd_angstrom > CEILING_RMSD:
        return Verdict("C1", NOT_EVALUABLE, reason, numbers)
    rmsds = [r["heavy_rmsd"] for r in present]
    bonds = [r["bond_mad"] for r in present if r.get("bond_mad") is not None]
    med, worst = median(rmsds), max(rmsds)
    bond_med = median(bonds) if bonds else None
    numbers.update(median_heavy_rmsd=med, max_heavy_rmsd=worst, median_bond_mad=bond_med)
    if worst > C1_FAIL_ANY or med > C1_FAIL_MEDIAN:
        return Verdict("C1", FAIL, f"median heavy-atom RMSD {med:.3f} A (fail above {C1_FAIL_MEDIAN}), maximum {worst:.3f} A (fail above {C1_FAIL_ANY})", numbers)
    if med <= C1_PASS_MEDIAN and worst <= C1_PASS_MAX and bond_med is not None and bond_med <= C1_PASS_BOND_MEDIAN:
        return Verdict("C1", PASS, f"median {med:.3f} A, maximum {worst:.3f} A, median bond deviation {bond_med:.4f} A", numbers)
    return Verdict("C1", PARTIAL, f"median {med:.3f} A, maximum {worst:.3f} A, median bond deviation {'n/a' if bond_med is None else f'{bond_med:.4f}'} A", numbers)


# --- C2 ---------------------------------------------------------------------------------------------------------------------


def judge_relative(
    pairs: list[dict], conformer_pairs: int, missing_cells: int = 0, total_cells: int | None = None, floors: Floors | None = None
) -> Verdict:
    """C2. `pairs` are all the pairs that exist (the isomer pairs and the same-minimum conformer pairs); `conformer_pairs` is how many of them are conformer pairs. A pair with a `None` energy is a missing cell.

    The tier is the MAE tier, lowered one level when fewer than C2_RANKING_NEEDED of the pairs whose reference difference exceeds C2_RANKING_SEPARATION are ordered the same way. With NO such pair the ordering test
    cannot be applied and the tier stands, said in the result (a rule cannot lower a tier on an empty set).
    """
    total = total_cells if total_cells is not None else len(pairs)
    usable = [p for p in pairs if p.get("xtb_kcal") is not None and p.get("reference_kcal") is not None]
    missing = missing_cells + (len(pairs) - len(usable))
    numbers: dict = {"pairs": len(usable), "conformer_pairs": conformer_pairs, "missing": missing, "cells": total}
    if conformer_pairs < C2_MIN_CONFORMER_PAIRS:
        return Verdict("C2", NOT_EVALUABLE, f"only {conformer_pairs} same-minimum conformer pairs survive (need {C2_MIN_CONFORMER_PAIRS})", numbers)
    if not usable or (total and missing / total > MISSING_LIMIT):
        return Verdict("C2", NOT_EVALUABLE, f"{missing} of {total} cells are missing (limit {MISSING_LIMIT:.0%})", numbers)
    errors = [p["xtb_kcal"] - p["reference_kcal"] for p in usable]
    mae = sum(abs(e) for e in errors) / len(errors)
    signed = sum(errors) / len(errors)
    tier = TIER_A if mae <= C2_TIER_A_MAE else TIER_B if mae <= C2_TIER_B_MAE else TIER_C
    separated = [p for p in usable if abs(p["reference_kcal"]) > C2_RANKING_SEPARATION]
    ordered = [p for p in separated if (p["xtb_kcal"] > 0) == (p["reference_kcal"] > 0)]
    share = len(ordered) / len(separated) if separated else None
    numbers.update(mae_kcal=mae, mean_signed_error_kcal=signed, max_abs_error_kcal=max(abs(e) for e in errors), ranking_share=share, ranking_pairs=len(separated))
    note = ""
    if share is None:
        note = "; no pair is separated by more than 1 kcal/mol in the reference, so the ordering test could not be applied and the tier stands"
    elif share < C2_RANKING_NEEDED:
        tier = {TIER_A: TIER_B, TIER_B: TIER_C, TIER_C: TIER_C}[tier]
        note = f"; only {share:.0%} of the {len(separated)} separated pairs are ordered as the reference orders them, so the tier is lowered"
    else:
        note = f"; {share:.0%} of the {len(separated)} separated pairs are ordered as the reference orders them"
    return Verdict("C2", tier, f"MAE {mae:.2f} kcal/mol over {len(usable)} pairs (mean signed error {signed:+.2f}){note}", numbers)


# --- C3 ---------------------------------------------------------------------------------------------------------------------


def wilcoxon_less(after: list[float], before: list[float]) -> float:
    """The one-sided Wilcoxon signed-rank p-value that `after` is smaller than `before` (pairs, zero differences dropped; all zero = p of 1.0)."""
    from scipy.stats import wilcoxon

    differences = [a - b for a, b in zip(after, before, strict=True)]
    if all(d == 0 for d in differences):
        return 1.0
    return float(wilcoxon(differences, alternative="less", zero_method="wilcox").pvalue)


def judge_preoptimizer(rows: list[dict], floors: Floors, missing_cells: int = 0, total_cells: int | None = None) -> Verdict:
    """C3. Rows are the judged molecules; a row whose energies or cycle counts are `None` is a missing pair."""
    total = total_cells if total_cells is not None else len(rows)
    complete = [r for r in rows if all(r.get(k) is not None for k in ("cycles_mmff", "cycles_xtb", "energy_mmff", "energy_xtb"))]
    missing = missing_cells + (len(rows) - len(complete))
    numbers: dict = {"pairs": len(complete), "missing": missing, "cells": total}
    reason = floors.broken()
    if reason is not None:
        return Verdict("C3", NOT_EVALUABLE, reason, numbers)
    if not complete or (total and missing / total > MISSING_LIMIT):
        return Verdict("C3", NOT_EVALUABLE, f"{missing} of {total} pairs are missing (limit {MISSING_LIMIT:.0%})", numbers)
    t_e = floors.same_minimum_meh
    same = [r for r in complete if abs(r["energy_xtb"] - r["energy_mmff"]) * HARTREE_TO_MEH <= t_e]
    share = len(same) / len(complete)
    numbers.update(same_minimum_share=share, same_minimum_tolerance_meh=t_e)
    if share < C3_SAME_MINIMUM_NEEDED:
        return Verdict("C3", FAIL, f"only {share:.0%} of the pairs end at the same minimum within {t_e:.3f} mEh (need {C3_SAME_MINIMUM_NEEDED:.0%})", numbers)
    ratios = [r["cycles_xtb"] / r["cycles_mmff"] for r in complete]
    ratio = median(ratios)
    p = wilcoxon_less([r["cycles_xtb"] for r in complete], [r["cycles_mmff"] for r in complete])
    timed = [r for r in complete if r.get("seconds_mmff") is not None and r.get("seconds_xtb_total") is not None]
    faster = sum(1 for r in timed if r["seconds_xtb_total"] < r["seconds_mmff"]) / len(timed) if timed else 0.0
    numbers.update(median_cycle_ratio=ratio, wilcoxon_p=p, faster_share=faster)
    detail = f"median cycle ratio {ratio:.2f}, one-sided p {p:.3f}, total time lower from the xtb start in {faster:.0%} of molecules; {share:.0%} reach the same minimum"
    if ratio <= C3_RATIO_MAX and p < C3_P_MAX and faster >= C3_FASTER_SHARE:
        return Verdict("C3", PASS, detail, numbers)
    return Verdict("C3", PARTIAL, detail + " (same minimum, but no demonstrated saving)", numbers)
