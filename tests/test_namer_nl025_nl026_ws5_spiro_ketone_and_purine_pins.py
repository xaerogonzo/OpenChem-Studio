"""WS5 P3: NL-025 and NL-026 — round 84 / 81 fixes pinned for programme closure.

NL-025 (R84d): a spiro ring ketone on a partner with one aromatic ring N-H is cited
``-4(1H)-one`` (D-377); bridgehead or sulfur partners use ``4H`` without that added
hydrogen (D-378); saturated lactam partners omit ``(1H)`` (round-84 KEPT row).

NL-026 (R81c): adenine joined through an exocyclic atom uses the purine parent,
``[(9H-purin-6-yl)amino]``, not the nucleoside ``adenin-9-yl`` (D-370). Ring
N-glycoside attachment still names ``9H-purin-9-yl`` (round-81 KEPT row).

Engine behaviour was fixed in naming rounds 84 and 81; this file is the programme
oracle beside ``tests/test_namer_round84_spiro_joints_of_lactam_rings_and_a_numbering_search_that_never_returned.py``
and ``tests/test_namer_round81_ring_pairs_n_linked_purines_added_hydrogen_and_bi_assemblies.py``.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NL025_PINS = [
    (
        "NL-025 D-377 aromatic NH → (1H)-one",
        "O=c1cc[nH]c2c1CC1(CC1)CC2",
        "spiro[5,6,7,8-tetrahydroquinoline-6,1'-cyclopropane]-4(1H)-one",
    ),
    (
        "NL-025 D-378 bridgehead ketone without (1H)",
        "O=c1ccnc2n1CCC1(CCCCC1)C2",
        "spiro[6,7,8,9-tetrahydro-4H-pyrido[1,2-a]pyrimidine-8,1'-cyclohexane]-4-one",
    ),
    (
        "NL-025 saturated spiro lactam ketone",
        "O=C1CC2(CCCCC2)Nc2ccccc12",
        "spiro[1,2,3,4-tetrahydroquinoline-2,1'-cyclohexane]-4-one",
    ),
]

NL026_PINS = [
    (
        "NL-026 D-370 adenine exocyclic amino",
        "O=C1NCCc2cnn(Nc3ncnc4[nH]cnc34)c21",
        "1-[(9H-purin-6-yl)amino]-1,4,5,6-tetrahydro-7H-pyrazolo[3,4-c]pyridin-7-one",
    ),
    (
        "NL-026 nucleoside still 9H-purin-9-yl",
        "OC1C(O)C(CO)OC1n1cnc2c(N)ncnc12",
        "2-(6-amino-9H-purin-9-yl)-5-(hydroxymethyl)oxolane-3,4-diol",
    ),
]

PINS = NL025_PINS + NL026_PINS


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
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


def test_nl026_exocyclic_adenine_link_not_adenin_yl():
    wrong = "1-(adenin-9-yl)-1,4,5,6-tetrahydro-7H-pyrazolo[3,4-c]pyridin-7-one"
    got = name_smiles("O=C1NCCc2cnn(Nc3ncnc4[nH]cnc34)c21")
    assert got != wrong
    assert "adenin-9-yl" not in got