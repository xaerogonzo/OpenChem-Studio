"""The release workflow and the helper it runs.

The workflow can create a GitHub Release, so what is held here is its safety shape: it
publishes nothing (only a draft), only the draft job can write to the repository, every
third-party action is pinned to a commit, no untrusted expression is spliced into a shell
script, and the files it builds are checked before anything leaves the runner. The YAML is
read as text, deliberately: this repository has no YAML parser in its environment and the
properties below are all visible without one.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


info = _load("release_info")


# --- the helper ----------------------------------------------------------------------


def test_the_version_comes_from_pyproject():
    version = info.project_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert f'version = "{version}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


@pytest.mark.parametrize("tag", ["0.10.0", "v0.10", "v0.10.0.1", "v0.10.0-rc1", "release-0.10.0", "V0.10.0", "v1.2.x", ""])
def test_a_tag_that_is_not_a_release_tag_is_refused(tag):
    with pytest.raises(info.ReleaseInfoError, match="not a release tag"):
        info.check_tag(tag, "0.10.0")


def test_a_tag_that_disagrees_with_the_version_is_refused_and_says_what_to_do():
    with pytest.raises(info.ReleaseInfoError, match="bump the version in a merged PR first"):
        info.check_tag("v0.11.0", "0.10.0")
    assert info.check_tag("v0.10.0", "0.10.0") == "0.10.0"


CHANGELOG = """# Changelog

## [Unreleased]

### Something not released
- new thing

## [0.10.0] — 2026-08-17

### Added
- the thing
- another

### Fixed
- a bug

## [0.9.0] — 2026-08-04

### Added
- older
"""


def test_the_notes_are_exactly_that_versions_section():
    notes = info.release_notes(CHANGELOG, "0.10.0")
    assert "the thing" in notes and "a bug" in notes and "### Added" in notes
    assert "older" not in notes and "new thing" not in notes
    assert notes.endswith("\n") and not notes.endswith("\n\n")


def test_a_version_with_no_section_is_refused_and_unreleased_is_not_a_version():
    with pytest.raises(info.ReleaseInfoError, match="no '## \\[0.11.0\\]' section"):
        info.release_notes(CHANGELOG, "0.11.0")
    with pytest.raises(info.ReleaseInfoError):
        info.release_notes(CHANGELOG, "Unreleased")


def test_an_empty_section_is_refused():
    with pytest.raises(info.ReleaseInfoError, match="empty"):
        info.release_notes("## [Unreleased]\n\n## [1.0.0] — 2027-01-01\n\n## [0.9.0]\n- x\n", "1.0.0")


def test_the_last_section_runs_to_the_end_of_the_file():
    assert info.release_notes("## [1.0.0]\n- only entry\n", "1.0.0") == "- only entry\n"


def test_a_version_that_is_a_prefix_of_another_is_not_confused_with_it():
    text = "## [1.0.10] — d\n- ten\n\n## [1.0.1] — d\n- one\n"
    assert info.release_notes(text, "1.0.1") == "- one\n"


def test_the_current_version_already_has_a_changelog_section():
    """Fails the moment someone bumps pyproject.toml without moving the Unreleased entries
    under that version, which is the same check the release workflow makes, one PR earlier."""
    notes = info.release_notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), info.project_version())
    assert notes.strip()


def test_the_command_line(capsys, tmp_path):
    version = info.project_version()
    assert info.main(["version"]) == 0 and capsys.readouterr().out.strip() == version
    assert info.main(["check-tag", f"v{version}"]) == 0
    assert info.main(["check-tag", "v9.9.9"]) == 1 and "pyproject.toml says" in capsys.readouterr().err
    out = tmp_path / "notes.md"
    assert info.main(["notes", f"v{version}", "--out", str(out)]) == 0 and out.read_text(encoding="utf-8").strip()
    assert b"\r" not in out.read_bytes()


# --- the workflow's shape ----------------------------------------------------------------


def _job(name: str) -> str:
    """The text of one top-level job."""
    body = WORKFLOW.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  (?=[a-z][\w-]*:\n)", body)
    for part in parts:
        if part.startswith(f"{name}:\n"):
            return part
    raise AssertionError(f"no job named {name}")


def _run_blocks(text: str) -> list[str]:
    """Every `run:` script in `text`, single-line or block."""
    blocks: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        indent, rest = len(match.group(1)), match.group(2)
        if rest and not rest.startswith(("|", ">")):
            blocks.append(rest)
            continue
        body = []
        for following in lines[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        blocks.append("\n".join(body))
    return blocks


def test_it_runs_on_a_release_tag_on_relevant_pull_requests_and_on_demand():
    assert "tags:\n      - 'v[0-9]+.[0-9]+.[0-9]+'" in WORKFLOW
    assert "pull_request:\n    # " in WORKFLOW and "workflow_dispatch:" in WORKFLOW
    paths = re.findall(r"^      - '([^']+)'$", WORKFLOW.split("pull_request:", 1)[1].split("workflow_dispatch:", 1)[0], re.M)
    assert ".github/workflows/release.yml" in paths and "build.ps1" in paths and "packaging/**" in paths
    assert "tools/changelog.py" in paths  # it decides whether a tag can be cut
    for path in paths:
        if "*" not in path:
            assert (ROOT / path).exists(), f"the workflow watches {path}, which does not exist"


def test_it_has_no_permissions_by_default_and_only_the_draft_job_can_write():
    assert re.search(r"(?m)^permissions: \{\}$", WORKFLOW)
    assert WORKFLOW.count("contents: write") == 1
    assert "contents: write" in _job("draft") and "contents: write" not in _job("build")
    assert "contents: read" in _job("build")
    assert WORKFLOW.count("id-token: write") == 1 and "id-token: write" in _job("build")


def test_the_release_is_a_draft_and_nothing_publishes_it():
    draft = _job("draft")
    assert "gh release create" in draft and "--draft" in draft and "--verify-tag" in draft
    for forbidden in ("--latest", "--prerelease=false", "gh release edit", "gh release upload", "draft=false"):
        assert forbidden not in WORKFLOW, f"the workflow must not publish: {forbidden}"


def test_the_draft_only_happens_for_a_tag_push_after_a_successful_build():
    draft = _job("draft")
    assert "needs: build" in draft
    assert "github.event_name == 'push' && github.ref_type == 'tag'" in draft
    attest_step = WORKFLOW.split("- name: Attest where these files came from")[1].split("- name:")[0]
    assert "github.event_name == 'push' && github.ref_type == 'tag'" in attest_step


def test_every_third_party_action_is_pinned_to_a_commit():
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(?:\s+#\s*(.*))?$", WORKFLOW, re.M)
    assert len(uses) >= 6
    for action, comment in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), f"{action} is not pinned to a full commit SHA"
        assert comment and comment.startswith("v"), f"{action} has no version comment saying which release the SHA is"


def test_no_expression_is_spliced_into_a_shell_script():
    """`${{ ... }}` inside a `run:` is text substitution BEFORE the shell sees it, so a tag or
    branch name becomes code. Everything reaches scripts through `env:`."""
    scripts = _run_blocks(WORKFLOW)
    assert len(scripts) >= 8
    for script in scripts:
        assert "${{" not in script, f"an expression is spliced into a script:\n{script}"


def test_the_tag_and_the_changelog_are_checked_before_the_long_build():
    build = _job("build")
    order = [
        build.index(s)
        for s in ("check-tag", "release_info.py notes", "changelog.py check --no-pending", "Install uv", "build.ps1")
    ]
    assert order == sorted(order), "the cheap checks must come before the build"


def test_the_build_is_the_one_pipeline_the_docs_describe():
    build = _job("build")
    assert "./build.ps1 -Release -Installer" in build
    assert "uv sync --frozen --extra ai --extra network --extra openbabel --group build" in build
    assert "sha256sum -c SHA256SUMS.txt" in build and "sha256sum -c SHA256SUMS.txt" in _job("draft")


def test_inno_setup_is_pinned_by_version_and_checked_against_its_hash():
    assert "innosetup-6.7.3.exe" in WORKFLOW
    assert "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732" in WORKFLOW
    assert "if ($actual -ne $expected) { throw" in WORKFLOW
    assert '"ISCC=$iscc"' in WORKFLOW and "GITHUB_ENV" in WORKFLOW


def test_a_failed_build_keeps_its_evidence():
    build = _job("build")
    assert "if: failure()" in build and "openchem-smoke-*" in build and "release-evidence" in build


def test_the_workflow_says_what_it_does_and_does_not_prove():
    assert "DRAFT" in WORKFLOW and "not a code signature" in WORKFLOW
    assert "gh attestation verify" in WORKFLOW
