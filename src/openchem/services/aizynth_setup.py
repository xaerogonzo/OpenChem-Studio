"""Builds a working AiZynthFinder environment so nobody has to assemble one
from a GitHub zip and a documentation recipe.

The planner cannot live in this application's own environment: it needs
Python 3.10 to 3.12 and numpy below 2, while OpenChem Studio runs 3.13
and numpy 2. It is invoked out of process, the same way pkasolver and
ADMET are. The models and stock are not in the wheel; they are fetched
by the planner's own `download_public_data` after an ask-first
confirmation (`docs/SYNTHESIS_HELPER_DESIGN.md`).

Every version here is the combination the quality benchmark ran
(aizynthfinder 4.4.1, Python 3.12) plus the pin a fresh pip install
needs (`pyarrow<21`) or it will not import.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openchem import paths as app_paths

logger = logging.getLogger("openchem.services")

#: AiZynthFinder supports 3.10-3.12; 3.12 is what the quality benchmark ran.
_TARGET_PYTHON = "3.12"
#: The planner version the quality benchmark used (`docs/SYNTHESIS_HELPER_DESIGN.md` 0b).
PLANNER_PACKAGE = "aizynthfinder==4.4.1"
#: A fresh pip install of 4.4.1 resolves a pyarrow that needs NumPy 2; this pin does not.
PYARROW_PIN = "pyarrow<21"

#: Environment ~900 MB plus models and stock ~754 MB, measured 2026-10-19.
APPROX_DOWNLOAD_MB = 1700
#: Same measurement, stated in the ask-first confirmation as finished disk use.
APPROX_DISK_GB = 1.7

#: Hosts `download_public_data` fetches from (named so the privacy page can
#: list them; this module itself only starts that program).
PUBLIC_DATA_HOSTS = ("zenodo.org", "figshare.com")


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class AizynthSetupError(RuntimeError):
    """Setup failed. The message is meant to be shown to a user verbatim."""


def default_install_root() -> Path:
    """Beside the app's other tool data, not inside the source tree."""
    return app_paths.subdirectory("aizynthfinder_env")


def interpreter_for(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def config_for(root: Path) -> Path:
    return root / "data" / "config.yml"


def data_dir(root: Path) -> Path:
    return root / "data"


def find_uv() -> str | None:
    """uv is preferred because it can provision Python 3.12 on demand."""
    return shutil.which("uv")


def find_fallback_python() -> str | None:
    """An already-installed interpreter in aizynthfinder's supported range.

    Only consulted when uv is absent. The app's own 3.13 cannot be used.
    """
    for version in ("3.12", "3.11", "3.10"):
        if os.name == "nt":
            found = shutil.which("py")
            if found and _python_reports_version(found, ["-" + version], version):
                return f"{found} -{version}"
        candidate = shutil.which(f"python{version}")
        if candidate and _python_reports_version(candidate, [], version):
            return candidate
    return None


def _python_reports_version(executable: str, extra_args: list[str], expected: str) -> bool:
    try:
        result = subprocess.run(
            [executable, *extra_args, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == expected


def describe_prerequisites() -> str:
    if find_uv():
        return f"Ready: uv found, will provision Python {_TARGET_PYTHON} automatically."
    fallback = find_fallback_python()
    if fallback:
        return f"Ready: will use {fallback}."
    return (
        f"Cannot set up automatically: needs either uv (recommended -- it fetches "
        f"Python {_TARGET_PYTHON} for you) or an existing Python 3.10-3.12 on PATH. "
        f"This app's own Python {sys.version_info.major}.{sys.version_info.minor} "
        f"cannot be used: AiZynthFinder supports 3.10 to 3.12 only."
    )


def _run(command: list[str], step: str, timeout: int = 3600) -> None:
    logger.info("AiZynthFinder setup: %s -> %s", step, " ".join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AizynthSetupError(f"{step} timed out after {timeout}s") from exc
    except OSError as exc:
        raise AizynthSetupError(f"{step} could not start: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-600:]
        raise AizynthSetupError(f"{step} failed:\n{tail}")


def _public_data_complete(root: Path) -> bool:
    folder = data_dir(root)
    return all(
        (folder / name).is_file()
        for name in ("config.yml", "uspto_model.onnx", "uspto_templates.csv.gz", "zinc_stock.hdf5")
    )


def _downloader_for(python: Path) -> Path:
    scripts = python.parent
    name = "download_public_data.exe" if os.name == "nt" else "download_public_data"
    candidate = scripts / name
    if candidate.is_file():
        return candidate
    raise AizynthSetupError(
        f"aizynthfinder installed but its download_public_data command is missing at {candidate}."
    )


def install(root: Path | None = None, on_progress: ProgressCallback | None = None) -> tuple[Path, Path]:
    """Build the environment and fetch public models/stock.

    Returns `(python, config.yml)` to store in Settings. Safe to re-run:
    an existing interpreter is reused, pip install is idempotent, and a
    data folder that already holds the models is not downloaded again.
    """
    root = root or default_install_root()
    root.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv"
    python = interpreter_for(root)
    config = config_for(root)

    steps = [
        f"Creating a Python {_TARGET_PYTHON} environment",
        f"Installing {PLANNER_PACKAGE} and {PYARROW_PIN}",
        "Downloading public models and stock (~750 MB)",
        "Verifying the planner can read its configuration",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    uv = find_uv()

    report(0)
    if python.is_file():
        logger.info("AiZynthFinder setup: reusing the existing environment at %s", python)
    else:
        if uv:
            _run([uv, "venv", "--python", _TARGET_PYTHON, "--clear", str(venv)], steps[0])
        else:
            fallback = find_fallback_python()
            if not fallback:
                raise AizynthSetupError(describe_prerequisites())
            _run([*fallback.split(), "-m", "venv", str(venv)], steps[0])
        if not python.is_file():
            raise AizynthSetupError(f"Environment created but no interpreter at {python}")

    report(1)
    pip_install = ([uv, "pip", "install", "--python", str(python)] if uv else [str(python), "-m", "pip", "install"])
    _run([*pip_install, PLANNER_PACKAGE, PYARROW_PIN], steps[1])

    report(2)
    folder = data_dir(root)
    if _public_data_complete(root):
        logger.info("AiZynthFinder setup: reusing public data at %s", folder)
    else:
        folder.mkdir(parents=True, exist_ok=True)
        _run([str(_downloader_for(python)), str(folder)], steps[2], timeout=900)

    if not config.is_file():
        raise AizynthSetupError(f"download_public_data finished but no configuration at {config}")

    report(3)
    _verify(python, config)
    return python, config


def _verify(python: Path, config: Path) -> None:
    """Prove the planner imports and the files the configuration names are there.

    Deliberately not the External Tools Test search (aspirin, ~20-40 s):
    that is the Test button's job. Missing models are how a previous
    sidecar (STOUT) looked installed and then produced nothing.
    """
    from openchem.chem.aizynth_planner import inspect_environment
    from openchem.services.synthesis_planner_setup import assets_problem, explain_inspection, select_keys

    inspection = inspect_environment(python, config)
    if not inspection.ok:
        raise AizynthSetupError(explain_inspection(inspection, str(python)))

    class _Defaults:
        def get(self, key: str, default=""):
            return default

    expansion, stock, filter_name, problem = select_keys(inspection, _Defaults())
    if problem:
        raise AizynthSetupError(problem.capitalize() + ".")
    missing = assets_problem(inspection, expansion, stock, filter_name)
    if missing is not None:
        raise AizynthSetupError(f"{missing[1][:1].upper()}{missing[1][1:]}.")
