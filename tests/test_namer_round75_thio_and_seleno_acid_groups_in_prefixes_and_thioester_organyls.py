"""Naming round 75 (D-340 .. D-343): the defects a CONGENER SWAP finds.

The population is new. ONE heavy atom of each census molecule is swapped for its congener (O to S or Se, S to O or Se, N to P or As, C to Si or Ge), the result is named, read back
through OPSIN and compared on the standard InChIKey. 2,000 molecules: the chalcogen swaps alone gave 59 NAMING ERRORs in 1,600 (a sulfonothioyl or sulfonoselenoyl group, `S(=O)(=S)`,
anywhere but on a bare NH2), a handful of names OPSIN cannot parse (`selenonamido`) and of names for another molecule (`selanylidenemethanolate`, read as a hypervalent Se-H).

* D-340 `R-S(=O)(=S)-` and `R-S(=O)(=Se)-` had no prefix. The sulfonothioamide FG matches only NH2 (an N-substituent has no place in its prefix), so every other one was
  `{[NAMING ERROR: No valid naming plan found for O=[SH](=S)...]}`; the carved `[SH]` is the free valence. The sulfonyl/sulfinyl prefix is built from the terminal chalcogens now:
  `sulfonothioyl`, `sulfonoselenoyl`, `sulfinothioyl`, `sulfonodithioyl` (`4-(methylsulfonothioyl)aniline`, `N-[4-(pyrrolidin-1-ylsulfonothioyl)phenyl]acetamide`).
* D-341 The same prefix for a SELENIUM and a TELLURIUM centre: `selenonamidobenzene` is not a name OPSIN reads (and dropped the N-substituent), `(methylaminoselenonyl)benzene` is.
  The selenonamide FG is NH2-only like seleninamide, with the prefix `aminoselenonyl`.
* D-342 `C([O-])=[Se]` had no FG (the carbothioic O-acid has one): `phenylselanylidenemethanolate`, which OPSIN reads with a hypervalent Se-H. `benzenecarboselenoate`.
* D-343 `S-3,5-dimethylcyclohexyl ethanethioate` and `S-(isoquinolin-1-yl)(phenyl)methyl ...` are names OPSIN cannot parse: a locant list right after the italic `S-`, or two enclosed
  prefixes side by side, ends the word early. The organyl is enclosed in that case (`S-(3,5-dimethylcyclohexyl) ethanethioate`); `S-2-methylcyclohexyl` stays as it was.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a sulfonothioyl on a benzene", "CNS(=O)(=S)c1ccccc1", "(methylaminosulfonothioyl)benzene"),
    ("...on a ring nitrogen, in a bigger name", "CC(=O)Nc1ccc(S(=O)(=S)N2CCCC2)cc1", "N-[4-(pyrrolidin-1-ylsulfonothioyl)phenyl]acetamide"),
    ("...a C-substituent", "CS(=O)(=S)c1ccc(N)cc1", "4-(methylsulfonothioyl)aniline"),
    ("...beside a second sulfonyl", "CCS(=O)(=S)c1c(S(=O)(=O)CC)c2c(C)cccn2c1C(=O)c1ccccc1", "[1-(ethanesulfonyl)-2-(ethylsulfonothioyl)-8-methylindolizin-3-yl](phenyl)methanone"),
    ("a sulfonoselenoyl", "CC(=O)Nc1ccc(S(=O)(=[Se])N2CCCC2)cc1", "N-[4-(pyrrolidin-1-ylsulfonoselenoyl)phenyl]acetamide"),
    ("...a bare NH2", "NS(=O)(=[Se])c1ccccc1", "(aminosulfonoselenoyl)benzene"),
    ("a sulfinothioyl", "CS(=S)c1ccc(N)cc1", "4-(methylsulfinothioyl)aniline"),
    ("a sulfonodithioyl", "CS(=S)(=S)c1ccc(N)cc1", "4-(methylsulfonodithioyl)aniline"),
    ("a sulfinothioyl beside a sulfonyl", "O=S(=O)(c1ccccc1)S(=S)c1ccccc1", "(phenylsulfinothioylsulfonyl)benzene"),
    ("an N-substituted selenonamide", "c1ccccc1[Se](=O)(=O)Nc1ccccc1", "[(benzeneselenonyl)amino]benzene"),
    ("...on an acid", "O=C(O)c1ccc(cc1)[Se](=O)(=O)NC", "4-(methylaminoselenonyl)benzoic acid"),
    ("a telluronamide", "c1ccccc1[Te](=O)(=O)Nc1ccccc1", "[(benzenetelluronyl)amino]benzene"),
    ("a carboselenoate", "[O-]C(=[Se])c1ccccc1", "benzenecarboselenoate"),
    ("...the O-acid", "OC(=[Se])c1ccccc1", "benzenecarboselenoic O-acid"),
    ("...beside a ring", "O=Cc1ccc(-c2ccc(C([O-])=[Se])s2)s1", "5-(5-formylthiophen-2-yl)thiophene-2-carboselenoate"),
    ("a thioester with a locant list in its organyl", "CC(=O)SC1CC(C)CC(C)C1", "S-(3,5-dimethylcyclohexyl) ethanethioate"),
    ("...a bridged organyl", "CC(=O)SC1C2(C)CN3CCN(C2)CC1(C)C3", "S-(1,8-dimethyl-3,6-diazatricyclo[4.3.1.1^{3,8}]undecan-9-yl) ethanethioate"),
    ("a thionoester takes the same marks", "CC(=S)OC1CC(C)CC(C)C1", "O-(3,5-dimethylcyclohexyl) ethanethioate"),
    ("...two enclosed prefixes", "O=C(SC(c1ccccc1)c1nccc2ccccc12)c1ccccc1Cl", "S-[(isoquinolin-1-yl)(phenyl)methyl] 2-chlorobenzene-1-carbothioate"),
]

KEPT = [
    ("a sulfonyl is as it was", "CCCS(=O)(=O)c1ccccc1", "(propanesulfonyl)benzene"),
    ("a sulfinyl too", "CCCS(=O)c1ccccc1", "(propanesulfinyl)benzene"),
    ("a ring-nitrogen sulfonyl", "O=S(=O)(c1ccccc1)N1CCCC1", "1-(benzenesulfonyl)pyrrolidine"),
    ("a bare sulfonothioamide is still the parent", "NS(=O)(=S)c1ccccc1", "benzenesulfonothioamide"),
    ("a bare selenonamide is still the parent", "N[Se](=O)(=O)c1ccccc1", "benzeneselenonamide"),
    ("a carbothioate is as it was", "[O-]C(=S)c1ccccc1", "benzenecarbothioate"),
    ("an S-ester with one locant keeps its bare organyl", "CC(=O)SC1CCCCC1C", "S-2-methylcyclohexyl ethanethioate"),
    ("an ordinary ester of the same alcohol", "CC(=O)OC1CC(C)CC(C)C1", "3,5-dimethylcyclohexyl acetate"),
]

ALL = NAMED + KEPT


def test_a_group_with_a_thio_and_a_seleno_replacement_is_refused_visibly():
    """`sulfinothioselenoyl` is not built: a visible NAMING ERROR, where leaving the guard out names it `sulfonothioyl` and silently drops the Se."""
    assert "NAMING ERROR" in name_smiles("CS(=S)(=[Se])c1ccccc1")


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_same_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert _key(back) == _key(smiles), (expected, back)
