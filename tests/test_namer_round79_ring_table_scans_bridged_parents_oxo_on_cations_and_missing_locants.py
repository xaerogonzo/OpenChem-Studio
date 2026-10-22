"""Naming round 79 (D-361 .. D-363): the defects a SCAN OF THE RING TABLE finds.

The population is new. Every substitutable ring atom of every curated ring is given one substituent (OH, Cl, CO2H, NH2; 2,800 molecules), two (Cl and OH; 944), and every aromatic ring is turned
into its ring ketone or diketone (one atom in a ring double bond becomes C=O and its partner takes the hydrogen: 770), each named and read back through OPSIN on the standard InChIKey.
The substituent scans are clean apart from the stereo defaults OPSIN gives a cephem, a penam, a carbapenem or a morphinan (a read-back with stereo for a drawing with none); the finds:

* D-361 a ring ALCOHOL on an sp3 carbon of a bridged fusion parent (`2,6-methano-3-benzazocine`) was planned by the P-58.2 hydrogen module on the mancude skeleton, which has no atom for the
  bridge: `2,3,4,5,6,11-hexahydro-1H-2,6-methano-3-benzazocin-1-ol`, a name OPSIN cannot read (the bridge carbon is `11`). The module declines a parent with a bridge prefix, and the
  hydro parent's own text stands: `1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocin-1-ol`.
* D-362 a ring CATION with an `oxo` prefix (chromenylium, thiochromenylium, the selenium and tellurium analogues and the iso forms, and an N-substituted pyridinium) said nothing of the hydrogens the ketone needs:
  `3-oxochromenylium`, which OPSIN reads as ANOTHER tautomer (C2H2 for C4H2); `1-methyl-3-oxopyridin-1-ium` named BOTH 3-oxo-3,4-dihydro and 3-oxo-2,3-dihydro. The oxo carbon is planned as a ring C=X group and said as hydro prefixes (`3-oxo-3,4-dihydrochromenylium`).
* D-363 the curated 3H-pyrrolo[2,3-d]pyrimidine had no atom locants at all, so the generic numbering counted its pyrrole nitrogen as 8: `3,8-dihydro-2H-pyrrolo[2,3-d]pyrimidin-2-one`.
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
    ("an alcohol on a bridged benzazocine", "OC1c2ccccc2C2CCNC1C2", "1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocin-1-ol"),
    ("...on another carbon", "OC1CC2CC(Cc3ccccc32)N1", "1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocin-4-ol"),
    ("...on a bridged azepinoquinoxaline", "OC12CNCC(C1)c1cc3nccnc3cc12", "7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxalin-6-ol"),
    ("a ketone on chromenylium", "O=C1C=[O+]c2ccccc2C1", "3-oxo-3,4-dihydrochromenylium"),
    ("...on the benzo ring", "O=C1C=CC=C2C=CC=[O+]C12", "8-oxo-8,8a-dihydrochromenylium"),
    ("...on thiochromenylium", "O=C1C=[S+]c2ccccc2C1", "3-oxo-3,4-dihydrothiochromenylium"),
    ("...on tellurochromenylium, beside the hyphen rule", "O=C1C=[Te+]c2ccccc2C1", "3-oxo-3,4-dihydro-tellurochromenylium"),
    ("...on an isochromenylium", "O=C1Cc2ccccc2C=[Se+]1", "3-oxo-3,4-dihydroisoselenochromenylium"),
    ("an N-methylpyridinium with a ketone, hydrogen on C4", "O=C1CC=C[N+](C)=C1", "1-methyl-3-oxo-3,4-dihydropyridin-1-ium"),
    ("...hydrogen on C2: the other molecule, once named the same", "O=C1C=CC=[N+](C)C1", "1-methyl-3-oxo-2,3-dihydropyridin-1-ium"),
    ("a pyrrolopyrimidinone with its hydrogen on N3", "O=c1nc2[nH]ccc2c[nH]1", "3,7-dihydro-2H-pyrrolo[2,3-d]pyrimidin-2-one"),
    ("...drawn the other way", "O=c1[nH]cc2cc[nH]c2n1", "3,7-dihydro-2H-pyrrolo[2,3-d]pyrimidin-2-one"),
]

KEPT = [
    ("the bridged benzazocine alone", "C1C2NCCC(c3ccccc31)C2", "1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine"),
    ("...with a methyl", "CC1c2ccccc2C2CCNC1C2", "1-methyl-1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine"),
    ("chromenylium alone", "c1ccc2[o+]cccc2c1", "chromenylium"),
    ("a substituted cation with no ketone", "Cc1cc[o+]c2ccccc12", "4-methylchromenylium"),
    ("a quinolone acid keeps its oxo prefix", "O=C(O)c1c[nH]c2ccccc2c1=O", "4-oxo-1H-quinoline-3-carboxylic acid"),
    ("a saturated quaternary ammonium with a ketone is no pi atom", "O=C1CC[N+]2(C)CCc3ccccc3C2C1", "5-methyl-2-oxo-1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinolin-5-ium"),
    ("the 7H tautomer alone", "c1ncc2cc[nH]c2n1", "7H-pyrrolo[2,3-d]pyrimidine"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[r[0] for r in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in ALL], ids=[r[0] for r in ALL])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)
