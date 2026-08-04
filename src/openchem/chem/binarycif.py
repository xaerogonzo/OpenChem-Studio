"""BinaryCIF, decoded to the mmCIF text the rest of this app already reads.

WHY DECODE RATHER THAN CARRY THE BINARY. BinaryCIF is a transport format:
the same data model as mmCIF, packed into MessagePack with column
encodings. Nothing downstream here wants it in that shape. Measured: Open
Babel -- which prepares every docking receptor and supplies
`pose_analysis`'s receptor atoms -- reads `pdb`, `mmcif` and `cif` and
does NOT read `bcif`. Carrying binary inward would therefore produce a
receptor that renders in the viewer and cannot be docked, which is the
same "the structure you looked at is not the structure you computed on"
failure this codebase has now fixed four times. Decoding at the boundary
leaves every consumer untouched and `MacromoleculeModel.structure_text`
a `str`, as it already is.

WHY NOT MMTF. Checked, not assumed, and the answer is that it no longer
exists: `mmtf.rcsb.org` fails DNS resolution outright (`getaddrinfo
failed`) in the same run where `files.rcsb.org` and `models.rcsb.org`
both resolve, and the vendored Mol* bundle contains zero occurrences of
the string "mmtf" -- the viewer dropped it too. An importer for it would
read files no one can obtain and display them in nothing.

WHY HAND-ROLLED. `biotite` decodes BinaryCIF, and costs five packages
including scipy and networkx to do it. The encodings are a small closed
set -- seven kinds, all implemented below -- and the result is checkable
against an independent ground truth: RCSB serves the same entry as both
`.bcif` and `.cif`, so the decoder can be held against the text file it
should reproduce. `tests/test_binarycif.py` does exactly that. One small
dependency (`msgpack`) instead of five.

ALL SEVEN ENCODINGS ARE IMPLEMENTED, not just the five that appear in the
file this was developed against. Producers differ: RCSB's own
`python-mmcif` writes coordinates as a plain float64 `ByteArray`, while
Mol*'s encoder writes them `FixedPoint`. Implementing only what one
sample needed would fail on the next file, silently, in the digits.
"""

from __future__ import annotations

import struct
from typing import Any

#: BinaryCIF's type codes for a raw byte array, mapped to `struct` format
#: characters. Everything is little-endian per the specification.
_BYTE_ARRAY_TYPES: dict[int, tuple[str, int]] = {
    1: ("b", 1),  # Int8
    2: ("h", 2),  # Int16
    3: ("i", 4),  # Int32
    4: ("B", 1),  # Uint8
    5: ("H", 2),  # Uint16
    6: ("I", 4),  # Uint32
    32: ("f", 4),  # Float32
    33: ("d", 8),  # Float64
}

#: Mask values, from the specification. 0 means the row has a value; the
#: other two are CIF's two distinct kinds of absence, and they are not
#: interchangeable -- "." is "no value applies here", "?" is "unknown".
_MASK_PRESENT = 0
_MASK_NOT_SPECIFIED = 1  # renders as "."
_MASK_UNKNOWN = 2  # renders as "?"


class BinaryCIFError(ValueError):
    """Raised when a payload is not BinaryCIF, or uses something this
    decoder does not implement. Never returns a partial structure: a
    half-decoded column would be a plausible-looking wrong molecule."""


def _decode_byte_array(data: bytes, encoding: dict[str, Any]) -> list:
    type_code = encoding["type"]
    if type_code not in _BYTE_ARRAY_TYPES:
        raise BinaryCIFError(f"unknown ByteArray type code {type_code}")
    char, size = _BYTE_ARRAY_TYPES[type_code]
    count = len(data) // size
    return list(struct.unpack(f"<{count}{char}", data[: count * size]))


def _decode_fixed_point(values: list, encoding: dict[str, Any]) -> list:
    factor = encoding["factor"]
    return [value / factor for value in values]


def _decode_interval_quantization(values: list, encoding: dict[str, Any]) -> list:
    minimum = encoding["min"]
    maximum = encoding["max"]
    steps = encoding["numSteps"]
    delta = (maximum - minimum) / (steps - 1)
    return [minimum + delta * value for value in values]


def _decode_run_length(values: list, encoding: dict[str, Any]) -> list:
    """Pairs of (value, repeat count), flattened."""
    out: list = []
    for index in range(0, len(values) - 1, 2):
        out.extend([values[index]] * values[index + 1])
    expected = encoding.get("srcSize")
    if expected is not None and len(out) != expected:
        raise BinaryCIFError(
            f"RunLength produced {len(out)} values, header declares {expected}"
        )
    return out


def _decode_delta(values: list, encoding: dict[str, Any]) -> list:
    """Cumulative sum from `origin`. The first stored value is already
    relative to it, so the running total starts AT the origin rather than
    the origin being prepended as an extra element."""
    total = encoding.get("origin", 0)
    out = []
    for value in values:
        total += value
        out.append(total)
    return out


def _decode_integer_packing(values: list, encoding: dict[str, Any]) -> list:
    """Values too large for the packed width are split across several
    entries, each saturated at the type's limit.

    A saturated entry means "add my limit and keep reading", so the run
    accumulates until a non-saturated value terminates it. Signed arrays
    saturate at BOTH ends, and a negative run must be terminated by the
    lower limit rather than the upper -- checking only the upper limit
    decodes large negative numbers as garbage, which for a coordinate is a
    plausible atom in the wrong place.
    """
    byte_count = encoding["byteCount"]
    is_unsigned = encoding["isUnsigned"]
    if is_unsigned:
        upper = (1 << (8 * byte_count)) - 1
        lower = 0
    else:
        upper = (1 << (8 * byte_count - 1)) - 1
        lower = -upper - 1

    out: list = []
    total = 0
    for value in values:
        if value == upper or (not is_unsigned and value == lower):
            total += value
            continue
        out.append(total + value)
        total = 0
    expected = encoding.get("srcSize")
    if expected is not None and len(out) != expected:
        raise BinaryCIFError(
            f"IntegerPacking produced {len(out)} values, header declares {expected}"
        )
    return out


def _decode_string_array(data: bytes, encoding: dict[str, Any]) -> list:
    """A shared string pool plus per-row indices into it.

    `offsets` gives the substring boundaries in `stringData`, and the data
    column holds an index per row -- with **-1 meaning no string at all**,
    which is distinct from the empty string and must not collapse into it.
    """
    offsets = _decode_chain(encoding["offsets"], encoding["offsetEncoding"])
    text = encoding["stringData"]
    pool = [text[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)]
    indices = _decode_chain(data, encoding["dataEncoding"])
    return [None if index < 0 else pool[index] for index in indices]


_DECODERS = {
    "FixedPoint": _decode_fixed_point,
    "IntervalQuantization": _decode_interval_quantization,
    "RunLength": _decode_run_length,
    "Delta": _decode_delta,
    "IntegerPacking": _decode_integer_packing,
}


def _decode_chain(data: bytes, encodings: list[dict[str, Any]]) -> list:
    """Applies an encoding chain in REVERSE.

    The header lists encodings in the order they were APPLIED, so decoding
    runs backwards through them. Getting this the right way round is not
    something a wrong answer announces -- a Delta and a RunLength swapped
    still yields numbers of a believable magnitude.
    """
    current: Any = data
    for encoding in reversed(encodings):
        kind = encoding["kind"]
        if kind == "ByteArray":
            current = _decode_byte_array(current, encoding)
        elif kind == "StringArray":
            current = _decode_string_array(current, encoding)
        elif kind in _DECODERS:
            current = _DECODERS[kind](current, encoding)
        else:
            raise BinaryCIFError(f"unsupported BinaryCIF encoding {kind!r}")
    return current


def _decode_column(column: dict[str, Any]) -> list[str]:
    """One column as CIF-ready strings, absence included.

    Returns strings rather than typed values because the only consumer is
    the mmCIF writer, and a float that has already been through `repr`
    once cannot be rounded a second time. Values arrive from the byte
    array at full precision and are formatted exactly once.
    """
    values = _decode_chain(column["data"]["data"], column["data"]["encoding"])
    mask_field = column.get("mask")
    mask = (
        _decode_chain(mask_field["data"], mask_field["encoding"]) if mask_field else None
    )

    out: list[str] = []
    for index, value in enumerate(values):
        if mask is not None and mask[index] != _MASK_PRESENT:
            out.append("?" if mask[index] == _MASK_UNKNOWN else ".")
        elif value is None:
            out.append(".")
        else:
            out.append(_format_value(value))
    return out


def _format_value(value: Any) -> str:
    """Numbers back to text without inventing or losing digits.

    `repr` on a float is the shortest string that round-trips, which is
    the right choice here: it neither pads 5.5 out to 5.500000 nor rounds
    a coordinate away. Integral floats lose the trailing `.0` because
    mmCIF writes ordinals like `label_seq_id` bare, and a reader that
    parses them as ints would choke on `12.0`.
    """
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _needs_text_field(value: str) -> bool:
    """Whether a value can only be written as a `;`-delimited text field.

    A quoted CIF value CANNOT span lines, and real values do: RCSB stores
    `_entity_poly.pdbx_seq_one_letter_code` as a sequence wrapped across
    several lines, so the decoded string arrives with newlines already in
    it. Wrapping that in single quotes produces a file whose first line
    ends mid-quote -- which Open Babel accepts and Mol* rejects outright,
    so it looked fine right up until the viewer showed nothing.

    Both quote characters present is the other case: there is then no
    inline form left.
    """
    return "\n" in value or ("'" in value and '"' in value)


def _text_field(value: str) -> str:
    """CIF's multi-line form. The delimiters must each start their own
    line, which is why callers splice this in as whole lines rather than
    as a token inside a row."""
    return f";{value}\n;"


def _inline_token(value: str) -> str:
    """A value as a single whitespace-delimited token.

    An empty value is not writable bare -- it would vanish and shift every
    later column on the row, silently renumbering atoms.
    """
    if value == "":
        return "''"
    if value in (".", "?"):
        return value
    needs_quote = any(c.isspace() for c in value) or value[0] in "_$[];'\"#"
    if not needs_quote:
        return value
    return f"'{value}'" if "'" not in value else f'"{value}"'


def _row_lines(values: list[str]) -> list[str]:
    """One loop row as physical lines.

    Usually a single line, but a value needing the text-field form breaks
    the row: the `;` delimiters have to start their own lines, so tokens
    before it are flushed first and tokens after it begin a new line. CIF
    reads a loop as a flat token stream, so a row spanning several lines
    is legal and is what RCSB's own files do here.
    """
    lines: list[str] = []
    current: list[str] = []
    for value in values:
        if _needs_text_field(value):
            if current:
                lines.append(" ".join(current))
                current = []
            lines.append(_text_field(value))
        else:
            current.append(_inline_token(value))
    if current:
        lines.append(" ".join(current))
    return lines


def to_mmcif(payload: bytes) -> str:
    """Decode BinaryCIF bytes to mmCIF text.

    Every category present is written out, rather than a chosen subset:
    the consumers differ (Mol* wants entity and assembly records for a
    faithful view, Open Babel wants `_atom_site`, `pose_analysis` wants
    chains and residues), and picking for them would quietly drop whatever
    the next consumer needed.
    """
    try:
        import msgpack
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise BinaryCIFError("msgpack is required to read BinaryCIF") from exc

    try:
        document = msgpack.unpackb(payload, raw=False)
    except Exception as exc:
        raise BinaryCIFError(f"not a readable MessagePack payload: {exc}") from exc
    if not isinstance(document, dict) or "dataBlocks" not in document:
        raise BinaryCIFError("payload is MessagePack but not BinaryCIF (no dataBlocks)")

    lines: list[str] = []
    for block in document["dataBlocks"]:
        lines.append(f"data_{block.get('header') or 'UNNAMED'}")
        lines.append("#")
        for category in block["categories"]:
            name = category["name"]
            row_count = category["rowCount"]
            columns = category["columns"]
            decoded = {column["name"]: _decode_column(column) for column in columns}

            if row_count == 1:
                # A single-row category is conventionally written as
                # key/value pairs rather than a loop. Both forms are legal
                # mmCIF; this one is what every reference file looks like,
                # and staying conventional keeps diffs against RCSB's own
                # text readable.
                width = max(len(n) for n in decoded) if decoded else 0
                for column_name, values in decoded.items():
                    tag = f"{name}.{column_name}"
                    if _needs_text_field(values[0]):
                        # The tag has to stand alone: a `;` field starts at
                        # the beginning of the line after it.
                        lines.append(tag)
                        lines.append(_text_field(values[0]))
                    else:
                        padded = f"{name}.{column_name:<{width}}"
                        lines.append(f"{padded} {_inline_token(values[0])}")
            else:
                lines.append("loop_")
                for column_name in decoded:
                    lines.append(f"{name}.{column_name}")
                for row in range(row_count):
                    lines.extend(_row_lines([decoded[c][row] for c in decoded]))
            lines.append("#")
    return "\n".join(lines) + "\n"


def looks_like_binary_cif(payload: bytes) -> bool:
    """Cheap sniff, so a caller can route a file without decoding it.

    MessagePack has no magic number, so this checks the one structural
    thing that is always true of BinaryCIF: the top level is a map whose
    keys include `dataBlocks`. Reads only the first bytes rather than
    unpacking a 100 MB structure to answer a yes/no question.
    """
    if not payload[:1]:
        return False
    # A fixmap (0x80-0x8f), map16 (0xde) or map32 (0xdf) at the top.
    first = payload[0]
    if not (0x80 <= first <= 0x8F or first in (0xDE, 0xDF)):
        return False
    return b"dataBlocks" in payload[:4096]
