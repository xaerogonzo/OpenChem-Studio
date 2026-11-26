"""Last complete QC dipole block: shared a.u.→Debye, fail-closed vector."""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dipole import _E_ANGSTROM_TO_DEBYE, centre_of_mass
from openchem.chem.qc_dipole import (
    AU_TO_DEBYE,
    VECTOR_FRAME_JOB,
    VECTOR_ORIGIN_CARTESIAN,
    VECTOR_ORIGIN_COM,
    com_referenced_dipole_debye,
    dipole_descriptor,
    parse_orca_dipole,
    parse_psi4_dipole,
    parse_xtb_dipole,
    run_geometry_molblock,
    vector_matches_magnitude,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus, new_run_id


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


def _helper_molblock(smiles: str = "CCO", seed: int = 1) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)


def _helper_dipole(
    *,
    value: float = AU_TO_DEBYE,
    vector=None,
    origin: str | None = VECTOR_ORIGIN_COM,
    frame: str = VECTOR_FRAME_JOB,
    provider: str = "orca",
    units: str = "Debye",
) -> DescriptorValue:
    parameters = {"origin_independent": True}
    if vector is None and origin is not None:
        vector = [AU_TO_DEBYE, 0.0, 0.0]
    if origin is not None:
        parameters["vector"] = list(vector)
        parameters["vector_origin"] = origin
        parameters["vector_frame"] = frame
    return DescriptorValue(
        descriptor_id=f"{provider}.dipole_moment",
        name="Dipole",
        units=units,
        category="quantum_chemistry",
        provider=provider,
        molecule_uuid="m1",
        value=value,
        timestamp=1.0,
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(created_by="core", method=provider, parameters=parameters, timestamp=1.0),
    )


def _helper_run(*, charge: int = 0, descriptors=None, calc_type: str = "sp", **kwargs) -> QuantumChemistryRun:
    kwargs.setdefault("input_molblock", "")
    return QuantumChemistryRun(
        run_id=new_run_id(),
        molecule_uuid="m1",
        calc_type=calc_type,
        method_basis="B3LYP def2-SVP",
        charge=charge,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp",
        provider="orca",
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results={"descriptors": list(descriptors or [])},
        output_status={},
        **kwargs,
    )


def test_charged_com_origin_returns_stored_magnitude_without_geometry() -> None:
    run = _helper_run(charge=1, descriptors=[_helper_dipole(origin=VECTOR_ORIGIN_COM)])
    assert com_referenced_dipole_debye(run, None) == pytest.approx(AU_TO_DEBYE)


def test_charged_cartesian_translates_by_signed_charge_and_com() -> None:
    block = _helper_molblock()
    mol = Chem.MolFromMolBlock(block, removeHs=False)
    com = centre_of_mass(mol)
    vector = (AU_TO_DEBYE, 0.0, 0.0)
    for charge in (1, -1):
        run = _helper_run(
            charge=charge,
            descriptors=[_helper_dipole(vector=vector, origin=VECTOR_ORIGIN_CARTESIAN)],
        )
        translated = tuple(vector[i] - charge * _E_ANGSTROM_TO_DEBYE * float(com[i]) for i in range(3))
        expected = math.hypot(translated[0], math.hypot(translated[1], translated[2]))
        assert com_referenced_dipole_debye(run, block) == pytest.approx(expected)
        assert com_referenced_dipole_debye(run, block) != pytest.approx(AU_TO_DEBYE)


def test_neutral_cartesian_keeps_stored_magnitude() -> None:
    block = _helper_molblock()
    run = _helper_run(
        charge=0,
        descriptors=[_helper_dipole(origin=VECTOR_ORIGIN_CARTESIAN)],
    )
    assert com_referenced_dipole_debye(run, block) == pytest.approx(AU_TO_DEBYE)


def test_neutral_without_vector_still_usable() -> None:
    dipole = _helper_dipole(origin=None)
    run = _helper_run(charge=0, descriptors=[dipole])
    assert com_referenced_dipole_debye(run, None) == pytest.approx(AU_TO_DEBYE)


def test_charged_cartesian_without_geometry_is_none() -> None:
    run = _helper_run(
        charge=1,
        descriptors=[_helper_dipole(origin=VECTOR_ORIGIN_CARTESIAN)],
    )
    assert com_referenced_dipole_debye(run, None) is None
    assert com_referenced_dipole_debye(run, "not a molblock") is None


def test_charged_unknown_origin_or_bad_vector_is_none() -> None:
    unknown = _helper_dipole()
    unknown.provenance.parameters["vector_origin"] = "principal_axes"
    assert com_referenced_dipole_debye(_helper_run(charge=1, descriptors=[unknown]), None) is None

    missing = _helper_dipole()
    missing.provenance.parameters.pop("vector")
    assert com_referenced_dipole_debye(_helper_run(charge=1, descriptors=[missing]), None) is None

    wrong_frame = _helper_dipole(frame="cma")
    assert com_referenced_dipole_debye(_helper_run(charge=1, descriptors=[wrong_frame]), None) is None

    nonfinite = _helper_dipole(vector=[float("nan"), 0.0, 0.0])
    assert com_referenced_dipole_debye(_helper_run(charge=1, descriptors=[nonfinite]), None) is None

    mismatch = _helper_dipole(value=9.0, vector=[AU_TO_DEBYE, 0.0, 0.0])
    assert com_referenced_dipole_debye(_helper_run(charge=1, descriptors=[mismatch]), None) is None


def test_duplicate_or_wrong_descriptor_is_none() -> None:
    dipole = _helper_dipole()
    run = _helper_run(charge=0, descriptors=[dipole, dipole])
    assert com_referenced_dipole_debye(run, None) is None
    wrong_provider = _helper_dipole(provider="psi4")
    run = _helper_run(charge=0, descriptors=[wrong_provider])
    assert com_referenced_dipole_debye(run, None) is None
    wrong_units = _helper_dipole(units="a.u.")
    run = _helper_run(charge=0, descriptors=[wrong_units])
    assert com_referenced_dipole_debye(run, None) is None
    nonfinite = _helper_dipole(value=float("inf"))
    run = _helper_run(charge=0, descriptors=[nonfinite])
    assert com_referenced_dipole_debye(run, None) is None


def test_opt_geometry_rejects_same_atom_count_different_species() -> None:
    ethanol = _helper_molblock("CCO", seed=1)
    ether = _helper_molblock("COC", seed=1)
    conf = ConformerModel(molblock=ether)
    molecule = MoleculeModel(uuid="m1", conformers=[conf])
    run = _helper_run(
        calc_type="opt",
        descriptors=[_helper_dipole()],
        input_molblock=ethanol,
        output_conformer_id=conf.conformer_id,
    )
    assert run_geometry_molblock(run, molecule) is None
