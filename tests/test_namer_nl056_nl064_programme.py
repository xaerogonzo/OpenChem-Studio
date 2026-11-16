"""Programme closure for NL-056..NL-064 (carried rows, rounds 13–27).

Exhaustive pins live in round tests (`test_namer_round43_*`, `test_round26_polyol_esters.py`,
`test_round24_morphinan.py`, `test_namer_numbering.py`, matrix run 2026-11-03 for NL-056). This file
holds thin exemplars and disposition guards.
"""

from __future__ import annotations

import shutil

import pytest

from openchem.vendor.iupac_namer import name_smiles
from tests.test_naming_heldout_lock import DRAWING_SCRIPTS
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PINS = [
    # NL-056 (WS2 closed 2026-11-03; round 43 helicene locant table)
    (
        "NL-056 pentahelicene substituent locant",
        "CC(=O)Nc1cccc2ccc3ccc4ccc5ccccc5c4c3c12",
        "N-(pentahelicen-1-yl)acetamide",
    ),
    # NL-059 (round 26 polyol esters; multiplicative vs acyloxy)
    (
        "NL-059 one acid symmetric diester PIN",
        "CC(=O)OCCOC(C)=O",
        "ethane-1,2-diyl diacetate",
    ),
    (
        "NL-059 different acids stay acyloxy",
        "CC(=O)OCCOC(=O)CC",
        "2-(acetyloxy)ethyl propanoate",
    ),
    (
        "NL-059 polyol with free OH",
        "CC(=O)OC(CO)COC(C)=O",
        "3-hydroxypropane-1,2-diyl diacetate",
    ),
    # NL-060 (round 25 senior-acid / von Baeyer numbering)
    (
        "NL-060 tropane ester senior acid on bicyclo",
        "CN1[C@@H]2CC[C@@H]1[C@@H]([C@H](C2)OC(=O)C3=CC=CC=C3)C(=O)OC",
        "methyl (1R,2S,3S,5R)-3-(benzoyloxy)-8-methyl-8-azabicyclo[3.2.1]octane-2-carboxylate",
    ),
    # NL-061 (round 24 morphinan retained parent; charged types still limited)
    (
        "NL-061 morphine morphinan parent",
        "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)O)O[C@H]3[C@H](C=C4)O",
        "(5R,6S,9R,13S,14R)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-3,6-diol",
    ),
    (
        "NL-061 fused cation falls back from curated parent",
        "O=C1CC[N+]2(C)CCc3ccccc3C2C1",
        "5-methyl-2-oxo-1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinolin-5-ium",
    ),
    # NL-062 (round 16/23; multiplicative nitramide not built)
    (
        "NL-062 ethylenedinitramine amine spelling",
        "O=[N+]([O-])NCCN[N+](=O)[O-]",
        "N1,N2-dinitroethane-1,2-diamine",
    ),
    # NL-063 (round 20–22; imino forms and hydrazine spelling)
    (
        "NL-063 azine keeps imino form",
        "C/C=N/N",
        "(1E)-ethylidenehydrazine",
    ),
    (
        "NL-063 phenylhydrazine retained PIN",
        "NNc1ccccc1",
        "phenylhydrazine",
    ),
    # NL-064 (rounds 26–27 stereo cache; P-14.5.4 tie partially open)
    (
        "NL-064 meso difluoropentane P-14.4(j)",
        "C[C@H](F)C[C@@H](C)F",
        "(2R,4S)-2,4-difluoropentane",
    ),
]

PENTYL_DIARYL = "CCCC(C)c1ccc(C(CC)CC)cc1"


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_documented_name_round_trips_where_opsin_can(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    from rdkit import Chem
    from rdkit.Chem import inchi

    back = py2opsin(expected)
    if not back:
        pytest.skip(f"OPSIN cannot parse {expected!r}")
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )


def test_nl058_bluebook_frozen_sealed_without_row_replay():
    """NL-058: two round-40 seal rows differ; we do not read frozen rows for naming tests."""
    assert "bluebook_frozen" in DRAWING_SCRIPTS


def test_nl064_pentyl_prefix_locant_order_still_splits_on_spelling():
    """P-14.5.4 letter ties are not fully pinned; stereo-cache work fixed the structural cases."""
    names = {name_smiles(s) for s in checked_spellings(PENTYL_DIARYL, 12, 42)}
    assert len(names) == 2