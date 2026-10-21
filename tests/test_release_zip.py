"""The release zip: inventory, atomic promotion, and what a failure leaves behind.

The property that matters is that nothing which fails halfway can be mistaken
for a finished release: no `.zip` without its checksum, no checksum for bytes
that changed, no overwrite of an existing release, and a zip whose own extracted
copy has to pass the smoke test before it is promoted.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


release = _load("make_release_zip")
VERSION = "9.9.9"


def _dist(tmp_path) -> Path:
    dist = tmp_path / "dist" / "OpenChemStudio"
    (dist / "_internal" / "openchem" / "chem" / "data").mkdir(parents=True, exist_ok=True)
    (dist / "OpenChemStudio.exe").write_bytes(b"MZ not a real exe")
    (dist / "README.md").write_text("readme", encoding="utf-8")
    (dist / "LICENSE").write_text("licence", encoding="utf-8")
    (dist / "_internal" / "openchem" / "chem" / "data" / "elements.json").write_text("{}", encoding="utf-8")
    (dist / "plugins" / "x").mkdir(parents=True, exist_ok=True)
    (dist / "plugins" / "x" / "plugin.py").write_text("x = 1", encoding="utf-8")
    return dist


def _names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def _build(tmp_path, **kwargs):
    out = tmp_path / "out"
    return release.build_release(_dist(tmp_path), VERSION, out, smoke=kwargs.pop("smoke", lambda exe: True), **kwargs), out


# --- the happy path -------------------------------------------------------------


def test_a_release_is_one_versioned_folder_with_checksums_named_for_the_final_file(tmp_path):
    final, out = _build(tmp_path)
    assert final.name == "OpenChemStudio-v9.9.9-windows-x64.zip"
    names = _names(final)
    assert names and all(n.startswith("OpenChemStudio-v9.9.9/") for n in names)
    assert "OpenChemStudio-v9.9.9/OpenChemStudio.exe" in names
    sums = (out / "SHA256SUMS.txt").read_bytes()
    assert sums == f"{hashlib.sha256(final.read_bytes()).hexdigest()} *{final.name}\n".encode("utf-8")
    assert not sums.startswith(b"\xef\xbb\xbf") and b"\r" not in sums  # no BOM, LF only
    assert not list(out.glob("*.partial"))


def test_the_smoke_test_runs_on_the_extracted_zip_in_a_folder_with_a_space(tmp_path):
    seen = []
    _build(tmp_path, smoke=lambda exe: seen.append(exe) or True)
    (exe,) = seen
    assert exe.name == "OpenChemStudio.exe" and exe.parent.name == "OpenChemStudio-v9.9.9"
    assert " " in str(exe.parent.parent)
    assert not exe.parent.parent.exists(), "the scratch extraction was not cleaned up"


# --- every way it must refuse ----------------------------------------------------


@pytest.mark.parametrize("version", ["", "unknown", "UNKNOWN", "1.0 beta", "a/b", "a\\b"])
def test_an_unknown_or_unsafe_version_is_refused(tmp_path, version):
    with pytest.raises(release.ReleaseError):
        release.build_release(_dist(tmp_path), version, tmp_path / "out", smoke=lambda e: True)


def test_a_folder_that_is_not_a_build_is_refused(tmp_path):
    with pytest.raises(release.ReleaseError, match="built application"):
        release.build_release(tmp_path, VERSION, tmp_path / "out", smoke=lambda e: True)


def test_an_existing_release_is_never_overwritten_without_force(tmp_path):
    final, out = _build(tmp_path)
    before = final.read_bytes()
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.build_release(_dist(tmp_path), VERSION, out, smoke=lambda e: True)
    assert final.read_bytes() == before
    release.build_release(_dist(tmp_path), VERSION, out, smoke=lambda e: True, force=True)


def test_a_failed_smoke_test_leaves_no_zip_and_no_checksums(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(release.ReleaseError, match="smoke test failed"):
        release.build_release(_dist(tmp_path), VERSION, out, smoke=lambda exe: False)
    assert list(out.iterdir()) == [], "a failed release left something that could look final"


def test_a_failure_does_not_destroy_the_previous_release(tmp_path):
    final, out = _build(tmp_path)
    before = final.read_bytes()
    sums_before = (out / "SHA256SUMS.txt").read_bytes()
    with pytest.raises(release.ReleaseError):
        release.build_release(_dist(tmp_path), VERSION, out, smoke=lambda e: False, force=True)
    assert final.read_bytes() == before and (out / "SHA256SUMS.txt").read_bytes() == sums_before


def test_an_inventory_failure_stops_before_anything_is_promoted(tmp_path):
    dist = _dist(tmp_path)
    (dist / "_internal" / "openchem" / "_help_bundle.py").write_text("loose!", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(release.ReleaseError, match="must not ship loose"):
        release.build_release(dist, VERSION, out, smoke=lambda e: pytest.fail("smoke must not run"))
    assert list(out.iterdir()) == []


# --- the inventory validator, on hand-made archives -------------------------------


def _zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


TOP = "OpenChemStudio-v9.9.9"
GOOD = {
    f"{TOP}/OpenChemStudio.exe": b"x",
    f"{TOP}/README.md": b"x",
    f"{TOP}/LICENSE": b"x",
    f"{TOP}/_internal/openchem/chem/data/elements.json": b"{}",
}


def test_a_good_archive_has_no_problems(tmp_path):
    assert release.validate_inventory(_zip(tmp_path / "a.zip", GOOD), VERSION) == []


@pytest.mark.parametrize(
    "extra, fragment",
    [
        ({"../evil.txt": b"x"}, "escapes"),
        ({"/abs.txt": b"x"}, "escapes"),
        ({"C:/x.txt": b"x"}, "escapes"),
        ({f"{TOP}/a/../../b": b"x"}, "escapes"),
        ({"OpenChemStudio/OpenChemStudio.exe": b"x"}, "outside"),  # the old unversioned folder
        ({f"{TOP}/_internal/__pycache__/m.pyc": b"x"}, "debris"),
        ({f"{TOP}/_internal/openchem/docs/USER_GUIDE.md": b"x"}, "must not ship loose"),
        ({f"{TOP}/_internal/openchem/_integrity.py": b"x"}, "must not ship loose"),
        ({f"{TOP}/_internal/openchem/_build_stamp.py": b"x"}, "must not ship loose"),
    ],
)
def test_each_forbidden_entry_is_named(tmp_path, extra, fragment):
    problems = release.validate_inventory(_zip(tmp_path / "a.zip", {**GOOD, **extra}), VERSION)
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize("missing", release.REQUIRED)
def test_each_required_file_is_checked(tmp_path, missing):
    entries = {k: v for k, v in GOOD.items() if not k.endswith("/" + missing)}
    problems = release.validate_inventory(_zip(tmp_path / "a.zip", entries), VERSION)
    assert any(missing in p for p in problems)


def test_an_empty_or_unreadable_archive_is_a_problem(tmp_path):
    assert release.validate_inventory(_zip(tmp_path / "e.zip", {}), VERSION)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert release.validate_inventory(bad, VERSION)
    assert release.validate_inventory(tmp_path / "absent.zip", VERSION)


def test_pycache_in_the_build_is_left_out_of_the_zip(tmp_path):
    dist = _dist(tmp_path)
    (dist / "plugins" / "x" / "__pycache__").mkdir()
    (dist / "plugins" / "x" / "__pycache__" / "p.pyc").write_bytes(b"c")
    final = release.build_release(dist, VERSION, tmp_path / "out", smoke=lambda e: True)
    assert not any("__pycache__" in n for n in _names(final))


def test_the_cli_refuses_an_unknown_version(tmp_path, capsys):
    code = release.main(["--dist", str(_dist(tmp_path)), "--version", "unknown", "--out-dir", str(tmp_path / "o"), "--no-smoke"])
    assert code == 1 and "unknown" in capsys.readouterr().err
