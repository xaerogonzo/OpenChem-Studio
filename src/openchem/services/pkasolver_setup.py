"""Builds a working pkasolver environment, so nobody has to assemble one
from a documentation recipe to unlock numeric pKa.

pkasolver cannot live in this application's own environment: it requires
`numpy<2` while OpenChem Studio runs numpy 2.x, and it is not
pip-installable at all on modern Python (its `setup.py` uses `versioneer`,
which calls the `configparser.SafeConfigParser` removed in 3.12). So it
gets its own virtual environment and is invoked out of process, exactly
how this app already treats ORCA and Vina.

Every version here is pinned because it was verified live, and each pin
exists for a reason that was discovered the hard way (see `_STEPS`).
Loosening any of them silently breaks prediction rather than failing
loudly, which is why they are constants rather than ranges.
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

import platformdirs
from openchem import paths as app_paths

logger = logging.getLogger("openchem.services")

_APP_NAME = "OpenChemStudio"

PKASOLVER_REPO = "https://github.com/mayrf/pkasolver.git"

# The verified-working combination. Each pin is load-bearing:
#
#   torch 2.3.0     -- 2.4.0 fails on Windows with a missing fbgemm.dll
#                      dependency; 2.3.0 is the newest that loads cleanly.
#   torch-geometric -- 2.0.1 exactly. Newer versions build GINConv's inner
#                      network as their own MLP class, so pkasolver's 2021
#                      checkpoints (raw Sequential + BatchNorm) will not
#                      load into them at all.
#   scatter/sparse  -- from PyG's own wheel index, which publishes PREBUILT
#                      Windows wheels. This is what makes a C++ compiler
#                      unnecessary; building them from source does need one.
#   numpy < 2       -- pkasolver hits NumPy 2's stricter float(array).
#   scipy < 1.14    -- modern scipy uses np.long, gone in numpy 1.26.
TORCH_VERSION = "2.3.0"
_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
_PYG_WHEEL_INDEX = f"https://data.pyg.org/whl/torch-{TORCH_VERSION}+cpu.html"

# torch 2.3.0 publishes wheels for cp38-cp312 only -- this app itself runs
# on 3.13, so the environment CANNOT be built from sys.executable and needs
# its own interpreter provisioned.
_TARGET_PYTHON = "3.12"

APPROX_DOWNLOAD_MB = 900
APPROX_DISK_GB = 2.3


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class PkasolverSetupError(RuntimeError):
    """Setup failed. The message is meant to be shown to a user verbatim,
    so it names what failed and what to do, not just a return code."""


def default_install_root() -> Path:
    """Beside the app's other tool data, not inside the source tree -- an
    installed copy of this app has no writable source directory."""
    return app_paths.subdirectory("pkasolver_env")


def interpreter_for(root: Path) -> Path:
    """Where the venv's interpreter lands, per platform."""
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def find_uv() -> str | None:
    """uv is strongly preferred because it can PROVISION a Python 3.12 on
    demand; the app itself runs 3.13, which torch 2.3.0 has no wheels for.
    Without uv the user must already have a 3.10-3.12 available."""
    return shutil.which("uv")


def find_fallback_python() -> str | None:
    """An already-installed interpreter in torch 2.3.0's supported range.
    Only consulted when uv is absent."""
    for version in ("3.12", "3.11", "3.10"):
        # Windows ships the `py` launcher; POSIX uses versioned names.
        if os.name == "nt":
            found = shutil.which("py")
            if found and _python_reports_version(f"{found}", ["-" + version], version):
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
    """What the user needs before setup can run -- surfaced in the dialog
    BEFORE they commit to a multi-gigabyte download."""
    if find_uv():
        return f"Ready: uv found, will provision Python {_TARGET_PYTHON} automatically."
    fallback = find_fallback_python()
    if fallback:
        return f"Ready: will use {fallback}."
    return (
        f"Cannot set up automatically: needs either uv (recommended -- it fetches "
        f"Python {_TARGET_PYTHON} for you) or an existing Python 3.10-3.12 on PATH. "
        f"This app's own Python {sys.version_info.major}.{sys.version_info.minor} "
        f"cannot be used: PyTorch {TORCH_VERSION} publishes no wheels for it."
    )


def _run(command: list[str], step: str, cwd: Path | None = None, timeout: int = 3600) -> None:
    logger.info("pkasolver setup: %s -> %s", step, " ".join(command))
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise PkasolverSetupError(f"{step} timed out after {timeout}s") from exc
    except OSError as exc:
        raise PkasolverSetupError(f"{step} could not start: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-600:]
        raise PkasolverSetupError(f"{step} failed:\n{tail}")


def install(root: Path | None = None, on_progress: ProgressCallback | None = None) -> Path:
    """Builds the environment and returns the interpreter path to store in
    Settings. Raises `PkasolverSetupError` with a user-readable message on
    any failure.

    Safe to re-run: every step either overwrites or is idempotent, so a
    partially-completed setup can be repaired by running it again rather
    than requiring manual cleanup.
    """
    root = root or default_install_root()
    root.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv"
    python = interpreter_for(root)
    repo = root / "pkasolver"

    steps = [
        "Creating the Python environment",
        f"Installing PyTorch {TORCH_VERSION} (largest download)",
        "Installing torch-scatter and torch-sparse (prebuilt wheels)",
        "Installing torch-geometric and pinned scientific stack",
        "Downloading pkasolver and its trained models",
        "Making pkasolver importable",
        "Verifying with a real prediction",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    uv = find_uv()

    # 1. environment
    report(0)
    if uv:
        _run([uv, "venv", "--python", _TARGET_PYTHON, str(venv)], steps[0])
    else:
        fallback = find_fallback_python()
        if not fallback:
            raise PkasolverSetupError(describe_prerequisites())
        _run([*fallback.split(), "-m", "venv", str(venv)], steps[0])
    if not python.is_file():
        raise PkasolverSetupError(f"Environment created but no interpreter at {python}")

    pip_install = ([uv, "pip", "install", "--python", str(python)] if uv
                   else [str(python), "-m", "pip", "install"])

    # 2. torch first and alone -- the scatter/sparse wheels below are built
    #    against a specific torch build and must find it already present.
    report(1)
    _run([*pip_install, f"torch=={TORCH_VERSION}", "--index-url", _TORCH_INDEX], steps[1])

    # 3. prebuilt compiled extensions -- the step that would otherwise
    #    demand a C++ compiler.
    report(2)
    _run([*pip_install, "torch-scatter", "torch-sparse", "--find-links", _PYG_WHEEL_INDEX,
          "--no-build-isolation"], steps[2])

    # 4. everything else, pinned.
    report(3)
    _run([*pip_install, "torch-geometric==2.0.1", "numpy<2", "scipy<1.14", "pandas", "rdkit",
          "cairosvg", "svgutils"], steps[3])

    # 5. pkasolver itself, source + the ~200 MB trained model ensemble.
    report(4)
    git = shutil.which("git")
    if not git:
        raise PkasolverSetupError("git is required to download pkasolver, but was not found on PATH.")
    if repo.exists():
        shutil.rmtree(repo, ignore_errors=True)
    _run([git, "clone", "--depth", "1", PKASOLVER_REPO, str(repo)], steps[4])

    # 6. A .pth file rather than `pip install -e .`: pkasolver's setup.py
    #    uses versioneer, which calls configparser.SafeConfigParser --
    #    removed in Python 3.12, so a normal install simply cannot succeed
    #    on the interpreter this environment needs.
    report(5)
    site_packages = _site_packages_of(python)
    (site_packages / "openchem_pkasolver.pth").write_text(str(repo) + "\n", encoding="utf-8")

    # 7. Prove it works rather than assuming -- a setup that "succeeded"
    #    but cannot predict is worse than one that failed loudly.
    report(6)
    _verify(python)
    return python


def _site_packages_of(python: Path) -> Path:
    result = subprocess.run(
        [str(python), "-c", "import site; print(site.getsitepackages()[-1])"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise PkasolverSetupError("Could not locate the new environment's site-packages directory.")
    return Path(result.stdout.strip())


def _verify(python: Path) -> None:
    from openchem.chem.pka_providers import compute_pka

    from rdkit import Chem

    try:
        pkas = compute_pka(Chem.MolFromSmiles("CC(=O)O"), str(python))
    except RuntimeError as exc:
        raise PkasolverSetupError(f"Setup finished but the test prediction failed: {exc}") from exc
    if not pkas:
        raise PkasolverSetupError("Setup finished but the test prediction returned no pKa for acetic acid.")
    # Acetic acid's real pKa is 4.76; the model predicts ~4.2. A wildly
    # different number means something is wrong with the install even
    # though it ran, so this is a sanity band rather than an accuracy check.
    value = pkas[0][1]
    if not 2.0 <= value <= 8.0:
        raise PkasolverSetupError(
            f"Setup finished but the test prediction looks wrong: acetic acid pKa {value:.2f} "
            f"(expected roughly 4-5). The environment may be subtly mismatched."
        )
