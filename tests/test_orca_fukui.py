"""The ORCA side of the Fukui calculation: the input it writes and the output it reads.

`tests/fixtures/orca/water_fukui.out` is VERBATIM extracts of a real ORCA 6.1.1 compound run written by
`build_input` (`! HF STO-3G` on water at its textbook geometry, O-H 0.9572 A and H-O-H 104.52 degrees): the version
banner, each job's echo of its charge and multiplicity, the Mulliken and Loewdin charge blocks of the first job, the
three Hirshfeld blocks, and the three energy lines, in the order ORCA printed them. Every other line (about 100 KB,
mostly SCF iterations) is dropped.

The expected numbers below are worked out by hand from the Hirshfeld rows that file prints, not by the code under test:

    neutral  O -0.311603  H 0.155803  H 0.155803
    cation   O  0.331199  H 0.334402  H 0.334402
    anion    O -0.684286  H -0.157855 H -0.157855
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import (
    CALC_TYPE_LABELS,
    OrcaOutputError,
    OrcaQuantumEngineProvider,
    parse_hirshfeld_tables,
)

FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "water_fukui.out"
REAL_OUTPUT = FIXTURE.read_text(encoding="utf-8")

NEUTRAL = {"O": -0.311603, "H": 0.155803}
CATION = {"O": 0.331199, "H": 0.334402}
ANION = {"O": -0.684286, "H": -0.157855}

#: By hand: f+ = q(N) - q(N+1), f- = q(N-1) - q(N), f0 = their mean, dual = f+ - f-.
EXPECTED = {
    "orca.fukui_plus": [0.372683, 0.313658, 0.313658],
    "orca.fukui_minus": [0.642802, 0.178599, 0.178599],
    "orca.fukui_zero": [0.5077425, 0.2461285, 0.2461285],
    "orca.fukui_dual": [-0.270119, 0.135059, 0.135059],
}


def _water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


def _datasets(output: str = REAL_OUTPUT, mol=None) -> dict:
    found = OrcaQuantumEngineProvider().parse_per_atom_output(output, mol or _water(), "mol-1", "fukui")
    return {dataset.property_id: dataset for dataset in found}


# --- the input -------------------------------------------------------------------------------------------------------


def _input(charge: int = 0, multiplicity: int = 1) -> str:
    return OrcaQuantumEngineProvider().build_input(_water(), charge, multiplicity, "B3LYP def2-SVP", "fukui")


def test_the_input_is_three_jobs_neutral_then_cation_then_anion():
    """ORCA gives no way to tell the three results apart but their order, so the order is the contract: a
    swapped cation and anion would flip f+ and f- and produce numbers that look entirely reasonable."""
    text = _input()
    assert text.count("$new_job") == 2
    assert [line for line in text.splitlines() if line.startswith("* xyz")] == ["* xyz 0 1", "* xyz 1 2", "* xyz -1 2"]


def test_each_job_prints_its_hirshfeld_table_before_its_coordinates():
    """The block goes before `* xyz` in every job, like every ORCA block but %eprnmr; ORCA reads the print flag
    for the job it precedes, so one block at the top would give the neutral state a table and no other."""
    jobs = _input().split("$new_job")
    assert len(jobs) == 3
    for job in jobs:
        assert "%output" in job and "Print[P_Hirshfeld] 1" in job
        assert job.index("%output") < job.index("* xyz")


def test_nothing_is_optimized_and_every_job_shares_one_geometry():
    """The Fukui function is the response at FIXED nuclei: an Opt on an ion would measure a different thing."""
    text = _input()
    assert "Opt" not in text
    blocks = [job.split("* xyz")[1].split("*")[0].splitlines()[1:] for job in text.split("$new_job")]
    assert blocks[0] == blocks[1] == blocks[2] and len(blocks[0]) == 3


def test_a_cation_carries_its_charge_through_all_three_states():
    text = _input(charge=1)
    assert [line for line in text.splitlines() if line.startswith("* xyz")] == ["* xyz 1 1", "* xyz 2 2", "* xyz 0 2"]


def test_an_anion_is_two_jobs_because_its_n_plus_one_state_is_a_dianion():
    """An anion has no f+ here: the dianion is not bound by any basis set in the gas phase (`chem.fukui_plan`), so only the N and N-1 states are run."""
    text = _input(charge=-1)
    assert [line for line in text.splitlines() if line.startswith("* xyz")] == ["* xyz -1 1", "* xyz 0 2"]
    assert text.count("$new_job") == 1


@pytest.mark.parametrize("multiplicity", [2, 3])
def test_an_open_shell_species_is_refused_with_the_reason(multiplicity):
    """Delta-SCF takes the lower-spin ion and says so; here the cation and anion each have more than one spin state
    and the Fukui function is not defined until one is chosen, so nothing is guessed."""
    with pytest.raises(ValueError, match="closed-shell"):
        _input(multiplicity=multiplicity)


def test_the_method_and_basis_come_from_the_caller():
    text = OrcaQuantumEngineProvider().build_input(_water(), 0, 1, "PBE0 def2-TZVP", "fukui")
    assert text.count("! PBE0 def2-TZVP") == 3


def _jobs(text: str) -> list[str]:
    return text.split("$new_job")


def test_every_job_states_whether_it_is_restricted_and_a_singlet_is_never_left_to_inherit_it():
    """ORCA switches the first doublet to UHF/UKS and keeps that for the later jobs of a compound input, so a closed-shell job written after it ran unrestricted
    (measured: `HFTyp .... UHF` and <S**2> 0 on the extra starts of a closed-shell anion). Each job says what it is."""
    jobs = _jobs(_input())
    assert [("HFTyp RHF" in job, "HFTyp UHF" in job) for job in jobs] == [(True, False), (False, True), (False, True)]
    for job in _jobs(OrcaQuantumEngineProvider().build_input(_water(), -1, 1, "B3LYP 6-31+G*", "fukui")):
        singlet = "* xyz -1 1" in job
        assert ("HFTyp RHF" in job) == singlet and ("HFTyp UHF" in job) == (not singlet)


def test_every_job_has_the_finer_integration_grid_before_its_coordinates():
    """Hirshfeld charges are integrals on the grid, and ORCA's default one left 0.010 to 0.073 electrons of seven diffuse anions out."""
    for job in _jobs(_input()):
        assert "%method\n  IntAcc 6.0\nend" in job
        assert job.index("IntAcc 6.0") < job.index("* xyz")


def test_a_basis_without_diffuse_functions_writes_no_guess_keyword_anywhere():
    for charge, jobs in ((0, 3), (1, 3), (-1, 2)):
        text = OrcaQuantumEngineProvider().build_input(_water(), charge, 1, "B3LYP 6-31G**", "fukui")
        assert len(_jobs(text)) == jobs
        assert "HCore" not in text and "Hueckel" not in text


def test_a_diffuse_basis_adds_the_extra_starts_of_the_anionic_state_after_every_default_job():
    text = OrcaQuantumEngineProvider().build_input(_water(), 0, 1, "B3LYP 6-311+G**", "fukui")
    jobs = _jobs(text)
    assert [line for line in text.splitlines() if line.startswith("* xyz")] == ["* xyz 0 1", "* xyz 1 2", "* xyz -1 2", "* xyz -1 2", "* xyz -1 2"]
    assert [next(line for line in job.splitlines() if line.startswith("!")) for job in jobs] == [
        "! B3LYP 6-311+G**", "! B3LYP 6-311+G**", "! B3LYP 6-311+G**", "! B3LYP 6-311+G** HCore", "! B3LYP 6-311+G** Hueckel"
    ]


def test_an_anion_at_a_diffuse_basis_has_two_states_and_two_extra_starts_of_its_own_n_state():
    text = OrcaQuantumEngineProvider().build_input(_water(), -1, 1, "B3LYP 6-31+G*", "fukui")
    assert [line for line in text.splitlines() if line.startswith("* xyz")] == ["* xyz -1 1", "* xyz 0 2", "* xyz -1 1", "* xyz -1 1"]
    assert text.count("HCore") == 1 and text.count("Hueckel") == 1


def test_the_other_calc_types_are_untouched_by_the_fukui_additions():
    for calc_type in ("sp", "opt", "delta_scf", "nmr"):
        text = OrcaQuantumEngineProvider().build_input(_water(), 0, 1, "B3LYP 6-31+G*", calc_type)
        assert "IntAcc" not in text and "HFTyp" not in text and "HCore" not in text


# --- reading the tables ----------------------------------------------------------------------------------------------


def test_three_hirshfeld_tables_are_read_in_file_order():
    tables = parse_hirshfeld_tables(REAL_OUTPUT)
    assert len(tables) == 3
    for table, states in zip(tables, (NEUTRAL, CATION, ANION)):
        assert [element for element, _ in table] == ["O", "H", "H"]
        assert [charge for _, charge in table] == [states["O"], states["H"], states["H"]]


def test_the_table_ends_at_the_total_row():
    """The `TOTAL` row has the same four columns as an atom row without the index, so it must not be read as an atom."""
    assert all(len(table) == 3 for table in parse_hirshfeld_tables(REAL_OUTPUT))


def test_a_crlf_output_reads_the_same():
    """ORCA's output has CRLF line ends on Windows (found by a live run once before); the parse must not care."""
    assert parse_hirshfeld_tables(REAL_OUTPUT.replace("\n", "\r\n")) == parse_hirshfeld_tables(REAL_OUTPUT)


#: VERBATIM from a real ORCA 6.1.1 run of formaldehyde with `! B3LYP def2-SVP MBIS CHELPG` and `Print[P_Hirshfeld] 1`:
#: the MBIS table that follows the Hirshfeld one has a POPULATION column, and its valence-shell block rows look like
#: atom rows too. Neither may be taken for Hirshfeld rows.
MBIS_AFTER_HIRSHFELD = """
------------------
HIRSHFELD ANALYSIS
------------------

Total integrated alpha density =      7.999999505
Total integrated beta density  =      7.999999505

  ATOM     CHARGE      SPIN
   0 C    0.152559    0.000000
   1 O   -0.221511    0.000000
   2 H    0.034476    0.000000
   3 H    0.034476    0.000000

  TOTAL   0.000001    0.000000


------------------
MBIS ANALYSIS
------------------

Convergence threshold (charges)      ...        1.000e-06
Number of iterations                 ...        50

Total integrated alpha density       ...      7.999999505
Total integrated beta density        ...      7.999999505

  ATOM     CHARGE    POPULATION     SPIN
   0 C    0.368886    5.631114    0.000000
   1 O   -0.391741    8.391741    0.000000
   2 H    0.011428    0.988572    0.000000
   3 H    0.011428    0.988572    0.000000

  TOTAL   0.000001   15.999999    0.000000

 MBIS VALENCE-SHELL DATA:
  ATOM   POPULATION   WIDTH(A.U.)
   0 C    3.986360    0.481018
   1 O    6.783069    0.388131
   2 H    0.988572    0.399365
   3 H    0.988572    0.399365
"""


def test_an_mbis_table_after_the_hirshfeld_one_is_not_read_as_atoms():
    tables = parse_hirshfeld_tables(MBIS_AFTER_HIRSHFELD)
    assert tables == [[("C", 0.152559), ("O", -0.221511), ("H", 0.034476), ("H", 0.034476)]]


def test_an_output_with_no_hirshfeld_table_has_none():
    assert parse_hirshfeld_tables("MULLIKEN ATOMIC CHARGES\n   0 O :   -0.366360\n") == []


# --- the per-atom datasets --------------------------------------------------------------------------------------------


def test_the_four_datasets_are_the_hand_computed_finite_differences():
    found = _datasets()
    assert set(found) == set(EXPECTED)
    for property_id, expected in EXPECTED.items():
        values = found[property_id].values
        assert sorted(values) == [0, 1, 2]
        assert [values[i] for i in range(3)] == pytest.approx(expected, abs=1e-6)


def test_the_sum_rule_holds_on_the_real_numbers():
    found = _datasets()
    assert sum(found["orca.fukui_plus"].values.values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(found["orca.fukui_minus"].values.values()) == pytest.approx(1.0, abs=1e-5)
    assert sum(found["orca.fukui_dual"].values.values()) == pytest.approx(0.0, abs=1e-5)


def test_the_numbers_are_hirshfeld_not_mulliken():
    """The Mulliken block sits in the same output, right above the Hirshfeld one. Differencing the wrong block gives
    plausible numbers (Mulliken's oxygen charge is -0.366, Hirshfeld's -0.312); the values must be Hirshfeld's."""
    plus_on_oxygen = _datasets()["orca.fukui_plus"].values[0]
    assert plus_on_oxygen == pytest.approx(-0.311603 + 0.684286, abs=1e-6)
    assert plus_on_oxygen != pytest.approx(-0.366360 + 0.684286, abs=1e-3)


def test_a_crlf_output_gives_the_same_datasets():
    plain = _datasets()
    crlf = _datasets(REAL_OUTPUT.replace("\n", "\r\n"))
    for property_id in EXPECTED:
        assert crlf[property_id].values == plain[property_id].values


def test_names_ids_category_and_units():
    found = _datasets()
    assert found["orca.fukui_plus"].name == "Fukui f+ (Hirshfeld)"
    assert found["orca.fukui_minus"].name == "Fukui f- (Hirshfeld)"
    assert found["orca.fukui_zero"].name == "Fukui f0 (Hirshfeld)"
    assert found["orca.fukui_dual"].name == "Dual descriptor f+ - f- (Hirshfeld)"
    for dataset in found.values():
        assert dataset.molecule_uuid == "mol-1"
        assert dataset.category == "quantum_chemistry"
        assert dataset.method == "orca"
        assert dataset.units == ""


def test_provenance_says_scheme_vertical_version_and_the_unbound_anion():
    """At STO-3G the water anion is 15.98 eV ABOVE the neutral (E -74.375667 against -74.962928 Eh), and the
    dataset must say so wherever it is read."""
    parameters = _datasets()["orca.fukui_plus"].provenance.parameters
    assert parameters["charge_scheme"] == "hirshfeld"
    assert parameters["states"] == "vertical"
    assert parameters["orca_version"] == "6.1.1"
    assert parameters["unbound_anion_ev"] == pytest.approx((-74.375666859613 + 74.962928183933) * 27.211386245988)
    assert "ABOVE" in parameters["caveat"]


def test_every_other_calc_type_has_no_per_atom_output():
    provider = OrcaQuantumEngineProvider()
    for calc_type in ("sp", "opt", "opt_freq", "nmr", "delta_scf"):
        assert provider.parse_per_atom_output(REAL_OUTPUT, _water(), "mol-1", calc_type) == []


# --- parse_output: the run fails when the numbers cannot be read -----------------------------------------------------


def test_parse_output_returns_only_the_neutral_energy_and_no_koopmans_numbers():
    """Three orbital tables follow in the output, and the frontier parsers take the LAST: the anion's. Koopmans
    descriptors read from it would be about a different species, so none are emitted."""
    values, conformer = OrcaQuantumEngineProvider().parse_output(REAL_OUTPUT, _water(), "mol-1", "fukui")
    assert [(d.descriptor_id, d.value) for d in values] == [("orca.scf_energy", -74.962928183933)]
    assert conformer is None


def test_a_job_missing_an_ion_fails_loudly():
    """Two tables of three means an ion did not converge. Differencing the two that did would give a number for the wrong pair, and the
    message names the STATE that is missing (the old one could only say the totals were wrong)."""
    truncated = REAL_OUTPUT.rsplit("FINAL SINGLE POINT ENERGY", 1)[0]
    truncated = truncated.rsplit("Total Charge", 1)[0]
    with pytest.raises(OrcaOutputError, match=r"The N\+1 state of this Fukui calculation did not finish"):
        OrcaQuantumEngineProvider().parse_output(truncated, _water(), "mol-1", "fukui")


def test_a_job_that_started_but_never_finished_is_named():
    """ORCA echoes a job's charge and multiplicity as it starts it, so a job that died has a stretch of output with no energy and no table. It is
    the N+1 state, and says so, where counting energies could only say there were two."""
    started_not_finished = REAL_OUTPUT.rsplit("FINAL SINGLE POINT ENERGY", 1)[0].rsplit("HIRSHFELD ANALYSIS", 1)[0]
    assert started_not_finished.count("Total Charge") == 3
    with pytest.raises(OrcaOutputError, match=r"N\+1 state.*job 3"):
        OrcaQuantumEngineProvider().parse_output(started_not_finished, _water(), "mol-1", "fukui")


def test_an_output_with_the_ions_swapped_is_refused_by_the_sum_check():
    """The charge each job echoes is what assigns a table to a state. Swap the cation's and anion's `Total Charge` lines and each table is now read as the
    OTHER state's, so its charges sum to the wrong charge and the state is named in the refusal. (The old parse refused this by position; the echoed
    charge is the better evidence, and the sum rule is the check on it.)"""
    cation_line = " Total Charge           Charge          ....    1\n"
    anion_line = " Total Charge           Charge          ....   -1\n"
    assert REAL_OUTPUT.count(cation_line) == 1 and REAL_OUTPUT.count(anion_line) == 1
    swapped = REAL_OUTPUT.replace(cation_line, "@@").replace(anion_line, cation_line).replace("@@", anion_line)
    with pytest.raises(OrcaOutputError, match=r"(cation|anion) \(N[-+]1 electrons\) state's charges sum to"):
        OrcaQuantumEngineProvider().parse_output(swapped, _water(), "mol-1", "fukui")


def test_an_output_whose_first_job_is_not_closed_shell_is_refused():
    open_shell = REAL_OUTPUT.replace(" Multiplicity           Mult            ....    1\n", " Multiplicity           Mult            ....    2\n", 1)
    assert open_shell != REAL_OUTPUT
    with pytest.raises(OrcaOutputError, match="Job 1 of this output"):
        OrcaQuantumEngineProvider().parse_output(open_shell, _water(), "mol-1", "fukui")


def test_an_output_with_no_job_echo_is_refused():
    """`parse_output` fails first on the missing energy (it always has); the per-atom parse, which a stored run's re-read goes through, says why."""
    with pytest.raises(OrcaOutputError, match="echoes no job's charge"):
        OrcaQuantumEngineProvider().parse_per_atom_output("nothing here", _water(), "mol-1", "fukui")


def test_an_output_of_another_molecule_is_refused():
    methane = Chem.AddHs(Chem.MolFromSmiles("C"))
    AllChem.EmbedMolecule(methane, randomSeed=7)
    with pytest.raises(OrcaOutputError, match="not this molecule's"):
        OrcaQuantumEngineProvider().parse_output(REAL_OUTPUT, methane, "mol-1", "fukui")


def test_a_hirshfeld_table_in_another_state_is_refused_by_the_sum_check():
    """A cation table pasted over the anion's still has three atoms and the right elements; only its charges give it
    away, and the sum check names the state."""
    anion_rows = "   0 O   -0.684286    0.475077"
    assert anion_rows in REAL_OUTPUT
    broken = REAL_OUTPUT.replace(anion_rows, "   0 O    0.331199    0.475077")
    with pytest.raises(OrcaOutputError, match="anion"):
        OrcaQuantumEngineProvider().parse_output(broken, _water(), "mol-1", "fukui")


def test_mulliken_alone_cannot_stand_in_for_a_missing_hirshfeld_table():
    """With the Hirshfeld blocks gone the job has nothing to difference, even though Mulliken charges are printed."""
    no_hirshfeld = REAL_OUTPUT.replace("HIRSHFELD ANALYSIS", "NOT A TABLE")
    with pytest.raises(OrcaOutputError):
        OrcaQuantumEngineProvider().parse_output(no_hirshfeld, _water(), "mol-1", "fukui")


# --- how it is offered ------------------------------------------------------------------------------------------------


def test_fukui_is_offered_in_the_panel_and_described():
    from openchem.bootstrap import _QM_CALC_TYPE_DESCRIPTIONS

    assert CALC_TYPE_LABELS["Fukui functions (Hirshfeld)"] == "fukui"
    assert set(_QM_CALC_TYPE_DESCRIPTIONS) == set(CALC_TYPE_LABELS.values())
    assert "Closed-shell" in _QM_CALC_TYPE_DESCRIPTIONS["fukui"]


# --- <S**2> of the ions ----------------------------------------------------------------------------------------------------------------


def test_the_expectation_of_s_squared_of_each_ion_is_recorded_from_the_real_output():
    """ORCA prints it once per unrestricted job: 0.755189 for the water cation and 0.758372 for the anion, verbatim in the fixture."""
    parameters = _datasets()["orca.fukui_plus"].provenance.parameters
    assert parameters["cation_s_squared"] == 0.755189 and parameters["anion_s_squared"] == 0.758372


def _warns_of_contamination(caveat: str) -> bool:
    """Whether the caveat carries a per-ion spin warning. The "Not validated" sentence also contains the word (it names the case that
    failed the gate), so the match is on the sentence that begins with the ion."""
    return "The cation is spin-contaminated" in caveat or "The anion is spin-contaminated" in caveat


def test_clean_doublets_carry_no_spin_warning_but_every_result_says_it_is_not_validated():
    caveat = _datasets()["orca.fukui_plus"].provenance.parameters["caveat"]
    assert not _warns_of_contamination(caveat) and "Not validated" in caveat


def test_a_contaminated_cation_in_the_output_reaches_the_caveat():
    """Carbon monoxide's cation at HF/6-31G** read 0.967; put that number where ORCA printed the cation's."""
    contaminated = REAL_OUTPUT.replace("0.755189", "0.967155")
    assert contaminated != REAL_OUTPUT
    parameters = _datasets(contaminated)["orca.fukui_plus"].provenance.parameters
    assert parameters["cation_s_squared"] == 0.967155
    assert "The cation is spin-contaminated (<S^2> = 0.97" in parameters["caveat"]
    assert "anion is spin-contaminated" not in parameters["caveat"]


def test_an_output_with_no_s_squared_lines_says_nothing_about_contamination():
    stripped = "\n".join(
        line for line in REAL_OUTPUT.splitlines() if not line.startswith(("Expectation value of <S**2>", "Ideal value S*(S+1)"))
    )
    assert stripped != REAL_OUTPUT
    parameters = _datasets(stripped)["orca.fukui_plus"].provenance.parameters
    assert "cation_s_squared" not in parameters and not _warns_of_contamination(parameters["caveat"])


def test_the_last_energy_of_a_job_is_its_energy_as_the_last_s_squared_is_its_s_squared():
    """A single point prints one energy, so this cannot happen in a real run; the rule (the converged print is the last) is the same as for <S**2> and is pinned here, because the unbound-anion gap
    is a difference of two of these energies and an earlier line in a job's stretch must not be taken for it."""
    extra = REAL_OUTPUT.replace("FINAL SINGLE POINT ENERGY", "FINAL SINGLE POINT ENERGY       -1.000000000000\nFINAL SINGLE POINT ENERGY", 1)
    assert extra.count("FINAL SINGLE POINT ENERGY") == 4
    parameters = _datasets(extra)["orca.fukui_plus"].provenance.parameters
    assert parameters["unbound_anion_ev"] == pytest.approx((-74.375666859613 + 74.962928183933) * 27.211386245988)


def test_each_s_squared_is_read_from_its_own_job_so_a_later_print_in_that_job_wins():
    """The old parse took the two prints by POSITION and called any other count unknown. Now each is read from the stretch of output of the job it
    belongs to, so a second print inside the anion's job (appended here after its last line) is the anion's, the cation's is untouched, and the last
    print of a job is the one read, because it belongs to the converged density."""
    extra = REAL_OUTPUT + "\nExpectation value of <S**2>     :     0.990000\n"
    parameters = _datasets(extra)["orca.fukui_plus"].provenance.parameters
    assert parameters["cation_s_squared"] == 0.755189 and parameters["anion_s_squared"] == 0.99
    assert "The anion is spin-contaminated (<S^2> = 0.99" in parameters["caveat"]
    assert "The cation is spin-contaminated" not in parameters["caveat"]
