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


def logd_henderson_hasselbalch(logp: float, ph: float, pkas: list[float], is_acid: list[bool]) -> float:
    """logD = logP - log10(1 + sum of ionization terms).

    Only the NEUTRAL species partitions into octanol, so the measured
    distribution coefficient is the partition coefficient reduced by
    however much of the compound is ionized at this pH:

        acid  HA <-> A- + H+   ->  term = 10^(pH - pKa)
        base  B + H+ <-> BH+   ->  term = 10^(pKa - pH)

    Both forms are the standard derivation. Multiple ionizable centres
    contribute additively inside the log, which is the usual
    multi-protic approximation (it assumes independent, non-cooperative
    sites -- true enough for the drug-like molecules this targets, and
    exact for the monoprotic case that dominates in practice).
    """
    total = 0.0
    for pka, acidic in zip(pkas, is_acid):
        exponent = (ph - pka) if acidic else (pka - ph)
        # Clamped: a centre ionized far past its pKa contributes a term so
        # large it overflows float, and the physical answer there is just
        # "essentially fully ionized" -- 10^12 already saturates log10 to
        # within rounding of any larger value.
        total += 10.0 ** min(exponent, 12.0)
    return logp - math.log10(1.0 + total)


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

    # pkasolver returns pKa values but its reaction-centre indices do not
    # map onto our atom numbering (documented in compute_pka), so acid/base
    # character is assigned from the molecule's own matched groups instead:
    # lowest pKa values to acidic centres, highest to basic ones, which is
    # the correct pairing for the overwhelmingly common case of a molecule
    # whose acidic groups are more acidic than its basic groups are.
    ordered = sorted(pka_values)
    is_acid = [True] * min(acids, len(ordered)) + [False] * max(0, len(ordered) - acids)
    return logd_henderson_hasselbalch(Crippen.MolLogP(mol), ph, ordered, is_acid[: len(ordered)])


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
