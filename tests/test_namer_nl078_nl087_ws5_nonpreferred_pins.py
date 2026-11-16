"""WS5 P3: NL-078, NL-079, NL-086, NL-087 — non-preferred names that OPSIN round-trip.

Programme disposition (2026-11-15): **closed** as structurally correct but not the Blue Book PIN.
SMILES for NL-078/079 are from ``benchmarks/naming/charged_panel_r4a.json`` (B3-hydrogen-* and A2-*).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PINS = [
    (
        "NL-078 phenylphosphonate anion",
        "OP(=O)([O-])c1ccccc1",
        "hydroxy(oxido)(oxo)(phenyl)phosphane",
    ),
    (
        "NL-078 phenyl hydrogen phosphate anion",
        "OP(=O)([O-])Oc1ccccc1",
        "hydroxy(oxido)(oxo)(phenoxy)phosphane",
    ),
    (
        "NL-079 alaninate",
        "CC(N)C(=O)[O-]",
        "2-aminopropanoate",
    ),
    (
        "NL-079 prolinate",
        "[O-]C(=O)C1CCCN1",
        "pyrrolidine-2-carboxylate",
    ),
    (
        "NL-079 (2S)-prolinate",
        "[O-]C(=O)[C@@H]1CCCN1",
        "(2S)-pyrrolidine-2-carboxylate",
    ),
    (
        "NL-086 phosphoryl on acetic acid",
        "CCP(=O)(CC)CC(=O)O",
        "[diethyl(oxo)phosphanyl]acetic acid",
    ),
    (
        "NL-087 tert-butyl as 2-methylpropan-2-yl",
        "CC(C)(C)[Si](C)(C)O",
        "dimethyl(2-methylpropan-2-yl)silanol",
    ),
]


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_nonpreferred_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_documented_name_round_trips(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, (smiles, expected)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )