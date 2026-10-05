"""The Windows suite retries a CRASHED shard once; what counts as a crash must stay narrow.

A crash is a fatal exception with no pytest summary line and no test reported FAILED or ERROR. The
classifier is a PowerShell script (it runs on the Windows runner), exercised here against canned logs: one that
must be retried and the cases that must NOT be retried away.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "ci_classify_crash.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="PowerShell (pwsh) is not installed here")

#: The runner's checkout path, as it appears in a crashed run's frames (raw: backslashes are literal).
CHECKOUT = r"D:\a\OpenChem-Studio\OpenChem-Studio"
PROGRESS = "." * 72 + " [ 82%]\n"
FRAMES = (
    "\nCurrent thread 0x000009b0 (most recent call first):\n"
    f'  File "{CHECKOUT}\\tests\\conftest.py", line 206 in dispose\n'
    f'  File "{CHECKOUT}\\tests\\test_result_presentation.py", line 373 in test_x\n'
    f'  File "{CHECKOUT}\\.venv\\Lib\\site-packages\\_pytest\\python.py", line 167 in call\n'
)
CRASH = PROGRESS + "Windows fatal exception: access violation\n" + FRAMES
SUMMARY_PASS = "======= slowest 30 durations =======\n6400 passed, 14 skipped in 1373.96s (0:22:53)\n"
SUMMARY_FAIL = (
    "=== short test summary info ===\nFAILED tests/test_a.py::test_b - assert 1 == 2\n"
    "2 failed, 6414 passed in 1373.96s\n"
)
TIMEOUT = PROGRESS + "##[error]The operation was canceled.\n"


def classify(tmp_path, text: str) -> list[str]:
    log = tmp_path / "attempt.log"
    log.write_text(text, encoding="utf-8")
    done = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(SCRIPT), "-Log", str(log), "-Shard", "2"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return [line for line in done.stdout.splitlines() if line.strip()]


def test_a_fatal_exception_with_no_summary_and_no_failed_test_is_a_crash(tmp_path):
    out = classify(tmp_path, CRASH)
    assert out[0] == "crashed=true"
    detail = out[1]
    assert detail.startswith("detail=shard 2 crashed at 82%")
    assert "access violation" in detail
    # The victim is named by its own frames, outside the test framework: that is the measurement.
    assert r"tests\conftest.py:206 dispose <- tests\test_result_presentation.py:373 test_x" in detail
    assert "site-packages" not in detail


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("a real failure with a summary", PROGRESS + SUMMARY_FAIL),
        ("a clean pass", PROGRESS + SUMMARY_PASS),
        ("a failure reported, then a crash at teardown", PROGRESS + "FAILED tests/test_a.py::test_b - x\n" + CRASH),
        ("a crash that still printed a summary", CRASH + SUMMARY_PASS),
        ("a timeout kill: no fatal exception to retry", TIMEOUT),
        ("an empty log", ""),
    ],
)
def test_anything_else_is_not_retried_away(tmp_path, name, text):
    assert classify(tmp_path, text) == ["crashed=false"], name


def test_a_missing_log_is_not_a_crash(tmp_path):
    done = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(SCRIPT), "-Log", str(tmp_path / "nope.log")],
        capture_output=True, text=True, timeout=120, check=True,
    )
    assert done.stdout.strip() == "crashed=false"


def test_the_workflow_wires_the_retry_and_keeps_each_attempts_budget():
    text = WORKFLOW.read_text(encoding="utf-8")
    suite = text[text.index("  suite:"): text.index("\n  gates:")]
    # Only the part this change is about: up to the step that publishes the timings. (Later steps are
    # separate, non-blocking runs with their own pytest invocations.)
    suite = suite[: suite.index("- name: Publish the Windows suite timings")]
    code ="\n".join(line for line in suite.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("ci_suite_shard.ps1") == 2 and "ci_classify_crash.ps1" in code
    assert code.count("timeout-minutes: 30") == 2  # each attempt keeps the growth gate
    assert "timeout-minutes: 65" in code  # and the job can hold both
    # The first attempt must not fail the job by itself, and the job must still go red without a retry.
    assert "continue-on-error: true" in code and "Fail the job if the suite failed and was not retried" in code
    # The pytest invocation, and so the network deselection, lives in ONE place: the shard script.
    assert "-m pytest" not in code
    assert "NetworkTest" in (ROOT / "tools" / "ci_suite_shard.ps1").read_text(encoding="utf-8")


# --- the crash that exits non-zero AFTER a clean summary (measurement only: -ExitCode) --------------------


def classify_with_exit(tmp_path, text: str, exit_code: int) -> list[str]:
    log = tmp_path / "attempt.log"
    log.write_text(text, encoding="utf-8")
    done = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(SCRIPT), "-Log", str(log), "-Shard", "1", "-ExitCode", str(exit_code)],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return [line for line in done.stdout.splitlines() if line.strip()]


def test_a_clean_summary_with_a_nonzero_exit_is_a_crash_at_exit(tmp_path):
    """Measured on windows-crash-rate run 37356155136, leg 5: '6535 passed ... in 1322.04s', exit 1, and no
    fatal-exception text. Filed as an ordinary failure, it made the crash rate read low."""
    out = classify_with_exit(tmp_path, PROGRESS + SUMMARY_PASS, 1)
    assert out[0] == "crashed=true"
    assert "exited with code 1 after a clean pytest summary" in out[1]
    assert "6400 passed" in out[1]


@pytest.mark.parametrize(
    ("name", "text", "exit_code"),
    [
        ("a clean pass with a clean exit", PROGRESS + SUMMARY_PASS, 0),
        ("a real failure, which exits non-zero by design", PROGRESS + SUMMARY_FAIL, 1),
        ("an error-only summary", PROGRESS + "FAILED tests/test_a.py::t - x\n" + "1 error, 6400 passed in 9.00s\n", 1),
        ("a failed test reported, clean-looking count line", PROGRESS + "FAILED tests/test_a.py::t - x\n" + SUMMARY_PASS, 1),
        ("a timeout kill: no summary at all", TIMEOUT, 1),
    ],
)
def test_a_nonzero_exit_is_a_crash_only_after_a_clean_summary(tmp_path, name, text, exit_code):
    assert classify_with_exit(tmp_path, text, exit_code) == ["crashed=false"], name


def test_without_an_exit_code_the_ci_retry_classifier_is_unchanged(tmp_path):
    """tests.yml does not pass -ExitCode, so what CI retries must stay exactly the narrow fatal-exception shape."""
    assert classify(tmp_path, PROGRESS + SUMMARY_PASS) == ["crashed=false"]
