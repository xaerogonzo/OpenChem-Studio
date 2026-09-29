"""Keshavarz (2010), J. Hazard. Mater. 177, 648-659 -- "Improved prediction of heats of sublimation
of energetic compounds using their molecular structure", Eq. (3). Covers exactly the four classes this
survey's corpus needs (nitroaromatics, nitramines, nitroaliphatics, nitrate esters), and the paper
explicitly names its own tested compounds as including "PETN, TNT, RDX, HMX, TEX, TATB, DATB, tetryl
and CL-20" -- this survey's corpus almost verbatim.

**Reproduction status: strong, not yet exhaustive.** The paper's own Table 1 "Cyclic and acyclic
nitramines" section opens with a row (Hsub_exp printed as 175.3, "Hsub_cal" 174.6) that is almost
certainly HMX (the largest, best-known cyclic nitramine, and the value/magnitude match): applying
Eq. (3) with HMX's own molecular weight and the nitramine correction rule (Sec. 3.2) gives 174.67 kJ/mol
-- matching the paper's own printed calculated value (174.6) almost exactly. This is a strong signal
the equation is transcribed correctly (unlike `keshavarz_sadeghi2009`'s condensed-Hf sister paper, which
failed an equivalent check), but the row identification rests on magnitude/plausibility, not a named
compound in the extracted text (compound names in this paper's tables are structure images, not text) --
treat as SOURCE_VALIDATED-plus-one-strong-check, not the same confidence level as
`keshavarz_nitroaromatic2009`'s named-row reproduction.

**Reported accuracy** (the paper's own numbers): rms deviation 9.9 kJ/mol against 15 compounds compared
with quantum-mechanical computation (13.8 kJ/mol for QM); rms 6.9 kJ/mol (Table 1, max deviation 17.6);
rms 10.4 kJ/mol (Table 3, further compounds); the full 107-compound set across all three tables is
"within +/-21.0 kJ/mol of the measured values" -- coincidentally almost exactly
docs/research/SENSITIVITY.md's own ~21 kJ/mol condensed-phase Hf bar, though sublimation enthalpy and
condensed-phase Hf are different quantities and that coincidence is not itself evidence about the
combined route's accuracy.
"""

from __future__ import annotations

#: Eq. (3) coefficients, kJ/mol.
W = {"w1": 53.74, "w2": 0.2666, "w3": 13.99, "w4": -15.58}


def compute_hsub(molar_mass: float, *, c_in: float = 0.0, c_de: float = 0.0) -> float:
    """Eq. (3): Hsub = w1 + w2*MW' + w3*CIn + w4*CDe (kJ/mol).

    `molar_mass` is MW' -- the paper's own revised form (excluding halogen atomic weights) for
    halogenated nitroaromatics and hydrogen-free nitro compounds specifically; plain molecular weight
    otherwise. No corpus molecule needs the halogen revision yet, so callers should pass plain MW.
    """
    return W["w1"] + W["w2"] * molar_mass + W["w3"] * c_in + W["w4"] * c_de


def nitramine_correction(n_n_no2: int) -> tuple[float, float]:
    """Sec. 3.2: for 5-membered-or-larger cyclic nitramines with only N-NO2 fragments, and for acyclic
    nitramines, C = 1.75*n_(N-NO2) - 4. Returns (c_in, c_de): C feeds CIn when >=0, CDe (as a positive
    magnitude) when negative -- the paper states the sign determines which slot the same value fills,
    not that both are computed independently."""
    c = 1.75 * n_n_no2 - 4
    return (c, 0.0) if c >= 0 else (0.0, -c)


def nitroaromatic_correction(*, n_nh2: int = 0, n_cooh: int = 0, n_two_oh: int = 0, n_carbonyl: int = 0,
                              n_r_over_no2: float = 0.0, bulky_alkyl_count: int = 0) -> tuple[float, float]:
    """Sec. 3.1: nitroaromatic CIn/CDe rules.

    CIn: nNH2 amino groups (Sec 3.1.1(ii), CIn=n_NH2 -- e.g. TATB, CIn=3); COOH or two separated
    hydroxyls (CIn=2.0, Sec 3.1.1(i)); ring carbonyl as amide/ketone (CIn=0.75, Sec 3.1.1(iii)). At most
    one of these is expected on a single molecule in this corpus; if more than one genuinely applies,
    sum them (the paper does not explicitly forbid combination the way it does for the condensed-Hf
    sister model's "lower value" rule).

    CDe: alkyl substituents, only when n_R/n_NO2 >= 1 (Sec 3.1.2) -- TNT's own ratio (1 methyl / 3 nitro
    = 0.33) does NOT meet this threshold, so TNT gets CDe=0 despite having a methyl group; this is a
    real, checked feature of the rule, not an oversight.
    """
    c_in = 0.0
    if n_nh2 > 0:
        c_in += n_nh2
    if n_cooh > 0 or n_two_oh > 0:
        c_in += 2.0
    if n_carbonyl > 0:
        c_in += 0.75

    c_de = 0.0
    if n_r_over_no2 >= 1 and bulky_alkyl_count >= 0:
        c_de = 1.0 if bulky_alkyl_count == 0 else (2.0 if bulky_alkyl_count == 1 else 3.0)

    return c_in, c_de


#: Sec. 3.3: nitroaliphatic compounds get a flat CDe = 3.0, no CIn.
NITROALIPHATIC_CDE = 3.0
