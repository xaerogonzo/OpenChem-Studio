"""A kept recipe answer as the Results reader holds it (`docs/RECIPES_DESIGN.md` sections 6, 7 and 12, slice 3b).

Pure: the runs come from the real evaluator over real stored-run objects, the assessments from the real `assess`, and
the reader's own rules (`MergedResults`, `format_report`) are what read the entries. Nothing draws anything.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from openchem.chem.lewis_pairing_eval import evaluate_lewis_pairing
from openchem.domain.merged_results import is_report_shaped, merge_reports
from openchem.domain.recipe_answer import (
    GONE_MOLECULE,
    STALE_STAMP,
    RecipeAnswer,
    project_answers,
    report_id_of,
)
from openchem.domain.recipe_run import Assessment, ProjectView, RecipeRun, RecipeRunStatus, assess
from openchem.domain.report import ReportResult
from openchem.ui.report_format import format_report
from tests.lewis_helpers import METHOD, borane, carbon_monoxide

FORMATS = ("Plain text", "Markdown", "JSON", "CSV")
NAMES = {"bh3": "BH3", "co": "CO", "nh3": "NH3"}
VERSION = 7


def _run(first=None, second=None, **kw) -> RecipeRun:
    return evaluate_lewis_pairing(
        first or borane(), second or carbon_monoxide(), method_basis=kw.pop("method_basis", METHOD), role="acid", **kw
    )


def _view(run: RecipeRun, **changes) -> ProjectView:
    """The project exactly as `run` found it, then changed."""
    keys = {i.molecule_uuid: i.constitution_key for i in run.inputs}
    qc_run_ids = {e.run_id for e in run.evidence()}
    keys.update(changes.pop("keys", {}))
    for gone in changes.pop("removed", ()):
        keys.pop(gone)
    qc_run_ids -= set(changes.pop("deleted_runs", ()))
    return ProjectView(constitution_keys=keys, qc_run_ids=qc_run_ids, **changes)


def _answers(runs, *, viewing="bh3", views=None, names=NAMES, version=VERSION):
    views = views or {}
    return project_answers(
        runs,
        viewing=viewing,
        assessments={r.run_id: assess(r, views.get(r.run_id) or _view(r)) for r in runs},
        names=names,
        structure_version=version,
    )


def _stale(answer, version=VERSION) -> bool:
    return merge_reports([answer], structure_version=version).is_stale(answer)


# --- who sees it ------------------------------------------------------------------------------------------------


def test_the_answer_shows_under_each_molecule_that_took_part_stamped_with_that_molecule():
    run = _run()
    [under_borane] = _answers([run], viewing="bh3")
    [under_mono] = _answers([run], viewing="co")
    assert under_borane.molecule_uuid == "bh3" and under_mono.molecule_uuid == "co"
    assert under_borane.facts == under_mono.facts == run.result.facts


def test_it_does_not_show_under_a_molecule_that_took_no_part():
    assert _answers([_run()], viewing="nh3") == ()


def test_a_run_with_no_result_has_nothing_to_show():
    nothing = _run(second=carbon_monoxide(hardness=False))
    nothing = replace(nothing, result=None)
    assert _answers([nothing]) == ()


def test_it_is_a_report_the_reader_admits_and_every_copy_format_writes():
    [answer] = _answers([_run()])
    assert isinstance(answer, RecipeAnswer) and isinstance(answer, ReportResult) and is_report_shaped(answer)
    for fmt in FORMATS:
        assert format_report(answer, fmt)


def test_the_answers_keep_the_run_they_describe_and_nothing_is_drawn_for_them():
    """A stale stamp is not a version anyone prints; that holds only while the answer declares no picture."""
    run = _run()
    [answer] = _answers([run])
    assert answer.run_id == run.run_id
    assert not getattr(answer, "spatial", ()) and not getattr(answer, "charts", ())


# --- what it is called --------------------------------------------------------------------------------------------


def test_the_title_names_the_molecules_in_slot_order_and_the_level():
    [answer] = _answers([_run()])
    assert answer.name == "Lewis pairing: BH3 + CO at B3LYP def2-SVP (gas phase)"


def test_the_title_says_the_solvent_when_there_is_one():
    water = dict(solvent="Water")
    [answer] = _answers([_run(borane(**water), carbon_monoxide(**water), solvent="Water")])
    assert answer.name == "Lewis pairing: BH3 + CO at B3LYP def2-SVP in Water"


def test_a_molecule_no_longer_in_the_project_is_not_given_a_name_it_does_not_have():
    [answer] = _answers([_run()], names={"bh3": "BH3"})
    assert answer.name.startswith(f"Lewis pairing: BH3 + {GONE_MOLECULE} at ")


def test_the_report_id_is_the_recipe_and_the_run_so_two_kept_runs_never_share_one():
    first, second = _run(), _run()
    answers = _answers([first, second])
    assert [a.report_id for a in answers] == [report_id_of(first), report_id_of(second)]
    assert report_id_of(first) == f"lewis_pairing:{first.run_id}" and len({a.report_id for a in answers}) == 2


def test_the_same_pair_kept_twice_at_one_level_is_told_apart_by_its_short_run_id():
    first, second = _run(), _run()
    one, two = _answers([first, second])
    assert one.name != two.name
    assert one.name.endswith(f"[{first.run_id[:8]}]") and two.name.endswith(f"[{second.run_id[:8]}]")


def test_a_pair_kept_once_has_no_suffix_and_a_different_partner_is_not_a_clash():
    other = evaluate_lewis_pairing(
        borane(), carbon_monoxide(), method_basis=METHOD, role="acid"
    )
    other = replace(other, inputs=(other.inputs[0], replace(other.inputs[1], molecule_uuid="nh3")))
    [a, b] = _answers([_run(), other])
    assert "[" not in a.name and "[" not in b.name and a.name != b.name


def test_the_same_pair_at_two_levels_is_not_a_clash():
    level = "PBE0 def2-TZVP"
    a = _run()
    b = _run(borane(method_basis=level), carbon_monoxide(method_basis=level), method_basis=level)
    first, second = _answers([a, b])
    assert "[" not in first.name and "[" not in second.name


# --- current and stale ------------------------------------------------------------------------------------------


def test_an_answer_the_project_has_not_moved_on_from_reads_current_at_the_structure_version_it_is_given():
    [answer] = _answers([_run()])
    assert answer.structure_version == VERSION and answer.stale_note == "" and not _stale(answer)


def test_editing_either_molecule_marks_it_stale_and_names_the_molecule():
    run = _run()
    for edited, name in (("bh3", "BH3"), ("co", "CO")):
        view = _view(run, keys={edited: "something else"})
        [answer] = _answers([run], viewing="bh3", views={run.run_id: view})
        assert _stale(answer) and answer.structure_version == STALE_STAMP
        assert f"The structure of {name} was edited after this answer was made." in answer.stale_note
        assert "Evaluate it again from the Tools menu to bring it up to date." in answer.stale_note


def test_both_molecules_edited_are_both_named():
    run = _run()
    view = _view(run, keys={"bh3": "x", "co": "y"})
    [answer] = _answers([run], views={run.run_id: view})
    assert "The structure of BH3 and CO was edited" in answer.stale_note


def test_a_removed_molecule_marks_it_stale_without_naming_one_that_is_gone():
    run = _run()
    view = _view(run, removed=["co"])
    [answer] = _answers([run], viewing="bh3", names={"bh3": "BH3"}, views={run.run_id: view})
    assert _stale(answer) and "A molecule this answer was made from is no longer in the project." in answer.stale_note


def test_two_removed_molecules_are_said_in_the_plural():
    run = _run()
    view = _view(run, removed=["bh3", "co"])
    [answer] = _answers([run], viewing="bh3", names={}, views={run.run_id: view})
    assert "Molecules this answer was made from are no longer in the project." in answer.stale_note


def test_a_deleted_run_marks_it_stale_says_the_numbers_are_the_recorded_ones_and_names_the_run():
    run = _run()
    view = _view(run, deleted_runs=["co-dscf"])
    [answer] = _answers([run], views={run.run_id: view})
    assert _stale(answer) and answer.structure_version == STALE_STAMP
    assert "The quantum-chemistry run behind its numbers (co-dscf) was deleted" in answer.stale_note
    assert "the numbers shown are the ones recorded" in answer.stale_note


def test_several_deleted_runs_are_said_in_the_plural_with_short_ids():
    run = _run()
    view = _view(run, deleted_runs=["co-dscf", "co-sp"])
    [answer] = _answers([run], views={run.run_id: view})
    assert "The quantum-chemistry runs behind its numbers (co-dscf, co-sp) were deleted" in answer.stale_note


def test_a_recipe_version_this_build_does_not_have_is_shown_as_recorded_and_never_offers_a_rerun():
    run = replace(_run(), recipe_version="v0-never-shipped")
    [answer] = _answers([run])
    assert _stale(answer)
    assert "This build has no version v0-never-shipped of the recipe" in answer.stale_note
    assert "Evaluate it again" not in answer.stale_note


def test_every_cause_is_reported_at_once():
    run = _run()
    view = _view(run, keys={"bh3": "x"}, removed=["co"], deleted_runs=["bh3-sp"])
    [answer] = _answers([run], names={"bh3": "BH3"}, views={run.run_id: view})
    note = answer.stale_note
    assert "was edited" in note and "no longer in the project" in note and "was deleted" in note


def test_a_stale_answer_keeps_every_fact_it_recorded():
    run = _run()
    view = _view(run, keys={"co": "other"})
    [answer] = _answers([run], views={run.run_id: view})
    assert answer.facts == run.result.facts


def test_the_reader_names_the_stale_answer_through_its_one_rule_and_not_a_second_one():
    run = _run()
    [current] = _answers([run])
    [stale] = _answers([run], views={run.run_id: _view(run, keys={"co": "other"})})
    merged = merge_reports([current, replace(stale, report_id="x:y")], structure_version=VERSION)
    assert merged.stale_report_ids() == ("x:y",)


# --- could not check ----------------------------------------------------------------------------------------------


def test_a_slot_that_could_not_be_compared_is_not_stale_but_says_so():
    run = _run()
    view = _view(run, keys={"co": None})
    [answer] = _answers([run], views={run.run_id: view})
    assert not _stale(answer) and answer.stale_note == ""
    assert any("Could not check whether the structure of CO was edited since" in text for text in answer.limitations)


def test_a_slot_with_no_recorded_key_is_the_same_unverifiable_case():
    run = _run()
    keyless = replace(run, inputs=(replace(run.inputs[0], constitution_key=""), run.inputs[1]))
    [answer] = _answers([keyless])
    assert not _stale(answer)
    assert any("structure of BH3 was edited since" in text for text in answer.limitations)


# --- complete and partial -----------------------------------------------------------------------------------------


def test_a_complete_answer_adds_no_limitation_of_its_own():
    run = _run()
    assert run.status is RecipeRunStatus.COMPLETED
    [answer] = _answers([run])
    assert answer.limitations == tuple(run.result.limitations)


def test_a_partial_answer_says_it_is_partial_in_its_limitations():
    run = _run(second=carbon_monoxide(hardness=False))
    assert run.status is RecipeRunStatus.PARTIAL and run.result is not None
    [answer] = _answers([run])
    assert any(text.startswith("This answer is partial") for text in answer.limitations)
    assert answer.limitations[: len(run.result.limitations)] == tuple(run.result.limitations)


# --- it is a projection, not a copy -------------------------------------------------------------------------------


def test_the_kept_result_is_not_changed_by_projecting_it():
    run = _run()
    before = (run.result.report_id, run.result.name, run.result.molecule_uuid, run.result.structure_version)
    _answers([run], viewing="co")
    assert (run.result.report_id, run.result.name, run.result.molecule_uuid, run.result.structure_version) == before


def test_provenance_still_names_the_run_it_came_from():
    run = _run()
    [answer] = _answers([run])
    assert answer.provenance.parameters["recipe_run_id"] == run.run_id


def test_an_answer_nobody_assessed_is_refused_rather_than_read_as_current():
    with pytest.raises(KeyError):
        project_answers([_run()], viewing="bh3", assessments={}, names=NAMES, structure_version=VERSION)


def test_an_empty_assessment_is_current():
    run = _run()
    [answer] = project_answers(
        [run], viewing="bh3", assessments={run.run_id: Assessment()}, names=NAMES, structure_version=VERSION
    )
    assert not _stale(answer)
