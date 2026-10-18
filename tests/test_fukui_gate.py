"""The Fukui gate's arithmetic (`app/fukui_gate.py`, `benchmarks/fukui_gate/PREREGISTRATION.md`), with invented runs.

The rules that decide which published numbers may be targets are tested on the REAL typed tables, because the tables are what
the rules are about: a rule tested only on invented numbers would not say that three of Olah's columns are misprints. The
judge is tested with runs built from the published numbers themselves, so a perfect reproduction is a PASS by construction
and every other outcome is one named perturbation away.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem

from openchem.app import fukui_gate as gate
from openchem.app.fukui_gate import (
    BULTINCK,
    DECIDED_LEVELS,
    DFT_B,
    HF_B,
    METHOD_BASIS,
    OLAH,
    OLAH_COMPLETE,
    OLAH_LEVELS,
    SITE_STATEMENTS,
    SPECIES,
    THANIKAIVELAN,
    MeasuredRun,
    Outcome,
)

# --- the typed tables and the rules over them --------------------------------------------------------------------------------


def test_exactly_three_published_columns_fail_the_sum_rule():
    """CO2 f- at B3LYP/6-31G**, CNO- f+ at B3LYP/6-31G** and NCO- f- at HF/6-31G**: each a misprint in the source, found by
    summing the atoms of a molecule whose every atom is tabulated. The sums are the ones the PDF's own numbers give."""
    assert gate.failing_columns() == (
        ("CNO-", "f+", DFT_B, 1.0241),
        ("CO2", "f-", DFT_B, 1.0119),
        ("NCO-", "f-", HF_B, 0.996),
    )


def test_every_other_complete_column_sums_to_one():
    failing = {(m, a, level) for m, a, level, _ in gate.failing_columns()}
    checked = 0
    for molecule in sorted(OLAH_COMPLETE):
        for attack in gate.ATTACKS:
            for level in OLAH_LEVELS:
                if (molecule, attack, level) in failing:
                    continue
                checked += 1
                assert gate.column_sum(molecule, attack, level) == pytest.approx(1.0, abs=gate.SUM_TOLERANCE)
    assert checked == len(OLAH_COMPLETE) * 2 * 4 - 3


def test_a_partial_column_cannot_be_summed():
    with pytest.raises(ValueError, match="omits atoms"):
        gate.column_sum("H2CO", "f+", HF_B)


def test_the_column_sum_reads_the_right_attack():
    """A mix-up of the two tuples would still sum plausibly, because both columns sum to 1; CO's two attacks differ."""
    assert gate.column_sum("CO", "f+", DFT_B) == pytest.approx(0.6705 + 0.3295)
    assert gate.column_sum("CO2", "f+", DFT_B) == pytest.approx(0.4043 + 2 * 0.2979)
    assert gate.column_sum("CO2", "f-", DFT_B) == pytest.approx(0.2193 + 2 * 0.3963)


def test_the_other_sources_sum_to_one_where_they_can():
    """Bultinck's two columns with two hydrogens; Thanikaivelan's Table 5 is 0.998 on f+ (it prints three decimals)."""
    assert sum(count * plus for count, plus, _ in BULTINCK.values()) == pytest.approx(1.0, abs=1e-9)
    assert sum(count * minus for count, _, minus in BULTINCK.values()) == pytest.approx(1.0, abs=1e-9)
    assert sum(count * plus for count, plus, _ in THANIKAIVELAN.values()) == pytest.approx(0.998, abs=1e-9)
    assert sum(count * minus for count, _, minus in THANIKAIVELAN.values()) == pytest.approx(1.0, abs=1e-9)


def test_formaldehyde_is_corroborated_by_two_independent_sources():
    assert gate.corroboration_failures() == ()


def test_a_corroboration_that_fails_is_reported(monkeypatch):
    broken = {**OLAH, "H2CO": {**OLAH["H2CO"], "C": (1, (0.4278, 0.3948, 0.4446, 0.50), (0.2337, 0.2280, 0.2324, 0.2277))}}
    monkeypatch.setattr(gate, "OLAH", broken)
    failed = gate.corroboration_failures()
    assert [(e, a, level) for e, a, level, _, _ in failed] == [("C", "f+", HF_B)]
    # and then formaldehyde is no longer a target at all
    assert not [e for e in gate.decided_entries() if e.molecule == "H2CO" and e.source == "olah2002"]


def test_the_published_scatter_is_the_evidence_for_the_tolerance():
    """The largest disagreement among independent published values of formaldehyde at comparable levels: 0.0080, B3LYP/6-31G**
    against BLYP/dnd for the carbon's f-. The tolerance is two and a half times it."""
    assert gate.published_scatter() == pytest.approx(0.008, abs=1e-4)
    assert gate.TOLERANCE == pytest.approx(2.5 * gate.published_scatter(), abs=1e-3)


def test_the_hf_values_of_two_programs_agree_to_four_thousandths():
    """Bultinck's and Olah's HF/6-31G** values of formaldehyde, the same quantity from two programs: the reason a tolerance of
    0.02 is not generous."""
    index = OLAH_LEVELS.index(HF_B)
    differences = []
    for attack_position, other in ((1, 1), (2, 2)):
        for element in ("C", "O"):
            differences.append(abs(OLAH["H2CO"][element][attack_position][index] - BULTINCK[element][other]))
    assert max(differences) < 0.0045


def test_the_decided_numbers_are_the_ones_the_rules_leave():
    decided = gate.decided_entries()
    assert len(decided) == 54
    assert {e.level for e in decided} == set(DECIDED_LEVELS)
    assert {e.source for e in decided} == {"olah2002", "bultinck2007"}
    assert sum(e.source == "bultinck2007" for e in decided) == 6
    keys = {(e.molecule, e.attack, e.level) for e in decided if e.source == "olah2002"}
    for dropped in gate.failing_columns():
        assert dropped[:3] not in keys
    # no diffuse-basis number decides anything, and acetone gives no number (partial, no second source)
    assert not [e for e in decided if "6-311" in e.level]
    assert not [e for e in decided if e.molecule == "acetone"]


def test_every_decided_number_is_for_a_species_the_gate_runs():
    assert {e.molecule for e in gate.decided_entries()} <= set(SPECIES)


def test_thirteen_site_statements_are_decidable_and_one_is_not():
    decidable = gate.decidable_site_statements()
    assert len(decidable) == 13
    undecidable = gate.undecidable_site_statements()
    assert len(undecidable) == 1
    statement, level, margin = undecidable[0]
    assert (statement.molecule, statement.attack, statement.element, level) == ("NCO-", "f-", "N", HF_B)
    assert margin == pytest.approx(0.0198, abs=1e-4)


def test_a_site_must_clear_twice_the_tolerance_to_be_decided():
    """The rule that removes NCO-: a tolerance wider than half the margin could turn the ordering over."""
    for statement, level in gate.decidable_site_statements():
        assert gate.published_margin(statement, level) >= gate.SITE_MARGIN_FACTOR * gate.TOLERANCE - 1e-9
    # a looser tolerance removes more; a tighter one admits NCO- at HF/6-31G**
    assert len(gate.decidable_site_statements(0.05)) < 13
    assert len(gate.decidable_site_statements(0.009)) == 14


def test_every_site_statement_is_supported_by_the_papers_own_numbers_at_the_decided_levels():
    """A statement the source's own table contradicts could not be decided against: acetone's f+ is the case left out, and
    this checks nothing else is in the same position."""
    for statement in SITE_STATEMENTS:
        for level in DECIDED_LEVELS:
            assert gate.published_margin(statement, level) is not None, (statement, level)


def test_acetones_f_plus_is_not_a_site_statement_because_the_table_contradicts_it():
    """Olah's own numbers at B3LYP/6-31G** put the oxygen's f+ (0.2491) above the carbonyl carbon's (0.2388)."""
    from openchem.app.fukui_gate import SiteStatement

    assert gate.published_margin(SiteStatement("acetone", "f+", "C", ""), DFT_B) is None
    assert not [s for s in SITE_STATEMENTS if s.molecule == "acetone" and s.attack == "f+"]


def test_the_statements_name_species_and_elements_the_tables_have():
    for statement in SITE_STATEMENTS:
        assert statement.molecule in SPECIES and statement.molecule in OLAH
        assert statement.element in OLAH[statement.molecule]
        assert statement.attack in gate.ATTACKS


# --- the species the application is asked to run -------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SPECIES))
def test_each_species_is_the_molecule_its_atoms_and_charge_say(name):
    """The atom order and the net charge the gate assumes are what RDKit gives for the SMILES, with hydrogens added."""
    species = SPECIES[name]
    mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
    assert tuple(atom.GetSymbol() for atom in mol.GetAtoms()) == species.atoms
    assert sum(atom.GetFormalCharge() for atom in mol.GetAtoms()) == species.charge


def test_the_charged_species_are_the_three_anions():
    assert {name for name, species in SPECIES.items() if not species.neutral} == {"CN-", "NCO-", "CNO-"}


def test_the_levels_are_the_models_of_the_paper_and_each_has_a_method_string():
    assert set(METHOD_BASIS) == set(OLAH_LEVELS) | {gate.DEFAULT_LEVEL}
    assert METHOD_BASIS[HF_B] == "HF 6-31G**" and METHOD_BASIS[DFT_B] == "B3LYP 6-31G**"


# --- the judge ---------------------------------------------------------------------------------------------------------------


def _labels(species):
    """The published label of each atom position (acetone's carbons are not the one element)."""
    if species.name == "acetone":
        return ["Cm", "C", "Cm", "O"] + ["H"] * 6
    return list(species.atoms)


def _ideal_values(molecule, level, attack):
    """The published numbers as a run's per-atom values; hydrogens (not tabulated) take the remainder equally, and a column
    that fails the sum rule is filled from the other decided level (it is not a target, but a run must sum to one)."""
    species = SPECIES[molecule]
    failing = {(m, a, lv) for m, a, lv, _ in gate.failing_columns()}
    use = level
    if (molecule, attack, level) in failing:
        use = HF_B if level == DFT_B else DFT_B
    index = OLAH_LEVELS.index(use)
    table = {el: (plus if attack == "f+" else minus)[index] for el, (count, plus, minus) in OLAH[molecule].items()}
    counts = {el: count for el, (count, _, _) in OLAH[molecule].items()}
    labels = _labels(species)
    hydrogens = labels.count("H")
    remainder = 1.0 - sum(table[el] * counts[el] for el in table)
    return tuple(table[label] if label != "H" else remainder / hydrogens for label in labels)


def _run(molecule, level, **changes):
    species = SPECIES[molecule]
    plus, minus = _ideal_values(molecule, level, "f+"), _ideal_values(molecule, level, "f-")
    base = MeasuredRun(
        molecule=molecule, level=level, symbols=species.atoms, f_plus=plus, f_minus=minus,
        f_zero=tuple((p + m) / 2 for p, m in zip(plus, minus)), dual=tuple(p - m for p, m in zip(plus, minus)),
        charge=species.charge, multiplicity=1, orca_version="6.1.1",
    )
    return dataclasses.replace(base, **changes)


def _runs():
    return {(name, level): _run(name, level) for name in SPECIES for level in DECIDED_LEVELS}


def _judge(runs=None, **kwargs):
    arguments = {"tolerance": gate.TOLERANCE, "floor": 0.0, "orca_versions": ["6.1.1"]}
    arguments.update(kwargs)
    return gate.judge(_runs() if runs is None else runs, **arguments)


def _shift(run, element, attack, amount, *, to):
    """Add `amount` to one attack's value on every atom of `element` and take the total from the first atom of `to`, so the
    column still sums to one; f0 and the dual follow, since a run's own identities must still hold."""
    values = list(run.values(attack))
    taken = 0.0
    for index, symbol in enumerate(run.symbols):
        if symbol == element:
            values[index] += amount
            taken += amount
    values[next(index for index, symbol in enumerate(run.symbols) if symbol == to)] -= taken
    plus = tuple(values) if attack == "f+" else run.f_plus
    minus = tuple(values) if attack == "f-" else run.f_minus
    return dataclasses.replace(
        run, f_plus=plus, f_minus=minus, f_zero=tuple((p + m) / 2 for p, m in zip(plus, minus)),
        dual=tuple(p - m for p, m in zip(plus, minus)),
    )


def test_a_perfect_reproduction_passes():
    verdict = _judge()
    assert verdict.outcome is Outcome.PASS and verdict.reasons == ()
    assert len(verdict.rows) == 54
    assert len(verdict.site_rows) == 13 and all(row.reproduced for row in verdict.site_rows)
    assert all(row.within for row in verdict.rows)


def test_the_rows_name_the_published_value_and_the_measured_one():
    verdict = _judge()
    row = next(r for r in verdict.rows if (r.molecule, r.element, r.attack, r.level, r.source) == ("CO", "C", "f+", DFT_B, "olah2002"))
    assert row.published == 0.6705 and row.measured == pytest.approx(0.6705) and row.difference == pytest.approx(0.0, abs=1e-12)
    assert row.neutral and row.decided


def test_a_neutral_value_outside_tolerance_fails():
    runs = _runs()
    runs[("CO", DFT_B)] = _shift(runs[("CO", DFT_B)], "C", "f+", 0.03, to="O")
    verdict = _judge(runs)
    assert verdict.outcome is Outcome.FAIL
    assert any(reason.startswith("CO C f+ at B3LYP/6-31G**") and "+0.0300" in reason for reason in verdict.reasons)


def test_the_tolerance_edge_is_inclusive():
    just_in = _runs()
    just_in[("CO", DFT_B)] = _shift(just_in[("CO", DFT_B)], "C", "f+", 0.0199, to="O")
    assert _judge(just_in).outcome is Outcome.PASS
    just_out = _runs()
    just_out[("CO", DFT_B)] = _shift(just_out[("CO", DFT_B)], "C", "f+", 0.0201, to="O")
    assert _judge(just_out).outcome is Outcome.FAIL


def test_a_value_below_the_published_one_is_a_failure_too():
    runs = _runs()
    runs[("CO", HF_B)] = _shift(runs[("CO", HF_B)], "C", "f-", -0.03, to="O")
    assert _judge(runs).outcome is Outcome.FAIL


def test_an_anion_outside_tolerance_with_every_neutral_inside_is_partial():
    runs = _runs()
    runs[("CN-", HF_B)] = _shift(runs[("CN-", HF_B)], "C", "f+", 0.03, to="N")
    verdict = _judge(runs)
    assert verdict.outcome is Outcome.PARTIAL
    assert verdict.anions_outside == ("CN-",)
    assert all(reason.startswith("CN-") for reason in verdict.reasons)


def test_a_neutral_failure_beats_an_anion_failure_and_both_are_listed():
    runs = _runs()
    runs[("CN-", HF_B)] = _shift(runs[("CN-", HF_B)], "C", "f+", 0.03, to="N")
    runs[("CO2", HF_B)] = _shift(runs[("CO2", HF_B)], "C", "f+", 0.03, to="O")
    verdict = _judge(runs)
    assert verdict.outcome is Outcome.FAIL
    assert any(reason.startswith("CO2") for reason in verdict.reasons) and any(reason.startswith("CN-") for reason in verdict.reasons)
    assert verdict.anions_outside == ("CN-",)


def test_a_site_the_run_puts_on_the_wrong_atom_fails_a_neutral_species():
    """CO's f- put on the oxygen: the numbers move by far more than the tolerance too, but the site row says it in its own words."""
    runs = _runs()
    run = runs[("CO", DFT_B)]
    swapped = dataclasses.replace(run, f_minus=run.f_minus[::-1], f_zero=tuple((p + m) / 2 for p, m in zip(run.f_plus, run.f_minus[::-1])),
                                  dual=tuple(p - m for p, m in zip(run.f_plus, run.f_minus[::-1])))
    runs[("CO", DFT_B)] = swapped
    verdict = _judge(runs)
    assert verdict.outcome is Outcome.FAIL
    assert any("CO f- at B3LYP/6-31G**: the largest value is on O, the documented site is C" in r for r in verdict.reasons)


def test_a_site_miss_on_an_anion_alone_is_partial():
    runs = _runs()
    run = runs[("CN-", DFT_B)]
    flipped = dataclasses.replace(run, f_minus=run.f_minus[::-1], f_zero=tuple((p + m) / 2 for p, m in zip(run.f_plus, run.f_minus[::-1])),
                                  dual=tuple(p - m for p, m in zip(run.f_plus, run.f_minus[::-1])))
    runs[("CN-", DFT_B)] = flipped
    assert _judge(runs).outcome is Outcome.PARTIAL


def test_the_undecidable_site_is_never_a_row():
    rows = _judge().site_rows
    assert not [r for r in rows if (r.molecule, r.attack, r.level) == ("NCO-", "f-", HF_B)]


# --- what makes the gate unable to decide --------------------------------------------------------------------------------------


def _reason(verdict, fragment):
    assert verdict.outcome is Outcome.NOT_EVALUABLE, verdict
    assert any(fragment in reason for reason in verdict.reasons), verdict.reasons


def test_another_tolerance_cannot_be_used():
    for tolerance in (None, 0.03, 0.01):
        _reason(_judge(tolerance=tolerance), "preregistered one is 0.02")


def test_no_floor_or_a_noisy_floor_cannot_be_used():
    _reason(_judge(floor=None), "no noise floor")
    _reason(_judge(floor=0.0061), "noise floor 0.0061")
    assert _judge(floor=0.005).outcome is Outcome.PASS


def test_another_orca_is_a_recorded_difference_not_a_pass():
    _reason(_judge(orca_versions=["6.1.1", "6.0.0"]), "ORCA 6.0.0")
    _reason(_judge(orca_versions=[]), "no recorded version")


def test_a_run_that_did_not_complete_cannot_be_judged():
    _reason(_judge(unfinished_runs=["CO at HF/6-31G**"]), "did not complete: CO at HF/6-31G**")
    runs = _runs()
    runs[("CO", HF_B)] = dataclasses.replace(runs[("CO", HF_B)], completed=False)
    _reason(_judge(runs), "CO at HF/6-31G** did not complete")


def test_every_species_at_every_decided_level_is_needed():
    runs = _runs()
    del runs[("CNO-", DFT_B)]
    _reason(_judge(runs), "no run for: CNO- at B3LYP/6-31G**")


def test_a_run_at_the_wrong_charge_or_spin_cannot_be_judged():
    runs = _runs()
    runs[("CN-", HF_B)] = dataclasses.replace(runs[("CN-", HF_B)], charge=0)
    _reason(_judge(runs), "CN- at HF/6-31G** ran at charge 0, not the species' -1")
    runs = _runs()
    runs[("CO", HF_B)] = dataclasses.replace(runs[("CO", HF_B)], multiplicity=3)
    _reason(_judge(runs), "multiplicity 3")


def test_a_run_not_on_the_optimized_geometry_cannot_be_judged():
    runs = _runs()
    runs[("CO", HF_B)] = dataclasses.replace(runs[("CO", HF_B)], on_optimized_geometry=False)
    _reason(_judge(runs), "did not run on the ORCA-optimized geometry")


def test_a_run_of_other_atoms_cannot_be_judged():
    runs = _runs()
    runs[("CO", HF_B)] = dataclasses.replace(runs[("CO", HF_B)], symbols=("O", "C"))
    _reason(_judge(runs), "has atoms ('O', 'C')")


def test_a_run_whose_own_sum_rule_fails_is_a_defect_not_a_result():
    runs = _runs()
    run = runs[("CO", HF_B)]
    runs[("CO", HF_B)] = dataclasses.replace(run, f_plus=tuple(v + 0.01 for v in run.f_plus))
    verdict = _judge(runs)
    _reason(verdict, "CO at HF/6-31G**: f+ sums to 1.0199, not 1")  # the published CO column sums to 0.9999


def test_a_dual_that_is_not_the_difference_cannot_be_judged():
    runs = _runs()
    run = runs[("CO", HF_B)]
    runs[("CO", HF_B)] = dataclasses.replace(run, dual=(0.0, 0.0))
    _reason(_judge(runs), "the dual descriptor is not f+ - f-")


def test_an_f0_that_is_not_the_mean_cannot_be_judged():
    runs = _runs()
    run = runs[("CO", HF_B)]
    runs[("CO", HF_B)] = dataclasses.replace(run, f_zero=run.f_plus)
    _reason(_judge(runs), "f0 is not the mean")


def test_not_evaluable_takes_precedence_over_a_failure():
    runs = _runs()
    runs[("CO", DFT_B)] = _shift(runs[("CO", DFT_B)], "C", "f+", 0.03, to="O")
    verdict = _judge(runs, orca_versions=["6.0.0"])
    assert verdict.outcome is Outcome.NOT_EVALUABLE and verdict.rows == ()


def test_every_undecided_reason_is_collected():
    verdict = _judge(tolerance=0.05, floor=0.1, orca_versions=["6.0.0"], unfinished_runs=["CO at HF/6-31G**"])
    assert verdict.outcome is Outcome.NOT_EVALUABLE and len(verdict.reasons) == 4


# --- comparison, repeat and floor ------------------------------------------------------------------------------------------------


def test_a_symmetric_pair_that_came_apart_is_seen_by_its_worse_atom():
    """CO2's two oxygens are one published number; if one is off, the row is the off one."""
    run = _run("CO2", HF_B)
    values = list(run.f_plus)
    values[0] += 0.05
    values[1] -= 0.05
    off = dataclasses.replace(run, f_plus=tuple(values))
    entry = next(e for e in gate.decided_entries() if (e.molecule, e.element, e.attack, e.level) == ("CO2", "O", "f+", HF_B))
    (row,) = gate.compare([entry], {("CO2", HF_B): off}, gate.TOLERANCE)
    assert row.difference == pytest.approx(0.05) and row.within is False


def test_an_entry_with_no_run_is_not_compared():
    assert gate.compare(gate.decided_entries(), {}, gate.TOLERANCE) == []


def test_a_reported_comparison_never_decides():
    run = _run("CO", HF_B)
    entry = next(e for e in gate.olah_entries() if (e.molecule, e.element, e.attack, e.level) == ("CO", "C", "f+", "HF/6-311+G**"))
    (row,) = gate.compare([entry], {("CO", "HF/6-311+G**"): dataclasses.replace(run, level="HF/6-311+G**")}, gate.TOLERANCE, decided=False)
    assert row.decided is False


def test_a_repeat_of_the_same_run_differs_by_nothing_and_a_changed_one_by_its_change():
    first = _run("CO", HF_B)
    assert set(gate.repeat_differences(first, first).values()) == {0.0}
    second = _shift(first, "C", "f+", 0.004, to="O")
    differences = gate.repeat_differences(first, second)
    assert max(differences.values()) == pytest.approx(0.004)
    assert gate.noise_floor(gate.repeat_differences(first, first), differences) == pytest.approx(0.004)


def test_a_repeat_of_another_species_is_refused_and_a_floor_needs_a_repeat():
    with pytest.raises(ValueError, match="same species at the same level"):
        gate.repeat_differences(_run("CO", HF_B), _run("CO", DFT_B))
    with pytest.raises(ValueError, match="at least one repeat"):
        gate.noise_floor()


# --- from the stored records to a verdict -------------------------------------------------------------------------------------


def _record(run, *, attempt=1, completed=True, **changes):
    record = {
        "species": run.molecule, "level": run.level, "symbols": list(run.symbols), "f_plus": list(run.f_plus),
        "f_minus": list(run.f_minus), "f_zero": list(run.f_zero), "dual": list(run.dual), "charge": run.charge,
        "multiplicity": run.multiplicity, "orca_version": run.orca_version, "completed": completed,
        "on_optimized_geometry": True, "attempt": attempt,
    }
    record.update(changes)
    return record


def _records():
    return [_record(run) for run in _runs().values()]


def test_a_record_describes_the_run_it_was_written_from():
    run = _run("CN-", HF_B)
    back = gate.measured_from_record(_record(run))
    assert back == run


def test_a_record_that_does_not_say_it_ran_on_the_optimized_geometry_did_not():
    """Fail closed: a missing key is not a yes."""
    record = _record(_run("CO", HF_B))
    del record["on_optimized_geometry"]
    assert gate.measured_from_record(record).on_optimized_geometry is False


def test_perfect_records_pass():
    verdict = gate.judge_records(_records(), floor=0.0)
    assert verdict.outcome is Outcome.PASS


def test_one_completed_attempt_after_failed_ones_is_the_one_used():
    run = _run("CO", HF_B)
    records = [r for r in _records() if (r["species"], r["level"]) != ("CO", HF_B)]
    records += [_record(run, attempt=1, completed=False), _record(run, attempt=2, completed=False), _record(run, attempt=3)]
    chosen, never, unfinished, conflicts = gate.settle_attempts(records)
    assert chosen[("CO", HF_B)]["attempt"] == 3 and not never and not unfinished and not conflicts
    assert gate.judge_records(records, floor=0.0).outcome is Outcome.PASS


def test_fewer_failed_attempts_than_the_limit_leave_the_gate_unable_to_decide():
    run = _run("CO", HF_B)
    records = [r for r in _records() if (r["species"], r["level"]) != ("CO", HF_B)]
    records += [_record(run, attempt=1, completed=False), _record(run, attempt=2, completed=False)]
    verdict = gate.judge_records(records, floor=0.0)
    _reason(verdict, "did not complete: CO at HF/6-31G**")


def test_a_species_that_never_completes_in_three_attempts_is_not_computed():
    run = _run("CNO-", DFT_B)
    records = [r for r in _records() if (r["species"], r["level"]) != ("CNO-", DFT_B)]
    records += [_record(run, attempt=n, completed=False) for n in (1, 2, 3)]
    chosen, never, unfinished, conflicts = gate.settle_attempts(records)
    assert never == {("CNO-", DFT_B)} and ("CNO-", DFT_B) not in chosen
    verdict = gate.judge_records(records, floor=0.0)
    # an anion ORCA cannot compute is an anion that did not reproduce: PARTIAL, not undecidable
    assert verdict.outcome is Outcome.PARTIAL
    assert verdict.reasons == ("CNO- at B3LYP/6-31G**: ORCA did not complete the three states in 3 attempts",)
    assert verdict.anions_outside == ("CNO-",)


def test_a_neutral_species_that_never_completes_fails_the_gate():
    run = _run("CO2", HF_B)
    records = [r for r in _records() if (r["species"], r["level"]) != ("CO2", HF_B)]
    records += [_record(run, attempt=n, completed=False) for n in (1, 2, 3)]
    verdict = gate.judge_records(records, floor=0.0)
    assert verdict.outcome is Outcome.FAIL
    assert verdict.reasons[0].startswith("CO2 at HF/6-31G**: ORCA did not complete")


def test_two_completed_attempts_of_one_job_are_a_second_draw_and_the_gate_does_not_choose():
    records = _records() + [_record(_run("CO", HF_B), attempt=2)]
    verdict = gate.judge_records(records, floor=0.0)
    assert verdict.outcome is Outcome.NOT_EVALUABLE
    assert any("CO at HF/6-31G** has 2 completed attempts" in r for r in verdict.reasons)


def test_the_versions_the_records_carry_are_judged():
    records = [_record(_run(*pair), orca_version="6.0.0") if pair == ("CO", HF_B) else _record(_run(*pair)) for pair in _runs()]
    _reason(gate.judge_records(records, floor=0.0), "ORCA 6.0.0")


# --- the reported arm -------------------------------------------------------------------------------------------------------------


def test_the_reported_arm_never_overlaps_what_decides():
    """Nothing in the reported arm is a decided number: the levels are the diffuse ones and the application's default."""
    decided = {(e.source, e.molecule, e.element, e.attack, e.level) for e in gate.decided_entries()}
    reported = {(e.source, e.molecule, e.element, e.attack, e.level) for e in gate.reported_entries()}
    assert not decided & reported
    assert {e.level for e in gate.reported_entries()} == set(gate.REPORTED_LEVELS) | {gate.DEFAULT_LEVEL}
    assert not set(gate.REPORTED_LEVELS) & set(DECIDED_LEVELS) and gate.DEFAULT_LEVEL not in DECIDED_LEVELS


def test_the_default_level_is_compared_with_the_three_sources_formaldehyde():
    entries = [e for e in gate.reported_entries() if e.level == gate.DEFAULT_LEVEL]
    assert {e.source for e in entries} == {"olah2002", "thanikaivelan2002", "bultinck2007"}
    assert {e.molecule for e in entries} == {"H2CO"}
    assert len(entries) == 16  # Thanikaivelan 6, Bultinck 6, Olah C and O at B3LYP/6-31G** 4


def test_the_reported_rows_mark_the_columns_that_fail_the_sum_rule_and_decide_nothing():
    rows = gate.reported_rows({("CO2", gate.HF_A): dataclasses.replace(_run("CO2", HF_B), level=gate.HF_A)})
    assert rows and all(row["decided"] is False for row in rows)
    assert not any(row["suspect"] for row in rows)  # CO2's failing column is at B3LYP/6-31G**, not the diffuse HF level
    # a reported level that has the misprint is marked: none of the three failing columns is at a reported level, so check the rule
    failing = {(m, a, level) for m, a, level, _ in gate.failing_columns()}
    assert all(level in DECIDED_LEVELS for _, _, level in failing)


def test_a_reported_row_outside_tolerance_does_not_change_the_verdict():
    """The verdict is `judge`'s, from the decided runs; the reported rows are a separate list nobody judges."""
    far = dataclasses.replace(
        _run("CO", HF_B), level=gate.HF_A, f_plus=(0.9, 0.1), f_minus=(0.9, 0.1), f_zero=(0.9, 0.1), dual=(0.0, 0.0)
    )
    rows = gate.reported_rows({("CO", gate.HF_A): far})
    assert any(row["within"] is False for row in rows)
    assert _judge().outcome is Outcome.PASS


# --- which atoms a published number is of ---------------------------------------------------------------------------------------


def test_acetones_carbons_carry_the_labels_the_table_gives_them_and_every_other_species_its_elements():
    assert SPECIES["acetone"].site_labels == ("Cm", "C", "Cm", "O") + ("H",) * 6
    assert all(species.site_labels == species.atoms for name, species in SPECIES.items() if name != "acetone")
    # the atoms embedded from the SMILES: the carbonyl carbon is the SECOND heavy atom
    mol = Chem.MolFromSmiles(SPECIES["acetone"].smiles)
    carbonyl = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C" and any(b.GetBondTypeAsDouble() == 2 for b in a.GetBonds()))
    assert SPECIES["acetone"].labels[carbonyl] == "C"


def _acetone_run(f_plus, level=HF_B):
    """An acetone run whose f+ is `f_plus` (carbon, carbon, carbon, oxygen, six hydrogens); the rest is as the published columns give it."""
    base = _run("acetone", level)
    return dataclasses.replace(base, f_plus=tuple(f_plus))


def test_a_published_number_is_compared_with_the_atoms_it_names_and_not_every_atom_of_the_element():
    """Acetone's carbons are three atoms of one element and two published labels. A first version compared the carbonyl carbon's published
    value with whichever of the three carbons was farthest from it, which for a methyl carbon is another atom entirely."""
    run = _acetone_run((0.1056, 0.0293, 0.1063, 0.0569, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1))
    assert run.of_element("f+", "C") == (0.0293,)
    assert run.of_element("f+", "Cm") == (0.1056, 0.1063)
    assert run.of_element("f+", "O") == (0.0569,)
    entry = gate.Entry("olah2002", "acetone", "C", "f+", HF_B, 0.0474)
    (row,) = gate.compare([entry], {("acetone", HF_B): run}, gate.TOLERANCE, decided=False)
    assert row.measured == 0.0293 and row.difference == pytest.approx(0.0293 - 0.0474) and row.within is True
    methyl = gate.Entry("olah2002", "acetone", "Cm", "f+", HF_B, 0.1025)
    (row,) = gate.compare([methyl], {("acetone", HF_B): run}, gate.TOLERANCE, decided=False)
    assert row.measured == 0.1063 and row.within is True  # the farther of the two equivalent methyl carbons, as for any symmetric pair


def test_a_run_that_does_not_have_the_species_atoms_is_labelled_by_its_elements():
    """The labels are the species' when the run has the atoms the species should, and nothing else's."""
    run = dataclasses.replace(_run("CO2", HF_B), molecule="acetone", symbols=("C", "C"), f_plus=(0.5, 0.5), f_minus=(0.5, 0.5), f_zero=(0.5, 0.5), dual=(0.0, 0.0))
    assert run.labels() == ("C", "C")


def test_every_published_number_of_a_gate_species_names_atoms_that_species_has():
    """A comparison skips an entry whose label no atom carries, silently, so the labels of the tables are held to the species here:
    acetone's methyl carbons ("Cm") were in the table and compared with nothing until the labels existed."""
    for entry in (*gate.decided_entries(), *gate.reported_entries()):
        assert entry.element in SPECIES[entry.molecule].site_labels, (entry.molecule, entry.element, entry.level)


def test_the_reported_arm_compares_acetones_methyl_carbons_too():
    far = dataclasses.replace(_run("acetone", HF_B), level=gate.HF_A)
    rows = [r for r in gate.reported_rows({("acetone", gate.HF_A): far}) if r["molecule"] == "acetone"]
    assert {(r["element"], r["attack"]) for r in rows} == {(el, at) for el in ("C", "O", "Cm") for at in gate.ATTACKS}
