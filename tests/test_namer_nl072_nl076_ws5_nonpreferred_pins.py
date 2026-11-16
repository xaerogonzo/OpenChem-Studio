"""WS5 P3: NL-072..NL-076 — candidate-generation spellings that OPSIN round-trip (round 8 rows 805–819).

Programme disposition (2026-11-15): **closed** as non-preferred but **structurally correct**. The Blue Book
prints different constructions for several of these; the engine's names read back and stay the documented PIN for
regression. Book targets are cited in ``src/openchem/vendor/KNOWN_LIMITATIONS.md`` (Open after naming round 8).

NL-074 note: di-tert-butyl dicarbonate now names ``bis(2-methylpropan-2-yl) carbonate`` (D-128 carbonate work); the
plan's long systematic spelling is historical.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, engine pin) — SMILES from tests/fixtures/naming_cation_shapes.txt / KNOWN_LIMITATIONS round 8.
PINS = [
  ("NL-072 thioamide", "CON(C)C(=S)C", "N-methoxy-N-methyl-1-thioxoethan-1-amine"),
  ("NL-072 dialkoxy amide", "CON(OC)C(=O)C", "1-(dimethoxyamino)-1-oxoethane"),
  ("NL-072 aminooxy", "CON", "(aminooxy)methane"),
  ("NL-073 glycerol trinitrate", "O=[N+]([O-])OCC(CO[N+](=O)[O-])O[N+](=O)[O-]", "1,2,3-tris(nitrooxy)propane"),
  ("NL-074 chloroformate", "COC(=O)Cl", "methoxymethanoyl chloride"),
  ("NL-074 di-tert-butyl carbonate", "CC(C)(C)OC(=O)OC(C)(C)C", "bis(2-methylpropan-2-yl) carbonate"),
  ("NL-075 benzil", "O=C(c1ccccc1)C(=O)c1ccccc1", "1,2-diphenylethane-1,2-dione"),
  ("NL-076 diacetyl peroxide", "CC(=O)OOC(C)=O", "1-(acetylperoxy)-1-oxoethane"),
  ("NL-076 xanthate ester", "CCOC(=S)SC", "O-ethyl (methylsulfanyl)methanethioate"),
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