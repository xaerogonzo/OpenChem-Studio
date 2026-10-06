"""Naming round 25: stereo that was dropped for four natural products, and a diester name that depended on SMILES atom order.

* atropine / scopolamine: the engine writes pseudoasymmetric `3r`/`7s`, which OPSIN cannot read, and the validator then stripped EVERY
  R/S on the bridged parent. It now strips only the lowercase ones first (`pseudoasymmetric` mode), so OPSIN-readable `(1R,5S)` stays.
  The names still carry the "does not express stereochemistry" note, correctly: tropine and pseudotropine differ only at C3.
* galantamine: the curated table had 8a and 12a swapped (found with OPSIN chloro probes), so `12aR` was unparseable and both junction
  descriptors were dropped.
* ibogaine: a bridged system named by FUSION numbers its junctions with letters; the gate admitted only plain integers.
* diesters: which ester is the principal anion followed atom order. Now the senior acid (P-65.6.3.3.3.2 method 2), then the lowest locants
  of the alcohol component (free valence first, then prefixes; P-31.1.4) on executed names, then RDKit's canonical class rank.
"""
import pytest
from rdkit import Chem, rdBase

from openchem.chem.naming_providers import derived_name_for_structure, opsin_available
from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

STEREO = [
    ("galantamine", "CN1CC[C@]23C=C[C@@H](C[C@@H]2OC4=C(C=CC(=C34)C1)OC)O",
     "(4aS,6R,8aR)-3-methoxy-11-methyl-4a,5,9,10,11,12-hexahydro-6H-[1]benzofuro[3a,3,2-ef][2]benzazepin-6-ol", False),
    ("ibogaine", "CC[C@H]1C[C@H]2C[C@@H]3[C@H]1N(C2)CCc1c3[nH]c2ccc(OC)cc12",
     "(6R,6aS,7S,9S)-7-ethyl-2-methoxy-5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole", False),
    ("atropine", "CN1[C@H]2CC[C@@H]1C[C@@H](C2)OC(=O)C(CO)c1ccccc1",
     "(1R,5S)-8-methyl-8-azabicyclo[3.2.1]octan-3-yl 3-hydroxy-2-phenylpropanoate", True),
    ("scopolamine", "CN1[C@H]2C[C@H](OC(=O)[C@H](CO)c3ccccc3)C[C@@H]1[C@H]1O[C@@H]21",
     "(1R,2R,4S,5S)-9-methyl-3-oxa-9-azatricyclo[3.3.1.0^{2,4}]nonan-7-yl (2S)-3-hydroxy-2-phenylpropanoate", True),
]


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected,partial", STEREO, ids=[s[0] for s in STEREO])
def test_stereo_kept_where_opsin_can_read_it(label, smiles, expected, partial):
    result = derived_name_for_structure(Chem.MolFromSmiles(smiles))
    assert result.name == expected
    # the two tropanes omit the pseudoasymmetric centre and SAY so; the other two read back exactly
    assert bool(result.note) is partial
    if partial:
        assert "does not express stereochemistry" in result.note


DIESTERS = [
    # one acid twice: a single name whichever way the SMILES is written, and the lower locants win (`propyl`, not `propan-2-yl`)
    ("CC(=O)OC1CCC(OC(C)=O)CC1C", "4-(acetyloxy)-2-methylcyclohexyl acetate"),
    ("CC(=O)Oc1ccc(OC(C)=O)cc1C", "4-(acetyloxy)-2-methylphenyl acetate"),
    ("CC(=O)OCC(C)OC(C)=O", "2-(acetyloxy)propyl acetate"),
    ("CC(=O)OC(C)CCOC(C)=O", "3-(acetyloxy)butyl acetate"),
    # two acids: the senior (longer) one is the principal anion, P-65.6.3.3.3.2 method 2
    ("CCC(=O)OCCCOC(C)=O", "3-(acetyloxy)propyl propanoate"),
    ("CC(=O)OCCOC(=O)CCC", "2-(acetyloxy)ethyl butanoate"),
]


@pytest.mark.parametrize("smiles,expected", DIESTERS)
def test_a_diester_is_named_the_same_whatever_order_its_atoms_are_written_in(smiles, expected):
    rdBase.SeedRandomNumberGenerator(20261005)
    mol = Chem.MolFromSmiles(smiles)
    names = {name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(12)}
    assert names == {expected}


def test_heroin_is_one_name_in_every_atom_order():
    rdBase.SeedRandomNumberGenerator(20261005)
    mol = Chem.MolFromSmiles("CC(=O)O[C@H]1C=C[C@H]2[C@H]3Cc4ccc(OC(C)=O)c5O[C@@H]1[C@]2(CCN3C)c45")
    names = {name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(10)}
    assert len(names) == 1


def test_the_lowest_locant_ester_wins_where_a_canonical_rank_alone_did_not():
    # heldout_v4 h4cid52750 (a tuning row): the alcohol component's attachment locant is 2 in one reading and 3 in the other
    smiles = "S=C=NCC(OC(C)=O)C(OC(C)=O)C(OC(C)=O)C(OC(C)=O)CN=C=S"
    assert name_smiles(smiles) == "3,4,5-tris(acetyloxy)-1,6-diisothiocyanatohexan-2-yl acetate"


RULES = [
    # the senior ACID is the principal anion: a ring carboxylic acid before an acetic-acid chain (P-44.1.2.2), whichever alcohol it carries
    ("CCOC(=O)Cc1ccc(C(=O)OC)cc1", "methyl 4-(2-ethoxy-2-oxoethyl)benzoate"),
    ("COC(=O)Cc1ccc(C(=O)OCC)cc1", "ethyl 4-(2-methoxy-2-oxoethyl)benzoate"),
    # locants compare only within one parent: a ring parent for the alcohol component before a chain parent
    ("CC(=O)OCC1CCCC(OC(C)=O)C1", "3-[(acetyloxy)methyl]cyclohexyl acetate"),
    # a well-formed poly-ester reading (P-65.6.3.3.2) is the answer; the single-ester readings only compete when it is not
    ("COC(=O)CCC(=O)OC", "dimethyl butanedioate"),
    ("CCOC(=O)CCC(=O)OC", "ethyl methyl butanedioate"),
]


@pytest.mark.parametrize("smiles,expected", RULES)
def test_the_principal_ester_follows_the_acid_then_the_alcohol(smiles, expected):
    rdBase.SeedRandomNumberGenerator(20261005)
    mol = Chem.MolFromSmiles(smiles)
    assert {name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(12)} == {expected}


def test_more_tied_esters_than_the_tie_break_will_execute_keep_one_name():
    # five acetates on one chain: past the four the tie-break executes, so the canonical class rank alone must make the name atom-order free
    rdBase.SeedRandomNumberGenerator(20261005)
    mol = Chem.MolFromSmiles("CC(=O)OCC(OC(C)=O)C(OC(C)=O)C(OC(C)=O)C(C)OC(C)=O")
    assert len({name_smiles(Chem.MolToSmiles(mol, doRandom=True)) for _ in range(16)}) == 1
