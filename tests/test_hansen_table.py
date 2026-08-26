"""The shipped Hansen group table must match Stefanis & Panayiotou's paper.

`[source:stefanis2008]`, Tables 3-6 of *Int J Thermophys* (2008) 29:568-585.

THE ORACLE IS THE PAPER'S OWN ARITHMETIC, not a value recalled from
elsewhere. It works two compounds end to end and prints their group
assignments, their per-group contributions AND their totals:

    1-hexanal   Tables 7-9     W=0, no second-order groups
    alizarin    Tables 11-16   W=1, with a second-order correction

so a transcription error in any row either example touches contradicts a
number the paper printed. That is a stronger check than a spot comparison,
and it is what caught the `Ccyclic=O` / `C(cyclic)=O` spelling split.

**THESE GUARD THE TABLE, NOT A FRAGMENTER.** Nothing here matches a
structure; the SMARTS work lands separately, exactly as Joback's did
(`test_joback_table.py` against `test_joback_fragmenter.py`). Splitting them
is what makes a failure legible: a wrong number here is a transcription
fault, and a wrong number there is a chemistry fault.

`tools/build_hansen_tables.py` regenerates the JSON, needs `pymupdf` and a
local copy of the paper, and so cannot run in CI -- the same admitted limit
`build_ketcher_notices.py` carries. These tests read the committed file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

TABLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "openchem" / "chem" / "data" / "hansen_groups.json"
)


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def _key(name: str) -> str:
    """Mirror of the builder's canonicalisation, for looking a group up.

    Deliberately re-implemented in one line rather than imported: the point is
    that the SHIPPED keys are already canonical, so a test that imported the
    builder would pass even if the JSON had been written with raw names.
    """
    dashes = "-‐‑‒–—−"
    return " ".join(
        "".join("-" if c in dashes else c for c in name).split()
    ).casefold()


def _evaluate(table, first, second, parameter):
    total = table["_constants"][parameter]
    for name, count in first:
        total += count * table["first_order"][_key(name)][parameter]
    for name, count in second or ():
        total += count * table["second_order"][_key(name)][parameter]
    return total


# ---------------------------------------------------------------------------
# The paper's two worked examples
# ---------------------------------------------------------------------------

HEXANAL = [("-CH3", 1), ("-CH2", 4), ("CHO (aldehydes)", 1)]

#: Alizarin's `>C=O` is printed `>C=0` -- a DIGIT ZERO -- in Table 3. The
#: builder corrects it and records the change, so this looks it up by the
#: corrected name, which is what any consumer will use.
ALIZARIN = [("ACH", 6), ("AC", 4), ("ACOH", 2), (">C=O (except as above)", 2)]
ALIZARIN_SECOND = [("Ccyclic=O", 2)]


@pytest.mark.parametrize(
    "parameter,printed",
    [("d", 15.8411), ("p", 7.9654), ("hb", 5.7191)],
)
def test_the_paper_works_1_hexanal_at_w_zero(table, parameter, printed):
    """Tables 7-9, p582. No second-order group applies, so W=0."""
    assert _evaluate(table, HEXANAL, None, parameter) == pytest.approx(
        printed, abs=5e-5
    )


@pytest.mark.parametrize(
    "parameter,printed",
    [("d", 21.5535), ("p", 10.4308), ("hb", 22.9753)],
)
def test_the_paper_works_alizarin_at_w_zero(table, parameter, printed):
    """Tables 11, 13 and 15 -- the first-order half of the alizarin example."""
    assert _evaluate(table, ALIZARIN, None, parameter) == pytest.approx(
        printed, abs=5e-5
    )


def test_the_paper_works_alizarin_at_w_one(table):
    """Table 16 plus the text: delta_hb = 22.02 once the correction applies.

    THE ONLY PRINTED SECOND-ORDER TOTAL IN THE PAPER, which is why this is one
    test rather than three. It is also the only end-to-end check that the
    second-order table is transcribed correctly at all.
    """
    assert _evaluate(table, ALIZARIN, ALIZARIN_SECOND, "hb") == pytest.approx(
        22.02, abs=5e-3
    )


def test_the_second_order_correction_actually_moves_the_answer(table):
    """The setup assertion, without which the test above is about nothing.

    If the second-order contribution were zero -- or the group missing, so a
    consumer skipped it -- W=0 and W=1 would agree and the guard above would
    pass while testing only the first-order table.
    """
    without = _evaluate(table, ALIZARIN, None, "hb")
    with_second = _evaluate(table, ALIZARIN, ALIZARIN_SECOND, "hb")
    assert abs(with_second - without) > 0.9


# ---------------------------------------------------------------------------
# Shape, and the four transcription hazards
# ---------------------------------------------------------------------------

def test_the_table_holds_what_the_paper_prints(table):
    """Row counts, so a walk that slid cannot pass unnoticed.

    Table 6 extracted 0 rows of 11 at one point, because a single unparsed
    cell slides a shape-recognising walk and empties the table rather than
    shortening it.
    """
    assert len(table["first_order"]) == 76
    assert len(table["second_order"]) == 37
    assert len(table["first_order_low"]) == 43
    assert len(table["second_order_low"]) == 11


@pytest.mark.parametrize(
    "section,parameters",
    [
        ("first_order", ("d", "p", "hb")),
        ("second_order", ("d", "p", "hb")),
        ("first_order_low", ("p", "hb")),
        ("second_order_low", ("p", "hb")),
    ],
)
def test_every_contribution_is_a_real_number_or_absent(table, section, parameters):
    for key, row in table[section].items():
        for parameter in parameters:
            value = row[parameter]
            assert value is None or isinstance(value, (int, float)), (
                f"{section}/{key}/{parameter} is {value!r}"
            )
            if isinstance(value, float):
                assert math.isfinite(value), f"{section}/{key}/{parameter}"


def test_absence_is_not_zero(table):
    """`***` is the paper's own marker and its caption defines it.

    "The specific group contributions to this delta parameter are not
    available" -- so a null is ABSENCE. Storing it as 0.0 would make a group
    with no published contribution silently contribute nothing to a sum that
    still returns a number, which is the failure this project keeps recording
    under other names.
    """
    nulls = sum(
        1
        for section in ("first_order", "second_order", "first_order_low", "second_order_low")
        for row in table[section].values()
        for parameter in ("d", "p", "hb")
        if parameter in row and row[parameter] is None
    )
    assert nulls > 20, "the *** marker is not reaching the shipped table"
    assert "never zero" in table["_missing_marker"].casefold()


def test_the_digit_zero_group_name_is_corrected_and_recorded(table):
    """Hazard 1: `>C=0` carries a digit zero where the letter O belongs."""
    row = table["first_order"][_key(">C=O (except as above)")]
    assert "0" in row["printed"], "the paper's own spelling must be kept"
    assert row["corrected"] == ">C=O (except as above)"
    # The control: the paper is not systematically wrong about O.
    assert table["first_order"][_key("O=C=N-")]["printed"].startswith("O")


def test_the_same_group_is_keyed_alike_across_tables(table):
    """Hazard 3, and it is invisible in every rendering.

    Table 3 writes `-CH3` with U+2212 MINUS SIGN and Table 5 writes it with
    U+2013 EN DASH. The two strings look identical and are not equal, so a raw
    lookup makes the low-delta branch find nothing -- and an empty contribution
    set is a number rather than an error.
    """
    key = _key("-CH3")
    assert key in table["first_order"]
    assert key in table["first_order_low"]

    main = table["first_order"][key]["printed"]
    low = table["first_order_low"][key]["printed"]
    assert main != low, (
        "this guard is vacuous unless the two tables really do spell it "
        "differently -- if the paper is ever reprinted consistently, delete it"
    )
    assert ord(main[0]) == 0x2212
    assert ord(low[0]) == 0x2013


def test_the_flattened_scientific_values_parsed(table):
    """Hazard 4: `10-8` is the paper's 10^-8 with its superscript lost.

    Three cells in Table 6 are written that way, one of them `2 10-8`. They do
    not parse as floats, so a pattern that merely fails to match them skips a
    cell and slides the walk.
    """
    tiny = [
        row[parameter]
        for row in table["second_order_low"].values()
        for parameter in ("p", "hb")
        if isinstance(row[parameter], float) and 0 < abs(row[parameter]) < 1e-6
    ]
    assert len(tiny) == 3, f"expected the three 10^-8 cells, got {tiny}"
    assert all(value == pytest.approx(v, abs=1e-12) for value, v in zip(tiny, tiny))


def test_a_bare_zero_survives_the_page_number_filter(table):
    """One Table 6 cell is a bare `0`, and `str.isdigit()` ate it.

    That cost the row entirely -- 10 extracted of 11 -- because a skipped cell
    slides the walk. Page numbers here are three digits; a contribution is one.
    """
    zeroes = [
        key
        for key, row in table["second_order_low"].items()
        if row["p"] == 0 or row["hb"] == 0
    ]
    assert zeroes, "the bare-zero contribution is missing from the table"


# ---------------------------------------------------------------------------
# What the paper says about using it
# ---------------------------------------------------------------------------

def test_the_constants_are_the_papers(table):
    """Eqs. 24-26. The intercept is per parameter and is not a group."""
    assert table["_constants"] == {"d": 17.3231, "p": 7.3548, "hb": 7.9793}


def test_the_total_is_the_pythagorean_combination(table):
    """Eq. 4, READ from the paper rather than recalled.

    And the paper names it `delta_hb`, not `delta_h`.
    """
    assert table["_equations"]["delta_t"] == (
        "sqrt(delta_d**2 + delta_p**2 + delta_hb**2)"
    )
    assert set(table["_units"]) == {"delta_d", "delta_p", "delta_hb", "delta_t"}
    assert set(table["_units"].values()) == {"MPa^0.5"}


def test_the_low_delta_branch_is_declared(table):
    """Eqs. 25 and 26 are valid only above 3 (MPa)^0.5, and 5/6 cover below."""
    low = table["_low_delta"]
    assert low["threshold"] == 3.0
    assert low["applies_to"] == ["p", "hb"]
    assert "delta_d" not in low["applies_to"], (
        "delta_d has no low-range table -- Eq. 24 carries no such caveat"
    )


def test_the_applicability_domain_is_recorded(table):
    """p574: three or more carbons, excluding the characteristic group's atom.

    A refusal condition, not a footnote -- and one the fragmenter will need.
    """
    text = table["_applicability"].casefold()
    assert "three or more carbon" in text
    assert "excluding" in text


def test_the_two_tables_are_not_subsets_of_each_other(table):
    """Recorded from the paper rather than resolved.

    Table 5 lists four first-order groups Table 3 does not, each verified
    against the raw page: ACCH<, CHNH, CCl2F and a bare CHO. So a low-delta
    contribution can exist for a group with no main-table contribution.
    """
    main = set(table["first_order"])
    low = set(table["first_order_low"])
    only_low = {k for k in low - main}
    assert only_low == {_key(n) for n in ("ACCH<", "CCl2F", "CHNH", "CHO")}
    assert set(table["_asymmetries"]["low_first_order_groups_absent_from_table_3"]) == {
        "ACCH<", "CCl2F", "CHNH", "CHO"
    }


def test_the_bare_cho_ambiguity_is_declared_rather_than_guessed(table):
    """Table 3 splits CHO two ways; Table 5 does not.

    Its low-delta_hb value cannot be attributed to aldehydes or to ethers
    without a judgement the paper does not make. The data cannot express the
    distinction, so the consumer must refuse rather than pick -- written down
    here so the next author meets the reason before the choice.
    """
    assert _key("CHO (aldehydes)") in table["first_order"]
    assert _key("CHO (ethers)") in table["first_order"]
    assert _key("CHO") in table["first_order_low"]
    assert _key("CHO") not in table["first_order"]
    # Assert the OPERATIVE instruction, not a descriptive adjective. The first
    # version of this looked for "ambiguous" and failed on prose that says
    # "disambiguates" -- which is grading wording rather than content, and is
    # what `help_tooltip.py`'s no-LLM-grading rule refuses for the same reason.
    note = table["_asymmetries"]["cho_is_ambiguous"].casefold()
    assert "refuse" in note, "the note must say what a consumer should DO"
    assert "invent" in note
