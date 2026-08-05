"""Reading JCAMP-DX, the format instruments emit.

NOT VALIDATED AGAINST A REAL INSTRUMENT FILE. No JCAMP-DX file was
available on the reference machine, so these fixtures are written by hand
to exercise each encoding the spec defines. That shows the decoders match
the SPEC; it does not show they match what a particular vendor writes, and
vendor deviation is this format's main practical hazard.
"""

from __future__ import annotations

import pytest

from openchem.chem.jcamp import JcampError, parse


def _doc(points: int, data: str, **overrides: str) -> str:
    headers = {
        "TITLE": "test spectrum",
        "XUNITS": "1/CM",
        "YUNITS": "TRANSMITTANCE",
        "FIRSTX": "1000",
        "LASTX": str(1000 + points - 1),
        "DELTAX": "1",
        "NPOINTS": str(points),
        "XFACTOR": "1",
        "YFACTOR": "1",
    }
    headers.update(overrides)
    lines = [f"##{key}={value}" for key, value in headers.items()]
    lines.append("##XYDATA=(X++(Y..Y))")
    lines.append(data)
    lines.append("##END=")
    return "\n".join(lines)


# --- The four encodings -------------------------------------------------


def test_pac_plain_numbers():
    assert parse(_doc(5, "1000 10 20 30\n1003 40 50")).y == [10, 20, 30, 40, 50]


def test_sqz_encodes_the_leading_digit_as_a_letter():
    """"A0" is +10: A is +1, then the remaining digits follow."""
    assert parse(_doc(3, "1000 A0 B0 C0")).y == [10, 20, 30]


def test_dif_values_are_differences_from_the_previous_point():
    """"J0" is +10 relative to what came before, not the value 10."""
    assert parse(_doc(4, "1000 A0 J0 J0\n1003 C0 J0")).y == [10, 20, 30, 40]


def test_dif_handles_negative_differences():
    """Lowercase is the negative branch: "j5" is -15."""
    assert parse(_doc(3, "1000 C0 j5 j5")).y == [30, 15, 0]


def test_dup_repeats_the_previous_value():
    """"U" is a count of 3, meaning the value appears three times total."""
    assert parse(_doc(3, "1000 A0 U")).y == [10, 10, 10]


# --- The Y-value check, in both directions ------------------------------


def test_a_line_after_a_dif_run_opens_with_a_dropped_checkpoint():
    """After differences, the next line repeats the previous line's last Y
    as an absolute check. It is a checkpoint, not a data point -- keeping
    it would add one point per line and shift every X after it."""
    spectrum = parse(_doc(4, "1000 A0 J0 J0\n1003 C0 J0"))
    assert spectrum.y == [10, 20, 30, 40]
    assert spectrum.point_count == 4


def test_a_line_after_plain_values_opens_with_real_data():
    """THE MIRROR CASE, and the first version of this reader got it wrong.
    Applying the Y-value check unconditionally rejected every valid PAC
    file, because there the opening value is simply the next point and has
    no reason to match anything."""
    assert parse(_doc(5, "1000 10 20 30\n1003 40 50")).y == [10, 20, 30, 40, 50]


def test_a_failed_y_value_check_is_reported_not_absorbed():
    """A spectrum wrong by one point per line still looks entirely
    plausible, which is why this refuses rather than repairing."""
    with pytest.raises(JcampError, match="Y-value check failed"):
        parse(_doc(4, "1000 A0 J0 J0\n1003 F0 J0"))


# --- Headers and reconstruction -----------------------------------------


def test_x_is_rebuilt_from_firstx_and_deltax():
    """The per-line X is a checkpoint in this format, not the data. The
    line below claims 9999, and the reconstruction must ignore it."""
    spectrum = parse(_doc(3, "9999 10 20 30"))
    assert spectrum.x == [1000, 1001, 1002]


def test_yfactor_scales_the_values():
    assert parse(_doc(3, "1000 10 20 30", YFACTOR="0.5")).y == [5, 10, 15]


def test_deltax_is_derived_when_absent():
    doc = _doc(3, "1000 10 20 30", LASTX="1004")
    doc = "\n".join(l for l in doc.splitlines() if not l.startswith("##DELTAX"))
    assert parse(doc).x == [1000, 1002, 1004]


def test_headers_are_exposed():
    spectrum = parse(_doc(3, "1000 10 20 30"))
    assert spectrum.title == "test spectrum"
    assert spectrum.x_units == "1/CM"
    assert spectrum.y_units == "TRANSMITTANCE"
    assert spectrum.x_range() == (1000, 1002)


# --- Refusals -----------------------------------------------------------


def test_a_point_count_mismatch_is_refused():
    """Rather than plotting a spectrum that is the wrong length."""
    with pytest.raises(JcampError, match="NPOINTS"):
        parse(_doc(99, "1000 10 20 30"))


def test_a_peak_table_is_refused_by_name_not_misread():
    """`(XY..XY)` is a different shape. Reading it as `(X++(Y..Y))` would
    treat every X as a Y."""
    with pytest.raises(JcampError, match="Unsupported data form"):
        parse("##TITLE=t\n##PEAKTABLE=(XY..XY)\n1000,10\n##END=")


def test_a_file_with_no_data_block_is_refused():
    with pytest.raises(JcampError, match="No ##XYDATA"):
        parse("##TITLE=t\n##END=")


def test_comments_and_blank_lines_are_ignored():
    doc = _doc(3, "$$ instrument comment\n1000 10 20 30\n")
    assert parse(doc).y == [10, 20, 30]
