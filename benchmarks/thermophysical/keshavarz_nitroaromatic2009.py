"""Keshavarz (2009), J. Hazard. Mater. 169, 890-900 -- "Predicting condensed phase heat of formation
of nitroaromatic compounds", Eq. (2). Transcribed and independently verified against the paper's own
Table 1 -- see the module-level test in tests/test_keshavarz_nitroaromatic2009.py before trusting any
number from this file.

**Why this file exists and the sister model does not.** docs/research/literature.toml's
`keshavarz_sadeghi2009` entry (the nitramine/nitrate-ester/nitroaliphatic sister paper from the same
survey) has a full writeup of a REPRODUCTION ATTEMPT THAT FAILED: its equation's own coefficients,
verified three separate ways against the source PDF, do not reproduce that paper's own printed table
values, by a margin (~4x on a clean homologous-series check) far too large to be the DE/IE correction
terms. THIS paper's Eq. (2) is different in structure -- a ratio, divided by `0.0001 * MW`, not a plain
linear sum -- and DOES reproduce its own table exactly (within rounding) on every row checked:

    1,3-dinitrobenzene (C6H4N2O4, MW 168.112, no corrections):  computed -49.25, printed -49.3
    dinitrophenol (C6H4N2O5, MW 184.112, DFG term 0.5):          computed -239.83, printed -240.0

So the two sister papers are NOT interchangeable in confidence: this one is REPRODUCED, the other is
SOURCE_VALIDATED-only. Treat them accordingly -- do not assume a working formula here says anything
about the nitramine paper's own (still-unexplained) discrepancy.
"""

from __future__ import annotations

#: Table 1's own regression coefficients, Eq. (2) (read directly from the paper, zoomed-crop verified).
Z = {
    "z1": 2.690,   # per carbon
    "z2": -2.896,  # per hydrogen
    "z3": 2.876,   # per nitrogen
    "z4": -2.784,  # per oxygen
    "z5": -1.701,  # per (n'_Ar - 1)
    "z6": -1.607,  # multiplies (n_NO2 / n_DFG/SP) * E  -- the DECREASING structural term
    "z7": 3.246,   # multiplies (n_IFG/SP / n_NO2) * F  -- the INCREASING structural term
}


def compute_hf(
    *,
    n_c: int,
    n_h: int,
    n_n: int,
    n_o: int,
    molar_mass: float,
    n_aromatic_rings: int,
    dfg_term: float = 0.0,
    ifg_term: float = 0.0,
) -> float:
    """Eq. (2): condensed-phase enthalpy of formation, kJ/mol.

    `dfg_term` is the already-combined `(n_NO2 / n_DFG/SP) * E` and `ifg_term` is
    `(n_IFG/SP / n_NO2) * F` -- callers compute these via `decreasing_term`/`increasing_term` below (or
    pass 0.0 for a compound with no applicable functional group, matching the paper's own "E and F are
    assigned to be zero if the conditions... are not met").
    """
    numerator = (
        Z["z1"] * n_c
        + Z["z2"] * n_h
        + Z["z3"] * n_n
        + Z["z4"] * n_o
        + Z["z5"] * (n_aromatic_rings - 1)
        + Z["z6"] * dfg_term
        + Z["z7"] * ifg_term
    )
    return numerator / (0.0001 * molar_mass)


def decreasing_term(n_no2: int, *, n_oh: int = 0, n_nhx: int = 0, n_cooh: int = 0, n_naphthalene: int = 0) -> float:
    """The `(n_NO2 / n_DFG/SP) * E` column, Sec. 3.2.

    **Despite the column header's literal ratio notation, the table's own printed values equal E alone**
    (or, for naphthalene, `n_DFG/SP` alone) -- NOT `E` multiplied by any `n_NO2/n_DFG/SP` ratio. Found
    2026-09-28 by cross-checking three independent Table 1/3 rows against this paper's own printed
    "(n_NO2/n_DFG/SP) x E" column:

        dinitrophenol (1 OH, 2 NO2):            printed term 0.5  == E (nOH=1, nNO2>1 -> E=0.5)
        N-nitro-N'-nitrodiphenylamine (1 NH, 2 NO2 total): printed term 0.75 == E (nNHx=1 -> E=0.75)
        1,4-/1,8-dinitronaphthalene:             printed term 2.0 == n_DFG/SP (fixed at 2.0 for this rule)

    A first implementation used the literal `(n_NO2/n_DFG/SP)*E` ratio and reproduced TATB by
    coincidence (its own ratio is exactly 1) while failing dinitrophenol by 2x -- kept as a cautionary
    note, not a second code path, since the ratio reading is simply wrong.

    At most ONE of OH/NHx/COOH/naphthalene is expected per the paper's own "lower value of E" rule for
    a compound with more than one candidate group; a genuine multi-group compound should have each
    candidate computed and the smaller value passed in explicitly, not decided by this function.
    """
    if n_naphthalene > 0:
        return 2.0
    if n_oh > 0:
        return 1.0 if n_no2 == 1 else (0.5 if n_oh == 1 else 1.75)
    if n_nhx > 0:
        return 0.0 if n_no2 == 1 else (0.75 if n_nhx == 1 else 0.67)
    if n_cooh > 0:
        return 1.75
    return 0.0


def increasing_term(n_no2: int, *, n_alkyl_or_alkoxy: int = 0) -> float:
    """`(n_IFG/SP / n_NO2) * F`, Sec. 3.3(a) only -- alkyl/alkoxy attachment (F=2.0). Hydrazine (F=1.0)
    and azo (F=6.0 or 12.0) attachments are in the paper but not implemented here: no corpus molecule
    needs them yet, and adding an untested code path for a rule never exercised would be worse than
    leaving it out."""
    if n_alkyl_or_alkoxy > 0 and n_no2 > 0:
        return (n_alkyl_or_alkoxy / n_no2) * 2.0
    return 0.0
