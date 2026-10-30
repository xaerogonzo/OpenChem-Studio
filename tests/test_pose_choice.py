"""The sentence that tells a reader pose 1 is the best-scoring pose, not a verified one."""

from __future__ import annotations

import pathlib
import re

import pytest

from openchem.chem import pose_choice as pc

RESULT = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking" / "PREP_BOX_RESULT.md"


def test_a_close_pose_in_another_place_is_flagged():
    choice = pc.assess([-8.8, -8.1, -4.0], [0.0, 5.5, 6.0])
    assert choice.elsewhere == (2,)
    assert choice.same_place == ()


def test_a_close_pose_in_the_same_place_is_one_placement():
    choice = pc.assess([-8.8, -8.6, -8.5], [0.0, 0.9, 1.4])
    assert choice.same_place == (2, 3)
    assert choice.elsewhere == ()


def test_the_score_window_is_inclusive_and_a_worse_pose_is_ignored():
    # Exactly 2.85 kcal/mol worse is still inside the window, a hair beyond is not.
    assert pc.assess([-9.0, -6.15], [0.0, 5.0]).elsewhere == (2,)
    assert pc.assess([-9.0, -6.14], [0.0, 5.0]).elsewhere == ()


def test_the_rmsd_cutoff_is_the_surveys_two_angstrom():
    assert pc.assess([-9.0, -9.0], [0.0, 2.0]).same_place == (2,)
    assert pc.assess([-9.0, -9.0], [0.0, 2.01]).elsewhere == (2,)


def test_one_pose_or_none_says_nothing():
    assert pc.summarize([], []) == ""
    assert pc.summarize([-7.0], [0.0]) == ""
    assert pc.assess([-7.0], [0.0]) == pc.PoseChoice((), ())


def test_mismatched_inputs_are_refused_not_zipped():
    with pytest.raises(ValueError):
        pc.assess([-7.0, -6.0], [0.0])


def test_the_sentence_never_names_a_correct_pose_and_lists_at_most_four():
    many = pc.summarize([-9.0] * 8, [0.0] + [5.0] * 7)
    assert "poses 2, 3, 4, 5 and 3 more" in many
    assert "cannot separate them" in many
    for banned in ("confidence", "best pose is", "correct pose is", "use pose"):
        assert banned not in many


def test_each_of_the_three_cases_reads_differently():
    other = pc.summarize([-9.0, -8.9], [0.0, 4.0])
    same = pc.summarize([-9.0, -8.9], [0.0, 1.0])
    none = pc.summarize([-9.0, -2.0], [0.0, 4.0])
    assert len({other, same, none}) == 3
    assert "no other pose scores within" in none


def test_the_quoted_redocking_figures_are_the_result_documents():
    """A re-run that moves the survey must move the panel, or this fails."""
    text = RESULT.read_text(encoding="utf-8")
    top = re.search(r"\| top-ranked pose within 2\.0 A \| (\d+) \|", text)
    lower = re.search(r"but is not top-ranked \| (\d+) \|", text)
    assert top and lower
    assert int(top.group(1)) == pc.REDOCK_TOP_CORRECT
    assert int(lower.group(1)) == pc.REDOCK_RANKED_LOWER
    assert f"{pc.REDOCK_TOP_CORRECT} of {pc.REDOCK_RECEPTORS}" in text
