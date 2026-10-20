"""Naming round 73 (D-334 .. D-336): the defects a NON-CANONICAL TAUTOMER of each census molecule finds.

The population is new. RDKit's tautomer enumerator gives each census molecule another form of itself (an imidic acid for an amide, an exocyclic imine for an amine on an azole,
a quinoid ring for a conjugated one), the form is named, and the name is read back through OPSIN and compared on InChI WITH the mobile-hydrogen layer (`/FixedH`): the standard key
treats tautomers as one molecule, which is exactly the thing this population asks. 1,200 forms: 17 names for another molecule, 9 names with an error in them, 5 for another tautomer.

* D-334 `phenyl` is joined by a SINGLE bond. A benzene ring joined to its parent by a DOUBLE bond is a quinoid ring (`C=C1C=CC(=C(N)N)C=C1`), and was named `(4-methylidenephenyl)methanediamine`,
  which OPSIN reads as a different compound with two more hydrogens (a silent wrong name). It is `(4-methylidenebenzen-1-ylidene)methanediamine`, as the same ring with two methylidenes is already
  `1,4-dimethylidenebenzene`.
* D-335 `1,3,4-thiadiazole` and `1,3,4-oxadiazole` were curated without `atom_locants`, so the hydrogen of `CN=c1[nH]nc(C)s1` could not be placed: `2-methyl-5-(methylimino)-1,3,4-thiadiazole`,
  which OPSIN reads with the hydrogen on the CARBON (`CC1SC(N=N1)=NC`). They are `5-methyl-2-(methylimino)-3H-1,3,4-thiadiazole` now.
* (refused, not fixed) a guanidinium nitrogen joined to its group by a DOUBLE bond lost the bond in `_name_branch_as_prefix`; it is declined there, so the ion is refused.
* D-336 an imidic acid beside a group with an oxygen or nitrogen of its own on its imine (`N(C)C(O)=Nc1ccccc1OC` inside a bigger name) carried an ErrorTree: the split of a demoted
  `carboximidic acid` into `imino` and `hydroxy` visited EVERY atom of the group, took the ether oxygen of the methoxy for a second hydroxy of the anchor and cut a substituent with no bond to it.
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
    ("a quinoid ring joined by a double bond", "C=C1C=CC(=C(N)N)C=C1", "(4-methylidenebenzen-1-ylidene)methanediamine"),
    ("...beside an acid", "O=C(O)C(=C1C=CC(=C)C=C1)C", "2-(4-methylidenebenzen-1-ylidene)propanoic acid"),
    ("...with a second ring", "CC(=C1C=CC(=C)C=C1)c1ccccc1", "1-methylidene-4-(1-phenylethan-1-ylidene)benzene"),
    ("a quinoid ring with two ylidenes of its own", "CC(O)=C1C=CC(=C(C)O)C=C1", "1,4-bis(1-hydroxyethylidene)benzene"),
    ("an imine on a thiadiazole with its hydrogen on the ring nitrogen", "CN=c1[nH]nc(C)s1", "5-methyl-2-(methylimino)-3H-1,3,4-thiadiazole"),
    ("...an oxadiazole", "CN=c1[nH]nc(C)o1", "5-methyl-2-(methylimino)-3H-1,3,4-oxadiazole"),
    ("...unsubstituted", "CN=c1[nH]ncs1", "2-(methylimino)-3H-1,3,4-thiadiazole"),
    ("...an acylimine", "CC(=O)N=c1[nH]nc(-c2ccccc2)s1", "2-(acetylimino)-5-phenyl-3H-1,3,4-thiadiazole"),
    ("an imidic acid whose imine carries a methoxy", "OC(=O)CN(C)C(O)=Nc1ccccc1OC", "{[hydroxy(2-methoxyphenylimino)methyl](methyl)amino}acetic acid"),
    ("...an acyl", "OC(=O)CN(C)C(O)=NC(=O)C", "{[(acetylimino)(hydroxy)methyl](methyl)amino}acetic acid"),
    ("...an amino", "OC(=O)CN(C)C(O)=Nc1ccccc1N", "{[(2-aminophenylimino)(hydroxy)methyl](methyl)amino}acetic acid"),
    ("...a thioimidic acid", "OC(=O)CN(C)C(S)=Nc1ccccc1OC", "{[(2-methoxyphenylimino)(sulfanyl)methyl](methyl)amino}acetic acid"),
    ("...on a ring that is the parent", "C1CCOC1N(C)C(O)=NCCOC", "N-[hydroxy(2-methoxyethylimino)methyl]-N-methyloxolan-2-amine"),
]

KEPT = [
    ("a phenyl is still a phenyl", "OC(=O)Cc1ccccc1", "phenylacetic acid"),
    ("a thiadiazole with nothing to place keeps its name", "Cc1nnc(N)s1", "5-methyl-1,3,4-thiadiazol-2-amine"),
    ("an oxadiazole too", "Cc1nnc(Cl)o1", "2-chloro-5-methyl-1,3,4-oxadiazole"),
    ("an imidic acid with a plain imine is as it was", "OC(=O)CN(C)C(O)=Nc1ccccc1Cl", "{[(2-chlorophenylimino)(hydroxy)methyl](methyl)amino}acetic acid"),
]

REFUSED = [
    # the nitrogen of a guanidinium joined to its group by a DOUBLE bond: named as a single-bonded substituent the group gained a hydrogen, `1-[anilino(hydroxy)methyl]-2-ethylguanidinium`
    ("a guanidinium nitrogen double-bonded to its group", "NC(=[NH+]CC)N=C(O)Nc1ccccc1"),
]

ALL = NAMED + KEPT


def _fixed_key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles), options="/FixedH")


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles", REFUSED, ids=[row[0] for row in REFUSED])
def test_a_charged_group_that_would_lose_a_double_bond_is_refused(label, smiles):
    with pytest.raises(ValueError, match="guanidinium"):
        name_smiles(smiles)


def test_the_same_group_on_a_single_bond_is_named():
    assert name_smiles("NC(=[NH+]CC)NC(O)=Nc1ccccc1") == "2-ethyl-1-[hydroxy(phenylimino)methyl]guanidinium"


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_same_tautomer(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert _fixed_key(back) == _fixed_key(smiles), (expected, back)
