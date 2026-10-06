"""Guards for the Windows crash-rate measurement (`tools/crash_rate.py`, `windows-crash-rate.yml`).

The statistics are checked against values worked out independently (Fisher's exact on 2x2 tables whose
p-values are textbook, Wilson on the standard 0/10 case), because a wrong interval here would read as a
result: the whole point of the instrument is to say whether a change to the crash did anything.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _tool():
    if "_crash_rate" in sys.modules:
        return sys.modules["_crash_rate"]
    spec = importlib.util.spec_from_file_location("_crash_rate", REPO / "tools" / "crash_rate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_crash_rate"] = module
    spec.loader.exec_module(module)
    return module


def test_a_crash_is_not_a_test_failure_and_wins_over_the_exit_code():
    tool = _tool()
    assert tool.leg_outcome(crashed=True, exit_code=1) == "crashed"
    assert tool.leg_outcome(crashed=True, exit_code=0) == "crashed"
    assert tool.leg_outcome(crashed=False, exit_code=1) == "failed"
    assert tool.leg_outcome(crashed=False, exit_code=0) == "passed"


def test_wilson_matches_the_textbook_values():
    tool = _tool()
    low, high = tool.wilson(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    low, high = tool.wilson(5, 10)
    assert (low, high) == (pytest.approx(0.2366, abs=1e-3), pytest.approx(0.7634, abs=1e-3))
    assert tool.wilson(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("a", "an", "b", "bn", "expected"),
    [
        (8, 10, 2, 10, 0.02301),  # the classic [[8,2],[2,8]] table
        (5, 10, 5, 10, 1.0),
        (10, 10, 0, 10, 1.083e-5),  # as extreme as 10 legs allow: 2 / C(20,10)
        (0, 10, 0, 10, 1.0),
    ],
)
def test_fisher_exact_matches_worked_values(a, an, b, bn, expected):
    assert _tool().fisher_exact(a, an, b, bn) == pytest.approx(expected, rel=2e-3)


def test_fisher_is_symmetric_and_a_probability():
    tool = _tool()
    for a, b in [(3, 7), (7, 3), (0, 4), (10, 1)]:
        p = tool.fisher_exact(a, 10, b, 10)
        assert 0.0 < p <= 1.0
        assert p == pytest.approx(tool.fisher_exact(b, 10, a, 10))


def _write_leg(directory: Path, arm: str, replica: int, outcome: str, detail: str = "") -> None:
    (directory / f"{arm}-{replica}.json").write_text(
        json.dumps({"arm": arm, "replica": str(replica), "outcome": outcome, "detail": detail}), encoding="utf-8"
    )


def test_the_report_counts_per_arm_and_compares_two_arms(tmp_path):
    tool = _tool()
    for i in range(10):
        _write_leg(tmp_path, "as-is", i, "crashed" if i < 2 else "passed", "shard 1 crashed at 5%")
        _write_leg(tmp_path, "reverted", i, "crashed" if i < 8 else "passed")
    text = tool.render(tool.summarise(tool.load_legs(tmp_path)), None, tool.load_legs(tmp_path))
    assert "| as-is | 10 | 2 | 0 | 8 | 20% |" in text
    assert "| reverted | 10 | 8 | 0 | 2 | 80% |" in text
    assert "Fisher's exact p = 0.023" in text
    assert "Do not extend the run" in text
    assert "as-is #0: shard 1 crashed at 5%" in text


def test_a_leg_that_never_reported_is_missing_not_a_pass(tmp_path):
    tool = _tool()
    for i in range(3):
        _write_leg(tmp_path, "as-is", i, "passed")
    legs = tool.load_legs(tmp_path)
    text = tool.render(tool.summarise(legs), {"as-is": 10, "reverted": 10}, legs)
    assert "| as-is | 3 | 0 | 0 | 3 | 0% | 0% to 56% | 7 |" in text
    assert "| reverted | 0 | 0 | 0 | 0 | no data | n/a | 10 |" in text
    assert "Fisher" not in text, "an arm with no data must not be compared"


def test_failed_legs_are_reported_but_are_not_crashes(tmp_path):
    tool = _tool()
    _write_leg(tmp_path, "as-is", 1, "failed")
    _write_leg(tmp_path, "as-is", 2, "crashed")
    (summary,) = tool.summarise(tool.load_legs(tmp_path))
    assert (summary.crashed, summary.failed, summary.passed, summary.n) == (1, 1, 0, 2)
    assert summary.rate == 0.5


def test_unrelated_json_in_the_directory_is_ignored(tmp_path):
    tool = _tool()
    (tmp_path / "other.json").write_text(json.dumps({"hello": 1}), encoding="utf-8")
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    assert tool.load_legs(tmp_path) == []


def test_the_leg_command_writes_what_the_report_reads(tmp_path):
    tool = _tool()
    out = tmp_path / "leg.json"
    tool.main(["leg", "--arm", "as-is", "--replica", "3", "--exit-code", "1", "--crashed", "true",
               "--seconds", "840.04", "--detail", "shard 1 crashed at 5%", "--out", str(out)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["outcome"] == "crashed" and data["arm"] == "as-is" and data["seconds"] == 840.0
    assert tool.load_legs(tmp_path) == [data]


# --- the workflow's shape (text checks: PyYAML is not a dependency of this project) ----------------------


def _workflow() -> str:
    return (REPO / ".github" / "workflows" / "windows-crash-rate.yml").read_text(encoding="utf-8")


def _code(text: str) -> str:
    """The workflow without its comment lines, so a check for a forbidden word does not match the comment
    explaining why it is forbidden."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_workflow_runs_only_when_asked_for():
    """It spends N Windows legs; a push or PR trigger would spend them on every commit."""
    code = _code(_workflow())
    assert "workflow_dispatch:" in code
    for trigger in ("push:", "pull_request:", "schedule:", "pull_request_target:"):
        assert trigger not in code


def test_every_leg_is_a_single_attempt_that_cannot_be_retried_or_cancelled_by_a_sibling():
    code = _code(_workflow())
    assert "fail-fast: false" in code, "a crash in one leg must not cancel the others"
    # Two call sites (with and without -Files), both inside the one attempt loop: no retry step exists.
    assert code.count("ci_suite_shard.ps1") == 2, "a retry would hide the event being counted"
    assert "retry" not in code.lower()
    assert "exit 0" in code, "the leg must always record its outcome"


def test_the_control_arm_reverts_commits_rather_than_checking_out_another_ref():
    """Two refs differ in which test files exist; a revert on the same tree differs only by the change."""
    code = _code(_workflow())
    assert "if: matrix.arm == 'reverted'" in code
    assert "git revert --no-commit" in code


def test_the_report_runs_even_when_legs_were_cancelled():
    code = _code(_workflow())
    report = code[code.index("  report:"):]
    assert "if: always()" in report


def test_the_leg_hands_the_exit_code_to_the_classifier():
    """Without it a crash at exit (clean summary, non-zero exit) is filed as a test failure and the rate reads low."""
    assert "-ExitCode $code" in _code(_workflow())


def test_a_revert_conflict_in_prose_is_resolved_and_one_in_code_stops_the_leg():
    """The first run's whole control arm failed on a docs conflict: the fix's own ARCHITECTURE entry had been
    edited since. Prose keeps the current text; anything that runs must not be silently half-reverted."""
    code = _code(_workflow())
    assert "git checkout --ours" in code
    # An ALLOW-list of prose, not a deny-list of code directories: an unlisted conflict must stop the leg.
    assert "docs/|CHANGELOG" in code and "tests/test_docs_are_current" in code
    assert "-notmatch $prose" in code
    assert "conflicts in code" in code


def test_the_bisect_inputs_exist_and_cannot_be_combined_with_a_revert_arm():
    code = _code(_workflow())
    assert "ranges:" in code and "attempts:" in code
    assert "ranges and revert are different experiments" in code
    assert "attempts > 1 is for ranges" in code, "a whole-shard attempt is ~25 minutes; many per leg would time out"


def test_each_attempt_is_a_fresh_process_with_no_retry_and_its_own_leg_file():
    code = _code(_workflow())
    assert code.count("ci_suite_shard.ps1") == 2, "one call with -Files, one without, both inside the attempt loop"
    assert 'leg-$n.json' in code and "path: leg-*.json" in code
    assert "-ExitCode $code" in code


def test_artifact_names_cannot_contain_the_arm_label():
    """An arm label like 'files 0:28' holds a colon, which artifact names reject: every upload of the first
    bisect run failed on it, and the legs' results survived only in the step logs."""
    code = _code(_workflow())
    for line in code.splitlines():
        if line.strip().startswith(("name: crash-leg-", "name: crash-log-")):
            assert "matrix.arm" not in line and "strategy.job-index" in line, line


def test_the_job_name_survives_yaml_comment_parsing():
    """` #` in an unquoted scalar starts a comment: the replica vanished from the job name, the three legs of
    an arm became indistinguishable, and `gh run view --log` printed one leg's log three times."""
    code = _code(_workflow())
    assert 'name: "${{ matrix.arm }} / leg ${{ matrix.replica }}"' in code


def test_treatment_mode_exists_and_is_exclusive_with_the_other_experiments():
    code = _code(_workflow())
    assert "treatments:" in code and "TREATMENTS:" in code
    assert "treatments, ranges and revert are different experiments" in code
    assert "treatment labels must be unique" in code
    assert "treatment env must map strings to strings" in code


def test_a_treatments_environment_is_applied_inside_the_leg_not_the_runner_job():
    """Set-Item Env: inside the step's own pwsh process: it reaches every attempt's pytest of this leg and
    nothing else (each leg is its own runner)."""
    code = _code(_workflow())
    assert "TREATMENT_ENV: ${{ matrix.env }}" in code
    assert "ConvertFrom-Json" in code and 'Set-Item -Path "Env:' in code


def test_native_crash_dumps_are_opt_in_per_arm_and_uploaded():
    code = _code(_workflow())
    assert "OPENCHEM_CAPTURE_DUMPS -eq '1'" in code, "dumps must be opt-in: they are large and need a registry write"
    assert "Windows Error Reporting" in code and "LocalDumps" in code
    assert "name: crash-dumps-${{ strategy.job-index }}" in code and "path: dumps/" in code
