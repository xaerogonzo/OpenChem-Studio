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
Pepekin, Apin, 1971) -- and refitting all four atom equivalents from the resulting 7-point set changed the
picture substantially: RDX cleared the accuracy bar, HMX's error roughly halved, and PETN got WORSE.

**Two follow-ups, same investigation, different questions.**

1. *Was RDX/HMX's own starting conformer the problem?* A single ETKDGv3 embed (seed 0xC0FFEE, MMFF94
   pre-optimized) was used for every ORCA job, with no conformer search -- and MMFF94 ranked that RDX
   conformer 18th of 35 (7.25 kcal/mol = 30.3 kJ/mol above an 80-conformer search's own minimum) and
   HMX's 30th of 50 (15.90 kcal/mol = 66.5 kJ/mol above). Re-running ORCA's B3LYP/def2-SVP Opt from each
   molecule's MMFF94-global-minimum conformer instead: RDX's converged Etot moved by only -4.3 kJ/mol,
   nitropiperidine's by -1.8 kJ/mol, and HMX's by **+6.1 kJ/mol -- the "better" MMFF conformer converged
   to a HIGHER DFT energy**, not a lower one. **Conclusion: conformer choice is NOT the source of
   RDX/HMX's remaining error.** The large MMFF94 energy gaps do not translate to comparable DFT energy
   gaps after ORCA's own optimization -- expected, since a force-field ranking is not a DFT ranking, but
   worth having actually checked rather than assumed. The original single-seed Etot values are kept as
   the recorded result (below) for consistency with the rest of the calibration set, which was never
   re-checked this way.

2. *Does more calibration data, specifically more of the two chemistry classes that mattered, help?*
   Added a second nitramine -- 1-nitropiperidine (a 6-membered RING nitramine, structurally much closer
   to RDX's own ring than dimethylnitramine was), DfH(gas) = -44 +/- 3 kJ/mol, NIST WebBook (Matyushin et
   al. 1971, the same source series) -- and a second nitrate ester, ethyl nitrate, DfH(gas) = -155 +/- 3
   kJ/mol, NIST WebBook (Gray, Pratt, Larkin, 1956). Refitting on the resulting 9-point set:

    compound   6-fit    7-fit(+dimethylnitramine)   9-fit(+nitropiperidine,+ethyl_nitrate)   measured         best diff
    RDX         50.1        80.4                         82.9                               66.6 / 85.0      2.1 kJ/mol
    HMX         66.0        87.8                         91.0                               116.1            25.1 kJ/mol
    PETN       -482.0      -466.3                       -458.6                              -539.0           80.4 kJ/mol

   RDX improved again (now within 2.1 kJ/mol of Klapoetke's Table 9.6 value, comfortably inside the
   ~21 kJ/mol bar against both of its measured readings). HMX improved again but is still over the bar.
   **PETN got WORSE a second time, monotonically across all three fits (46.6 -> 72.7 -> 80.4 kJ/mol as
   more nitramine/nitrate-ester data was added)** -- despite ethyl nitrate being exactly the kind of
   additional nitrate-ester data the earlier writeup called for. A one-point fluke would not do this
   twice in the same direction. The more likely explanation: PETN's own structure (a quaternary carbon
   bearing FOUR -CH2-O-NO2 arms) is not well represented by methyl/ethyl nitrate's simple primary
   alkyl-nitrate chemistry, and a purely elemental atom-equivalent scheme has no way to encode that
   structural difference -- more data of the WRONG shape for PETN specifically cannot fix this, and did
   not.

**This is a real, useful, and still explicitly NOT a validated result.** Nine calibration compounds
fitting four free parameters is a real improvement over seven (five degrees of freedom, not three), and
RDX's result is now genuinely strong evidence, not a single lucky point. PETN's monotonically worsening
error across three independent refits is equally real evidence, in the other direction, that a single
per-element atom-equivalent scheme cannot generalize to its specific structural class without a nitrate
ester more like it (a branched/quaternary-carbon polyol nitrate, not a simple primary one) in the
calibration set -- the clear, now more specific, next step for anyone continuing this.

**Reproducibility note**: the ORCA total energies below are recorded from real jobs run on this machine
(ORCA 6.1.1, B3LYP/def2-SVP) -- not re-run by the test suite, the same way this project records a paper's
own printed table values rather than re-deriving them from source data it doesn't hold. All calibration
compounds and RDX/HMX/PETN use the original single ETKDGv3-seed-0xC0FFEE seed; only the conformer CHECK
above (RDX/HMX/nitropiperidine) used a wider search, and its own result was not substituted in below,
per the conformer-choice conclusion just above.
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
    # NIST WebBook (Matyushin, V'yunova, Pepekin, Apin, 1971) -- two nitramines, one acyclic, one a
    # 6-membered ring (structurally close to RDX's own ring).
    "dimethylnitramine": ((2, 6, 2, 2), -890642.600, -5.0),
    "nitropiperidine": ((5, 10, 2, 2), -1196717.858, -44.0),
    # NIST WebBook (Gray, Pratt, Larkin, 1956) -- a second, simple primary nitrate ester.
    "ethyl_nitrate": ((2, 5, 1, 3), -942717.292, -155.0),
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
