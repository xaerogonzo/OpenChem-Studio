"""Fetches nmrshiftdb2 and builds the shift index, from a button.

Everything the HOSE lookup needs (`chem/nmr_database.py`) already
existed; what was missing was any way to GET the data without running a
script by hand. A machine that has never had the index built cannot
predict from experiment at all, and silently offering a calculator that
always fails is worse than offering one that says what to do.

The raw distribution is DELETED after indexing by default. It is ~150 MB,
the 15 MB index is the only thing queried afterwards, and keeping it
would triple the footprint for a file that is only needed if the index is
ever rebuilt -- which can re-download it.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from openchem.net import open_url

from openchem.chem.nmr_database import (
    BuildStats,
    build_index,
    database_summary,
    default_database_path,
    connect,
    is_populated,
    stale_format,
)

logger = logging.getLogger("openchem.services")

# The variant carrying PER-ATOM signal assignments. The plain
# `nmrshiftdb2.sd` has spectra but not the atom-level assignment a
# per-environment lookup is built on, so it is the wrong file despite
# being smaller.
SOURCE_FILE = "nmrshiftdb2withsignals.sd"
DOWNLOAD_URL = (
    f"https://sourceforge.net/projects/nmrshiftdb2/files/data/{SOURCE_FILE}/download"
)
APPROX_DOWNLOAD_MB = 152

# Six spheres, measured rather than picked: at four, a para carbon cannot
# see what substituent its ring carries, so toluene's para pooled ~4000
# unrelated measurements and came out 3.6 ppm wrong. At six it matches 6
# and lands within 0.2. Deeper costs index size and nothing else, because
# a lookup already widens on demand.
INDEX_SPHERES = 6


@dataclass(frozen=True)
class SetupProgress:
    step: int
    total: int
    message: str


ProgressCallback = Callable[[SetupProgress], None]


class NmrDatabaseSetupError(RuntimeError):
    """Setup failed, with a message meant to be shown verbatim."""


def describe_status() -> str:
    path = default_database_path()
    if not is_populated(path):
        return (
            "Not built. Database-backed NMR prediction is unavailable until the index exists. "
            f"'Build Index' downloads nmrshiftdb2 (~{APPROX_DOWNLOAD_MB} MB, open content) and "
            "indexes it; the download is discarded afterwards, leaving about 15 MB."
        )
    connection = connect(path)
    try:
        summary = database_summary(connection)
    finally:
        connection.close()
    molecules = summary.get("molecules", "?")
    measurements = summary.get("measurements", "?")
    size_mb = path.stat().st_size / 1e6
    built = (
        f"Built: {int(molecules):,} molecules, {int(measurements):,} assigned shifts "
        f"({size_mb:.1f} MB index)."
        if molecules.isdigit() and measurements.isdigit()
        else f"Built: index present ({size_mb:.1f} MB)."
    )
    if stale_format(path):
        # Offered rather than forced: this index still answers correctly
        # for the environments it can reach, so the cost of not rebuilding
        # is accuracy, not correctness.
        built += (
            " This index predates the single-vocabulary environment codes, so about a third "
            "of it cannot be matched. Rebuilding lowers mean error from 2.91 to 2.85 ppm on "
            "carbon and moves ~2% of atoms into the 'good' band."
        )
    return built


def build(
    on_progress: ProgressCallback | None = None,
    keep_source: bool = False,
    source_path: Path | None = None,
    database_path: Path | None = None,
) -> BuildStats:
    """Download (unless `source_path` is given) and index.

    `source_path` exists so an already-downloaded file can be reused --
    re-indexing after a change to the code that generates environment
    codes should not mean fetching 150 MB again. `database_path` names
    where the index goes, rather than the destination being fixed inside
    the function where no caller can redirect it.
    """
    steps = [
        f"Downloading nmrshiftdb2 (~{APPROX_DOWNLOAD_MB} MB)",
        "Indexing (a few minutes; every atom is coded at six depths)",
    ]

    def report(index: int) -> None:
        if on_progress:
            on_progress(SetupProgress(step=index + 1, total=len(steps), message=steps[index]))

    scratch: Path | None = None
    try:
        if source_path is not None:
            if not source_path.is_file():
                raise NmrDatabaseSetupError(f"No such file: {source_path}")
            sdf = source_path
        else:
            report(0)
            scratch = Path(tempfile.mkdtemp(prefix="nmrshiftdb_"))
            sdf = scratch / SOURCE_FILE
            try:
                with open_url(DOWNLOAD_URL, timeout=300) as response, sdf.open("wb") as target:
                    shutil.copyfileobj(response, target)
            except OSError as exc:
                raise NmrDatabaseSetupError(
                    f"Could not download nmrshiftdb2: {exc}"
                ) from exc
            # A truncated download parses as a shorter database rather than
            # failing, which would produce a quietly worse index -- so the
            # file has to end where a complete SDF record ends.
            if not _looks_complete(sdf):
                raise NmrDatabaseSetupError(
                    "The download did not complete -- the file does not end with a full "
                    "record. Try again."
                )

        report(1)
        stats = build_index(
            sdf, database_path or default_database_path(), max_spheres=INDEX_SPHERES
        )
        if stats.measurements == 0:
            raise NmrDatabaseSetupError(
                "The file was read but contained no assigned spectra. It may be the wrong "
                f"nmrshiftdb2 variant -- this needs {SOURCE_FILE}."
            )
        return stats
    finally:
        if scratch is not None and not keep_source:
            shutil.rmtree(scratch, ignore_errors=True)


def _looks_complete(path: Path) -> bool:
    """An SDF ends with a record terminator. Cheap, and catches the
    failure mode that otherwise passes silently."""
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 64))
            return b"$$$$" in handle.read()
    except OSError:
        return False
