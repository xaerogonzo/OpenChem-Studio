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

**RETRACTED 2026-09-29 (Track 4, Gate B): the "RDX clears the bar at 2.1 kJ/mol" conclusion above did
not survive a fresh, internally-consistent recomputation, and the recorded Etot values above were
never internally consistent to begin with.** Re-running HMX's exact documented recipe (this SMILES,
ETKDGv3 seed 0xC0FFEE, MMFF94 pre-optimize, B3LYP/def2-SVP opt) gave an Etot **108 kJ/mol** away from
the value recorded above -- an order of magnitude bigger than the already-ruled-out conformer-choice
effect (6.1 kJ/mol), and bigger than the entire ~25 kJ/mol HMX residual this whole module was built to
explain. Every one of the 12 CALIBRATION_SET/TARGET_ETOT_KJMOL entries showed the same one-directional
drift when re-run (fresh always higher-energy than recorded), scaling with molecular flexibility:
0.1-0.8 kJ/mol for the rigid small molecules (methane/ammonia/benzene), 3-13 kJ/mol for the mid-sized
nitro compounds, 45-108 kJ/mol for RDX/HMX/PETN. **Root cause**: `pyproject.toml` pinned RDKit as
`>=2024.3.1`, a floating lower bound, and `uv.lock`'s resolved RDKit version changed at least twice
across this multi-session survey -- ETKDGv3 is only deterministic for a given seed WITHIN one RDKit
build, so different sessions' "same seed 0xC0FFEE" embeds were silently landing on different starting
conformers, which converged to different DFT local minima. **The 6/7/9-fit progression's whole narrative
-- that adding nitramine-specific calibration data systematically helped RDX -- was built on that drift,
not on real signal**: every compound in the original table above was computed at a different, unrecorded
point in that drift, so the fit's apparent improvement conflated genuine calibration-chemistry signal
with environment noise of comparable or larger size. `pyproject.toml` is now pinned exact
(`rdkit==2025.9.6`) to prevent this recurring.

**All 9 calibration compounds plus RDX/HMX/PETN were re-run fresh, in one sitting, under the pinned
environment**, and the atom equivalents refit on the internally-consistent result:

    compound   6-fit    7-fit(+dimethylnitramine)   9-fit(+nitropiperidine,+ethyl_nitrate)   measured         best diff
    RDX         53.4       121.2                        123.4                               66.6 / 85.0      13.2 kJ/mol (6-fit)
    HMX         68.0       158.4                        161.3                               116.1            42.3 kJ/mol (7-fit)
    PETN       -479.5      -458.5                       -451.4                              -539.0           59.5 kJ/mol (6-fit)

**The qualitative conclusion is now the OPPOSITE of the original writeup for RDX**: under consistent
data, adding nitramine/nitrate-ester calibration chemistry makes RDX's combined-route error WORSE,
monotonically (13.2 -> 36.2 -> 38.4 kJ/mol), not better -- the untargeted 6-compound fit (no nitramine
data at all) is RDX's best available result, and it is the ONLY one of the three fits that still clears
SENSITIVITY.md's ~21 kJ/mol bar. HMX is non-monotonic (48.1 -> 42.3 -> 45.2 kJ/mol) and never clears the
bar in any fit. **PETN's finding is the one part of the original writeup that survives**: its error still
gets monotonically worse as nitramine/nitrate-ester data is added (59.5 -> 80.5 -> 87.6 kJ/mol), the same
direction as before, so that specific conclusion (a purely elemental atom-equivalent scheme cannot
represent PETN's four-arm quaternary-carbon structure without a matching calibration compound) was not
an artifact of the environment drift -- it reproduces under a consistent recomputation, unlike RDX's.

**This is now, honestly, a worse-performing route than it was reported to be**, and the reason to keep
this module rather than delete it is that the drift itself -- and PETN's surviving, now doubly-confirmed
finding -- are real results worth keeping on record. Any further work on this route (a higher level of
theory, more calibration data) must start from the fresh numbers below, and must re-run the ENTIRE
calibration set together in one sitting if it changes anything, never add one new compound to the
existing (already environment-drifted) numbers.

**Reproducibility note**: the ORCA total energies below are recorded from real jobs run on this machine
(ORCA 6.1.1, B3LYP/def2-SVP, RDKit 2025.9.6 -- now pinned exact in `pyproject.toml`) -- not re-run by the
test suite, the same way this project records a paper's own printed table values rather than re-deriving
them from source data it doesn't hold. All calibration compounds and RDX/HMX/PETN use the same single
ETKDGv3-seed-0xC0FFEE seed, re-embedded fresh in the current environment; only the conformer CHECK above
(RDX/HMX/nitropiperidine, from the original, now-superseded numbers) used a wider search, and its own
qualitative conclusion (conformer choice does not explain RDX/HMX's error) is unaffected by this
correction -- the 108 kJ/mol drift is roughly 4x that conformer study's own largest gap (30.3 kJ/mol,
MMFF-ranked) and was traced to the RDKit version, not to conformer choice within one version.
"""

from __future__ import annotations

import numpy as np

#: (element_counts as (C, H, N, O), Etot from a real ORCA B3LYP/def2-SVP `opt` job, kJ/mol,
#: experimental gas DfH, kJ/mol -- primary source noted per row).
#:
#: RE-RUN FRESH 2026-09-29, all 9 rows plus TARGET_ETOT_KJMOL below, in one sitting under the pinned
#: environment (RDKit 2025.9.6, ORCA 6.1.1) -- see the module docstring's RETRACTED note. The previous
#: values were each computed at a different, undocumented point in an RDKit-version drift and were never
#: internally consistent with each other.
CALIBRATION_SET = {
    # Lange's Handbook Table 6.1 for all experimental values below. Water was run first as a pipeline
    # feasibility check but deliberately left out of the fit -- an inorganic, non-hydride-bonded-carbon
    # molecule pulls the O atom equivalent in a direction the fit's actual use case (organic/energetic
    # C,H,N,O compounds) does not need, and every number in this module's docstring and the paired tests
    # was computed on the 7-compound organic set below.
    "methane": ((1, 4, 0, 0), -106206.299, -74.6),
    "ammonia": ((0, 3, 1, 0), -148269.955, -45.9),
    "benzene": ((6, 6, 0, 0), -608933.278, 82.6),
    "methanol": ((1, 4, 0, 1), -303413.897, -201.0),
    "nitromethane": ((1, 3, 1, 2), -642474.368, -74.3),
    "methyl_nitrate": ((1, 3, 1, 3), -839626.586, -124.4),
    # NIST WebBook (Matyushin, V'yunova, Pepekin, Apin, 1971) -- two nitramines, one acyclic, one a
    # 6-membered ring (structurally close to RDX's own ring).
    "dimethylnitramine": ((2, 6, 2, 2), -890629.381, -5.0),
    "nitropiperidine": ((5, 10, 2, 2), -1196706.729, -44.0),
    # NIST WebBook (Gray, Pratt, Larkin, 1956) -- a second, simple primary nitrate ester.
    "ethyl_nitrate": ((2, 5, 1, 3), -942707.230, -155.0),
}

#: RDX, HMX, PETN Etot from the same real ORCA jobs -- no experimental gas-phase DfH exists to check
#: these against directly (both decompose before vaporizing); see the module docstring for how the
#: COMBINED (gas - Hsub) route was checked instead, against real condensed-phase measured values.
#: Re-run fresh 2026-09-29 alongside CALIBRATION_SET -- see that note.
TARGET_ETOT_KJMOL = {
    "RDX": ((3, 6, 6, 6), -2353224.239),
    "HMX": ((4, 8, 8, 8), -3137634.721),
    "PETN": ((5, 8, 4, 12), -3452150.435),
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
