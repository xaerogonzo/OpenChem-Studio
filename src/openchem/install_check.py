"""Is this installation still the one that was built? (No Qt; pure.)

A release is a folder of files, and a person can change one by accident: an
editor saving over a data file, an unzip over an older version, a half-finished
copy. Most of the application's own data files fail SILENTLY when that happens
(a rules table that loads fewer rules, a record that reads `unvalidated`), so
nobody is told. This module says so.

WHAT IT CLAIMS, AND WHAT IT DOES NOT. It detects ACCIDENTAL change to the data
files this application ships, by comparing each against the sha256 and size
taken when the build was made. It does not repair anything, does not block
anything, and is not tamper protection: the expected hashes ride inside the same
unsigned executable, so someone who can rewrite the files can rewrite those.
Authenticity is a signature's job (see the release notes), not this module's.

THE MANIFEST COMES FROM THE SPEC'S OWN `datas` LIST (`build_manifest`), after the
data entries are assembled and before PyInstaller runs, so there is no second
hand-written map of source path to installed path to drift out of step with it.
The mapping is then proved twice: the built tree is checked with `verify`, and
the frozen smoke test asserts the running exe reaches `verified`.

IN SCOPE: every `datas` entry whose source is under `src/openchem` (resources,
vendored data, the ChEMBL lists, `chem/data`, the sidecar runner scripts).
DELIBERATELY OUT: third-party packages (Qt, numpy, RDKit, Open Babel, py2opsin),
`plugins/` (editable by design), the human `docs/` copy (never read) and
everything the user owns (data directory, settings). Files present in the
install but not in the manifest are ignored: the installed tree is fixed, so an
extra file is not corruption.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

#: The format of the manifest module; a module of any other schema is `check_failed`.
MANIFEST_SCHEMA = 1

#: Read size when hashing; large enough that the 44 MB of web assets is not a thousand tiny reads.
_CHUNK = 1 << 20


class InstallCheckError(ValueError):
    """The manifest cannot be built or trusted."""


class Status(str, Enum):
    NOT_APPLICABLE = "not_applicable"  # not a frozen build: nothing was installed
    CHECKING = "checking"
    VERIFIED = "verified"
    MODIFIED = "modified"  # at least one file differs, is missing or unreadable
    CHECK_FAILED = "check_failed"  # the check itself could not be made; never "verified"


@dataclass(frozen=True)
class InstallCheckResult:
    status: Status
    checked: int = 0
    modified: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unreadable: tuple[str, ...] = ()
    detail: str = ""

    @property
    def problems(self) -> int:
        return len(self.modified) + len(self.missing) + len(self.unreadable)

    def summary(self) -> str:
        """One line for About. Counts only; paths go in `report`, never file contents."""
        if self.status is Status.NOT_APPLICABLE:
            return "not applicable (running from source)"
        if self.status is Status.CHECKING:
            return "checking..."
        if self.status is Status.VERIFIED:
            return f"verified ({self.checked} data files match the build)"
        if self.status is Status.CHECK_FAILED:
            return f"could not be checked ({self.detail})"
        parts = [
            f"{len(items)} {label}"
            for items, label in ((self.modified, "changed"), (self.missing, "missing"), (self.unreadable, "unreadable"))
            if items
        ]
        return "MODIFIED: " + ", ".join(parts) + ". Re-extract or reinstall the release."

    def report(self, limit: int = 20) -> str:
        """The summary plus the affected relative paths (capped), for a bug report."""
        lines = [self.summary()]
        for label, items in (("changed", self.modified), ("missing", self.missing), ("unreadable", self.unreadable)):
            lines += [f"  {label}: {path}" for path in items[:limit]]
            if len(items) > limit:
                lines.append(f"  ... and {len(items) - limit} more {label}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building the manifest (build time, from the spec)
# ---------------------------------------------------------------------------


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _walk(source: Path):
    """Every regular file under `source` (or `source` itself), refusing links and oddities."""
    if source.is_symlink():
        raise InstallCheckError(f"a symbolic link is not a data file: {source}")
    if source.is_file():
        yield source, source.name
        return
    if not source.is_dir():
        raise InstallCheckError(f"a data entry names something that is not there: {source}")
    for path in sorted(source.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise InstallCheckError(f"a symbolic link is not a data file: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise InstallCheckError(f"not a regular file: {path}")
        yield path, path.relative_to(source).as_posix()


def build_manifest(
    datas,
    package_root: Path,
    *,
    drop_prefixes: tuple[str, ...] = (),
) -> list[tuple[str, str, int]]:
    """``[(installed path, sha256, size)]`` for the package's own data files.

    `datas` is PyInstaller's ``[(source, destination directory)]``. Only entries
    whose source lies under `package_root` are taken, and `drop_prefixes` removes
    installed paths the spec's own filter removes, so the two cannot disagree.
    Raises `InstallCheckError` for a link, a non-regular file, a path that
    escapes its root, a duplicate (compared case-insensitively, since the
    install is on Windows) or no files at all: a manifest of nothing would
    report `verified` for a tree it never looked at.
    """
    root = Path(package_root).resolve()
    entries: dict[str, tuple[str, int]] = {}
    seen_folded: dict[str, str] = {}
    for source, destination in datas:
        source_path = Path(source)
        try:
            source_path.resolve().relative_to(root)
        except ValueError:
            continue  # third-party data: out of scope on purpose
        for file_path, relative in _walk(source_path):
            installed = PurePosixPath(str(destination).replace("\\", "/")) / relative
            text = installed.as_posix()
            if installed.is_absolute() or ".." in installed.parts:
                raise InstallCheckError(f"an installed path escapes its root: {text}")
            if any(text.startswith(prefix) for prefix in drop_prefixes):
                continue
            if text in entries or text.casefold() in seen_folded:
                raise InstallCheckError(f"two data entries install to the same path: {text}")
            entries[text] = _hash_file(file_path)
            seen_folded[text.casefold()] = text
    if not entries:
        raise InstallCheckError("the manifest would be empty; refusing to build a check that checks nothing")
    return [(path, digest, size) for path, (digest, size) in sorted(entries.items())]


def render_module(files: list[tuple[str, str, int]]) -> str:
    """The text of the generated `_integrity.py`: plain literals, no code."""
    lines = ["# Generated by packaging/openchem.spec -- do not edit, do not commit.", f"SCHEMA = {MANIFEST_SCHEMA}", "FILES = ("]
    lines += [f"    ({path!r}, {digest!r}, {size})," for path, digest, size in files]
    lines.append(")")
    return "\n".join(lines) + "\n"


def write_module_atomically(path: Path, files: list[tuple[str, str, int]]) -> None:
    """Temp file beside the target, then replace: an interrupted build leaves no half module."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(render_module(files))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Verifying (run time, and the post-freeze check)
# ---------------------------------------------------------------------------


def validate_manifest(schema: object, files: object) -> list[tuple[str, str, int]]:
    """The entries of a manifest, or `InstallCheckError` saying what is wrong."""
    if schema != MANIFEST_SCHEMA:
        raise InstallCheckError(f"unsupported manifest schema ({schema!r})")
    if not isinstance(files, (tuple, list)) or not files:
        raise InstallCheckError("the manifest holds no files")
    checked: list[tuple[str, str, int]] = []
    folded: set[str] = set()
    for entry in files:
        if not (isinstance(entry, (tuple, list)) and len(entry) == 3):
            raise InstallCheckError("a manifest entry is malformed")
        path, digest, size = entry
        if not (isinstance(path, str) and isinstance(digest, str) and isinstance(size, int) and size >= 0):
            raise InstallCheckError("a manifest entry has the wrong field types")
        pure = PurePosixPath(path)
        if not path or "\\" in path or pure.is_absolute() or ".." in pure.parts or (len(path) > 1 and path[1] == ":"):
            raise InstallCheckError(f"a manifest path is not a relative installed path: {path!r}")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InstallCheckError(f"a manifest digest is not a sha256: {path}")
        if path.casefold() in folded:
            raise InstallCheckError(f"the manifest names a path twice: {path}")
        folded.add(path.casefold())
        checked.append((path, digest, size))
    return checked


def verify(files: list[tuple[str, str, int]], root: Path) -> InstallCheckResult:
    """Compare every manifest entry with the file under `root`.

    Separate lists for changed, missing and unreadable; one unreadable file
    anywhere means the verdict is `modified`, never `verified`.
    """
    root = Path(root)
    if not root.is_dir():
        return InstallCheckResult(Status.CHECK_FAILED, detail="the install folder was not found")
    modified: list[str] = []
    missing: list[str] = []
    unreadable: list[str] = []
    for path, digest, size in files:
        target = root.joinpath(*PurePosixPath(path).parts)
        try:
            if not target.is_file():
                missing.append(path)
                continue
            if target.stat().st_size != size:
                modified.append(path)
                continue
            if _hash_file(target)[0] != digest:
                modified.append(path)
        except OSError:
            unreadable.append(path)
    if modified or missing or unreadable:
        return InstallCheckResult(
            Status.MODIFIED,
            checked=len(files),
            modified=tuple(modified),
            missing=tuple(missing),
            unreadable=tuple(unreadable),
        )
    return InstallCheckResult(Status.VERIFIED, checked=len(files))


def install_root() -> Path | None:
    """Where a frozen build's data files were unpacked (`_internal`), else None."""
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle) if bundle else None


def check_installed() -> InstallCheckResult:
    """The whole check for the running application. Never raises."""
    if not getattr(sys, "frozen", False):
        return InstallCheckResult(Status.NOT_APPLICABLE)
    try:
        # import_module, not `from openchem import _integrity`: a missing submodule
        # there is a bare ImportError, which cannot say WHICH module was missing.
        _integrity = importlib.import_module("openchem._integrity")
    except ModuleNotFoundError as exc:
        if exc.name == "openchem._integrity":
            return InstallCheckResult(Status.CHECK_FAILED, detail="this build has no manifest")
        return InstallCheckResult(Status.CHECK_FAILED, detail=f"the manifest could not be imported ({exc.name})")
    except Exception as exc:  # noqa: BLE001 - reported as a failed check, never raised into the app
        return InstallCheckResult(Status.CHECK_FAILED, detail=f"the manifest could not be imported ({type(exc).__name__})")
    try:
        files = validate_manifest(getattr(_integrity, "SCHEMA", None), getattr(_integrity, "FILES", None))
    except InstallCheckError as exc:
        return InstallCheckResult(Status.CHECK_FAILED, detail=str(exc))
    root = install_root()
    if root is None:
        return InstallCheckResult(Status.CHECK_FAILED, detail="the install folder is not known")
    try:
        return verify(files, root)
    except Exception as exc:  # noqa: BLE001 - the check must never take the app down
        return InstallCheckResult(Status.CHECK_FAILED, detail=f"the check failed ({type(exc).__name__})")


# ---------------------------------------------------------------------------
# The latest answer, for About and for anything that wants to ask
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_current = InstallCheckResult(Status.NOT_APPLICABLE if not getattr(sys, "frozen", False) else Status.CHECKING)


def current() -> InstallCheckResult:
    """The latest result: `checking` until the first one arrives, in a frozen build."""
    with _lock:
        return _current


def record(result: InstallCheckResult) -> None:
    global _current
    with _lock:
        _current = result
