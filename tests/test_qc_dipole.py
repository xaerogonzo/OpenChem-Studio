"""Last complete QC dipole block: shared a.u.→Debye, fail-closed vector."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.qc_dipole import (
    AU_TO_DEBYE,
    VECTOR_FRAME_JOB,
    VECTOR_ORIGIN_CARTESIAN,
    VECTOR_ORIGIN_COM,
    dipole_descriptor,
    parse_orca_dipole,
    parse_psi4_dipole,
    parse_xtb_dipole,
    vector_matches_magnitude,
)
from openchem.domain.common import Provenance


def _mol(smiles: str = "CCO") -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


def _prov() -> Provenance:
    return Provenance(created_by="core", method="test", parameters={}, timestamp=1.0)


def test_shared_conversion_is_psi4s_printed_factor() -> None:
    assert AU_TO_DEBYE == 2.5417464519


def test_xtb_three_decimal_tot_still_matches_the_converted_vector() -> None:
    """GFN2 ethanol SP: full XYZ −0.122, −0.564, 0.483 a.u. and tot 1.913 D."""
    vector = tuple(part * AU_TO_DEBYE for part in (-0.122, -0.564, 0.483))
    assert vector_matches_magnitude(vector, 1.913)


def test_a_tight_universal_epsilon_would_reject_that_gfn_table() -> None:
    vector = tuple(part * AU_TO_DEBYE for part in (-0.122, -0.564, 0.483))
    import math

    norm = math.hypot(vector[0], math.hypot(vector[1], vector[2]))
    assert abs(norm - 1.913) > 1e-6
    assert abs(norm - 1.913) <= 0.005


def test_mismatch_and_non_finite_omit_vector_only() -> None:
    mol = _mol()
    mismatch = dipole_descriptor(
        "orca", "u", 9.0, _prov(), mol,
        vector_au=(1.0, 0.0, 0.0), vector_origin=VECTOR_ORIGIN_COM,
    )
    assert mismatch is not None and mismatch.value == 9.0
    assert "vector" not in mismatch.provenance.parameters

    bad = dipole_descriptor(
        "orca", "u", 2.5417464519, _prov(), mol,
        vector_au=(float("nan"), 0.0, 0.0), vector_origin=VECTOR_ORIGIN_COM,
    )
    assert bad is not None and "vector" not in bad.provenance.parameters


def test_zero_magnitude_is_stored() -> None:
    mol = _mol("[CH3]")
    value = dipole_descriptor(
        "xtb", "u", 0.0, _prov(), mol,
        vector_au=(0.0, 0.0, 0.0), vector_origin=VECTOR_ORIGIN_CARTESIAN,
    )
    assert value is not None and value.value == 0.0
    assert value.provenance.parameters["vector"] == [0.0, 0.0, 0.0]


def test_unknown_origin_omits_vector() -> None:
    value = dipole_descriptor(
        "orca", "u", 2.5417464519, _prov(), _mol(),
        vector_au=(1.0, 0.0, 0.0), vector_origin=None,
    )
    assert value is not None and "vector" not in value.provenance.parameters
    assert "vector_origin" not in value.provenance.parameters
    assert "vector_frame" not in value.provenance.parameters


def test_complete_vector_stamps_origin_and_job_frame() -> None:
    value = dipole_descriptor(
        "orca", "u", 2.5417464519, _prov(), _mol(),
        vector_au=(1.0, 0.0, 0.0), vector_origin=VECTOR_ORIGIN_COM,
    )
    params = value.provenance.parameters
    assert params["vector"] == pytest.approx([AU_TO_DEBYE, 0.0, 0.0])
    assert params["vector_origin"] == VECTOR_ORIGIN_COM
    assert params["vector_frame"] == VECTOR_FRAME_JOB


def test_orca_parse_uses_the_same_block_for_xyz_and_magnitude() -> None:
    text = (
        "Total Dipole Moment    :      0.100000000       0.000000000       0.000000000\n"
        "Magnitude (Debye)      :      0.254174645\n"
        "Total Dipole Moment    :     -1.164262564       0.299844712      -0.000000024\n"
        "Magnitude (Debye)      :      3.055886271\n"
    )
    magnitude, vector_au, origin = parse_orca_dipole(text)
    assert magnitude == pytest.approx(3.055886271)
    assert vector_au == pytest.approx((-1.164262564, 0.299844712, -0.000000024))
    assert origin is None


def test_orca_origin_from_choice_of_electric_origin() -> None:
    text = (
        "Choice of electric origin   ... Center of mass\n"
        "Total Dipole Moment    :      1.000000000       0.000000000       0.000000000\n"
        "Magnitude (Debye)      :      2.5417464519\n"
    )
    _mag, _vec, origin = parse_orca_dipole(text)
    assert origin == VECTOR_ORIGIN_COM


def test_psi4_takes_the_total_column() -> None:
    text = (
        "Properties will be evaluated at   0.000000,   0.000000,   0.000000 [a0]\n"
        " Multipole Moments:\n"
        " Dipole X            :          1.0000000            2.0000000            0.1000000\n"
        " Dipole Y            :          0.0000000            0.0000000            0.0000000\n"
        " Dipole Z            :         -1.1583243            1.8324674            0.6741431\n"
        " Magnitude           :                                                    0.6815000\n"
    )
    _mag, vector_au, origin = parse_psi4_dipole(text)
    assert vector_au == pytest.approx((0.1000000, 0.0000000, 0.6741431))
    assert origin == VECTOR_ORIGIN_CARTESIAN


def test_psi4_missing_origin_line_returns_vector_without_origin() -> None:
    text = (
        " Multipole Moments:\n"
        " Dipole X            :          0.0000000            0.0000000            0.0000000\n"
        " Dipole Y            :          0.0000000            0.0000000            0.0000000\n"
        " Dipole Z            :         -0.7793841            0.0000000           -0.7793841\n"
        " Magnitude           :                                                    0.7793841\n"
    )
    magnitude, vector_au, origin = parse_psi4_dipole(text)
    assert magnitude == pytest.approx(0.7793841 * AU_TO_DEBYE)
    assert vector_au is not None
    assert origin is None


def test_xtb_gfn2_uses_full_not_q_only() -> None:
    text = (
        "molecular dipole:\n"
        "                 x           y           z       tot (Debye)\n"
        "   q only:     0.111       0.222       0.333       0.463\n"
        "     full:    -0.122      -0.564       0.483       1.913\n"
    )
    magnitude, vector_au, origin = parse_xtb_dipole(text)
    assert magnitude == pytest.approx(1.913)
    assert vector_au == pytest.approx((-0.122, -0.564, 0.483))
    assert origin == VECTOR_ORIGIN_CARTESIAN
