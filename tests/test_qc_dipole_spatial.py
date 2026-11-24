"""Quantum-history dipole overlay: this run's vector on this run's geometry."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dipole import _E_ANGSTROM_TO_DEBYE, centre_of_mass
from openchem.chem.qc_dipole import AU_TO_DEBYE, VECTOR_FRAME_JOB, VECTOR_ORIGIN_CARTESIAN, VECTOR_ORIGIN_COM
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus, new_run_id
from openchem.ui.history_entries import QC_PREFIX, entry_from_quantum_run
from openchem.ui.qc_dipole_spatial import dipole_arrow_for_run, run_geometry_molblock


def _molblock(seed: int) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)


def _dipole(
    *,
    value: float = AU_TO_DEBYE,
    vector=None,
    origin: str | None = VECTOR_ORIGIN_COM,
    frame: str = VECTOR_FRAME_JOB,
    provider: str = "orca",
    extra: dict | None = None,
) -> DescriptorValue:
    parameters = {"origin_independent": True}
    if extra:
        parameters.update(extra)
    if vector is None:
        vector = [AU_TO_DEBYE, 0.0, 0.0]
    if origin is not None:
        parameters["vector"] = list(vector)
        parameters["vector_origin"] = origin
        parameters["vector_frame"] = frame
    elif vector is not None and extra and "vector" in extra:
        pass
    return DescriptorValue(
        descriptor_id=f"{provider}.dipole_moment",
        name="Dipole",
        units="Debye",
        category="quantum_chemistry",
        provider=provider,
        molecule_uuid="m1",
        value=value,
        timestamp=1.0,
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(created_by="core", method=provider, parameters=parameters, timestamp=1.0),
    )


def _run(
    *,
    calc_type: str = "sp",
    charge: int = 0,
    provider: str = "orca",
    input_molblock: str = "",
    output_conformer_id: str | None = None,
    descriptors: list | None = None,
    molecule_uuid: str = "m1",
) -> QuantumChemistryRun:
    return QuantumChemistryRun(
        run_id=new_run_id(),
        molecule_uuid=molecule_uuid,
        calc_type=calc_type,
        method_basis="B3LYP def2-SVP",
        charge=charge,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp",
        input_molblock=input_molblock,
        provider=provider,
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        output_conformer_id=output_conformer_id,
        results={"descriptors": list(descriptors or [])},
        output_status={},
    )


def test_sp_uses_input_molblock_not_a_later_canonical():
    submitted, canonical = _molblock(1), _molblock(7)
    assert submitted != canonical
    molecule = MoleculeModel(uuid="m1", conformers=[ConformerModel(molblock=canonical)])
    run = _run(calc_type="sp", input_molblock=submitted, descriptors=[_dipole()])
    assert run_geometry_molblock(run, molecule) == submitted
    entry = entry_from_quantum_run(run, {}, 1, molecule=molecule)
    assert entry.spatial
    mol = Chem.MolFromMolBlock(submitted, removeHs=False)
    assert entry.spatial[0].anchor == pytest.approx(tuple(float(v) for v in centre_of_mass(mol)))


def test_opt_uses_that_output_conformer_while_a_newer_opt_exists():
    older, newer = _molblock(3), _molblock(11)
    assert older != newer
    kept = ConformerModel(molblock=older)
    later = ConformerModel(molblock=newer)
    molecule = MoleculeModel(uuid="m1", conformers=[kept, later])
    run = _run(
        calc_type="opt",
        input_molblock=older,
        output_conformer_id=kept.conformer_id,
        descriptors=[_dipole()],
    )
    assert run_geometry_molblock(run, molecule) == older
    entry = entry_from_quantum_run(run, {}, 1, molecule=molecule)
    loaded = Chem.MolFromMolBlock(older, removeHs=False)
    assert entry.spatial[0].anchor == pytest.approx(tuple(float(v) for v in centre_of_mass(loaded)))


def test_opt_freq_uses_output_conformer_id():
    block = _molblock(5)
    conf = ConformerModel(molblock=block)
    molecule = MoleculeModel(uuid="m1", conformers=[conf])
    run = _run(
        calc_type="opt_freq",
        input_molblock=block,
        output_conformer_id=conf.conformer_id,
        descriptors=[_dipole()],
    )
    assert run_geometry_molblock(run, molecule) == block


def test_missing_output_conformer_has_no_overlay():
    block = _molblock(5)
    molecule = MoleculeModel(uuid="m1", conformers=[ConformerModel(molblock=block)])
    run = _run(calc_type="opt", input_molblock=block, output_conformer_id=None, descriptors=[_dipole()])
    entry = entry_from_quantum_run(run, {}, 1, molecule=molecule)
    assert entry.spatial == ()
    assert run_geometry_molblock(run, molecule) is None


def test_missing_vector_keeps_magnitude_without_spatial():
    block = _molblock(1)
    dipole = _dipole()
    dipole.provenance.parameters.pop("vector")
    dipole.provenance.parameters.pop("vector_origin")
    dipole.provenance.parameters.pop("vector_frame")
    run = _run(input_molblock=block, descriptors=[dipole])
    entry = entry_from_quantum_run(run, {}, 1, molecule=MoleculeModel(uuid="m1"))
    assert entry.spatial == ()
    assert run.results["descriptors"][0].value == pytest.approx(AU_TO_DEBYE)


def test_zero_displayed_magnitude_has_no_arrow():
    block = _molblock(1)
    run = _run(
        input_molblock=block,
        descriptors=[_dipole(value=0.004, vector=[0.004, 0.0, 0.0])],
    )
    assert dipole_arrow_for_run(run, block) is None
    entry = entry_from_quantum_run(run, {}, 1, molecule=MoleculeModel(uuid="m1"))
    assert entry.spatial == ()


def test_neutral_overlay_direction_com_and_label():
    block = _molblock(1)
    mol = Chem.MolFromMolBlock(block, removeHs=False)
    vector = (AU_TO_DEBYE, 0.0, 0.0)
    run = _run(input_molblock=block, descriptors=[_dipole(vector=vector)])
    arrow = dipole_arrow_for_run(run, block)
    assert arrow is not None
    assert arrow.vector == pytest.approx(vector)
    assert arrow.anchor == pytest.approx(tuple(float(v) for v in centre_of_mass(mol)))
    assert arrow.units == "D"
    assert arrow.label == "2.54 D"


def test_charged_cartesian_vector_is_translated_with_run_charge():
    block = _molblock(1)
    mol = Chem.MolFromMolBlock(block, removeHs=False)
    com = centre_of_mass(mol)
    vector = (AU_TO_DEBYE, 0.0, 0.0)
    run = _run(
        charge=-1,
        input_molblock=block,
        descriptors=[_dipole(vector=vector, origin=VECTOR_ORIGIN_CARTESIAN)],
    )
    arrow = dipole_arrow_for_run(run, block)
    expected = tuple(vector[i] - (-1) * _E_ANGSTROM_TO_DEBYE * float(com[i]) for i in range(3))
    assert arrow is not None
    assert arrow.vector == pytest.approx(expected)
    assert arrow.anchor == pytest.approx(tuple(float(v) for v in com))


def test_charged_missing_origin_has_no_arrow():
    block = _molblock(1)
    dipole = _dipole(origin=None, extra={"vector": [AU_TO_DEBYE, 0.0, 0.0], "vector_frame": VECTOR_FRAME_JOB})
    run = _run(charge=-1, input_molblock=block, descriptors=[dipole])
    assert dipole_arrow_for_run(run, block) is None


def test_com_origin_does_not_translate_a_charged_vector():
    block = _molblock(1)
    vector = (AU_TO_DEBYE, 0.0, 0.0)
    run = _run(
        charge=-1,
        input_molblock=block,
        descriptors=[_dipole(vector=vector, origin=VECTOR_ORIGIN_COM)],
    )
    arrow = dipole_arrow_for_run(run, block)
    assert arrow is not None
    assert arrow.vector == pytest.approx(vector)
