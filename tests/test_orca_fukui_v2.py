"""The ORCA side of Fukui v2, on REAL ORCA 6.1.1 output written by the application's own input builder.

`tests/fixtures/orca/*_fukui_*.out` are verbatim extracts (see `benchmarks/fukui_gate_2/make_fixtures.py`, which regenerates them): the version banner, each job's
echo of charge, multiplicity and electron count, the guess it started from, its <S**2> lines, its Hirshfeld block and its energy line. The `.inp` beside each is
the exact input ORCA was given. Every expected number below is worked out by hand from the rows those files print, not by the code under test.

    methoxide_fukui_fminus.out        CH3O-, B3LYP 6-31+G*. An anion (two states, f- alone) at a basis with diffuse functions (HCore and Hueckel starts of its N
                                      state after the default jobs): four jobs, all converging to one solution; the HCore job is 0.0026 eV lower, inside the margin.
    acetone_fukui_diffuse_hf.out      acetone at HF/6-311+G**. The N+1 state has the solution ORCA's default start misses: the HCore start is 1.013 eV lower.
    methoxide_fukui_failed_start.out  the first with its last job (Hueckel) given two SCF iterations: ORCA exited 115 after echoing it, the three before it intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.chem.fukui import f_plus_not_computed_sentence
from openchem.chem.orca_engine import OrcaOutputError, OrcaQuantumEngineProvider

FIXTURES = Path(__file__).parent / "fixtures" / "orca"
HARTREE_TO_EV = 27.211386245988


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mol_from_input(smiles: str, input_text: str) -> Chem.Mol:
    """The molecule of a fixture's `.inp`: the SMILES' atoms in the order the application embeds them, at the coordinates the file gives its first job."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    block = input_text.split("* xyz", 1)[1].split("\n", 1)[1].split("*", 1)[0].strip().splitlines()
    assert [row.split()[0] for row in block] == [atom.GetSymbol() for atom in mol.GetAtoms()]
    conformer = Chem.Conformer(mol.GetNumAtoms())
    for index, row in enumerate(block):
        conformer.SetAtomPosition(index, Point3D(*(float(value) for value in row.split()[1:])))
    mol.RemoveAllConformers()
    mol.AddConformer(conformer, assignId=True)
    return mol


METHOXIDE = _text("methoxide_fukui_fminus.out")
METHOXIDE_FAILED = _text("methoxide_fukui_failed_start.out")
ACETONE = _text("acetone_fukui_diffuse_hf.out")


def _datasets(output: str, smiles: str, inp: str) -> dict:
    mol = _mol_from_input(smiles, _text(inp))
    found = OrcaQuantumEngineProvider().parse_per_atom_output(output, mol, "mol-1", "fukui")
    return {dataset.property_id: dataset for dataset in found}


def _methoxide(output: str = METHOXIDE) -> dict:
    return _datasets(output, "C[O-]", "methoxide_fukui_fminus.inp")


def _acetone(output: str = ACETONE) -> dict:
    return _datasets(output, "CC(C)=O", "acetone_fukui_diffuse_hf.inp")


def _atoms(dataset) -> list[float]:
    return [dataset.values[index] for index in range(len(dataset.values))]


# --- the input the application writes is the input ORCA was given -------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles,charge,method_basis,name",
    [
        ("C[O-]", -1, "B3LYP 6-31+G*", "methoxide_fukui_fminus"),
        ("CC(C)=O", 0, "HF 6-311+G**", "acetone_fukui_diffuse_hf"),
    ],
)
def test_the_builder_writes_exactly_the_input_the_real_run_was_given(smiles, charge, method_basis, name):
    """Not a snapshot of text for its own sake: this is the input that produced the output the other tests read, so a change to the builder that
    changes what ORCA is asked fails here until the fixtures are regenerated and the outputs looked at again."""
    expected = _text(f"{name}.inp")
    mol = _mol_from_input(smiles, expected)
    assert OrcaQuantumEngineProvider().build_input(mol, charge, 1, method_basis, "fukui") == expected


# --- an anion: f- alone, from a four-job output ---------------------------------------------------------------------------------


def test_an_anion_gives_one_dataset_f_minus_and_it_is_the_hand_computed_difference_of_the_two_states():
    """f- = q(N-1) - q(N), the neutral radical's Hirshfeld row minus the anion's, for C, O, H, H, H:
    0.012364 + 0.101474, -0.147240 + 0.674234, 0.054973 + 0.074737, 0.064560 + 0.074723, 0.015357 + 0.074713."""
    found = _methoxide()
    assert set(found) == {"orca.fukui_minus"}
    values = _atoms(found["orca.fukui_minus"])
    assert values == pytest.approx([0.113838, 0.526994, 0.129710, 0.139283, 0.090070], abs=1e-6)
    assert sum(values) == pytest.approx(1.0, abs=2e-4)


def test_the_default_start_is_kept_when_another_is_lower_by_less_than_the_margin():
    """The HCore job is 0.0000962 Eh = 0.0026 eV below the default one, which is the SCF's own convergence and not a different solution, so the
    default's table is read: f- on carbon is 0.113838 from it and would be 0.114182 from the HCore job's (0.012364 + 0.101818)."""
    carbon = _methoxide()["orca.fukui_minus"].values[0]
    assert carbon == pytest.approx(0.113838, abs=1e-6) and carbon != pytest.approx(0.114182, abs=1e-5)


def test_the_provenance_of_an_anions_result():
    parameters = _methoxide()["orca.fukui_minus"].provenance.parameters
    assert parameters["functions"] == "f-"
    assert parameters["grid"] == "IntAcc 6.0"
    assert parameters["reference_charge"] == -1
    assert parameters["charge_scheme"] == "hirshfeld" and parameters["states"] == "vertical" and parameters["orca_version"] == "6.1.1"
    # the N state had three jobs that finished (default, HCore, Hueckel) and the N-1 state one
    assert parameters["starts_run"] == 4 and parameters["starts_failed"] == 0
    assert parameters["start_gain_ev"] == 0.0
    assert "start_note" not in parameters
    # only the N-1 state (a doublet) prints <S**2>; there is no N+1 state
    assert parameters["cation_s_squared"] == 0.754014 and "anion_s_squared" not in parameters
    assert "unbound_anion_ev" not in parameters


def test_an_anions_caveat_says_f_plus_was_not_computed_and_that_it_is_not_validated():
    caveat = _methoxide()["orca.fukui_minus"].provenance.parameters["caveat"]
    assert f_plus_not_computed_sentence() in caveat and "Not validated" in caveat
    assert "SCF solution" not in caveat and "did not converge and" not in caveat


def test_parse_output_reads_the_anion_with_the_first_jobs_energy_and_no_koopmans_numbers():
    mol = _mol_from_input("C[O-]", _text("methoxide_fukui_fminus.inp"))
    values, conformer = OrcaQuantumEngineProvider().parse_output(METHOXIDE, mol, "mol-1", "fukui")
    assert [(d.descriptor_id, d.value) for d in values] == [("orca.scf_energy", -115.040629211585)] and conformer is None


def test_a_crlf_output_reads_the_same_four_job_anion():
    """ORCA's output has CRLF line ends on Windows; the job echoes, the guess lines and the tables must read through them."""
    plain = _methoxide()["orca.fukui_minus"]
    crlf = _methoxide(METHOXIDE.replace("\n", "\r\n"))["orca.fukui_minus"]
    assert crlf.values == plain.values
    assert crlf.provenance.parameters["starts_run"] == 4


# --- an extra start that did not finish ------------------------------------------------------------------------------------------


def test_a_failed_extra_start_costs_nothing_but_itself_and_is_said():
    """ORCA ends the whole compound input at the first job that does not converge, and the Hueckel job is the last, so the three before it are intact: the
    run is read as before, the answer is the same numbers, and the result says one start did not converge."""
    found = _methoxide(METHOXIDE_FAILED)
    assert _atoms(found["orca.fukui_minus"]) == pytest.approx([0.113838, 0.526994, 0.129710, 0.139283, 0.090070], abs=1e-6)
    parameters = found["orca.fukui_minus"].provenance.parameters
    assert parameters["starts_failed"] == 1 and parameters["starts_run"] == 4
    assert parameters["start_note"] == (
        "The Hueckel start of the anion state did not converge and was not used; the choice was made among the 2 that finished."
    )
    assert parameters["start_note"] in parameters["caveat"]


def test_a_failed_extra_start_does_not_fail_the_run():
    mol = _mol_from_input("C[O-]", _text("methoxide_fukui_fminus.inp"))
    values, _conformer = OrcaQuantumEngineProvider().parse_output(METHOXIDE_FAILED, mol, "mol-1", "fukui")
    assert [d.descriptor_id for d in values] == ["orca.scf_energy"]


def test_a_job_the_answer_needs_that_did_not_finish_still_fails_the_run_and_names_the_state():
    """Cut the output after the anion's first energy: the neutral radical (N-1) job never ran, and that is no extra start."""
    cut = METHOXIDE.split("FINAL SINGLE POINT ENERGY")[0] + "FINAL SINGLE POINT ENERGY      -115.040629211585\n"
    with pytest.raises(OrcaOutputError, match=r"The N-1 state of this Fukui calculation did not finish"):
        _methoxide(cut)


def test_the_default_start_of_a_state_that_never_finished_is_not_replaced_by_an_extra_one():
    """An output in which the anion's default job has no table but its HCore job does (which ORCA cannot print: it stops at the first failure) is refused."""
    first_table = METHOXIDE.index("HIRSHFELD ANALYSIS")
    broken = METHOXIDE[:first_table] + "NOT A TABLE" + METHOXIDE[first_table + len("HIRSHFELD ANALYSIS"):]
    with pytest.raises(OrcaOutputError, match=r"The N state of this Fukui calculation did not finish"):
        _methoxide(broken)


# --- a state with more than one SCF solution -----------------------------------------------------------------------------------------


#: By hand from the Hirshfeld rows of job 1 (the neutral) and job 4 (the HCore start of the anion), atom order C, C, C, O, H x 6:
F_PLUS_FROM_HCORE = [0.102518, 0.032944, 0.102524, 0.058069, 0.132612, 0.146614, 0.072214, 0.072297, 0.132535, 0.146850]
#: ... and from job 3, ORCA's default start, which the run must NOT read once the HCore start is 1.013 eV below it:
F_PLUS_FROM_DEFAULT = [0.053692, 0.245069, 0.053684, 0.251466, 0.078713, 0.072356, 0.046905, 0.046904, 0.078642, 0.072408]
#: f- from jobs 1 and 2 (neutral and cation): cation minus neutral.
ACETONE_F_MINUS = [0.064094, 0.121563, 0.064097, 0.449167, 0.055943, 0.056457, 0.038143, 0.038143, 0.055943, 0.056458]


def test_the_lowest_solution_of_the_anion_is_read_and_the_default_starts_is_not():
    """At HF/6-311+G** ORCA's default start (the cation's orbitals) put acetone's extra electron on one solution and the HCore start found another 1.013 eV
    lower, whose f+ puts 0.058 on the oxygen where the default solution puts 0.251. The lowest is read."""
    found = _acetone()
    assert set(found) == {"orca.fukui_plus", "orca.fukui_minus", "orca.fukui_zero", "orca.fukui_dual"}
    plus = _atoms(found["orca.fukui_plus"])
    assert plus == pytest.approx(F_PLUS_FROM_HCORE, abs=1e-6)
    assert plus[3] != pytest.approx(F_PLUS_FROM_DEFAULT[3], abs=0.05)


def test_the_states_that_had_one_start_are_unchanged_by_the_choice_among_anion_starts():
    found = _acetone()
    assert _atoms(found["orca.fukui_minus"]) == pytest.approx(ACETONE_F_MINUS, abs=1e-6)
    plus, minus = _atoms(found["orca.fukui_plus"]), _atoms(found["orca.fukui_minus"])
    assert _atoms(found["orca.fukui_dual"]) == pytest.approx([p - m for p, m in zip(plus, minus)], abs=1e-12)
    assert _atoms(found["orca.fukui_zero"]) == pytest.approx([(p + m) / 2 for p, m in zip(plus, minus)], abs=1e-12)


def test_the_choice_is_recorded_with_how_much_lower_it_was_and_the_sentence_is_in_the_caveat():
    parameters = _acetone()["orca.fukui_plus"].provenance.parameters
    gain = (-191.917667774782 + 191.954893804735) * HARTREE_TO_EV
    assert parameters["start_gain_ev"] == pytest.approx(gain, abs=1e-9) and gain == pytest.approx(1.013, abs=5e-4)
    assert parameters["starts_run"] == 5 and parameters["starts_failed"] == 0
    note = parameters["start_note"]
    assert note.startswith("The anion state has more than one SCF solution. ORCA's default start reached one 1.01 eV above the lowest of the 3 starts that finished")
    assert "from the HCore start" in note and "up to 0.212 electrons in one atom's Hirshfeld charge" in note and "one atom's f+ value" in note
    assert note in parameters["caveat"]


def test_the_unbound_anion_energy_and_the_spin_are_those_of_the_solution_that_was_read():
    """E(N+1) - E(N) from the HCore job is 0.062207 Eh = 1.693 eV (the default solution's would be 2.704 eV), and the anion's <S**2> is the HCore job's."""
    parameters = _acetone()["orca.fukui_plus"].provenance.parameters
    assert parameters["unbound_anion_ev"] == pytest.approx((-191.954893804735 + 192.017100717944) * HARTREE_TO_EV, abs=1e-9)
    assert parameters["unbound_anion_ev"] == pytest.approx(1.693, abs=5e-4)
    assert parameters["anion_s_squared"] == 0.750566 and parameters["cation_s_squared"] == 0.773895


def test_a_neutral_species_keeps_all_four_datasets_and_no_f_plus_not_computed_sentence():
    found = _acetone()
    assert f_plus_not_computed_sentence() not in found["orca.fukui_plus"].provenance.parameters["caveat"]
    assert found["orca.fukui_plus"].provenance.parameters["functions"] == "f+ f- f0 dual"
    assert found["orca.fukui_plus"].provenance.parameters["reference_charge"] == 0


def test_the_hueckel_job_that_reached_the_default_solution_is_not_a_second_opinion_that_moves_anything():
    """Job 5 (Hueckel) ended where job 3 did, 2e-8 Eh away: it is a finished start and counted, and it replaces nothing."""
    parameters = _acetone()["orca.fukui_plus"].provenance.parameters
    assert parameters["starts_run"] == 5
    assert parameters["start_note"].count("more than one SCF solution") == 1
