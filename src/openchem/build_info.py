"""What a bug report needs, collected in one place.

The version and the library versions are easy. The **commit** is the part
that takes real work, because a frozen build has no `.git` directory to ask
-- PyInstaller ships the code, not the repository. So the commit has to be
baked in while the build still has a checkout around it: `build.ps1` writes
`_build_stamp.py` immediately before freezing, and this module prefers it
when it exists and falls back to asking git when running from source.

That asymmetry is the whole point. A version number alone does not identify
a build, because everything between two tags shares one.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata

#: How long to wait for `git rev-parse`. Generous enough for a cold disk,
#: short enough that a broken git install cannot hang the About dialog --
#: which is the one thing a diagnostics dialog must never do.
_GIT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class BuildInfo:
    version: str
    commit: str
    commit_source: str
    python: str
    platform_name: str
    libraries: dict[str, str] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)

    def as_text(self) -> str:
        """The form that goes in an issue -- plain text, one fact per line."""
        lines = [
            f"OpenChem Studio {self.version}",
            f"Commit:   {self.commit} ({self.commit_source})",
            f"Python:   {self.python}",
            f"Platform: {self.platform_name}",
            "",
            "Libraries:",
        ]
        lines += [f"  {name:<12} {value}" for name, value in self.libraries.items()]
        lines += ["", "External tools:"]
        lines += [f"  {name:<12} {value}" for name, value in self.tools.items()]
        return "\n".join(lines)


def _app_version() -> str:
    try:
        return metadata.version("openchem")
    except metadata.PackageNotFoundError:
        # A frozen build installs no distribution metadata, so this is the
        # normal path there rather than an error.
        return _stamped("version", "unknown")


def _stamped(name: str, default: str) -> str:
    try:
        from openchem import _build_stamp  # type: ignore[attr-defined]
    except ImportError:
        return default
    return str(getattr(_build_stamp, name, default))


def _commit() -> tuple[str, str]:
    """Returns (commit, where it came from) -- never raises."""
    stamped = _stamped("commit", "")
    if stamped:
        return stamped, "baked at build time"

    if getattr(sys, "frozen", False):
        # No stamp and no checkout. Saying so is far better than reporting a
        # blank field that reads as "no commit" rather than "not recorded".
        return "unknown", "frozen build, not stamped"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown", "git unavailable"
    if result.returncode != 0:
        return "unknown", "not a git checkout"
    return result.stdout.strip() or "unknown", "from the working checkout"


def _libraries() -> dict[str, str]:
    """Import-guarded throughout: every one of these is genuinely optional
    in some configuration, and a diagnostics dialog that crashes on a
    missing optional dependency is worse than useless -- it fails exactly
    when someone is trying to report that dependency being missing.
    """
    versions: dict[str, str] = {}

    try:
        import PySide6  # noqa: PLC0415

        versions["PySide6"] = PySide6.__version__
        from PySide6.QtCore import qVersion  # noqa: PLC0415

        versions["Qt"] = qVersion()
    except Exception:
        versions["PySide6"] = "not available"

    try:
        import rdkit  # noqa: PLC0415

        versions["RDKit"] = rdkit.__version__
    except Exception:
        versions["RDKit"] = "not available"

    try:
        from openbabel import openbabel as ob  # noqa: PLC0415

        versions["Open Babel"] = ob.OBReleaseVersion()
    except Exception:
        versions["Open Babel"] = "not installed (optional)"

    try:
        import numpy  # noqa: PLC0415

        versions["NumPy"] = numpy.__version__
    except Exception:
        versions["NumPy"] = "not available"

    return versions


def _tools(settings: object | None) -> dict[str, str]:
    """Resolved paths, not just booleans.

    "Vina: configured" is not actionable; a path that turns out to point at
    a binary the user moved is. That exact case cost real debugging time --
    a stale configured path reads identically to a working one until you
    look at it.
    """
    found: dict[str, str] = {}

    def configured(key: str) -> str:
        if settings is None:
            return "unknown (no settings)"
        value = ""
        try:
            value = str(settings.get(key, "") or "")  # type: ignore[attr-defined]
        except Exception:
            return "unknown"
        if not value:
            return "not configured"
        from pathlib import Path  # noqa: PLC0415

        return value if Path(value).exists() else f"{value}  [MISSING]"

    from openchem.chem.admet_providers import ADMET_PYTHON_SETTING  # noqa: PLC0415
    from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING  # noqa: PLC0415
    from openchem.services.sidecar_inventory import VINA_SETTING  # noqa: PLC0415

    found["Vina"] = configured(VINA_SETTING)
    found["ORCA"] = configured("orca/executable_path")
    found["pkasolver"] = configured(PKASOLVER_PYTHON_SETTING)
    found["ADMET"] = configured(ADMET_PYTHON_SETTING)

    for label, module_name in (("Java", "java_setup"), ("NMR index", "nmr_database_setup")):
        try:
            module = __import__(f"openchem.services.{module_name}", fromlist=["describe_status"])
            found[label] = module.describe_status()
        except Exception:
            found[label] = "unknown"

    return found


def collect(settings: object | None = None) -> BuildInfo:
    """Gather everything. `settings` is the app's Settings when there is one
    -- it is optional so this stays callable from a script or a test without
    standing up the whole container.
    """
    commit, source = _commit()
    return BuildInfo(
        version=_app_version(),
        commit=commit,
        commit_source=source,
        python=f"{platform.python_version()} ({platform.architecture()[0]})",
        platform_name=f"{platform.system()} {platform.release()}",
        libraries=_libraries(),
        tools=_tools(settings),
    )
