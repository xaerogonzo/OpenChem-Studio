"""Builds a working STOUT environment, so nobody has to assemble one from
a documentation recipe to unlock structure-to-name prediction.

STOUT cannot live in this application's own environment: it pins
`tensorflow==2.10.1`, whose newest wheels are cp310, while this app runs
CPython 3.13. Confirmed by resolver -- `stout-pypi` is unsatisfiable here
("no wheels with a matching Python ABI tag") and resolves cleanly under
`--python-version 3.10`. So it gets its own virtual environment and is
invoked out of process, exactly as ORCA, Vina and pkasolver already are.

Deliberately mirrors `pkasolver_setup.py` step for step. The two solve the
same problem and diverging their shapes would make both harder to reason
about; the real differences are the target Python version and what gets
installed.
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

# tensorflow 2.10.1 publishes cp37-cp310 wheels only. 3.10 is therefore the
# newest usable interpreter, and this app's own 3.13 cannot be reused --
# which is the entire reason this module exists.
_TARGET_PYTHON = "3.10"

STOUT_PACKAGE = "STOUT-pypi"

# TensorFlow 2.10's compiled extensions were built against the NumPy 1.x C
# ABI, and its own metadata does not cap the version -- so a fresh install
# silently pulls NumPy 2.x and then dies on IMPORT with
#
#     _np_bfloat16 = _pywrap_bfloat16.TF_bfloat16_type()
#     TypeError: Unable to convert function return value to a Python type!
#
# which names neither TensorFlow nor NumPy and is unguessable from the
# message. Confirmed live: a STOUT environment built without this pin
# ended up on numpy 2.2.6 and could not import tensorflow at all.
#
# Installed in the SAME pip call as STOUT, not a later one: a second call
# would let the resolver satisfy STOUT with numpy 2 first and then
# downgrade, which works but leaves the wrong wheels' metadata cached.
NUMPY_PIN = "numpy<2"

# TensorFlow is most of this. The trained translation models download on
# first use rather than at install time, so the on-disk figure grows after
# the first prediction -- stated up front rather than surprising anyone.
APPROX_DOWNLOAD_MB = 600
APPROX_DISK_GB = 2.0


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class StoutSetupError(RuntimeError):
    """Setup failed. The message is meant to be shown to a user verbatim,
    so it names what failed and what to do, not just a return code."""


def default_install_root() -> Path:
    return app_paths.subdirectory("stout_env")


def interpreter_for(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def find_uv() -> str | None:
    """uv is strongly preferred because it can PROVISION a Python 3.10 on
    demand. Without it the user must already have one installed, since
    3.10 is now several releases old."""
    return shutil.which("uv")


def find_fallback_python() -> str | None:
    """An already-installed 3.10, the only version tensorflow 2.10 supports
    that this app can drive. Unlike pkasolver's 3.10-3.12 window there is
    no choice here."""
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher and _python_reports_version(launcher, ["-3.10"], "3.10"):
            return f"{launcher} -3.10"
    candidate = shutil.which("python3.10")
    if candidate and _python_reports_version(candidate, [], "3.10"):
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


def find_java() -> str | None:
    """STOUT needs a JVM AT RUNTIME, not just at install time.

    Not obvious and not documented anywhere prominent: `STOUT.repack.helper`
    starts a JVM through jpype to reach CDK, at import. Without one, every
    prediction dies with

        OSError: [WinError 126] JVM DLL not found: Define/path/or/set/
        JAVA_HOME/variable/properly

    after the ~600 MB TensorFlow download has already completed. Checking
    first turns a multi-gigabyte dead end into an immediate, actionable
    message.

    This is a DIFFERENT requirement from OPSIN's Java dependency, which
    the External Tools text already mentioned -- OPSIN is name-to-
    structure and entirely optional; this is STOUT itself.
    """
    # Includes the portable runtime this app can install itself
    # (services/java_setup.py), so a managed Java counts as found and the
    # Java check is not a permanent wall for anyone without one.
    from openchem.services.java_setup import java_home

    managed_or_system = java_home()
    if managed_or_system is not None:
        return str(managed_or_system)
    # jpype finds a JVM through JAVA_HOME or the loader path, so an install
    # that is on neither still counts as missing for our purposes -- but
    # naming a real directory we can see makes the fix obvious.
    for candidate in (
        Path("C:/Program Files/Eclipse Adoptium"),
        Path("C:/Program Files/Java"),
        Path("/usr/lib/jvm"),
    ):
        if candidate.is_dir() and any(candidate.iterdir()):
            return str(candidate)
    return None


_JAVA_MISSING = (
    "No Java runtime found. STOUT itself needs one: it starts a JVM through jpype to reach "
    "CDK every time it loads, so without Java no prediction can run at all. Install any JRE "
    "or JDK (Temurin/Adoptium is a good free choice) and make sure java is on PATH or "
    "JAVA_HOME is set, then try again."
)


def describe_prerequisites() -> str:
    if not find_java():
        # Reported FIRST and on its own: no amount of Python provisioning
        # helps if the JVM is missing, and it is the cheaper thing to fix.
        return f"Cannot set up: {_JAVA_MISSING}"
    if find_uv():
        return f"Ready: uv found, will provision Python {_TARGET_PYTHON} automatically."
    fallback = find_fallback_python()
    if fallback:
        return f"Ready: will use {fallback}."
    return (
        f"Cannot set up automatically: needs either uv (recommended -- it fetches "
        f"Python {_TARGET_PYTHON} for you) or an existing Python {_TARGET_PYTHON} on PATH. "
        f"This app's own Python {sys.version_info.major}.{sys.version_info.minor} "
        f"cannot be used: TensorFlow 2.10 publishes no wheels for it."
    )


def _run(command: list[str], step: str, timeout: int = 3600) -> None:
    logger.info("STOUT setup: %s -> %s", step, " ".join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise StoutSetupError(f"{step} timed out after {timeout}s") from exc
    except OSError as exc:
        raise StoutSetupError(f"{step} could not start: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-600:]
        raise StoutSetupError(f"{step} failed:\n{tail}")


def install(root: Path | None = None, on_progress: ProgressCallback | None = None) -> Path:
    """Builds the environment and returns the interpreter path to store in
    Settings. Safe to re-run: every step overwrites or is idempotent."""
    # Checked BEFORE anything is created or downloaded. Failing here costs
    # a second; failing at _verify costs ~600 MB and several minutes for
    # the same unusable result.
    if not find_java():
        raise StoutSetupError(_JAVA_MISSING)

    root = root or default_install_root()
    root.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv"
    python = interpreter_for(root)

    steps = [
        f"Creating a Python {_TARGET_PYTHON} environment",
        "Installing STOUT and TensorFlow (largest download)",
        "Verifying with a real prediction (downloads the model on first run)",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    uv = find_uv()

    report(0)
    if uv:
        _run([uv, "venv", "--python", _TARGET_PYTHON, str(venv)], steps[0])
    else:
        fallback = find_fallback_python()
        if not fallback:
            raise StoutSetupError(describe_prerequisites())
        _run([*fallback.split(), "-m", "venv", str(venv)], steps[0])
    if not python.is_file():
        raise StoutSetupError(f"Environment created but no interpreter at {python}")

    pip_install = (
        [uv, "pip", "install", "--python", str(python)]
        if uv
        else [str(python), "-m", "pip", "install"]
    )

    report(1)
    _run([*pip_install, STOUT_PACKAGE, NUMPY_PIN], steps[1])

    # Prove it works rather than assuming. A setup that "succeeded" but
    # cannot predict is worse than one that failed loudly -- and STOUT
    # additionally downloads its trained models on FIRST USE, so an
    # install that has never predicted has not actually finished.
    report(2)
    _verify(python)
    return python


def _verify(python: Path) -> None:
    from rdkit import Chem

    from openchem.chem.stout_providers import run_stout

    try:
        name = run_stout(Chem.MolFromSmiles("CCO"), str(python))
    except RuntimeError as exc:
        raise StoutSetupError(f"Setup finished but the test prediction failed: {exc}") from exc
    if not name:
        raise StoutSetupError("Setup finished but the test prediction returned no name for ethanol.")
    # Ethanol is the simplest possible check and STOUT should name it
    # exactly. A wildly different answer means the model loaded wrong even
    # though it ran -- a sanity check, not an accuracy measurement.
    if "ethanol" not in name.lower():
        raise StoutSetupError(
            f"Setup finished but the test prediction looks wrong: STOUT named ethanol {name!r}."
        )
