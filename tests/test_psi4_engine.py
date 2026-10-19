"""The Psi4 engine (`chem/psi4_engine.py`, `docs/PSI4_ENGINE_DESIGN.md`): the input it writes, the functional table, and the output it reads.

The outputs under `tests/fixtures/psi4/` are REAL Psi4 1.11 outputs (the spike of 2026-10-19, `psi4 -o stdout`), never hand-written: a parser written against what a manual says it prints is the
parser that fails on the first real run. The last test runs a real Psi4 when one is configured (`OPENCHEM_PSI4_EXE`) and is skipped otherwise.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import psi4_engine as pe
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.conformer import (
    ORCA_OPTIMIZED,
    PSI4_OPTIMIZED,
    QUANTUM_OPTIMIZED_METHODS,
    ConformerModel,
    conformer_choice_text,
    quantum_optimized_note,
)

FIXTURES = Path(__file__).parent / "fixtures" / "psi4"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _water() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


@pytest.fixture
def provider() -> pe.Psi4QuantumEngineProvider:
    return pe.Psi4QuantumEngineProvider(threads=lambda: 3)


# --- the input -------------------------------------------------------------------------------------------------------


def test_the_input_is_a_complete_psi4_job_with_nothing_left_to_a_default(provider):
    text = provider.build_input(_water(), 0, 1, "B3LYP def2-SVP", "sp")

    assert "molecule {" in text and "0 1" in text
    # the atoms stay where the molecule has them, in its order
    assert "symmetry c1" in text and "no_reorient" in text and "no_com" in text
    assert "set reference rhf" in text
    assert "set basis def2-SVP" in text
    # Pople bases are cartesian in Psi4 and spherical in ORCA: always spherical (1.8 mEh on 6-31G(d) water)
    assert "set puream true" in text
    assert "set scf_type df" in text and "set e_convergence 1e-8" in text
    assert text.rstrip().endswith("energy('b3lyp5')")


def test_b3lyp_means_the_functional_orcas_b3lyp_is_not_psi4s_b3lyp(provider):
    """THE TRAP, measured: Psi4's `b3lyp` is VWN1RPA and differs from ORCA's `B3LYP` by 37 mEh on water. The label must map to `b3lyp5`."""
    assert pe.PSI4_METHODS["b3lyp"] == "b3lyp5"
    assert pe.PSI4_METHODS["b3lyp/g"] == "b3lyp"
    assert "energy('b3lyp5')" in provider.build_input(_water(), 0, 1, "B3LYP def2-SVP", "sp")
    # compared case-insensitively
    assert "energy('b3lyp5')" in provider.build_input(_water(), 0, 1, "b3lyp def2-SVP", "sp")
    assert "energy('m06-2x')" in provider.build_input(_water(), 0, 1, "M062X def2-TZVP", "sp")
    assert "energy('scf')" in provider.build_input(_water(), 0, 1, "HF def2-SVP", "sp")


def test_an_open_shell_is_unrestricted_and_a_geometry_job_optimizes(provider):
    radical = provider.build_input(_water(), 1, 2, "B3LYP def2-SVP", "sp")
    assert "set reference uhf" in radical and "\n1 2\n" in radical

    assert provider.build_input(_water(), 0, 1, "PBE0 def2-TZVP", "opt").rstrip().endswith("optimize('pbe0')")


@pytest.mark.parametrize(
    "method_basis, fragment",
    [
        ("WB97X-D3 def2-SVP", "not offered"),  # a functional the table does not hold: never guessed
        ("B3LYP def2-SVP CPCM(Water)", "not 'B3LYP def2-SVP CPCM(Water)'"),  # a third word is refused, not dropped
        ("B3LYP", "a method and a basis"),
        ("", "a method and a basis"),
    ],
)
def test_an_input_the_engine_does_not_run_is_refused_by_name_and_never_changed(provider, method_basis, fragment):
    with pytest.raises(ValueError) as error:
        provider.build_input(_water(), 0, 1, method_basis, "sp")
    assert fragment in str(error.value)


def test_a_calculation_type_the_engine_does_not_run_is_refused(provider):
    for calc_type in ("nmr", "fukui", "delta_scf", "opt_freq", "led"):
        with pytest.raises(ValueError, match="does not run"):
            provider.build_input(_water(), 0, 1, "B3LYP def2-SVP", calc_type)


def test_the_command_takes_threads_and_stdout_and_survives_a_path_with_a_space(provider):
    args = provider.command_args(r"C:\Tools\psi4\Scripts\psi4.exe", Path(r"D:\a folder\job.inp"))

    assert args == [r"C:\Tools\psi4\Scripts\psi4.exe", "-n", "3", "-o", "stdout", str(Path(r"D:\a folder\job.inp"))]
    # a thread count below one is one, never zero
    assert pe.Psi4QuantumEngineProvider(threads=lambda: 0).command_args("psi4", Path("job.inp"))[2] == "1"


def test_the_engine_declares_what_it_runs_and_where_its_executable_is(provider):
    assert provider.supports("sp") and provider.supports("opt")
    assert not provider.supports("nmr") and not provider.supports("fukui")
    assert provider.engine_name() == "Psi4"
    assert provider.executable_setting() == "psi4/executable_path"
    assert provider.executable_names() == ("psi4",)
    # ORCA runs everything and keeps the setting it has always had
    orca = OrcaQuantumEngineProvider()
    assert orca.supports("fukui") and orca.supports("nmr")
    assert orca.engine_name() == "ORCA" and orca.executable_setting() == "orca/executable_path"


# --- the output, from real runs --------------------------------------------------------------------------------------


def test_a_single_point_reads_the_total_energy_and_names_what_ran(provider):
    descriptors, conformer = provider.parse_output(_fixture("water_b3lyp5_def2svp_sp.out"), _water(), "u-1", "sp")

    assert conformer is None
    [energy] = descriptors
    assert energy.descriptor_id == "psi4.scf_energy" and energy.units == "Hartree"
    assert energy.value == pytest.approx(-76.32100289408265, abs=1e-12)
    assert energy.provenance.parameters["psi4_version"] == "1.11"
    assert energy.provenance.parameters["scf_type"] == "df" and energy.provenance.parameters["puream"] is True


def test_an_open_shell_output_reads_too(provider):
    descriptors, _conformer = provider.parse_output(_fixture("oh_radical_uks_sp.out"), _water(), "u-1", "sp")

    assert descriptors[0].value == pytest.approx(-75.63397071477293, abs=1e-12)


def test_an_optimization_returns_the_final_geometry_as_a_psi4_conformer_and_the_last_energy(provider):
    mol = _water()
    descriptors, conformer = provider.parse_output(_fixture("water_b3lyp5_def2svp_opt.out"), mol, "u-1", "opt")

    # every step prints an energy; the one reported is the LAST, at the converged geometry
    assert descriptors[0].value == pytest.approx(-76.32118516654147, abs=1e-12)
    assert conformer is not None and conformer.method == PSI4_OPTIMIZED
    assert conformer.method != ORCA_OPTIMIZED
    optimized = Chem.MolFromMolBlock(conformer.molblock, removeHs=False)
    positions = optimized.GetConformer().GetPositions()
    # the final geometry of the run (Angstrom, the input's atom order: O, H, H; a molfile keeps four decimals)
    assert positions[0][2] == pytest.approx(0.127325399351, abs=1e-4)
    assert positions[1][1] == pytest.approx(0.756995261115, abs=1e-4)
    assert positions[2][2] == pytest.approx(-0.474212699675, abs=1e-4)


def test_a_geometry_that_does_not_fit_the_input_atoms_is_never_applied(provider):
    methane = Chem.AddHs(Chem.MolFromSmiles("C"))
    AllChem.EmbedMolecule(methane, randomSeed=7)

    with pytest.raises(pe.Psi4OutputError, match="final geometry has atoms"):
        provider.parse_output(_fixture("water_b3lyp5_def2svp_opt.out"), methane, "u-1", "opt")


def test_an_optimization_that_did_not_converge_is_a_failed_run_not_a_geometry(provider):
    text = _fixture("water_b3lyp5_def2svp_opt.out").replace("Optimizer: Optimization complete!", "Optimizer: stopped")

    with pytest.raises(pe.Psi4OutputError, match="did not converge"):
        provider.parse_output(text, _water(), "u-1", "opt")


@pytest.mark.parametrize(
    "fixture, expected",
    [
        ("water_unknown_method.out", "Method=nosuchfunctional is not available"),
        ("water_unknown_basis.out", "Unable to find a basis set"),
    ],
)
def test_a_failed_run_is_reported_in_psi4s_own_words(provider, fixture, expected):
    """MEASURED: a failing Psi4 run exits 1 and ends "Psi4 encountered an error" (no success banner). The service does not read the exit code,
    so the marker in the text is what turns the run into a failed one, and the failing statement's own box is the message."""
    text = _fixture(fixture)
    assert "Psi4 encountered an error" in text and "Psi4 exiting successfully" not in text

    with pytest.raises(pe.Psi4OutputError) as error:
        provider.parse_output(text, _water(), "u-1", "sp")
    assert expected in str(error.value)


def test_an_output_with_no_energy_is_a_failed_run(provider):
    with pytest.raises(pe.Psi4OutputError, match="without printing a total energy"):
        provider.parse_output("Psi4 1.11 release\nnothing useful\n", _water(), "u-1", "sp")


# --- the labels a geometry carries -----------------------------------------------------------------------------------


def test_a_psi4_geometry_is_a_quantum_optimized_conformer_labelled_as_psi4s():
    assert PSI4_OPTIMIZED in QUANTUM_OPTIMIZED_METHODS and ORCA_OPTIMIZED in QUANTUM_OPTIMIZED_METHODS
    psi4 = ConformerModel(method=PSI4_OPTIMIZED)
    orca = ConformerModel(method=ORCA_OPTIMIZED)

    assert conformer_choice_text([psi4], 0) == "1 - Psi4 optimized"
    assert conformer_choice_text([orca], 0) == "1 - ORCA optimized"
    assert quantum_optimized_note([psi4]) == "Psi4-optimized geometry"
    assert quantum_optimized_note([orca]) == "ORCA-optimized geometry"
    assert quantum_optimized_note([psi4, ConformerModel(method=PSI4_OPTIMIZED)]) == "2 Psi4-optimized conformers"
    # two engines' geometries are not all one engine's: "quantum", not the newest one's name for both
    assert quantum_optimized_note([psi4, orca]) == "2 quantum-optimized conformers"


# --- a real Psi4, when there is one ----------------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("OPENCHEM_PSI4_EXE"), reason="set OPENCHEM_PSI4_EXE to a real psi4 executable to run this")
def test_a_real_psi4_runs_the_input_this_engine_writes_and_the_parser_reads_it(tmp_path, provider):
    mol = _water()
    (tmp_path / "job.inp").write_text(provider.build_input(mol, 0, 1, "B3LYP def2-SVP", "opt"), encoding="utf-8")
    args = provider.command_args(os.environ["OPENCHEM_PSI4_EXE"], tmp_path / "job.inp")

    completed = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=300)
    descriptors, conformer = provider.parse_output(completed.stdout, mol, "u-1", "opt")

    assert completed.returncode == 0
    # B3LYP def2-SVP water, optimized: the fixture's energy to the SCF's tolerance
    assert descriptors[0].value == pytest.approx(-76.32118516654147, abs=1e-5)
    assert conformer is not None and conformer.method == PSI4_OPTIMIZED
