"""The installer's build tool, and the promises its Inno Setup script makes.

The silent lifecycle (install, upgrade, uninstall, the removal options) is driven
against a REAL compiled installer by `tools/drive_installer.py`, which `build.ps1
-Installer` runs; it needs Inno Setup and minutes, so it is not a unit test. What is
held here is everything that can be checked without compiling: the compiler lookup,
the version and overwrite rules, what a failed compile leaves behind, the checksum
file, and the properties of `packaging/openchem.iss` that, if edited away, would turn
the installer into something other than what the docs say it is.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = _load("make_installer")
SCRIPT = (ROOT / "packaging" / "openchem.iss").read_text(encoding="utf-8")


def _dist(tmp_path) -> Path:
    dist = tmp_path / "dist" / "OpenChemStudio"
    dist.mkdir(parents=True)
    (dist / "OpenChemStudio.exe").write_bytes(b"MZ")
    return dist


class _FakeCompiler:
    """Stands in for ISCC: records the command, and (optionally) writes the setup it would."""

    def __init__(self, *, succeed=True, write=True):
        self.succeed, self.write, self.commands = succeed, write, []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        out = Path(next(a for a in command if a.startswith("/DOutputDir=")).split("=", 1)[1])
        version = next(a for a in command if a.startswith("/DAppVersion=")).split("=", 1)[1]
        if self.succeed and self.write:
            (out / installer.installer_name(version, test_build="/DTestBuild" in command)).write_bytes(b"setup bytes")
        return SimpleNamespace(returncode=0 if self.succeed else 1, stdout="compiler said X", stderr="")


# --- finding the compiler ---------------------------------------------------------


def _fake_iscc(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ISCC.exe"
    path.write_bytes(b"x")
    return path


def test_the_compiler_is_found_from_the_environment_first(tmp_path):
    chosen = _fake_iscc(tmp_path / "chosen")
    other = _fake_iscc(tmp_path / "Programs" / "Inno Setup 6")
    found = installer.find_iscc({"ISCC": str(chosen), "LOCALAPPDATA": str(tmp_path)}, which=lambda n: None)
    assert found == chosen and other.is_file()


def test_the_compiler_is_found_where_a_per_user_install_puts_it(tmp_path):
    expected = _fake_iscc(tmp_path / "Programs" / "Inno Setup 6")
    assert installer.find_iscc({"LOCALAPPDATA": str(tmp_path)}, which=lambda n: None) == expected


def test_the_compiler_is_found_in_program_files(tmp_path):
    expected = _fake_iscc(tmp_path / "Inno Setup 6")
    assert installer.find_iscc({"ProgramFiles(x86)": str(tmp_path)}, which=lambda n: None) == expected


def test_a_missing_compiler_says_how_to_get_it(tmp_path):
    with pytest.raises(installer.InstallerError, match="winget install --id JRSoftware.InnoSetup"):
        installer.find_iscc({"LOCALAPPDATA": str(tmp_path)}, which=lambda n: None)


# --- versions, names, checksums ------------------------------------------------------


@pytest.mark.parametrize("version", ["", "unknown", "UNKNOWN", "1.0-beta", "a/b", "1 2"])
def test_a_bad_version_is_refused(version):
    with pytest.raises(installer.InstallerError):
        installer.check_version(version)


def test_the_names_match_the_zip_convention_and_the_test_build_cannot_be_mistaken_for_a_release():
    assert installer.installer_name("0.10.0") == "OpenChemStudio-v0.10.0-windows-x64-setup.exe"
    assert installer.installer_name("0.10.0", test_build=True) == "OpenChemStudio-TEST-setup.exe"


def test_the_checksum_line_is_added_replaced_and_leaves_other_lines_alone(tmp_path):
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_bytes(b"aaaa *OpenChemStudio-v1-windows-x64.zip\n")
    setup = tmp_path / "OpenChemStudio-v1-windows-x64-setup.exe"
    setup.write_bytes(b"first")
    installer.update_checksums(sums, setup)
    setup.write_bytes(b"second")
    installer.update_checksums(sums, setup)  # replaced, not duplicated
    lines = sums.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "aaaa *OpenChemStudio-v1-windows-x64.zip" and len(lines) == 2
    import hashlib

    assert lines[1] == f"{hashlib.sha256(b'second').hexdigest()} *{setup.name}"
    raw = sums.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw


def test_the_zip_tool_keeps_the_installers_checksum_line(tmp_path):
    zip_tool = _load("make_release_zip")
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_bytes(b"bbbb *OpenChemStudio-v1-windows-x64-setup.exe\ncccc *OpenChemStudio-v1-windows-x64.zip\n")
    archive = tmp_path / "x.zip"
    archive.write_bytes(b"zip bytes")
    zip_tool.write_checksums(tmp_path / "new.txt", archive, "OpenChemStudio-v1-windows-x64.zip", keep_from=sums)
    lines = (tmp_path / "new.txt").read_text(encoding="utf-8").splitlines()
    assert any(l.endswith("*OpenChemStudio-v1-windows-x64-setup.exe") and l.startswith("bbbb") for l in lines)
    assert sum(l.endswith("*OpenChemStudio-v1-windows-x64.zip") for l in lines) == 1
    assert not any(l.startswith("cccc") for l in lines)


# --- compiling -----------------------------------------------------------------------


def test_the_compiler_gets_the_version_the_source_and_a_scratch_output(tmp_path):
    fake = _FakeCompiler()
    out = tmp_path / "out"
    final = installer.compile_installer(_dist(tmp_path), "9.9.9", out, run=fake, iscc=Path("ISCC.exe"))
    (command,) = fake.commands
    assert "/DAppVersion=9.9.9" in command and "/DTestBuild" not in command
    assert any(a.startswith("/DSourceDir=") and a.endswith("OpenChemStudio") for a in command)
    assert command[-1].endswith("openchem.iss")
    scratch = next(a for a in command if a.startswith("/DOutputDir=")).split("=", 1)[1]
    assert Path(scratch) != out and not Path(scratch).exists(), "compiled into scratch, which is removed"
    assert final == out / "OpenChemStudio-v9.9.9-windows-x64-setup.exe" and final.read_bytes() == b"setup bytes"
    assert "*OpenChemStudio-v9.9.9-windows-x64-setup.exe" in (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert list(out.iterdir()) == [final, out / "SHA256SUMS.txt"] or set(out.iterdir()) == {final, out / "SHA256SUMS.txt"}


def test_a_test_build_passes_the_define_and_is_never_checksummed_as_a_release(tmp_path):
    fake = _FakeCompiler()
    out = tmp_path / "out"
    final = installer.compile_installer(_dist(tmp_path), "9.9.9", out, run=fake, iscc=Path("ISCC.exe"), test_build=True)
    assert "/DTestBuild" in fake.commands[0] and final.name == "OpenChemStudio-TEST-setup.exe"
    assert not (out / "SHA256SUMS.txt").exists()


def test_a_failed_compile_leaves_nothing_and_shows_the_compilers_words(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(installer.InstallerError, match="compiler said X"):
        installer.compile_installer(_dist(tmp_path), "9.9.9", out, run=_FakeCompiler(succeed=False), iscc=Path("ISCC.exe"))
    assert list(out.iterdir()) == []


def test_a_compiler_that_claims_success_without_producing_a_file_is_an_error(tmp_path):
    with pytest.raises(installer.InstallerError, match="not there"):
        installer.compile_installer(_dist(tmp_path), "9.9.9", tmp_path / "o", run=_FakeCompiler(write=False), iscc=Path("ISCC.exe"))


def test_an_existing_installer_is_not_overwritten_without_force(tmp_path):
    out = tmp_path / "out"
    first = installer.compile_installer(_dist(tmp_path), "9.9.9", out, run=_FakeCompiler(), iscc=Path("ISCC.exe"))
    before = first.read_bytes()
    with pytest.raises(installer.InstallerError, match="already exists"):
        installer.compile_installer(_dist(tmp_path) if False else tmp_path / "dist" / "OpenChemStudio", "9.9.9", out, run=_FakeCompiler(), iscc=Path("ISCC.exe"))
    assert first.read_bytes() == before
    installer.compile_installer(tmp_path / "dist" / "OpenChemStudio", "9.9.9", out, run=_FakeCompiler(), iscc=Path("ISCC.exe"), force=True)


def test_a_folder_that_is_not_a_build_is_refused(tmp_path):
    with pytest.raises(installer.InstallerError, match="built application"):
        installer.compile_installer(tmp_path, "9.9.9", tmp_path / "o", run=_FakeCompiler(), iscc=Path("ISCC.exe"))


# --- the script's promises --------------------------------------------------------------


def _code(section: str) -> str:
    """A script section without its `;` comment lines."""
    return "\n".join(line for line in section.splitlines() if not line.lstrip().startswith(";"))


def _ids():
    import re

    return re.findall(r'#define AppIdGuid "(\{\{[0-9A-F-]+\})"', SCRIPT)


def test_the_test_build_has_its_own_app_id_so_it_cannot_clobber_a_real_install():
    """The shipped id is the one `tools/drive_installer.py` refuses to run over."""
    ids = _ids()
    assert len(ids) == 2 and ids[0] != ids[1]
    test_tool = _load("drive_installer")
    assert ids[0].replace("{{", "").replace("}", "") == test_tool.TEST_APP_ID
    assert ids[1].replace("{{", "").replace("}", "") == test_tool.REAL_APP_ID


def test_the_person_chooses_per_user_or_all_users_and_per_user_is_the_default():
    assert "PrivilegesRequired=lowest" in SCRIPT
    assert "PrivilegesRequiredOverridesAllowed=dialog" in SCRIPT
    assert "DefaultDirName={autopf}" in SCRIPT


def test_an_upgrade_clears_the_old_runtime_but_never_the_plugins_folder():
    install_delete = _code(SCRIPT.split("[InstallDelete]")[1].split("[Icons]")[0])
    assert r'Name: "{app}\_internal"' in install_delete
    assert "plugins" not in install_delete, "people add their own plugins there"
    uninstall_delete = _code(SCRIPT.split("[UninstallDelete]")[1].split("[Code]")[0])
    assert r'Name: "{app}\_internal"' in uninstall_delete
    assert "plugins" not in uninstall_delete


def test_uninstall_asks_and_defaults_to_keeping_everything():
    assert "InitializeUninstall" in SCRIPT and "UninstallSilent()" in SCRIPT
    assert "REMOVESETTINGS" in SCRIPT and "REMOVEDATA" in SCRIPT
    assert ".Checked := True" not in SCRIPT, "a removal box must never start ticked"
    assert "Result := False" in SCRIPT, "Cancel must abort the uninstall"


def test_removal_is_confined_to_the_applications_own_folder():
    assert "Pos('OpenChemStudio', ExtractFileName(Folder)) = 1" in SCRIPT
    assert "never removed here" in SCRIPT  # a moved data folder is only reported


def test_the_places_the_script_cleans_are_the_ones_the_application_uses():
    """Drift here means 'remove my data' removes nothing, or the wrong thing."""
    from openchem import paths
    from openchem.app import settings

    assert paths.APP_NAME == "OpenChemStudio"
    assert r"{localappdata}\OpenChemStudio'" in SCRIPT, "the default data folder"
    assert f"Software\\{settings.ORG_NAME}'" in SCRIPT, "the QSettings registry key"
    assert paths._POINTER_FILENAME in SCRIPT, "the file that records a moved data folder"


def test_the_installer_is_documented_as_unsigned_and_has_no_signing_hook():
    assert "NOT SIGNED" in SCRIPT
    assert "SignTool" not in SCRIPT, "an untested signing hook in a release path is worse than none"


def test_the_installer_carries_the_licence_and_closes_a_running_copy():
    assert r"LicenseFile={#SourceDir}\LICENSE" in SCRIPT
    assert "CloseApplications=yes" in SCRIPT


def test_the_build_makes_and_tests_the_installer_and_refuses_a_dirty_tree_for_it():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert "[switch]$Installer" in build
    assert "make_installer.py" in build and "drive_installer.py" in build
    assert "$dirty -and ($Release -or $Installer)" in build
