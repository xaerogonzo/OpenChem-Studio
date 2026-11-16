"""WS5 P2: NL-104 — programme disposition on naming round 14 residue.

Round 14 split clusters are largely fixed (D-151..D-161); this file re-measures thin
exemplars and points at ``test_namer_round42_spiro_stereo.py``, ``test_namer_round46_*``,
and ``test_namer_known_defects.py`` for the full set. OPSIN artifacts on sulfonamidate
anions are classed validator limits, not engine regressions.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN)")

_uncharge = rdMolStandardize.Uncharger()


def _neutral_inchi_key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return inchi.MolToInchiKey(_uncharge.uncharge(Chem.Mol(mol)))


PINS = [
    (
        "NL-104 D-162 hydroxamic ester (fixed round 14)",
        "CC(=O)OCC(=O)N(O)C",
        "2-[hydroxy(methyl)amino]-2-oxoethyl acetate",
    ),
    (
        "NL-104 sulfonamidate beside amide",
        "CC(=O)Nc1ccc(S(=O)(=O)[N-]c2ncccn2)cc1",
        "4-acetamido-N-(pyrimidin-2-yl)benzene-1-sulfonamidate",
    ),
    (
        "NL-104 spiro methano-benzazocine von Baeyer partner",
        "c1ccc2c(c1)CC1CC2CC2(N1)c1ccccc1C1CCNC2C1",
        "spiro[1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine-4,8'-10-azatricyclo[7.3.1.0^{2,7}]trideca-2(7),3,5-triene]",
    ),
]

D225 = (
    "NL-104 D-225 primed locant (fixed round 42; stereo needs OPSIN path)",
    "O=C1Nc2ccccc2[C@]12Oc1ccc([N+](=O)[O-])cc1[C@H]1CC(c3ccc(Cl)cc3)=NN12",
    "(3S,10b'R)-2'-(4-chlorophenyl)-9'-nitrospiro[2,3-dihydro-1H-indole-3,5'-1,10b-dihydro-5H-pyrazolo[1,5-c][1,3]benzoxazine]-2-one",
)


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
def test_d225_spiro_junction_letter_and_stereo_pinned_in_round42():
    label, smiles, expected = D225
    del label
    assert name_smiles(smiles) == expected


def test_nl104_sulfonamidate_name_carries_charge_in_words():
    smiles = PINS[1][1]
    name = name_smiles(smiles)
    assert "sulfonamidate" in name
    assert _check_charge_named(Chem.MolFromSmiles(smiles), name) is None


@needs_opsin
def test_nl104_sulfonamidate_opsin_reads_neutral_connectivity_only():
    """Round 14 classed two rows as OPSIN reading anion names as neutral sulfonamide."""
    from py2opsin import py2opsin

    smiles, expected = PINS[1][1], PINS[1][2]
    back = py2opsin(expected)
    assert back
    assert _neutral_inchi_key(back) == _neutral_inchi_key(smiles)