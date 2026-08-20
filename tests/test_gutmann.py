"""Gutmann DN and AN, against the values the 1976 tables print.

**THE ORACLE IS THE PUBLISHED VALUES, NOT AGREEMENT WITH DRAGO.** An
earlier draft of the plan for this work proposed checking that these
donicities and the shipped Drago E/C parameters "agree where they
overlap", because DN is defined as -dH against SbCl5 and E/C predicts
-dH for acid-base pairs. That is too strong: they are distinct scales
with distinct parameterisations and experimental bases, so making
cross-scale numerical agreement a CORRECTNESS criterion would let a real
transcription error hide behind a legitimate difference -- or the
reverse.

**DN AND AN GET SEPARATE FIXTURES**, not one combined "Gutmann numbers"
test. Their sources differ in quality here: DN comes from a table whose
render reads cleanly, AN from a page of the same scanned journal, and a
combined test would hide which half failed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.chem import gutmann


def _payload() -> dict:
    return json.loads(
        (Path(gutmann.__file__).parent / "data" / "gutmann_solvents.json").read_text(
            encoding="utf-8"
        )
    )


# --- donor numbers ----------------------------------------------------------


@pytest.mark.parametrize(
    "solvent,expected",
    [
        ("benzene", 0.1),
        ("nitromethane", 2.7),
        ("acetonitrile", 14.1),
        ("tetrahydrofuran", 20.0),
        ("dimethylformamide", 26.6),
        ("dimethyl sulphoxide", 29.8),
        ("pyridine", 33.1),
        ("hexamethylphosphoramide", 38.8),
        ("triethylamine", 61.0),
    ],
    ids=lambda v: str(v),
)
def test_donor_numbers_are_the_papers_own(solvent, expected):
    """Typed from a 300 dpi render of Table 1, spanning the whole range.

    The span matters: a systematic error in reading a column shows at the
    ends, not in the middle.
    """
    record = gutmann.donicity(solvent)
    assert record is not None, f"{solvent} is not in the table"
    assert record.donor_number == pytest.approx(expected, abs=1e-9)


def test_t_butylamines_value_is_the_one_the_page_shows_not_the_ocr():
    """THE TRANSCRIPTION ERROR THIS METHOD ALREADY CAUGHT.

    The PDF's text layer reports 57.6. The rendered page says 57.5. It is
    a 0.1 difference in one row of 53 -- exactly the size the Drago audit
    found (one value in 53, out by 0.01) and exactly what no averaged
    validation could ever see.
    """
    assert gutmann.donicity("t-butylamine").bulk_donicity == pytest.approx(57.5)


def test_the_measurement_medium_carries_no_donicity_of_its_own():
    """1,2-dichloroethane is listed WITH NO VALUE, and that is the point.

    DN is measured in dilute 1,2-dichloroethane, so the medium cannot
    have one on its own scale. It is present in the table rather than
    omitted so the absence reads as a reason rather than as an oversight.
    """
    record = gutmann.donicity("1,2-dichloroethane")
    assert record is not None
    assert record.donor_number is None
    assert "measured in" in record.note


# --- bulk donicity is a different measurement -------------------------------


def test_bulk_donicity_is_never_returned_as_a_donor_number():
    """The paper's footnote a is a DIFFERENT quantity: "the donicity of
    the solvent in the associated liquid".

    Seven rows carry only that. Serving one as `donor_number` would put
    two measurements in one column -- the failure this project has now
    found three times: `HLB` meaning Griffin or Davies, "steric index"
    meaning any of four things, and now donicity meaning dilute or bulk.
    """
    bulk_only = ["hydrazine", "ethylenediamine", "ethylamine", "isopropylamine",
                 "t-butylamine", "ammonia"]
    for name in bulk_only:
        record = gutmann.donicity(name)
        assert record.donor_number is None, f"{name} served a bulk value as a DN"
        assert record.bulk_donicity is not None


def test_water_carries_both_and_they_differ_by_fifteen():
    """THE ROW THAT PROVES THE DISTINCTION IS NOT PEDANTRY.

    Water is reported both ways -- `18.0 (33.0 a)` -- and the two differ
    by 15 kcal/mol. Any implementation that merged the columns would be
    wrong here by more than the entire range from benzene to acetonitrile.
    """
    water = gutmann.donicity("water")
    assert water.donor_number == pytest.approx(18.0)
    assert water.bulk_donicity == pytest.approx(33.0)
    assert abs(water.bulk_donicity - water.donor_number) == pytest.approx(15.0)


def test_an_approximate_value_says_so():
    """The paper writes "~24" for dimethoxyethane, not 24."""
    dme = gutmann.donicity("dimethoxyethane")
    assert dme.donor_number == pytest.approx(24.0)
    assert dme.approximate is True
    assert gutmann.donicity("pyridine").approximate is False


# --- acceptor numbers -------------------------------------------------------


@pytest.mark.parametrize(
    "solvent,expected",
    [
        ("hexane", 0.0),
        ("tetrahydrofuran", 8.0),
        ("acetone", 12.5),
        ("dimethyl sulphoxide", 19.3),
        ("chloroform", 23.1),
        ("methanol", 41.3),
        ("water", 54.8),
        ("trifluoroacetic acid", 105.3),
        ("methanesulphonic acid", 126.3),
    ],
    ids=lambda v: str(v),
)
def test_acceptor_numbers_are_the_papers_own(solvent, expected):
    record = gutmann.donicity(solvent)
    assert record is not None, f"{solvent} is not in the table"
    assert record.acceptor_number == pytest.approx(expected, abs=1e-9)


def test_the_acceptor_scale_keeps_both_of_its_anchors():
    """AN IS A POSITION, NOT A MEASUREMENT IN ITS OWN UNITS.

    It is defined by two points -- hexane = 0 and SbCl5 in
    dichloroethane = 100 -- so a transcription slip in either would
    silently rescale the entire column while every individual value still
    looked plausible.
    """
    anchors = gutmann.scale_anchors()
    assert anchors["hexane"] == 0.0
    assert anchors["antimony pentachloride in dichloroethane"] == 100.0


def test_the_two_scales_are_not_a_single_ordering():
    """A solvent can be a strong donor and a weak acceptor.

    HMPA has the second-highest donicity in the table and an acceptor
    number near diethyl ether's. Asserting it is what stops a later
    "solvent polarity" convenience collapsing the two into one number.
    """
    hmpa = gutmann.donicity("hexamethylphosphoramide")
    water = gutmann.donicity("water")
    assert hmpa.donor_number > water.donor_number
    assert hmpa.acceptor_number < water.acceptor_number


# --- the table as shipped ---------------------------------------------------


def test_the_table_declares_its_source_and_its_definitions():
    payload = _payload()
    assert payload["_source_key"] == "gutmann1976"
    assert "mayer1975" in payload["_supplementary_source_keys"]
    # The definitions are shipped BESIDE the numbers because "donicity"
    # alone does not say dilute-or-bulk, and "acceptor number" alone does
    # not say what the scale is anchored on.
    for key in ("dn", "bulk_dn", "an", "p31_shift"):
        assert payload["definitions"][key].strip()


def test_every_recorded_solvent_carries_at_least_one_number():
    """A row with nothing on it would be a transcription that lost its
    value while keeping its name -- which reads as a gap in the source
    rather than as a mistake here.

    1,2-dichloroethane is the ONE deliberate exception and says why.
    """
    empty = [
        name
        for name, record in ((n, gutmann.donicity(n)) for n in gutmann.solvent_names())
        if record.donor_number is None
        and record.bulk_donicity is None
        and record.acceptor_number is None
    ]
    assert empty == ["1,2-dichloroethane"], empty
