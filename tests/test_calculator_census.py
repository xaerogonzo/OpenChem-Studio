"""Every calculator over the census panel, through the app's own path -- and what it must not do.

The census (`tools/calculator_census.py`) draws 29 structures chosen for SHAPE
-- nitramines, energetic materials, hydrazines, ring tertiary amines, salts,
metals, a peptide, a large molecule -- and runs every registered calculator and
the always-on set over each, recording what came back AND what the application
logged while it did. A live session on one nitramine found four defects nothing
had caught; this is how the next one is a failing test on the day the calculator
is added.

**FIVE THINGS MAY NOT HAPPEN, AND THE FIRST FOUR ARE ABSOLUTE.**

    a FAULT          a result that failed and is neither a limit, a missing
                     input nor a missing setup
    an error logged  a traceback (or ERROR) in the application's own log while
                     a calculator ran, even if it still returned a number
    a PENDING cell   a calculator that never answered
    an unclassified  a refusal code nobody put in `domain.refusal_kinds`; it
    refusal code     would read as a permanent limit only by a legacy flag
    a moved cell     any result or observation that differs from the committed
                     baseline -- which is a change detector, not a verdict: the
                     fix is to look, then `tools/calculator_census.py --record`

WARNINGS are recorded and never fail: the vendored naming engine logs its own
diagnostics ("Unknown FG overlap") for structures it has no rule for, and that is
the naming track's to close, not this guard's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
import calculator_census as census_tool  # noqa: E402


@pytest.fixture(scope="module")
def census(qapp, tmp_path_factory):
    """The whole panel, with NO experimental NMR database.

    The sidecars are unconfigured here (the suite's settings are isolated), but the
    NMR database lives at a data path: a developer who had built it saw a different
    matrix from CI, and the multicomponent guard once went green locally and red on
    CI for exactly that reason (PR #133).
    """
    from openchem.chem import nmr_database

    missing = tmp_path_factory.mktemp("no-nmr-db") / "absent.sqlite"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nmr_database, "default_database_path", lambda: missing)
        return census_tool.run_census(qapp, census_tool.load_corpus())


def _describe(census, keys: list[str]) -> str:
    lines = []
    for key in keys:
        cell = census["cells"][key]
        lines.append(f"{key}: {cell['result']}/{cell['observation']} {cell['log'][:2]}")
    return "\n".join(lines)


# --- the four that may never happen ---------------------------------------------


def test_no_calculator_faults_on_any_row(census):
    found = census_tool.findings(census)["faults"]
    assert not found, "a failure that is not a limit, a missing input or a missing setup:\n" + _describe(census, found)


def test_no_calculator_logs_an_error_on_any_row(census):
    found = census_tool.findings(census)["error_logged"]
    assert not found, "the application logged an ERROR while these ran:\n" + _describe(census, found)


def test_every_calculator_answered_every_row(census):
    found = census_tool.findings(census)["pending"]
    assert not found, "no result was recorded for:\n" + "\n".join(found)


def test_no_refusal_code_is_unclassified(census):
    """A code in no kind table reads as a limit only because a producer set the
    legacy flag. Classify it in `domain/refusal_kinds.py` (or declare its kind at
    the raise): somebody decides limit, missing input or missing setup."""
    assert census_tool.findings(census)["unclassified_codes"] == []


# --- the matrix does not move silently -------------------------------------------


def test_the_matrix_matches_the_committed_baseline(census):
    baseline = json.loads(census_tool.BASELINE.read_text(encoding="utf-8"))
    moved = census_tool.diff_against(census, baseline)
    assert not moved, (
        "the census moved. Look at each cell, decide whether it is right, then run "
        "`python tools/calculator_census.py --record` and say why in the commit:\n  " + "\n  ".join(moved)
    )


def test_the_baseline_covers_every_registered_calculator_and_row(census):
    baseline = json.loads(census_tool.BASELINE.read_text(encoding="utf-8"))
    assert list(baseline["rows"]) == list(census["rows"])
    assert set(baseline["matrix"]) == set(census["columns"])
    for column, letters in baseline["matrix"].items():
        assert len(letters) == len(baseline["rows"]), column


# --- what the census says about support metadata -----------------------------------


def test_no_experimental_calculator_is_offered_by_default(census):
    """`CalculatorSupport` already refuses to construct one; the census reads the
    registry the app actually built, which is the claim that matters."""
    offered = [
        column for column, support in census["support"].items()
        if support["stage"] == "experimental" and support["visibility"] == "shown"
    ]
    assert offered == []


def test_the_census_reads_the_two_calculators_it_was_built_around(census):
    """Joback and Detonation, on the structures that started this."""
    row = {r: i for i, r in enumerate(census["rows"])}
    matrix = census_tool.baseline_form(census)["matrix"]
    joback, detonation = matrix["joback_properties"], matrix["detonation"]
    for refused in ("dinitrodiazetidine", "rdx", "hmx"):
        assert joback[row[refused]] == census_tool.LIMIT, refused
    for ran in ("tnt", "petn", "aspirin"):
        assert joback[row[ran]] == census_tool.READY, ran
    # Kamlet-Jacobs: covered and needing input, or outside its range -- never a fault.
    assert detonation[row["dinitrodiazetidine"]] == census_tool.NEEDS_INPUT
    assert detonation[row["tatb"]] == census_tool.NEEDS_INPUT
    assert detonation[row["nitroglycerin"]] == census_tool.LIMIT, "refused before asking for inputs"


# --- the control arm: the guard can fail ------------------------------------------------


def test_a_calculator_that_raises_is_a_fault_and_an_error_logged(qapp, monkeypatch):
    """**A GUARD THAT NEVER FAILED IS UNPROVEN.** One calculator is made to raise on
    the way in (through the registry, exactly where a broken compute would), and the
    census must name it in both columns."""
    from openchem.services.calculator_registry import CalculatorRegistry

    original = CalculatorRegistry.compute

    def broken(self, calculator_id, mol, molecule_uuid, parameters=None):
        if calculator_id == "oxygen_balance":
            raise RuntimeError("a calculator that raises")
        return original(self, calculator_id, mol, molecule_uuid, parameters)

    monkeypatch.setattr(CalculatorRegistry, "compute", broken)
    rows = [r for r in census_tool.load_corpus() if r.id == "aspirin"]
    result = census_tool.run_census(qapp, rows, calculator_ids=["oxygen_balance"])

    found = census_tool.findings(result)
    assert found["faults"] == ["oxygen_balance|aspirin"]
    assert found["error_logged"] == ["oxygen_balance|aspirin"]


def test_an_unclassified_code_is_reported_not_swallowed(qapp, monkeypatch):
    """A refusal a producer marks `inapplicable` with a code nobody classified reads
    as a limit -- and the census lists the code."""
    from openchem.domain.calculator import CalculationRefusal
    from openchem.services.calculator_registry import CalculatorRegistry

    original = CalculatorRegistry.compute

    def refusing(self, calculator_id, mol, molecule_uuid, parameters=None):
        if calculator_id == "oxygen_balance":
            raise CalculationRefusal("A_BRAND_NEW_CODE", "s", "d", inapplicable=True)
        return original(self, calculator_id, mol, molecule_uuid, parameters)

    monkeypatch.setattr(CalculatorRegistry, "compute", refusing)
    rows = [r for r in census_tool.load_corpus() if r.id == "aspirin"]
    result = census_tool.run_census(qapp, rows, calculator_ids=["oxygen_balance"])

    # `CalculationRefusal(inapplicable=True)` resolves to LIMIT itself, so it is not a
    # FAULT -- and its code is listed, because nothing classified it.
    found = census_tool.findings(result)
    assert found["faults"] == []
    assert result["cells"]["oxygen_balance|aspirin"]["result"] == census_tool.LIMIT
    assert found["unclassified_codes"] == ["oxygen_balance:A_BRAND_NEW_CODE"]


def test_the_classifier_reads_the_launchers_own_word():
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.refusal_kinds import RefusalKind, refusal_parameters
    from openchem.domain.report import ReportResult

    def report(kind, **extra):
        return ReportResult(
            molecule_uuid="u", report_id="r", name="R", facts=(), cache_state=CacheState.FAILED,
            provenance=Provenance(created_by="core", method="m", parameters=refusal_parameters("C", kind)),
            **extra,
        )

    assert census_tool.classify_result(report(RefusalKind.NEEDS_INPUT)) == census_tool.NEEDS_INPUT
    assert census_tool.classify_result(report(RefusalKind.NEEDS_SETUP)) == census_tool.NEEDS_SETUP
    assert census_tool.classify_result(report(RefusalKind.LIMIT)) == census_tool.LIMIT
    plain = ReportResult(molecule_uuid="u", report_id="r", name="R", facts=(), cache_state=CacheState.FAILED)
    assert census_tool.classify_result(plain) == census_tool.FAULT
    ok = ReportResult(molecule_uuid="u", report_id="r", name="R", facts=())
    assert census_tool.classify_result(ok) == census_tool.READY
