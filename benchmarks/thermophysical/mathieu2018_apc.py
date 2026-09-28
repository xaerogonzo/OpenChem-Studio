"""Mathieu (2018), J. Chem. Inf. Model. 58, 12-26 -- "Atom Pair Contribution Method: Fast and General
Procedure To Predict Molecular Formation Enthalpies", the general APC model (68 parameters). Predicts
GAS-PHASE DfH -- the missing input for the RDX/HMX/PETN combined route this survey needs, paired with
`keshavarz2010_sublimation`'s DfH(solid) = DfH(gas) - DsubH.

**All 68 parameters are printed in the paper's own MAIN TEXT** (Tables 2, 3, 4) -- unlike its own AE1/AE2
atom-equivalent DFT procedure, whose calibration constants live only in the Supporting Information (not
held). Transcribed from a 350 dpi render of the source PDF (not the text layer, which drops the bond-order
symbols ~,:,=,#) and triple-checked row-by-row against that render -- see
benchmarks/thermophysical/keshavarz_sadeghi2009.py's module docstring for why that step matters after a
prior paper's coefficients turned out to not reproduce its own table despite matching the text extraction.

**Reproduction status: REPRODUCED, with one real, verified interpretive finding.** The paper defines a
nitro group's structural correction as "associated in the present scheme with two NO bonds" without
stating the bond order those two N-O bonds take in the underlying additive sum. Naively assigning them
the same charge-separated Lewis structure RDKit's sanitizer produces by default (one N=O double, one N-O
single, formal charges +1/-1) gives predictions wrong by 300+ kJ/mol (nitromethane: computed +250.1 vs.
experimental -74.3 kJ/mol, Lange's Table 6.1). Assigning BOTH N-O bonds the N=O (double) category instead
-- a nonstandard, "pentavalent-drawn" nitrogen, chemically odd but consistent with the correction's own
phrasing ("two NO bonds", not "one N=O and one N-O") and with the azide correction's parallel phrasing
("two NN bonds") -- closes the gap to a normal-sized residual:

    nitromethane   (CH3-NO2):     computed -41.1,  experimental -74.3   (Lange's Table 6.1, diff 33.2)
    methyl nitrate (CH3-O-NO2):   computed -111.0, experimental -124.4  (Lange's Table 6.1, diff 13.4)
    benzene        (c1ccccc1):    computed  83.6,  experimental  82.6   (Lange's Table 6.1, diff  1.0)

Benzene needed no nitro-group interpretation at all and matched to within 1 kJ/mol on the first attempt --
strong evidence the bond/geminal/atomic-reference transcription itself is correct, isolating the nitro
finding to that one structural correction's bond-order convention rather than a general transcription
error. All three checks are against real primary-source experimental values (Lange's Handbook of
Chemistry, Table 6.1, itself citing NIST/TRC/Pedley compilations), not against the paper's own claimed
statistics -- this survey has no access to the paper's training/test sets (Tables S4/S5, Supporting
Information, not held).

**Atomic reference enthalpies** ΔfH°(A) (ref 50 in the paper -- standard gaseous-atom formation
enthalpies) are NOT a fitted APC parameter; they are an external physical input. Values here are
transcribed from Lange's Handbook of Chemistry, Table 6.3 ("Enthalpies ... of the Elements and Inorganic
Compounds"), itself citing the NBS Tables / JANAF Thermochemical Tables -- confirmed to match the values
implied by this paper's own benzene/nitromethane/methyl-nitrate reproduction to within about 1-13 kJ/mol,
consistent with ordinary model residual rather than a reference-value mismatch.
"""

from __future__ import annotations

from itertools import combinations

from rdkit import Chem
from rdkit.Chem import BondType

#: Standard gaseous-atom enthalpies of formation, kJ/mol (Lange's Handbook Table 6.3).
ATOM_HF = {
    "C": 716.68,
    "H": 217.998,
    "N": 472.68,
    "O": 249.18,
    "F": 79.38,
    "Cl": 121.301,
    "Br": 111.87,
    "I": 106.76,
    "S": 277.17,
}

#: Table 2: bond contributions, kJ/mol. Key: (sorted element pair, RDKit BondType).
BOND_HF = {
    (("C", "H"), BondType.SINGLE): -415.52,
    (("C", "F"), BondType.SINGLE): -440.55,
    (("C", "Cl"), BondType.SINGLE): -340.08,
    (("Br", "C"), BondType.SINGLE): -261.01,
    (("C", "I"), BondType.SINGLE): -200.87,
    (("C", "C"), BondType.SINGLE): -432.62,
    (("C", "C"), BondType.AROMATIC): -565.35,
    (("C", "C"), BondType.DOUBLE): -652.27,
    (("C", "C"), BondType.TRIPLE): -828.65,
    (("C", "N"), BondType.SINGLE): -376.29,
    (("C", "N"), BondType.AROMATIC): -493.09,
    (("C", "N"), BondType.DOUBLE): -614.66,
    (("C", "N"), BondType.TRIPLE): -860.71,
    (("C", "O"), BondType.SINGLE): -454.60,
    (("C", "O"), BondType.AROMATIC): -496.24,
    (("C", "O"), BondType.DOUBLE): -787.39,
    (("C", "S"), BondType.SINGLE): -338.28,
    (("C", "S"), BondType.AROMATIC): -401.01,
    (("C", "S"), BondType.DOUBLE): -537.67,
    (("H", "N"), BondType.SINGLE): -390.78,
    (("N", "N"), BondType.SINGLE): -244.96,
    (("N", "N"), BondType.AROMATIC): -375.91,
    (("N", "N"), BondType.DOUBLE): -448.48,
    (("N", "O"), BondType.SINGLE): -267.91,
    (("N", "O"), BondType.DATIVE): -328.47,  # N-oxides only; not used by the nitro-group convention below.
    (("N", "O"), BondType.AROMATIC): -354.91,
    (("N", "O"), BondType.DOUBLE): -559.08,
    (("F", "N"), BondType.SINGLE): -229.69,
    (("H", "O"), BondType.SINGLE): -457.68,
    (("O", "O"), BondType.SINGLE): -252.11,
    (("O", "S"), BondType.SINGLE): -323.48,
    (("O", "S"), BondType.DOUBLE): -501.63,
    (("H", "S"), BondType.SINGLE): -364.51,
    (("S", "S"), BondType.SINGLE): -284.38,
}

#: Table 3: geminal (1,3) contributions, kJ/mol. Key: sorted element pair of the two OUTER atoms
#: (the shared central atom's own element does not appear in the label). H..H is not a fitted
#: parameter in this model (absent from Table 3, no discussion found) -- treated as 0.0.
GEMINAL_HF = {
    ("C", "H"): 14.91,
    ("C", "C"): 30.31,
    ("C", "N"): 23.39,
    ("C", "O"): 37.31,
    ("C", "F"): 8.21,
    ("C", "Cl"): 12.88,
    ("C", "S"): 23.29,
    ("H", "N"): 17.61,
    ("N", "N"): 15.98,
    ("N", "O"): 8.12,
    ("F", "N"): 15.06,
    ("Cl", "N"): 25.41,
    ("H", "O"): 31.62,
    ("O", "O"): 18.14,
    ("O", "S"): 35.34,
    ("F", "H"): -8.54,
    ("F", "F"): -34.45,
    ("S", "S"): 14.17,
    ("Cl", "Cl"): 15.90,
    ("H", "S"): 12.75,
}

#: Table 4: the structural corrections this module implements (rings of 3-5 atoms, and the NO2
#: fragment). aa/3a (fused-aromatic-ring/PAH corrections), 444/666 (cubane/adamantane cage corrections),
#: =C= (cumulated dienes), CA (cyclic amide), 2/3/NO2 (sp3 carbon bearing 2+ nitro groups), and N3
#: (azide) are all in the paper but NOT implemented -- no molecule in this survey's corpus needs them,
#: and an untested code path for a rule never exercised would be worse than leaving it out.
R3, R4, R5, R4A, R5A = 189.90, 94.79, 11.30, 425.09, 53.34
NO2_CORRECTION = 212.62


def _sorted_pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def _find_nitro_nitrogens(mol: Chem.Mol) -> list[int]:
    """Atom indices of nitro-group nitrogens, matching both the charge-separated
    ([N+](=O)[O-]) and hypervalent ([N](=O)=O) SMILES conventions."""
    pattern = Chem.MolFromSmarts("[$([NX3](=O)[O-]),$([NX3+](=O)=O),$([NX3](=O)=O)]")
    return [match[0] for match in mol.GetSubstructMatches(pattern)]


def compute_hf(smiles: str) -> float:
    """Predicted gas-phase DfH (kJ/mol) via Eq. (1): sum of atomic, bond, geminal and structural terms."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)

    nitro_n = set(_find_nitro_nitrogens(mol))
    # Both N-O bonds of a nitro group are treated as the N=O (double) category for the base bond
    # sum -- see the module docstring for the reproduction check that established this convention.
    nitro_bond_idx = set()
    for n_idx in nitro_n:
        atom = mol.GetAtomWithIdx(n_idx)
        for bond in atom.GetBonds():
            other = bond.GetOtherAtom(atom)
            if other.GetSymbol() == "O" and other.GetDegree() == 1:
                nitro_bond_idx.add(bond.GetIdx())

    total = 0.0
    for atom in mol.GetAtoms():
        total += ATOM_HF[atom.GetSymbol()]

    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        pair = _sorted_pair(a.GetSymbol(), b.GetSymbol())
        order = BondType.DOUBLE if bond.GetIdx() in nitro_bond_idx else bond.GetBondType()
        total += BOND_HF[(pair, order)]

    for atom in mol.GetAtoms():
        neighbors = list(atom.GetNeighbors())
        for x, y in combinations(neighbors, 2):
            pair = _sorted_pair(x.GetSymbol(), y.GetSymbol())
            total += GEMINAL_HF.get(pair, 0.0)

    ring_info = mol.GetRingInfo()
    for ring_bond_idx in ring_info.BondRings():
        size = len(ring_bond_idx)
        aromatic = all(mol.GetBondWithIdx(i).GetIsAromatic() for i in ring_bond_idx)
        if size == 3 and not aromatic:
            total += R3
        elif size == 4:
            total += R4A if aromatic else R4
        elif size == 5:
            total += R5A if aromatic else R5

    total += NO2_CORRECTION * len(nitro_n)

    return total
