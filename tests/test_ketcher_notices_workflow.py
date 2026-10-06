"""The one workflow handed a write-capable token on a PR, held to the properties that make that safe.

`ketcher-notices.yml` runs on `pull_request` for Dependabot's PRs and pushes with a token stored as a DEPENDABOT
secret. It is `pull_request` and not `pull_request_target` because GitHub withholds secrets from a
`pull_request_target` run on a Dependabot-authored PR (its docs: "the GITHUB_TOKEN will be read-only and secrets
are not available"), which made the first version unable to do anything on a real bump. A `pull_request` run
executes the PR's own copy of the workflow, so what matters is what a PR can make it do: that is a property of a
handful of lines and would be lost by a plausible-looking edit (a build step, an inline `${{ ... head.ref }}`, a
dropped file check). So the properties are tests, in the textual style of `test_workflow_safety.py` and for the same
reason: a YAML parse is not a dependency of this project.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
NOTICES = WORKFLOWS / "ketcher-notices.yml"


def _body(path: Path) -> str:
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not re.match(r"^\s*#", line))


def test_no_workflow_uses_pull_request_target():
    """Write-capable and runs the base branch's workflow on a PR's behalf: the first version of this one used it and
    could never have worked on a Dependabot PR, so nothing here needs it and nothing should be added casually."""
    found = [p.name for p in sorted(WORKFLOWS.glob("*.y*ml")) if "pull_request_target" in _body(p)]
    assert not found, f"pull_request_target in {found}: see this file's docstring before adding one"


def test_the_trigger_is_pull_request_on_the_ketcher_lockfile_only():
    body = _body(NOTICES)
    assert re.search(
        r"^on:\n  pull_request:\n    paths:\n      - tools/ketcher-host/package-lock\.json$", body, re.M
    )


def test_the_notices_workflow_runs_nothing_from_the_pr():
    body = _body(NOTICES)
    # Dependencies install without lifecycle scripts: no package can run code during the install.
    assert "npm ci --ignore-scripts" in body
    assert "npm ci" not in body.replace("npm ci --ignore-scripts", "")
    # Only Dependabot's own PRs, from a branch in this repository.
    assert "pull_request.user.login == 'dependabot[bot]'" in body
    assert "head.repo.full_name == github.repository" in body
    # The generator is the BASE commit's, by SHA; the PR checkout is only pushed from.
    assert "ref: ${{ github.event.pull_request.base.sha }}" in body
    assert "python3 base/tools/build_ketcher_notices.py" in body
    assert "python3 pr/" not in body


def test_it_stands_down_unless_the_pr_touches_only_the_manifests_and_every_step_waits_for_that():
    """A Dependabot-looking branch that also changed a workflow or the generator must get no push, and nothing may
    run before the check passes."""
    body = _body(NOTICES)
    assert "pulls/${PR_NUMBER}/files" in body
    allowed = re.search(r"grep -v -E '\^\((.*?)\)\$'", body)
    assert allowed, "the file allow-list is gone"
    assert set(allowed.group(1).split("|")) == {
        r"tools/ketcher-host/package\.json",
        r"tools/ketcher-host/package-lock\.json",
        r"src/openchem/resources/ketcher/THIRD-PARTY-NOTICES\.txt",
    }
    steps = re.split(r"^      - name: ", body, flags=re.M)[1:]
    assert len(steps) == 5
    assert "id: scope" in steps[0]
    for step in steps[1:]:
        assert "if: steps.scope.outputs.go == 'true'" in step, step.splitlines()[0]


def test_the_token_it_is_handed_cannot_write_and_the_one_that_can_is_used_only_to_push():
    body = _body(NOTICES)
    permissions = re.search(r"^permissions:\n((?:  .*\n)+)", body, re.M).group(1)
    assert "write" not in permissions
    assert "pull-requests: read" in permissions, "the first step lists the PR's files"
    # NOTICES_PUSH_TOKEN appears as the env that is tested, and as the PR checkout's token (which is what pushes).
    uses = [m.start() for m in re.finditer(r"secrets\.NOTICES_PUSH_TOKEN", body)]
    assert len(uses) == 2, uses


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
