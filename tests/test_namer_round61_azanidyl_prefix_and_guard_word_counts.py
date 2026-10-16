"""Naming round 61 (D-291 .. D-294): the `azanidyl` prefix, and four ways the charge guard counted a word for a charge or let one go.

The round widened the PAIR populations to the sites round 60 added (an alkoxide, an anilide NH, the oxygens of an ester, an acid, an aldehyde, an ether and an alcohol). They found:

D-291: an aryl `[NH-]` beside another anion was cited as the prefix `azanide` (`4-azanidebenzoate`, refused; `4-azanide-N-...sulfonamidate`, unreadable). `azanide` is the parent hydride
  anion; the prefix is `azanidyl`, which OPSIN reads.
D-292 (a silent lost anion): a charge-separated GROUP whose charges do not cancel is an ion. The nitronate-like `[c-][N+](=O)[O-]` of a nitro carbon acid is -1 over three atoms; the
  guard dropped the whole group as a dipole, so `...-5-nitro-1,3-diazine-4,6-dione` stood for it beside a cation, the anion gone.
D-293 (silent lost charges): the guard's multiplier pattern took `dihydropyrido`, `pentanamido`, `pyridinium` and `dichloroacetate` for multiplied ion words, so a name that cited ONE
  cation counted several, and a protonated ester or acid beside another cation passed with its charge gone. And `pyrido` was an `oxido` anion word.
D-294 (a wrong protonation site): an O-protonated ester beside a ketone was named with the KETONE's `oxo` as the `oxidaniumylidene`, the ester's `ethoxycarbonyl` neutral: the same
  neutral compound, another cation. It is left to the guard, which refuses it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _ANION_WORD_END, _CATION_WORD, _check_charge_named, _ion_word_weight

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

NAMED = [
    ("an anilide beside a carboxylate", "[NH-]c1ccc(C(=O)[O-])cc1", "4-azanidylbenzoate"),
    ("an anilide beside a sulfonate", "[NH-]c1ccc(S(=O)(=O)[O-])cc1", "4-azanidylbenzene-1-sulfonate"),
    ("an anilide beside an ammonium", "[NH-]c1ccc(CC[NH3+])cc1", "[2-(4-azanidylphenyl)ethyl]azanium"),
    ("an O-protonated ketone beside an urea (unchanged)", "CC(=[OH+])c1cccc(NC(=O)Nc2ccc(Nc3ccccc3)cc2)c1", "N-(4-anilinophenyl)-N'-[3-(1-oxidaniumylideneethyl)phenyl]urea"),
    ("an O-protonated carbamate beside a carboxylate (unchanged)", "[NH3+][C@@H](CCCCNC(=[OH+])OCc1ccccc1)C(=O)[O-]",
     "(2S)-2-azaniumyl-6-{[(oxidaniumylidene)(phenylmethoxy)methyl]amino}hexanoate"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


# --- D-292 -----------------------------------------------------------------------------------------------------------------------------------------------------------
def test_a_nitro_carbanion_beside_a_cation_is_an_anion_and_a_name_without_it_is_refused():
    mol = Chem.MolFromSmiles("C[OH+]c1ccccc1Nc1nc(=O)[c-]([N+](=O)[O-])c(=O)[nH]1")
    with pytest.raises(ValueError, match="negative"):
        _check_charge_named(mol, "2-{[2-(methyloxidaniumyl)phenyl]amino}-5-nitro-1,3-diazine-4,6-dione")


def test_a_nitro_group_alone_is_still_neutral():
    _check_charge_named(Chem.MolFromSmiles("C[NH2+]c1ccc([N+](=O)[O-])cc1"), "methyl(4-nitrophenyl)azanium")


# --- D-293 -----------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,word,weight", [
    ("1-(3-{3-amino-5-[carbamimidoyl(methyl)amino]pentanamido}-pyran-6-yl)-2-oxopyrimidin-4-aminium", _CATION_WORD, 1),     # `pentanamido`
    ("9-(ethoxycarbonyl)-4,10-dimethyl-2-oxo-2,7-dihydropyrido[2,3-f]quinolin-1-ium", _CATION_WORD, 1),                      # `dihydropyrido`
    ("4-(pyridinium-4-yl)quinolin-1-ium", _CATION_WORD, 2),                                                                  # `pyridinium`
    ("4-oxidaniumyl-16,18-dioxo-pentacyclo[10.7.0.0]nonadeca-5-yl dichloroacetate", _CATION_WORD, 1),                         # an anion word is no cation
    ("propane-1,3-diium", _CATION_WORD, 2),
    ("1-(3-{3-amino-5-[carbamimidoyl(methyl)amino]pentanamido}-pyran-6-yl)-2-oxopyrimidin-4-aminium", _ANION_WORD_END, 0),   # `pentanamido` is no anion either
    ("9-(ethoxycarbonyl)-4,10-dimethyl-2-oxo-2,7-dihydropyrido[2,3-f]quinolin-1-ium", _ANION_WORD_END, 0),
    ("propanedioate", _ANION_WORD_END, 2),
    ("6-oxidaniumylidene-2,3,4,5-decahydro-1H-cyclopenta[c]pyrido[3,2-h]quinoline", _ANION_WORD_END, 0),                      # `pyrido` is no oxido
])
def test_the_weight_of_a_name(name, word, weight):
    assert _ion_word_weight(name, word) == weight


# --- D-294 -----------------------------------------------------------------------------------------------------------------------------------------------------------
def test_a_protonated_ester_beside_a_ketone_does_not_hand_its_charge_to_the_ketone():
    with pytest.raises(ValueError):
        name_smiles("CCOC(=[OH+])c1[nH]c(C)c(C(=O)[C@@H]2C(=O)C(=O)N(CC[NH+](C)C)[C@@H]2c2ccc(C(C)C)cc2)c1C")


# --- the tool --------------------------------------------------------------------------------------------------------------------------------------------------------
def test_the_pair_modes_take_the_kinds_round_60_added():
    assert {"alcohol", "aniline_nh"} <= set(pop.ZWITTERION_ACIDS) & set(pop.DIANION_KINDS)
    assert {"ester_o", "acid_o", "aldehyde_o", "ether_o", "alcohol_o"} <= set(pop.ZWITTERION_BASES) & set(pop.DICATION_KINDS)
