"""Keeping expensive results, keyed by what actually produced them.

WHY THIS EXISTS, AND IT IS NOT PRIMARILY SPEED. `CacheState`
(`domain/common.py`) has always been a LIFECYCLE enum -- QUEUED, RUNNING,
COMPLETED, FAILED -- and never storage. So a geometry optimisation that
took forty minutes is recomputed on demand, and the ORCA scratch directory
it ran in is deleted in a `finally` and inventoried as "always safe to
remove". The deletion is right; an optimisation leaves gigabytes. What was
wrong is that nothing survived it in a form anyone could point at later.

Reproducibility is the larger half of the argument. A result that can be
re-opened, with the method and basis and the structure that produced it
recorded beside it, is a record. A result that has to be recomputed to be
seen again is a rumour.

THE KEY IS THE WHOLE DESIGN, and it is content-addressed for a reason that
is not tidiness. The first retention in this codebase --
`quantum_chemistry_service._retain_wavefunction` -- was keyed by
`molecule_uuid`, and a molecule's uuid is STABLE ACROSS STRUCTURE EDITS.
`EditStructureCommand` clears a molecule's conformers when its structure
changes, because Phase 9.1 established that they described the old
structure; the retained wavefunction was never given the same treatment.
So: draw benzene, run ORCA, edit the structure to toluene, ask for the
HOMO -- and the surface plots benzene's orbitals against toluene, silently,
because the only check was that a file existed under that uuid.

Keying on the structure and the method makes that impossible rather than
merely unlikely. Edit the structure and the key changes, so the outcome is
a MISS -- a recomputation -- instead of a confident wrong answer. A cache
whose key omits an input is not a cache, it is a way of serving stale data
with extra steps.

WHAT GOES IN THE KEY: everything that changes the answer, and nothing that
does not. The structure in a canonical form, the method, the basis, the
calculation type, and any option that alters the result. NOT the molecule's
uuid, its display name, or when it was run -- two identical calculations on
the same structure in two different projects are the same calculation, and
should hit.

FAILURES ARE NEVER CACHED. A job that failed for a transient reason -- a
sidecar that was not installed yet, a disk that was full -- must be
retryable by running it again, and a cached failure turns a fixed
environment into a permanently broken one.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openchem import paths as app_paths

logger = logging.getLogger("openchem.services")

#: Bumped when the on-disk layout or the key recipe changes in a way that
#: makes existing entries wrong rather than merely old. Entries under a
#: different version are ignored and can be deleted, which is safer than
#: attempting a migration of data that is by definition regenerable.
CACHE_VERSION = 1

_MANIFEST_NAME = "entry.json"


@dataclass(frozen=True)
class CacheEntry:
    """One stored result: where its files are, and what produced them."""

    key: str
    directory: Path
    kind: str
    created_at: float
    #: Everything that went into the key, kept in readable form. This is
    #: what makes the entry a record rather than an opaque blob -- someone
    #: looking at it months later can see the method and basis without
    #: reversing a hash.
    inputs: dict[str, Any]
    metadata: dict[str, Any]

    def file(self, name: str) -> Path | None:
        candidate = self.directory / name
        return candidate if candidate.is_file() else None

    def size_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.directory.rglob("*") if p.is_file())


def cache_root() -> Path:
    """Where entries live.

    Under the wavefunction root rather than `paths.cache_root()`, which is
    scratch and is advertised to the user as always-safe-to-delete. These
    entries are safe to delete too -- everything here is regenerable -- but
    deleting them costs hours of recomputation, which is a different
    proposition from deleting a scratch directory, and the storage UI
    should be able to say so separately.
    """
    return app_paths.wavefunction_root().parent / "results"


def parameters_key(parameters: dict[str, Any] | None) -> str:
    """A stable key for one calculator's parameter set.

    **A THIN WRAPPER, SO THERE IS ONE RECIPE AND NOT TWO.** The retained
    batch results are keyed partly on their parameters, and the obvious
    alternative -- `str(sorted(parameters.items()))` at the call site --
    is a second serialisation scheme that would drift from this one and
    make two identical requests into two different keys. `key_for` already
    solves this: sorted JSON into SHA-256, stable across processes and
    sessions, and it stringifies values rather than trusting them to
    serialise so an enum or a Path cannot turn a cache into an outage.

    Empty parameters give a stable key too, rather than "" -- a calculator
    with no settings still has a parameter set, and it is the empty one.
    """
    return key_for("calculator_parameters", **(parameters or {}))


def key_for(kind: str, **inputs: Any) -> str:
    """A stable key from everything that determines a result.

    Stable ACROSS PROCESSES and across sessions, which rules out `hash()`
    (randomised per process by PYTHONHASHSEED) and rules out anything
    depending on dict ordering. Sorted JSON into SHA-256.

    Values are stringified rather than trusted to serialise: a caller
    passing an enum, a Path or a float is normal, and a key that raises on
    an unexpected type turns a cache into an outage.
    """
    payload = {
        "version": CACHE_VERSION,
        "kind": kind,
        "inputs": {str(k): _stringify(v) for k, v in sorted(inputs.items())},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def lookup(kind: str, **inputs: Any) -> CacheEntry | None:
    """The stored result for these exact inputs, or None."""
    return entry_for(key_for(kind, **inputs))


def entry_for(key: str) -> CacheEntry | None:
    directory = cache_root() / key
    manifest = directory / _MANIFEST_NAME
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A half-written manifest is a miss, not a crash. The result it
        # described is regenerable by definition.
        return None
    if data.get("version") != CACHE_VERSION:
        return None
    return CacheEntry(
        key=key,
        directory=directory,
        kind=str(data.get("kind", "")),
        created_at=float(data.get("created_at", 0.0)),
        inputs=dict(data.get("inputs", {})),
        metadata=dict(data.get("metadata", {})),
    )


def store(
    kind: str,
    files: dict[str, Path],
    metadata: dict[str, Any] | None = None,
    **inputs: Any,
) -> CacheEntry | None:
    """Copy `files` into a new entry for these inputs.

    Best-effort: a cache that cannot write must not fail the calculation
    whose result it was trying to keep. Returns None and logs.

    Writes the manifest LAST. A reader treats a directory with no manifest
    as a miss, so a run interrupted mid-copy leaves an entry that is
    ignored rather than one that is half-present and trusted.
    """
    key = key_for(kind, **inputs)
    directory = cache_root() / key
    try:
        # Replaced rather than merged. A partially-overwritten entry mixes
        # files from two runs, and for a wavefunction that means a `.gbw`
        # and a `.densities` that do not describe the same calculation --
        # exactly the mismatch `_retain_wavefunction` already warns about.
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)

        for name, source in files.items():
            if source.is_file():
                shutil.copy2(source, directory / name)

        manifest = {
            "version": CACHE_VERSION,
            "kind": kind,
            "created_at": time.time(),
            "inputs": {str(k): _stringify(v) for k, v in sorted(inputs.items())},
            "metadata": dict(metadata or {}),
        }
        (directory / _MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=1), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not cache %s result: %s", kind, exc)
        shutil.rmtree(directory, ignore_errors=True)
        return None
    return entry_for(key)


def find(kind: str, **must_match: Any) -> CacheEntry | None:
    """The newest entry whose inputs include these values, or None.

    A PARTIAL-key search, and deliberately separate from `lookup`, which
    needs every input that went into the key. Both exist because callers
    genuinely differ: the code that stores a wavefunction knows the
    structure, the method and the calculation type, while the code that
    later wants to plot a surface from one knows only the structure.

    Restricting a search to "same structure" is not a weakening. The
    per-molecule retention this backs up never matched on method at all --
    it serves whatever was last run on that molecule -- so a match on
    structure alone is exactly as strong, and turns misses into hits
    without making any hit less true.

    Newest first, because when the same structure has been computed
    several ways the most recent is the one the user was working on.
    """
    wanted = {str(k): _stringify(v) for k, v in must_match.items()}
    for entry in entries(kind):
        if all(entry.inputs.get(k) == v for k, v in wanted.items()):
            return entry
    return None


def entries(kind: str | None = None) -> list[CacheEntry]:
    """Every stored entry, newest first."""
    root = cache_root()
    if not root.is_dir():
        return []
    found = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        entry = entry_for(directory.name)
        if entry is not None and (kind is None or entry.kind == kind):
            found.append(entry)
    return sorted(found, key=lambda e: e.created_at, reverse=True)


def total_size_bytes() -> int:
    root = cache_root()
    if not root.is_dir():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def clear(kind: str | None = None) -> int:
    """Delete stored entries and report how many bytes went.

    Everything here is regenerable, so this is always safe -- the cost is
    time, not data.
    """
    freed = 0
    for entry in entries(kind):
        try:
            freed += entry.size_bytes()
            shutil.rmtree(entry.directory, ignore_errors=True)
        except OSError as exc:  # noqa: PERF203 - one bad entry must not stop the rest
            logger.warning("Could not remove cache entry %s: %s", entry.key, exc)
    return freed


def _stringify(value: Any) -> Any:
    """A key-safe form of a value.

    Numbers and booleans keep their type so 1 and "1" cannot collide;
    everything else becomes its string, which is what makes the function
    total. `None` is kept distinct from the empty string for the same
    reason -- "no basis set specified" and "basis set called ''" are
    different inputs even though both are falsy.
    """
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_stringify(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _stringify(v) for k, v in sorted(value.items())}
    return str(value)
