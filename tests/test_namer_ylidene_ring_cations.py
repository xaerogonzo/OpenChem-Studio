"""Naming round 36 (D-209): a ring cation with an exocyclic C=C on a ring carbon keeps its hydro prefixes.

`C=C1CCC[NH+]=C1` was `5-methylideneazinan-1-ium`, the SATURATED piperidinium: a different molecule. `retained_lookup._try_derive_hydro_retained` finds the hydro positions of a
partly saturated ring of a retained parent, and it counted a ring carbon holding an exocyclic double bond as an sp2 ring member (as it must for the ring's own double bonds). The
ylidene carbon is a hydro position, as in the neutral `3-methylidene-3,4,5,6-tetrahydropyridine`; counted as sp2 it left an odd number of positions and the derivation gave up,
so the cation fell to the saturated ring. The neutral ring never showed it: a curated `3,4,5,6-tetrahydropyridine` entry matches it with the ylidene as a substituent.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    ("protonated 3-methylidene-tetrahydropyridine", "C=C1CCC[NH+]=C1", "5-methylidene-2,3,4,5-tetrahydropyridin-1-ium"),
    ("an isopropylidene", "CC(C)=C1CCC[NH+]=C1", "5-(propan-2-ylidene)-2,3,4,5-tetrahydropyridin-1-ium"),
    ("its N-methyl iminium", "C=C1CCC[N+](C)=C1", "1-methyl-5-methylidene-2,3,4,5-tetrahydropyridin-1-ium"),
    ("a ylidene beside a ring double bond", "C=C1C=C[NH+]=CC1", "4-methylidene-3,4-dihydropyridin-1-ium"),
]

# Names that existed before keep them: the neutral ring, a ylidene on a saturated ring, on a carbocycle, and the five ring cation.
UNCHANGED = [
    ("the neutral ring", "C=C1CCCN=C1", "3-methylidene-3,4,5,6-tetrahydropyridine"),
    ("a ylidene on a piperidinium", "C=C1CCC[NH2+]C1", "3-methylidenepiperidin-1-ium"),
    ("a ylidene on a tetralin", "C=C1CCCc2ccccc21", "1-methylidene-1,2,3,4-tetrahydronaphthalene"),
    ("an oxo ring cation (the carbonyl is no ylidene)", "O=C1CCC[NH+]=C1", "5-oxo-2,3-dihydropyridin-1-ium"),
    ("the five ring cation", "C=C1CC[NH+]=C1", "4-methylidene-3,4-dihydro-2H-azol-1-ium"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_ring_cation_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_ylidene_cation_is_not_the_saturated_ring():
    assert name_smiles("C=C1CCC[NH+]=C1") != "5-methylideneazinan-1-ium"
