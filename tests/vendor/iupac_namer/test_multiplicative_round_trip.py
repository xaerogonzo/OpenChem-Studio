"""Naming round 5 (N4): every multiplicative, hydrazine-parent and sulfamic
name the engine now emits parses back through OPSIN to the structure named.

The name expectations live in tests/test_namer_multiplicative.py and the
D-087 rows of tests/test_namer_known_defects.py; this file is the round trip,
which needs Java and so runs with the vendored suite.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer.engine import name_smiles

CASES = [
    "OC(=O)c1ccc(Sc2ccc(C(O)=O)cc2)cc1",
    "c1ccc(OOc2ccccc2)cc1",
    "OCCSCCO",
    "[SiH3]CCCCCCCCCCCCCCOCCCCCCCCCCCCCC[SiH3]",
    "OC(=O)C1CCC(OC2CCC(C(O)=O)CC2)CC1",
    "OS(=O)(=O)c1ccc(Oc2ccc(S(O)(=O)=O)cc2)cc1",
    "OC(=O)COCC(O)=O",
    "OC(=O)CCOCCC(O)=O",
    "OC(=O)CP(CC(O)=O)CC(O)=O",
    "OP(O)(=O)CNCP(O)(O)=O",
    "OP(O)(=O)CP(O)(O)=O",
    "NCCOCCN",
    "OC(=O)COCCOCCOCC(O)=O",
    "CC(=O)NNCNNC(C)=O",
    "Nc1ccc(NCNc2ccc(N)cc2)cc1",
    "Brc1ccc(Oc2ccc(Br)cc2)cc1",
    "OC(=O)c1ccc(Oc2ccc(C(O)=O)c(Br)c2)cc1Br",
    "CN(C)C(=O)CCSCCC(=O)N(C)C",
    "c1ccccc1Cc1ccccc1",
    "OC(=O)CSCC(O)=O",
    "OC(=O)c1ccc(OCCOc2ccc(C(O)=O)cc2)cc1",
    "OC(=O)c1ccccc1CCOCCOCCOCCc1ccccc1C(O)=O",
    "NC(N)=NCCCCCCCCCCCCCCN=C(N)N",
    "C[Si](C)(C)CC[Si](C)(C)C",
    "OC(=O)c1ccc(C(=O)c2ccc(C(O)=O)cc2)cc1",
    "NNc1ccccc1",
    "NNC(N)=O",
    "NNC(=O)Nc1ccccc1",
    "CNC(=O)N(C)N",
    "CCCC(CC)=NNC(=O)N(c1ccccc1)c1ccccc1",
    "NNC(=O)O",
    "NNC(=O)NN",
    "O=C(NN)c1ccccc1S(=O)(=O)O",
    "C[Si](C)(C)c1ccccn1",
    "NS(=O)(=O)O",
    "CNS(=O)(=O)O",
    "CN(C)S(=O)(=O)O",
    "C1C=NN(c2ccccc2)C1",
]


def _canonical(smiles: str | None) -> str | None:
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    return Chem.MolToSmiles(mol) if mol is not None else None


@pytest.mark.parametrize("smiles", CASES)
def test_the_name_parses_back_to_the_structure(smiles: str) -> None:
    try:
        from py2opsin import py2opsin
    except ImportError:  # pragma: no cover - py2opsin is in test extras
        pytest.skip("py2opsin not installed")
    name = name_smiles(smiles)
    assert _canonical(py2opsin(name)) == _canonical(smiles), name
