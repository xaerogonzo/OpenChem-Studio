"""The driven run's ledger of what the application LOGGED, and its verdict.

A live session logged five identical tracebacks in forty seconds and nothing
failed: no test, no driven check, no exit code. These tests pin the two things
that make a ledger worth reading -- that one defect is ONE entry however many
times it fires, and that the driver's own progress lines are not mistaken for
the application's warnings -- and that the verdict is a real exit status.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

import openchem.app.debug_drive as debug_drive
from openchem.app import drive_ledger
from openchem.app.drive_ledger import ErrorLedger, RunIdentity


@pytest.fixture
def ledger():
    """A ledger on a private logger, so nothing else's records reach it."""
    found = ErrorLedger()
    log = logging.getLogger("openchem.test_ledger")
    log.addHandler(found)
    log.setLevel(logging.DEBUG)
    log.propagate = False
    yield found, log
    log.removeHandler(found)


def _raise_here(message: str) -> None:
    raise ValueError(message)  # the innermost frame the ledger must name


def _raise_elsewhere(message: str) -> None:
    raise ValueError(message)  # same exception, same message, a different place


def _log_failure(log: logging.Logger, raiser, message: str) -> None:
    try:
        raiser(message)
    except ValueError:
        log.exception("Alert computation failed")


def test_one_defect_that_fires_five_times_is_one_entry_with_a_count(ledger):
    """The live-session shape: the same traceback once per edit, the atom
    indices and nothing else changing between them."""
    found, log = ledger
    for edit in range(5):
        _log_failure(log, _raise_here, f"fg:hydrazine matched cationic atoms [{edit}, {edit + 6}]")
    entries = found.errors()
    assert len(entries) == 1
    assert entries[0].count == 5
    assert entries[0].exception == "ValueError"
    assert "matched cationic atoms" in entries[0].message
    assert "Traceback" in entries[0].sample


def test_the_key_is_where_it_happened_so_two_failures_with_one_first_line_stay_apart(ledger):
    """Same exception type, same message: different raise sites are different
    defects, and merging them would hide the second behind the first."""
    found, log = ledger
    _log_failure(log, _raise_here, "boom")
    _log_failure(log, _raise_elsewhere, "boom")
    origins = sorted(e.origin for e in found.errors())
    assert len(origins) == 2
    assert all(o.startswith("test_drive_ledger.py:") for o in origins)
    assert origins[0] != origins[1]


def test_a_uuid_or_a_number_in_the_message_does_not_split_an_entry(ledger):
    found, log = ledger
    for uuid_text in ("2bb3bba9-ab67-4fa8-a822-37ff0ae55ade", "11111111-2222-3333-4444-555555555555"):
        log.error("no conformers for molecule %s after %d attempts", uuid_text, len(uuid_text))
    assert len(found.errors()) == 1
    assert found.errors()[0].count == 2


def test_the_drivers_progress_warnings_are_not_the_applications(ledger):
    """The driver logs every step at WARNING so it shows on a console; counting
    those would make every ledger noise."""
    found, log = ledger
    log.warning("OPENCHEM_DRIVE: step 3 calculator")
    log.warning("OPENCHEM_DRIVE: EXPECT results ok[a]")
    assert found.entries == []
    assert found.driver_failures == []


def test_the_drivers_errors_are_failures_of_the_run_not_application_errors(ledger):
    found, log = ledger
    log.error("OPENCHEM_DRIVE: no molecule selected for 'solubility'")
    assert found.errors() == []
    assert found.driver_failures == ["no molecule selected for 'solubility'"]


def test_an_application_warning_is_kept_apart_from_an_error(ledger):
    found, log = ledger
    log.warning("The pKa predictor is not configured")
    log.error("Calculator solubility failed")
    assert [e.level for e in found.warnings()] == ["WARNING"]
    assert [e.level for e in found.errors()] == ["ERROR"]
    # an INFO record is below the handler's level and never enters the ledger
    log.info("4 distinct conformer(s) from 150 embedding(s)")
    assert len(found.entries) == 2


def test_an_allow_list_excuses_only_what_it_names(ledger):
    found, log = ledger
    log.error("sidecar missing")
    log.error("something new broke")
    left = found.unexpected(["sidecar missing"])
    assert [e.message for e in left] == ["something new broke"]
    # nothing is excused by an empty string
    assert len(found.unexpected([""])) == 2


def test_warnings_count_only_when_asked_for(ledger):
    found, log = ledger
    log.warning("degraded")
    assert found.unexpected() == []
    assert len(found.unexpected(include_warnings=True)) == 1


def test_the_ledger_is_capped_and_says_how_much_it_dropped(ledger, monkeypatch):
    found, log = ledger
    monkeypatch.setattr(drive_ledger, "MAX_ENTRIES", 3)
    for i in range(10):
        log.error("distinct failure %s", "abcdefghij"[i])
    assert len(found.errors()) == 3
    assert found.dropped == 7
    assert any("dropped" in line for line in found.summary_lines())


# --- the driver's verdict ------------------------------------------------------


@pytest.fixture
def driver(tmp_path):
    """A driver against a stand-in window, its ledger attached to the root
    logger the way `start()` does, and detached again afterwards."""
    fake_panel = SimpleNamespace(
        _status_for=lambda calculator_id: {"solubility": "inapplicable", "detonation": "ready"}.get(
            calculator_id, "not_run"
        ),
        _result_for=lambda calculator_id: SimpleNamespace(
            provenance=SimpleNamespace(parameters={"refusal": "NO_PREDICTION"}),
            facts=[SimpleNamespace(label="Nitro", display_value="3")],
        ),
    )
    window = SimpleNamespace(
        _property_panel=fake_panel,
        _session=SimpleNamespace(mark_clean=lambda: None),
        _undo_stack=SimpleNamespace(clear=lambda: None),
    )
    made = debug_drive._Driver(window, [], report_path=tmp_path / "run.report.json")
    logging.getLogger().addHandler(made._ledger)
    yield made
    logging.getLogger().removeHandler(made._ledger)


def _report(driver) -> dict:
    return json.loads(driver._report_path.read_text(encoding="utf-8"))


def test_a_clean_run_passes_and_writes_a_report(driver):
    assert driver._finish() == 0
    report = _report(driver)
    assert report["verdict"] == "PASS" and report["exit_code"] == 0
    assert report["ledger"]["errors"] == []


def test_an_application_error_fails_the_run_even_though_no_step_asked(driver):
    """The whole point: the run had no assertion about logging and still fails,
    because five tracebacks in a Console is not a passing run."""
    logging.getLogger("openchem.chemistry").error("Alert computation failed for provider rdkit")
    assert driver._finish() == 1
    report = _report(driver)
    assert report["verdict"] == "FAIL"
    assert report["ledger"]["errors"][0]["allowed"] is False


def test_an_allowed_error_does_not_fail_the_run(driver):
    driver._do_expect_clean({"allow": ["provider rdkit"]})  # nothing logged yet: passes
    logging.getLogger("openchem.chemistry").error("Alert computation failed for provider rdkit")
    assert driver._finish() == 0
    assert _report(driver)["ledger"]["errors"][0]["allowed"] is True


def test_tolerate_errors_opts_a_script_out_that_provokes_one_on_purpose(driver):
    logging.getLogger("openchem.chemistry").error("expected, on purpose")
    assert driver._finish(tolerate_errors=True) == 0
    assert _report(driver)["tolerate_errors"] is True


def test_expect_clean_fails_the_run_at_the_moment_it_is_asked(driver):
    logging.getLogger("openchem.chemistry").error("broke")
    driver._do_expect_clean({"tag": "after-draw"})
    assert driver._assertions[-1]["ok"] is False
    assert driver._finish() == 1
    assert any(a["tag"] == "after-draw" and not a["ok"] for a in _report(driver)["assertions"])


def test_a_driver_failure_fails_the_run(driver):
    """`no molecule selected` and `EXPECT ... FAILED` were only ever log lines."""
    logging.getLogger("openchem.ui").error("OPENCHEM_DRIVE: no molecule selected for 'solubility'")
    assert driver._finish() == 1
    assert _report(driver)["ledger"]["driver_failures"]


def test_a_step_that_raises_is_a_failure_of_the_run(qapp, tmp_path):
    """A step that raised used to be one log line and an exit code of 0. Needs
    a real window: `_run_next` schedules the next step against it."""
    import conftest
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    try:
        made = debug_drive._Driver(
            window, [{"do": "expand", "section": "admet", "after_ms": 60_000}],
            report_path=tmp_path / "raised.report.json",
        )
        logging.getLogger().addHandler(made._ledger)
        try:
            made._run_next()  # `expand` needs a property panel this bare window lacks
            assert made._finish() == 1
        finally:
            logging.getLogger().removeHandler(made._ledger)
        assert made._ledger.driver_failures, "the exception was not recorded as a driver failure"
    finally:
        conftest.dispose(window)


def test_expect_results_asserts_what_the_panel_holds(driver):
    driver._do_expect_results({"expect": {
        "solubility": {"status": ["inapplicable"], "refusal": "NO_PREDICTION"},
        "detonation": "ready",
        "fragment_counts": {"facts_contain": ["Nitro"], "facts_absent": ["Hydrazine"]},
    }, "tag": "nitramine"})
    assert driver._assertions[-1]["ok"], driver._assertions[-1]["detail"]


@pytest.mark.parametrize(
    "expect,needle",
    [
        ({"solubility": "failed"}, "status 'inapplicable', wanted ['failed']"),
        ({"solubility": {"not_status": ["inapplicable"]}}, "ruled out"),
        ({"solubility": {"refusal": ""}}, "refusal 'NO_PREDICTION', wanted ''"),
        ({"fragment_counts": {"facts_contain": ["Hydrazine"]}}, "no fact contains 'Hydrazine'"),
        ({"fragment_counts": {"facts_absent": ["Nitro"]}}, "a fact contains 'Nitro'"),
    ],
)
def test_expect_results_names_what_did_not_match(driver, expect, needle):
    driver._do_expect_results({"expect": expect})
    last = driver._assertions[-1]
    assert not last["ok"]
    assert needle in last["detail"]


def test_a_calculator_still_running_is_named_as_such_not_as_a_failure(driver):
    driver._window._property_panel._status_for = lambda calculator_id: "running"
    driver._do_expect_results({"expect": {"solubility": "ready"}})
    assert "still running" in driver._assertions[-1]["detail"]


def test_quit_exits_with_the_verdict(driver, monkeypatch):
    from PySide6.QtWidgets import QApplication

    codes: list[int] = []
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: SimpleNamespace(exit=codes.append)))
    logging.getLogger("openchem.chemistry").error("broke")
    driver._do_quit({})
    assert codes == [1]


def test_quit_can_excuse_an_error_by_name(driver, monkeypatch):
    from PySide6.QtWidgets import QApplication

    codes: list[int] = []
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: SimpleNamespace(exit=codes.append)))
    logging.getLogger("openchem.chemistry").error("known sidecar problem")
    driver._do_quit({"allow": ["known sidecar problem"]})
    assert codes == [0]


def test_the_verdict_is_reached_once_and_detaches_the_ledger(driver):
    assert driver._finish() == 0
    logging.getLogger("openchem.chemistry").error("after the verdict")
    assert driver._finish() == 0  # idempotent: what was logged after it is not counted
    assert driver._ledger not in logging.getLogger().handlers


def test_a_driver_built_in_a_test_attaches_nothing_to_the_process_logging(tmp_path):
    before = list(logging.getLogger().handlers)
    debug_drive._Driver(SimpleNamespace(), [], report_path=tmp_path / "x.json")
    assert logging.getLogger().handlers == before


# --- which run this was ---------------------------------------------------------


def test_a_run_says_which_script_which_build_and_which_stack(tmp_path):
    script = tmp_path / "s.json"
    script.write_text("[]", encoding="utf-8")
    identity = RunIdentity.capture(script).to_dict()
    assert len(identity["run_id"]) == 32
    assert len(identity["script_sha256"]) == 64
    assert identity["versions"]["python"] and identity["versions"]["rdkit"]
    assert len(identity["commit"]) == 40  # this test runs in a checkout
    assert identity["log_start"] >= 0
    # two runs are never the same run
    assert RunIdentity.capture(script).run_id != identity["run_id"]
