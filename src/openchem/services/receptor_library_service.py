"""Fetch catalogued receptor structures from RCSB, and keep them.

The catalogue (`chem/receptor_library.py`) ships identifiers; the
coordinates live at RCSB. This is the piece that goes and gets them, and
caches each one on disk so the second use of a target costs nothing and
works offline.

NOTHING HERE FIRES ON ITS OWN. A download happens because a user picked
an entry, matching how every other network path in this app behaves (the
naming providers, the database and sidecar installers). Opening the
catalogue browser downloads nothing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from openchem.chem.receptor_library import ReceptorEntry
from openchem.net import open_url
from openchem.paths import subdirectory

logger = logging.getLogger("openchem.services")

#: RCSB serves the whole archive from here with no key and no rate limit
#: worth engineering around. `.pdb` rather than `.cif` because the app's
#: receptor path is better exercised on PDB, and every catalogue entry was
#: checked to have one -- very large modern deposits are mmCIF-only, and
#: `_MMCIF_FALLBACK` covers that without failing the download.
_PDB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
_MMCIF_FALLBACK = "https://files.rcsb.org/download/{pdb_id}.cif"

#: A structure is a few hundred KB to a few MB. Generous enough for a slow
#: connection, short enough that a hung fetch does not look like a freeze.
_TIMEOUT_SECONDS = 120


def cache_directory() -> Path:
    return subdirectory("receptors")


def cached_path(pdb_id: str, source_format: str = "pdb") -> Path:
    suffix = "cif" if source_format == "mmcif" else "pdb"
    return cache_directory() / f"{pdb_id.upper()}.{suffix}"


def is_cached(pdb_id: str) -> bool:
    return any(cached_path(pdb_id, fmt).is_file() for fmt in ("pdb", "mmcif"))


def cached_structure(pdb_id: str) -> tuple[str, str] | None:
    """Returns `(structure_text, source_format)` if already downloaded."""
    for source_format in ("pdb", "mmcif"):
        path = cached_path(pdb_id, source_format)
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace"), source_format
            except OSError:
                logger.warning("Cached receptor %s unreadable; will re-fetch", path)
    return None


def fetch_structure(pdb_id: str, timeout: float = _TIMEOUT_SECONDS) -> tuple[str, str]:
    """Download `pdb_id` (or return the cached copy) as
    `(structure_text, source_format)`.

    Tries PDB format first and falls back to mmCIF, because RCSB genuinely
    has no `.pdb` for entries too large for the fixed-column format --
    which is a normal outcome for big cryo-EM channel structures, not an
    error. `source_format` uses Mol*'s vocabulary so it can go straight
    into `MacromoleculeModel` without translation.
    """
    cached = cached_structure(pdb_id)
    if cached is not None:
        return cached

    identifier = pdb_id.strip().upper()
    attempts = ((_PDB_URL, "pdb"), (_MMCIF_FALLBACK, "mmcif"))
    last_error: Exception | None = None
    for template, source_format in attempts:
        try:
            payload = open_url(template.format(pdb_id=identifier), timeout=timeout).read()
        except Exception as exc:  # noqa: BLE001 - reported, and the fallback still runs
            last_error = exc
            continue
        text = payload.decode("utf-8", errors="replace")
        _write_cache(identifier, source_format, text)
        return text, source_format

    raise RuntimeError(
        f"Could not download {identifier} from RCSB: {last_error}. "
        "Check the network connection, or download the structure manually "
        "and use File > Import Macromolecule."
    )


def _write_cache(pdb_id: str, source_format: str, text: str) -> None:
    """Cache write failures are logged, not raised -- a read-only or full
    data directory should cost the user a re-download next time, not the
    structure they just successfully fetched."""
    try:
        path = cached_path(pdb_id, source_format)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        logger.warning("Could not cache receptor %s", pdb_id, exc_info=True)


def entry_metadata(entry: ReceptorEntry) -> dict[str, object]:
    """What to put in `MacromoleculeModel.metadata` for a catalogue import.

    Deliberately includes `ligand_code`: it is what lets the docking panel
    re-derive the search box later without the user having to remember
    which component defined the site.
    """
    return {
        "pdb_id": entry.pdb_id,
        "target": entry.target,
        "family": entry.family,
        "resolution": entry.resolution_angstrom,
        "method": entry.method,
        "state": entry.state,
        "ligand_code": entry.ligand_code,
        "ligand_name": entry.ligand_name,
        "caveat": entry.caveat,
        "source": "RCSB Protein Data Bank",
        "source_url": f"https://www.rcsb.org/structure/{entry.pdb_id}",
    }
