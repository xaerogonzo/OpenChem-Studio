from __future__ import annotations

import math

from rdkit import Chem
from rdkit.Chem import Crippen

# An ionizable centre is treated as acidic or basic by what it is, since
# Henderson-Hasselbalch takes a different form for each. Verified SMARTS,
# deliberately narrow -- an unmatched centre is skipped rather than
# guessed at, which loses a term instead of inventing one.
_ACID_SMARTS = Chem.MolFromSmarts("[$([CX3](=O)[OX2H1]),$([OX2H1][cX3]),$([SX4](=O)(=O)[OX2H1]),$([PX4](=O)[OX2H1])]")
# Same basic-amine pattern verified across 9 reference molecules in Phase
# 20 (matches verapamil/amitriptyline/di- and triethylamine; excludes
# amides, sulfonamides, aromatic N, and anilines).
_BASE_SMARTS = Chem.MolFromSmarts("[NX3;H2,H1,H0;!$(NC=[O,S]);!$(N=*);!$(NS(=O)=O);!$(Nc);!a]")


def classify_ionizable_centres(mol: Chem.Mol) -> tuple[int, int]:
    """Returns (acidic_count, basic_count) for the molecule -- how many
    Henderson-Hasselbalch terms of each kind apply."""
    acids = len(mol.GetSubstructMatches(_ACID_SMARTS)) if _ACID_SMARTS is not None else 0
    bases = len(mol.GetSubstructMatches(_BASE_SMARTS)) if _BASE_SMARTS is not None else 0
    return acids, bases


#: A pKa outside this range is not a measurement, it is a typo or a
#: predictor that has come apart. Deliberately wider than water's own
#: 0-14 window, because a superacid or a very weak carbon acid really
#: does sit outside it and refusing those would be the wrong error.
_PKA_RANGE = (-20.0, 40.0)


def ionization_log_factor(ph: float, pkas: list[float], is_acid: list[bool]) -> float:
    """log10 of how far ionization moves a property from its neutral value.

        acid  HA <-> A- + H+   ->  term = 10^(pH - pKa)
        base  B + H+ <-> BH+   ->  term = 10^(pKa - pH)

    Sites COMPOSE MULTIPLICATIVELY, so this is `sum(log10(1 + term))` and
    not `log10(1 + sum(term))`.

    **THAT DISTINCTION WAS A REAL BUG, AND THIS FILE HAD IT.** The summed
    form is exact for one site and wrong for more than one: it never
    reaches the doubly-ionized scaling, because reaching that state
    requires BOTH protons to leave and the sum has no term for it.
    Measured on a pKa 3.0/4.5 diacid at pH 8, the sum understates the
    adjustment by **3.49 log units**.

    Avdeef 2007 (Adv Drug Deliv Rev 59:568-590, doi
    10.1016/j.addr.2007.05.008) Table 1 gives the sequential form for a
    diprotic acid as

        log S = log S0 + log{10^(2pH-pKa1-pKa2) + 10^(pH-pKa1) + 1}

    **NEARLY the expanded product, and deliberately not identical to it.**
    The product carries an extra `10^(pH-pKa2)` term, worth 4.3e-6 log at
    pH 8 on a 3.0/4.5 diacid. The two are not meant to coincide: Avdeef's
    constants are MACROSCOPIC, where the singly-ionized species already
    lumps both microstates, while these are per-SITE. `ph_curves` records
    that pkasolver "predicts per-site values, which are closer to
    microscopic constants", so the product is the form that matches the
    inputs this function is given.

    What matters is that both reach the doubly-ionized 10^(2pH) scaling
    and a SUM never does.

    **THE CORRECT MATH WAS ALREADY IN THIS CODEBASE, one module away.**
    `ph_curves.microspecies_fractions` builds the same beta-product from
    successive dissociation constants and has since it was written. Two
    implementations of one piece of chemistry, one right, coexisting --
    which is the argument for this function existing at all.

    Computed in log space rather than as a product, so a molecule with
    many sites cannot overflow a float on the way to a modest answer.

    **`pkas[i]` and `is_acid[i]` are ONE MATCHED SITE.** Order matters
    only through that pairing, and a length mismatch RAISES rather than
    letting `zip` silently drop the tail -- a dropped site is a term
    missing from a sum that still looks perfectly reasonable.

    **THIS IS NOT A GENERAL IONIZATION ENGINE.** It is the independent-site
    HH factor and nothing more. An ampholyte's real speciation is not this
    (see `chem/solubility.py`, which refuses them rather than calling this
    and believing the answer), and neither is a cooperative system's.

    Shared deliberately by logD and solubility, which apply it with
    OPPOSITE SIGN -- ionization removes partitioning and adds solubility:

        logD(pH) = logP     - ionization_log_factor(...)
        logS(pH) = baseline + ionization_log_factor(...)

    One implementation means the two can never drift apart, and a mutation
    to the clamp below is caught by both suites.
    """
    if len(pkas) != len(is_acid):
        raise ValueError(
            f"{len(pkas)} pKa values against {len(is_acid)} acid/base flags -- "
            "each pKa needs exactly one flag saying which it is."
        )
    total = 0.0
    for pka, acidic in zip(pkas, is_acid):
        if not math.isfinite(pka):
            raise ValueError(f"pKa {pka!r} is not a finite number.")
        if not _PKA_RANGE[0] <= pka <= _PKA_RANGE[1]:
            raise ValueError(f"pKa {pka} is outside the plausible range {_PKA_RANGE}.")
        exponent = (ph - pka) if acidic else (pka - ph)
        # Clamped: a centre ionized far past its pKa contributes a term so
        # large it overflows float, and the physical answer there is just
        # "essentially fully ionized" -- 10^12 already saturates log10 to
        # within rounding of any larger value.
        #
        # The log goes INSIDE the sum. That one placement is the whole
        # correction: sites multiply, so their logs add.
        total += math.log10(1.0 + 10.0 ** min(exponent, 12.0))
    return total


def logd_henderson_hasselbalch(logp: float, ph: float, pkas: list[float], is_acid: list[bool]) -> float:
    """logD = logP - the ionization log factor.

    Only the NEUTRAL species partitions into octanol, so the measured
    distribution coefficient is the partition coefficient reduced by
    however much of the compound is ionized at this pH. The reduction is
    `ionization_log_factor` above, which carries the derivation.

    **MONOPROTIC ANSWERS ARE UNCHANGED to the last bit** by the multi-site
    correction -- one site is exactly the case where a sum and a product
    agree. Only molecules with more than one ionizable centre moved, and
    they moved because they were wrong.
    """
    return logp - ionization_log_factor(ph, pkas, is_acid)


def assign_site_polarity(mol: Chem.Mol, pka_values: list[float]) -> tuple[list[float], list[bool]]:
    """Pair each predicted pKa with an acidic or basic centre.

    pkasolver returns pKa values but its reaction-centre indices do not map
    onto our atom numbering (documented in `compute_pka`), so acid/base
    character is assigned from the molecule's OWN matched groups instead:
    lowest pKa values to acidic centres, highest to basic ones, which is
    the correct pairing for the overwhelmingly common case of a molecule
    whose acidic groups are more acidic than its basic groups are.

    Returns `(sorted_pkas, is_acid)`, always the same length, so the pair
    can go straight into `ionization_factor` without tripping its
    length check.

    Extracted so logD and solubility share ONE convention. Two copies of a
    heuristic pairing is two chances for them to disagree about what a
    molecule's second pKa means.
    """
    acids, _bases = classify_ionizable_centres(mol)
    ordered = sorted(pka_values)
    is_acid = [True] * min(acids, len(ordered)) + [False] * max(0, len(ordered) - acids)
    return ordered, is_acid[: len(ordered)]


def logd_from_pkas(mol: Chem.Mol, ph: float, pka_values: list[float]) -> float | None:
    """Real Henderson-Hasselbalch logD, when numeric pKa values are
    available (pkasolver, out of process -- see `chem/pka_providers.py`).

    Each predicted pKa is assigned to an acidic or basic centre by
    matching the molecule's own ionizable groups. Returns `None` when the
    molecule has no recognizable ionizable centre at all, since then
    logD == logP and the caller should say so rather than present an
    identical number as if it were a distinct calculation.
    """
    acids, bases = classify_ionizable_centres(mol)
    if acids == 0 and bases == 0:
        return None

    ordered, is_acid = assign_site_polarity(mol, pka_values)
    return logd_henderson_hasselbalch(Crippen.MolLogP(mol), ph, ordered, is_acid)


def logd_from_microspecies(mol: Chem.Mol, ph: float) -> float:
    """Fallback when no numeric pKa is available: Crippen LogP recomputed
    on the dominant microspecies at `ph` (Dimorphite-DL).

    This is a real pH-dependent number, but it is NOT true
    Henderson-Hasselbalch logD -- it is the LogP of whichever single
    protonation state dominates, with no ensemble weighting, so it steps
    between states rather than varying smoothly through a pKa. Named and
    reported accordingly wherever it is surfaced.
    """
    from openchem.chem.pka_providers import protonate_at_ph

    return Crippen.MolLogP(protonate_at_ph(mol, ph))
