"""Invokes STOUT out of process, from its own Python environment.

STOUT (Structure-TO-IUPAC-name Translator) cannot live in this
application's environment: it pins `tensorflow==2.10.1`, which publishes
no wheels beyond CPython 3.10, while this app runs 3.13. Confirmed by
resolver: `stout-pypi` is unsatisfiable here and resolves cleanly under
`--python-version 3.10`.

That is the same shape of problem `chem/pka_providers.py` already solved
for pkasolver, so it gets the same solution -- a separate environment,
invoked and parsed rather than imported. See `services/stout_setup.py` for
the installer.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from rdkit import Chem

logger = logging.getLogger("openchem.chemistry")

# Settings key holding the path to a Python interpreter with STOUT
# installed. Configured via Tools -> External Tools, same as ORCA, Vina
# and pkasolver.
STOUT_PYTHON_SETTING = "naming/stout_python_path"

_RUNNER = Path(__file__).resolve().parent / "stout_runner.py"

# TensorFlow's import alone takes tens of seconds cold, and the translation
# model is loaded per invocation. Generous but bounded, matching the
# reasoning behind pkasolver's timeout.
_TIMEOUT_SECONDS = 600


def stout_available(interpreter_path: str | None) -> bool:
    """Whether a usable STOUT environment is configured.

    Only checks that the interpreter exists -- actually importing
    TensorFlow to prove it works would take half a minute, which is far
    too slow for a availability check called while building a menu.
    """
    if not interpreter_path:
        return False
    return Path(interpreter_path).is_file()


def describe_stout_status(interpreter_path: str | None) -> str:
    if stout_available(interpreter_path):
        return f"Ready: STOUT will run from {interpreter_path}"
    return (
        "Not configured. STOUT predicts an IUPAC name for any structure, but it pins "
        "tensorflow 2.10, which has no wheels for this app's Python — so it needs its own "
        "Python 3.10 environment. Use \"Set up automatically\" to build one."
    )


def _parse_runner_output(stdout: str, stderr: str, returncode: int) -> dict:
    """The runner's JSON is the LAST brace-line of stdout.

    TensorFlow prints banners, oneDNN notices and progress bars to stdout
    on import, so the payload is never the only thing there -- the same
    reason `pka_providers._parse_runner_output` scans from the end.
    """
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    tail = (stderr or stdout or "").strip()[-500:]
    raise RuntimeError(f"STOUT produced no usable output (exit {returncode}).\n{tail}")


def run_stout(mol: Chem.Mol, interpreter_path: str | None) -> str:
    """Predicted IUPAC name for `mol`, or raises with a readable message."""
    if not stout_available(interpreter_path):
        raise RuntimeError(describe_stout_status(interpreter_path))

    smiles = Chem.MolToSmiles(mol)
    try:
        # JAVA_HOME is injected rather than assumed to be set: STOUT
        # starts a JVM through jpype on import, and a Temurin runtime this
        # app installed itself is on neither PATH nor the environment. See
        # services/java_setup.py.
        from openchem.services.java_setup import environment_with_java

        result = subprocess.run(
            [str(interpreter_path), str(_RUNNER)],
            input=smiles,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            env=environment_with_java(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"STOUT timed out after {_TIMEOUT_SECONDS}s.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start the STOUT interpreter: {exc}") from exc

    payload = _parse_runner_output(result.stdout, result.stderr, result.returncode)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    name = payload.get("name")
    if not name:
        raise RuntimeError("STOUT returned no name.")
    return str(name)


def describe_stout_test(interpreter_path: str | None) -> str:
    """One-line human-readable result of a real prediction, for the
    External Tools dialog.

    The chem layer owns which molecule to test with and how to build it --
    the UI layer must not import RDKit directly (enforced by
    `tests/test_layering.py`), and pushing `Chem.MolFromSmiles` into the
    dialog broke exactly that rule. Mirrors `describe_pka_status`.
    """
    if not stout_available(interpreter_path):
        return "Not configured - predicted names unavailable (PubChem lookup still works)"
    try:
        name = run_stout(Chem.MolFromSmiles("CCO"), interpreter_path)
    except RuntimeError as exc:
        return f"Configured but not working: {exc}"
    if "ethanol" not in name.lower():
        return f"Configured, but named ethanol {name!r} - check the install"
    return f"Found: STOUT (named ethanol {name!r})"
