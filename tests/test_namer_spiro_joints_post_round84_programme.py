"""Programme disposition: spiro joints after naming rounds 84–85 (D-376..D-379).

Fixes are pinned in ``test_namer_round84_spiro_joints_of_lactam_rings_*``,
``test_namer_round85_methanoazepinoquinoxaline_*``, and ``test_namer_nl025_nl026_ws5_spiro_ketone_and_purine_pins.py``.
This file holds round-84/85 exemplars plus one residual policy pin (saturated spiro lactam ketone without ``(1H)``).
Open adamantane-with-substituent naming errors stay in vendor ``KNOWN_LIMITATIONS`` (round 85 item a).
"""

from __future__ import annotations

import time

import pytest

from openchem.vendor.iupac_namer import name_smiles

FIXED = [
    (
        "round 84 quinolin-4(1H)-one spiro",
        "O=c1cc[nH]c2c1CC1(CC1)CC2",
        "spiro[5,6,7,8-tetrahydroquinoline-6,1'-cyclopropane]-4(1H)-one",
    ),
    (
        "round 85 hung molecule",
        "O=C1CC2(c3ccccc3N1)C1CNCC2c2cc3nccnc3cc21",
        "spiro[1,2,3,4-tetrahydroquinoline-4,12'-7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline]-2-one",
    ),
]

RESIDUAL = (
    "saturated spiro lactam ketone without (1H)",
    "O=C1CC2(CCCCC2)Nc2ccccc12",
    "spiro[1,2,3,4-tetrahydroquinoline-2,1'-cyclohexane]-4-one",
)


@pytest.mark.parametrize("label,smiles,expected", FIXED, ids=[p[0] for p in FIXED])
def test_spiro_joint_fixes_from_round84_and_85(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


def test_residual_saturated_spiro_lactam_ketone_omits_indicated_hydrogen():
    """Round 84 KEPT: only partners with an aromatic ring N-H take ``-4(1H)-one`` (NL-025)."""
    label, smiles, expected = RESIDUAL
    del label
    assert name_smiles(smiles) == expected
    assert "(1H)" not in expected


def test_large_bridged_spiro_names_in_seconds():
    start = time.time()
    name_smiles("O=C1CC2(c3ccccc3N1)C1CNCC2c2cc3nccnc3cc21")
    assert time.time() - start < 60