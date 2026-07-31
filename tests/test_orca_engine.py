from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import (
    METHOD_BASIS_PRESETS,
    NMR_METHOD_BASIS,
    SOLVENTS,
    OrcaOutputError,
    OrcaQuantumEngineProvider,
)
from openchem.domain.common import CacheState
from openchem.domain.scientific_result import NMRSpectrumResult

# A verbatim excerpt (not trimmed/reworded) from a REAL ORCA 6.1.1 run --
# `! HF STO-3G NMR` on water -- captured live via a real installed ORCA
# executable during Phase 12's implementation. Unlike FIXTURE_OUTPUT below
# (SCF/thermochemistry/cartesian-coordinates, not independently verified
# this session), every line here is copied exactly from real ORCA output,
# not reconstructed from documentation.
REAL_NMR_FIXTURE_OUTPUT = """
                         Program Version 6.1.1  -  RELEASE   -

FINAL SINGLE POINT ENERGY       -74.963023138558

--------------------------------
CHEMICAL SHIELDING SUMMARY (ppm)
--------------------------------


  Nucleus  Element    Isotropic     Anisotropy
  -------  -------  ------------   ------------
      0       O          365.694          4.029
      1       H           33.679         15.151
      2       H           33.679         15.151


NMR shielding tensor and spin rotation calculation done in   0.0 sec

Maximum memory used throughout the entire PROP-calculation: 2.1 MB
"""

# A verbatim excerpt from a REAL ORCA 6.1.1 run -- `! HF STO-3G NMR` on
# formaldehyde (H2C=O) with a `%eprnmr Nuclei = all C,H { shift, ssall }`
# block placed AFTER the coordinate block (confirmed live: ORCA aborts at
# startup with "nuclear properties are requested but no coordinates have
# been read" if the block precedes coordinates -- the opposite ordering
# every other ORCA block in this file uses). Captured live via the real
# installed ORCA executable during Phase 22's implementation, the same
# discipline REAL_NMR_FIXTURE_OUTPUT above already established. Real
# values sanity-checked: 1J(C-H) ~122 Hz >> 2J(H-H, geminal) ~38 Hz, the
# right relative ordering for this chemistry even at this crude
# minimal-basis level of theory.
REAL_COUPLING_FIXTURE_OUTPUT = """
                         Program Version 6.1.1  -  RELEASE   -

FINAL SINGLE POINT ENERGY      -112.352352895878

--------------------------------
CHEMICAL SHIELDING SUMMARY (ppm)
--------------------------------


  Nucleus  Element    Isotropic     Anisotropy
  -------  -------  ------------   ------------
      0       C           97.747        142.432
      2       H           22.536          6.475
      3       H           22.536          6.475


NMR shielding tensor and spin rotation calculation done in   0.0 sec

-----------------------------------------------------------------------------
                SUMMARY OF ISOTROPIC COUPLING CONSTANTS J (Hz)
-----------------------------------------------------------------------------
                  0 C        2 H        3 H
      0 C        0.000    122.043    122.043
      2 H      122.043      0.000     37.978
      3 H      122.043     37.978      0.000

NMR spin-spin coupling calculation done in   0.0 sec

Maximum memory used throughout the entire PROP-calculation: 2.2 MB
"""

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


def test_build_input_nmr_includes_keyword():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    text = provider.build_input(mol, charge=0, multiplicity=1, method_basis="HF STO-3G", calc_type="nmr")

    assert text.startswith("! HF STO-3G NMR")


def test_build_input_carries_a_cpcm_solvent_keyword_through_method_basis():
    """The panel appends CPCM(...) to method_basis rather than passing a
    separate solvent argument -- confirmed live against ORCA 6.1.1, which
    accepts it as a plain header keyword and reports CPCM as active."""
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    text = provider.build_input(
        mol, charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1 CPCM(Chloroform)", calc_type="nmr"
    )

    assert text.startswith("! B3LYP pcSseg-1 CPCM(Chloroform) NMR")


def test_nmr_preset_is_one_of_the_offered_presets():
    """The panel only preselects NMR_METHOD_BASIS when the current text is
    an untouched preset, and compares against METHOD_BASIS_PRESETS -- if the
    NMR preset ever fell out of that list the preselect would fire once and
    then never again."""
    assert NMR_METHOD_BASIS in METHOD_BASIS_PRESETS


def test_solvents_start_with_gas_phase():
    """Empty string first means the combo defaults to gas phase, so existing
    jobs and every already-cached TMS reference keep their exact header."""
    assert SOLVENTS[0] == ""


def test_parse_output_nmr_still_extracts_scf_energy_and_version():
    """A pure `! NMR` job still needs a converged SCF first -- confirmed
    live that 'FINAL SINGLE POINT ENERGY' is present even with no Opt/Freq
    keyword. calc_type='nmr' isn't 'opt'/'opt_freq', so no conformer."""
    provider = OrcaQuantumEngineProvider()
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))

    descriptors, conformer = provider.parse_output(REAL_NMR_FIXTURE_OUTPUT, mol, "mol-1", "nmr")

    assert len(descriptors) == 1
    assert descriptors[0].descriptor_id == "orca.scf_energy"
    assert descriptors[0].value == pytest.approx(-74.963023138558)
    assert descriptors[0].provenance.parameters["orca_version"] == "6.1.1"
    assert conformer is None


def test_parse_spectrum_output_extracts_real_shielding_values():
    provider = OrcaQuantumEngineProvider()
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))

    spectrum = provider.parse_spectrum_output(REAL_NMR_FIXTURE_OUTPUT, mol, "mol-1", "nmr")

    assert spectrum is not None
    assert spectrum.spectrum_type == "nmr_raw_shielding"
    assert spectrum.molecule_uuid == "mol-1"
    assert spectrum.values == {0: 365.694, 1: 33.679, 2: 33.679}
    assert spectrum.elements == {0: "O", 1: "H", 2: "H"}
    assert spectrum.provenance is not None
    assert spectrum.provenance.method == "orca"
    assert spectrum.provenance.parameters["orca_version"] == "6.1.1"
    # Phase 22: NMRSpectrumResult (not the bare SpectrumResult) so the
    # empirical estimator's ranges field has somewhere to live -- the ORCA
    # path just never populates it.
    assert isinstance(spectrum, NMRSpectrumResult)
    assert spectrum.ranges is None


def test_parse_spectrum_output_returns_none_for_non_nmr_calc_types():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    assert provider.parse_spectrum_output(FIXTURE_OUTPUT, mol, "mol-1", "sp") is None
    assert provider.parse_spectrum_output(FIXTURE_OUTPUT, mol, "mol-1", "opt") is None
    assert provider.parse_spectrum_output(FIXTURE_OUTPUT, mol, "mol-1", "opt_freq") is None


def test_parse_spectrum_output_missing_summary_raises():
    provider = OrcaQuantumEngineProvider()
    mol = _ethanol_mol()

    with pytest.raises(OrcaOutputError):
        provider.parse_spectrum_output("ORCA crashed, no NMR results here", mol, "mol-1", "nmr")


def test_build_input_nmr_coupling_puts_eprnmr_block_after_coordinates():
    """Regression test for the real ordering requirement confirmed live:
    ORCA aborts if %eprnmr precedes coordinates."""
    provider = OrcaQuantumEngineProvider()
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)

    input_text = provider.build_input(mol, 0, 1, "HF STO-3G", "nmr_coupling")

    coord_block_end = input_text.rindex("*")
    eprnmr_index = input_text.index("%eprnmr")
    assert eprnmr_index > coord_block_end
    assert "ssall" in input_text


def test_parse_spectrum_output_works_for_nmr_coupling_calc_type():
    provider = OrcaQuantumEngineProvider()
    mol = Chem.AddHs(Chem.MolFromSmiles("C=O"))

    spectrum = provider.parse_spectrum_output(REAL_COUPLING_FIXTURE_OUTPUT, mol, "mol-1", "nmr_coupling")

    assert spectrum is not None
    assert spectrum.values == {0: 97.747, 2: 22.536, 3: 22.536}


def test_parse_spin_spin_coupling_extracts_real_values():
    provider = OrcaQuantumEngineProvider()

    couplings = provider.parse_spin_spin_coupling(REAL_COUPLING_FIXTURE_OUTPUT, "nmr_coupling")

    assert couplings == {(0, 2): 122.043, (0, 3): 122.043, (2, 3): 37.978}
    # 1J(C-H) must be much larger than 2J(H-H, geminal) -- real formaldehyde
    # chemistry, not an artifact of the parser.
    assert couplings[(0, 2)] > couplings[(2, 3)]


def test_parse_spin_spin_coupling_returns_none_for_other_calc_types():
    provider = OrcaQuantumEngineProvider()

    assert provider.parse_spin_spin_coupling(REAL_COUPLING_FIXTURE_OUTPUT, "nmr") is None
    assert provider.parse_spin_spin_coupling(FIXTURE_OUTPUT, "sp") is None


def test_parse_spin_spin_coupling_missing_summary_raises():
    provider = OrcaQuantumEngineProvider()

    with pytest.raises(OrcaOutputError):
        provider.parse_spin_spin_coupling("ORCA crashed, no coupling results here", "nmr_coupling")
