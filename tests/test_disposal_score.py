"""The disposal A/B's scorer, and the refusals that make its n honest.

`benchmarks/disposal/score.py` turns each CI leg into one Bernoulli trial
and assembles the 2x2. It is guarded because the thing it decides -- "is
this an n=10 experiment or not" -- is exactly the claim a scorer can get
wrong while looking like it worked, and because a benchmark that runs
twice a year is a benchmark nobody notices rotting.

The preregistration it serves is `benchmarks/disposal/README.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCORER = Path(__file__).resolve().parent.parent / "benchmarks" / "disposal"
if str(_SCORER) not in sys.path:
    sys.path.insert(0, str(_SCORER))

from score import (  # noqa: E402
    fisher_exact_two_sided,
    leg_record,
    odds_ratio,
    score,
    wilson,
)

_CLEAN = (
    "# census pid=1\n"
    "BEGIN tests/a.py::t1 pid=1\n"
    "  end tests/a.py::t1 built=1 destroyed=1 late=0 alive=0\n"
    "# session finished\n"
)
_CRASHED = (
    "# census pid=1\n"
    "BEGIN tests/a.py::t1 pid=1\n"
    "  end tests/a.py::t1 built=1 destroyed=1 late=0 alive=0\n"
    "BEGIN tests/b.py::t2 pid=1\n"
)
_SUMMARY = "==== 10 passed, 1 skipped in 3.00s ====\n"


def _leg(arm, replica, crashed, ran=True):
    return {
        "arm": arm,
        "replica": str(replica),
        "crashed": crashed,
        "ran": ran,
        "victim": "tests/x.py::t" if crashed else None,
    }


def _full_matrix(control_crashes=5, treatment_crashes=0, n=10):
    return [
        _leg("control", i, i <= control_crashes) for i in range(1, n + 1)
    ] + [_leg("treatment", i, i <= treatment_crashes) for i in range(1, n + 1)]


_EXPECT = {"control": list(range(1, 11)), "treatment": list(range(1, 11))}


# --------------------------------------------------------------------------
# One leg is one trial, and "could not tell" is a THIRD state
# --------------------------------------------------------------------------


def test_a_finished_session_is_not_a_crash():
    record = leg_record(_CLEAN, _SUMMARY, "control", "1")
    assert record["crashed"] is False
    assert record["ran"] is True
    assert record["victim"] is None


def test_a_missing_sentinel_is_a_crash_and_names_its_victim():
    record = leg_record(_CRASHED, "", "control", "2")
    assert record["crashed"] is True
    assert record["victim"] == "tests/b.py::t2"


def test_an_unreadable_trail_with_a_summary_is_a_COMPLETION():
    """Two witnesses, and either one settles it.

    A leg whose census never got written but whose pytest summary is
    right there did reach the end. Scoring it as a crash because the
    sentinel is absent would be `Census.usable` ignored -- the mistake
    that class's own docstring warns about, in the direction that
    manufactures crashes rather than hiding them.
    """
    record = leg_record("", _SUMMARY, "control", "3")
    assert record["crashed"] is False
    assert record["ran"] is True


def test_a_leg_with_NEITHER_witness_is_not_a_completion():
    """The load-bearing narrow half.

    "No trail" defaulting to "finished" is how a runner that died before
    pytest started becomes a data point saying the treatment worked.
    """
    record = leg_record("", "", "control", "4")
    assert record["crashed"] is None
    assert record["ran"] is False


# --------------------------------------------------------------------------
# The refusals -- an arm that does not run is not an arm
# --------------------------------------------------------------------------


def test_a_complete_matrix_is_scored():
    result = score(_full_matrix(), _EXPECT)
    assert result["refused"] is False
    assert result["table"] == {"control": [5, 5], "treatment": [0, 10]}


def test_a_missing_replica_is_REFUSED_rather_than_scored_as_nine():
    legs = [
        leg
        for leg in _full_matrix()
        if not (leg["arm"] == "treatment" and leg["replica"] == "7")
    ]
    result = score(legs, _EXPECT)
    assert result["refused"] is True
    assert any("MISSING ['7']" in problem for problem in result["problems"])


def test_a_leg_that_ran_nothing_is_REFUSED():
    legs = [dict(leg) for leg in _full_matrix()]
    legs[3]["ran"] = False
    legs[3]["crashed"] = None
    result = score(legs, _EXPECT)
    assert result["refused"] is True
    assert any("ran nothing" in problem for problem in result["problems"])


def test_an_unexpected_replica_is_refused_too():
    """The other direction, which a missing-only check would pass.

    A dispatch that quietly ran more legs than were registered is not the
    experiment either -- and it is how a second wave gets folded into a
    first one's numbers without anybody deciding to.
    """
    legs = _full_matrix() + [_leg("treatment", 11, False)]
    result = score(legs, _EXPECT)
    assert result["refused"] is True
    assert any("UNEXPECTED ['11']" in problem for problem in result["problems"])


# --------------------------------------------------------------------------
# The statistics, against answers computed elsewhere
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table, expected",
    [
        ((5, 5, 0, 10), 0.0325),  # near-total elimination: the only n=10 win
        ((5, 5, 1, 9), 0.1409),  # a real but partial effect: NOT detectable
        ((5, 5, 5, 5), 1.0000),  # the null
        ((10, 10, 2, 18), 0.0138),  # what n=20 buys
    ],
)
def test_the_fisher_values_are_the_ones_the_preregistration_quotes(table, expected):
    """`README.md`'s power table is not decoration -- it is this function.

    Those figures were written into the preregistration BEFORE this
    implementation existed, from an independent calculation. Two routes
    agreeing is what makes a hand-rolled statistic checkable; scipy is
    not a dependency of this project, so there is no third.
    """
    assert fisher_exact_two_sided(*table) == pytest.approx(expected, abs=5e-5)


def test_the_odds_ratio_is_UNDEFINED_on_a_zero_cell_rather_than_invented():
    """The zero cell is the expected SUCCESS case, not an edge case.

    Total elimination in the treatment arm is precisely the outcome this
    experiment is powered for, and it makes the odds ratio infinite.
    Returning a finite number there means a continuity correction has
    been applied silently -- a value the data does not carry.
    """
    assert odds_ratio(5, 5, 0, 10) is None
    assert odds_ratio(5, 5, 1, 9) == pytest.approx(9.0)


def test_the_interval_for_zero_out_of_ten_is_not_degenerate():
    """Wilson, not the normal approximation.

    The normal interval for 0/10 is [0, 0], which asserts the crash rate
    is known EXACTLY to be zero from ten runs of a 50/50 process. That is
    the claim this whole experiment exists to avoid making.
    """
    low, high = wilson(0, 10)
    assert low == 0.0
    assert 0.2 < high < 0.35


def test_the_verdict_threshold_is_the_preregistered_one():
    """0.05, and it is not renegotiated by having seen a number.

    Asserted on both sides of the line so a widened threshold fails here
    rather than quietly turning an insufficient result into a finding.
    """
    assert score(_full_matrix(5, 0), _EXPECT)["fisher_p"] < 0.05
    assert score(_full_matrix(5, 1), _EXPECT)["fisher_p"] > 0.05
