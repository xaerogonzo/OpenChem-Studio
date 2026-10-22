"""Compile the Windows installer (Inno Setup) from a built `dist/OpenChemStudio`.

    uv run --no-sync python tools/make_installer.py --dist dist/OpenChemStudio --version 0.10.0 --out-dir dist

Writes `OpenChemStudio-v<version>-windows-x64-setup.exe` and adds its line to
`SHA256SUMS.txt` beside it. The script is `packaging/openchem.iss`, whose header
says what the installer does. This tool only finds the compiler, passes the
version and the source folder, and keeps the same promise as the zip: compile into a
scratch folder, promote only a finished file, never overwrite a release without
`--force`.

`--test-build` compiles the TEST variant (own AppId, sandbox data folder and
registry key, faster compression) that `tools/drive_installer.py` drives, so removal
can be tested without touching anybody's real data. It is never a release.

NOT SIGNED. See the script header.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "packaging" / "openchem.iss"


class InstallerError(RuntimeError):
    """The installer cannot be made."""


def installer_name(version: str, *, test_build: bool = False) -> str:
    return "OpenChemStudio-TEST-setup.exe" if test_build else f"OpenChemStudio-v{version}-windows-x64-setup.exe"


def find_iscc(environ: dict[str, str] | None = None, which=shutil.which) -> Path:
    """The Inno Setup compiler: `ISCC` in the environment, on PATH, or where its installer puts it.

    Inno's own installer defaults to Program Files (all users) but offers a per-user
    install under `%LOCALAPPDATA%\\Programs`, which is where it is on a machine set up
    that way; both are checked.
    """
    env = os.environ if environ is None else environ
    candidates: list[Path] = []
    if env.get("ISCC"):
        candidates.append(Path(env["ISCC"]))
    on_path = which("ISCC")
    if on_path:
        candidates.append(Path(on_path))
    for variable, suffix in (
        ("LOCALAPPDATA", "Programs/Inno Setup 6"),
        ("ProgramFiles(x86)", "Inno Setup 6"),
        ("ProgramFiles", "Inno Setup 6"),
    ):
        if env.get(variable):
            candidates.append(Path(env[variable]) / suffix / "ISCC.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise InstallerError(
        "Inno Setup 6 was not found (looked for ISCC.exe in: "
        + ", ".join(str(c) for c in candidates)
        + "). Install it with: winget install --id JRSoftware.InnoSetup"
    )


def check_version(version: str) -> None:
    if not version or version.lower() == "unknown" or not all(c.isdigit() or c == "." for c in version):
        raise InstallerError(f"refusing to build an installer with the version {version!r}")


def update_checksums(sums_path: Path, installer: Path) -> None:
    """Add or replace this file's line in SHA256SUMS.txt, keeping every other line.

    UTF-8, no BOM, LF, `<sha256> *<name>`, the way sha256sum writes it.
    """
    digest = hashlib.sha256()
    with installer.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    line = f"{digest.hexdigest()} *{installer.name}"
    kept: list[str] = []
    if sums_path.exists():
        kept = [
            existing
            for existing in sums_path.read_text(encoding="utf-8").splitlines()
            if existing.strip() and not existing.rstrip().endswith(f" *{installer.name}")
        ]
    sums_path.write_bytes(("\n".join(kept + [line]) + "\n").encode("utf-8"))


def compile_installer(
    dist: Path,
    version: str,
    out_dir: Path,
    *,
    force: bool = False,
    test_build: bool = False,
    run=subprocess.run,
    iscc: Path | None = None,
) -> Path:
    check_version(version)
    if not (dist / "OpenChemStudio.exe").is_file():
        raise InstallerError(f"{dist} does not hold a built application (no OpenChemStudio.exe)")
    compiler = iscc or find_iscc()
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / installer_name(version, test_build=test_build)
    if final.exists() and not force:
        raise InstallerError(f"{final.name} already exists; pass --force to replace it")

    scratch = Path(tempfile.mkdtemp(prefix="openchem-installer-", dir=out_dir))
    try:
        command = [
            str(compiler),
            "/Q",
            f"/DAppVersion={version}",
            f"/DSourceDir={dist.resolve()}",
            f"/DOutputDir={scratch}",
        ]
        if test_build:
            command.append("/DTestBuild")
        command.append(str(SCRIPT))
        result = run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallerError(f"the Inno Setup compiler failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}")
        built = scratch / installer_name(version, test_build=test_build)
        if not built.is_file():
            raise InstallerError(f"the compiler reported success but {built.name} is not there")
        os.replace(built, final)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not test_build:
        update_checksums(out_dir / "SHA256SUMS.txt", final)
    print(f"make_installer: {final} ({final.stat().st_size / 1e6:.0f} MB)")
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--test-build", action="store_true")
    args = parser.parse_args(argv)
    try:
        compile_installer(args.dist, args.version, args.out_dir, force=args.force, test_build=args.test_build)
    except InstallerError as exc:
        print(f"make_installer: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
