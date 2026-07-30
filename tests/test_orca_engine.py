from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaOutputError, OrcaQuantumEngineProvider
from openchem.domain.common import CacheState

# Best-effort fixture based on ORCA's documented/widely-referenced output
# shape (FINAL SINGLE POINT ENERGY, the CARTESIAN COORDINATES (ANGSTROEM)
# block repeated once per optimization step, and the THERMOCHEMISTRY
# section's labeled lines) -- NOT a byte-perfect transcript from a real
# ORCA run, since ORCA is external, separately-licensed software this
# project cannot install. See chem/orca_engine.py's module docstring.
FIXTURE_OUTPUT = """
Some ORCA banner text here
...

CARTESIAN COORDINATES (ANGSTROEM)
---------------------------------
  C      0.000000    0.000000    0.000000
  C      1.500000    0.000000    0.000000
  O      2.200000    1.100000    0.000000
  H     -0.500000    0.900000    0.000000
  H     -0.500000   -0.900000    0.700000
  H     -0.500000   -0.900000   -0.700000
  H      1.900000    0.500000    0.900000
  H      1.900000    0.500000   -0.900000
  H      3.150000    0.950000    0.000000

Geometry convergence not reached, continuing...

CARTESIAN COORDINATES (ANGSTROEM)
---------------------------------
  C      0.010000    0.000000    0.000000
  C      1.510000    0.000000    0.000000
  O      2.210000    1.110000    0.000000
  H     -0.490000    0.910000    0.000000
  H     -0.490000   -0.910000    0.710000
  H     -0.490000   -0.910000   -0.710000
  H      1.910000    0.510000    0.910000
  H      1.910000    0.510000   -0.910000
  H      3.160000    0.960000    0.000000

*** OPTIMIZATION RUN DONE ***

-------------------------
THERMOCHEMISTRY AT 298.15K
-------------------------

Electronic energy                ...    -154.987654 Eh
Zero point energy                ...       0.080123 Eh
Total thermal energy                    -154.900000 Eh

Total enthalpy                   ...    -154.899000 Eh

Final entropy term                ...       0.023456 Eh
G-E(el)                           ...      -0.030000 Eh
Final Gibbs free energy         ...    -154.922456 Eh

FINAL SINGLE POINT ENERGY      -154.987654123
"""


def _ethanol_mol() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return mol


def test_build_input_single_point():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    text = provider.build_input(mol, charge=0, multiplicity=1, method_basis="B3LYP def2-SVP", calc_type="sp")

    assert text.startswith("! B3LYP def2-SVP")
    assert "Opt" not in text.splitlines()[0]
    assert "* xyz 0 1" in text
    assert text.strip().endswith("*")
    # One coordinate line per atom.
    atom_lines = [
        line
        for line in text.splitlines()
        if line and line[0].isalpha() and not line.startswith(("!", "*"))
    ]
    assert len(atom_lines) == mol.GetNumAtoms()


def test_build_input_opt_freq_includes_keywords():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    text = provider.build_input(mol, charge=1, multiplicity=2, method_basis="PBE0 def2-TZVP", calc_type="opt_freq")

    assert text.startswith("! PBE0 def2-TZVP Opt Freq")
    assert "* xyz 1 2" in text


def test_build_input_unknown_calc_type_raises():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()
    with pytest.raises(ValueError):
        provider.build_input(mol, charge=0, multiplicity=1, method_basis="B3LYP def2-SVP", calc_type="bogus")


def test_command_args_matches_orca_invocation_convention():
    provider = OrcaQuantumEngineProvider()
    input_path = Path("scratch") / "job.inp"
    args = provider.command_args("/opt/orca/orca", input_path)
    assert args == ["/opt/orca/orca", str(input_path)]


def test_parse_output_sp_extracts_only_scf_energy():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    descriptors, conformer = provider.parse_output(FIXTURE_OUTPUT, mol, "mol-1", "sp")

    assert len(descriptors) == 1
    assert descriptors[0].descriptor_id == "orca.scf_energy"
    assert descriptors[0].value == pytest.approx(-154.987654123)
    assert descriptors[0].provider == "orca"
    assert descriptors[0].molecule_uuid == "mol-1"
    assert descriptors[0].cache_state == CacheState.COMPLETED
    assert conformer is None


def test_parse_output_opt_returns_optimized_conformer_from_last_block():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    descriptors, conformer = provider.parse_output(FIXTURE_OUTPUT, mol, "mol-1", "opt")

    assert len(descriptors) == 1  # no thermochemistry for a plain "opt"
    assert conformer is not None
    assert conformer.method == "orca_opt"
    # The LAST cartesian block's first atom is at x=0.01, not the first
    # block's x=0.0 -- confirms "last block wins."
    assert "0.0100" in conformer.molblock or "0.010000" in conformer.molblock.replace("  ", " ")


def test_parse_output_opt_freq_includes_thermochemistry():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    descriptors, conformer = provider.parse_output(FIXTURE_OUTPUT, mol, "mol-1", "opt_freq")

    descriptor_ids = {d.descriptor_id for d in descriptors}
    assert descriptor_ids == {
        "orca.scf_energy",
        "orca.enthalpy",
        "orca.entropy_term",
        "orca.gibbs_free_energy",
    }
    by_id = {d.descriptor_id: d.value for d in descriptors}
    assert by_id["orca.enthalpy"] == pytest.approx(-154.899000)
    assert by_id["orca.entropy_term"] == pytest.approx(0.023456)
    assert by_id["orca.gibbs_free_energy"] == pytest.approx(-154.922456)
    assert conformer is not None


def test_parse_output_missing_scf_energy_raises():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()
    with pytest.raises(OrcaOutputError):
        provider.parse_output("ORCA crashed, no results here", mol, "mol-1", "sp")


def test_parse_output_results_carry_provenance():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    descriptors, conformer = provider.parse_output(FIXTURE_OUTPUT, mol, "mol-1", "opt_freq")

    assert conformer is not None
    assert conformer.provenance is not None
    assert conformer.provenance.created_by == "core"
    assert conformer.provenance.method == "orca"
    for descriptor in descriptors:
        assert descriptor.provenance is not None
        assert descriptor.provenance.method == "orca"
    # Every descriptor + the conformer from the SAME call share one
    # Provenance instance (same timestamp), not independently-timed ones.
    assert len({d.provenance.timestamp for d in descriptors} | {conformer.provenance.timestamp}) == 1


def test_parse_output_atom_count_mismatch_skips_conformer():
    """If the cartesian block doesn't match the molecule's atom count (a
    differently-shaped block this regex wasn't meant to match), the
    conformer must be skipped, not silently mis-assigned."""
    provider = OrcaQuantumEngineProvider()
    mol = Chem.AddHs(Chem.MolFromSmiles("C"))  # methane: 5 atoms, not 9
    AllChem.EmbedMolecule(mol, randomSeed=1)

    descriptors, conformer = provider.parse_output(FIXTURE_OUTPUT, mol, "mol-1", "opt")

    assert len(descriptors) == 1
    assert conformer is None
