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
