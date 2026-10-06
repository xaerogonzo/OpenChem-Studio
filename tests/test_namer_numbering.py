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
# the principal characteristic group (P-14.4 (c)) never got to choose between the
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
    # a different element on each, so they write different text. P-23.3.2.2
    # puts the senior element (O) on the lower locant; this was 12/12 by spelling.
    ("C1OC2CC1NC2", "2-oxa-5-azabicyclo[2.2.1]heptane"),
    # Cocaine as the report wrote it (PubChem's SMILES): the acid at 2 and the benzoyloxy at 3 in every spelling. The ester parent is
    # round 25's (the azabicyclo acid outranks benzoic acid), the numbering this change's; the name read back stereo-exact by InChIKey.
    ("CN1[C@H]2CC[C@@H]1[C@@H]([C@H](C2)OC(=O)C3=CC=CC=C3)C(=O)OC",
     "methyl (1R,2S,3S,5S)-3-(benzoyloxy)-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylate"),
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

    9-azabicyclo[3.3.1]non-1-ene has two numberings whose bond is cited
    differently: `1` in one, `1(8)` in the other. Pinning both let the strategy
    layer pick the second for a chlorine beside the bridgehead while the text
    said `non-1-ene`, which OPSIN reads as the chlorine ON the alkene carbon: a
    different molecule. Measured before the comparison existed: 12 of 24
    spellings. Since the unsaturation tier ranks a single locant above a compound
    one (P-31.1.4.2, `test_a_single_locant_outranks_a_compound_one_for_a_double_bond`)
    those two no longer tie, so the name is now one, `8-chloro-...non-1-ene`, and
    this keeps the read-back as the thing that must not vary. The comparison
    itself stays as a safety net for a tie the score cannot see (an aromatic bond
    in a bridged ring is read from the Kekule form by the name and not by the score).
    """
    from py2opsin import py2opsin

    smiles = "N1C2CCC=C1C(Cl)CC2"
    want = Chem.MolToSmiles(Chem.MolFromSmiles(smiles))
    names = {name_smiles(spelling) for spelling in _many_spellings(smiles)}
    assert names == {"8-chloro-9-azabicyclo[3.3.1]non-1-ene"}
    for name in sorted(names):
        back = py2opsin(name, output_format="SMILES")
        assert back, f"{name!r} did not parse back at all"
        assert Chem.MolToSmiles(Chem.MolFromSmiles(back)) == want, (name, back)


# ---------------------------------------------------------------------------
# P-14.4 (j): a tie on every locant goes to the preferred stereodescriptor
# ---------------------------------------------------------------------------
# The two numberings of a meso compound differ in nothing but their CIP labels, so nothing scored them differently and the later-generated plan
# won: the book's own example, `(2R,4S)-2,4-difluoropentane`, was `(2S,4R)` for 9 of 16 spellings, and tropane, cis-1,3-dibromocyclohexane,
# meso-2,3-dibromobutane and a handful of census structures split the same way. P-14.4 (j), the last criterion of the numbering list, gives the
# lower locant to the descriptor Z, R, M or r over E, S, P or s, compared from the lowest locant up (the first point of difference).
# Each case is named from 24 spellings (random roots and random atom orders) and read back stereo-exact except tropine, whose pseudoasymmetric
# 3r OPSIN cannot read, so the engine drops it (KNOWN_LIMITATIONS): that row pins only which way the two labels it keeps are written.
MESO_CASES = [
    # The book's two examples for (j), verbatim.
    ("C[C@H](F)C[C@@H](C)F", "(2R,4S)-2,4-difluoropentane"),
    ("OC(=O)/C=C\\C/C=C/C(O)=O", "(2Z,5E)-hepta-2,5-dienedioic acid"),
    # The same rule on a chain, a monocycle and a suffix with NO prefix at all (the tie-break used to give up when there was no prefix to compare).
    ("C[C@H](Br)[C@@H](C)Br", "(2R,3S)-2,3-dibromobutane"),
    ("C[C@H](O)[C@@H](C)O", "(2R,3S)-butane-2,3-diol"),
    ("C[C@H]1CCCC[C@H]1C", "(1R,2S)-1,2-dimethylcyclohexane"),
    ("Br[C@H]1CCC[C@@H](Br)C1", "(1R,3S)-1,3-dibromocyclohexane"),
    # Von Baeyer skeletons, where it was first seen: tropane, and three census structures.
    ("CN1[C@H]2CC[C@@H]1C[C@H](O)C2", "(1R,5S)-8-methyl-8-azabicyclo[3.2.1]octan-3-ol"),
    ("O=C(NN1C(=O)[C@@H]2[C@H](C1=O)[C@H]1C=C[C@@H]2C1)[C@H](O)c1ccccc1",
     "(1R,2R,6S,7S)-4-[(2R)-2-hydroxy-2-phenylacetamido]-4-azatricyclo[5.2.1.0^{2,6}]dec-8-ene-3,5-dione"),
    ("OC1[C@H]2CCC[C@@H]1[C@H](c1ccccc1)N[C@@H]2c1ccccc1",
     "(1R,2R,4S,5S)-2,4-diphenyl-3-azabicyclo[3.3.1]nonan-9-ol"),
    ("CC[C@H](C)OC(=O)[C@@H]1[C@@H]2C=C[C@@H]([C@H]3C[C@@H]23)[C@H]1C(=O)OCC(=O)c1ccccc1",
     "(2S)-butan-2-yl 2-oxo-2-phenylethyl (1R,2R,4S,5S,8R,9R)-tricyclo[3.2.2.0^{2,4}]non-6-ene-8,9-dicarboxylate"),
]


@pytest.mark.parametrize("smiles,expected", MESO_CASES, ids=[c[1][:60] for c in MESO_CASES])
def test_a_tie_on_every_locant_goes_to_the_preferred_stereodescriptor(smiles, expected):
    assert name_smiles(smiles) == expected
    for spelling in _many_spellings(smiles):
        assert name_smiles(spelling) == expected, spelling


# ---------------------------------------------------------------------------
# P-31.1.4.2: a single locant outranks a compound one for a double bond
# ---------------------------------------------------------------------------
# A bond between non-consecutive locants is cited at its lower locant AND at its higher one in parentheses, a COMPOUND locant, `1(8)`. P-31.1.4.2
# ranks, in order, (1) the fewest compound locants, (2) the lowest locants with the parenthesised ones ignored, (3) all of them. So the book's own
# example is `bicyclo[4.2.0]oct-6-ene (PIN)`, not `oct-1(8)-ene`, although 1 is lower than 6. The engine ranked by the lower locant alone, and on
# a carbocycle the name text came from one numbering and the substituent locants from another: three of these five were a WRONG MOLECULE or
# unreadable (`7-methylbicyclo[4.2.0]oct-1(8)-ene`, `1-chloro...oct-1(8)-ene`, `2-chlorobicyclo[3.3.1]non-1-ene`).
BRIDGEHEAD_ENE_CASES = [
    ("C1CCC2=CCC2C1", "bicyclo[4.2.0]oct-6-ene"),
    ("C1CCC2=C(C)CC2C1", "7-methylbicyclo[4.2.0]oct-6-ene"),
    ("C1CCC2=CCC2(Cl)C1", "1-chlorobicyclo[4.2.0]oct-6-ene"),
    ("C1C2CCC=C1C(Cl)CC2", "8-chlorobicyclo[3.3.1]non-1-ene"),
    ("N1C2CCC=C1C(Cl)CC2", "8-chloro-9-azabicyclo[3.3.1]non-1-ene"),
    # A suffix OUTRANKS the ene locants (P-14.4 (c) before (e)), so it can force the compound numbering: `-7-ol` needs the alkene cited `1(8)`.
    ("C1CCC2=CC(O)C2C1", "bicyclo[4.2.0]oct-1(8)-en-7-ol"),
    # A bond from a bridgehead to the one-atom bridge is compound from BOTH bridgeheads, so the name text is baked as `oct-1(8)-ene`; with the
    # hydroxy beside the other bridgehead, -6-ol needs that bridgehead as C1 and the bond becomes `5(8)`. The engine rewrote only a plain locant,
    # left `oct-1(8)-en-6-ol`, and named a different molecule.
    ("C1(=C2)CCCC2CC1O", "bicyclo[3.2.1]oct-5(8)-en-6-ol"),
    ("C1(=C2)CCCC2C(O)C1", "bicyclo[3.2.1]oct-1(8)-en-6-ol"),
]


@pytest.mark.parametrize("smiles,expected", BRIDGEHEAD_ENE_CASES, ids=[c[1] for c in BRIDGEHEAD_ENE_CASES])
def test_a_single_locant_outranks_a_compound_one_for_a_double_bond(smiles, expected):
    assert name_smiles(smiles) == expected
    for spelling in _many_spellings(smiles):
        assert name_smiles(spelling) == expected, spelling


@pytest.mark.parametrize("smiles,expected", BRIDGEHEAD_ENE_CASES, ids=[c[1] for c in BRIDGEHEAD_ENE_CASES])
def test_a_bridgehead_alkene_name_reads_back(smiles, expected):
    """The name's `-ene` locant must follow the numbering the substituents were given."""
    from py2opsin import py2opsin

    back = py2opsin(name_smiles(smiles), output_format="SMILES")
    assert back, f"{expected!r} did not parse back at all"
    assert Chem.MolToSmiles(Chem.MolFromSmiles(back)) == Chem.MolToSmiles(Chem.MolFromSmiles(smiles)), (expected, back)
