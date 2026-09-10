"""What a launcher may say about a calculator, and in which order.

**EVERY TEST HERE IS ABOUT A PAIR THIS APPLICATION CAN BE IN AT ONCE.** A
status is one glyph, so where two are true the order decides which is
shown -- and each of those orderings is a decision that reads as arbitrary
until it is wrong in front of somebody.
"""

from __future__ import annotations

import pytest

from openchem.domain.common import CacheState
from openchem.domain.report import ReportResult
from openchem.domain.result_status import (
    FAILED,
    INAPPLICABLE,
    NOT_RUN,
    READY,
    RESULT_STATUSES,
    RUNNING,
    STALE,
    status_of,
)


def _result(**kwargs) -> ReportResult:
    fields = dict(
        molecule_uuid="mol-1",
        report_id="r",
        name="R",
        facts=(),
        structure_version=1,
    )
    fields.update(kwargs)
    return ReportResult(**fields)


def test_nothing_asked_is_not_run():
    assert status_of(None) == NOT_RUN


def test_a_run_in_flight_beats_whatever_came_before():
    """**A PREVIOUS ANSWER IS ABOUT TO BE REPLACED.** Reporting it while a
    re-run is in flight invites somebody to read a value that is being
    recomputed, which is worse than saying nothing about it yet."""
    ready = _result()
    assert status_of(ready, structure_version=1) == READY
    assert status_of(ready, running=True, structure_version=1) == RUNNING
    # And with nothing to report at all.
    assert status_of(None, running=True) == RUNNING


def test_an_inapplicable_result_is_not_a_failure_even_though_it_carries_one():
    """**THE ORDERING THAT MATTERS MOST, AND THIS PROJECT HAS SHIPPED IT
    WRONG.** A refusal travels AS a FAILED cache state -- that is how the
    reason reaches the reader -- so testing FAILED first paints every
    correct, permanent refusal as a fault. Joback has no group for a ring
    tertiary amine and Kamlet-Jacobs needs a measured loading density; both
    were reported as "some calculator failures" when neither had failed.
    """
    refusal = _result(cache_state=CacheState.FAILED, inapplicable=True, error="no group")
    assert refusal.cache_state is CacheState.FAILED, "setup: the refusal carries one"
    assert status_of(refusal, structure_version=1) == INAPPLICABLE


def test_a_plain_failure_is_a_failure():
    """The narrow half. "Anything FAILED is inapplicable" satisfies the test
    above and silently stops reporting real faults."""
    broke = _result(cache_state=CacheState.FAILED, error="boom")
    assert status_of(broke, structure_version=1) == FAILED


def test_a_stale_failure_reports_the_failure():
    """Both are true and one glyph fits. "It did not run" is the more
    actionable, and re-running answers either."""
    broke = _result(cache_state=CacheState.FAILED, error="boom", structure_version=1)
    assert status_of(broke, structure_version=7) == FAILED


def test_a_result_computed_for_an_older_structure_is_stale():
    assert status_of(_result(structure_version=1), structure_version=7) == STALE


def test_a_calculator_that_ran_and_found_NOTHING_is_ready():
    """**THE CASE THE PLAN NAMES, AND THE ONE A READER-DERIVED STATUS GETS
    WRONG.** Asking "does this report have facts?" is the tempting
    shortcut, and a successful calculator with nothing to say -- a clean
    catalogue, an empty structure set -- would be painted as broken. The
    request succeeded; that is the whole claim READY makes.
    """
    empty = _result(facts=())
    assert not empty.facts, "setup: nothing was produced"
    assert status_of(empty, structure_version=1) == READY


@pytest.mark.parametrize(
    "result,running,version",
    [
        (None, False, 0),
        (None, True, 0),
        (_result(), False, 1),
        (_result(structure_version=1), False, 9),
        (_result(cache_state=CacheState.FAILED, error="x"), False, 1),
        (_result(cache_state=CacheState.FAILED, inapplicable=True), False, 1),
    ],
)
def test_every_answer_is_in_the_closed_vocabulary(result, running, version):
    """Total over the states, so a consumer mapping them to glyphs can be
    total too -- a status absent from the vocabulary would render as a
    `KeyError` in a paint path rather than as a new kind of outcome."""
    assert status_of(result, running=running, structure_version=version) in RESULT_STATUSES


def test_the_vocabulary_has_no_duplicates_and_no_gaps():
    """A change detector on the closed set, in the shape `RESULT_KINDS` and
    `VISUALIZATION_KINDS` already use."""
    assert len(set(RESULT_STATUSES)) == len(RESULT_STATUSES)
    assert set(RESULT_STATUSES) == {NOT_RUN, RUNNING, READY, STALE, FAILED, INAPPLICABLE}
