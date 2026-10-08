"""Knowledge Vista (`kv`): a separate, optional program that knows where a document is NOW.

OpenChem Studio is fully useful without it (it is a library manager for the PDFs the project reads, not part of the chemistry). This
module is the whole of OpenChem's side of the connection, and it keeps one rule: **every way Knowledge Vista can be unavailable is a
value the caller can show, never an exception it must remember to catch.** Not configured, not there, a program that is not Knowledge
Vista, a timeout, unparsable output and a protocol this build was not taught are all `KnowledgeVistaUnavailable` with a sentence a
person can read.

The wire contract is Knowledge Vista's own (docs/INTEGRATION.md in that repository): `kv --json capabilities` names a
`protocol_version`, and this module understands exactly `SUPPORTED_PROTOCOL`.

**WHAT IS NOT HERE, ON PURPOSE.** There is no "open this paper in Knowledge Vista". It was planned, and it needs a screen that shows a
paper; no screen in this application does (the literature manifest is a development record, not something the application displays).
Code that nothing can reach is how a feature ships looking finished and does nothing, so it waits for the screen. When one exists, Knowledge
Vista's `kv --json open <reference>` is the call, it reports the page it was asked for without navigating to it, and this module is where
the wrapper goes.

Nothing in this module reads a document, sends one anywhere or writes to the library.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("openchem.tools")

#: The only `protocol_version` of `kv capabilities` this build understands. Anything else is "present but unusable", said plainly.
SUPPORTED_PROTOCOL = 1
#: The settings key holding the path of the `kv` executable (Settings > External tools > Knowledge Vista).
SETTING_KEY = "knowledgevista/executable_path"
#: Where a person gets Knowledge Vista; shown as the tab's vendor link. This app never downloads it.
PROJECT_PAGE = "https://github.com/xaerogonzo/knowledgevista"
#: How long one `kv` call may take before it is reported as not answering. Long enough for a cold start, short enough that a hung program is not mistaken for a slow one.
TIMEOUT_SECONDS = 20.0


class KnowledgeVistaUnavailable(Exception):
    """Knowledge Vista cannot be used right now; `str(exc)` says why."""


def executable(configured: str | None) -> list[str] | None:
    """The argv prefix that runs `kv`: the configured path if it names a file, else `kv` on PATH, else None. Starts nothing."""
    configured = (configured or "").strip()
    if configured:
        return [configured] if Path(configured).is_file() else None
    found = shutil.which("kv")
    return [found] if found else None


def _run(configured: str | None, arguments: list[str], timeout: float = TIMEOUT_SECONDS) -> dict[str, Any]:
    argv = executable(configured)
    if argv is None:
        raise KnowledgeVistaUnavailable(
            "Knowledge Vista (kv) is not set up. Install it and point OpenChem Studio at it under Settings > External Tools > Knowledge Vista."
        )
    full = [*argv, "--json", *arguments]
    try:
        done = subprocess.run(full, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as exc:
        raise KnowledgeVistaUnavailable(f"`kv {arguments[0]}` did not answer within {timeout:g} s.") from exc
    except OSError as exc:
        raise KnowledgeVistaUnavailable(f"`kv` could not be started ({type(exc).__name__}: {exc}).") from exc
    try:
        envelope = json.loads(done.stdout)
    except ValueError as exc:
        raise KnowledgeVistaUnavailable(f"`kv {arguments[0]}` exited {done.returncode} without a JSON answer: that program is not Knowledge Vista, or is broken.") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool) or not isinstance(envelope.get("records"), list):
        raise KnowledgeVistaUnavailable(f"`kv {arguments[0]}` did not answer in Knowledge Vista's format.")
    if done.returncode not in (0, 1, 2):
        raise KnowledgeVistaUnavailable(f"`kv {arguments[0]}` exited {done.returncode}.")
    return envelope


def check_protocol(configured: str | None, timeout: float = TIMEOUT_SECONDS) -> dict[str, Any]:
    """The `capabilities` record, or `KnowledgeVistaUnavailable` if this is not a Knowledge Vista this build can use."""
    envelope = _run(configured, ["capabilities"], timeout)
    record = envelope["records"][0] if envelope["ok"] and envelope["records"] else None
    if not isinstance(record, dict) or record.get("app") != "KnowledgeVista":
        raise KnowledgeVistaUnavailable("That program answered `capabilities` but is not Knowledge Vista.")
    if record.get("protocol_version") != SUPPORTED_PROTOCOL:
        raise KnowledgeVistaUnavailable(
            f"This Knowledge Vista speaks integration protocol {record.get('protocol_version')!r}; this OpenChem Studio understands {SUPPORTED_PROTOCOL}. "
            "Update whichever is older."
        )
    return record


def describe_status(configured: str | None) -> str:
    """One line for the tool's tab. **Does not run it**: a status line is read on every visit; the Test button is the deliberate run."""
    configured = (configured or "").strip()
    if configured:
        path = Path(configured)
        return f"Configured: {path.name} in {path.parent}" if path.is_file() else f"Configured, but no file at {path}"
    found = shutil.which("kv")
    return f"Found on PATH: {found}" if found else "Not configured (optional: OpenChem Studio works without it)"


def verify(configured: str | None) -> str:
    """Ask the configured program what it is, and say what it can do; raises `KnowledgeVistaUnavailable` if it is not usable."""
    record = check_protocol(configured)
    read_only = sum(1 for command in record.get("commands", []) if command.get("read_only"))
    return f"Works: Knowledge Vista {record.get('app_version', '?')} (integration protocol {record['protocol_version']}, {read_only} read-only commands)."


def responds_as_knowledge_vista(path: Path | str) -> bool:
    """Whether the program at `path` really is a usable Knowledge Vista, asked by running `capabilities`. A name match is not enough."""
    try:
        check_protocol(str(path), timeout=10.0)
    except KnowledgeVistaUnavailable:
        return False
    return True

