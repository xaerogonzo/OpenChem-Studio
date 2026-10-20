"""The ORCA side of Fukui v2, on REAL ORCA 6.1.1 output written by the application's own input builder.

`tests/fixtures/orca/*_fukui_*.out` are verbatim extracts (see `benchmarks/fukui_gate_2/make_fixtures.py`, which regenerates them): the version banner, each job's
echo of charge, multiplicity and electron count, the guess it started from, its <S**2> lines, its Hirshfeld block and its energy line. The `.inp` beside each is
the exact input ORCA was given. Every expected number below is worked out by hand from the rows those files print, not by the code under test.

    methoxide_fukui_anion.out         CH3O-, B3LYP 6-31+G*. An anion with its dianion (seven jobs, in `chem/fukui_plan.py`'s order: the anion, the neutral radical, the
                                      anion's HCore and Hueckel starts, the dianion, the dianion's two starts): all four datasets; every start of a state ends in one solution.
    cyanide_fukui_anion_no_diffuse.out  CN-, B3LYP 6-31G** at its optimized bond length. An anion without diffuse functions: three jobs and no extra start; the dianion lies
                                      13.0 eV above the anion. The case the first gate decided on, and its f+ is the first gate's to 2e-5.
    methoxide_fukui_failed_dianion.out  the first with its dianion's default job (the fifth) given two SCF iterations: ORCA exited 115 after echoing it, the four before it
                                      intact, the dianion's own two starts never run. f- alone, and the result says why.
    acetone_fukui_diffuse_hf.out      acetone at HF/6-311+G**. The N+1 state has the solution ORCA's default start misses: the HCore start is 1.013 eV lower.

    methoxide_fukui_fminus.out        written by Fukui v2's builder, in which an anion had NO dianion job (the builder no longer reproduces its `.inp`): four jobs, the
                                      anion, the neutral radical and the anion again from HCore and Hueckel. Kept as a real output of an anion run without a dianion.
    methoxide_fukui_failed_start.out  that one with its last job (Hueckel) given two SCF iterations: ORCA exited 115 after echoing it, the three before it intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.chem.fukui import f_plus_not_computed_sentence, summary_lines, unbound_anion_sentence
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
METHOXIDE_ANION = _text("methoxide_fukui_anion.out")
METHOXIDE_FAILED_DIANION = _text("methoxide_fukui_failed_dianion.out")
CYANIDE = _text("cyanide_fukui_anion_no_diffuse.out")
ACETONE = _text("acetone_fukui_diffuse_hf.out")


def _datasets(output: str, smiles: str, inp: str) -> dict:
    mol = _mol_from_input(smiles, _text(inp))
    found = OrcaQuantumEngineProvider().parse_per_atom_output(output, mol, "mol-1", "fukui")
    return {dataset.property_id: dataset for dataset in found}


def _methoxide(output: str = METHOXIDE) -> dict:
    return _datasets(output, "C[O-]", "methoxide_fukui_fminus.inp")


def _acetone(output: str = ACETONE) -> dict:
    return _datasets(output, "CC(C)=O", "acetone_fukui_diffuse_hf.inp")


def _methoxide_anion(output: str = METHOXIDE_ANION) -> dict:
    return _datasets(output, "C[O-]", "methoxide_fukui_anion.inp")


def _cyanide(output: str = CYANIDE) -> dict:
    return _datasets(output, "[C-]#N", "cyanide_fukui_anion_no_diffuse.inp")


def _atoms(dataset) -> list[float]:
    return [dataset.values[index] for index in range(len(dataset.values))]


# --- the input the application writes is the input ORCA was given -------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles,charge,method_basis,name",
    [
        ("C[O-]", -1, "B3LYP 6-31+G*", "methoxide_fukui_anion"),
        ("[C-]#N", -1, "B3LYP 6-31G**", "cyanide_fukui_anion_no_diffuse"),
        ("CC(C)=O", 0, "HF 6-311+G**", "acetone_fukui_diffuse_hf"),
    ],
)
def test_the_builder_writes_exactly_the_input_the_real_run_was_given(smiles, charge, method_basis, name):
    """Not a snapshot of text for its own sake: this is the input that produced the output the other tests read, so a change to the builder that
    changes what ORCA is asked fails here until the fixtures are regenerated and the outputs looked at again."""
    expected = _text(f"{name}.inp")
    mol = _mol_from_input(smiles, expected)
    assert OrcaQuantumEngineProvider(cation_search=lambda: False).build_input(mol, charge, 1, method_basis, "fukui") == expected


def test_the_failed_dianion_input_is_the_methoxide_input_with_two_scf_iterations_given_to_the_fifth_job():
    """`make_fixtures.py` makes the dianion's default job unable to converge by giving it `MaxIter 2`; nothing else differs from what the builder writes."""
    failing = _text("methoxide_fukui_failed_dianion.inp")
    assert failing.count("  MaxIter 2\n") == 1
    jobs = failing.split("$new_job")
    assert "  MaxIter 2\n" in jobs[4] and "* xyz -2 2" in jobs[4]
    mol = _mol_from_input("C[O-]", failing)
    assert OrcaQuantumEngineProvider(cation_search=lambda: False).build_input(mol, -1, 1, "B3LYP 6-31+G*", "fukui") == failing.replace("  MaxIter 2\n", "")


# --- an anion WITHOUT a dianion job (what Fukui v2's builder wrote): f- alone, from a four-job output -----------------------------


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


# --- an anion WITH its dianion: all four datasets -------------------------------------------------------------------------------------

#: By hand from the Hirshfeld rows of job 1 (the anion), job 2 (the neutral radical) and job 5 (the dianion, ORCA's default start), atoms C, O, H, H, H:
#: f+ = q(N) - q(N+1) = -0.101474 + 0.287031, -0.674234 + 0.760648, -0.074737 + 0.317716, -0.074723 + 0.317222, -0.074713 + 0.317201.
ANION_F_PLUS = [0.185557, 0.086414, 0.242979, 0.242499, 0.242488]
ANION_F_MINUS = [0.113838, 0.526994, 0.129710, 0.139283, 0.090070]
METHOXIDE_ATOMS = ["C", "O", "H", "H", "H"]


def test_an_anion_with_its_dianion_gives_all_four_datasets_and_each_is_the_hand_computed_difference():
    found = _methoxide_anion()
    assert set(found) == {"orca.fukui_plus", "orca.fukui_minus", "orca.fukui_zero", "orca.fukui_dual"}
    plus, minus = _atoms(found["orca.fukui_plus"]), _atoms(found["orca.fukui_minus"])
    assert plus == pytest.approx(ANION_F_PLUS, abs=1e-6) and minus == pytest.approx(ANION_F_MINUS, abs=1e-6)
    assert _atoms(found["orca.fukui_zero"]) == pytest.approx([(p + m) / 2 for p, m in zip(plus, minus)], abs=1e-12)
    assert _atoms(found["orca.fukui_dual"]) == pytest.approx([p - m for p, m in zip(plus, minus)], abs=1e-12)
    # each of f+ and f- sums to one over the atoms (to the integration's few 1e-4)
    assert sum(plus) == pytest.approx(1.0, abs=2e-4) and sum(minus) == pytest.approx(1.0, abs=2e-4)


def test_the_provenance_of_an_anion_that_has_its_dianion():
    parameters = _methoxide_anion()["orca.fukui_plus"].provenance.parameters
    assert parameters["functions"] == "f+ f- f0 dual" and parameters["reference_charge"] == -1 and parameters["grid"] == "IntAcc 6.0"
    # the anion had three jobs that finished (default, HCore, Hueckel), the neutral radical one and the dianion three; nothing was lower than a default by the margin
    assert parameters["starts_run"] == 7 and parameters["starts_failed"] == 0 and parameters["start_gain_ev"] == 0.0
    assert "start_note" not in parameters and "f_plus_note" not in parameters
    assert parameters["cation_s_squared"] == 0.754014 and parameters["anion_s_squared"] == 0.750701


def test_the_dianion_is_called_what_it_is_and_the_unbound_energy_is_the_dianions_above_the_anions():
    """E(dianion) - E(anion) = -114.824262601343 + 115.040629211585 = 0.216367 Eh = 5.888 eV: the extra electron of CH3O(2-) is not bound, and the Hirshfeld rows
    put it on the three hydrogens (-0.317 each, against -0.075 in the anion), which is where f+ is large (0.24 each). The result says so."""
    parameters = _methoxide_anion()["orca.fukui_plus"].provenance.parameters
    gap = (-114.824262601343 + 115.040629211585) * HARTREE_TO_EV
    assert parameters["unbound_anion_ev"] == pytest.approx(gap, abs=1e-9) and gap == pytest.approx(5.888, abs=5e-4)
    assert unbound_anion_sentence(gap, -1) in parameters["caveat"]
    assert "The dianion is 5.89 eV ABOVE the anion (a negative electron affinity)" in parameters["caveat"]
    assert f_plus_not_computed_sentence() not in parameters["caveat"] and "Not validated" in parameters["caveat"]


def test_the_default_start_of_the_dianion_is_kept_when_its_other_starts_are_inside_the_margin():
    """HCore and Hueckel end 7.2e-6 and 2.2e-6 Eh (0.0002 and 0.0001 eV) below ORCA's default start: the same solution. The default's table is read:
    f+ on carbon is 0.185557 from it, 0.185499 from the HCore job's and 0.185539 from the Hueckel job's."""
    carbon = _methoxide_anion()["orca.fukui_plus"].values[0]
    assert carbon == pytest.approx(0.185557, abs=1e-6) and carbon != pytest.approx(0.185499, abs=1e-5)


def test_parse_output_reads_an_anion_with_its_dianion_with_the_first_jobs_energy():
    mol = _mol_from_input("C[O-]", _text("methoxide_fukui_anion.inp"))
    values, conformer = OrcaQuantumEngineProvider().parse_output(METHOXIDE_ANION, mol, "mol-1", "fukui")
    assert [(d.descriptor_id, d.value) for d in values] == [("orca.scf_energy", -115.040629211585)] and conformer is None


def test_a_crlf_output_reads_the_same_seven_job_anion():
    plain = _methoxide_anion()["orca.fukui_plus"]
    crlf = _methoxide_anion(METHOXIDE_ANION.replace("\n", "\r\n"))["orca.fukui_plus"]
    assert crlf.values == plain.values and crlf.provenance.parameters["starts_run"] == 7


def test_the_summary_of_an_anion_with_its_dianion_names_the_largest_f_plus_and_the_dianion_sentence():
    lines = summary_lines(list(_methoxide_anion().values()), METHOXIDE_ATOMS)
    assert any(line.startswith("Largest f+ (attack by a nucleophile): H (atom 3): 0.243") for line in lines)
    assert any(line.startswith("Largest f- (attack by an electrophile): O (atom 2): 0.527") for line in lines)
    assert any(line.startswith("The dianion is 5.89 eV ABOVE the anion") for line in lines)
    assert f_plus_not_computed_sentence() not in lines


# --- an anion without diffuse functions: the case the first gate decided on ---------------------------------------------------------------


#: The first gate's stored run of the same molecule at the same level (`benchmarks/fukui_gate/artifacts/records.json`, species CN-, level B3LYP/6-31G**): the f+ it
#: compared with Olah and co-workers' published values (largest difference of that species at that level, 0.0043), from the same dianion.
FIRST_GATE_CYANIDE_F_PLUS = [0.595047, 0.404954]
FIRST_GATE_CYANIDE_F_MINUS = [0.599511, 0.400489]


def test_cyanide_at_a_basis_without_diffuse_functions_is_three_jobs_and_all_four_numbers():
    """CN-, B3LYP 6-31G** at its ORCA-optimized bond length (1.183918 A): f+ = q(N) - q(N+1) = -0.470447 + 1.065500, -0.529553 + 0.934500 and
    f- = q(N-1) - q(N) = 0.129087 + 0.470447, -0.129087 + 0.529553. The dianion lies 13.03 eV above the anion."""
    found = _cyanide()
    assert set(found) == {"orca.fukui_plus", "orca.fukui_minus", "orca.fukui_zero", "orca.fukui_dual"}
    assert _atoms(found["orca.fukui_plus"]) == pytest.approx([0.595053, 0.404947], abs=1e-6)
    assert _atoms(found["orca.fukui_minus"]) == pytest.approx([0.599534, 0.400466], abs=1e-6)
    parameters = found["orca.fukui_plus"].provenance.parameters
    assert parameters["starts_run"] == 3 and parameters["starts_failed"] == 0 and "start_note" not in parameters
    gap = (-92.290207363006 + 92.769156504006) * HARTREE_TO_EV
    assert parameters["unbound_anion_ev"] == pytest.approx(gap, abs=1e-9) and gap == pytest.approx(13.033, abs=5e-4)
    assert parameters["anion_s_squared"] == 0.751473 and parameters["cation_s_squared"] == 0.757664


def test_the_restored_f_plus_of_an_anion_is_the_quantity_the_first_gate_measured():
    """The dianion came back after the second gate. At the level and geometry of the first gate's decided anion it gives that gate's own numbers, to 2e-5 (the first
    gate's run was a separate ORCA optimization, whose bond length differs from this fixture's by the optimizer's tolerance), so it is not a different calculation."""
    found = _cyanide()
    assert _atoms(found["orca.fukui_plus"]) == pytest.approx(FIRST_GATE_CYANIDE_F_PLUS, abs=2e-5)
    assert _atoms(found["orca.fukui_minus"]) == pytest.approx(FIRST_GATE_CYANIDE_F_MINUS, abs=5e-5)


# --- a dianion that did not finish: f- alone, and the reason --------------------------------------------------------------------------


DIANION_DID_NOT_FINISH = "ORCA printed no SCF energy and Hirshfeld table for the dianion (job 5), most likely because its SCF did not converge."


def test_a_dianion_that_did_not_converge_costs_f_plus_and_nothing_else():
    """The fifth job was given two SCF iterations, so ORCA ended the run (exit 115) there: the four jobs before it are intact, f- is the same four-job answer,
    and f+, f0 and the dual descriptor are absent with the reason, instead of the whole result failing."""
    found = _methoxide_anion(METHOXIDE_FAILED_DIANION)
    assert set(found) == {"orca.fukui_minus"}
    assert _atoms(found["orca.fukui_minus"]) == pytest.approx(ANION_F_MINUS, abs=1e-6)
    parameters = found["orca.fukui_minus"].provenance.parameters
    assert parameters["functions"] == "f-" and parameters["reference_charge"] == -1
    assert parameters["f_plus_note"] == f_plus_not_computed_sentence(DIANION_DID_NOT_FINISH)
    assert parameters["f_plus_note"] in parameters["caveat"]
    # the choice among the anion's three starts and the neutral radical's one is still reported; the dianion, which never ran, adds nothing
    assert parameters["starts_run"] == 4 and parameters["starts_failed"] == 0
    assert "unbound_anion_ev" not in parameters and "anion_s_squared" not in parameters


def test_a_dianion_that_did_not_converge_does_not_fail_the_run():
    mol = _mol_from_input("C[O-]", _text("methoxide_fukui_failed_dianion.inp"))
    values, _conformer = OrcaQuantumEngineProvider().parse_output(METHOXIDE_FAILED_DIANION, mol, "mol-1", "fukui")
    assert [d.descriptor_id for d in values] == ["orca.scf_energy"]


def test_the_summary_of_that_run_says_the_reason_and_not_the_general_sentence():
    lines = summary_lines(list(_methoxide_anion(METHOXIDE_FAILED_DIANION).values()), METHOXIDE_ATOMS)
    assert f_plus_not_computed_sentence(DIANION_DID_NOT_FINISH) in lines and f_plus_not_computed_sentence() not in lines
    assert not any(line.startswith("Largest f+") for line in lines)


def test_an_anion_whose_run_ended_at_an_earlier_job_says_it_never_reached_the_dianion():
    """The v2-era failed-start output: the Hueckel start (job 4) of the anion did not converge and ORCA ended the run there. A dianion job written after it would never
    have run, and the output has none; the result says why f+ is missing rather than that no basis set binds a dianion."""
    parameters = _methoxide(METHOXIDE_FAILED)["orca.fukui_minus"].provenance.parameters
    assert parameters["f_plus_note"] == f_plus_not_computed_sentence("ORCA ended the run at job 4, which did not converge, before it reached the dianion.")
    assert parameters["start_note"] in parameters["caveat"] and parameters["f_plus_note"] in parameters["caveat"]


def test_an_output_with_no_dianion_job_and_no_failed_job_keeps_the_general_sentence_and_says_where_the_switch_is():
    """What a run with f+ of an anion switched off in Settings prints (and what Fukui v2's builder wrote): no dianion job, and no job that failed. The sentence says the
    run left the dianion out and points at Settings, rather than saying nothing about why it is missing."""
    note = _methoxide()["orca.fukui_minus"].provenance.parameters["f_plus_note"]
    assert note == f_plus_not_computed_sentence()
    assert "no basis set binds in the gas phase" in note and note.endswith("This run left the dianion out; Settings > Quantum chemistry can switch it on.")


def _corrupt_dianion_carbon(replacement: str) -> str:
    """The seven-job output with the dianion's carbon row (the only row with -0.287031) changed to `replacement`: a deliberate corruption of a real output."""
    assert METHOXIDE_ANION.count("-0.287031") == 1
    return METHOXIDE_ANION.replace("-0.287031", replacement)


def test_a_dianion_table_that_misses_a_few_hundredths_of_an_electron_is_the_integration_and_costs_f_plus_only():
    """Carbon -0.237031 puts the dianion's charges at -1.949818, 0.050 from -2: too small to be another state's table, so it is the grid, with the diffuse advice."""
    found = _methoxide_anion(_corrupt_dianion_carbon("-0.237031"))
    assert set(found) == {"orca.fukui_minus"}
    note = found["orca.fukui_minus"].provenance.parameters["f_plus_note"]
    assert "The dianion (N+1 electrons) state's charges sum to -1.950, 0.050 electrons from its charge of -2" in note
    assert "numerical integration" in note and "diffuse" in note
    assert note.endswith("f- needs only the anion and the neutral radical it becomes, and is complete.")


def test_a_dianion_table_that_is_another_states_is_dropped_the_same_way():
    found = _methoxide_anion(_corrupt_dianion_carbon("-0.987031"))
    assert set(found) == {"orca.fukui_minus"}
    assert "the table read is not that state's" in found["orca.fukui_minus"].provenance.parameters["f_plus_note"]


def test_the_same_corruption_of_a_neutral_species_n_plus_one_table_still_fails_the_run():
    """Only an anion's N+1 state is optional. Acetone's anion table with a row changed by half an electron is refused, as it always was. The table read is the HCore
    start's (the fourth job's: it is 1.013 eV below ORCA's default start), so that is the one changed."""
    parts = ACETONE.split("HIRSHFELD ANALYSIS")
    row = next(line for line in parts[4].splitlines() if line.split()[:2] == ["0", "C"])
    changed = row.replace(row.split()[2], f"{float(row.split()[2]) + 0.5:.6f}")
    broken = "HIRSHFELD ANALYSIS".join([*parts[:4], parts[4].replace(row, changed), *parts[5:]])
    assert broken != ACETONE
    with pytest.raises(OrcaOutputError, match=r"anion \(N\+1 electrons\) state's charges sum to"):
        _acetone(broken)


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
