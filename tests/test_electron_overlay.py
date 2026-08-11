"""The chemistry the canvas overlay is given, and the rules it is judged by.

Two halves that never meet in production: `chem/electron_overlay.py`
answers *how many pairs*, and `chem/electron_layout.py` judges *where the
page drew them*. Placement itself is in the JS, because only the page
knows the viewport — so this file tests the question and the judge, and
`tests/test_electron_overlay_canvas.py` runs the judge over what the JS
really produced.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem

from openchem.chem.electron_layout import (
    LABEL_PADDING_FRACTION,
    MIN_BOND_CLEARANCE_DEGREES,
    MIN_SLOT_SEPARATION_DEGREES,
    Box,
    pair_bearings,
    slot_candidates,
    violations,
)
from openchem.chem.electron_overlay import (
    NO_PAIRS_MESSAGE,
    UNAVAILABLE_PREFIX,
    ElectronOverlay,
    build,
)

BOND = 40.0
CENTRE = (100.0, 100.0)


def _pair_at(bearing_degrees: float, radius: float = 0.33 * BOND, gap: float = 0.055 * BOND):
    """Two dots straddling a slot, the way the renderer draws one pair."""
    radians = math.radians(bearing_degrees)
    cx = CENTRE[0] + radius * math.cos(radians)
    cy = CENTRE[1] + radius * math.sin(radians)
    px, py = -math.sin(radians) * gap, math.cos(radians) * gap
    return [(cx + px, cy + py), (cx - px, cy - py)]


# --- the payload: three states, never two ------------------------------------


def test_a_carbonyl_oxygen_carries_two_pairs():
    overlay = build(Chem.MolFromSmiles("CC=O"))

    oxygen = next(a.GetIdx() for a in Chem.MolFromSmiles("CC=O").GetAtoms() if a.GetSymbol() == "O")
    assert overlay.refused is False
    assert overlay.counts[oxygen] == 2
    assert overlay.any_pairs
    assert overlay.status_message() == "", "dots are on screen; prose would be noise"


def test_zero_pairs_is_carried_EXPLICITLY_and_is_an_answer():
    """**The distinction the whole module exists for.** An ammonium
    nitrogen has no lone pair, and that is a fact about it. Leaving it out
    of `counts` would make it indistinguishable from an atom the analysis
    could not speak for."""
    mol = Chem.MolFromSmiles("C[NH3+]")
    nitrogen = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N")

    overlay = build(mol)

    assert nitrogen in overlay.counts, "the nitrogen is missing, so 'none' reads as 'unknown'"
    assert overlay.counts[nitrogen] == 0
    assert not overlay.refused
    assert not overlay.any_pairs
    assert overlay.status_message() == NO_PAIRS_MESSAGE


def test_an_unpaired_electron_refuses_the_whole_molecule_with_a_reason():
    """A singlet carbene has a donor pair; the triplet has two lone
    electrons. The drawing does not say which, so nothing is drawn AND
    something is said."""
    overlay = build(Chem.MolFromSmiles("[CH2]"))

    assert overlay.refused
    assert overlay.counts == {}
    assert overlay.status_message().startswith(UNAVAILABLE_PREFIX)
    assert "unpaired" in overlay.status_message().lower(), overlay.status_message()


def test_a_metal_is_absent_from_the_counts_rather_than_reported_as_zero():
    """Iron(III) is d5 with five UNPAIRED electrons. "Two lone pairs" and
    "zero lone pairs" are both fabrications; absence is the honest
    answer, and the contract says absence means "no definite answer"."""
    mol = Chem.MolFromSmiles("[Fe+3]")

    overlay = build(mol)

    assert not overlay.refused
    assert overlay.counts == {}
    assert overlay.undetermined == (0,)


def test_an_ALL_UNDETERMINED_structure_does_not_claim_it_has_no_pairs():
    """**FOUND BY LOOKING AT IT, and the guard had encoded the bug.**

    Driving the app on iron(III): no dots, not refused, and the status bar
    said "No lone pairs." -- the one claim `lone_pairs` had declined to
    make. There were three named states and four real situations, and the
    fourth borrowed the wrong message. The earlier version of the test
    above asserted `NO_PAIRS_MESSAGE` as EXPECTED, so it could never have
    caught it.
    """
    overlay = build(Chem.MolFromSmiles("[Fe+3]"))

    message = overlay.status_message()

    assert message.startswith(UNAVAILABLE_PREFIX), message
    assert NO_PAIRS_MESSAGE not in message
    assert "metal" in message


def test_a_mixture_says_how_much_it_could_not_speak_for():
    """Sodium methoxide: the oxygen and carbon have definite counts, the
    sodium does not. "No lone pairs" would be wrong and "unavailable"
    would be too, so it says both halves."""
    overlay = build(Chem.MolFromSmiles("C[NH3+].[Na+]"))

    assert overlay.undetermined, overlay
    assert not overlay.any_pairs
    message = overlay.status_message()
    assert "cannot" in message and "1" in message, message


def test_the_status_message_is_one_sentence_not_a_paragraph():
    """`analyse`'s reasons run to several lines, which a status bar
    cannot show. The full text stays in the Atom Inspector, where
    somebody asking "why" is already looking."""
    overlay = build(Chem.MolFromSmiles("[CH2]"))

    message = overlay.status_message()
    assert len(message) < 160, message
    assert "\n" not in message


def test_the_payload_keys_positions_as_STRINGS_because_json_will():
    """Written as strings here rather than discovered to be strings on
    the far side, where the page would be indexing by an integer that
    never matches."""
    overlay = build(Chem.MolFromSmiles("CC=O"))

    payload = overlay.to_payload()

    assert all(isinstance(key, str) for key in payload["counts"])
    assert payload["refused"] is False


# --- the checker: the rules, independently of any placement ------------------


def test_a_sound_placement_has_no_violations():
    dots = _pair_at(90.0) + _pair_at(180.0)

    assert violations(dots, CENTRE, [0.0], None, BOND, expected_pairs=2) == []


def test_a_pair_lying_along_a_bond_is_a_violation():
    """A pair drawn down a bond reads as a decoration on that bond."""
    dots = _pair_at(5.0)

    breaches = violations(dots, CENTRE, [0.0], None, BOND, expected_pairs=1)

    assert len(breaches) == 1
    assert "from a bond" in breaches[0]


def test_two_pairs_too_close_together_are_a_violation():
    dots = _pair_at(90.0) + _pair_at(110.0)

    breaches = violations(dots, CENTRE, [], None, BOND, expected_pairs=2)

    assert any("apart" in breach for breach in breaches), breaches


def test_a_dot_inside_the_label_box_is_a_violation():
    """Water, ammonia and methanol are the real cases: the label is
    exactly where naive placement puts the pair."""
    dots = _pair_at(0.0)
    box = Box(CENTRE[0] - 2, CENTRE[1] - 8, CENTRE[0] + 30, CENTRE[1] + 8)

    breaches = violations(dots, CENTRE, [], box, BOND, expected_pairs=1)

    assert any("label box" in breach for breach in breaches), breaches


def test_the_label_box_is_PADDED_so_a_dot_that_grazes_it_still_fails():
    """A dot touching the glyphs is as unreadable as one on top of them.

    **The padding is a FRACTION OF BOND LENGTH, not a pixel count**, and
    that was a bug for one commit: the checker works in whatever units the
    caller uses, so the page -- which works in model units, because that
    is what makes pan and zoom free -- padded every box by two BOND
    LENGTHS and every placement came back invalid. A unit belongs in the
    caller or in none of it.
    """
    padding = LABEL_PADDING_FRACTION * BOND
    box = Box(CENTRE[0] - 2, CENTRE[1] - 8, CENTRE[0] + 10, CENTRE[1] + 8)
    grazing = [(CENTRE[0] + 10 + padding / 2, CENTRE[1]), (CENTRE[0] + 12, CENTRE[1])]

    breaches = violations(grazing, CENTRE, [], box, BOND, expected_pairs=1)

    assert any("label box" in breach for breach in breaches), breaches
    assert padding == pytest.approx(2.0), "40 px bond, 2 px of padding"


def test_dots_too_far_from_the_atom_are_a_violation():
    """Out past half a bond length they read as belonging to the bond, or
    to the next atom along."""
    dots = _pair_at(90.0, radius=0.9 * BOND)

    breaches = violations(dots, CENTRE, [], None, BOND, expected_pairs=1)

    assert any("bond lengths" in breach for breach in breaches), breaches


def test_the_wrong_NUMBER_of_dots_is_caught_first_and_alone():
    """Reported on its own: every other rule reads dots in pairs, so a
    stray dot would otherwise produce a cascade of confusing breaches
    about a pair that does not exist."""
    breaches = violations(_pair_at(90.0)[:1], CENTRE, [], None, BOND, expected_pairs=1)

    assert len(breaches) == 1
    assert "1 dots for 1 pair(s)" in breaches[0]


def test_every_breach_is_reported_not_just_the_first():
    """A wrong placement is usually wrong several ways, and fixing them
    one test run at a time is how a geometry bug takes an afternoon."""
    dots = _pair_at(2.0) + _pair_at(12.0)

    breaches = violations(dots, CENTRE, [0.0], None, BOND, expected_pairs=2)

    assert len(breaches) >= 3, breaches


def test_pair_bearings_reassociate_consecutive_dots():
    """The renderer draws circles, so the pair has to be recovered from
    them -- and getting that wrong would make every angular rule compare
    the wrong things while still returning plausible numbers."""
    dots = _pair_at(90.0) + _pair_at(-90.0)

    bearings = pair_bearings(dots, CENTRE)

    assert bearings[0] == pytest.approx(90.0, abs=0.5)
    assert bearings[1] == pytest.approx(-90.0, abs=0.5)


def test_the_slot_candidates_are_a_fixed_ring():
    """Shared with the JS so the two agree on resolution rather than each
    picking one. A coarse ring is deliberate: it keeps two nearly
    equivalent directions from trading places on a rounding difference."""
    candidates = slot_candidates(10.0)

    assert len(candidates) == 36
    assert candidates[0] == -180.0
    assert all(
        round(b - a, 6) == 10.0 for a, b in zip(candidates, candidates[1:])
    )


def test_the_constants_are_the_ones_the_rules_actually_use():
    """Guards against a constant being edited while a rule keeps a
    hard-coded copy of the old value -- which would leave every test here
    green and the canvas unchanged."""
    just_inside = _pair_at(90.0) + _pair_at(90.0 + MIN_SLOT_SEPARATION_DEGREES - 1)
    just_outside = _pair_at(90.0) + _pair_at(90.0 + MIN_SLOT_SEPARATION_DEGREES + 1)

    assert violations(just_inside, CENTRE, [], None, BOND, 2), "the minimum is not enforced"
    assert violations(just_outside, CENTRE, [], None, BOND, 2) == []

    grazing = _pair_at(MIN_BOND_CLEARANCE_DEGREES - 1)
    clear = _pair_at(MIN_BOND_CLEARANCE_DEGREES + 1)
    assert violations(grazing, CENTRE, [0.0], None, BOND, 1)
    assert violations(clear, CENTRE, [0.0], None, BOND, 1) == []
