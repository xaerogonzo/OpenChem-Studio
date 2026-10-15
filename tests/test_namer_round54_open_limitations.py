"""Naming round 54 (D-256 .. D-264): the limitations rounds 50 to 53 recorded as open.

D-256: a THIOAMIDE N-prefix with a second acid in its chain (`-NC(=S)CC(=O)O`) was `[hydroxy(thioxo)methyl]acetamido`: replacing the nitrogen by OH makes a thio acid, the OTHER acid
  becomes the parent, and the O and S swapped. The generic path names it.
D-257: an O-protonated or O-alkylated UREA (`NC(N)=[OH+]`) was refused or a `NAMING ERROR`: the urea group claimed the carbon. A new classifier makes the cation the parent,
  `(diaminomethylidene)oxidanium` (the sulfur analogue was round 52).
D-258: cutting a branch off a stereo centre (`[C@H]`) left a radical, because the centre's hydrogen is an explicit count; the group was named from a radical and lost its ring double
  bond (`acetyl(oxan-3-yl)azanide` for a 3,6-dihydropyran).
D-259: the CIP descriptor of the ATTACHMENT atom of a prefix on an azanide was dropped (`acetyl(butan-2-yl)azanide` for `CC[C@H](C)[N-]C(C)=O`); it is added from the whole molecule.
D-260: a lactam anion the engine writes with a ketone SUFFIX (`3,4-dihydroquinolin-2(1H)-on-1-ide`) is unreadable; the `ide` goes in as an infix, `3,4-dihydroquinolin-1-id-2(1H)-one`.
D-261: an amidinium beside two or more acids (`NC(=[NH2+])C(C(=O)O)(C(=O)O)CC(=O)[O-]`) was refused: every neutral acid is masked as its methyl ester now, and `bis(methoxycarbonyl)` is read back.
D-262: a deprotonated amidoxime the plan search wrote with a neutral `hydroxyimino` (`1-[1-(hydroxyimino)ethyl]pyrrolidine`) is `oxidoimino`.
D-263: the N-acyl isothiourea thiolate claimed its carbonyl oxygen twice (strict ownership raised): the amide split put a second `oxo` on an oxygen that was not bonded to the anchor.
D-264: an amide or hydrazide anion beside a CATION elsewhere in the molecule was a `NAMING ERROR`; the anion is the parent (P-41) and the cation a prefix.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
THIOAMIDE_PREFIX = [
    ("a thioamide with an acetic acid chain on an anilinium", "[NH3+]c1ccc(NC(=S)CC(=O)O)cc1", "4-[(2-carboxy-1-thioxoethyl)amino]anilinium"),
    ("a thiooxamic acid on an anilinium", "[NH3+]c1ccc(NC(=S)C(=O)O)cc1", "4-{[carboxy(thioxo)methyl]amino}anilinium"),
]

OXONIUM_UREA = [
    ("O-protonated urea", "NC(N)=[OH+]", "(diaminomethylidene)oxidanium"),
    ("O-protonated N-methylurea", "CNC(N)=[OH+]", "[amino(methylamino)methylidene]oxidanium"),
    ("O-protonated N-phenylurea", "c1ccccc1NC(N)=[OH+]", "[amino(anilino)methylidene]oxidanium"),
    ("O-methylated urea", "NC(N)=[O+]C", "(diaminomethylidene)(methyl)oxidanium"),
    ("a ring sulfoxide cation, read back", "C1CCS(=[OH+])C1", "(1lambda4-thiolan-1-ylidene)oxidanium"),
]

CUT_STEREO_CENTRE = [
    ("a dihydropyran on a stereo centre (S)", "CC(=O)[N-][C@H]1C=CCOC1", "acetyl[(3S)-3,6-dihydro-2H-pyran-3-yl]azanide"),
    ("the same centre (R)", "CC(=O)[N-][C@@H]1C=CCOC1", "acetyl[(3R)-3,6-dihydro-2H-pyran-3-yl]azanide"),
    ("a saturated oxane on a stereo centre", "CC(=O)[N-][C@H]1CCCOC1", "acetyl[(3S)-oxan-3-yl]azanide"),
]

ATTACHMENT_STEREO = [
    ("sec-butyl (S)", "CC[C@H](C)[N-]C(C)=O", "acetyl[(2S)-butan-2-yl]azanide"),
    ("sec-butyl (R)", "CC[C@@H](C)[N-]C(C)=O", "acetyl[(2R)-butan-2-yl]azanide"),
    ("an alanyl and a phenylethyl group", "C[C@H](N)C(=O)[N-][C@@H](C)c1ccccc1", "[(2S)-2-aminopropanoyl][(1S)-1-phenylethyl]azanide"),
    ("a ring group with its own stereo centre", "CC(=O)[N-][C@H]1C=C[C@H](C)OC1", "acetyl[(3S,6S)-6-methyl-3,6-dihydro-2H-pyran-3-yl]azanide"),
]

LACTAM_ANION = [
    ("a dihydroquinolinone anion", "O=C1CCc2ccccc2[N-]1", "3,4-dihydroquinolin-1-id-2(1H)-one"),
    ("the same with a chlorine", "O=C1CCc2cc(Cl)ccc2[N-]1", "6-chloro-3,4-dihydroquinolin-1-id-2(1H)-one"),
    ("a benzazepinone anion", "O=C1CCCc2ccccc2[N-]1", "1,3,4,5-tetrahydro-2H-1-benzazepin-1-id-2-one"),
]

AMIDINIUM_ACIDS = [
    ("a carboxylate beside two neutral acids", "NC(=[NH2+])C(C(=O)O)(C(=O)O)CC(=O)[O-]", "3-carboxylato-2,2-dicarboxypropanamidinium"),
    ("an amidinium beside two ring acids", "NC(=[NH2+])c1cc(C(=O)O)cc(C(=O)O)c1", "3,5-dicarboxybenzamidinium"),
    ("an amidinium beside two acids on one carbon", "NC(=[NH2+])C(C(=O)O)(C(=O)O)C", "3-hydroxy-2-carboxy-2-methyl-3-oxopropanamidinium"),
]

OXIMATE = [
    ("a pyrrolidinyl amidoxime anion", "CC(N1CCCC1)=N[O-]", "1-[1-(oxidoimino)ethyl]pyrrolidine"),
    ("a piperazinyl amidoxime anion", "CC(N1CCNCC1)=N[O-]", "1-[1-(oxidoimino)ethyl]piperazine"),
    ("a morpholinyl amidoxime anion", "CC(N1CCOCC1)=N[O-]", "4-[1-(oxidoimino)ethyl]morpholine"),
]

IMIDAMIDE_OWNERSHIP = [
    ("an N-acyl isothiourea thiolate", "NC([S-])=NC(=O)c1ccccc1", "amino(benzoylimino)methanethiolate"),
]

ANION_BESIDE_CATION = [
    ("an anilide anion beside an ammonium", "CC(=O)[N-]c1ccc(cc1)C[NH3+]", "acetyl[4-(azaniumylmethyl)phenyl]azanide"),
    ("a hydrazide anion beside an ammonium", "N[N-]C(=O)c1ccc(cc1)C[NH3+]", "amino[[4-(azaniumylmethyl)phenyl](oxo)methyl]azanide"),
    ("an anilide anion beside a quaternary ammonium", "CC(=O)[N-]c1ccc(cc1)C[N+](C)(C)C", "acetyl[4-[(trimethylazaniumyl)methyl]phenyl]azanide"),
]

ANIONS = LACTAM_ANION + OXIMATE + ATTACHMENT_STEREO + CUT_STEREO_CENTRE + IMIDAMIDE_OWNERSHIP + ANION_BESIDE_CATION
CATIONS = THIOAMIDE_PREFIX + OXONIUM_UREA + AMIDINIUM_ACIDS
ALL = ANIONS + CATIONS


def _neutral_key(smiles: str) -> str:
    """The InChIKey with the anion's charge removed (standard InChI places a proton, so the question is connectivity and stereo), other charges kept."""
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() < 0 and not any(n.GetFormalCharge() > 0 for n in atom.GetNeighbors()):
            atom.SetFormalCharge(0)
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
    Chem.SanitizeMol(mol)
    return Chem.MolToInchiKey(mol)


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    mol = Chem.MolFromSmiles(back)
    assert Chem.GetFormalCharge(mol) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert _neutral_key(back) == _neutral_key(smiles), (expected, back)


def test_the_acylamino_prefix_of_an_ordinary_thioamide_is_untouched():
    assert name_smiles("[NH3+]c1ccc(NC(=S)C)cc1") == "4-(ethanethioylamino)anilinium"


def test_an_ordinary_stereo_prefix_on_an_oxygen_is_untouched():
    assert name_smiles("CC[C@H](C)Oc1ccccc1") == "{[(2S)-butan-2-yl]oxy}benzene"


def test_an_unspecified_attachment_gets_no_descriptor():
    assert name_smiles("CC(=O)[N-]C(C)C") == "acetyl(propan-2-yl)azanide"
    assert name_smiles("CC(=O)[N-]C1CCCCC1") == "acetyl(cyclohexyl)azanide"


def test_a_neutral_lactam_and_a_neutral_amidoxime_are_untouched():
    assert name_smiles("O=C1CCCN1") == "pyrrolidin-2-one"
    assert name_smiles("CC(N1CCCC1)=NO") == "1-[1-(hydroxyimino)ethyl]pyrrolidine"


def test_a_protonated_amide_and_isourea_keep_their_names():
    assert name_smiles("CC(N)=[OH+]") == "(1-aminoethylidene)oxidanium"
    assert name_smiles("COC(N)=[OH+]") == "[amino(methoxy)methylidene]oxidanium"


def test_two_anions_in_one_molecule_are_named_since_round_56():
    """Round 54 left an amide anion beside a phenolate a visible failure; round 56 cites the second anion as an `azanidyl` prefix (see test_namer_round56_*)."""
    assert name_smiles("CC(=O)[N-]c1ccc([O-])cc1") == "4-(acetylazanidyl)benzen-1-olate"
