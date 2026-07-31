"""Shared checks for the out-of-process sidecar interpreters.

pkasolver and STOUT both run in their own virtual environments, both
store an interpreter path in Settings, and both can therefore be pointed
at something that is not an interpreter at all. This turns that into a
sentence a user can act on.

The failure that prompted it: a stored path of
`...\\pkasolver_env\\pkasolver\\.codecov.yml` -- a file from the cloned
repo, not a Python -- surfaced only as

    [WinError 193] %1 is not a valid Win32 application

which names nothing, suggests nothing, and appeared while a perfectly
good interpreter sat two directories away in the same environment.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Long enough for a cold interpreter start on a loaded machine, short
# enough that a wrong path does not hang the dialog.
_VERSION_TIMEOUT = 30


def interpreter_problem(path: str) -> str | None:
    """A sentence describing why `path` is not a usable Python, or None.

    Deliberately runs the thing rather than pattern-matching its name: a
    file called `python.exe` can still be broken, and an interpreter with
    an unusual name is still an interpreter.
    """
    if not path or not path.strip():
        return "No interpreter configured."
    candidate = Path(path.strip())
    if not candidate.exists():
        return f"Nothing exists at {candidate}."
    if candidate.is_dir():
        return (
            f"{candidate} is a folder. Point at the interpreter INSIDE it -- "
            f"{'.venv\\Scripts\\python.exe' if os.name == 'nt' else '.venv/bin/python'}."
        )
    if candidate.suffix.lower() in {".yml", ".yaml", ".txt", ".md", ".cfg", ".toml", ".json"}:
        # Caught by name only for this one case, because the OS error for
        # "tried to execute a text file" is famously opaque on Windows.
        return f"{candidate.name} is a text file, not a Python interpreter."
    try:
        result = subprocess.run(
            [str(candidate), "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{candidate.name} could not be run as a program: {exc}"
    if result.returncode != 0 or not result.stdout.strip().startswith("3"):
        return f"{candidate.name} ran but is not a Python 3 interpreter."
    return None


def working_interpreter_in(root: Path) -> Path | None:
    """The interpreter inside a sidecar environment, if one is really
    there and really runs.

    Used to offer a way out when the CONFIGURED path is broken: the app
    installed that environment and knows where it put it, so it can say
    so instead of leaving the user to find it.
    """
    for relative in (Path(".venv/Scripts/python.exe"), Path(".venv/bin/python")):
        candidate = root / relative
        if candidate.is_file() and interpreter_problem(str(candidate)) is None:
            return candidate
    return None


def recovery_hint(root: Path) -> str:
    """Appended to a failure message when a usable environment exists
    anyway. Empty when there is nothing to suggest, so callers can
    concatenate unconditionally."""
    found = working_interpreter_in(root)
    # ASCII only: this string reaches logs and the console as well as Qt,
    # and a non-ASCII dash has already caused a real UnicodeEncodeError in
    # this codebase under cp1252.
    return f" A working interpreter was found at {found} -- use Browse to select it." if found else ""
