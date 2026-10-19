"""The fourth Fukui gate's reading of a state's character and its judge (`app/fukui_gate_4.py`): the arithmetic of the verdict is tested on invented records, and the reading of a state's spin on
real ORCA output, before any real record of the gate exists."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from openchem.app import fukui_gate_4 as gate

HARTREE_TO_EV = gate.HARTREE_TO_EV
FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "pyridine_cation_states_spin.txt"
PYRIDINE_ATOMS = 11


def _fixture_jobs() -> dict[int, str]:
    """The four jobs of the real fixture, keyed by the job number in its '##### job N' heading."""
    text = FIXTURE.read_text(encoding="utf-8")
    parts = re.split(r"^##### job (\d+):.*$", text, flags=re.MULTILINE)
    return {int(number): block for number, block in zip(parts[1::2], parts[2::2])}


# --- the reading of real output --------------------------------------------------------------------------------------------------


def test_the_fixture_holds_the_four_jobs_it_is_named_for():
    assert sorted(_fixture_jobs()) == [2, 4, 5, 6]


@pytest.mark.parametrize(
    ("job", "expected_kind", "nitrogen_spin_between"),
    [
        (2, "sigma", (0.70, 0.80)),  # the default start landed in the nitrogen lone-pair hole: most of the spin on N
        (4, "pi", (-0.10, -0.03)),  # 1a2: a node through N, so none on it
        (5, "pi", (0.30, 0.45)),  # 2b1: the pi orbital that reaches N
        (6, "sigma", (0.05, 0.12)),  # 5b2: the sigma bonds
    ],
)
def test_real_pyridine_states_are_read_as_the_literature_names_them(job, expected_kind, nitrogen_spin_between):
    """Trofimov 2017's four lowest cation states of pyridine are 7a1 (sigma), 1a2 (pi), 2b1 (pi) and 5b2 (sigma); ORCA's own spin populations reproduce the kind of each."""
    spins = gate.parse_lowdin_spin(_fixture_jobs()[job], PYRIDINE_ATOMS)
    assert spins is not None and len(spins) == PYRIDINE_ATOMS
    fraction = gate.out_of_plane_fraction(spins)
    assert gate.classify(fraction) == expected_kind
    nitrogen = sum(spins[3].values())  # the ring's fourth atom is the nitrogen in the order the application writes
    assert nitrogen_spin_between[0] <= nitrogen <= nitrogen_spin_between[1], nitrogen
    assert sum(sum(atom.values()) for atom in spins) == pytest.approx(1.0, abs=0.02)  # one unpaired electron


def test_a_pi_hole_is_one_and_a_sigma_hole_is_zero_in_the_real_output():
    jobs = _fixture_jobs()
    pi = gate.out_of_plane_fraction(gate.parse_lowdin_spin(jobs[4], PYRIDINE_ATOMS))
    sigma = gate.out_of_plane_fraction(gate.parse_lowdin_spin(jobs[2], PYRIDINE_ATOMS))
    assert pi == pytest.approx(1.0, abs=0.02)
    assert sigma == pytest.approx(0.0, abs=0.02)


SELENOPHENE_FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "selenophene_cation_spin_block.txt"


def test_a_two_letter_element_is_read_though_orca_prints_no_space_before_its_shell():
    """The first run of the fourth gate stopped at selenophene: ORCA prints "3 Ses" for selenium where a one-letter element has "0 C s", and the pattern needed the space. This is that output, whole."""
    text = SELENOPHENE_FIXTURE.read_text(encoding="utf-8")
    assert re.search(r"^\s*3 Ses\s", text, flags=re.MULTILINE)
    spins = gate.parse_lowdin_spin(text, 9)
    assert spins is not None and len(spins) == 9
    assert all({"s", "pz", "px", "py"} <= set(atom) for atom in spins[:5])  # the four carbons and the selenium have p and d functions
    assert all(set(atom) == {"s"} for atom in spins[5:])  # the hydrogens only an s function
    assert sum(sum(atom.values()) for atom in spins) == pytest.approx(1.0, abs=0.02)  # one unpaired electron, whichever state it is
    assert gate.out_of_plane_fraction(spins) == pytest.approx(gate.out_of_plane_fraction(spins))  # computable (not NaN, no division by zero)


def test_a_block_of_the_wrong_molecule_is_refused_not_read_short():
    with pytest.raises(ValueError, match="atoms"):
        gate.parse_lowdin_spin(_fixture_jobs()[4], PYRIDINE_ATOMS + 1)


def test_a_job_with_no_spin_block_reads_as_none():
    assert gate.parse_lowdin_spin("ORCA printed nothing of the kind here\n", 3) is None
    assert gate.parse_lowdin_spin("LOEWDIN REDUCED ORBITAL CHARGES AND SPIN POPULATIONS\nCHARGE\n", 3) is None


def test_spin_populations_that_add_to_zero_are_refused():
    with pytest.raises(ValueError, match="zero"):
        gate.out_of_plane_fraction([{"s": 0.0, "pz": 0.0}])


# --- the limits of the reading -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fraction", "kind"),
    [(1.0, "pi"), (0.75, "pi"), (0.7499, None), (0.5, None), (0.2501, None), (0.25, "sigma"), (0.0, "sigma"), (-0.05, "sigma"), (1.05, "pi")],
)
def test_classify_at_the_limits(fraction, kind):
    assert gate.classify(fraction) == kind


@pytest.mark.parametrize(("spin", "kind"), [(-0.07, "a2"), (0.0, "a2"), (0.10, "a2"), (0.1001, None), (0.15, None), (0.1999, None), (0.20, "b1"), (0.58, "b1")])
def test_hetero_class_at_the_limits(spin, kind):
    assert gate.hetero_class(spin) == kind


def test_the_two_limits_leave_a_gap_between_them_and_do_not_overlap():
    assert gate.SIGMA_LIMIT < gate.PI_LIMIT
    assert gate.A2_HETERO_LIMIT < gate.B1_HETERO_LIMIT


# --- states ----------------------------------------------------------------------------------------------------------------


def _job(above_ev: float, fraction: float, spin=(0.0, 0.0, 0.0), base: float = -100.0) -> dict:
    return {"energy_hartree": base + above_ev / HARTREE_TO_EV, "out_of_plane": fraction, "atom_spin": list(spin)}


def test_jobs_within_the_state_margin_are_one_state_read_from_the_lowest():
    states = gate.states_of([_job(0.004, 1.0), _job(0.0, 1.0), _job(0.123, 0.0), _job(0.127, 0.0)])
    assert [state.jobs for state in states] == [2, 2]
    assert states[0].above_ev == 0.0
    assert states[1].above_ev == pytest.approx(0.123)


def test_a_chain_of_jobs_each_within_the_margin_of_the_last_is_one_state():
    states = gate.states_of([_job(0.0, 1.0), _job(0.009, 1.0), _job(0.018, 1.0)])
    assert len(states) == 1 and states[0].jobs == 3


def test_jobs_exactly_a_state_margin_apart_are_one_state():
    assert len(gate.states_of([_job(0.0, 1.0), _job(gate.STATE_MARGIN_EV, 1.0)])) == 1


def test_a_gap_just_over_the_margin_splits_two_states():
    assert len(gate.states_of([_job(0.0, 1.0), _job(0.0101, 1.0)])) == 2


def test_jobs_of_one_energy_that_disagree_about_their_kind_make_an_inconsistent_state():
    state = gate.states_of([_job(0.0, 1.0), _job(0.001, 0.0)])[0]
    assert not state.consistent


def test_no_jobs_make_no_states():
    assert gate.states_of([]) == []


def test_a_state_reports_its_kind():
    assert gate.states_of([_job(0.0, 0.98)])[0].kind == "pi"
    assert gate.states_of([_job(0.0, 0.5)])[0].kind is None


# --- the references -------------------------------------------------------------------------------------------------------


PAIR = re.compile(r"(\d+\.\d+)(?: \([^)]*\))?(?:, | and )(\d+\.\d+)(?: \([^)]*\))?: (\d+\.\d+)")


@pytest.mark.parametrize("species", gate.GATE_SPECIES, ids=lambda s: s.name)
def test_every_gap_a_reference_prints_is_the_difference_of_the_two_energies_beside_it(species):
    """A table can check its own transcription: each 'A, B: G' in a source line must have G = B - A (to the rounding of the numbers printed), and the reference's range must be the smallest and the
    largest of them."""
    gaps = []
    for line in species.reference.values:
        found = PAIR.findall(line)
        assert found, f"no 'A, B: G' triple in: {line}"
        for first, second, gap in found:
            assert abs((float(second) - float(first)) - float(gap)) <= 0.011, (species.name, first, second, gap)
            gaps.append(float(gap))
    assert min(gaps) == pytest.approx(species.reference.gap_ev[0], abs=1e-9)
    assert max(gaps) == pytest.approx(species.reference.gap_ev[1], abs=1e-9)


def test_the_species_are_the_seven_decided_and_the_four_calibration_and_no_name_repeats():
    names = [s.name for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)]
    assert len(names) == len(set(names)) == 11
    assert {s.name for s in gate.GATE_SPECIES} == {"pyrimidine", "pyrazine", "pyridazine", "imidazole", "pyrazole", "oxazole", "selenophene"}
    assert all(s.role == "decided" for s in gate.GATE_SPECIES) and all(s.role == "calibration" for s in gate.CALIBRATION)


def test_the_decided_species_were_never_in_an_earlier_gate():
    """The third gate's panel and the calibration are the molecules whose states were seen before this gate; a decided species must not be one of them."""
    from openchem.app import fukui_gate_3

    seen = {s.name.lower() for s in (*fukui_gate_3.PANEL, *fukui_gate_3.FLOOR_SPECIES, *fukui_gate_3.REPORTED_SPECIES)} | {s.name for s in gate.CALIBRATION}
    assert not ({s.name for s in gate.GATE_SPECIES} & seen)


def test_the_smiles_are_the_molecules_named():
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    formulas = {"pyrimidine": "C4H4N2", "pyrazine": "C4H4N2", "pyridazine": "C4H4N2", "imidazole": "C3H4N2", "pyrazole": "C3H4N2", "oxazole": "C3H3NO", "selenophene": "C4H4Se"}
    for species in gate.GATE_SPECIES:
        mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
        assert rdMolDescriptors.CalcMolFormula(mol) == formulas[species.name]
    # The three diazines differ in where the nitrogens are: the number of bonds between them.
    path = {s.name: Chem.GetDistanceMatrix(Chem.MolFromSmiles(s.smiles)) for s in gate.GATE_SPECIES}
    def between(name):
        mol = Chem.MolFromSmiles(next(s.smiles for s in gate.GATE_SPECIES if s.name == name))
        nitrogens = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N"]
        return path[name][nitrogens[0]][nitrogens[1]]
    assert (between("pyridazine"), between("pyrimidine"), between("pyrazine")) == (1, 2, 3)
    assert between("pyrazole") == 1 and between("imidazole") == 2
    oxazole = Chem.MolFromSmiles(next(s.smiles for s in gate.GATE_SPECIES if s.name == "oxazole"))
    oxygen = next(a for a in oxazole.GetAtoms() if a.GetSymbol() == "O")
    assert any(n.GetSymbol() == "C" and any(m.GetSymbol() == "N" for m in n.GetNeighbors()) for n in oxygen.GetNeighbors())  # C2 lies between the O and the N


# --- the judge -----------------------------------------------------------------------------------------------------------------


def _passing_jobs(name: str) -> tuple[list[dict], int | None]:
    """The jobs of an exhaustive search that agrees with the literature for this species, and the hetero index."""
    sigma_first = {"pyrimidine": (0.68), "pyrazine": (0.60), "pyridazine": (1.40)}
    if name in sigma_first:
        return [_job(0.0, 0.0), _job(0.0, 0.01), _job(sigma_first[name], 1.0), _job(sigma_first[name] + 1.0, 0.0)], None
    if name in ("imidazole", "pyrazole", "oxazole"):
        gap = {"imidazole": 1.3, "pyrazole": 1.5, "oxazole": 1.4}[name]
        return [_job(0.0, 1.0), _job(gap, 0.0), _job(gap + 0.2, 1.0)], None
    # selenophene: two pi states, 0.05 apart, the lower with no spin on Se (a2) and the upper with much (b1); atom 4 is Se here
    return [_job(0.0, 1.0, (0.1, 0.1, 0.4, -0.05, 0.4)), _job(0.05, 1.0, (0.3, 0.3, -0.1, 0.6, -0.1))], 3


def _exhaustive(**overrides) -> list[dict]:
    records = []
    for species in gate.GATE_SPECIES:
        jobs, index = _passing_jobs(species.name)
        records.append({"species": species.name, "completed": True, "jobs": jobs, "planarity": 0.001, "hetero_index": index, **overrides})
    return records


def _application(**overrides) -> list[dict]:
    records = []
    for species in gate.GATE_SPECIES:
        jobs, _index = _passing_jobs(species.name)
        lowest = min(job["energy_hartree"] for job in jobs)
        records.append({"species": species.name, "completed": True, "lowest_hartree": lowest, "note": "Another state of the cation lies close." if species.hetero else "", **overrides})
    return records


def _runs(**overrides) -> list[dict]:
    return [{"orca_version": "6.1.1", "dirty": False, "commit": "abc123", **overrides}]


def _judge(**overrides):
    arguments = {"exhaustive": _exhaustive(), "application": _application(), "runs": _runs()}
    arguments.update(overrides)
    return gate.judge(**arguments)


def test_a_search_that_agrees_with_every_source_passes():
    verdict = _judge()
    assert verdict.outcome == "PASS", verdict.reasons
    assert bool(verdict)
    assert {row.claim for row in verdict.rows} >= {"C1", "C2", "C3", "C5", "S1", "S2", "S3"}
    assert all(row.holds for row in verdict.rows)
    assert verdict.arms == {"kind": True, "distance": True}


def test_every_species_is_judged_on_its_own_claims():
    claims = {}
    for row in _judge().rows:
        claims.setdefault(row.species, set()).add(row.claim)
    assert claims["pyrimidine"] == {"C1", "C2", "C3", "C5"}
    assert claims["imidazole"] == {"C1", "C3", "C5"}
    assert claims["selenophene"] == {"S1", "S2", "S3", "C5"}


def test_the_wrong_kind_of_lowest_state_is_a_fail():
    exhaustive = _exhaustive()
    pyrimidine = next(r for r in exhaustive if r["species"] == "pyrimidine")
    pyrimidine["jobs"] = [_job(0.0, 1.0), _job(0.68, 0.0)]  # a pi hole lowest where the literature says sigma
    verdict = _judge(exhaustive=exhaustive, application=_application())
    assert verdict.outcome == "FAIL"
    assert any("C1 pyrimidine" in reason for reason in verdict.reasons)


def test_the_wrong_kind_of_second_state_is_a_fail():
    exhaustive = _exhaustive()
    pyrazine = next(r for r in exhaustive if r["species"] == "pyrazine")
    pyrazine["jobs"] = [_job(0.0, 0.0), _job(0.55, 0.0), _job(1.5, 1.0)]  # a second sigma hole before the pi hole
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "FAIL"
    assert any("C2 pyrazine" in reason for reason in verdict.reasons)


@pytest.mark.parametrize(
    ("species", "gap", "holds"),
    [("pyrimidine", 0.48 - 0.25, True), ("pyrimidine", 0.48 - 0.26, False), ("pyrimidine", 0.80 + 0.25, True), ("pyrimidine", 0.80 + 0.26, False),
     ("pyridazine", 1.30 - 0.25, True), ("pyridazine", 1.52 + 0.26, False), ("imidazole", 1.23 - 0.24, True), ("imidazole", 1.67 + 0.26, False), ("pyrazole", 1.55 + 0.24, True), ("pyrazole", 1.55 - 0.26, False)],
)
def test_the_gap_is_judged_against_the_printed_range_widened_by_the_tolerance(species, gap, holds):
    exhaustive = _exhaustive()
    record = next(r for r in exhaustive if r["species"] == species)
    jobs = record["jobs"]
    # replace the other-kind state's energy by the gap under test
    other_kind_fraction = 1.0 if species in ("pyrimidine", "pyrazine", "pyridazine") else 0.0
    target = next(job for job in jobs[1:] if job["out_of_plane"] == other_kind_fraction)
    target["energy_hartree"] = jobs[0]["energy_hartree"] + gap / HARTREE_TO_EV
    verdict = _judge(exhaustive=exhaustive)
    row = next(r for r in verdict.rows if r.species == species and r.claim == "C3")
    assert row.holds is holds
    assert verdict.outcome == ("PASS" if holds else "PARTIAL")


def test_a_gap_that_misses_while_every_kind_is_right_is_partial_and_not_fail():
    exhaustive = _exhaustive()
    pyridazine = next(r for r in exhaustive if r["species"] == "pyridazine")
    pyridazine["jobs"] = [_job(0.0, 0.0), _job(3.0, 1.0)]
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "PARTIAL" and verdict.arms == {"kind": True, "distance": False}


def test_an_other_kind_state_whose_jobs_disagree_is_not_used_for_the_gap():
    """Two jobs at one energy that disagree about their kind are no state of either kind: the gap is then measured to the next state that is read, and fails if there is none in range."""
    exhaustive = _exhaustive()
    imidazole = next(r for r in exhaustive if r["species"] == "imidazole")
    # a pi lowest state; at the sigma state's energy one job reads pi and one sigma; the next sigma state is far above
    imidazole["jobs"] = [_job(0.0, 1.0), _job(1.3, 0.0), _job(1.3, 1.0), _job(4.0, 0.0)]
    row = next(r for r in _judge(exhaustive=exhaustive).rows if r.species == "imidazole" and r.claim == "C3")
    assert not row.holds and "4.000" in row.found


def test_no_state_of_the_other_kind_found_fails_the_gap_claim():
    exhaustive = _exhaustive()
    imidazole = next(r for r in exhaustive if r["species"] == "imidazole")
    imidazole["jobs"] = [_job(0.0, 1.0), _job(0.3, 1.0)]  # only pi holes
    verdict = _judge(exhaustive=exhaustive)
    row = next(r for r in verdict.rows if r.species == "imidazole" and r.claim == "C3")
    assert not row.holds and "no sigma state" in row.found
    assert verdict.outcome == "PARTIAL"


def test_an_application_search_that_missed_the_lowest_state_is_partial():
    application = _application()
    pyrazine = next(r for r in application if r["species"] == "pyrazine")
    pyrazine["lowest_hartree"] += 0.05 / HARTREE_TO_EV
    verdict = _judge(application=application)
    assert verdict.outcome == "PARTIAL"
    assert [r.claim for r in verdict.rows if not r.holds] == ["C5"]


def test_c5_holds_exactly_at_the_state_margin_and_fails_just_past_it():
    for extra, holds in ((0.0, True), (gate.LOWEST_AGREEMENT_EV, True), (gate.LOWEST_AGREEMENT_EV + 0.002, False)):
        application = _application()
        next(r for r in application if r["species"] == "pyrazine")["lowest_hartree"] += extra / HARTREE_TO_EV
        row = next(r for r in _judge(application=application).rows if r.species == "pyrazine" and r.claim == "C5")
        assert row.holds is holds, extra


def test_an_application_search_that_found_a_lower_state_than_the_exhaustive_one_does_not_fail_c5():
    application = _application()
    application[0]["lowest_hartree"] -= 0.2 / HARTREE_TO_EV
    assert _judge(application=application).outcome == "PASS"


def test_selenophene_with_two_pi_states_of_the_same_hetero_class_fails_s1():
    exhaustive = _exhaustive()
    selenophene = next(r for r in exhaustive if r["species"] == "selenophene")
    selenophene["jobs"] = [_job(0.0, 1.0, (0.1, 0.1, 0.4, -0.05, 0.4)), _job(0.05, 1.0, (0.1, 0.1, 0.4, -0.04, 0.4))]  # both a2
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "FAIL"
    assert any(reason.startswith("S1 selenophene") for reason in verdict.reasons)


def test_selenophene_with_a_sigma_state_second_fails_s1():
    exhaustive = _exhaustive()
    selenophene = next(r for r in exhaustive if r["species"] == "selenophene")
    selenophene["jobs"] = [_job(0.0, 1.0, (0.1, 0.1, 0.4, -0.05, 0.4)), _job(0.05, 0.0, (0.3, 0.3, -0.1, 0.6, -0.1))]
    assert _judge(exhaustive=exhaustive).outcome == "FAIL"


def test_selenophene_far_apart_is_partial_and_without_the_note_is_partial():
    exhaustive = _exhaustive()
    selenophene = next(r for r in exhaustive if r["species"] == "selenophene")
    selenophene["jobs"][1] = _job(0.9, 1.0, (0.3, 0.3, -0.1, 0.6, -0.1))
    assert _judge(exhaustive=exhaustive).outcome == "PARTIAL"
    quiet = _application()
    next(r for r in quiet if r["species"] == "selenophene")["note"] = ""
    verdict = _judge(application=quiet)
    assert verdict.outcome == "PARTIAL" and any(r.claim == "S3" and not r.holds for r in verdict.rows)


def test_a_note_that_says_something_else_does_not_satisfy_s3():
    application = _application()
    next(r for r in application if r["species"] == "selenophene")["note"] = "The search did not run: it was switched off in Settings > Quantum chemistry."
    verdict = _judge(application=application)
    assert verdict.outcome == "PARTIAL"
    assert [r.claim for r in verdict.rows if not r.holds] == ["S3"]


@pytest.mark.parametrize("competing", [1, 2])
def test_s3_accepts_the_note_the_application_really_writes_for_one_or_several_close_states(competing):
    """The sentences S3 looks for are matched against notes built by the application's own `cation_state_sentences` from real `read_cation` readings, one competing state and two."""
    from openchem.chem.fukui import cation_state_sentences
    from openchem.chem.fukui_plan import START_DEFAULT, STATE_N, STATE_OXIDISED, JobResult, hole_start
    from openchem.chem.fukui_states import read_cation

    def job(start, above_ev, charges):
        return JobResult(STATE_OXIDISED, 1, 2, start, -100.0 + above_ev / HARTREE_TO_EV, tuple(charges), 0.76)

    states = [(0.0, (0.20, 0.50, 0.30)), (0.12, (0.60, 0.30, 0.10)), (0.30, (0.40, 0.40, 0.20))][: competing + 1]
    jobs = [job(START_DEFAULT if k == 0 else hole_start(k), gap, charges) for k, (gap, charges) in enumerate(states)]
    reading = read_cation([JobResult(STATE_N, 0, 1, START_DEFAULT, -109.0, (-0.30, 0.10, 0.20)), *jobs], planned_holes=tuple(range(1, competing + 1)))
    [note] = cation_state_sentences(reading, 0, ["O", "C", "H"])
    application = _application()
    next(r for r in application if r["species"] == "selenophene")["note"] = note
    assert any(sentence in note for sentence in gate.CLOSE_STATE_SENTENCES)
    assert _judge(application=application).outcome == "PASS"


def test_one_state_of_selenophene_found_fails_s1():
    exhaustive = _exhaustive()
    next(r for r in exhaustive if r["species"] == "selenophene")["jobs"] = [_job(0.0, 1.0, (0.1, 0.1, 0.4, -0.05, 0.4))]
    assert _judge(exhaustive=exhaustive).outcome == "FAIL"


def test_a_heteroatom_spin_between_the_limits_cannot_be_decided():
    exhaustive = _exhaustive()
    selenophene = next(r for r in exhaustive if r["species"] == "selenophene")
    selenophene["jobs"] = [_job(0.0, 1.0, (0.1, 0.1, 0.4, 0.15, 0.4)), _job(0.05, 1.0, (0.3, 0.3, -0.1, 0.6, -0.1))]
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "NOT EVALUABLE" and "selenophene" in verdict.reasons[0]


# --- what makes the record unfit ----------------------------------------------------------------------------------------------


def test_another_orca_version_is_not_evaluable():
    verdict = _judge(runs=_runs(orca_version="6.0.0"))
    assert verdict.outcome == "NOT EVALUABLE" and "ORCA" in verdict.reasons[0]


def test_a_dirty_source_tree_is_not_evaluable():
    assert _judge(runs=_runs(dirty=True)).outcome == "NOT EVALUABLE"


def test_two_commits_are_not_evaluable():
    assert _judge(runs=[*_runs(), *_runs(commit="def456")]).outcome == "NOT EVALUABLE"


def test_a_species_with_no_record_is_not_evaluable():
    verdict = _judge(exhaustive=[r for r in _exhaustive() if r["species"] != "oxazole"])
    assert verdict.outcome == "NOT EVALUABLE" and "oxazole" in verdict.reasons[0]
    verdict = _judge(application=[r for r in _application() if r["species"] != "oxazole"])
    assert verdict.outcome == "NOT EVALUABLE"


def test_a_species_that_was_not_planar_cannot_be_read():
    for planarity in (0.051, None):
        exhaustive = _exhaustive()
        exhaustive[0]["planarity"] = planarity
        verdict = _judge(exhaustive=exhaustive)
        assert verdict.outcome == "NOT EVALUABLE" and "planar" in verdict.reasons[0]


def test_planarity_exactly_at_the_limit_is_read():
    exhaustive = _exhaustive()
    exhaustive[0]["planarity"] = gate.PLANARITY_LIMIT_ANGSTROM
    assert _judge(exhaustive=exhaustive).outcome == "PASS"


def test_an_unclassified_lowest_state_cannot_be_decided():
    exhaustive = _exhaustive()
    pyrimidine = next(r for r in exhaustive if r["species"] == "pyrimidine")
    pyrimidine["jobs"][0]["out_of_plane"] = 0.5
    pyrimidine["jobs"][1]["out_of_plane"] = 0.5
    assert _judge(exhaustive=exhaustive).outcome == "NOT EVALUABLE"


def test_a_lowest_state_whose_jobs_disagree_cannot_be_decided():
    exhaustive = _exhaustive()
    pyrimidine = next(r for r in exhaustive if r["species"] == "pyrimidine")
    pyrimidine["jobs"][1]["out_of_plane"] = 1.0  # the two jobs at the lowest energy disagree
    assert _judge(exhaustive=exhaustive).outcome == "NOT EVALUABLE"


def test_a_job_that_could_not_be_computed_is_a_fail_naming_it():
    exhaustive = _exhaustive()
    exhaustive[1]["completed"] = False
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "FAIL" and "could not be computed" in verdict.reasons[0]
    application = _application()
    application[2]["completed"] = False
    assert _judge(application=application).outcome == "FAIL"


def test_the_instrument_constants_are_the_earlier_gates():
    from openchem.app import fukui_gate

    assert gate.ORCA_VERSION == fukui_gate.ORCA_VERSION == "6.1.1"
    assert gate.MAX_ATTEMPTS == fukui_gate.MAX_ATTEMPTS


def test_the_verdict_is_a_frozen_value():
    verdict = _judge()
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.outcome = "FAIL"  # type: ignore[misc]
