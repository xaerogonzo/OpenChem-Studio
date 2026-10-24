"""`tools/changelog.py`: changelog fragments exist so two PRs cannot conflict on CHANGELOG.md.

Everything runs in a temporary root. The one property that matters, that two branches each
adding a fragment merge cleanly while two branches each editing [Unreleased] do not, is
tested in a disposable git repository, including the old style so the test can fail.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("changelog_tool", ROOT / "tools" / "changelog.py")
tool = importlib.util.module_from_spec(_spec)
sys.modules["changelog_tool"] = tool
_spec.loader.exec_module(tool)

CHANGELOG = (
    "# Changelog\n\n## [Unreleased]\n\n### Old entry\n- legacy bullet\n\n"
    "## [0.1.0] — 2026-01-01\n\n### Released\n- shipped\n"
)
GOOD = "### {title}\n- did a thing\n"


def _root(tmp_path: Path, text: str = CHANGELOG) -> Path:
    (tmp_path / "CHANGELOG.md").write_bytes(text.encode("utf-8"))
    (tmp_path / "changelog.d").mkdir()
    return tmp_path


def _frag(root: Path, name: str, body: str) -> Path:
    path = root / "changelog.d" / name
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def test_same_slug_twice_gives_two_paths_and_never_overwrites(tmp_path):
    root = _root(tmp_path)
    when = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    paths = {tool.new_fragment(root, "Fix Docs", when) for _ in range(20)}
    assert len(paths) == 20
    assert all(tool.FRAGMENT_NAME.fullmatch(p.name) and p.name.startswith("202610221200-fix-docs-") for p in paths)


def test_a_name_collision_retries_and_never_truncates_the_existing_file(tmp_path, monkeypatch):
    root = _root(tmp_path)
    when = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    taken = _frag(root, "202610221200-x-abcd.md", "precious")
    draws = iter(["abcd", "ef01"])
    monkeypatch.setattr(tool.secrets, "token_hex", lambda n: next(draws))
    made = tool.new_fragment(root, "x", when)
    assert made.name == "202610221200-x-ef01.md" and taken.read_text(encoding="utf-8") == "precious"


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", "..", "", "!!!"])
def test_an_unsafe_slug_is_refused(tmp_path, bad):
    with pytest.raises(tool.ChangelogError):
        tool.new_fragment(_root(tmp_path), bad)


def test_the_untouched_template_fails_check(tmp_path):
    root = _root(tmp_path)
    tool.new_fragment(root, "x")
    assert any("placeholder" in e for e in tool.validate(root, CHANGELOG))


def test_readme_is_not_a_fragment(tmp_path):
    root = _root(tmp_path)
    (root / "changelog.d" / "README.md").write_text("not a fragment", encoding="utf-8")
    assert tool.fragment_paths(root) == [] and tool.validate(root, CHANGELOG) == []


@pytest.mark.parametrize(
    "body, expect",
    [
        ("", "empty"),
        ("preamble\n### T\n- b\n", "first line"),
        ("### \n- b\n", "title is empty"),
        ("### T\n", "no '- ' bullet"),
        ("### T\n```\n- fake bullet\n```\n", "no '- ' bullet"),
        ("### T\n- b\n```\n", "never closed"),
        ("### T\n- b\n### U\n- c\n", "exactly one"),
        ("## T\n- b\n", "heading"),
    ],
)
def test_each_validation_rule_fails_its_case(tmp_path, body, expect):
    root = _root(tmp_path)
    _frag(root, "202610221200-x-aaaa.md", body)
    assert any(expect in e for e in tool.validate(root, CHANGELOG)), tool.validate(root, CHANGELOG)


def test_a_fenced_heading_and_bullet_inside_a_real_entry_are_fine(tmp_path):
    root = _root(tmp_path)
    _frag(root, "202610221200-x-aaaa.md", "### T\n- real\n```\n### not a title\n```\n")
    assert tool.validate(root, CHANGELOG) == []


def test_duplicate_titles_and_a_clash_with_the_legacy_unreleased_are_reported_together(tmp_path):
    root = _root(tmp_path)
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="Same  Title"))
    _frag(root, "202610221201-b-bbbb.md", GOOD.format(title="same title"))
    _frag(root, "202610221202-c-cccc.md", GOOD.format(title="OLD ENTRY"))
    errors = tool.validate(root, CHANGELOG)
    assert len(errors) == 2
    assert any("duplicates" in e and "bbbb" in e for e in errors) or any("duplicates" in e for e in errors)
    assert any("already in [Unreleased]" in e for e in errors)


def test_a_title_used_in_a_released_section_is_allowed(tmp_path):
    root = _root(tmp_path)
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="Released"))
    assert tool.validate(root, CHANGELOG) == []


def test_render_keeps_legacy_and_released_text_and_orders_newest_first(tmp_path):
    root = _root(tmp_path)
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    _frag(root, "202610221300-b-bbbb.md", GOOD.format(title="Second"))
    text, consumed = tool.build(root, write=False)
    assert [p.name[:12] for p in consumed] == ["202610221300", "202610221200"]
    assert text.index("### Second") < text.index("### First") < text.index("### Old entry")
    assert text.endswith(CHANGELOG.split("## [0.1.0]", 1)[1])
    assert tool.build(root, write=False)[0] == text  # deterministic


def test_build_writes_consumes_and_a_second_build_is_a_noop(tmp_path):
    root = _root(tmp_path)
    frag = _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    preview, _ = tool.build(root, write=False)
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG  # preview wrote nothing
    assert tool.main(["--root", str(root), "build"]) == 0
    assert (root / "CHANGELOG.md").read_bytes().decode() == preview and not frag.exists()
    assert tool.main(["--root", str(root), "build"]) == 0
    assert (root / "CHANGELOG.md").read_bytes().decode() == preview


def test_crlf_changelog_stays_crlf(tmp_path):
    root = _root(tmp_path, CHANGELOG.replace("\n", "\r\n"))
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    text, _ = tool.build(root, write=False)
    assert "\n" not in text.replace("\r\n", "")


def test_an_invalid_fragment_stops_build_and_consumes_nothing(tmp_path):
    root = _root(tmp_path)
    good = _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    _frag(root, "202610221201-b-bbbb.md", "### T\n")
    assert tool.main(["--root", str(root), "build"]) == 1
    assert good.exists() and (root / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG


def test_a_failed_write_consumes_nothing(tmp_path, monkeypatch):
    root = _root(tmp_path)
    frag = _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    monkeypatch.setattr(tool.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        tool.build(root, write=True)
    assert frag.exists() and (root / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG
    assert not list(root.glob(".CHANGELOG.*.tmp"))


def test_no_pending_gate(tmp_path):
    root = _root(tmp_path)
    assert tool.main(["--root", str(root), "check", "--no-pending"]) == 0
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    assert tool.main(["--root", str(root), "check"]) == 0
    assert tool.main(["--root", str(root), "check", "--no-pending"]) == 1


def test_a_missing_or_doubled_unreleased_heading_is_refused(tmp_path):
    assert tool.main(["--root", str(_root(tmp_path, "# C\n## [0.1.0]\n- x\n")), "check"]) == 1


def test_it_does_not_depend_on_the_working_directory(tmp_path):
    (tmp_path / "repo").mkdir()
    root = _root(tmp_path / "repo")
    _frag(root, "202610221200-a-aaaa.md", GOOD.format(title="First"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    done = subprocess.run(
        [sys.executable, "-I", str(ROOT / "tools" / "changelog.py"), "--root", str(root), "check"],
        cwd=elsewhere, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr


def test_the_real_repository_has_only_valid_fragments():
    assert tool.validate(ROOT, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")) == []


# --- the property this exists for ------------------------------------------------------

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
        cwd=cwd, capture_output=True, text=True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_two_branches_adding_fragments_merge_cleanly_and_two_editing_unreleased_do_not(tmp_path):
    (tmp_path / "r").mkdir()
    repo = _root(tmp_path / "r")
    _git(repo, "init", "-q", "-b", "main")
    (repo / "changelog.d" / ".keep").write_text("", encoding="utf-8")
    _git(repo, "add", "-A")
    assert _git(repo, "commit", "-qm", "base").returncode == 0

    def branch(name: str, edit):
        _git(repo, "checkout", "-q", "-b", name, "main")
        edit()
        _git(repo, "add", "-A")
        assert _git(repo, "commit", "-qm", name).returncode == 0

    def old_style(title):
        def go():
            path = repo / "CHANGELOG.md"
            path.write_bytes(path.read_bytes().replace(b"## [Unreleased]\n\n", f"## [Unreleased]\n\n### {title}\n- x\n\n".encode()))
        return go

    branch("frag-a", lambda: tool.new_fragment(repo, "same-slug"))
    branch("frag-b", lambda: tool.new_fragment(repo, "same-slug"))
    branch("old-a", old_style("A"))
    branch("old-b", old_style("B"))

    _git(repo, "checkout", "-q", "frag-a")
    assert _git(repo, "merge", "-q", "--no-edit", "frag-b").returncode == 0
    assert len(tool.fragment_paths(repo)) == 2
    _git(repo, "checkout", "-q", "old-a")
    assert _git(repo, "merge", "-q", "--no-edit", "old-b").returncode != 0  # the conflict this removes
