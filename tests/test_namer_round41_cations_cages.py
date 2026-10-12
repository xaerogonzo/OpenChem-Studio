"""Naming round 41 (D-220 .. D-222): ring cations named as their rings, one name per cation, and cages that kept their own numbering.

D-220: (a) a protonated furan, thiophene or 1-pyrroline had the Hantzsch-Widman spelling beside the retained name the neutral ring has (`oxol-1-ium`,
`3,4-dihydro-2H-azol-1-ium`): only an aromatic [n+] was neutralised for the retained lookup. (b) An N-substituted fused cation of three or more rings
(`C[n+]1cccc2ccc3ccccc3c21`) had no fusion name -- the neutral twin kept the substituent bond and did not kekulise, and a charged system of more than two
rings was refused outright -- so it was cited as the substituent of its own methyl: `(benzo[h]quinolin-1-ium-1-yl)methane`. (c) The two resonance forms of
a cyclic amidinium (`C1CC[N+]2=C(C1)NCCC2` and `C1CCN2CCC[NH+]=C2C1`, one InChIKey) got two different names; the form with the smaller canonical SMILES is
named for both.

D-221: the curated numberings of adamantane and cubane were assignments in atom order, not numberings (2 lies between 1 and 3; 1 is bonded to 2, 6 and 8), so
a second substituent landed on the wrong atom: `N-(5-hydroxyadamantan-2-yl)acetamide` was written `3-hydroxy`, and 1,3- and 1,8-dimethylcubane were one name
for two compounds. The same census row that exposed it (a bis-adamantane) could not be checked at all, because OPSIN fails to assign CIP descriptors on it.

D-222: thirteen curated ring entries gave no locant to a ring heteroatom, so their cations were named by the next plan, not by the retained parent.

D-212 (closed for good): an amidine on a RING nitrogen is a carboximidamide (`N'-benzoyl-3,5-dimethyl-1H-pyrazole-1-carboximidamide`, the target derived in round 38):
the imidamide group excluded every carbon with three nitrogens, so it never saw the ring N as its substituent and the amidine was a methanamine.

D-223: the cation of such an amidine (`NC(=[NH2+])N1CCCCC1`) was named as the NEUTRAL compound, `imino(piperidin-1-yl)methanamine`: it is no guanidinium (that needs every N
outside a ring) and was no amidinium (that needed a carbon), so the plan search dropped the charge. D-224: an amidinium with a second acid group (`NC(=[NH2+])CCC(=O)O`)
was named `butanediamidinium` -- both acids turned into amidiniums -- and is now `3-carboxypropanamidinium` (a cation outranks an acid, so the acid is the prefix).

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import re
import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

CURATED = [
    ("imidazo[2,1-b]oxazole", "C[N+]1(C)CCN2C1OCC2", "7,7-dimethylhexahydroimidazo[2,1-b][1,3]oxazol-7-ium"),
    ("oxazolo-pyrrolo-pyrazine N4", "C1CC2C3OCC[N+]3(C)CCN2C1", "4-methyloctahydro-8H-oxazolo[3,2-a]pyrrolo[2,1-c]pyrazin-4-ium"),
    ("oxazolo-pyrrolo-pyrazine N7", "C1CC2C3OCCN3CC[N+]2(C)C1", "7-methyloctahydro-8H-oxazolo[3,2-a]pyrrolo[2,1-c]pyrazin-7-ium"),
    ("dibenzo-oxepino-pyrrole", "C[NH+]1CC2c3ccccc3Oc3ccccc3C2C1", "2-methyl-2,3,3a,12b-tetrahydro-1H-dibenzo[2,3:6,7]oxepino[4,5-c]pyrrol-2-ium"),
    ("pyrido[2,1-a]isoquinolin-2-one", "O=C1CC[N+]2(C)CCc3ccccc3C2C1", "5-methyl-2-oxo-1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinolin-5-ium"),
    ("pyrido[2,1-a]isoquinoline", "C[N+]12CCCCC1c1ccccc1CC2", "5-methyl-1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinolin-5-ium"),
    ("azeto[2,1-b][1,3]oxazole", "C[N+]12CCOC1CC2", "4-methyltetrahydroazeto[2,1-b][1,3]oxazol-4-ium"),
    ("imidazo[4,5-d][1,3]diazepine", "C1=Nc2[nH]c[nH+]c2CCN1", "3,6,7,8-tetrahydroimidazo[4,5-d][1,3]diazepin-1-ium"),
    ("1,2-benzodithiete", "c1ccc2c(c1)S[SH+]2", "1,2-benzodithiet-1-ium"),
]

N_SUBSTITUTED_FUSED = [
    ("benzo[h]quinoline, N-methyl", "C[n+]1cccc2ccc3ccccc3c21", "1-methylbenzo[h]quinolin-1-ium"),
    ("benzo[h]quinoline, N-ethyl", "CC[n+]1cccc2ccc3ccccc3c21", "1-ethylbenzo[h]quinolin-1-ium"),
    ("benzo[h]quinoline, N-carboxymethyl", "OC(=O)C[n+]1cccc2ccc3ccccc3c21", "1-(carboxymethyl)benzo[h]quinolin-1-ium"),
    ("pyrido[3,2-h]quinoline", "C[n+]1cccc2ccc3cccnc3c21", "1-methylpyrido[3,2-h]quinolin-1-ium"),
    ("benzo[f]isoquinoline", "C[n+]1ccc2c(c1)ccc1ccccc12", "3-methylbenzo[f]isoquinolin-3-ium"),
    ("pyrrolo[2,3-b]quinoline keeps its NH", "C[n+]1c2ccccc2cc2cc[nH]c21", "9-methyl-1H-pyrrolo[2,3-b]quinolin-9-ium"),
    ("thiazolo-benzimidazole", "C[n+]1c2ccccc2n2ccsc21", "9-methyl[1,3]thiazolo[3,2-a][1,3]benzimidazol-9-ium"),
    ("pyrido[1,2-a]benzimidazole", "C[n+]1c2ccccc2n2ccccc21", "5-methylpyrido[1,2-a][1,3]benzimidazol-5-ium"),
    ("pyrido[4,3-b]indole", "C[n+]1ccc2[nH]c3ccccc3c2c1", "2-methyl-5H-pyrido[4,3-b]indol-2-ium"),
    ("pyrrolo[1,2-a]benzimidazole", "CC[n+]1c2ccccc2n2c1CCC2", "4-ethyl-2,3-dihydro-1H-pyrrolo[1,2-a][1,3]benzimidazol-4-ium"),
    ("imidazo[1,2-a]benzimidazole", "C[n+]1ccn2c1[nH]c1ccccc12", "1-methyl-9H-imidazo[1,2-a][1,3]benzimidazol-1-ium"),
    ("a dibenzodiazepinium", "C1=Nc2ccccc2[NH2+]c2ccccc21", "5H-dibenzo[b,e][1,4]diazepin-5-ium"),
    ("a protonated pyrrolo[2,3-b]quinoline", "c1ccc2[nH+]c3[nH]ccc3cc2c1", "1H-pyrrolo[2,3-b]quinolin-9-ium"),
    ("bicyclic amidinium, N-methyl, 6-6", "C[N+]1=C2CCCCN2CCC1", "1-methyl-1,2,3,4,6,7,8,9-octahydropyrido[1,2-a]pyrimidin-5-ium"),
    ("bicyclic amidinium, N-methyl, 6-5", "C[N+]1=C2CCCN2CCC1", "1-methyl-2,3,4,6,7,8-hexahydro-1H-pyrrolo[1,2-a]pyrimidin-5-ium"),
    ("bicyclic amidinium, N-ethyl", "CC[N+]1=C2CCCCN2CCC1", "1-ethyl-1,2,3,4,6,7,8,9-octahydropyrido[1,2-a]pyrimidin-5-ium"),
    ("bicyclic amidinium, 6-7", "C[N+]1=C2CCCCCN2CCC1", "1-methyl-2,3,4,6,7,8,9,10-octahydro-1H-pyrimido[1,2-a]azepin-5-ium"),
    ("bicyclic amidinium, 5-6", "C[N+]1=C2CCCCN2CC1", "1-methyl-2,3,5,6,7,8-hexahydro-1H-imidazo[1,2-a]pyridin-4-ium"),
]

SPELLING = [
    ("furan", "c1cc[oH+]c1", "furan-1-ium"),
    ("thiophene", "c1cc[sH+]c1", "thiophen-1-ium"),
    ("3-methylfuran", "Cc1cc[oH+]c1", "3-methylfuran-1-ium"),
    ("benzofuran", "c1ccc2c(c1)cc[oH+]2", "1-benzofuran-1-ium"),
    ("1-pyrroline", "C1CC[NH+]=C1", "3,4-dihydro-2H-pyrrol-1-ium"),
    ("2-methyl-1-pyrroline", "CC1=[NH+]CCC1", "5-methyl-3,4-dihydro-2H-pyrrol-1-ium"),
    ("1-pyrroline carboxylic acid", "C1CC[NH+]=C1C(=O)O", "5-carboxy-3,4-dihydro-2H-pyrrol-1-ium"),
    ("3,4-dihydroisoquinoline", "C1=[NH+]CCC2=CC=CC=C12", "3,4-dihydroisoquinolin-2-ium"),
    ("an octahydroquinoline", "C1CC[NH+]=C2CCCCC12", "2,3,4,4a,5,6,7,8-octahydroquinolin-1-ium"),
    ("oxazoline", "C1=[NH+]CCO1", "4,5-dihydro-1,3-oxazol-3-ium"),
]

CAGES = [
    ("5-hydroxyadamantan-2-yl", "CC(=O)NC1C2CC3CC1CC(O)(C3)C2", "N-(5-hydroxyadamantan-2-yl)acetamide"),
    ("4-hydroxyadamantan-2-yl", "CC(=O)NC1C2CC3CC(C2)CC1C3O", "N-(4-hydroxyadamantan-2-yl)acetamide"),
    ("a bis-adamantane", "OC12CC3CC(C1)C(NC1C4CC5CC1CC(O)(C5)C4)C(C3)C2", "4,4'-azanediyldi(adamantan-1-ol)"),
    ("amino and hydroxy", "OC12CC3CC(C1)C(NC)C(C3)C2", "4-(methylamino)adamantan-1-ol"),
    ("2-amino-1-ol", "NC1C2CC3CC(C2)CC1(O)C3", "2-aminoadamantan-1-ol"),
    ("2,4-dimethyl", "CC1C2CC3CC1C(C)C(C3)C2", "2,4-dimethyladamantane"),
    ("1,2-dimethylcubane", "CC12C3C4C5C3C1(C)C5C42", "1,2-dimethylcubane"),
    ("1,3-dimethylcubane", "CC12C3C4C5C3C1C5(C)C42", "1,3-dimethylcubane"),
    ("1,4-dimethylcubane", "CC12C3C4C1C1C2C3C41C", "1,4-dimethylcubane"),
]

# Unchanged: the aromatic cations that already took their retained names, and a quinuclidinium.
UNCHANGED = [
    ("N-methylquinolinium", "C[n+]1cccc2ccccc12", "1-methylquinolin-1-ium"),
    ("N-methylacridinium", "C[n+]1c2ccccc2cc2ccccc21", "10-methylacridin-10-ium"),
    ("N-methylphenanthridinium", "C[n+]1cc2ccccc2c2ccccc12", "5-methylphenanthridin-5-ium"),
    ("quinuclidinium", "C1C[NH+]2CCC1CC2", "1-azabicyclo[2.2.2]octan-1-ium"),
    ("adamantan-1-ol", "OC12CC3CC(C1)CC(C3)C2", "adamantan-1-ol"),
    ("1-methyladamantane", "CC12CC3CC(C1)CC(C3)C2", "1-methyladamantane"),
    ("methylcubane", "CC12C3C4C1C1C2C3C41", "methylcubane"),
]

CARBOXIMIDAMIDE = [
    ("on piperidine", "NC(=N)N1CCCCC1", "piperidine-1-carboximidamide"),
    ("on morpholine", "NC(=N)N1CCOCC1", "morpholine-4-carboximidamide"),
    ("on pyrazole", "NC(=N)n1cccn1", "1H-pyrazole-1-carboximidamide"),
    ("N'-methyl", "NC(=NC)n1cccn1", "N'-methyl-1H-pyrazole-1-carboximidamide"),
    ("N'-methyl on pyrrolidine", "NC(=NC)N1CCCC1", "N'-methylpyrrolidine-1-carboximidamide"),
    ("N'-hydroxy", "NC(=NO)n1cccn1", "N'-hydroxy-1H-pyrazole-1-carboximidamide"),
    ("N'-benzoyl", "NC(=NC(=O)c1ccccc1)n1cccn1", "N'-benzoyl-1H-pyrazole-1-carboximidamide"),
    ("the census row (325625)", "Cc1cc(C)n(C(N)=NC(=O)c2ccccc2)n1", "N'-benzoyl-3,5-dimethyl-1H-pyrazole-1-carboximidamide"),
    ("the salt", "N=C(N)N1CCCCC1.Cl", "piperidine-1-carboximidamide hydrochloride"),
]

AMIDINIUM_ON_RING_N = [
    ("piperidine", "NC(=[NH2+])N1CCCCC1", "piperidin-1-amidinium"),
    ("pyrazole", "NC(=[NH2+])n1cccn1", "1H-pyrazol-1-amidinium"),
    ("morpholine", "NC(=[NH2+])N1CCOCC1", "morpholin-4-amidinium"),
]

# D-224: the cation outranks an acid (P-41), so the amidinium is the parent and the other acid a prefix.
AMIDINIUM_BESIDE_ACID = [
    ("a propanoic acid", "NC(=[NH2+])CCC(=O)O", "3-carboxypropanamidinium"),
    ("a butanoic acid", "NC(=[NH2+])CCCC(=O)O", "4-carboxybutanamidinium"),
    ("on a ring", "NC(=[NH2+])C1CCCC1C(=O)O", "2-carboxycyclopentan-1-amidinium"),
    ("on a ring N", "NC(=[NH2+])N1CCCC1C(=O)O", "2-carboxypyrrolidin-1-amidinium"),
    ("benzamidinium", "NC(=[NH2+])c1ccc(C(=O)O)cc1", "4-carboxybenzamidinium"),
    ("with an amino group", "NC(=[NH2+])CC(N)C(=O)O", "3-amino-3-carboxypropanamidinium"),
    ("with an oxo group", "NC(=[NH2+])CC(=O)CC(=O)O", "4-carboxy-3-oxobutanamidinium"),
    ("with a hydroxy group", "NC(=[NH2+])CC(O)C(=O)O", "3-carboxy-3-hydroxypropanamidinium"),
    ("beside an ester", "NC(=[NH2+])CCC(=O)OC", "4-methoxy-4-oxobutanamidinium"),
    ("beside a sulfonic acid", "NC(=[NH2+])CCS(=O)(=O)O", "3-sulfopropanamidinium"),
]

# Guanidines and amidines that did not change.
GUANIDINES = [
    ("guanidine", "NC(=N)N", "guanidine"),
    ("1,1-dimethylguanidine", "CN(C)C(=N)N", "N,N-dimethylguanidine"),
    ("methylguanidine", "NC(=N)NC", "N-methylguanidine"),
    ("benzamidine", "NC(=N)c1ccccc1", "benzenecarboximidamide"),
    ("guanidinium", "NC(=[NH2+])N", "guanidinium"),
    ("benzamidinium", "NC(=[NH2+])c1ccccc1", "benzamidinium"),
    ("acetamidinium", "CC(=[NH2+])N", "acetamidinium"),
]

ALL = CURATED + N_SUBSTITUTED_FUSED + SPELLING + CAGES + UNCHANGED + CARBOXIMIDAMIDE + AMIDINIUM_ON_RING_N + AMIDINIUM_BESIDE_ACID + GUANIDINES

# Two drawings of ONE cation, which the name must not tell apart.
RESONANCE_PAIRS = [
    ("C1CC[N+]2=C(C1)NCCC2", "C1CCN2CCC[NH+]=C2C1", "3,4,6,7,8,9-hexahydro-2H-pyrido[1,2-a]pyrimidin-1-ium"),
    ("C1CN2CCCCC2=[NH+]1", "C1C[N+]2=C(N1)CCCC2", "2,3,5,6,7,8-hexahydroimidazo[1,2-a]pyridin-1-ium"),
]


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_ring_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


@pytest.mark.parametrize("a,b,expected", RESONANCE_PAIRS)
def test_the_two_resonance_forms_of_a_cyclic_amidinium_get_one_name(a, b, expected):
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(a)) == Chem.MolToInchiKey(Chem.MolFromSmiles(b))
    assert name_smiles(a) == name_smiles(b) == expected


def test_an_acyclic_amidinium_is_not_renamed_by_the_resonance_rule():
    assert name_smiles("CC(=[NH2+])N") == "acetamidinium"


def test_a_substituted_cation_is_never_the_substituent_of_its_own_alkyl():
    """The defect cited the ring as `(...-ium-1-yl)methane`; a ring cation that carries its N-substituent is the parent."""
    for _label, smiles, _expected in N_SUBSTITUTED_FUSED:
        name = name_smiles(smiles)
        assert not re.search(r"ium-\d+-yl\)", name), name


def test_a_curated_table_names_every_ring_heteroatom():
    """D-222: the thirteen entries round 35 listed as open now have a locant for every ring N, O and S."""
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    for key, entry in _RING_CURATED_SMILES.items():
        locants = entry.get("atom_locants")
        mol = Chem.MolFromSmiles(key)
        if locants is None or mol is None:
            continue
        missing = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in ("N", "S", "O") and a.IsInRing() and a.GetIdx() not in locants]
        assert not missing, (key, missing)


def test_the_curated_cage_numberings_keep_their_adjacency():
    """D-221: in adamantane 2 is between 1 and 3, 4 between 3 and 5, 6 between 5 and 7, 8 between 7 and 1, 9 between 1 and 5, 10 between 3 and 7; in cubane
    1 is bonded to 2, 6 and 8 and so on. A map in atom order satisfies none of that."""
    from openchem.vendor.iupac_namer.data_loader import _RING_CURATED_SMILES

    def bonds(key):
        mol = Chem.MolFromSmiles(key)
        loc = {int(k): str(v) for k, v in _RING_CURATED_SMILES[key]["atom_locants"].items()}
        return {frozenset((loc[b.GetBeginAtomIdx()], loc[b.GetEndAtomIdx()])) for b in mol.GetBonds()}

    adamantane = bonds("C1C2CC3CC1CC(C2)C3")
    for methylene, pair in {"2": ("1", "3"), "4": ("3", "5"), "6": ("5", "7"), "8": ("7", "1"), "9": ("1", "5"), "10": ("3", "7")}.items():
        assert all(frozenset((methylene, end)) in adamantane for end in pair), methylene
    cubane = bonds("C12C3C4C1C1C2C3C41")
    for atom, ends in {"1": ("2", "6", "8"), "2": ("1", "3", "5"), "3": ("2", "4", "8"), "4": ("3", "5", "7")}.items():
        assert all(frozenset((atom, end)) in cubane for end in ends), atom


def test_opsin_respellings_name_the_same_compound_in_the_forms_opsin_reads():
    from openchem.chem.naming_providers import opsin_readable_spellings

    assert opsin_readable_spellings("N1-benzyl-N2-phenyloxamide")[1] == "N1-benzyl-N2-phenylethanediamide"
    assert opsin_readable_spellings("(oxobis{[a]oxy}phosphanyl)benzene")[1] == "(bis{[a]oxy}(oxo)phosphanyl)benzene"
    assert opsin_readable_spellings("2H-bis([1,3]dioxolo)[4,5-b:4',5'-d]pyran")[1] == "2H-bis[1,3]dioxolo[4,5-b:4',5'-d]pyran"
    assert opsin_readable_spellings("6-{[(1R,5S)-3-hydroxyadamantan-2-yl]amino}adamantan-1-ol")[-1] == "6-{[3-hydroxyadamantan-2-yl]amino}adamantan-1-ol"
    assert opsin_readable_spellings("ethanol") == ["ethanol"]


@needs_opsin
def test_the_app_reads_back_the_names_opsin_could_not_parse():
    """The four census names the engine writes as the book does and OPSIN does not parse as written (round 40's list)."""
    from openchem.chem.naming_providers import RoundTrip, verify_name_round_trip

    oxamide = Chem.MolFromSmiles("Cc1c(Cl)cccc1NC(=O)C(=O)NCc1ccccc1")
    assert verify_name_round_trip("N1-benzyl-N2-(3-chloro-2-methylphenyl)oxamide", oxamide) == RoundTrip.MATCH
    phosphonate = Chem.MolFromSmiles("CC(C)OP(=O)(OC(C)C)C(N)c1ccccc1")
    assert verify_name_round_trip("{oxobis[(propan-2-yl)oxy]phosphanyl}phenylmethanamine", phosphonate) == RoundTrip.MATCH


@needs_opsin
def test_a_respelled_name_that_reads_as_another_compound_is_still_a_mismatch():
    """The respelling only replaces a FAILURE; it must not turn a wrong name into a verdict of 'match'. The wrong bis-adamantane name is the case that was
    hidden behind OPSIN's CIP failure."""
    from openchem.chem.naming_providers import RoundTrip, verify_name_round_trip

    mol = Chem.MolFromSmiles("OC12CC3C[C@H](C1)C(NC1[C@@H]4CC5C[C@H]1CC(O)(C5)C4)[C@@H](C3)C2")
    assert verify_name_round_trip("6-{[(1R,5S)-3-hydroxyadamantan-2-yl]amino}adamantan-1-ol", mol) == RoundTrip.MISMATCH


def test_the_cation_of_a_ring_n_amidine_keeps_its_charge():
    for _label, smiles, expected in AMIDINIUM_ON_RING_N:
        name = name_smiles(smiles)
        assert name == expected and name.endswith("amidinium"), name
