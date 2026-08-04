"""BinaryCIF decoding, held against files it must reproduce.

The decisive check is not in this file: it is that RCSB serves the same
entry as both `.bcif` and `.cif`, so the decoder can be compared against
a text file written independently of it. That comparison was run live
against two DIFFERENT encoder implementations and is recorded in the
module docstring of `chem/binarycif.py`; it needs the network, so the
tests here work from committed fixtures and from synthetic payloads built
straight out of the specification.

Synthetic matters for a specific reason. Real files exercise only the
encodings their producer happens to emit -- RCSB's `python-mmcif` never
writes `FixedPoint`, and NOTHING among the sources checked writes
`IntervalQuantization`. Testing only against real files would leave those
paths unexecuted while looking like coverage.
"""

from __future__ import annotations

import gzip
import struct

import pytest

from openchem.chem.binarycif import (
    BinaryCIFError,
    looks_like_binary_cif,
    to_mmcif,
)
from openchem.chem.structure_io import StructureReadError, read_structure_bytes

msgpack = pytest.importorskip("msgpack")


def _byte_array(values, type_code):
    """The terminal encoding: raw little-endian values plus its header."""
    char = {1: "b", 2: "h", 3: "i", 4: "B", 5: "H", 6: "I", 32: "f", 33: "d"}[type_code]
    return struct.pack(f"<{len(values)}{char}", *values), {
        "kind": "ByteArray",
        "type": type_code,
    }


def _document(columns, row_count, category="_test", header="TEST"):
    return msgpack.packb(
        {
            "version": "0.3.0",
            "encoder": "openchem test",
            "dataBlocks": [
                {
                    "header": header,
                    "categories": [
                        {"name": category, "rowCount": row_count, "columns": columns}
                    ],
                }
            ],
        },
        use_bin_type=True,
    )


def _column(name, data, encodings, mask=None):
    column = {"name": name, "data": {"data": data, "encoding": encodings}}
    if mask is not None:
        mask_data, mask_encoding = _byte_array(mask, 4)
        column["mask"] = {"data": mask_data, "encoding": [mask_encoding]}
    return column


def _values_of(mmcif_text, tag):
    """Pull one column out of the emitted text, loop or key/value form."""
    values = []
    lines = mmcif_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{tag} "):
            return [line.split(None, 1)[1].strip()]
        if line.strip() == tag:
            # a loop column: find its position, then read the rows
            start = index
            while lines[start - 1].strip().startswith("_"):
                start -= 1
            names = []
            cursor = start
            while lines[cursor].strip().startswith("_"):
                names.append(lines[cursor].strip())
                cursor += 1
            position = names.index(tag)
            while cursor < len(lines) and lines[cursor].strip() not in ("#", ""):
                values.append(lines[cursor].split()[position])
                cursor += 1
            return values
    return values


# --- the seven encodings, each exercised on its own -----------------------


def test_a_plain_byte_array_round_trips():
    data, encoding = _byte_array([1, 2, 3], 3)
    text = to_mmcif(_document([_column("n", data, [encoding])], 3))

    assert _values_of(text, "_test.n") == ["1", "2", "3"]


def test_delta_accumulates_from_its_origin():
    """The stored values are increments. Reading them as absolute numbers
    still yields a monotonic-looking column, which is exactly why this
    needs asserting rather than eyeballing."""
    data, encoding = _byte_array([5, 5, 5], 3)
    text = to_mmcif(
        _document([_column("n", data, [{"kind": "Delta", "origin": 10, "srcType": 3}, encoding])], 3)
    )

    assert _values_of(text, "_test.n") == ["15", "20", "25"]


def test_run_length_expands_value_count_pairs():
    data, encoding = _byte_array([7, 3, 9, 2], 3)
    text = to_mmcif(
        _document(
            [_column("n", data, [{"kind": "RunLength", "srcType": 3, "srcSize": 5}, encoding])], 5
        )
    )

    assert _values_of(text, "_test.n") == ["7", "7", "7", "9", "9"]


def test_fixed_point_divides_by_its_factor():
    """How Mol*'s encoder stores coordinates. Getting the factor wrong
    moves every atom by a power of ten, which still renders."""
    data, encoding = _byte_array([12345, -6789], 3)
    text = to_mmcif(
        _document(
            [_column("x", data, [{"kind": "FixedPoint", "factor": 1000, "srcType": 3}, encoding])],
            2,
        )
    )

    assert _values_of(text, "_test.x") == ["12.345", "-6.789"]


def test_interval_quantization_maps_steps_onto_a_range():
    """Exercised by NO real file among the sources checked -- RCSB and
    PDBe both encode without it -- so this synthetic case is the only
    thing standing between the implementation and silent rot."""
    data, encoding = _byte_array([0, 1, 2], 3)
    text = to_mmcif(
        _document(
            [
                _column(
                    "v",
                    data,
                    [
                        {
                            "kind": "IntervalQuantization",
                            "min": 0.0,
                            "max": 10.0,
                            "numSteps": 3,
                            "srcType": 3,
                        },
                        encoding,
                    ],
                )
            ],
            3,
        )
    )

    assert _values_of(text, "_test.v") == ["0", "5", "10"]


def test_integer_packing_reassembles_oversized_values():
    """A value too large for the packed width is split across entries that
    saturate at the type's limit. 300 does not fit in a signed byte, so it
    arrives as 127 + 127 + 46."""
    data, encoding = _byte_array([127, 127, 46, 5], 1)
    text = to_mmcif(
        _document(
            [
                _column(
                    "n",
                    data,
                    [
                        {
                            "kind": "IntegerPacking",
                            "byteCount": 1,
                            "srcSize": 2,
                            "isUnsigned": False,
                        },
                        encoding,
                    ],
                )
            ],
            2,
        )
    )

    assert _values_of(text, "_test.n") == ["300", "5"]


def test_integer_packing_terminates_a_negative_run_at_the_lower_limit():
    """The asymmetry that a naive implementation misses: a signed array
    saturates at BOTH ends, and a large negative value is terminated by
    -128, not by 127. Checking only the upper limit turns -300 into
    something plausible and wrong."""
    data, encoding = _byte_array([-128, -128, -44], 1)
    text = to_mmcif(
        _document(
            [
                _column(
                    "n",
                    data,
                    [
                        {
                            "kind": "IntegerPacking",
                            "byteCount": 1,
                            "srcSize": 1,
                            "isUnsigned": False,
                        },
                        encoding,
                    ],
                )
            ],
            1,
        )
    )

    assert _values_of(text, "_test.n") == ["-300"]


def test_string_array_resolves_indices_through_the_pool():
    offsets, offset_encoding = _byte_array([0, 3, 6], 4)
    indices, index_encoding = _byte_array([1, 0, 1], 1)
    column = _column(
        "s",
        indices,
        [
            {
                "kind": "StringArray",
                "dataEncoding": [index_encoding],
                "stringData": "CYSGLY",
                "offsetEncoding": [offset_encoding],
                "offsets": offsets,
            }
        ],
    )

    text = to_mmcif(_document([column], 3))

    assert _values_of(text, "_test.s") == ["GLY", "CYS", "GLY"]


def test_a_negative_string_index_is_absence_not_the_empty_string():
    """-1 means no string at all. Collapsing it to "" would write a bare
    empty token, which shifts every later column on that row -- silently
    renumbering atoms rather than failing."""
    offsets, offset_encoding = _byte_array([0, 3], 4)
    indices, index_encoding = _byte_array([-1, 0], 1)
    column = _column(
        "s",
        indices,
        [
            {
                "kind": "StringArray",
                "dataEncoding": [index_encoding],
                "stringData": "GLY",
                "offsetEncoding": [offset_encoding],
                "offsets": offsets,
            }
        ],
    )

    text = to_mmcif(_document([column], 2))

    assert _values_of(text, "_test.s") == [".", "GLY"]


# --- masks, which carry CIF's two distinct kinds of absence ---------------


def test_the_two_mask_values_stay_distinct():
    """"." and "?" are not synonyms in CIF: one says no value applies, the
    other says it is unknown. Folding them together loses a real
    distinction that downstream readers act on."""
    data, encoding = _byte_array([1, 2, 3], 3)
    text = to_mmcif(_document([_column("n", data, [encoding], mask=[0, 1, 2])], 3))

    assert _values_of(text, "_test.n") == ["1", ".", "?"]


# --- the text that comes out ----------------------------------------------


def test_a_value_containing_a_space_is_quoted():
    """Unquoted, it becomes two tokens and every later column on the row
    shifts by one."""
    offsets, offset_encoding = _byte_array([0, 11], 4)
    indices, index_encoding = _byte_array([0], 1)
    column = _column(
        "title",
        indices,
        [
            {
                "kind": "StringArray",
                "dataEncoding": [index_encoding],
                "stringData": "HELLO WORLD",
                "offsetEncoding": [offset_encoding],
                "offsets": offsets,
            }
        ],
    )

    text = to_mmcif(_document([column], 1))

    assert "'HELLO WORLD'" in text


def _string_column(name, pool_words, indices):
    """A StringArray column built from whole words, for the text tests."""
    offsets_values, position = [0], 0
    for word in pool_words:
        position += len(word)
        offsets_values.append(position)
    offsets, offset_encoding = _byte_array(offsets_values, 6)
    data, data_encoding = _byte_array(indices, 1)
    return _column(
        name,
        data,
        [
            {
                "kind": "StringArray",
                "dataEncoding": [data_encoding],
                "stringData": "".join(pool_words),
                "offsetEncoding": [offset_encoding],
                "offsets": offsets,
            }
        ],
    )


def test_a_value_containing_a_newline_uses_the_semicolon_text_field():
    """The bug the viewer caught and nothing else did.

    `_entity_poly.pdbx_seq_one_letter_code` arrives with newlines already
    in it -- RCSB stores the sequence wrapped. Quoting that inline
    produces a line that ends mid-quote. Open Babel accepted the result
    and reported the right atom and residue counts; Mol* rejected the
    whole file and rendered nothing, so the defect was invisible from
    Python and obvious the moment the structure was put on screen.

    A `;` field must own its lines, and the delimiters must sit at column
    zero, or the next reader mis-frames every row after it.
    """
    text = to_mmcif(_document([_string_column("seq", ["AAA\nBBB"], [0])], 1))

    lines = text.splitlines()
    assert "_test.seq" in lines
    start = lines.index("_test.seq")
    assert lines[start + 1] == ";AAA"
    assert lines[start + 2] == "BBB"
    assert lines[start + 3] == ";"


def test_a_multi_line_value_inside_a_loop_breaks_the_row_correctly():
    """Same rule, harder case: in a loop the row becomes several physical
    lines, with the tokens before and after the text field on their own.
    Emitting the `;` inline would leave the row one token short and shift
    every column after it."""
    columns = [
        _string_column("a", ["one"], [0, 0]),
        _string_column("b", ["multi\nline", "plain"], [0, 1]),
        _string_column("c", ["last"], [0, 0]),
    ]

    text = to_mmcif(_document(columns, 2))

    lines = text.splitlines()
    body = lines[lines.index("_test.c") + 1 :]
    body = [line for line in body if line.strip() != "#"]
    assert body[0] == "one"
    assert body[1] == ";multi"
    assert body[2] == "line"
    assert body[3] == ";"
    assert body[4] == "last"
    # the second row has no multi-line value, so it stays on one line
    assert body[5] == "one plain last"


def test_the_block_header_survives():
    data, encoding = _byte_array([1], 3)
    text = to_mmcif(_document([_column("n", data, [encoding])], 1, header="5C1M"))

    assert text.startswith("data_5C1M")


def test_a_non_binarycif_payload_is_refused_clearly():
    """Not an assertion error from somewhere deep inside a decode -- a
    reader handed a PDB file by mistake should be told which of the two
    things is wrong."""
    with pytest.raises(BinaryCIFError, match="not a readable MessagePack"):
        to_mmcif(b"ATOM      1  N   MET A   1      1.0 2.0 3.0\n")

    with pytest.raises(BinaryCIFError, match="not BinaryCIF"):
        to_mmcif(msgpack.packb({"something": "else"}, use_bin_type=True))


def test_an_unknown_encoding_raises_rather_than_guessing():
    data, encoding = _byte_array([1], 3)
    with pytest.raises(BinaryCIFError, match="unsupported"):
        to_mmcif(_document([_column("n", data, [{"kind": "Invented"}, encoding])], 1))


# --- sniffing and the file reader -----------------------------------------


def test_binary_cif_is_recognised_without_decoding_it():
    data, encoding = _byte_array([1], 3)
    payload = _document([_column("n", data, [encoding])], 1)

    assert looks_like_binary_cif(payload)
    assert not looks_like_binary_cif(b"data_TEST\n_entry.id TEST\n")
    assert not looks_like_binary_cif(b"")


def test_the_reader_decides_by_content_not_by_extension():
    """A renamed file must still work. The alternative is a
    UnicodeDecodeError from inside a file read, which names neither the
    file nor the real problem."""
    data, encoding = _byte_array([1], 3)
    payload = _document([_column("n", data, [encoding])], 1)

    text, source_format = read_structure_bytes(payload, "misnamed.cif")

    assert source_format == "mmcif"
    assert text.startswith("data_TEST")


def test_gzip_is_unpacked_transparently():
    """How these files actually arrive -- RCSB's download links serve
    `.cif.gz` by default."""
    text, source_format = read_structure_bytes(gzip.compress(b"data_X\n_entry.id X\n"), "x.cif")

    assert source_format == "mmcif"
    assert text.startswith("data_X")


def test_a_gzipped_binary_cif_works_too():
    data, encoding = _byte_array([1], 3)
    payload = gzip.compress(_document([_column("n", data, [encoding])], 1))

    text, source_format = read_structure_bytes(payload, "x.bcif")

    assert source_format == "mmcif"
    assert text.startswith("data_TEST")


def test_plain_text_keeps_its_extension_derived_format():
    assert read_structure_bytes(b"ATOM  \n", "x.pdb")[1] == "pdb"
    assert read_structure_bytes(b"data_X\n", "x.cif")[1] == "mmcif"
    assert read_structure_bytes(b"data_X\n", "x.mmcif")[1] == "mmcif"


def test_undecodable_bytes_are_reported_as_such():
    with pytest.raises(StructureReadError, match="neither text nor BinaryCIF"):
        read_structure_bytes(b"\xff\xfe\x00\x01 not utf-8 and not msgpack", "x.pdb")
