"""The xtb engine (`chem/xtb_engine.py`, `docs/EXTERNAL_TOOL_CANDIDATES.md`): the input it writes, the command it builds from that input, and the output it reads.

The outputs under `tests/fixtures/xtb/` are REAL xtb 6.7.1pre outputs (the spike of 2026-10-27), produced by this module's own `build_input` and `command_args` and captured from STDOUT only, which is all the service reads
(xtb's `normal termination` line is on stderr). Never hand-written. The last test runs a real xtb when one is configured (`OPENCHEM_XTB_EXE`) and is skipped otherwise.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import xtb_engine as xe
from openchem.domain.conformer import QUANTUM_ENGINE_NAMES, QUANTUM_OPTIMIZED_METHODS, XTB_OPTIMIZED

FIXTURES = Path(__file__).parent / "fixtures" / "xtb"
BOHR = 1.8897261246257702


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


def _provider() -> xe.XtbQuantumEngineProvider:
    return xe.XtbQuantumEngineProvider(threads=lambda: 1)


def _distance(mol: Chem.Mol, i: int, j: int) -> float:
    conf = mol.GetConformer()
    return (conf.GetAtomPosition(i) - conf.GetAtomPosition(j)).Length()


def _geometry(molblock: str) -> Chem.Mol:
    return Chem.MolFromMolBlock(molblock, removeHs=False)


# -- the engine's identity ---------------------------------------------------------------------------------------------


def test_the_provider_names_itself_and_its_executable() -> None:
    provider = _provider()
    assert provider.provider_id == "xtb" and provider.engine_name() == "xtb"
    assert provider.executable_setting() == "xtb/executable_path"
    assert provider.executable_names() == ("xtb",)
    assert provider.supports("opt_freq") and provider.supports("sp") and not provider.supports("nmr")
    assert provider.supports_parallel is False


def test_an_xtb_geometry_is_a_quantum_optimized_conformer_with_its_own_label() -> None:
    assert XTB_OPTIMIZED == "xtb_opt" and XTB_OPTIMIZED in QUANTUM_OPTIMIZED_METHODS
    assert QUANTUM_ENGINE_NAMES[XTB_OPTIMIZED] == "xtb"


# -- the input ---------------------------------------------------------------------------------------------------------


def test_the_input_is_a_turbomole_block_in_bohr_with_the_job_in_a_header() -> None:
    mol = _mol("CCO")
    text = _provider().build_input(mol, 0, 1, "GFN2-xTB", "opt")
    lines = text.splitlines()
    assert lines[0] == "# openchem-xtb charge=0 uhf=0 job=opt gfn=2"
    assert lines[1] == "$coord" and lines[-1] == "$end" and len(lines) == mol.GetNumAtoms() + 3
    assert [line.split()[-1] for line in lines[2:-1]] == ["c", "c", "o", "h", "h", "h", "h", "h", "h"]
    x, y, z = (float(token) for token in lines[2].split()[:3])
    first = mol.GetConformer().GetAtomPosition(0)
    assert (x, y, z) == pytest.approx((first.x * BOHR, first.y * BOHR, first.z * BOHR), abs=1e-9)


@pytest.mark.parametrize("calc_type", ["sp", "opt", "opt_freq"])
def test_the_header_carries_the_calculation_type_and_the_spin(calc_type: str) -> None:
    text = _provider().build_input(_mol("[CH3]"), 0, 2, "GFN1-xTB", calc_type)
    assert text.splitlines()[0] == f"# openchem-xtb charge=0 uhf=1 job={calc_type} gfn=1"


@pytest.mark.parametrize(
    ("smiles", "charge", "multiplicity"),
    [("[CH3]", 0, 1), ("CCO", 0, 2), ("CCO", 0, 4), ("CC(=O)[O-]", 0, 1), ("[H][H]", 0, 5), ("CCO", 0, 0)],
)
def test_an_impossible_electron_count_is_refused_before_anything_runs(smiles: str, charge: int, multiplicity: int) -> None:
    # xtb itself ran a 7-electron methyl radical at --uhf 0 and exited 0 (module docstring); this is the guard it does not have.
    with pytest.raises(ValueError):
        _provider().build_input(_mol(smiles), charge, multiplicity, "GFN2-xTB", "sp")


def test_the_charge_is_part_of_the_electron_count() -> None:
    _provider().build_input(_mol("CC(=O)[O-]"), -1, 1, "GFN2-xTB", "sp")


@pytest.mark.parametrize("method_basis", ["GFN2-xTB ALPB", "GFN2-xTB water", "B3LYP def2-SVP", "GFN0-xTB", "GFN-FF", ""])
def test_anything_but_one_known_method_is_refused_not_dropped(method_basis: str) -> None:
    with pytest.raises(ValueError, match="xtb engine takes a method alone"):
        _provider().build_input(_mol("CCO"), 0, 1, method_basis, "sp")


def test_the_method_label_is_case_insensitive() -> None:
    assert xe.split_method("gfn2-xtb") == (2, "gfn2-xtb")


def test_a_calculation_type_the_engine_does_not_run_is_refused() -> None:
    with pytest.raises(ValueError, match="does not run 'nmr'"):
        _provider().build_input(_mol("CCO"), 0, 1, "GFN2-xTB", "nmr")


def test_an_element_beyond_the_parametrized_range_is_refused() -> None:
    mol = Chem.RWMol()
    mol.AddAtom(Chem.Atom(87))
    mol.AddConformer(Chem.Conformer(1))
    with pytest.raises(ValueError, match="elements 1 to 86"):
        _provider().build_input(mol.GetMol(), 0, 2, "GFN2-xTB", "sp")


# -- the command -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("calc_type", "job_flags"),
    [("sp", []), ("opt", ["--opt", "tight"]), ("opt_freq", ["--ohess", "tight"])],
)
def test_the_command_is_built_from_the_header_the_input_wrote(tmp_path: Path, calc_type: str, job_flags: list[str]) -> None:
    provider = xe.XtbQuantumEngineProvider(threads=lambda: 3)
    path = tmp_path / "job.inp"
    path.write_text(provider.build_input(_mol("CC(=O)[O-]"), -1, 1, "GFN1-xTB", calc_type), encoding="utf-8")
    assert provider.command_args("xtb.exe", path) == [
        "xtb.exe", str(path), "--gfn", "1", "--chrg", "-1", "--uhf", "0", "-P", "3", *job_flags,
    ]


def test_a_file_without_the_header_is_never_guessed_at(tmp_path: Path) -> None:
    path = tmp_path / "job.inp"
    path.write_text("$coord\n 0 0 0 h\n$end\n", encoding="utf-8")
    with pytest.raises(ValueError, match="job header"):
        _provider().command_args("xtb.exe", path)
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="job header"):
        _provider().command_args("xtb.exe", path)


def test_a_header_naming_a_job_the_engine_does_not_run_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "job.inp"
    path.write_text("# openchem-xtb charge=0 uhf=0 job=hess gfn=2\n$coord\n$end\n", encoding="utf-8")
    with pytest.raises(ValueError, match="job header"):
        _provider().command_args("xtb.exe", path)


# -- the output: a single point ----------------------------------------------------------------------------------------


def test_a_single_point_yields_its_energy_and_no_geometry() -> None:
    descriptors, conformer = _provider().parse_output(_fixture("ethanol_gfn2_sp.out"), _mol("CCO"), "u1", "sp")
    assert [d.descriptor_id for d in descriptors] == ["xtb.scf_energy"]
    energy = descriptors[0]
    assert energy.value == pytest.approx(-11.381897815, abs=1e-8)
    assert energy.units == "Hartree" and energy.provider == "xtb" and energy.molecule_uuid == "u1"
    assert energy.provenance.parameters["xtb_version"] == "6.7.1pre"
    assert conformer is None


def test_an_anion_single_point_is_read() -> None:
    descriptors, _ = _provider().parse_output(_fixture("acetate_anion_gfn2_sp.out"), _mol("CC(=O)[O-]"), "u", "sp")
    assert descriptors[0].value == pytest.approx(-14.143630713, abs=1e-8)


# -- the output: an optimization ---------------------------------------------------------------------------------------


def test_an_optimization_yields_the_lowest_energy_and_the_final_geometry_in_angstrom() -> None:
    mol = _mol("CCO")
    descriptors, conformer = _provider().parse_output(_fixture("ethanol_gfn2_opt.out"), mol, "u", "opt")
    assert descriptors[0].value == pytest.approx(-11.394339084, abs=1e-8)
    assert conformer is not None and conformer.method == XTB_OPTIMIZED and conformer.energy is None
    optimized = _geometry(conformer.molblock)
    assert [a.GetSymbol() for a in optimized.GetAtoms()] == [a.GetSymbol() for a in mol.GetAtoms()]
    # xtb prints Bohr for a Turbomole input; the conformer must be in Angstrom (a C-C single bond is 1.525 A, GFN2) and move off the RDKit start.
    assert _distance(optimized, 0, 1) == pytest.approx(1.5251, abs=2e-3)
    assert _distance(optimized, 1, 2) == pytest.approx(1.4086, abs=2e-3)
    assert _distance(optimized, 0, 1) != pytest.approx(_distance(mol, 0, 1), abs=1e-3)
    assert conformer.provenance.parameters["xtb_version"] == "6.7.1pre"


def test_the_optimized_energy_is_below_the_single_point_energy_at_the_start() -> None:
    sp, _ = _provider().parse_output(_fixture("ethanol_gfn2_sp.out"), _mol("CCO"), "u", "sp")
    opt, _ = _provider().parse_output(_fixture("ethanol_gfn2_opt.out"), _mol("CCO"), "u", "opt")
    assert opt[0].value < sp[0].value - 0.01


def test_gfn1_is_a_different_energy_from_gfn2_for_the_same_molecule() -> None:
    gfn1, _ = _provider().parse_output(_fixture("ethanol_gfn1_opt.out"), _mol("CCO"), "u", "opt")
    gfn2, _ = _provider().parse_output(_fixture("ethanol_gfn2_opt.out"), _mol("CCO"), "u", "opt")
    assert gfn1[0].value == pytest.approx(-12.163128369, abs=1e-8) and gfn1[0].value != pytest.approx(gfn2[0].value, abs=0.1)


def test_a_radical_run_with_its_spin_is_read() -> None:
    descriptors, conformer = _provider().parse_output(_fixture("methyl_radical_gfn2_opt.out"), _mol("[CH3]"), "u", "opt")
    assert descriptors[0].value == pytest.approx(-3.562970366, abs=1e-8)
    assert conformer is not None and _distance(_geometry(conformer.molblock), 0, 1) == pytest.approx(1.0675, abs=2e-3)


def test_an_optimization_that_did_not_converge_is_a_failed_run_though_xtb_completed() -> None:
    text = _fixture("ethanol_gfn2_opt_unconverged.out")
    assert "FAILED TO CONVERGE GEOMETRY OPTIMIZATION" in text and "finished run on" in text
    with pytest.raises(xe.XtbOutputError, match="did not converge"):
        _provider().parse_output(text, _mol("CCO"), "u", "opt")


def test_an_optimization_requested_of_a_single_point_output_is_not_given_the_start_geometry() -> None:
    with pytest.raises(xe.XtbOutputError, match="did not converge"):
        _provider().parse_output(_fixture("ethanol_gfn2_sp.out"), _mol("CCO"), "u", "opt")


def test_coordinates_are_never_applied_to_other_atoms() -> None:
    with pytest.raises(xe.XtbOutputError, match="not the input's"):
        _provider().parse_output(_fixture("ethanol_gfn2_opt.out"), _mol("CCN"), "u", "opt")


# -- the output: frequencies -------------------------------------------------------------------------------------------


def test_a_frequency_job_adds_the_thermochemistry_it_printed() -> None:
    descriptors, conformer = _provider().parse_output(_fixture("ethanol_gfn2_opt_freq.out"), _mol("CCO"), "u", "opt_freq")
    by_id = {d.descriptor_id: d.value for d in descriptors}
    assert set(by_id) == {"xtb.scf_energy", "xtb.enthalpy", "xtb.gibbs_free_energy", "xtb.zero_point_energy"}
    assert by_id["xtb.scf_energy"] == pytest.approx(-11.394339084, abs=1e-8)
    assert by_id["xtb.enthalpy"] == pytest.approx(-11.310981822, abs=1e-8)
    assert by_id["xtb.gibbs_free_energy"] == pytest.approx(-11.341577068, abs=1e-8)
    assert by_id["xtb.zero_point_energy"] == pytest.approx(0.078140922, abs=1e-8)
    assert by_id["xtb.enthalpy"] > by_id["xtb.gibbs_free_energy"]
    assert conformer is not None and conformer.method == XTB_OPTIMIZED


def test_the_vibrations_drop_the_translations_and_rotations() -> None:
    spectrum = _provider().parse_vibrational_spectrum(_fixture("ethanol_gfn2_opt_freq.out"), _mol("CCO"), "u", "opt_freq")
    assert spectrum is not None and spectrum.method == "xtb" and spectrum.molecule_uuid == "u"
    assert len(spectrum.modes) == 3 * 9 - 6
    assert spectrum.modes[0].wavenumber_cm1 == pytest.approx(223.27, abs=0.01)
    assert spectrum.modes[-1].wavenumber_cm1 == pytest.approx(3542.62, abs=0.01)
    assert not spectrum.imaginary_modes and spectrum.imaginary_warning == ""
    # The intensities are only in xtb's `vibspectrum` file, never the stdout: reported as absent, not as zero.
    assert all(mode.ir_intensity_km_mol is None for mode in spectrum.modes)


def test_a_linear_molecule_has_five_translations_and_rotations() -> None:
    # CO2's frequency block is headed "vibrational frequencies", not "projected vibrational frequencies" (measured); this fixture is why the heading is matched loosely.
    mol = _mol("O=C=O")
    spectrum = _provider().parse_vibrational_spectrum(_fixture("co2_gfn2_opt_freq.out"), mol, "u", "opt_freq")
    assert spectrum is not None
    assert [round(m.wavenumber_cm1) for m in spectrum.modes] == [600, 600, 1425, 2593]
    descriptors, _ = _provider().parse_output(_fixture("co2_gfn2_opt_freq.out"), mol, "u", "opt_freq")
    assert any(d.descriptor_id == "xtb.gibbs_free_energy" for d in descriptors)


def test_other_calculation_types_report_no_vibrations() -> None:
    for name, calc_type in (("ethanol_gfn2_sp.out", "sp"), ("ethanol_gfn2_opt.out", "opt")):
        assert _provider().parse_vibrational_spectrum(_fixture(name), _mol("CCO"), "u", calc_type) is None


def test_a_vibrational_block_for_another_molecule_is_not_reported() -> None:
    # 27 printed values against 5 atoms: the mode count does not fit, so nothing is claimed.
    assert _provider().parse_vibrational_spectrum(_fixture("ethanol_gfn2_opt_freq.out"), _mol("C"), "u", "opt_freq") is None


def test_an_imaginary_mode_is_reported_with_a_warning() -> None:
    text = _fixture("ethanol_gfn2_opt_freq.out").replace("eigval :      223.27", "eigval :     -123.27")
    spectrum = _provider().parse_vibrational_spectrum(text, _mol("CCO"), "u", "opt_freq")
    assert spectrum is not None and len(spectrum.imaginary_modes) == 1
    assert "imaginary" in spectrum.imaginary_warning and "not a minimum" in spectrum.imaginary_warning


def test_a_frequency_job_with_no_thermochemistry_is_a_failed_run() -> None:
    text = _fixture("ethanol_gfn2_opt_freq.out")
    for marker in ("TOTAL ENTHALPY", "TOTAL FREE ENERGY", ":: zero point energy"):
        text = text.replace(marker, "REMOVED")
    with pytest.raises(xe.XtbOutputError, match="no thermochemistry"):
        _provider().parse_output(text, _mol("CCO"), "u", "opt_freq")


# -- failure -----------------------------------------------------------------------------------------------------------


def test_a_failed_run_is_read_from_the_stdout_error_block() -> None:
    text = _fixture("no_coordinates.out")
    assert "normal termination" not in text  # it is on stderr; the stdout is all the service reads
    with pytest.raises(xe.XtbOutputError, match="coordinates not present"):
        _provider().parse_output(text, _mol("CCO"), "u", "sp")


def test_the_stderr_marker_is_honoured_if_the_channels_are_ever_merged() -> None:
    with pytest.raises(xe.XtbOutputError):
        _provider().parse_output(_fixture("ethanol_gfn2_sp.out") + "\nabnormal termination of xtb\n", _mol("CCO"), "u", "sp")


def test_a_run_cut_short_is_a_failed_run_not_a_partial_result() -> None:
    text = _fixture("ethanol_gfn2_sp.out")
    truncated = text[: text.index("finished run on")]
    with pytest.raises(xe.XtbOutputError, match="cut short"):
        _provider().parse_output(truncated, _mol("CCO"), "u", "sp")


def test_output_with_no_energy_is_a_failed_run() -> None:
    with pytest.raises(xe.XtbOutputError, match="without printing a total energy"):
        _provider().parse_output("* finished run on 2026/10/27\n", _mol("CCO"), "u", "sp")


# -- a real xtb, when one is configured --------------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("OPENCHEM_XTB_EXE"), reason="set OPENCHEM_XTB_EXE to a real xtb to run this")
@pytest.mark.parametrize("calc_type", ["sp", "opt", "opt_freq"])
def test_a_real_xtb_run_through_the_providers_own_input_and_command(tmp_path: Path, calc_type: str) -> None:
    provider = _provider()
    mol = _mol("CCO")
    path = tmp_path / "job.inp"
    path.write_text(provider.build_input(mol, 0, 1, "GFN2-xTB", calc_type), encoding="utf-8")
    result = subprocess.run(provider.command_args(os.environ["OPENCHEM_XTB_EXE"], path), cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0
    descriptors, conformer = provider.parse_output(result.stdout, mol, "u", calc_type)
    assert descriptors[0].descriptor_id == "xtb.scf_energy" and descriptors[0].value < -11.3
    assert (conformer is not None) == (calc_type != "sp")
