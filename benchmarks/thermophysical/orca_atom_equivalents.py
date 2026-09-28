"""A from-scratch atom-equivalent scheme for gas-phase DfH, calibrated on this app's own real ORCA
install (B3LYP/def2-SVP geometry optimizations, ORCA 6.1.1) rather than reproduced from a paper -- the
option `mathieu2018_apc`'s literature.toml entry flagged as "a real, unexplored option" for Track 3's
gas-phase-Hf gap, now actually run.

**Why this exists alongside `mathieu2018_apc`.** That module's combined route (its own gas-phase model
plus `keshavarz2010_sublimation`) was computed end-to-end and checked against real measured Klapoetke
values: REJECTED for RDX/HMX/PETN (HMX and PETN miss by 50-57 kJ/mol; RDX borderline). This module asks
whether OUR OWN ab initio route, calibrated directly rather than inherited from a 2671-compound fit that
never saw a nitramine specifically, does better.

**Method**: DfH(gas) = Etot(DFT, kJ/mol) + sum_atoms AtomEquivalent(element) -- the standard
Dewar/O'Connor-style scheme this app's own `orca_engine.py` docstrings already reference for AE1/AE2 (the
mathieu2018_apc paper's OWN atom-equivalent procedure, whose calibration constants are Supporting
Information, not held). AtomEquivalent(C/H/N/O) is fit here by ordinary least squares against a small
calibration set of real molecules with primary-source experimental gas DfH -- not copied from any paper.

**Calibration set and the finding that mattered**: a first fit on 6 small molecules (water, methane,
ammonia, benzene, methanol, nitromethane, methyl nitrate -- all Lange's Handbook Table 6.1/6.3) gave an
excellent SELF-consistent fit (residuals 0.5-11 kJ/mol) but, applied to RDX/HMX/PETN, missed the real
Klapoetke condensed-phase values by 71-141 kJ/mol -- worse than `mathieu2018_apc`'s literature route.
**The calibration set had zero nitramine chemistry** (nitromethane's N is bonded to carbon; methyl
nitrate's N is bonded to an ester oxygen; neither has RDX/HMX's ring-N-N(NO2) linkage). Adding ONE real
nitramine -- dimethylnitramine (CH3)2N-NO2, DfH(gas) = -5 +/- 1 kJ/mol, NIST WebBook (Matyushin, V'yunova,
Pepekin, Apin, 1971, combustion calorimetry) -- and refitting all four atom equivalents from the resulting
7-point set changed the picture substantially:

    compound            combined solid DfH, kJ/mol       measured (klapotke2017)     diff, kJ/mol
    RDX   (6-fit)        50.1 -> (7-fit, w/ nitramine)  80.4    66.6 / 85.0 (p.232/Tab.9.6)   13.8 / 4.6
    HMX   (6-fit)        66.0 -> (7-fit)                87.8    116.1 (Tab. 9.16a, p.270)      28.3
    PETN  (6-fit)       -482.0 -> (7-fit)              -466.3   -539.0 (Tab. 9.16b, p.270)      72.7

RDX moved from clearly failing the ~21 kJ/mol (5 kcal/mol) SENSITIVITY.md bar to clearing it against BOTH
of Klapoetke's own numbers. HMX's error roughly halved (still over the bar). PETN got WORSE, not better --
a nitrate ester, not a nitramine, and the single added calibration point pulled the fitted N/O atom
equivalents toward the nitramine's chemistry at nitrate-ester chemistry's expense.

**This is a real, useful, and explicitly NOT a validated result.** Seven calibration compounds fitting
four free parameters leaves three degrees of freedom -- a fragile fit, and the PETN regression is the
direct evidence of that fragility, not a coincidence to explain away. The improvement on RDX/HMX is
consistent with (and strong direct evidence for) a real, structurally grounded hypothesis -- atom
equivalents fit without any nitramine chemistry cannot describe nitramine chemistry -- but three data
points (RDX better, HMX better-but-short, PETN worse) is not enough to call the class-specific hypothesis
proven, and nowhere near enough to promote this route. The clear next step, not taken in this session, is
a genuinely adequately-sized calibration set per compound class (several nitramines, several nitrate
esters, fit separately or with enough points overall to support more than 4 free parameters) before this
could support any accuracy claim stronger than "worth continuing."

**Reproducibility note**: the ORCA total energies (`ORCA_ETOT_KJMOL` below) are recorded from real jobs
run on this machine (ORCA 6.1.1, B3LYP/def2-SVP, RDKit ETKDGv3 + MMFF94 starting geometry, single random
seed 0xC0FFEE, no conformer search) -- not re-run by the test suite, the same way this project records a
paper's own printed table values rather than re-deriving them from source data it doesn't hold. A
different starting conformer, a tighter convergence, or a different functional/basis could move Etot
enough to matter; this was not checked (no second conformer or method was tried for any molecule here).
"""

from __future__ import annotations

import numpy as np

#: (element_counts as (C, H, N, O), Etot from a real ORCA B3LYP/def2-SVP `opt` job, kJ/mol,
#: experimental gas DfH, kJ/mol -- primary source noted per row).
CALIBRATION_SET = {
    # Lange's Handbook Table 6.1 for all experimental values below. Water was run first as a pipeline
    # feasibility check (Etot -200381.462 kJ/mol) but deliberately left out of the fit -- an inorganic,
    # non-hydride-bonded-carbon molecule pulls the O atom equivalent in a direction the fit's actual
    # use case (organic/energetic C,H,N,O compounds) does not need, and every number in this module's
    # docstring and the paired tests was computed on the 7-compound organic set below.
    "methane": ((1, 4, 0, 0), -106206.509, -74.6),
    "ammonia": ((0, 3, 1, 0), -148270.087, -45.9),
    "benzene": ((6, 6, 0, 0), -608934.031, 82.6),
    "methanol": ((1, 4, 0, 1), -303417.836, -201.0),
    "nitromethane": ((1, 3, 1, 2), -642477.657, -74.3),
    "methyl_nitrate": ((1, 3, 1, 3), -839635.931, -124.4),
    # NIST WebBook (Matyushin, V'yunova, Pepekin, Apin, 1971) -- the only nitramine in this set.
    "dimethylnitramine": ((2, 6, 2, 2), -890642.600, -5.0),
}

#: RDX, HMX, PETN Etot from the same real ORCA jobs -- no experimental gas-phase DfH exists to check
#: these against directly (both decompose before vaporizing); see the module docstring for how the
#: COMBINED (gas - Hsub) route was checked instead, against real condensed-phase measured values.
TARGET_ETOT_KJMOL = {
    "RDX": ((3, 6, 6, 6), -2353293.341),
    "HMX": ((4, 8, 8, 8), -3137743.152),
    "PETN": ((5, 8, 4, 12), -3452195.112),
}

ELEMENTS = ("C", "H", "N", "O")


def fit_atom_equivalents(calibration_set: dict[str, tuple[tuple[int, int, int, int], float, float]]) -> dict[str, float]:
    """Ordinary least squares: exp - Etot = sum_e counts[e] * AtomEquivalent[e]."""
    names = list(calibration_set)
    counts = np.array([calibration_set[n][0] for n in names], dtype=float)
    residual = np.array([calibration_set[n][2] - calibration_set[n][1] for n in names], dtype=float)
    fitted, _, _, _ = np.linalg.lstsq(counts, residual, rcond=None)
    return dict(zip(ELEMENTS, fitted))


def compute_gas_hf(counts: tuple[int, int, int, int], etot_kjmol: float, atom_equivalents: dict[str, float]) -> float:
    return etot_kjmol + sum(n * atom_equivalents[e] for n, e in zip(counts, ELEMENTS))
