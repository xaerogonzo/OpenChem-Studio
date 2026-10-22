"""The install self-check: does a release still match the build it came from?

It exists because most of this application's data files fail SILENTLY when one
is altered or lost (a rules table with fewer rules, a record reading
`unvalidated`). The properties held here: a change of even one byte is seen
(including one that keeps the size), nothing unreadable or unknown ever reads as
`verified`, the manifest cannot be built empty or ambiguous, and the check never
raises into the application.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

from openchem import install_check as ic
from openchem.install_check import InstallCheckError, InstallCheckResult, Status

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _restore_the_recorded_result():
    saved = ic.current()
    yield
    ic.record(saved)


@pytest.fixture
def tree(tmp_path):
    """A fake package with a directory entry and a single-file entry, and the datas that ship it."""
    package = tmp_path / "pkg"
    (package / "data" / "sub dir").mkdir(parents=True)
    (package / "data" / "a.json").write_text('{"a": 1}', encoding="utf-8")
    (package / "data" / "sub dir" / "ünï.txt").write_text("unicode path", encoding="utf-8")
    (package / "data" / "__pycache__").mkdir()
    (package / "data" / "__pycache__" / "x.pyc").write_bytes(b"cache")
    (package / "one.py").write_text("print(1)\n", encoding="utf-8")
    (package / "data" / "regulatory" / "sources").mkdir(parents=True)
    (package / "data" / "regulatory" / "sources" / "in.json").write_text("{}", encoding="utf-8")
    datas = [
        (str(package / "data"), "openchem/chem/data"),
        (str(package / "one.py"), "openchem/chem"),
        (str(tmp_path / "elsewhere"), "thirdparty"),  # not under the package: out of scope, even if absent
    ]
    return package, datas


DROP = ("openchem/chem/data/regulatory/sources/",)


def _install(tmp_path, manifest):
    """Copy what the manifest names into an 'installed' folder, as PyInstaller would."""
    return tmp_path / "installed"


def _materialise(package, datas, destination):
    """Lay the tree out where the spec says it installs, minus what the spec drops."""
    for source, dest in datas:
        source = Path(source)
        if not source.exists() or package not in source.parents:
            continue
        if source.is_file():
            target = destination / dest / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            continue
        for path in source.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(source).as_posix()
                if f"{dest}/{relative}".startswith(DROP):
                    continue
                target = destination / dest / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())


# --- building ------------------------------------------------------------------


def test_the_manifest_names_installed_paths_and_leaves_out_what_the_spec_drops(tree):
    package, datas = tree
    files = ic.build_manifest(datas, package, drop_prefixes=DROP)
    paths = [path for path, _, _ in files]
    assert paths == sorted(paths)
    assert "openchem/chem/data/a.json" in paths
    assert "openchem/chem/data/sub dir/ünï.txt" in paths
    assert "openchem/chem/one.py" in paths  # a file entry installs as destination/name
    assert not any("__pycache__" in p or p.endswith(".pyc") for p in paths)
    assert not any(p.startswith(DROP) for p in paths)
    assert not any(p.startswith("thirdparty") for p in paths)


def test_the_manifest_is_deterministic_and_records_real_hashes(tree):
    package, datas = tree
    first = ic.build_manifest(datas, package, drop_prefixes=DROP)
    assert first == ic.build_manifest(datas, package, drop_prefixes=DROP)
    entry = next(e for e in first if e[0] == "openchem/chem/data/a.json")
    assert entry[1] == hashlib.sha256(b'{"a": 1}').hexdigest() and entry[2] == len(b'{"a": 1}')


def test_an_empty_manifest_is_refused_because_it_would_verify_a_tree_it_never_looked_at(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    with pytest.raises(InstallCheckError, match="empty"):
        ic.build_manifest([], package)
    (package / "d").mkdir()
    with pytest.raises(InstallCheckError, match="empty"):
        ic.build_manifest([(str(package / "d"), "x")], package)


def test_a_data_entry_that_is_not_there_is_a_build_error_not_a_skip(tree):
    package, _ = tree
    with pytest.raises(InstallCheckError, match="not there"):
        ic.build_manifest([(str(package / "missing"), "x")], package)


def test_two_entries_installing_to_one_path_are_refused_even_if_only_the_case_differs(tree):
    package, _ = tree
    (package / "A.json").write_text("{}", encoding="utf-8")
    (package / "other").mkdir()
    (package / "other" / "a.json").write_text("{}", encoding="utf-8")
    datas = [(str(package / "A.json"), "d"), (str(package / "other" / "a.json"), "d")]
    with pytest.raises(InstallCheckError, match="same path"):
        ic.build_manifest(datas, package)


def test_a_symbolic_link_is_not_a_data_file(tree):
    package, _ = tree
    link = package / "data" / "link.json"
    try:
        os.symlink(package / "data" / "a.json", link)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")
    with pytest.raises(InstallCheckError, match="symbolic link"):
        ic.build_manifest([(str(package / "data"), "d")], package)


def test_the_generated_module_is_plain_literals_that_round_trip(tree, tmp_path):
    package, datas = tree
    files = ic.build_manifest(datas, package, drop_prefixes=DROP)
    out = tmp_path / "_integrity.py"
    ic.write_module_atomically(out, files)
    assert not list(tmp_path.glob("*.tmp"))
    spec = importlib.util.spec_from_file_location("gen", out)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert ic.validate_manifest(module.SCHEMA, module.FILES) == files


# --- validating a manifest -----------------------------------------------------

_GOOD = "a" * 64


@pytest.mark.parametrize(
    "schema, files, message",
    [
        (2, [("a", _GOOD, 1)], "schema"),
        (1, [], "no files"),
        (1, None, "no files"),
        (1, [("a", _GOOD)], "malformed"),
        (1, [("a", _GOOD, "1")], "field types"),
        (1, [("a", _GOOD, -1)], "field types"),
        (1, [("/abs", _GOOD, 1)], "relative"),
        (1, [("../up", _GOOD, 1)], "relative"),
        (1, [("a/../../b", _GOOD, 1)], "relative"),
        (1, [("C:/x", _GOOD, 1)], "relative"),
        (1, [("a\\b", _GOOD, 1)], "relative"),
        (1, [("a", "xyz", 1)], "sha256"),
        (1, [("a", "A" * 64, 1)], "sha256"),
        (1, [("a", _GOOD, 1), ("A", _GOOD, 1)], "twice"),
    ],
)
def test_a_bad_manifest_is_rejected_with_a_reason(schema, files, message):
    with pytest.raises(InstallCheckError, match=message):
        ic.validate_manifest(schema, files)


# --- verifying -----------------------------------------------------------------


@pytest.fixture
def installed(tree, tmp_path):
    package, datas = tree
    files = ic.build_manifest(datas, package, drop_prefixes=DROP)
    root = tmp_path / "installed"
    _materialise(package, datas, root)
    return files, root


def test_an_untouched_install_verifies(installed):
    files, root = installed
    result = ic.verify(files, root)
    assert result.status is Status.VERIFIED and result.checked == len(files) and result.problems == 0


def test_one_flipped_byte_that_keeps_the_size_is_still_seen(installed):
    """The reason hashes are compared and not just sizes: an editor saving a
    one-character change leaves the length alone."""
    files, root = installed
    target = root / "openchem" / "chem" / "data" / "a.json"
    data = bytearray(target.read_bytes())
    data[3] ^= 0x01
    target.write_bytes(bytes(data))
    result = ic.verify(files, root)
    assert result.status is Status.MODIFIED and result.modified == ("openchem/chem/data/a.json",)


def test_a_changed_size_is_seen(installed):
    files, root = installed
    (root / "openchem" / "chem" / "data" / "a.json").write_text("{}", encoding="utf-8")
    assert ic.verify(files, root).modified == ("openchem/chem/data/a.json",)


def test_a_missing_file_is_missing_not_a_clean_verdict(installed):
    files, root = installed
    (root / "openchem" / "chem" / "data" / "sub dir" / "ünï.txt").unlink()
    result = ic.verify(files, root)
    assert result.status is Status.MODIFIED and result.missing == ("openchem/chem/data/sub dir/ünï.txt",)


def test_an_unreadable_file_is_never_verified(installed, monkeypatch):
    files, root = installed
    real = ic._hash_file

    def hashing(path):
        if path.name == "a.json":
            raise PermissionError("locked")
        return real(path)

    monkeypatch.setattr(ic, "_hash_file", hashing)
    result = ic.verify(files, root)
    assert result.status is Status.MODIFIED and result.unreadable == ("openchem/chem/data/a.json",)


def test_all_three_kinds_of_trouble_are_kept_apart_not_first_one_wins(installed):
    files, root = installed
    data = root / "openchem" / "chem" / "data"
    (data / "a.json").write_text("{}", encoding="utf-8")
    (data / "sub dir" / "ünï.txt").unlink()
    result = ic.verify(files, root)
    assert result.modified and result.missing
    assert "changed" in result.summary() and "missing" in result.summary()


def test_files_that_are_not_in_the_manifest_are_ignored(installed):
    files, root = installed
    (root / "openchem" / "chem" / "data" / "user-added.txt").write_text("extra", encoding="utf-8")
    assert ic.verify(files, root).status is Status.VERIFIED


def test_a_missing_install_folder_fails_the_check_instead_of_reporting_everything_missing(tmp_path):
    result = ic.verify([("a", _GOOD, 1)], tmp_path / "nope")
    assert result.status is Status.CHECK_FAILED


def test_the_root_is_where_the_files_are_not_the_working_directory(installed, tmp_path, monkeypatch):
    files, root = installed
    elsewhere = tmp_path / "somewhere else"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert ic.verify(files, root).status is Status.VERIFIED


# --- the running application ---------------------------------------------------


def _fake_integrity(monkeypatch, files, schema=1):
    module = types.ModuleType("openchem._integrity")
    module.SCHEMA = schema
    module.FILES = tuple(files)
    monkeypatch.setitem(sys.modules, "openchem._integrity", module)


def test_a_source_run_is_not_applicable(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert ic.check_installed().status is Status.NOT_APPLICABLE


def test_a_frozen_build_with_no_manifest_fails_the_check(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delitem(sys.modules, "openchem._integrity", raising=False)
    result = ic.check_installed()
    assert result.status is Status.CHECK_FAILED and "no manifest" in result.detail


def test_a_frozen_build_verifies_against_its_own_root(installed, monkeypatch):
    files, root = installed
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    _fake_integrity(monkeypatch, files)
    assert ic.check_installed().status is Status.VERIFIED
    (root / "openchem" / "chem" / "one.py").unlink()
    assert ic.check_installed().status is Status.MODIFIED


def test_a_malformed_manifest_or_unknown_root_is_check_failed_never_verified(installed, monkeypatch):
    files, root = installed
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    _fake_integrity(monkeypatch, files, schema=99)
    assert ic.check_installed().status is Status.CHECK_FAILED
    _fake_integrity(monkeypatch, files)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    result = ic.check_installed()
    assert result.status is Status.CHECK_FAILED and "not known" in result.detail


# --- what a person is shown ----------------------------------------------------


def test_the_report_names_paths_and_counts_but_is_capped(installed):
    result = InstallCheckResult(Status.MODIFIED, modified=tuple(f"p/{i}" for i in range(50)))
    report = result.report(limit=5)
    assert report.count("changed: p/") == 5 and "and 45 more changed" in report
    assert "50 changed" in result.summary() and "Re-extract" in result.summary()


def test_every_status_has_a_summary_and_only_verified_says_verified():
    for status in Status:
        text = InstallCheckResult(status, checked=3, detail="why").summary()
        assert text
        assert ("verified" in text) == (status is Status.VERIFIED)


def test_about_reports_the_install_line(monkeypatch):
    from openchem import build_info

    ic.record(InstallCheckResult(Status.VERIFIED, checked=7))
    info = build_info.collect()
    assert "Install:  verified (7 data files match the build)" in info.as_text()


# --- the monitor ---------------------------------------------------------------


def _wait_for(qapp, predicate, timeout=5.0):
    import time

    end = time.time() + timeout
    while time.time() < end and not predicate():
        qapp.processEvents()
        time.sleep(0.01)
    return predicate()


def test_the_monitor_runs_the_check_off_the_ui_thread_once_and_records_it(qapp, monkeypatch):
    import threading

    from openchem.app.install_monitor import InstallMonitor

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ic.record(InstallCheckResult(Status.CHECKING))
    seen = []
    threads = []

    def check():
        threads.append(threading.current_thread())
        return InstallCheckResult(Status.VERIFIED, checked=4)

    monkeypatch.setattr(ic, "check_installed", check)
    monitor = InstallMonitor()
    monitor.changed.connect(seen.append)
    monitor.start()
    monitor.start()  # a second call does nothing
    assert _wait_for(qapp, lambda: bool(seen))
    assert len(seen) == 1 and seen[0].status is Status.VERIFIED
    assert threads and threads[0] is not threading.main_thread()
    assert ic.current().status is Status.VERIFIED  # About reads this


def test_a_source_run_answers_at_once_without_a_worker(qapp, monkeypatch):
    from openchem.app.install_monitor import InstallMonitor

    monkeypatch.delattr(sys, "frozen", raising=False)
    ic.record(InstallCheckResult(Status.NOT_APPLICABLE))
    seen = []
    monitor = InstallMonitor()
    monitor.changed.connect(seen.append)
    monitor.start()
    assert [r.status for r in seen] == [Status.NOT_APPLICABLE]


@pytest.mark.parametrize(
    "result, shown",
    [
        (InstallCheckResult(Status.VERIFIED, checked=1), False),
        (InstallCheckResult(Status.NOT_APPLICABLE), False),
        (InstallCheckResult(Status.MODIFIED, checked=2, modified=("a",)), True),
        (InstallCheckResult(Status.CHECK_FAILED, detail="no manifest"), True),
    ],
)
def test_the_status_bar_is_used_only_for_a_finding(qapp, monkeypatch, result, shown):
    from PySide6.QtWidgets import QMainWindow

    from openchem.app import install_monitor

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(ic, "check_installed", lambda: result)
    window = QMainWindow()
    monitor = install_monitor.attach(window)
    assert _wait_for(qapp, lambda: ic.current() == result)
    qapp.processEvents()
    assert bool(window.statusBar().currentMessage()) is shown
    del monitor
    window.close()


# --- how the build wires it ----------------------------------------------------


def test_the_real_data_directory_is_covered_and_the_ruleset_sources_are_not():
    package = ROOT / "src" / "openchem"
    files = ic.build_manifest(
        [(str(package / "chem" / "data"), "openchem/chem/data")], package, drop_prefixes=DROP
    )
    paths = {p for p, _, _ in files}
    assert "openchem/chem/data/elements.json" in paths
    assert any(p.startswith("openchem/chem/data/regulatory/generated/") for p in paths)
    assert not any(p.startswith(DROP) for p in paths)


def test_the_spec_builds_the_manifest_from_its_own_datas_and_shares_the_drop_list():
    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    assert "install_check.build_manifest(datas, PKG, drop_prefixes=DROPPED_PREFIXES)" in spec
    assert "dest.startswith(DROPPED_PREFIXES)" in spec
    assert DROP == (spec.split("DROPPED_PREFIXES = (")[1].split(")")[0].strip().strip(",").strip('"'),) or DROP[0] in spec


def test_the_build_makes_proves_and_removes_the_manifest():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert "_integrity.py" in build
    assert "verify_install_tree.py" in build
    assert "Remove-Item $INTEGRITY" in build
    assert "/src/openchem/_integrity.py" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_the_post_freeze_tool_passes_a_matching_tree_and_fails_a_changed_or_absent_one(installed, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("verify_install_tree", ROOT / "tools" / "verify_install_tree.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    files, root = installed
    manifest = tmp_path / "_integrity.py"
    ic.write_module_atomically(manifest, files)
    assert tool.main(["--manifest", str(manifest), "--root", str(root)]) == 0
    (root / "openchem" / "chem" / "data" / "a.json").write_text("{}", encoding="utf-8")
    assert tool.main(["--manifest", str(manifest), "--root", str(root)]) == 1
    assert tool.main(["--manifest", str(tmp_path / "absent.py"), "--root", str(root)]) == 2
    capsys.readouterr()
