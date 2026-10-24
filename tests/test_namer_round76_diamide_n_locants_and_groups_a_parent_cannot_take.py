"""Naming round 76 (D-344 .. D-350): the defects a FUNCTIONAL-GROUP DECORATION finds.

The population is new. ONE extra functional group (OH, NH2, COOH, CONH2, CN, SO3H, NO2, an ester, a phosphate, a peroxide ...) is attached to a random C-H, N-H, O-H or S-H of each census
molecule, or two or three to a small scaffold (a chain, a ring), the result is named and read back through OPSIN and compared on the standard InChIKey. Past the census the base rate is a
percent or less (14 in 1,400), so the finds are the shapes a principal-group choice or a locant has not met:

* D-344 `CCNC(=O)CC(C)C(N)=O` was `N-ethyl-2-methylbutanediamide`, which puts the ethyl on the amide at C1: another molecule. A primary amide is not counted as an N-bearing group, so a diamide
  with ONE substituted nitrogen saw one position and cited a bare `N`. A bare N is the first group's; the other groups cite theirs: `N4-ethyl-2-methylbutanediamide`.
* D-345 two `-thioic S-acid` groups on a chain were `butanedithioic S-acid`, which OPSIN reads as ONE group, `C(=S)S`, and no spelling of the two-group name is readable. One takes the
  suffix and the other is `sulfanyl(oxo)methyl` (`3-[sulfanyl(oxo)methyl]propanethioic S-acid`); a ring parent's `benzene-1,2-dicarbothioic S-acid` reads and stays.
* D-346 a carbamate is an ester; taken as a substitutive principal group beside a phosphate it was `2-(phosphonooxy)ethane-1-carbamate`, which OPSIN reads as the N-alkyl carbamate ANION.
* D-347 `C(=NO)[N+](=O)[O-]` (a nitrolic acid's group) matched the imidamide group, whose second nitrogen is the nitro group's: `N'-hydroxy-N-oxido-N-oxopiperidine-4-carboximidamide`.
* D-348 `acetamidooxy` is read by OPSIN as `acetamido` with the `oxy` dropped (`2-acetamidooxybenzoic acid` is 2-acetamidobenzoic acid): `2-[(acetamido)oxy]benzoic acid`.
* D-349 `R-O-O-O-H` was `(hydroxyylperoxy)`, a name OPSIN cannot read; `(hydroperoxy)oxy`, which the peroxy contraction had turned into `hydroperylperoxy`.
* D-350 `anilinoacetyl` was a simple prefix and unenclosed after a locant, `1-anilinoacetyl-2-methylhydrazine-1-phosphonic acid`, which OPSIN cannot parse: `1-(anilinoacetyl)-2-methylhydrazine-1-phosphonic acid`.
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
    ("a diamide with its one substituted nitrogen on the second group", "CCNC(=O)CC(C)C(N)=O", "N4-ethyl-2-methylbutanediamide"),
    ("...spelled from the other end", "NC(=O)C(C)CC(=O)NCC", "N4-ethyl-2-methylbutanediamide"),
    ("...on an unsaturated chain", "CCNC(=O)C=C(c1ccccc1)C(N)=O", "N4-ethyl-2-phenylbut-2-enediamide"),
    ("...a dithioamide", "CCNC(=S)CC(C)C(N)=S", "N4-ethyl-2-methylbutanedithioamide"),
    ("...on a benzene", "CCNC(=O)c1cc(C)ccc1C(N)=O", "N2-ethyl-4-methylbenzene-1,2-dicarboxamide"),
    ("...on a cyclohexane", "NC(=O)C1CCC(C)C(C(=O)NCC)C1", "N3-ethyl-4-methylcyclohexane-1,3-dicarboxamide"),
    ("two thioic S-acids on a chain", "SC(=O)CCC(=O)S", "3-[sulfanyl(oxo)methyl]propanethioic S-acid"),
    ("...on a shorter one", "SC(=O)CC(=O)S", "[sulfanyl(oxo)methyl]ethanethioic S-acid"),
    ("...on a ring, which OPSIN reads", "SC(=O)c1ccccc1C(=O)S", "benzene-1,2-dicarbothioic S-acid"),
    ("a carbamate beside a phosphate", "NC(=O)OCCOP(=O)(O)O", "1-(carbamoyloxy)-2-(phosphonooxy)ethane"),
    ("...on a ring", "NC(=O)OC1CCCCC1OP(=O)(O)O", "1-(carbamoyloxy)-2-(phosphonooxy)cyclohexane"),
    ("...on a benzene with an amine", "NC(=O)Oc1cc(N)cc(OP(=O)(O)O)c1", "3-(carbamoyloxy)-5-(phosphonooxy)aniline"),
    ("a nitro group on an imidoyl carbon", "O=[N+]([O-])C(=NO)C1CCNCC1", "4-[(hydroxyimino)(nitro)methyl]piperidine"),
    ("...with an N-methyl imine", "[O-][N+](=O)C(=NC)c1ccccc1", "[(methylimino)(nitro)methyl]benzene"),
    ("an acylamino on an oxygen, as a prefix", "CC(=O)NOc1ccccc1C(=O)O", "2-[(acetamido)oxy]benzoic acid"),
    ("...a benzamido", "O=C(c1ccccc1)NOc1ccccc1C(=O)O", "2-[(benzamido)oxy]benzoic acid"),
    ("...on a phosphorus", "CC(=O)NOP(=O)(OCC)OCC", "[(acetamido)oxy]di(ethoxy)(oxo)phosphane"),
    ("...inside a larger prefix", "CC(=O)NOS(=O)(=O)c1ccccc1", "[(acetamido)oxysulfonyl]benzene"),
    ("a carbo thioic S-acid beside a terminal one", "CC=C(C(=O)S)C(OP(=O)(O)O)C(=O)S", "3-[(oxo)(sulfanyl)methyl]-2-(phosphonooxy)pent-3-enethioic S-acid"),
    ("a hydrotrioxide as a prefix", "OOOc1ccccc1C(=O)O", "2-[(hydroperoxy)oxy]benzoic acid"),
    ("a compound acyl prefix after a locant", "O=C(CNc1ccccc1)N(NC)P(=O)(O)O", "1-(anilinoacetyl)-2-methylhydrazine-1-phosphonic acid"),
]

KEPT = [
    ("a diamide with its substituent on the first group keeps a bare N", "CCNC(=O)C(C)CC(N)=O", "N-ethyl-2-methylbutanediamide"),
    ("a symmetric one", "CCNC(=O)CCC(N)=O", "N-ethylbutanediamide"),
    ("two substituted nitrogens already cite both", "CCNC(=O)C(CC)CC(=O)NC", "N1,2-diethyl-N4-methylbutanediamide"),
    ("a carbamate with nothing senior is still an ester", "NC(=O)OCCO", "2-hydroxyethyl carbamate"),
    ("an amidoxime is still an imidamide", "NC(=NO)c1ccccc1", "N'-hydroxybenzenecarboximidamide"),
    ("an N-alkoxy amide with nothing senior is an amide", "CC(=O)NOCC", "N-ethoxyacetamide"),
    ("a peroxide is as it was", "COOC", "(methylperoxy)methane"),
]

ALL = NAMED + KEPT


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
