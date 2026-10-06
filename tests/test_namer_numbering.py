"""Naming round 5 (N7): a numbering choice must not depend on how the
structure was written.

The hydro-orientation defect (D-092) was a TIE broken by enumeration order,
which is exactly the kind of choice that moves when the input's atom order
does. Each N7 case is named from shuffled atom orders, a Kekule SMILES and
randomly rooted SMILES, and must come out identical every time.
"""
from __future__ import annotations

import random

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

CASES = [
    ("OC(=O)C1=CCNCC1", "1,2,3,6-tetrahydropyridine-4-carboxylic acid"),
    ("CN1CCC(=CC1)c1ccccc1", "1-methyl-4-phenyl-1,2,3,6-tetrahydropyridine"),
    ("OC(=O)CN1CC=CC=C1", "(pyridin-1(2H)-yl)acetic acid"),
    ("OC(=O)CN1CC=CC(Cl)=C1", "(5-chloropyridin-1(2H)-yl)acetic acid"),
    ("OC1=CCCNC1", "1,2,5,6-tetrahydropyridin-3-ol"),
]


def _spellings(smiles: str) -> list[str]:
    mol = Chem.MolFromSmiles(smiles)
    rng = random.Random(20260919)
    out = []
    for _ in range(4):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        out.append(Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False))
    kek = Chem.Mol(mol)
    Chem.Kekulize(kek, clearAromaticFlags=True)
    out.append(Chem.MolToSmiles(kek, kekuleSmiles=True))
    out.append(Chem.MolToSmiles(mol))
    for seed in (1, 2, 3):
        Chem.rdBase.SeedRandomNumberGenerator(seed)
        out.append(Chem.MolToSmiles(mol, doRandom=True, canonical=False))
    return out


@pytest.mark.parametrize("smiles,expected", CASES, ids=[c[1] for c in CASES])
def test_the_numbering_does_not_depend_on_how_it_was_written(smiles, expected):
    assert name_smiles(smiles) == expected
    for spelling in _spellings(smiles):
        assert name_smiles(spelling) == expected, spelling


# ---------------------------------------------------------------------------
# Von Baeyer: a TIE between numberings belongs to the strategy layer
# ---------------------------------------------------------------------------
# Found in naming round 25 (8-azabicyclo[3.2.1]octane carboxylic acids came out
# `-2-` or `-4-` by SMILES atom order). `name_bridged` pinned ONE numbering for
# every ring with a heteroatom, chosen by "first generated wins" on a tie, so
# the principal characteristic group (P-31.1.4) never got to choose between the
# two mirror numberings of a symmetric skeleton. All of these read back to the
# input as written, so only the TIE-BREAK was wrong, and the corpora cannot see
# that: the right name needs a symmetric skeleton AND a substituent on it.
#
# Each case is named from 24 spellings (random roots and random atom orders);
# the old behaviour split roughly 40/60 on every one of them.
VB_TIE_CASES = [
    # The reported pair: acid at 2, not 4 (hydroxy takes the remaining 3).
    ("OC(=O)C1C2CCC(CC1O)N2C",
     "3-hydroxy-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylic acid"),
    # Its stereo twin: the descriptors follow the numbering, so they split too
    # (1S,3S,4S,5R vs 1R,... in the old output). Read back stereo-exact.
    ("CN1[C@@H]2CC[C@H]1[C@H]([C@H](C2)O)C(=O)O",
     "(1S,2R,3S,5R)-3-hydroxy-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylic acid"),
    # A 2.2.2 cage: the old output was -3-ol, -5-ol or -8-ol, by spelling.
    ("OC1CN2CCC1CC2", "1-azabicyclo[2.2.2]octan-3-ol"),
    # Two substituents, and a 2.2.1 skeleton with TWO equal bridges to permute.
    ("OC(=O)C1CC2C(C(=O)O)CC1N2", "7-azabicyclo[2.2.1]heptane-2,5-dicarboxylic acid"),
    ("OC(=O)C1CC2CCC1N2C(=O)O", "7-azabicyclo[2.2.1]heptane-2,7-dicarboxylic acid"),
    # An unsaturated hetero-bicycle: the ene is at 6 either way, the acid is the tie.
    ("OC(=O)C1C2C=CC(N2)CC1O", "3-hydroxy-8-azabicyclo[3.2.1]oct-6-ene-2-carboxylic acid"),
    # NOT a substituent tie: two numberings with the same heteroatom LOCANTS but
    # a different element on each, so they write different text. P-31.1.4.2.4
    # puts the senior element (O) on the lower locant; this was 12/12 by spelling.
    ("C1OC2CC1NC2", "2-oxa-5-azabicyclo[2.2.1]heptane"),
]


def _many_spellings(smiles: str, n: int = 24) -> list[str]:
    """Random-root SMILES and random atom renumberings: both move the atom order."""
    mol = Chem.MolFromSmiles(smiles)
    rng = random.Random(20261005)
    out = []
    for i in range(n):
        if i % 2 == 0:
            Chem.rdBase.SeedRandomNumberGenerator(1000 + i)
            out.append(Chem.MolToSmiles(mol, doRandom=True))
        else:
            order = list(range(mol.GetNumAtoms()))
            rng.shuffle(order)
            out.append(Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False))
    return out


@pytest.mark.parametrize("smiles,expected", VB_TIE_CASES, ids=[c[1] for c in VB_TIE_CASES])
def test_a_von_baeyer_tie_is_broken_by_locants_not_by_atom_order(smiles, expected):
    assert name_smiles(smiles) == expected
    for spelling in _many_spellings(smiles):
        assert name_smiles(spelling) == expected, spelling


def test_a_tied_numbering_is_never_paired_with_text_it_did_not_write():
    """The pin may hold only the numberings that write the SAME ring text.

    9-azabicyclo[3.3.1]non-1-ene has two numberings that tie on every score
    (the alkene's lower locant is 1 in both) but cite the bond differently:
    `1` in one, `1(8)` in the other. Pinning both let the strategy layer pick
    the second for a chlorine beside the bridgehead while the text said
    `non-1-ene`, which OPSIN reads as the chlorine ON the alkene carbon: a
    different molecule. Measured before the filter existed: 12 of 24
    spellings. The names legitimately differ by spelling here (`2-chloro-...
    non-1(8)-ene` or `8-chloro-...non-1-ene`, an open tie in the unsaturation
    tier, which ranks by the lower locant only), so this asserts the one
    thing that must not vary: every name reads back to the input.
    """
    from py2opsin import py2opsin

    smiles = "N1C2CCC=C1C(Cl)CC2"
    want = Chem.MolToSmiles(Chem.MolFromSmiles(smiles))
    names = {name_smiles(spelling) for spelling in _many_spellings(smiles)}
    for name in sorted(names):
        back = py2opsin(name, output_format="SMILES")
        assert back, f"{name!r} did not parse back at all"
        assert Chem.MolToSmiles(Chem.MolFromSmiles(back)) == want, (name, back)
