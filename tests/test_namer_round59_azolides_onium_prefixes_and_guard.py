"""Naming round 59 (D-278 .. D-284): an azolide's substituents, onium centres as prefixes, and four ways the charge guard counted a word for a charge.

The round's populations widened to the sites rounds 46-58 never changed (N-oxide O, selenium, phosphine oxide, boronic and phosphinic acids, an enol, a carbon acid, an O-protonated
carbonyl) and to three charges. They found:

D-278 (silent wrong molecule): a pyrazole or imidazole ANION beside a second ion was named with its substituent on a NITROGEN (`1-(carboxylatomethyl)-1H-pyrazol-2-ide` for the
  5-substituted pyrazol-1-ide). The indicated-hydrogen numbering filter read the deprotonated `[n-]` as a bare `=N-` and kept only the numberings that put a ring CARBON at locant 1.
  And as a SUBSTITUENT the ring `[n-]` had no infix at all, so the group was written neutral beside the cation (`-N-id-`: `1H-pyrazol-1-id-5-yl`); before a suffix the `-ide` came last
  (`1H-indol-5-ol-1-ide`, which OPSIN cannot read) and is now the infix too (`1H-indol-1-id-5-ol`).
D-279: a protonated thioether or ether (`C[SH+]C`, `C[OH+]C`) beside another ion was taken for an ETHER prefix (`methylsulfanyl`) and lost its charge; it is `methylsulfaniumyl`.
D-280 (silent wrong molecule): the guard counted a sulfonium and a pyridinium nitrogen on one carbon as ONE centre; and an alkane stem (`hexanoate`) was taken for a multiplier
  (`hexa` + `noate`), which skipped the count test altogether; and an ester's final `ate` was an anion word in a zwitterion.
D-281: a ring cation beside an anion that is only a PREFIX (`[methyl(oxido)amino]`) was named without its `-ium`.
D-282: an O-protonated carbonyl beside another charge (`C(=[OH+])N...`) had a neutral `oxo`; it is `oxidaniumylidene`, which OPSIN reads.
D-283: a cation parent hydride (sulfanium) took the suffix of a group standing beside it (`dimethylsulfaniumcarboximidamide`); the cation is the parent and the group is a prefix.
D-284 (silent wrong stereo): the only stereo centre of a branch carved out beside an anionic nitrogen was labelled in the branch, without the atom it was cut from, and read S where the
  molecule's centre is R.
Also: a carbanion with a ring HETERO neighbour (an oxazolone) is named (refused until now).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    # D-278
    ("a pyrazol-5-yl carboxylate beside a second anion", "O=C([O-])Cc1ccn[n-]1", "(1H-pyrazol-1-id-5-yl)acetate"),   # round 60: the acid anion is the parent
    ("a pyrazolide with an O-protonated acyl", "CC(=[OH+])c1cc(-c2ccccc2)n[n-]1", "5-(1-oxidaniumylideneethyl)-3-phenyl-1H-pyrazol-1-ide"),
    ("a pyrazolide as a substituent of an ammonium", "C[N+](C)(C)c1ccn[n-]1", "trimethyl(1H-pyrazol-1-id-5-yl)ammonium"),
    ("an imidazolide as a substituent", "C[NH+](C)CCc1ncc[n-]1", "[2-(1H-imidazol-1-id-2-yl)ethyl]di(methyl)azanium"),
    ("a tetrazolide as a substituent", "C[NH+](C)CCc1nn[n-]n1", "dimethyl[2-(2H-tetrazol-2-id-5-yl)ethyl]azanium"),
    ("an imidazolide with a carboxamide beside an azanium", "NC(=O)c1[n-]cnc1[NH2+]N=NCCF", "4-[(2-fluoroethyldiazenyl)azaniumyl]-1H-imidazol-1-id-5-carboxamide"),
    ("an indolide with a hydroxy beside an azanium", "C[NH2+]CCc1c[n-]c2ccc(O)cc12", "3-[2-(methylazaniumyl)ethyl]-1H-indol-1-id-5-ol"),
    ("a benzimidazolide as a substituent", "Cc1ccc2[n-]c(C[NH3+])nc2c1", "[(5-methyl-1H-benzimidazol-1-id-2-yl)methyl]azanium"),
    # D-279
    ("a protonated thioether beside a carboxylate", "C[SH+]CC(=O)[O-]", "(methylsulfaniumyl)acetate"),
    ("a protonated thioether beside a pyridinium", "C[SH+]c1cccc[nH+]1", "2-(methylsulfaniumyl)pyridin-1-ium"),
    ("a protonated thioether beside an ammonium", "C[SH+]CC[NH3+]", "2-(methylsulfaniumyl)ethan-1-aminium"),
    ("a protonated ether beside a carboxylate", "C[OH+]CC(=O)[O-]", "(methyloxidaniumyl)acetate"),
    ("a protonated isothiourea-like sulfur", "CC[SH+]C(S)=Nc1ccccc1", "{[(ethylsulfaniumyl)(sulfanyl)methylidene]amino}benzene"),
    ("a protonated thioether on a quinolinium", "Cc1cc([SH+]CCC(=O)[O-])c2cc(Cl)ccc2[nH+]1", "3-[(6-chloro-2-methylquinolin-1-ium-4-yl)sulfaniumyl]propanoate"),
    # D-281
    ("a pyridinium beside an N-oxido amine", "Cc1ccc(N(C)[O-])c[nH+]1", "2-methyl-5-[methyl(oxido)amino]pyridin-1-ium"),
    ("a pyridinium beside a dioxidoamino group", "Cc1ccc(N([O-])[O-])c[nH+]1", "5-dioxidoamino-2-methylpyridin-1-ium"),
    # D-282
    ("an O-protonated carbamate beside an ammonium and a carboxylate", "[NH3+][C@@H](CCCCNC(=[OH+])OCc1ccccc1)C(=O)[O-]",
     "(2S)-2-azaniumyl-6-{[(oxidaniumylidene)(phenylmethoxy)methyl]amino}hexanoate"),
    ("an O-protonated ketone on a urea", "CC(=[OH+])c1cccc(NC(=O)Nc2ccc(Nc3ccccc3)cc2)c1", "N-(4-anilinophenyl)-N'-[3-(1-oxidaniumylideneethyl)phenyl]urea"),
    # D-283
    ("an S-methylisothiourea sulfur", "CNC(=N)[SH+]C", "[(imino)(methylamino)methyl](methyl)sulfanium"),
    ("a protonated thiocyanate", "C[SH+]C#N", "cyano(methyl)sulfanium"),
    # the carbanion beside a ring hetero atom
    ("an oxazolone carbanion", "COC(=O)CCC(=O)[c-]1nc(-c2ccccc2)oc1=O", "4-(4-methoxy-1,4-dioxobutyl)-5-oxo-2-phenyl-4,5-dihydro-1,3-oxazol-4-ide"),
]

# Unchanged: the charge-separated groups and the single azolide keep what they had.
KEPT = [
    ("an N-oxide", "Cc1cccc[n+]1[O-]", "2-methylpyridine 1-oxide"),
    ("a nitropyridinium", "[O-][N+](=O)c1ccc[nH+]c1", "3-nitropyridin-1-ium"),
    ("a pyrazol-5-ide", "NC(=O)c1cc(C)n[n-]1", "5-carbamoyl-3-methyl-1H-pyrazol-1-ide"),
    ("a plain sulfonium", "C[S+](C)CC(=O)[O-]", "(dimethylsulfaniumyl)acetate"),
    ("an ordinary sulfanium", "C[SH+]CC", "ethyl(methyl)sulfanium"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.GetFormalCharge(Chem.MolFromSmiles(back)) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert pop._inchikey(back, neutral=True) == pop._inchikey(smiles, neutral=True), (expected, back)


# --- what the guard judges now -------------------------------------------------------------------------------------------------------------------------------------------
def test_a_sulfonium_and_a_pyridinium_on_one_carbon_are_two_cations():
    mol = Chem.MolFromSmiles("C[SH+]c1cccc[nH+]1")
    with pytest.raises(ValueError, match="fewer cation words"):
        _check_charge_named(mol, "2-(methylsulfanyl)pyridin-1-ium")


def test_an_alkane_stem_is_not_a_multiplier():
    mol = Chem.MolFromSmiles("[NH3+][C@@H](CCCCNC(=[OH+])OCc1ccccc1)C(=O)[O-]")
    with pytest.raises(ValueError, match="fewer cation words"):
        _check_charge_named(mol, "(2S)-2-azaniumyl-6-{[(oxo)(phenylmethoxy)methyl]amino}hexanoate")


def test_a_real_multiplier_still_stands_for_several_centres():
    # `dioxido` is one word for two O-; `propanedioate` one for two carboxylates
    _check_charge_named(Chem.MolFromSmiles("[O-]C(=O)CC(=O)[O-]"), "propanedioate")


def test_an_ester_ending_is_no_anion_word_in_a_zwitterion():
    mol = Chem.MolFromSmiles("CC[SH+]C1=C(C#N)[C@H](c2ccccc2Cl)[C-](C(=O)OC)C(=O)N1")
    with pytest.raises(ValueError, match="negative"):
        _check_charge_named(mol, "methyl (4R)-4-(2-chlorophenyl)-5-cyano-6-(ethylsulfaniumyl)-2-oxoazinane-3-carboxylate")


def test_a_carbanion_beside_a_protonated_thioether_is_refused_not_named_as_its_ester():
    with pytest.raises(ValueError):
        name_smiles("CC[SH+]C1=C(C#N)[C@H](c2ccccc2Cl)[C-](C(=O)OC)C(=O)N1")


def test_an_aryl_ester_ending_is_no_anion_word_either():
    mol = Chem.MolFromSmiles("COc1cc(C=[NH+]n2cn[n-]c2=S)ccc1OC(=O)c1ccccc1")
    with pytest.raises(ValueError, match="negative"):
        _check_charge_named(mol, "2-methoxy-4-{[(5-thioxo-1H,4H-1,2,4-triazol-4-yl)azaniumylidene]methyl}phenyl benzoate")


# --- the pieces ------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_a_charged_chalcogen_is_not_an_ether_prefix():
    # the neutral ether keeps `methylsulfanyl`
    assert name_smiles("CSCC(=O)[O-]") == "(methylsulfanyl)acetate"


def test_a_cation_hydride_parent_takes_no_suffix_that_stands_beside_it():
    assert "sulfaniumcarb" not in name_smiles("CCc1cccc(CC)c1NC(=NC(=O)c1ccc(Br)cc1)[SH+]C")


def test_the_deprotonated_azole_is_the_indicated_hydrogen_slot():
    from openchem.vendor.iupac_namer.engine import _filter_indicated_h_numberings  # noqa: F401  (the filter is exercised through the names above)

    assert name_smiles("Cc1ccn[n-]1") == "5-methyl-1H-pyrazol-1-ide"
    assert name_smiles("O=C([O-])Cc1ccn[n-]1").endswith("5-yl)acetate")


# --- the last four of the round ---------------------------------------------------------------------------------------------------------------------------------------
def test_a_carved_branchs_only_stereo_centre_keeps_the_label_it_has_in_the_whole_molecule():
    # the cut CH2-N- becomes CH2-H in the branch, below the phenyl, so the group's own centre read S where the molecule's is R (D-284)
    assert name_smiles("C[NH+](C)[C@@H](C[N-]C(=O)C)c1ccccc1") == "acetyl[(2R)-2-(dimethylazaniumyl)-2-phenylethyl]azanide"
    assert name_smiles("C[NH+](C)[C@H](C[N-]C(=O)C)c1ccccc1") == "acetyl[(2S)-2-(dimethylazaniumyl)-2-phenylethyl]azanide"


def test_a_multiplied_ion_word_counts_its_multiplier_and_no_more():
    # `1,4-diium` stands for two cations; a third (the O-protonated amide) was never missed while a multiplied word switched the count test off (D-280)
    mol = Chem.MolFromSmiles("COc1ccc([C@@H]2C[C@H](C(F)(F)F)n3[nH+]cc(C(=[OH+])Nc4ccccc4SC)c3[NH2+]2)cc1")
    with pytest.raises(ValueError, match="fewer cation words"):
        name_smiles("COc1ccc([C@@H]2C[C@H](C(F)(F)F)n3[nH+]cc(C(=[OH+])Nc4ccccc4SC)c3[NH2+]2)cc1")
    assert name_smiles("C[NH+]1CC[NH+](C)CC1") == "1,4-dimethylpiperazine-1,4-diium"
    assert name_smiles("[NH3+]CC[NH3+]") == "ethane-1,2-bis(aminium)"
    assert name_smiles("O=S(=O)([O-])c1cccc(S(=O)(=O)[O-])c1") == "benzene-1,3-disulfonate"
    assert mol is not None


def test_an_ion_word_inside_an_atom_prefix_is_not_a_multiplied_word():
    from openchem.vendor.iupac_namer.engine import _multiplies_an_ion_word

    assert not _multiplies_an_ion_word("13-oxa-10-thia-3,5,6,8-tetraazatetracyclo[7.7.0.0^{2,6}.0^{11,16}]hexadeca-1(9),2,4,7,11(16)-pentaen-8-ium")
    assert _multiplies_an_ion_word("propanedioate")
    assert not _multiplies_an_ion_word("hexanoate")


def test_an_ester_word_in_front_of_a_cation_parent_is_refused():
    # the molecule is named properly since round 60 (an O-alkylated carbonyl is a prefix); the guard's rule is exercised on the name it was written for
    mol = Chem.MolFromSmiles("CCOC(=O)C[SH+]C1=CCCNC1=[O+]C")
    with pytest.raises(ValueError, match="ester"):
        _check_charge_named(mol, "ethyl {5-[(carboxymethyl)sulfaniumyl]-3,4-dihydropyridin-2(1H)-ylidene}(methyl)oxidanium")


def test_a_protonated_carbonyl_whose_cation_is_already_cited_keeps_its_oxo():
    assert name_smiles("COC(=O)CC(=[OH+])C") == "(4-methoxy-4-oxobutan-2-ylidene)oxidanium"
