"""Reading a structure file into the (text, format) pair the app uses.

One place that knows how a file on disk becomes
`MacromoleculeModel.structure_text` plus a Mol*-vocabulary
`source_format`, so the UI layer never has to.

DECIDED BY CONTENT, NOT BY EXTENSION. A `.cif` that is actually
BinaryCIF, or a `.bcif` someone renamed, both happen -- and the failure
without sniffing is not a clean error but a `UnicodeDecodeError` from
deep inside a file read, which names neither the file nor the real
problem. Sniffing costs a few bytes and the extension is still used to
break the remaining tie between PDB and mmCIF text, which genuinely
cannot be told apart cheaply.

GZIP IS HANDLED because that is how these files actually arrive: RCSB's
download links serve `.cif.gz` by default, and a user who saved one had
no way to open it here at all.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from openchem.chem.binarycif import looks_like_binary_cif, to_mmcif

#: The first two bytes of any gzip member (RFC 1952).
_GZIP_MAGIC = b"\x1f\x8b"

#: Extensions that mean mmCIF text rather than PDB text. Only consulted
#: once the content has already ruled out the binary formats.
_MMCIF_SUFFIXES = {".cif", ".mmcif"}

#: What the file dialog should offer. Kept here beside the reader that has
#: to honour it, so the two cannot drift into offering a format nothing
#: opens.
STRUCTURE_FILE_FILTER = (
    "Structure files (*.pdb *.ent *.cif *.mmcif *.bcif "
    "*.pdb.gz *.ent.gz *.cif.gz *.mmcif.gz *.bcif.gz)"
)


class StructureReadError(ValueError):
    """Raised when a file cannot be read as any structure format we know."""


def read_structure_bytes(payload: bytes, filename: str = "") -> tuple[str, str]:
    """`(structure_text, source_format)` from a file's raw bytes.

    Separated from the path-based reader so the decision logic is testable
    without touching a filesystem, and so a caller holding bytes from
    elsewhere (a download, an archive member) uses the same rules.
    """
    if payload[:2] == _GZIP_MAGIC:
        try:
            payload = gzip.decompress(payload)
        except OSError as exc:
            raise StructureReadError(f"gzip data could not be decompressed: {exc}") from exc

    if looks_like_binary_cif(payload):
        # Decoded rather than kept binary -- see `binarycif`'s module
        # docstring for why nothing downstream wants the packed form.
        return to_mmcif(payload), "mmcif"

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StructureReadError(
            "file is neither text nor BinaryCIF -- if it is a structure "
            f"format, it is one this app does not read ({exc})"
        ) from exc

    suffix = Path(filename).suffix.lower()
    return text, "mmcif" if suffix in _MMCIF_SUFFIXES else "pdb"


def read_structure_file(path: Path) -> tuple[str, str]:
    """`(structure_text, source_format)` for a file on disk.

    A gzipped name carries two suffixes, so the format tie-break looks at
    the one before `.gz` -- `structure.cif.gz` is mmCIF, and treating it
    as PDB because its last suffix is `.gz` would hand Mol* and Open Babel
    a file whose declared format is a lie.
    """
    payload = path.read_bytes()
    name = path.name
    if name.lower().endswith(".gz"):
        name = name[: -len(".gz")]
    return read_structure_bytes(payload, name)
