from __future__ import annotations

import time

from openchem.plugins.async_task import run_async


class _ExpectedError(Exception):
    pass


def _wait_for(qapp, predicate, iterations=200):
    for _ in range(iterations):
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_run_async_reports_success(qapp):
    results = []
    run_async(lambda: 42, _ExpectedError, results.append, lambda msg: results.append(("error", msg)))
    assert _wait_for(qapp, lambda: results)
    assert results == [42]


def test_run_async_reports_expected_error(qapp):
    results = []

    def raise_expected():
        raise _ExpectedError("bad input")

    run_async(raise_expected, _ExpectedError, results.append, lambda msg: results.append(msg))
    assert _wait_for(qapp, lambda: results)
    assert results == ["bad input"]


def test_run_async_wraps_unexpected_error(qapp):
    results = []

    def raise_unexpected():
        raise RuntimeError("boom")

    run_async(raise_unexpected, _ExpectedError, results.append, lambda msg: results.append(msg))
    assert _wait_for(qapp, lambda: results)
    assert results == ["Unexpected error: boom"]
