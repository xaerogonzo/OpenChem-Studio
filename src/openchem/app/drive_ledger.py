"""What the application LOGGED during a driven run, kept as a verdict.

**WHY THIS EXISTS.** A live session drew a nitramine and the Console filled
with five identical tracebacks in forty seconds, one per edit -- an
exception in the alert pass, logged and then forgotten. Nothing failed: the
window stayed up, the panels rendered, and every driven check this project
has ever run would have ended with exit code 0 and a screenshot that looked
fine. `tests/multicomponent_sweep.py` records the same blind spot in its own
docstring: "the eager provider LOGS an alert or per-atom failure and records
nothing". The driver could photograph a window and assert on what a panel
held, but it never asked the one question that would have caught this: what
did the application say was wrong?

So a driven run now keeps a ledger of everything WARNING and above that the
application logged, and ends in a verdict (and an exit status) rather than a
screenshot.

**TWO KINDS OF RECORD, AND THEY MUST NOT BE MIXED.** The driver logs its own
progress at WARNING ("OPENCHEM_DRIVE: step 3 calculator") so that it shows on
a console whose root level is WARNING for some loggers; counting those as the
application's warnings would make every run noisy and every ledger useless.
Its ERROR records are the opposite case: "no molecule selected" or
"EXPECT ... FAILED" is the run failing to do what the script asked, which is a
result, not noise. Driver ERRORs therefore become **driver failures**, driver
WARNINGs are dropped, and everything else is the application's.

**DE-DUPLICATED BY WHERE IT HAPPENED, NOT BY WHAT IT SAID.** The same defect
logs a different message every time -- the atom indices, a molecule uuid -- so
the key is (logger, exception type, innermost frame, message with its numbers
collapsed). The innermost frame is what keeps two genuinely different
failures that share a first line apart: they raise from different places.

**"CLEAN" IS NOT A PASS ON ITS OWN.** A ledger that passes because logging
was turned off passes for the wrong reason, so the driver pairs
`expect_clean` with `expect_results`, which asserts what the panels actually
hold. See `debug_drive._do_expect_results`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openchem.failure_log import describe

#: What every driver log line starts with. The whole distinction between the
#: two kinds of record rests on it, so it is one constant and not a literal
#: repeated at each call site.
DRIVER_PREFIX = "OPENCHEM_DRIVE:"

#: Distinct failures kept. A pathological loop that logs a new message each
#: pass must not grow the ledger without bound; the count of what was dropped
#: is reported, which is the honest half of a cap.
MAX_ENTRIES = 500

@dataclass
class LedgerEntry:
    """One distinct application log problem, with how many times it happened."""

    level: str
    logger: str
    exception: str
    origin: str
    message: str
    count: int = 1
    first_seen: str = ""
    #: The first occurrence's traceback, truncated. One is enough to act on and
    #: five hundred would bury the report.
    sample: str = ""

    def text(self) -> str:
        """What an allow-list is matched against."""
        return f"{self.logger}: {self.exception}: {self.message} @ {self.origin}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level, "logger": self.logger, "exception": self.exception,
            "origin": self.origin, "message": self.message, "count": self.count,
            "first_seen": self.first_seen, "sample": self.sample,
        }


class ErrorLedger(logging.Handler):
    """Collects the application's WARNING-and-above records; see the module docstring."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self._entries: dict[tuple[str, str, str, str, str], LedgerEntry] = {}
        self._driver_failures: list[str] = []
        self.dropped = 0

    # --- collecting ---------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a malformed record is still evidence
            message = str(record.msg)
        description = describe(record)
        if message.startswith(DRIVER_PREFIX):
            if record.levelno >= logging.ERROR:
                text = message[len(DRIVER_PREFIX):].strip()
                exception = description.exception
                self._driver_failures.append(f"{text} ({exception})" if exception else text)
            return
        # "The same failure" is defined once, in `openchem.failure_log`, and
        # shared with the log's own repeat-collapsing so a verdict and a log
        # cannot disagree about how many problems there were.
        exception, origin, first_line = description.exception, description.origin, description.first_line
        key = (record.levelname, record.name, exception, origin, description.message_key)
        entry = self._entries.get(key)
        if entry is not None:
            entry.count += 1
            return
        if len(self._entries) >= MAX_ENTRIES:
            self.dropped += 1
            return
        sample = ""
        if record.exc_info and record.exc_info[1] is not None:
            sample = logging.Formatter().formatException(record.exc_info)[-2000:]
        self._entries[key] = LedgerEntry(
            level=record.levelname, logger=record.name, exception=exception,
            origin=origin, message=first_line[:400],
            first_seen=datetime.now(timezone.utc).isoformat(timespec="seconds"), sample=sample,
        )

    # --- reading ------------------------------------------------------------

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries.values())

    def errors(self) -> list[LedgerEntry]:
        return [e for e in self._entries.values() if logging.getLevelName(e.level) >= logging.ERROR]

    def warnings(self) -> list[LedgerEntry]:
        return [e for e in self._entries.values() if logging.getLevelName(e.level) < logging.ERROR]

    @property
    def driver_failures(self) -> list[str]:
        return list(self._driver_failures)

    def unexpected(self, allow: Iterable[str] = (), *, include_warnings: bool = False) -> list[LedgerEntry]:
        """Entries an allow-list does not excuse.

        `allow` is a list of substrings matched against `LedgerEntry.text()`.
        An entry is excused only by an explicit substring: nothing is excused
        by being familiar, which is how a run learns to ignore its own errors.
        """
        allowed = [a for a in allow if a]
        pool = self.entries if include_warnings else self.errors()
        return [e for e in pool if not any(a in e.text() for a in allowed)]

    def summary_lines(self, allow: Iterable[str] = ()) -> list[str]:
        lines = [
            f"app errors: {len(self.errors())} distinct, {sum(e.count for e in self.errors())} total; "
            f"app warnings: {len(self.warnings())} distinct, {sum(e.count for e in self.warnings())} total; "
            f"driver failures: {len(self._driver_failures)}"
            + (f"; {self.dropped} further distinct records dropped past the cap" if self.dropped else "")
        ]
        excused = {id(e) for e in self.errors()} - {id(e) for e in self.unexpected(allow)}
        for entry in self.errors():
            mark = "allowed" if id(entry) in excused else "UNEXPECTED"
            lines.append(f"  [{mark}] x{entry.count} {entry.text()}")
        for failure in self._driver_failures:
            lines.append(f"  [driver] {failure}")
        return lines

    def to_dict(self, allow: Iterable[str] = ()) -> dict[str, Any]:
        unexpected = {id(e) for e in self.unexpected(allow)}
        return {
            "errors": [{**e.to_dict(), "allowed": id(e) not in unexpected} for e in self.errors()],
            "warnings": [e.to_dict() for e in self.warnings()],
            "driver_failures": self.driver_failures,
            "dropped": self.dropped,
        }


# --- what a run was, so two runs cannot be confused --------------------------


def _sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _git(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, cwd=str(cwd),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - identity is best effort; a report must not stop a run
        return ""


def _ketcher_bundle_hash(package_root: Path) -> str:
    """The vendored Ketcher build, by file names and sizes.

    Names and sizes rather than content: the bundle is tens of megabytes and
    this only has to tell two builds apart, which a changed size does.
    """
    dist = package_root / "resources" / "ketcher" / "dist"
    if not dist.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        digest.update(f"{path.relative_to(dist).as_posix()}:{path.stat().st_size}\n".encode())
    return digest.hexdigest()


def _versions() -> dict[str, str]:
    found: dict[str, str] = {"python": sys.version.split()[0], "platform": platform.platform()}
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        found["pyside6"], found["qt"] = PySide6.__version__, qVersion()
    except Exception:  # noqa: BLE001
        pass
    try:
        # The distribution's metadata, NOT `import rdkit`: this layer must never
        # import a chemistry engine (tests/test_layering.py), and the version is
        # a property of the installed package, not of the running engine.
        from importlib.metadata import version

        found["rdkit"] = version("rdkit")
    except Exception:  # noqa: BLE001
        pass
    found["java"] = shutil.which("java") or ""
    return found


def log_file_size() -> int:
    """Bytes in the current application log, or 0. Read at the start and end of a run."""
    try:
        from openchem.app.logging_setup import log_file_path

        return log_file_path().stat().st_size
    except Exception:  # noqa: BLE001 - no log file is a fact about the run, not an error
        return 0


@dataclass
class RunIdentity:
    """Enough to say which run, of which script, on which build, wrote a report."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    pid: int = field(default_factory=os.getpid)
    started: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    script: str = ""
    script_sha256: str = ""
    commit: str = ""
    dirty: bool | None = None
    lockfile_sha256: str = ""
    ketcher_bundle: str = ""
    versions: dict[str, str] = field(default_factory=dict)
    log_start: int = 0

    @classmethod
    def capture(cls, script: str | os.PathLike[str] | None) -> "RunIdentity":
        import openchem

        package_root = Path(openchem.__file__).resolve().parent
        repo = package_root.parents[1]
        in_repo = (repo / ".git").exists()
        return cls(
            script=str(script or ""),
            script_sha256=_sha256(Path(script)) if script else "",
            commit=_git(["rev-parse", "HEAD"], repo) if in_repo else "",
            dirty=bool(_git(["status", "--porcelain"], repo)) if in_repo else None,
            lockfile_sha256=_sha256(repo / "uv.lock"),
            ketcher_bundle=_ketcher_bundle_hash(package_root),
            versions=_versions(),
            log_start=log_file_size(),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def write_report(path: Path, payload: dict[str, Any]) -> bool:
    """Write the run report as JSON. Never raises: a report must not fail a run."""
    try:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return True
    except OSError:
        return False
