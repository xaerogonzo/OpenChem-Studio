"""Provides a Java runtime, because two features need one and Windows
ships none.

STOUT starts a JVM through jpype to reach CDK every time it loads, and
OPSIN (name-to-structure) is a Java library outright. Without Java both
are simply unavailable, and the error each produces on its own names
neither Java nor the fix.

WHY THIS CAN BE MANAGED RATHER THAN DELEGATED TO THE USER. Eclipse
Temurin publishes PORTABLE archives -- a zip that is extracted, not
installed. Nothing is registered, no installer runs, no system setting is
touched, and removing the directory removes it completely. That makes it
exactly the same shape as the pkasolver and STOUT environments this app
already manages, and it is why "install a JRE yourself" is not the only
honest option.

A SYSTEM JAVA ALWAYS WINS. If the machine already has one, that is what
gets used -- this is a fallback for machines without, not a preference.
Downloading a second runtime beside a working one would be wasteful and
would make version questions harder to answer later.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

import platformdirs
from openchem import paths as app_paths

logger = logging.getLogger("openchem.services")

_APP_NAME = "OpenChemStudio"

# Adoptium's official release API. Resolves to the current general
# availability build, so this does not go stale as releases move.
# A JRE, not a JDK: nothing here compiles Java, and the JRE is roughly
# half the size.
FEATURE_VERSION = 21
_API = (
    "https://api.adoptium.net/v3/binary/latest/"
    "{version}/ga/{os}/{arch}/jre/hotspot/normal/eclipse"
)

APPROX_DOWNLOAD_MB = 49


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class JavaSetupError(RuntimeError):
    """Setup failed, with a message meant to be shown verbatim."""


def default_install_root() -> Path:
    return app_paths.subdirectory("jre")


def _platform() -> tuple[str, str]:
    import platform

    system = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}.get(
        platform.system()
    )
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        machine
    )
    if system is None or arch is None:
        raise JavaSetupError(
            f"No Temurin build is published for {platform.system()}/{platform.machine()}. "
            "Install a JRE manually and make sure java is on PATH."
        )
    return system, arch


def download_url() -> str:
    system, arch = _platform()
    return _API.format(version=FEATURE_VERSION, os=system, arch=arch)


def _java_executable(home: Path) -> Path:
    return home / "bin" / ("java.exe" if os.name == "nt" else "java")


def _works(home: Path) -> bool:
    executable = _java_executable(home)
    if not executable.is_file():
        return False
    try:
        result = subprocess.run(
            [str(executable), "-version"], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def managed_java_home(root: Path | None = None) -> Path | None:
    """The runtime this app installed, if it is there and runs.

    Temurin's archive contains a single versioned top-level directory
    (`jdk-21.0.12+8-jre`), whose exact name changes with every release --
    so it is discovered rather than assumed, and re-discovered on each
    call so an upgrade does not need a stored path to be updated.
    """
    root = root or default_install_root()
    if not root.is_dir():
        return None
    if _works(root):
        return root
    for candidate in sorted(root.iterdir()):
        if candidate.is_dir() and _works(candidate):
            return candidate
    return None


def system_java_home() -> Path | None:
    """A Java the machine already had, found the way jpype would."""
    configured = os.environ.get("JAVA_HOME")
    if configured and _works(Path(configured)):
        return Path(configured)
    on_path = shutil.which("java")
    if on_path:
        # .../bin/java -> the home is its grandparent.
        home = Path(on_path).resolve().parent.parent
        if _works(home):
            return home
    return None


def java_home() -> Path | None:
    """The runtime to use, system first."""
    return system_java_home() or managed_java_home()


def environment_with_java(base: dict[str, str] | None = None) -> dict[str, str]:
    """A subprocess environment that can find a JVM.

    jpype locates a JVM through JAVA_HOME or the loader path, and a
    managed runtime is on neither -- so it is injected here rather than
    exported globally. Nothing outside the processes this app launches is
    affected, which is the point of managing it this way.
    """
    environment = dict(base if base is not None else os.environ)
    home = java_home()
    if home is not None:
        environment["JAVA_HOME"] = str(home)
        environment["PATH"] = str(home / "bin") + os.pathsep + environment.get("PATH", "")
    return environment


def describe_status() -> str:
    system = system_java_home()
    if system is not None:
        return f"Found: system Java at {system}"
    managed = managed_java_home()
    if managed is not None:
        return f"Found: managed Temurin runtime at {managed}"
    return (
        "Not found. STOUT (structure-to-name) and OPSIN (name-to-structure) both need Java. "
        f"'Set Up Automatically' downloads a portable Temurin JRE (~{APPROX_DOWNLOAD_MB} MB) "
        "into this app's data directory -- extracted, not installed, and used only by this app."
    )


def install(root: Path | None = None, on_progress: ProgressCallback | None = None) -> Path:
    """Download and extract a portable Temurin JRE. Returns its home.

    Refuses when a system Java already works, rather than installing a
    second one nobody asked for.
    """
    existing = system_java_home()
    if existing is not None:
        raise JavaSetupError(
            f"Java is already available at {existing} -- nothing to install. "
            "If STOUT still fails, the problem is elsewhere."
        )

    root = root or default_install_root()
    steps = [
        f"Downloading Temurin {FEATURE_VERSION} JRE (~{APPROX_DOWNLOAD_MB} MB)",
        "Extracting",
        "Verifying it runs",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    root.mkdir(parents=True, exist_ok=True)
    archive = root / "temurin.zip"

    report(0)
    try:
        with urlopen(download_url(), timeout=120) as response, archive.open("wb") as target:
            shutil.copyfileobj(response, target)
    except OSError as exc:
        raise JavaSetupError(f"Could not download the Java runtime: {exc}") from exc

    report(1)
    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root)
    except (OSError, zipfile.BadZipFile) as exc:
        raise JavaSetupError(f"The downloaded archive could not be extracted: {exc}") from exc
    finally:
        # The archive is ~49 MB and is never needed again -- extraction is
        # the install.
        archive.unlink(missing_ok=True)

    report(2)
    home = managed_java_home(root)
    if home is None:
        raise JavaSetupError(
            "The runtime was extracted but does not run. Remove "
            f"{root} and try again, or install a JRE manually."
        )
    # Executable bits do not survive a zip on POSIX.
    if os.name != "nt":
        for entry in (home / "bin").iterdir():
            entry.chmod(entry.stat().st_mode | 0o111)
    return home
