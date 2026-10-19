"""The third Fukui gate's panel and judge (`app/fukui_gate_3.py`), on invented records: the arithmetic of the verdict is tested before any real record exists."""

from __future__ import annotations

import dataclasses
import math

import pytest
from rdkit import Chem

from openchem.app import fukui_gate_2 as second
from openchem.app import fukui_gate_3 as gate

HARTREE_TO_EV = 27.211386245988
N_ATOMS = 4
CLASSES = ((0, 1), (2,), (3,))  # atoms 0 and 1 are one symmetry class


# --- the records of a gate that passes ---------------------------------------------------------------------------------------


def _runs(**overrides) -> list[dict]:
    """Every run of R for every panel species: f- the same in all of them, from one commit, ORCA 6.1.1."""
    records = []
    for species in gate.PANEL:
        for variant in species.variants():
            records.append({
                "species": species.name, "variant": variant, "f_minus": [0.30, 0.20, 0.10, 0.40], "completed": True, "orca_version": "6.1.1", "dirty": False, "commit": "abc123", **overrides,
            })
    return records


def _states(*above_ev: float, base: float = -100.0):
    return [{"energy_hartree": base + gap / HARTREE_TO_EV, "charges": [0.1 * (k + 1), 0.2, 0.3, 0.4]} for k, gap in enumerate(above_ev)]


def _exhaustive(application=(0.0, 0.2), reference=(0.0, 0.2)) -> list[dict]:
    return [{"species": species.name, "completed": True, "states_application": _states(*application), "states_exhaustive": _states(*reference)} for species in gate.PANEL]


def _perfect(name: str) -> second.MeasuredRun:
    """A run of a second-gate species whose every published number is reproduced exactly: each atom carries the value its label has in the source."""
    species = second.ALL_SPECIES[name]
    values = {"f+": [0.0] * len(species.atoms), "f-": [0.0] * len(species.atoms)}
    for entry in second.deproft_entries([name]):
        indices = [index for index, label in enumerate(species.labels) if label == entry.label]
        for index, value in zip(indices, sorted(entry.values) if len(entry.values) > 1 else entry.values * len(indices)):
            values[entry.attack][index] = value
    return second.MeasuredRun(
        name, species.level, species.atoms, tuple(values["f+"]), tuple(values["f-"]), (), (), species.charge, 1, "6.1.1", dihedral_degrees=178.0 if name == "acrolein" else None
    )


def _published() -> list[second.MeasuredRun]:
    return [_perfect(name) for name in gate.N_SPECIES]


def _judge(**overrides):
    arguments = {
        "runs": _runs(), "exhaustive": _exhaustive(), "published_runs": _published(), "floor": 0.0,
        "classes": {species.name: CLASSES for species in gate.PANEL},
    }
    arguments.update(overrides)
    return gate.judge(**arguments)


# --- the panel ---------------------------------------------------------------------------------------------------------------


def test_the_panel_is_twelve_species_with_their_run_counts():
    assert len(gate.PANEL) == 12 and len({species.name for species in gate.PANEL}) == 12
    assert [species.group for species in gate.PANEL] == ["close"] * 4 + ["clean"] * 4 + ["held out"] * 4
    # Reference, four rotations, four displacements; three independent optimizations for the species marked.
    counts = {species.name: len(species.variants()) for species in gate.PANEL}
    assert set(counts.values()) == {9, 12}
    assert [name for name, count in counts.items() if count == 12] == ["benzaldehyde", "anilinium", "thiophene", "HCN", "toluene", "acetophenone"]
    assert gate.PANEL[0].variants()[:3] == ("reference", "rotation0", "rotation1") and gate.PANEL[0].variants()[-3:] == ("embedding101", "embedding102", "embedding103")
    assert sum(len(species.variants()) for species in gate.PANEL) == 6 * 12 + 6 * 9


def test_every_species_is_the_molecule_its_smiles_and_charge_say_and_runs_at_the_level_the_arms_are_written_for():
    for species in (*gate.PANEL, *gate.FLOOR_SPECIES, *gate.REPORTED_SPECIES):
        mol = Chem.MolFromSmiles(species.smiles)
        assert mol is not None and sum(atom.GetFormalCharge() for atom in mol.GetAtoms()) == species.charge, species.name
        assert species.method_basis == "B3LYP 6-31G*"


def test_the_panel_species_of_the_second_gate_are_the_second_gates_by_smiles_and_charge():
    for species in gate.PANEL:
        if species.name in second.SPECIES:
            assert (second.SPECIES[species.name].smiles, second.SPECIES[species.name].charge) == (species.smiles, species.charge)


def test_the_held_out_species_were_never_compared_with_anything_and_the_floors_are_in_neither_the_panel_nor_a_gate():
    held_out = {species.name for species in gate.PANEL if species.group == "held out"}
    assert held_out == {"pyridine", "toluene", "naphthalene", "acetophenone"}
    # Pyridine was a floor molecule of the second gate (a difference between two runs of it, never a comparison with a published number); the other three were in no run of any kind.
    assert (held_out - {"pyridine"}).isdisjoint(second.ALL_SPECIES)
    assert second.FLOOR_SPECIES.keys() == {"pyridine", "formate"}
    assert {species.name for species in gate.FLOOR_SPECIES}.isdisjoint({species.name for species in gate.PANEL} | set(second.ALL_SPECIES))


def test_the_n_species_are_the_eight_the_second_gate_reproduced_and_have_27_published_numbers():
    assert set(gate.N_SPECIES) <= set(second.SPECIES) and len(gate.N_SPECIES) == 8
    entries = [entry for entry in second.decided_entries() if entry.molecule in gate.N_SPECIES]
    assert second.count_numbers(entries) == 27


def test_the_limits_are_the_ones_the_preregistration_states():
    assert gate.REPRODUCIBILITY_LIMIT == 0.01 and gate.PUBLISHED_TOLERANCE == 0.02 and gate.FLOOR_LIMIT == 0.005 and gate.ORCA_VERSION == "6.1.1"
    assert gate.ROTATIONS == 4 and gate.DISPLACEMENTS == 4 and gate.DISPLACEMENT_SIGMA == 0.001 and gate.EMBEDDING_SEEDS == (101, 102, 103)
    assert gate.EXHAUSTIVE_OFFSETS == (1, 2, 3, 4, 5, 6, 7)
    # The limit sits between what one state reached two ways differs by (0.0004) and what two states do (0.085), and above the pilot's 0.0021.
    assert 0.0021 < gate.REPRODUCIBILITY_LIMIT < 0.085


# --- class_sorted_difference and match_states -------------------------------------------------------------------------------------


def test_equivalent_atoms_may_swap_values_and_inequivalent_ones_may_not():
    first = [0.30, 0.20, 0.10, 0.40]
    assert gate.class_sorted_difference(first, [0.20, 0.30, 0.10, 0.40], CLASSES) == 0.0
    assert gate.class_sorted_difference(first, [0.30, 0.20, 0.40, 0.10], CLASSES) == pytest.approx(0.30)
    assert gate.class_sorted_difference(first, [0.30, 0.21, 0.10, 0.40], CLASSES) == pytest.approx(0.01)
    assert gate.class_sorted_difference(first, first[:3], CLASSES) == math.inf


def test_states_match_on_absolute_energy_and_charges_and_a_lowest_state_that_was_missed_matches_nothing():
    wanted = _states(0.0, 0.2)
    assert gate.match_states(wanted, _states(0.0, 0.2)) == []
    assert gate.match_states(wanted, _states(0.004, 0.196)) == []
    assert len(gate.match_states(wanted, _states(0.0))) == 1
    assert len(gate.match_states(wanted, _states(0.0, 0.215))) == 1
    # A search that missed the lowest state and found the next as its lowest: its zero is higher, and the energies are absolute.
    assert len(gate.match_states(wanted, _states(0.2, base=-100.0 + 0.2 / HARTREE_TO_EV * 0))) >= 1
    shifted = [{"energy_hartree": wanted[0]["energy_hartree"], "charges": [0.1, 0.2, 0.3, 0.46]}]
    assert gate.match_states(wanted[:1], shifted) == wanted[:1]  # one charge 0.06 apart: a different state


# --- the verdict ---------------------------------------------------------------------------------------------------------------


def test_a_gate_whose_runs_agree_whose_search_is_complete_and_whose_published_numbers_hold_passes():
    verdict = _judge()
    assert verdict.outcome == "PASS" and verdict and verdict.arms == {"R": True, "C": True, "N": True} and verdict.reasons == ()
    assert len(verdict.reproducibility) == 6 * 11 + 6 * 8 and all(row.within for row in verdict.reproducibility)
    assert len(verdict.regression) == 27 and all(row.within for row in verdict.regression)
    assert {row["molecule"] for row in verdict.site_rows} == {"phenol", "aniline", "fluorobenzene", "styrene", "acrolein"}


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"floor": None}, "no noise floor"),
        ({"floor": 0.0051}, "above 0.005"),
        ({"runs": _runs(orca_version="6.0.0")}, "not 6.1.1"),
        ({"runs": _runs(dirty=True)}, "differed from its commit"),
    ],
)
def test_a_gate_whose_instrument_is_not_fit_is_not_evaluable_and_says_why(overrides, fragment):
    verdict = _judge(**overrides)
    assert verdict.outcome == "NOT EVALUABLE" and any(fragment in reason for reason in verdict.reasons)
    assert not verdict


@pytest.mark.parametrize("dihedral, evaluable", [(180.0, True), (-150.0, True), (150.0, True), (149.9, False), (0.0, False), (None, False)])
def test_acroleins_input_validity_is_the_second_gates_dihedral_rule(dihedral, evaluable):
    """The published acrolein is s-trans; an optimization that found the s-cis minimum is not that molecule, and nothing is claimed either way."""
    published = [dataclasses.replace(run, dihedral_degrees=dihedral) if run.molecule == "acrolein" else run for run in _published()]
    verdict = _judge(published_runs=published)
    assert (verdict.outcome != "NOT EVALUABLE") is evaluable
    if not evaluable:
        assert any("acrolein's optimized dihedral" in reason for reason in verdict.reasons)


def test_runs_from_two_commits_are_not_evaluable():
    runs = _runs()
    runs[5] = {**runs[5], "commit": "def456"}
    assert any("more than one version" in reason for reason in _judge(runs=runs).reasons)


def test_a_missing_reference_a_run_never_attempted_and_a_missing_exhaustive_record_are_each_not_evaluable():
    runs = [record for record in _runs() if not (record["species"] == "phenol" and record["variant"] == "reference")]
    assert any("phenol has no reference run" in reason for reason in _judge(runs=runs).reasons)
    runs = [record for record in _runs() if not (record["species"] == "toluene" and record["variant"] == "embedding102")]
    verdict = _judge(runs=runs)
    assert verdict.outcome == "NOT EVALUABLE" and any("toluene: runs never attempted: embedding102" in reason for reason in verdict.reasons)
    verdict = _judge(exhaustive=_exhaustive()[1:])
    assert any("benzaldehyde has no exhaustive search record" in reason for reason in verdict.reasons)


def _with_change(species: str, variant: str, f_minus) -> list[dict]:
    return [{**record, "f_minus": f_minus} if (record["species"], record["variant"]) == (species, variant) else record for record in _runs()]


def test_a_perturbed_run_beyond_the_limit_fails_the_gate_and_one_within_it_does_not():
    assert _judge(runs=_with_change("benzaldehyde", "displacement2", [0.30, 0.20, 0.10, 0.40 + 0.0099])).outcome == "PASS"
    failed = _judge(runs=_with_change("benzaldehyde", "displacement2", [0.30, 0.20, 0.10, 0.40 + 0.0101]))
    assert failed.outcome == "FAIL" and failed.arms["R"] is False
    assert failed.reasons == ("R benzaldehyde displacement2: f- differs from the reference by 0.0101 (limit 0.01)",)
    assert sum(1 for row in failed.reproducibility if not row.within) == 1


def test_a_run_that_swaps_two_equivalent_atoms_is_the_same_run():
    assert _judge(runs=_with_change("HCN", "embedding101", [0.20, 0.30, 0.10, 0.40])).outcome == "PASS"
    assert _judge(runs=_with_change("HCN", "embedding101", [0.30, 0.20, 0.40, 0.10])).outcome == "FAIL"


def test_a_run_that_could_not_be_computed_fails_the_gate_and_so_does_a_reference_that_could_not():
    runs = [{**record, "completed": False} if (record["species"], record["variant"]) == ("pyrrole", "rotation1") else record for record in _runs()]
    failed = _judge(runs=runs)
    assert failed.outcome == "FAIL" and failed.reasons == ("R pyrrole rotation1: not computed in 3 attempts",)
    runs = [{**record, "completed": False} if (record["species"], record["variant"]) == ("pyrrole", "reference") else record for record in _runs()]
    assert _judge(runs=runs).reasons == ("R pyrrole: the reference run could not be computed",)


def test_a_state_the_exhaustive_search_found_within_the_window_that_the_application_missed_makes_the_gate_partial():
    verdict = _judge(exhaustive=_exhaustive(application=(0.0,), reference=(0.0, 0.2)))
    assert verdict.outcome == "PARTIAL" and verdict.arms == {"R": True, "C": False, "N": True}
    assert len(verdict.completeness) == 12 and not verdict.completeness[0].within and len(verdict.completeness[0].missed) == 1
    assert verdict.reasons[0] == "C benzaldehyde: the exhaustive search found 1 state(s) within 0.5 eV that the application's did not"


def test_a_state_beyond_the_window_that_the_application_missed_is_no_reason():
    assert _judge(exhaustive=_exhaustive(application=(0.0,), reference=(0.0, 0.51))).outcome == "PASS"
    assert _judge(exhaustive=_exhaustive(application=(0.0,), reference=(0.0, 0.49))).outcome == "PARTIAL"


def test_an_application_search_that_missed_the_lowest_state_is_partial_and_says_how_far():
    exhaustive = _exhaustive(application=(0.15,), reference=(0.0, 0.15))
    for record in exhaustive:  # the application's lowest is the exhaustive search's second state: same absolute energy, so the pair is matched and only the missed lowest is the problem
        record["states_application"] = [record["states_exhaustive"][1]]
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "PARTIAL" and "a lowest state 0.150 eV lower" in verdict.reasons[0]
    assert verdict.completeness[0].lowest_missed_ev == pytest.approx(0.15)


def test_an_exhaustive_search_that_could_not_be_computed_is_a_completeness_failure_and_not_a_reproducibility_one():
    exhaustive = _exhaustive()
    exhaustive[3] = {"species": "HCN", "completed": False}
    verdict = _judge(exhaustive=exhaustive)
    assert verdict.outcome == "PARTIAL" and verdict.reasons == ("C HCN: the exhaustive search could not be computed",)


def _moved(runs: list[second.MeasuredRun], molecule: str, label: str, attack: str, by: float, *, to: float | None = None) -> list[second.MeasuredRun]:
    """`runs` with every atom of one label of one molecule moved by `by` (or set to `to`)."""
    out = []
    for run in runs:
        if run.molecule != molecule:
            out.append(run)
            continue
        values = list(run.values(attack))
        for index, atom_label in enumerate(second.ALL_SPECIES[molecule].labels):
            if atom_label == label:
                values[index] = to if to is not None else values[index] + by
        out.append(dataclasses.replace(run, **{"f_plus" if attack == "f+" else "f_minus": tuple(values)}))
    return out


def test_a_published_number_the_calculation_no_longer_reproduces_makes_the_gate_partial():
    verdict = _judge(published_runs=_moved(_published(), "phenol", "para", "f-", 0.0201))
    assert verdict.outcome == "PARTIAL" and verdict.arms == {"R": True, "C": True, "N": False}
    assert verdict.reasons == ("N phenol para f-: 0.1641 against the published 0.1440 (+0.0201)",)
    # Within the tolerance it is no reason.
    assert _judge(published_runs=_moved(_published(), "phenol", "para", "f-", 0.0199)).outcome == "PASS"


def test_a_species_with_no_published_run_leaves_numbers_uncompared_and_the_gate_partial():
    verdict = _judge(published_runs=[run for run in _published() if run.molecule != "styrene"])
    assert verdict.outcome == "PARTIAL" and any("N: 22 of the 27 numbers could be compared" in reason for reason in verdict.reasons)


def test_a_lost_site_statement_makes_the_gate_partial():
    verdict = _judge(published_runs=_moved(_published(), "aniline", "meta", "f-", 0.0, to=0.5))  # the largest ring value is now on a meta carbon
    assert verdict.outcome == "PARTIAL" and any("N aniline f-: the largest value is on meta, not para" in reason for reason in verdict.reasons)


def test_reproducibility_failing_is_a_fail_even_when_the_other_arms_fail_too():
    verdict = _judge(runs=_with_change("furan", "rotation0", [0.30, 0.20, 0.10, 0.90]), exhaustive=_exhaustive(application=(0.0,), reference=(0.0, 0.2)))
    assert verdict.outcome == "FAIL" and verdict.arms == {"R": False, "C": False, "N": True}
