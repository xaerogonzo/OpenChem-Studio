"""What a window says about a recipe run: job rows, choices, one sentence (`docs/RECIPES_DESIGN.md` section 8).

Pure: the runs come from the real evaluator over real stored-run objects, and nothing here draws anything.
"""

from __future__ import annotations

import pytest

from openchem.chem.lewis_pairing_eval import evaluate_lewis_pairing
from openchem.domain.lewis_pairing import LEWIS_PAIRING
from openchem.domain.recipe_preview import headline, job_rows, pick_choices
from openchem.domain.recipe_run import RecipeRunStatus, StepState
from tests.lewis_helpers import METHOD, borane, carbon_monoxide, member, runs_of, stored_run

NAMES = {"bh3": "BH3", "co": "CO"}
CHARGES = {"bh3": 0, "co": 0}
CONFORMERS = {"bh3": 1, "co": 1}


def _rows(run, *, orca=True, conformers=None):
    return job_rows(
        run, LEWIS_PAIRING, names=NAMES, formal_charges=CHARGES,
        conformer_counts=CONFORMERS if conformers is None else conformers, orca_configured=orca,
    )


def _run(first, second, **kw):
    return evaluate_lewis_pairing(first, second, method_basis=METHOD, role="acid", **kw)


# --- one row per job, in the plan's order -----------------------------------------------------------------------


def test_there_is_one_row_per_job_of_the_plan_in_its_order():
    rows = _rows(_run(borane(), carbon_monoxide()))
    assert [r.step_id for r in rows] == ["sp_first", "dscf_first", "sp_second", "dscf_second"]
    assert [r.slot for r in rows] == ["first", "first", "second", "second"]
    assert [r.calc_type for r in rows] == ["sp", "delta_scf", "sp", "delta_scf"]


def test_a_job_a_stored_run_supplied_is_done_and_says_which_run():
    rows = _rows(_run(borane(), carbon_monoxide()))
    assert all(r.state is StepState.COMPLETED and not r.to_do for r in rows)
    assert rows[0].note == "from stored run bh3-sp" and rows[3].note == "from stored run co-dscf"
    assert all(not r.requirements and not r.would_run_with for r in rows), "a finished job asks for nothing"


def test_a_finished_jobs_note_shows_short_run_ids_and_the_record_keeps_the_full_ones():
    from tests.lewis_helpers import runs_of

    long_sp = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    co = member("[C-]#[O+]", "co", "CO", [
        stored_run("co", long_sp, "sp", {"orca.homo_energy": -10.17, "orca.lumo_energy": 1.0}),
        runs_of("co", {"homo": 0, "lumo": 0, "hardness": 8.4})[1],
    ])
    run = _run(borane(), co)
    row = _rows(run)[2]
    assert row.note == "from stored run a1b2c3d4"
    assert next(s for s in run.steps if s.step_id == "sp_second").reason == f"from stored run {long_sp}"
    assert {b.evidence.run_id for b in run.bindings if b.target == "second_homo"} == {long_sp}


def test_an_ambiguity_sentence_shows_short_ids_for_the_runs_it_names():
    long_old, long_older = "0123456789abcdef0123456789abcdef", "fedcba9876543210fedcba9876543210"
    co = member("[C-]#[O+]", "co", "CO", [
        stored_run("co", long_old, "sp", {"orca.homo_energy": -10.0, "orca.lumo_energy": 1.0},
                   input_fingerprint="o" * 64, completed_at=5.0),
        stored_run("co", long_older, "sp", {"orca.homo_energy": -11.0, "orca.lumo_energy": 2.0},
                   input_fingerprint="p" * 64, completed_at=3.0),
    ] + runs_of("co", {"homo": 0, "lumo": 0, "hardness": 8.4})[1:])
    run = _run(borane(), co)
    [row] = [r for r in _rows(run) if r.step_id == "sp_second"]
    assert "01234567" in row.note and "fedcba98" in row.note and long_old not in row.note
    [choice] = pick_choices(run, names=NAMES)
    assert long_old not in choice.reason and "01234567" in choice.reason
    assert choice.candidates == (long_old, long_older), "what is CHOSEN is still the full id"
    assert long_old in next(b.reason for b in run.bindings if b.target == "second_homo"), "the record keeps the sentence whole"


def test_short_ids_fall_back_to_the_whole_id_for_two_that_would_collide():
    from openchem.domain.recipe_preview import short_id, short_ids

    assert short_id("0123456789abcdef") == "01234567"
    assert short_ids(("0123456789", "abcdefghij")) == ("01234567", "abcdefgh")
    assert short_ids(("0123456789", "01234567ab")) == ("0123456789", "01234567ab")


def test_the_title_names_the_molecule_and_what_the_job_gives():
    rows = _rows(_run(borane(), carbon_monoxide()))
    assert rows[0].title == "Single point on BH3: HOMO and LUMO energies"
    assert rows[3].title == "Delta-SCF job on CO: hardness"


def test_a_missing_job_is_a_row_to_do_with_the_binders_own_sentence():
    rows = _rows(_run(borane(), carbon_monoxide(hardness=False)))
    [todo] = [r for r in rows if r.to_do]
    assert todo.step_id == "dscf_second" and todo.molecule_uuid == "co" and todo.state is StepState.BLOCKED
    assert todo.note.startswith("CO has no delta-SCF run. Run one in the Quantum Chemistry panel at B3LYP def2-SVP (gas phase)")


def test_a_job_to_do_says_what_it_would_run_with():
    rows = _rows(_run(borane(), carbon_monoxide(hardness=False)))
    [todo] = [r for r in rows if r.to_do]
    assert todo.would_run_with.startswith("B3LYP def2-SVP (gas phase), charge +0")


def test_the_charge_in_the_settings_is_the_molecules_own():
    ion = member("C[N+](C)(C)C", "ion", "ion", [], charge=1)
    run = evaluate_lewis_pairing(borane(), ion, method_basis=METHOD, role="acid")
    rows = job_rows(run, LEWIS_PAIRING, names={"bh3": "BH3", "ion": "ion"}, formal_charges={"bh3": 0, "ion": 1},
                    conformer_counts={"bh3": 1, "ion": 1}, orca_configured=True)
    assert next(r for r in rows if r.molecule_uuid == "ion").would_run_with.startswith(f"{METHOD} (gas phase), charge +1")


def test_a_job_with_everything_it_needs_is_ready_to_run_and_one_without_is_not():
    run = _run(borane(), carbon_monoxide(hardness=False))
    [ready] = [r for r in _rows(run) if r.to_do]
    assert ready.ready_to_run and all(r.ok for r in ready.requirements)
    [no_orca] = [r for r in _rows(run, orca=False) if r.to_do]
    assert not no_orca.ready_to_run
    missing = [r for r in no_orca.requirements if not r.ok]
    assert [m.what for m in missing] == ["the ORCA executable"] and "External Tools" in missing[0].how_to_fix
    [no_conformer] = [r for r in _rows(run, conformers={"bh3": 1, "co": 0}) if r.to_do]
    missing = [r for r in no_conformer.requirements if not r.ok]
    assert [m.what for m in missing] == ["a 3D conformer for CO"] and "Conformers" in missing[0].how_to_fix


def test_a_requirement_that_is_met_carries_no_hint():
    [row] = [r for r in _rows(_run(borane(), carbon_monoxide(hardness=False))) if r.to_do]
    assert all(r.how_to_fix == "" for r in row.requirements if r.ok)


def test_a_molecule_with_no_name_is_named_by_its_slot():
    run = _run(borane(), carbon_monoxide(hardness=False))
    rows = job_rows(run, LEWIS_PAIRING, names={}, formal_charges={}, conformer_counts={}, orca_configured=True)
    assert rows[0].title == "Single point on first: HOMO and LUMO energies"


def test_the_rows_read_the_slot_from_the_plan_not_from_a_name():
    swapped = _run(carbon_monoxide(), borane())
    rows = _rows(swapped)
    assert [(r.slot, r.molecule_uuid) for r in rows[:2]] == [("first", "co"), ("first", "co")]


# --- choices among runs ------------------------------------------------------------------------------------------


def _earlier(molecule: str, tag: str, when: float, **kw):
    return stored_run(molecule, f"{molecule}-sp-{tag}", "sp", {"orca.homo_energy": -10.0, "orca.lumo_energy": 1.0},
                      input_fingerprint=tag * 64, completed_at=when, **kw)


def test_an_ambiguity_becomes_one_choice_per_molecule_and_calculation_not_one_per_number():
    co = member("[C-]#[O+]", "co", "CO", [_earlier("co", "o", 5.0), _earlier("co", "p", 3.0)] + runs_of("co", {"homo": 0, "lumo": 0, "hardness": 8.4})[1:])
    run = _run(borane(), co)
    [choice] = pick_choices(run, names=NAMES)
    assert (choice.slot, choice.calc_type, choice.molecule_name) == ("second", "sp", "CO")
    assert choice.candidates == ("co-sp-o", "co-sp-p"), "newest first"
    assert choice.what == "Single points of CO" and "earlier geometry" in choice.reason


def test_a_clean_run_has_nothing_to_choose():
    assert pick_choices(_run(borane(), carbon_monoxide()), names=NAMES) == ()


def test_a_gap_that_is_not_an_ambiguity_is_not_a_choice():
    assert pick_choices(_run(borane(), carbon_monoxide(hardness=False)), names=NAMES) == ()


# --- the one sentence --------------------------------------------------------------------------------------------


def test_a_complete_run_says_so_and_a_partial_one_says_it_is_not_complete():
    complete = _run(borane(), carbon_monoxide())
    partial = _run(borane(), carbon_monoxide(hardness=False))
    assert complete.status is RecipeRunStatus.COMPLETED and headline(complete).startswith("Complete.")
    assert partial.status is RecipeRunStatus.PARTIAL
    assert headline(partial).startswith("Partial.") and "not a complete answer" in headline(partial)


def test_a_partial_run_with_no_line_is_not_described_as_having_lines():
    run = _run(borane(), member("[C-]#[O+]", "co", "CO", []))
    assert run.status is RecipeRunStatus.PARTIAL and run.result is None
    assert "no line of evidence could be evaluated" in headline(run)


def test_a_run_with_nothing_is_blocked_and_says_what_that_means():
    run = _run(member("B", "bh3", "BH3", []), member("[C-]#[O+]", "co", "CO", []))
    assert run.status is RecipeRunStatus.BLOCKED and "Nothing could be evaluated" in headline(run)


@pytest.mark.parametrize("status", [s for s in RecipeRunStatus if s not in (
    RecipeRunStatus.COMPLETED, RecipeRunStatus.PARTIAL, RecipeRunStatus.BLOCKED, RecipeRunStatus.FAILED)])
def test_every_other_status_still_has_a_sentence(status):
    from dataclasses import replace

    base = _run(borane(), carbon_monoxide())
    assert headline(replace(base, status=status)).lower().startswith(status.value)
