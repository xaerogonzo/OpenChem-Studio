"""The ORCA side of Fukui v3, the search for other states of the cation, on REAL ORCA 6.1.1 output written by the application's own input builder.

`tests/fixtures/orca/*_fukui_cation_search*.out` are verbatim extracts (`benchmarks/fukui_gate_2/make_fixtures.py` regenerates them): the version banner, ORCA's echo of the whole
compound input, each job's echo of charge, multiplicity and electron count, its guess, its <S**2> lines, its Hirshfeld block and energy line, and the first job's orbital table.
The `.inp` beside each is the exact input ORCA was given. Every expected number below is worked out from the rows those files print, not by the code under test.

    hcn_fukui_cation_search.out               HCN, B3LYP 6-31G*: six jobs (N, N-1, N+1, then the cation with the hole in the HOMO-1, HOMO-2 and HOMO-3). The default job and the
                                              HOMO-1 hole reach the pi state (the HOMO is a degenerate pair of equal charges); the HOMO-2 and HOMO-3 holes reach a sigma state 0.39 eV
                                              above it, 0.085 away in one atom's charge.
    hcn_fukui_cation_search_failed_hole.out   the same with its fifth job (the HOMO-2 hole) given two SCF iterations: ORCA ended the run there (exit 115), the HOMO-3 hole never ran.
    benzaldehyde_fukui_cation_search.out      benzaldehyde at its ORCA optimized geometry: the default job reached a state 0.145 eV ABOVE the lowest (the state the published numbers belong
                                              to), the HOMO-1 hole a state 0.127 eV above it, and the HOMO-2 and HOMO-3 holes the lowest.
    benzene_fukui_cation_search.out           benzene: the HOMO is a degenerate e1g pair whose two states differ in f- by atom, the default job and the HOMO-1 hole reaching one each.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Geometry import Point3D

from openchem.chem.fukui_plan import START_DEFAULT, STATE_N, STATE_OXIDISED, STATE_REDUCED
from openchem.chem.orca_engine import OrcaQuantumEngineProvider, parse_hirshfeld_tables

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


CASES = {
    "hcn": ("C#N", "hcn_fukui_cation_search"),
    "hcn_failed": ("C#N", "hcn_fukui_cation_search_failed_hole"),
    "benzaldehyde": ("O=Cc1ccccc1", "benzaldehyde_fukui_cation_search"),
    "benzene": ("c1ccccc1", "benzene_fukui_cation_search"),
}


def _case(key: str) -> tuple[str, Chem.Mol]:
    smiles, name = CASES[key]
    return _text(f"{name}.out"), _mol_from_input(smiles, _text(f"{name}.inp"))


def _datasets(key: str, output: str | None = None) -> dict:
    text, mol = _case(key)
    found = OrcaQuantumEngineProvider().parse_per_atom_output(output if output is not None else text, mol, "mol-1", "fukui")
    return {dataset.property_id: dataset for dataset in found}


def _values(dataset) -> list[float]:
    return [dataset.values[index] for index in range(len(dataset.values))]


def _tables(output: str) -> list[list[float]]:
    return [[charge for _element, charge in table] for table in parse_hirshfeld_tables(output)]


def _energies(output: str) -> list[float]:
    import re

    return [float(value) for value in re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", output)]


# --- the input the application writes is the input ORCA was given ----------------------------------------------------------------


@pytest.mark.parametrize("key", ["hcn", "benzaldehyde", "benzene"])
def test_the_builder_writes_exactly_the_input_the_real_run_was_given(key):
    """The input that produced the output the other tests read, so a change to the builder that changes what ORCA is asked fails here until the fixtures are regenerated."""
    smiles, name = CASES[key]
    expected = _text(f"{name}.inp")
    assert OrcaQuantumEngineProvider().build_input(_mol_from_input(smiles, expected), 0, 1, "B3LYP 6-31G*", "fukui") == expected


def test_the_failed_hole_input_is_the_hcn_input_with_two_scf_iterations_given_to_the_fifth_job():
    failing = _text("hcn_fukui_cation_search_failed_hole.inp")
    jobs = failing.split("$new_job")
    assert failing.count("  MaxIter 2\n") == 1 and "  MaxIter 2\n" in jobs[4] and "Rotate {4, 6," in jobs[4]
    assert failing.replace("  MaxIter 2\n", "") == _text("hcn_fukui_cation_search.inp")


def test_a_hole_start_reads_the_neutrals_orbitals_and_swaps_the_homo_with_the_orbital_the_hole_goes_to():
    """HCN has 14 electrons, so its HOMO is orbital 6 and the holes go to orbitals 5, 4 and 3. Benzaldehyde has 56, HOMO 27, holes at 26, 25 and 24."""
    for key, homo in (("hcn", 6), ("benzaldehyde", 27)):
        jobs = _text(f"{CASES[key][1]}.inp").split("$new_job")
        assert len(jobs) == 6
        for offset, job in zip((1, 2, 3), jobs[3:]):
            assert job.strip().splitlines()[0] == "! B3LYP 6-31G* MORead"
            assert '%moinp "job.gbw"' in job and f"  Rotate {{{homo - offset}, {homo}, 90, 1, 1}} end" in job
            assert "HFTyp UHF" in job and "* xyz 1 2" in job
            # The swap is inside the SCF block, which closes after it, and everything sits before the coordinates.
            assert job.index("%scf") < job.index("Rotate") < job.index("end\n%method") < job.index("* xyz")
        # The jobs before them read nothing by name: the first starts from ORCA's guess and the second and third from the previous job's orbitals.
        assert all("%moinp" not in job and "MORead" not in job and "Rotate" not in job for job in jobs[:3])


def test_the_holes_come_after_the_n_plus_one_state_for_a_neutral_species():
    jobs = [line for line in _text("hcn_fukui_cation_search.inp").splitlines() if line.startswith("* xyz")]
    assert jobs == ["* xyz 0 1", "* xyz 1 2", "* xyz -1 2", "* xyz 1 2", "* xyz 1 2", "* xyz 1 2"]


def test_with_the_search_switched_off_the_input_is_the_three_jobs_it_was():
    provider = OrcaQuantumEngineProvider(cation_search=lambda: False)
    text = provider.build_input(_mol_from_input("C#N", _text("hcn_fukui_cation_search.inp")), 0, 1, "B3LYP 6-31G*", "fukui")
    assert text.count("$new_job") == 2 and "Rotate" not in text and "MORead" not in text


def test_a_molecule_with_no_search_gets_the_three_jobs_whatever_the_setting():
    """Dihydrogen has no orbital below its HOMO and hydrogen iodide an element heavier than krypton: neither can be written a hole start."""
    for smiles in ("[H][H]", "I"):
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()), assignId=True)
        assert OrcaQuantumEngineProvider().build_input(mol, 0, 1, "B3LYP def2-SVP", "fukui").count("$new_job") == 2


def test_the_hole_needs_the_homo_and_a_builder_asked_for_one_without_it_refuses():
    mol = Chem.AddHs(Chem.MolFromSmiles("C#N"))
    mol.AddConformer(Chem.Conformer(mol.GetNumAtoms()), assignId=True)
    with pytest.raises(ValueError, match="HOMO"):
        OrcaQuantumEngineProvider()._build_fukui_input("! B3LYP 6-31G*", ["C 0 0 0", "N 0 0 1", "H 0 0 -1"], 0, 1, holes=(1,))


# --- reading ORCA's echo of the input and the first job's orbitals -----------------------------------------------------------------


@pytest.mark.parametrize("key", CASES)
def test_the_echoed_input_says_which_jobs_are_holes(key):
    output, _mol = _case(key)
    assert OrcaQuantumEngineProvider._echoed_holes(output) == [0, 0, 0, 1, 2, 3]
    # A CRLF output (ORCA's own on Windows) reads the same.
    assert OrcaQuantumEngineProvider._echoed_holes(output.replace("\n", "\r\n")) == [0, 0, 0, 1, 2, 3]


def test_an_output_without_the_echo_names_no_hole():
    """The fixtures of Fukui v2 were trimmed to the lines the parsers read and keep no echo; they say nothing of holes, and read as they always did."""
    assert OrcaQuantumEngineProvider._echoed_holes(_text("water_fukui.out")) == []
    assert OrcaQuantumEngineProvider._echoed_holes("") == []
    assert OrcaQuantumEngineProvider._echoed_holes("INPUT FILE\nnothing that ends the echo") == []


def test_the_jobs_are_named_from_the_echo_and_a_hole_start_is_told_from_the_default_one_though_ORCA_calls_both_MOREAD():
    output, mol = _case("hcn")
    results = OrcaQuantumEngineProvider._fukui_job_results(output, [atom.GetSymbol().upper() for atom in mol.GetAtoms()])
    assert [(job.state, job.start) for job in results] == [
        (STATE_N, START_DEFAULT), (STATE_OXIDISED, START_DEFAULT), (STATE_REDUCED, START_DEFAULT),
        (STATE_OXIDISED, "HOMO-1"), (STATE_OXIDISED, "HOMO-2"), (STATE_OXIDISED, "HOMO-3"),
    ]
    assert output.count("INITIAL GUESS: MOREAD") == 5  # the guess line of the cation, the dianion... and every hole says MOREAD: the echo is the only way to tell


def test_the_occupied_orbitals_of_the_first_job_are_read_up_to_the_first_virtual_one():
    energies = OrcaQuantumEngineProvider._occupied_orbital_energies(_case("hcn")[0])
    assert len(energies) == 7 and energies[-1] == -9.6716 and energies[-3:] == [-10.2372, -9.6716, -9.6716]
    assert len(OrcaQuantumEngineProvider._occupied_orbital_energies(_case("benzaldehyde")[0])) == 28
    assert OrcaQuantumEngineProvider._occupied_orbital_energies("no orbitals here") == []


def test_the_orbital_below_the_deepest_hole_is_how_far_under_the_homo_by_hand():
    """Benzaldehyde: the HOMO is -6.8402 eV and the fifth orbital down (the one below the HOMO-3) is -9.7986: 2.9584 eV. HCN's is orbital 2, -24.9187, 15.2471 eV down."""
    output, _ = _case("benzaldehyde")
    benzaldehyde_z = [8, 6, 6, 6, 6, 6, 6, 6, 1, 1, 1, 1, 1, 1]
    assert OrcaQuantumEngineProvider._untried_orbital_gap_ev(output, benzaldehyde_z, 0, 3) == pytest.approx(2.9584, abs=1e-4)
    assert OrcaQuantumEngineProvider._untried_orbital_gap_ev(_case("hcn")[0], [6, 7, 1], 0, 3) == pytest.approx(15.2471, abs=1e-4)
    # No orbital to ask about: a hole already at the deepest valence orbital (water: HOMO 4, core 1, so the HOMO-4 is the core), or no table.
    assert OrcaQuantumEngineProvider._untried_orbital_gap_ev(output, [8, 1, 1], 0, 3) is None
    assert OrcaQuantumEngineProvider._untried_orbital_gap_ev("", benzaldehyde_z, 0, 3) is None


# --- what the search finds, on real outputs ----------------------------------------------------------------------------------------


def test_hcn_reads_its_pi_state_and_reports_the_sigma_state_0_39_ev_above_it_with_how_far_its_f_minus_is():
    output, _ = _case("hcn")
    tables, energies = _tables(output), _energies(output)
    datasets = _datasets("hcn")
    # f- = q(N-1) - q(N), from the default job (which reached the lowest state, the HOMO-1 hole agreeing with it).
    expected = [cation - neutral for neutral, cation in zip(tables[0], tables[1])]
    assert _values(datasets["orca.fukui_minus"]) == pytest.approx(expected, abs=1e-9)
    # A state's energy is the lowest any job reached it at: the pi state's is the default job's or the HOMO-1 hole's, the sigma state's the HOMO-2 hole's or the HOMO-3's.
    sigma_gap = (min(energies[4], energies[5]) - min(energies[1], energies[3])) * HARTREE_TO_EV
    assert sigma_gap == pytest.approx(0.3915, abs=5e-4)
    sigma_difference = max(abs(a - b) for a, b in zip(tables[4], tables[1]))
    parameters = datasets["orca.fukui_minus"].provenance.parameters
    assert parameters["cation_search"] == "holes HOMO-1, HOMO-2, HOMO-3" and parameters["cation_states_found"] == 2
    assert parameters["cation_competing_ev"] == pytest.approx(sigma_gap, abs=1e-9)
    assert parameters["starts_run"] == 6 and parameters["starts_failed"] == 0 and "cation_degenerate_states" not in parameters
    note = parameters["cation_note"]
    assert f"Another state of the cation lies {sigma_gap:.2f} eV (its f- differs by up to {sigma_difference:.3f}, at C (atom 1)) above the one f- is read from" in note
    assert "f- depends on which state is meant." in note and note in parameters["caveat"]


def test_a_search_that_ended_early_says_which_holes_did_not_run_and_reads_what_it_has():
    full = _datasets("hcn")["orca.fukui_minus"]
    partial = _datasets("hcn_failed")["orca.fukui_minus"]
    # The sigma state was only reached by the holes that did not run, so the lowest state is the same and f- is the same.
    assert _values(partial) == pytest.approx(_values(full), abs=1e-9)
    parameters = partial.provenance.parameters
    assert parameters["starts_run"] == 5 and parameters["starts_failed"] == 1 and parameters["cation_states_found"] == 1
    assert "cation_competing_ev" not in parameters
    assert parameters["cation_note"] == (
        "The HOMO-2 and HOMO-3 starts of the search for other states of the cation did not run to the end "
        "(ORCA ended the run at a job that did not converge), so the search covered fewer holes than it was written with."
    )


def test_benzaldehyde_reads_the_lowest_state_and_not_the_one_the_default_job_reached():
    """The molecule whose f- was not a function of the structure. The default job reached the state 0.145 eV above the lowest (and v2 would have read it); the search reads the
    lowest, which differs by 0.13 at the oxygen, and reports the two states above it."""
    output, _ = _case("benzaldehyde")
    tables, energies = _tables(output), _energies(output)
    default_f_minus = [cation - neutral for neutral, cation in zip(tables[0], tables[1])]
    lowest_f_minus = [cation - neutral for neutral, cation in zip(tables[0], tables[4])]
    datasets = _datasets("benzaldehyde")
    assert _values(datasets["orca.fukui_minus"]) == pytest.approx(lowest_f_minus, abs=1e-9)
    assert abs(default_f_minus[0] - lowest_f_minus[0]) > 0.12  # the oxygen: 0.34 where the lowest state gives 0.21
    assert energies[1] - energies[4] == pytest.approx(0.14546 / HARTREE_TO_EV, abs=1e-6) and energies[4] == pytest.approx(energies[5], abs=1e-4)
    parameters = datasets["orca.fukui_minus"].provenance.parameters
    assert parameters["cation_states_found"] == 3 and parameters["start_gain_ev"] == pytest.approx(0.14546, abs=1e-4)
    assert parameters["cation_competing_ev"] == pytest.approx((energies[3] - energies[4]) * HARTREE_TO_EV, abs=1e-9)
    assert parameters["cation_note"] == (
        "Other states of the cation lie 0.13 eV (its f- differs by up to 0.093, at O (atom 1)) and 0.15 eV (its f- differs by up to 0.128, at O (atom 1)) above the one f- "
        "is read from, which is the lowest found. f- depends on which state is meant."
    )
    # The N and N+1 states are not touched: f+ is the neutral minus the dianion... the anion, as it was.
    expected_f_plus = [neutral - anion for neutral, anion in zip(tables[0], tables[2])]
    assert _values(datasets["orca.fukui_plus"]) == pytest.approx(expected_f_plus, abs=1e-9)


def test_benzene_averages_the_two_components_of_its_degenerate_level_and_gets_the_symmetric_answer():
    """The HOMO is an e1g pair: two states with one energy (to 6e-5 hartree here) whose Hirshfeld charges differ by up to 0.10 in one atom, so a single determinant gives a lopsided
    f-. The mean of the two is what the level's f- is, uniform over the six carbons and over the six hydrogens to a few parts in a thousand."""
    output, _ = _case("benzene")
    tables = _tables(output)
    first, second = tables[1], tables[3]
    assert max(abs(a - b) for a, b in zip(first, second)) > 0.09
    datasets = _datasets("benzene")
    f_minus = _values(datasets["orca.fukui_minus"])
    assert f_minus == pytest.approx([((a + b) / 2) - n for n, a, b in zip(tables[0], first, second)], abs=1e-9)
    carbons, hydrogens = f_minus[:6], f_minus[6:]
    assert max(carbons) - min(carbons) < 0.002 and max(hydrogens) - min(hydrogens) < 0.002
    assert sum(carbons) + sum(hydrogens) == pytest.approx(1.0, abs=1e-4)  # Hirshfeld's own integration error: each state's charges sum to its charge to a few 1e-6
    parameters = datasets["orca.fukui_minus"].provenance.parameters
    assert parameters["cation_degenerate_states"] == 2 and parameters["cation_states_found"] == 4
    assert parameters["cation_note"] == (
        "The cation has 2 states within 0.01 eV of each other (a degenerate level), and f- is read from the average of their Hirshfeld charges because which of them an SCF "
        "reaches is arbitrary; they differ by up to 0.104 electrons in one atom's charge."
    )
    # A single determinant would not have been symmetric: that is what the average is for.
    one = [a - n for n, a in zip(tables[0], first)]
    assert max(one[:6]) - min(one[:6]) > 0.04


def test_the_hole_starts_do_not_change_f_plus_or_the_neutral_for_any_fixture():
    for key in CASES:
        output, _ = _case(key)
        tables = _tables(output)
        datasets = _datasets(key)
        assert _values(datasets["orca.fukui_plus"]) == pytest.approx([n - a for n, a in zip(tables[0], tables[2])], abs=1e-9)


# --- the same parse on an output with no search ------------------------------------------------------------------------------------


def test_an_output_with_no_hole_start_says_no_search_was_run_and_why():
    water = Chem.AddHs(Chem.MolFromSmiles("O"))
    found = OrcaQuantumEngineProvider().parse_per_atom_output(_text("water_fukui.out"), water, "mol-1", "fukui")
    parameters = found[0].provenance.parameters
    assert parameters["cation_search"] == "not run"
    assert parameters["cation_note"].startswith("No search for other states of the cation was run (it was switched off in Settings > Quantum chemistry)")
    assert "benzaldehyde did, 6 of 14 runs one state and 8 the other" in parameters["cation_note"]
    assert "cation_states_found" not in parameters and "cation_competing_ev" not in parameters


def test_a_search_that_finds_only_states_far_above_the_window_says_nothing_but_records_that_it_looked():
    """Water's cation: the HOMO-1 hole (3a1) is 2.2 eV above the 1b1 state and the HOMO-2 (1b2) 6.4, both beyond 0.5 eV, so f- is the default job's and there is nothing to say."""
    mol = _mol_from_input("O", _text("water_fukui_cation_search.inp"))
    output = _text("water_fukui_cation_search.out")
    energies = _energies(output)
    found = OrcaQuantumEngineProvider().parse_per_atom_output(output, mol, "mol-1", "fukui")
    by_id = {dataset.property_id: dataset for dataset in found}
    tables = _tables(output)
    assert _values(by_id["orca.fukui_minus"]) == pytest.approx([cation - neutral for neutral, cation in zip(tables[0], tables[1])], abs=1e-9)
    parameters = by_id["orca.fukui_minus"].provenance.parameters
    assert parameters["cation_search"] == "holes HOMO-1, HOMO-2, HOMO-3" and parameters["cation_states_found"] == 3
    assert (energies[3] - energies[1]) * HARTREE_TO_EV == pytest.approx(2.2, abs=0.05) and (energies[4] - energies[1]) * HARTREE_TO_EV > 6.0
    assert "cation_note" not in parameters and "cation_competing_ev" not in parameters and parameters["starts_run"] == 6
    # Nothing about the search reaches the caveats either (the standing sentences are about the calculation as a whole).
    assert "Another state of the cation" not in parameters["caveat"] and "Other states of the cation" not in parameters["caveat"]
    assert "No search for other states" not in parameters["caveat"]


def test_a_search_that_ran_to_the_end_and_found_one_state_is_recorded_and_adds_no_sentence():
    """The same HCN input at which the sigma state is out of reach cannot be made from a real run, so the claim is made on the reading itself (`tests/test_fukui_states.py`):
    one state, no competing one, no failed job and nothing unreached is no sentence. Here the real HCN output's own reading has exactly one more thing to say than that."""
    from openchem.chem.fukui import cation_state_sentences
    from openchem.chem.fukui_plan import JobResult
    from openchem.chem.fukui_states import read_cation

    output, mol = _case("hcn")
    results = OrcaQuantumEngineProvider._fukui_job_results(output, [atom.GetSymbol().upper() for atom in mol.GetAtoms()])
    only_the_pi_state = [job for job in results if job.start in (START_DEFAULT, "HOMO-1") or job.state != STATE_OXIDISED]
    reading = read_cation(only_the_pi_state, planned_holes=(1,))
    assert len(reading.averaged) == 1 and reading.competing == () and not reading.incomplete
    assert cation_state_sentences(reading, 0, ["C", "N", "H"]) == []
    assert len(cation_state_sentences(read_cation(results, planned_holes=(1, 2, 3)), 0, ["C", "N", "H"])) == 1
    assert isinstance(results[0], JobResult)
