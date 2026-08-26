"""The one CI rule that has a security consequence, enforced rather than documented.

A self-hosted runner executes workflow steps on somebody's own machine with
no sandbox, as whatever user started it. This repository is PUBLIC, so the
only thing standing between that machine and the internet is WHICH EVENTS
can send it a job:

    workflow_dispatch / schedule   run the workflow file from the DEFAULT
                                   BRANCH, and a fork cannot fire them
    pull_request                   a fork's PR brings its OWN workflow file

So adding a `pull_request` trigger to a self-hosted workflow -- or adding a
self-hosted runner to a workflow that already has one -- hands arbitrary
code execution on that machine to anybody with a GitHub account. Both
directions are one plausible-looking line, which is exactly why this is a
test and not a paragraph in a doc. See docs/SELF_HOSTED_RUNNER.md.

DELIBERATELY NOT A YAML PARSE. Two reasons, both practical. `pyyaml` is not
a dependency of this project and adding one to check five lines of text is a
poor trade. More importantly the dangerous property here is textual -- the
token must not appear at all -- and a parser would only see the file it was
pointed at, whereas the cross-file check below is the one that catches the
likelier mistake: adding `self-hosted` to the ALREADY pull_request-triggered
tests.yml, where nothing about that file would look new or suspicious.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

#: Full-line comments only. The self-hosted workflow's banner explains the
#: rule at length and necessarily uses both tokens, so a blanket substring
#: search over the raw file would fail on its own documentation.
_COMMENT = re.compile(r"^\s*#")


def _uncommented(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not _COMMENT.match(line))


def _workflows() -> list[Path]:
    found = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert found, f"no workflows found under {WORKFLOWS} -- has the path moved?"
    return found


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_self_hosted_workflows_are_never_triggered_by_pull_request(path: Path) -> None:
    """A workflow may be self-hosted OR pull_request-triggered, never both."""
    body = _uncommented(path)
    if "self-hosted" not in body:
        return

    assert "pull_request" not in body, (
        f"{path.name} runs on a self-hosted runner AND has a pull_request "
        "trigger. On a public repository that gives anybody with a GitHub "
        "account code execution on the runner machine, because a fork's PR "
        "supplies its own workflow file. Use workflow_dispatch or schedule, "
        "which run from the default branch. See docs/SELF_HOSTED_RUNNER.md."
    )


def test_the_self_hosted_workflow_still_exists_and_is_still_self_hosted() -> None:
    """Guards the test above against passing vacuously.

    Every assertion here is skipped for a workflow with no `self-hosted` in
    it, so a rename or a deletion would turn the whole file green while
    checking nothing. This is the canary.
    """
    path = WORKFLOWS / "benchmarks-selfhosted.yml"
    assert path.is_file(), (
        "benchmarks-selfhosted.yml is gone or renamed. If that is deliberate, "
        "update this test; the parametrized check above passes vacuously "
        "without a self-hosted workflow to check."
    )
    assert "self-hosted" in _uncommented(path)


def test_the_self_hosted_workflow_refuses_to_run_on_a_fork() -> None:
    """Belt and braces alongside the trigger rule, and cheap to keep honest.

    A fork that copies the workflow file cannot fire it by pull_request, but
    a fork owner who registers their own runner could dispatch it. The
    repository guard means the job refuses rather than running our steps
    against their checkout.
    """
    body = _uncommented(WORKFLOWS / "benchmarks-selfhosted.yml")
    assert "github.repository == 'xaerogonzo/OpenChem-Studio'" in body


# --- the shell a Windows runner hands a bash script to ---------------------
#
# Not a security rule like the ones above, but the same shape: one plausible
# line, and a failure that reads as something else entirely.
#
# GitHub's default shell for `run:` is `bash` on Linux and **`pwsh` on
# Windows**. `benchmarks-selfhosted.yml` runs on Windows and its steps are
# written in bash, so without an explicit declaration PowerShell is handed a
# bash script. Measured on the runner machine:
#
#     [ ! -d tdc_data ]     ParserError: Missing type name after '['
#     <<ROWS heredoc        ParserError
#     case / esac           ParserError
#
# A PowerShell PARSE error kills the WHOLE step before its first line runs,
# so the step fails having done nothing and the failure reads as a broken
# benchmark rather than a wrong shell.
#
# THE ONE THAT SURVIVED IS WHY THIS IS A TEST. `mkdir -p bench-out` shipped
# in the docking step long before anyone noticed, because PowerShell resolves
# `-p` as a prefix of `-Path` -- so it silently means something else, and
# errors only on a re-run when the directory already exists.

#: Constructs that PARSE in bash and do not in PowerShell. Deliberately
#: distinctive: `fi` and `[` alone appear in ordinary YAML and prose.
_BASH_ONLY = ("[ -", "[ !", "<<", "esac", "; do", "; then", '2>&1 | tee')

_WINDOWS_RUNNER = re.compile(r"^\s*runs-on:.*windows", re.M | re.I)

#: A job key: exactly two spaces of indent, under `jobs:`.
_JOB_KEY = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$", re.M)


def _jobs(body: str) -> list[tuple[str, str]]:
    """`(name, text)` per job. PER JOB IS THE WHOLE POINT of this split.

    `tests.yml` has a windows-latest job and an ubuntu-latest one, and the
    bash lives in the LINUX job's fingerprint. Checked over the whole file
    the two look like one Windows job full of bash, and this guard's first
    run said exactly that -- a false positive that would have demanded
    `shell: bash` on a file whose Windows steps are all single plain
    commands that run in any shell.
    """
    starts = [(m.start(), m.group(1)) for m in _JOB_KEY.finditer(body)]
    bounds = [s for s, _ in starts] + [len(body)]
    return [(name, body[bounds[i]:bounds[i + 1]]) for i, (_, name) in enumerate(starts)]


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_a_windows_job_running_bash_declares_that_it_is_bash(path: Path) -> None:
    """Windows defaults to `pwsh`, so bash steps must say so explicitly."""
    body = _uncommented(path)
    offenders = []
    for name, job in _jobs(body):
        if not _WINDOWS_RUNNER.search(job):
            continue
        used = [token for token in _BASH_ONLY if token in job]
        if used and "shell: bash" not in job:
            offenders.append((name, used))
    if not offenders:
        return
    used = sorted({token for _n, tokens in offenders for token in tokens})
    raise AssertionError(
        f"{path.name}: job(s) {[n for n, _ in offenders]} run on Windows and "
        f"use bash-only syntax ({', '.join(used)}) without declaring "
        "`shell: bash`. GitHub hands those steps to PowerShell, where they "
        "are a PARSE error -- the whole step dies before its first line runs."
    )


def test_the_self_hosted_workflow_really_is_written_in_bash() -> None:
    """ASSERTS THE SETUP of the guard above, which is otherwise vacuous.

    That test returns early for any workflow with no bash-only syntax in it,
    so it passes whether or not the rule is doing anything. If the
    self-hosted workflow were ever rewritten in PowerShell -- or if these
    tokens stopped appearing for any other reason -- the guard would go
    quietly green while the requirement it encodes had changed.

    Same reason `test_a_tab_bars_scroll_buttons_are_qt_s_own` asserts the
    window really does build a `QTabWidget`.
    """
    body = _uncommented(WORKFLOWS / "benchmarks-selfhosted.yml")
    jobs = [job for _name, job in _jobs(body) if _WINDOWS_RUNNER.search(job)]
    assert jobs, "this workflow no longer has a Windows job"
    assert [token for job in jobs for token in _BASH_ONLY if token in job], (
        "no bash-only syntax left in the self-hosted workflow, so the guard "
        "above is now vacuous -- either it was rewritten, or the tokens moved"
    )
