"""The naming-consumer manifest cannot go stale.

`tests/naming_consumers.toml` lists every test file that consumes the namer. Round 3 left one red for six stages
because "the whole naming-consuming test set" was a phrase; this makes it a list, and these tests keep the list
true in BOTH directions: a test that imports the namer and is not registered fails here, and an entry that names
a file which does not exist fails here.

The scan is static (a regex over the file's text), so it needs no engine and no JRE.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_consumers as manifest  # noqa: E402

#: What makes a test a consumer. Deliberately about the IMPORT or the artifact, never about a name string.
PATTERN = re.compile(
    r"iupac_namer|name_smiles|naming_providers|derived_name_for_structure|charged_panel|naming_stage_artifact"
    r"|naming_populations|charge_ownership|naming_ref_compare"
)
#: Support files: they hold fixtures and helpers, not assertions about names.
SUPPORT = {"tests/conftest.py"}


def _app_tests() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "tests/*.py"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    return [f for f in tracked if "/" not in f[len("tests/"):] and f not in SUPPORT]


def _registered() -> set[str]:
    return {c["file"] for c in manifest.consumers()}


def test_every_app_test_that_imports_the_namer_is_registered():
    unregistered = [
        f for f in _app_tests()
        if PATTERN.search((ROOT / f).read_text(encoding="utf-8", errors="replace")) and f not in _registered()
    ]
    assert not unregistered, (
        f"tests that consume the namer and are not in tests/naming_consumers.toml: {unregistered}"
    )


def test_every_registered_consumer_exists():
    missing = [c["file"] for c in manifest.consumers() if not (ROOT / c["file"]).exists()]
    assert not missing, missing


def test_an_entry_says_why_and_uses_the_declared_vocabulary():
    seen: set[str] = set()
    for c in manifest.consumers():
        assert c["file"] not in seen, f"duplicate entry {c['file']}"
        seen.add(c["file"])
        assert c["scope"] in manifest.SCOPES, c["file"]
        assert c["owner"] in {"namer", "benchmarks", "app"}, c["file"]
        assert len(c["why"].split()) >= 4, f"{c['file']}: a consumer says why it consumes names"


def test_the_vendored_suite_is_registered_once_as_a_directory():
    vendor = [c for c in manifest.consumers() if c["scope"] == "vendor"]
    assert [c["file"] for c in vendor] == ["tests/vendor/iupac_namer"]
    assert (ROOT / "tests/vendor/iupac_namer").is_dir()


def test_the_scope_selector_returns_files_in_manifest_order():
    core = manifest.select({"core"})
    assert core and all(f.startswith("tests/test_") for f in core)
    assert set(manifest.select({"core", "benchmark", "app", "vendor"})) == _registered()
    try:
        manifest.select({"everything"})
    except SystemExit:
        pass
    else:  # pragma: no cover - the failure is the assertion
        raise AssertionError("an unknown scope must be refused, not read as empty")


def test_the_two_sessions_partition_the_manifest():
    """Every consumer runs in exactly one pytest process. A file in neither would never be run by a gate built from
    sessions; a file in both would run twice and, if it is the vendored directory, in the wrong process."""
    app = set(manifest.session_files("app"))
    vendor = set(manifest.session_files("vendor"))
    assert not app & vendor
    assert app | vendor == _registered()
    assert vendor == {"tests/vendor/iupac_namer"}


def test_one_runnable_line_never_mixes_the_vendored_suite_with_the_app_tests():
    """Naming round 8: the default list ended in the vendored directory as its first token, a sed meant to strip it did not
    match, and `tests/vendor/iupac_namer/conftest.py` (which replaces `py2opsin.py2opsin` for the whole process) failed
    `test_opsin_isolation.py`'s signature check on a 28-minute run. A tool that cannot print the wrong line is the fix."""
    with pytest.raises(SystemExit, match="mixes the vendored suite"):
        manifest.refuse_mixed({"core", "vendor"})
    with pytest.raises(SystemExit, match="mixes the vendored suite"):
        manifest.refuse_mixed(set(manifest.SCOPES))
    manifest.refuse_mixed({"core", "benchmark", "app"})  # an app session is fine
    manifest.refuse_mixed({"vendor"})  # and so is the vendored one, alone


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "naming_consumers.py"), *argv], capture_output=True, text=True, cwd=ROOT
    )


def test_the_command_line_refuses_a_mixed_args_line_and_prints_each_session_alone():
    assert _run("--args").returncode != 0, "the default scope holds the vendored suite, so --args must refuse it"
    assert _run("--scope", "core,vendor", "--args").returncode != 0
    assert _run("--scope", "core,vendor", "--args", "--allow-mixed").returncode == 0
    app = _run("--session", "app", "--args")
    vendor = _run("--session", "vendor", "--args")
    assert app.returncode == 0 and vendor.returncode == 0
    assert "tests/vendor" not in app.stdout
    assert vendor.stdout.split() == ["tests/vendor/iupac_namer"]
    assert _run("--session", "app", "--scope", "core").returncode != 0, "--session and --scope are alternatives"
