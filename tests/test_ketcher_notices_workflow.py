"""The one workflow with a write token that runs on a PR, held to the properties that make that safe.

`ketcher-notices.yml` is `pull_request_target`: it runs the BASE branch's workflow with a token that
can push, in a PUBLIC repository. That is safe only while it never executes anything the PR supplies,
which is a property of a handful of lines and would be lost by a plausible-looking edit (a build step,
an inline `${{ ... head.ref }}`). So the properties are tests, in the textual style of
`test_workflow_safety.py` and for the same reason: a YAML parse is not a dependency of this project.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
NOTICES = WORKFLOWS / "ketcher-notices.yml"


def _body(path: Path) -> str:
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not re.match(r"^\s*#", line))


def test_no_other_workflow_uses_pull_request_target():
    others = [p.name for p in sorted(WORKFLOWS.glob("*.y*ml")) if p != NOTICES and "pull_request_target" in _body(p)]
    assert not others, f"a write-token PR trigger needs this file's safety properties: {others}"


def test_the_notices_workflow_runs_nothing_from_the_pr():
    body = _body(NOTICES)
    assert "pull_request_target" in body
    # Dependencies install without lifecycle scripts: no package can run code during the install.
    assert "npm ci --ignore-scripts" in body
    # Only Dependabot's own PRs, from a branch in this repository.
    assert "pull_request.user.login == 'dependabot[bot]'" in body
    assert "head.repo.full_name == github.repository" in body
    # The generator is the BASE checkout's; the PR checkout is only pushed from.
    assert "python3 base/tools/build_ketcher_notices.py" in body
    assert "python3 pr/" not in body and "npm ci" not in body.replace("npm ci --ignore-scripts", "")
    # Only the Ketcher lockfile triggers it.
    assert "tools/ketcher-host/package-lock.json" in body


def test_untrusted_names_reach_the_shell_through_the_environment_only():
    """A branch name inside a `run:` block is substituted BEFORE the shell sees it."""
    in_run = False
    for line in _body(NOTICES).splitlines():
        stripped = line.strip()
        if stripped.startswith(("run:", "- run:")):
            in_run = True
            continue
        if in_run and (stripped.startswith("- name:") or re.match(r"^\s{6}- ", line)):
            in_run = False
        if in_run:
            assert "${{" not in line, f"an expression inside a run block: {line!r}"


def test_it_never_forces_and_never_pushes_a_tag():
    body = _body(NOTICES)
    assert "--force" not in body.replace("No --force", "") and " -f " not in body
    assert "--tags" not in body
