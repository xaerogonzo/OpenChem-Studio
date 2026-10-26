"""Drive a compiled installer through install, upgrade and uninstall, silently, and check the results.

    uv run --no-sync python tools/drive_installer.py --installer dist/OpenChemStudio-v0.10.0-windows-x64-setup.exe
    uv run --no-sync python tools/drive_installer.py --installer <TEST build> --removal

Everything runs PER-USER (`/CURRENTUSER`, no administrator, no prompt) into a scratch
folder whose name contains a space. What it checks:

  * INSTALL puts the application there, registers an uninstall entry, and the installed
    exe passes the frozen smoke test (`tools/frozen_smoke.py`);
  * UPGRADE over it removes a file the new version no longer ships (a stale `_internal`
    file) and keeps a plugin somebody added;
  * UNINSTALL removes the runtime and the registration, KEEPS the added plugin, and leaves
    the user's data folder and settings exactly as they were (silent uninstall keeps
    everything unless told otherwise).

`--removal` additionally drives the data-removal options and needs the TEST build
(`tools/make_installer.py --test-build`), whose data folder and registry key are a
sandbox, so no real data can be touched: `/REMOVEDATA=1` removes the sandbox data
folder, `/REMOVESETTINGS=1` the sandbox key, a data folder that was MOVED elsewhere is
never removed, and a folder whose name is not the application's is refused.

SAFETY: the run refuses to start when the installer's AppId is already registered on
this machine, because installing over a real installation would replace its uninstall
entry. The all-users path needs an elevation prompt and is checked by hand.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

REAL_APP_ID = "C33CE7E7-F8EE-4EEA-82B6-142ECE2F7F4F"
TEST_APP_ID = "C33CE7E7-F8EE-4EEA-82B6-142ECE2F7F40"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
TEST_SETTINGS_KEY = r"Software\OpenChemStudio-TEST"


class Failure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)
    print(f"  ok: {message}")


# --- the registry (Windows only; imported lazily so the module loads anywhere) ------


def _winreg():
    import winreg

    return winreg


def registered(app_id: str) -> bool:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{UNINSTALL_KEY}\{{{app_id}}}_is1"):
            return True
    except OSError:
        return False


def key_exists(path: str) -> bool:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path):
            return True
    except OSError:
        return False


def make_key(path: str) -> None:
    winreg = _winreg()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, "marker", 0, winreg.REG_SZ, "kept?")


def delete_key(path: str) -> None:
    winreg = _winreg()
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


# --- running the installer --------------------------------------------------------


def run_setup(installer: Path, target: Path, log: Path, extra: list[str] = ()) -> int:
    command = [
        str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
        f"/DIR={target}", f"/LOG={log}", "/TASKS=", *extra,
    ]
    return subprocess.run(command, timeout=900).returncode


def run_uninstall(target: Path, extra: list[str] = (), wait_seconds: float = 240.0) -> int:
    """Run the uninstaller and WAIT FOR IT TO FINISH.

    Inno's uninstaller starts, copies itself to a temp folder, launches a SECOND PHASE and
    exits with 0 at once, so the process this returns from has done almost nothing. Reading
    the results then reads a half-finished uninstall. The second phase writes `Log closed.`
    as its last line, so the wait is on that, from a log this function asks for.
    """
    import tempfile
    import time

    uninstaller = target / "unins000.exe"
    if not uninstaller.is_file():
        return -1
    log = Path(tempfile.mkdtemp(prefix="openchem uninstall log ")) / "uninstall.log"
    code = subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}", *extra], timeout=300
    ).returncode
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            if "Log closed." in log.read_text(encoding="utf-8", errors="replace"):
                return code
        except OSError:
            pass
        time.sleep(0.5)
    raise Failure("the uninstaller never finished (its log did not close)")


def installed_snapshot(folder: Path) -> dict[str, int]:
    return {p.relative_to(folder).as_posix(): p.stat().st_size for p in sorted(folder.rglob("*")) if p.is_file()}


# --- the lifecycle ------------------------------------------------------------------


def lifecycle(installer: Path, app_id: str, scratch: Path, smoke: bool = True) -> Path:
    target = scratch / "Open Chem Install"
    log = scratch / "setup.log"
    print(f"install (per-user) -> {target}")
    check(run_setup(installer, target, log) == 0, "the installer exits 0")
    exe = target / "OpenChemStudio.exe"
    check(exe.is_file(), "the application is installed")
    check((target / "_internal" / "openchem" / "chem" / "data" / "elements.json").is_file(), "its data files are installed")
    check(registered(app_id), "an uninstall entry is registered for this user")
    check((target / "unins000.exe").is_file(), "an uninstaller is installed")

    if smoke:
        import frozen_smoke

        judgement, _ = frozen_smoke.run_smoke([str(exe)])
        check(judgement.ok, "the INSTALLED application passes the smoke test")

    print("upgrade over it")
    stale = target / "_internal" / "stale_from_an_older_version.dll"
    stale.write_bytes(b"old")
    mine = target / "plugins" / "my_own_plugin"
    mine.mkdir(parents=True, exist_ok=True)
    (mine / "plugin.py").write_text("# added by a person\n", encoding="utf-8")
    check(run_setup(installer, target, log) == 0, "installing again over it exits 0")
    check(not stale.exists(), "a file the new version does not ship is removed (no mixed versions)")
    check((mine / "plugin.py").is_file(), "a plugin the person added is kept")
    check(exe.is_file() and registered(app_id), "the application and its registration are intact")
    return target


def uninstall_and_check(target: Path, app_id: str, keep_check: list[Path]) -> None:
    print("uninstall (silent: keeps everything)")
    before = {p: p.read_bytes() for p in keep_check if p.is_file()}
    check(run_uninstall(target) == 0, "the uninstaller exits 0")
    check(not (target / "OpenChemStudio.exe").exists(), "the application is removed")
    check(not (target / "_internal").exists(), "the runtime folder is removed")
    check(not registered(app_id), "the uninstall entry is gone")
    check((target / "plugins" / "my_own_plugin" / "plugin.py").is_file(), "a plugin the person added is NOT deleted")
    for path, content in before.items():
        check(path.is_file() and path.read_bytes() == content, f"user data is untouched: {path.name}")


def removal_checks(installer: Path, scratch: Path) -> None:
    """Needs the TEST build: its data folder and registry key are a sandbox."""
    print("removal options (sandbox data folder and registry key)")
    data = scratch / "OpenChemStudio-TEST"
    for variant, flags, expect_data_gone, expect_key_gone, label in (
        ("none", [], False, False, "no flags: nothing extra is removed"),
        ("settings", ["/REMOVESETTINGS=1"], False, True, "/REMOVESETTINGS=1 removes only the settings key"),
        ("data", ["/REMOVEDATA=1"], True, False, "/REMOVEDATA=1 removes only the data folder"),
        ("both", ["/REMOVESETTINGS=1", "/REMOVEDATA=1"], True, True, "both flags remove both"),
    ):
        target = scratch / f"Install {variant}"
        check(run_setup(installer, target, scratch / f"{variant}.log", [f"/TESTDATADIR={data}"]) == 0, f"[{variant}] installs")
        data.mkdir(parents=True, exist_ok=True)
        (data / "cache.bin").write_bytes(b"cache")
        make_key(TEST_SETTINGS_KEY)
        check(run_uninstall(target, [f"/TESTDATADIR={data}", *flags]) == 0, f"[{variant}] uninstalls")
        check((not data.exists()) == expect_data_gone, f"[{variant}] {label} (data folder)")
        check((not key_exists(TEST_SETTINGS_KEY)) == expect_key_gone, f"[{variant}] {label} (settings key)")
        delete_key(TEST_SETTINGS_KEY)
        if data.exists():
            for child in data.iterdir():
                child.unlink()
            data.rmdir()

    print("a data folder that was MOVED is never removed")
    default = scratch / "OpenChemStudio-TEST"
    moved = scratch / "Big Drive" / "my data"
    moved.mkdir(parents=True)
    (moved / "orca.bin").write_bytes(b"gigabytes")
    default.mkdir(parents=True, exist_ok=True)
    (default / "data_root.txt").write_text(str(moved), encoding="utf-8")
    target = scratch / "Install moved"
    check(run_setup(installer, target, scratch / "moved.log", [f"/TESTDATADIR={default}"]) == 0, "[moved] installs")
    check(run_uninstall(target, [f"/TESTDATADIR={default}", "/REMOVEDATA=1"]) == 0, "[moved] uninstalls")
    check(not default.exists(), "[moved] the default folder (with its pointer file) is removed")
    check((moved / "orca.bin").is_file(), "[moved] the folder the person moved their data to is untouched")

    print("a folder that is not the application's own is refused")
    stranger = scratch / "Documents"
    stranger.mkdir()
    (stranger / "thesis.docx").write_bytes(b"precious")
    target = scratch / "Install stranger"
    check(run_setup(installer, target, scratch / "stranger.log", [f"/TESTDATADIR={stranger}"]) == 0, "[guard] installs")
    check(run_uninstall(target, [f"/TESTDATADIR={stranger}", "/REMOVEDATA=1"]) == 0, "[guard] uninstalls")
    check((stranger / "thesis.docx").is_file(), "[guard] a folder not named for the application is never deleted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--removal", action="store_true", help="also drive the removal options (TEST build only)")
    parser.add_argument("--no-smoke", action="store_true")
    parser.add_argument("--keep", action="store_true", help="keep the scratch folder")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("drive_installer: Windows only", file=sys.stderr)
        return 2
    if not args.installer.is_file():
        print(f"drive_installer: no installer at {args.installer}", file=sys.stderr)
        return 2
    is_test = "TEST" in args.installer.name
    app_id = TEST_APP_ID if is_test else REAL_APP_ID
    if args.removal and not is_test:
        print("drive_installer: --removal needs the TEST build (tools/make_installer.py --test-build)", file=sys.stderr)
        return 2
    if registered(app_id):
        print(
            "drive_installer: refusing to run: this installer's AppId is already registered on this machine, "
            "and installing over a real installation would replace its uninstall entry. Uninstall it first.",
            file=sys.stderr,
        )
        return 2

    scratch = Path(tempfile.mkdtemp(prefix="openchem installer test "))
    marker = scratch / "userdata" / "OpenChemStudio-sentinel.txt"
    marker.parent.mkdir()
    marker.write_text("user data that an uninstall must not touch", encoding="utf-8")
    try:
        target = lifecycle(args.installer, app_id, scratch, smoke=not args.no_smoke)
        uninstall_and_check(target, app_id, [marker])
        if args.removal:
            removal_checks(args.installer, scratch)
    except (Failure, subprocess.TimeoutExpired) as exc:
        print(f"drive_installer: FAILED: {exc}", file=sys.stderr)
        for leftover in scratch.glob("*/unins000.exe"):
            subprocess.run([str(leftover), "/VERYSILENT", "/SUPPRESSMSGBOXES"], timeout=300, check=False)
        return 1
    finally:
        if not args.keep:
            import shutil

            shutil.rmtree(scratch, ignore_errors=True)
    print("drive_installer: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
