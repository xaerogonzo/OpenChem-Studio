"""Builds a working ADMET-AI environment for hERG/CYP prediction.

Deliberately mirrors `pkasolver_setup.py` and `stout_setup.py` step for
step -- the three solve the same problem and diverging their shapes would
make all three harder to reason about.

It is, however, by far the easiest of the three, and the differences are
worth stating because they are what made this endpoint reachable at all
after being deferred repeatedly as impossible:

  * `admet-ai` resolves against modern Python with no pins to fight.
    Verified live on 3.12 and 3.13 -- no MSVC, no prebuilt-wheel hunt, no
    `numpy<2` conflict. pkasolver needed all three.
  * Its trained weights ship INSIDE the wheel (~15 MB), so there is no
    separate download to break. STOUT's separate weights download is
    exactly what died and took that feature with it.

So this is one `pip install` and a verification, not a seven-step
recipe. The environment is still separate because torch is ~490 MB and
belongs neither in this project's dependency tree nor in the frozen
build.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openchem import paths as app_paths

logger = logging.getLogger("openchem.services")

#: admet-ai declares requires-python >=3.11. 3.12 is chosen rather than
#: the newest available because torch wheels appear for it first, and a
#: sidecar that fails on a torch wheel gap is a support problem for
#: something that has nothing to do with chemistry.
_TARGET_PYTHON = "3.12"

ADMET_PACKAGE = "admet-ai"

#: Dominated by torch. Stated up front rather than surprising anyone
#: mid-download -- measured at 1.01 GB installed for the real environment.
APPROX_DOWNLOAD_MB = 700
APPROX_DISK_GB = 1.1


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class AdmetSetupError(RuntimeError):
    """Setup failed. The message is meant to be shown verbatim, so it
    names what failed and what to do, not just a return code."""


def default_install_root() -> Path:
    return app_paths.subdirectory("admet_env")


def interpreter_for(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def find_uv() -> str | None:
    """uv is preferred because it can PROVISION the target Python rather
    than requiring one already installed."""
    return shutil.which("uv")


def find_fallback_python() -> str | None:
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher and _python_reports_at_least(launcher, ["-3.12"], (3, 12)):
            return f"{launcher} -3.12"
    for name in ("python3.12", "python3.13", "python3"):
        candidate = shutil.which(name)
        if candidate and _python_reports_at_least(candidate, [], (3, 11)):
            return candidate
    return None


def _python_reports_at_least(executable: str, extra: list[str], minimum: tuple[int, int]) -> bool:
    try:
        result = subprocess.run(
            [executable, *extra, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    try:
        parts = tuple(int(p) for p in result.stdout.strip().split("."))
    except ValueError:
        return False
    return parts >= minimum


def describe_prerequisites() -> str:
    if find_uv():
        return f"Ready: uv found, will provision Python {_TARGET_PYTHON} automatically."
    fallback = find_fallback_python()
    if fallback:
        return f"Ready: will use {fallback}."
    return (
        f"Cannot set up automatically: needs either uv (recommended -- it fetches "
        f"Python {_TARGET_PYTHON} for you) or an existing Python 3.11+ on PATH."
    )


def _run(command: list[str], step: str, timeout: int = 3600) -> None:
    logger.info("ADMET setup: %s -> %s", step, " ".join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AdmetSetupError(f"{step} timed out after {timeout}s") from exc
    except OSError as exc:
        raise AdmetSetupError(f"{step} could not start: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip()[-600:]
        raise AdmetSetupError(f"{step} failed:\n{tail}")


def install(root: Path | None = None, on_progress: ProgressCallback | None = None) -> Path:
    """Builds the environment and returns the interpreter path to store in
    Settings.

    Safe to re-run, and that is load-bearing rather than a nicety: a
    re-run is what a user does after a failure, and the expensive part
    (~1 GB of PyTorch) must not be redownloaded to retry a check that
    takes seconds. An existing interpreter is reused; pip install is
    idempotent; verification simply runs again.
    """
    root = root or default_install_root()
    root.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv"
    python = interpreter_for(root)

    steps = [
        f"Creating a Python {_TARGET_PYTHON} environment",
        f"Installing ADMET-AI and PyTorch (~{APPROX_DOWNLOAD_MB} MB)",
        "Verifying with a real prediction",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    uv = find_uv()

    report(0)
    if python.is_file():
        # REUSE, don't recreate. `uv venv` refuses to touch a directory
        # that already holds an environment ("A virtual environment
        # already exists ... Use --clear to replace it") and exits
        # non-zero, so a re-run died at this first step -- which is
        # exactly what a user does after any later step fails. The
        # docstring claimed this was idempotent; it was not, and only the
        # `python -m venv` fallback ever actually was.
        logger.info("ADMET setup: reusing the existing environment at %s", python)
    else:
        if uv:
            # --clear covers a half-created venv: the directory exists,
            # the interpreter does not.
            _run([uv, "venv", "--python", _TARGET_PYTHON, "--clear", str(venv)], steps[0])
        else:
            fallback = find_fallback_python()
            if not fallback:
                raise AdmetSetupError(describe_prerequisites())
            _run([*fallback.split(), "-m", "venv", str(venv)], steps[0])
        if not python.is_file():
            raise AdmetSetupError(f"Environment created but no interpreter at {python}")

    report(1)
    pip_install = ([uv, "pip", "install", "--python", str(python)] if uv
                   else [str(python), "-m", "pip", "install"])
    _run([*pip_install, ADMET_PACKAGE], steps[1])

    # Prove it works rather than assuming. A setup that "succeeded" but
    # cannot predict is worse than one that failed loudly -- that lesson
    # came from STOUT, which installed 1.5 GB perfectly and only then
    # discovered its weights no longer existed.
    report(2)
    _verify(python)
    return python


def _verify(python: Path) -> None:
    """Run one real prediction through the same runner the app uses.

    Deliberately not a bare `import admet_ai`: importing proves the wheel
    landed, not that a prediction can be produced, and the whole point of
    this check is the difference between those two.
    """
    from openchem.chem.admet_providers import _RUNNER

    try:
        result = subprocess.run(
            [str(python), str(_RUNNER), "CN(C)C(=N)N=C(N)N"],  # metformin
            capture_output=True, text=True, timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmetSetupError(f"Verification could not run: {exc}") from exc

    import json

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        tail = (result.stdout or result.stderr or "").strip()[-500:]
        raise AdmetSetupError(f"Setup finished but the test prediction was unreadable:\n{tail}") from exc
    if "error" in payload:
        raise AdmetSetupError(f"Setup finished but the test prediction failed: {payload['error']}")
    if "hERG" not in (payload.get("endpoints") or {}):
        raise AdmetSetupError(
            "Setup finished but the model produced no hERG value, which is the "
            "endpoint this environment exists for."
        )
