"""A small, defensive client for Knowledge Vista's `kv` command, for the tools in this directory.

Knowledge Vista (https://github.com/xaerogonzo/knowledgevista) is a separate program that knows where a PDF is NOW, however its file was
renamed or moved. OpenChem works without it (the project's invariant: OpenChem is useful with KV absent), so this module's one rule is:

    **EVERY WAY KV CAN BE UNAVAILABLE IS "UNAVAILABLE", NEVER AN EXCEPTION THE CALLER MUST HANDLE ONE BY ONE.**

Not installed, a timeout, a non-zero exit it does not explain, output that is not JSON, a JSON envelope of the wrong shape, and a
protocol version this client has not been taught are all one outcome: `KvUnavailable`, with a reason a person can read. The caller
degrades to what it did before KV existed and prints the reason once.

What KV is asked is only a file's SHA-256 (`kv locate <sha256>`): no path, no title, no text leaves this machine, and KV is a local program
anyway. What KV answers is a LEAD, not evidence: a catalog scanned yesterday can name a file that has since moved, so the caller must
re-hash the path it is given before it believes it (`tools/index_literature.py` does).

Configuration, all optional:

    OPENCHEM_KV          the `kv` executable (or a `.py` script, run with this interpreter); default: `kv` on PATH
    OPENCHEM_KV_CATALOG  a catalog file to pass as `--catalog` (default: KV's own)

The wire contract this client speaks is Knowledge Vista's docs/INTEGRATION.md; `PROTOCOL_VERSION` is the only version it understands.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: The `protocol_version` of `kv capabilities` this client was written against. Another value means "KV is present and I cannot use it".
PROTOCOL_VERSION = 1
TIMEOUT_SECONDS = 20.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KvUnavailable(Exception):
    """KV cannot be used right now; `str(exc)` says why in a sentence."""


@dataclass(frozen=True)
class Located:
    """What KV says about one artifact (one SHA-256)."""

    artifact_id: str
    document_id: str | None
    status: str  # available | root_offline | missing | unlocated
    uri: str | None
    paths: tuple[str, ...] = field(default_factory=tuple)  # absolute paths KV believes hold these bytes, only those it checked on disk or could not check

    @property
    def reachable(self) -> bool:
        return bool(self.paths)


def command() -> list[str] | None:
    """The argv prefix that runs `kv`, or None if there is none to run. Does not start it."""
    configured = os.environ.get("OPENCHEM_KV", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_file() and shutil.which(configured) is None:
            return None
        return [sys.executable, str(path)] if path.suffix.lower() == ".py" else [configured]
    found = shutil.which("kv")
    return [found] if found else None


def configured() -> bool:
    """Whether the user pointed OpenChem at KV (as opposed to it merely being absent, which is normal and silent)."""
    return bool(os.environ.get("OPENCHEM_KV", "").strip())


def _run(arguments: list[str], timeout: float) -> tuple[int, dict]:
    argv = command()
    if argv is None:
        raise KvUnavailable("Knowledge Vista (`kv`) was not found: install it, or set OPENCHEM_KV to its path")
    catalog = os.environ.get("OPENCHEM_KV_CATALOG", "").strip()
    full = [*argv, "--json", *(["--catalog", catalog] if catalog else []), *arguments]
    try:
        done = subprocess.run(full, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as exc:
        raise KvUnavailable(f"`kv {arguments[0]}` did not answer within {timeout:g} s") from exc
    except OSError as exc:
        raise KvUnavailable(f"`kv` could not be started ({type(exc).__name__}: {exc})") from exc
    try:
        envelope = json.loads(done.stdout)
    except ValueError as exc:
        raise KvUnavailable(f"`kv {arguments[0]}` exited {done.returncode} without a JSON answer") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("ok"), bool) or not isinstance(envelope.get("records"), list):
        raise KvUnavailable(f"`kv {arguments[0]}` answered with something that is not a Knowledge Vista envelope")
    if done.returncode not in (0, 1, 2):
        raise KvUnavailable(f"`kv {arguments[0]}` exited {done.returncode}")
    return done.returncode, envelope


_checked: dict[str, str | None] = {}


def check_protocol(timeout: float = TIMEOUT_SECONDS) -> None:
    """Raise `KvUnavailable` unless `kv capabilities` names a protocol version this client understands. Remembered per kv command."""
    key = "\0".join(command() or ["-"]) + os.environ.get("OPENCHEM_KV_CATALOG", "")
    if key not in _checked:
        try:
            _, envelope = _run(["capabilities"], timeout)
            record = envelope["records"][0] if envelope["ok"] and envelope["records"] else {}
            version = record.get("protocol_version")
            _checked[key] = None if version == PROTOCOL_VERSION else f"Knowledge Vista speaks integration protocol {version!r}; this OpenChem understands {PROTOCOL_VERSION}"
        except KvUnavailable as exc:
            _checked[key] = str(exc)
    if _checked[key]:
        raise KvUnavailable(_checked[key])


def forget() -> None:
    """Drop what `check_protocol` remembered (tests, and a long-running caller after the user changes the setting)."""
    _checked.clear()


def locate_sha256(sha256: str, timeout: float = TIMEOUT_SECONDS) -> Located | None:
    """Where Knowledge Vista says the file with this SHA-256 is now, or None if it has never seen those bytes.

    Raises `KvUnavailable` if KV cannot be used. A hash is one artifact, so `KV_AMBIGUOUS` cannot legitimately happen; if it does the
    answer is not trusted and KV is treated as unavailable.
    """
    if not _SHA256.match(sha256 or ""):
        raise ValueError("locate_sha256 takes a full lowercase SHA-256")
    check_protocol(timeout)
    _, envelope = _run(["locate", sha256], timeout)
    if not envelope["ok"]:
        code = (envelope.get("errors") or [{}])[0].get("code")
        if code == "KV_NOT_FOUND":
            return None
        raise KvUnavailable(f"`kv locate` refused: {code or 'no error code'}")
    record = envelope["records"][0] if envelope["records"] else None
    if not isinstance(record, dict) or record.get("artifact_id") != sha256 or not isinstance(record.get("locations"), list):
        raise KvUnavailable("`kv locate` answered about different bytes than were asked about")
    reachable = tuple(
        loc["absolute_path"] for loc in record["locations"]
        if isinstance(loc, dict) and loc.get("state") == "active" and loc.get("root_status") == "online" and loc.get("on_disk") is not False
        and isinstance(loc.get("absolute_path"), str)
    )
    return Located(sha256, record.get("document_id"), str(record.get("status")), record.get("uri"), reachable)
