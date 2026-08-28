"""Where a powder pattern's peaks fall, and what is deliberately absent.

**THE ACCEPTANCE VALUES ARE ARITHMETIC A READER CAN REDO**, which is the
whole reason the positions half is shippable while the intensity half is
not. For a cubic cell the general reciprocal-metric-tensor expression
must reduce to `a/sqrt(h2+k2+l2)`, and halite's first lines are the ones
every powder-diffraction textbook prints.

**A CUBIC-ONLY CHECK CANNOT TELL THE GENERAL FORMULA FROM THE CLOSED
ONE**, exactly as `Lattice.volume`'s docstring already records for the
cell volume. So the tensor is also checked on a TRICLINIC cell, against
a quantity computed by code that predates it: `1/sqrt(det G*)` must
equal `Lattice.volume`.
"""

from __future__ import annotations

import math

import pytest

from openchem.chem.cif import read_cif
from openchem.chem.powder_xrd import (
    calculate_pattern,
    equivalent_reflections,
    intensity_refusal,
    is_systematically_absent,
)
from openchem.chem.space_groups import resolve
from openchem.domain.crystal import Lattice

#: Halite, a = 5.6402 A, Fm-3m. The acceptance case: a rock-salt pattern
#: is the one every text prints, and its lines are checkable by hand.
HALITE_CIF = """data_halite
_cell_length_a 5.6402
_cell_length_b 5.6402
_cell_length_c 5.6402
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na Na 0.0 0.0 0.0
Cl Cl 0.5 0.5 0.5
"""

#: Cu K-alpha1, as a TEST INPUT rather than a shipped constant. Nothing
#: in the application defaults to it -- see
#: `test_a_pattern_needs_a_wavelength_and_will_not_invent_one`.
CU_KA1 = 1.5406


def _halite():
    return read_cif(HALITE_CIF)


# --- the lattice geometry ---------------------------------------------------


@pytest.mark.parametrize("hkl", [(1, 1, 1), (2, 0, 0), (2, 2, 0), (3, 1, 1), (4, 2, 0)])
def test_the_general_tensor_reduces_to_the_cubic_closed_form(hkl):
    """One expression for all seven systems, checked against the one a
    textbook prints for the system where both apply."""
    lattice = Lattice(5.6402, 5.6402, 5.6402)
    n = sum(index * index for index in hkl)
    assert lattice.d_spacing(*hkl) == pytest.approx(
        lattice.a / math.sqrt(n), abs=1e-9
    )


def test_the_reciprocal_tensor_reproduces_the_volume_on_a_TRICLINIC_cell():
    """The check a cubic case cannot make.

    `V = 1/sqrt(det G*)` is a different computation from
    `Lattice.volume`'s closed form, and on an orthogonal cell both
    degenerate into a product of the edges -- so only a cell with three
    non-90 angles discriminates. `Lattice.volume` predates this work and
    carries its own test, which is what makes it an independent oracle
    rather than a circular one.
    """
    lattice = Lattice(7.0, 9.0, 11.0, 80.0, 95.0, 105.0)
    star = lattice.reciprocal_metric_tensor
    determinant = (
        star[0][0] * (star[1][1] * star[2][2] - star[1][2] * star[2][1])
        - star[0][1] * (star[1][0] * star[2][2] - star[1][2] * star[2][0])
        + star[0][2] * (star[1][0] * star[2][1] - star[1][1] * star[2][0])
    )
    assert 1.0 / math.sqrt(determinant) == pytest.approx(lattice.volume, rel=1e-12)
    # The setup assertion: without it this passes vacuously on a cell
    # where the general and closed forms happen to agree anyway.
    assert not lattice.is_orthogonal


def test_the_metric_tensor_is_symmetric_and_its_diagonal_is_the_squared_edges():
    lattice = Lattice(7.0, 9.0, 11.0, 80.0, 95.0, 105.0)
    g = lattice.metric_tensor
    for i in range(3):
        for j in range(3):
            assert g[i][j] == pytest.approx(g[j][i], rel=1e-12)
    assert (g[0][0], g[1][1], g[2][2]) == pytest.approx((49.0, 81.0, 121.0), rel=1e-12)


def test_the_zero_reflection_raises_rather_than_returning_infinity():
    """An infinite d propagates into a Bragg angle as a silent NaN."""
    with pytest.raises(ValueError, match="000"):
        Lattice(5.0, 5.0, 5.0).d_spacing(0, 0, 0)


# --- symmetry ---------------------------------------------------------------


@pytest.mark.parametrize(
    "hkl,allowed",
    [
        ((1, 1, 1), True),
        ((2, 0, 0), True),
        ((2, 2, 0), True),
        ((3, 1, 1), True),
        ((1, 0, 0), False),
        ((1, 1, 0), False),
        ((2, 1, 0), False),
        ((2, 2, 1), False),
    ],
)
def test_absences_derived_from_the_operations_reproduce_the_F_centring_rule(hkl, allowed):
    """An F-centred lattice reflects only when h, k and l share a parity.

    **THAT RULE IS NOWHERE IN THE SOURCE.** It falls out of one general
    statement -- a reflection invariant under an operation's rotation
    must also be unmoved by its translation -- applied to the 192
    operations the space-group table supplies. A hand-kept table of
    conditions per space group would be the `inapplicable_calculators`
    rot waiting to happen, 230 rows deep.
    """
    operations = resolve("F m -3 m", Lattice(5.6402, 5.6402, 5.6402)).symmetry_operations()
    assert is_systematically_absent(operations, hkl) is not allowed


def test_the_absence_rule_is_exercised_against_a_centred_group():
    """The setup assertion for the parametrised case above.

    A primitive group forbids nothing by centring, so every case would
    read "allowed" and the parametrisation would prove nothing about the
    rule. This asserts the fixture really is the centred one: 192
    operations, four times the 48 of the primitive group of the same
    point symmetry.
    """
    cubic = Lattice(5.6402, 5.6402, 5.6402)
    centred = resolve("F m -3 m", cubic).symmetry_operations()
    primitive = resolve("P m -3 m", cubic).symmetry_operations()
    assert len(centred) == 192
    assert len(primitive) == 48
    assert not is_systematically_absent(primitive, (1, 0, 0))
    assert is_systematically_absent(centred, (1, 0, 0))


@pytest.mark.parametrize(
    "hkl,multiplicity",
    [((1, 1, 1), 8), ((2, 0, 0), 6), ((2, 2, 0), 12), ((3, 1, 1), 24), ((3, 2, 1), 48)],
)
def test_cubic_multiplicities_are_the_textbook_ones(hkl, multiplicity):
    operations = resolve("F m -3 m", Lattice(5.6402, 5.6402, 5.6402)).symmetry_operations()
    assert len(equivalent_reflections(operations, hkl)) == multiplicity


def test_a_friedel_pair_is_ONE_powder_line_even_without_a_centre_of_symmetry():
    """A fact about POWDER, not about the point group.

    (hkl) and (-h-k-l) have the same d-spacing in every crystal system,
    so they arrive at one Bragg angle and superimpose -- including in a
    non-centrosymmetric group, where they are distinct reflections with
    distinct structure factors. P1 is the sharpest case: it has ONE
    operation, so any pairing at all must come from the Friedel term.
    """
    triclinic = Lattice(7.0, 9.0, 11.0, 80.0, 95.0, 105.0)
    p1 = resolve("P 1", triclinic).symmetry_operations()
    assert len(p1) == 1
    family = equivalent_reflections(p1, (1, 2, 3))
    assert family == frozenset({(1, 2, 3), (-1, -2, -3)})


# --- the pattern ------------------------------------------------------------


def test_halite_gives_the_powder_lines_a_textbook_prints():
    """The acceptance case, and every number here is `a/sqrt(N)` and Bragg.

    NOTE the plan this branch was written from quotes d(111) = 3.258 for
    a = 5.64; the arithmetic gives 3.2563, and 3.258 would need
    a = 5.6431. The computed value is used and the plan's is not.
    """
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=90.0)
    got = [(r.hkl, round(r.d_spacing, 4), round(r.two_theta, 2)) for r in pattern.reflections[:6]]
    assert got == [
        ((1, 1, 1), 3.2564, 27.37),
        ((2, 0, 0), 2.8201, 31.70),
        ((2, 2, 0), 1.9941, 45.45),
        ((3, 1, 1), 1.7006, 53.87),
        ((2, 2, 2), 1.6282, 56.47),
        ((4, 0, 0), 1.4101, 66.23),
    ]


def test_every_listed_halite_reflection_obeys_the_F_centring_parity_rule():
    """No forbidden line reaches the output.

    Asserted over the WHOLE pattern rather than the first few, because a
    truncated check is exactly how a forbidden reflection at high angle
    would survive.
    """
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    assert pattern.reflection_count > 6
    for reflection in pattern.reflections:
        parities = {index % 2 for index in reflection.hkl}
        assert len(parities) == 1, f"{reflection.label} is F-forbidden"


def test_reflections_come_back_ordered_by_angle():
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    angles = [r.two_theta for r in pattern.reflections]
    assert angles == sorted(angles)


def test_bragg_holds_for_every_reflection():
    """lambda = 2 d sin(theta), checked rather than assumed."""
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    for r in pattern.reflections:
        theta = math.radians(r.two_theta / 2.0)
        assert 2.0 * r.d_spacing * math.sin(theta) == pytest.approx(CU_KA1, rel=1e-9)


def test_nothing_is_reported_beyond_the_requested_angle():
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=60.0)
    assert pattern.reflections
    assert all(r.two_theta <= 60.0 + 1e-9 for r in pattern.reflections)


def test_a_wider_range_is_a_superset_of_a_narrower_one():
    """The enumeration bound is DERIVED from the range, so a wrong bound
    would drop reflections the wider run finds -- which a single run
    cannot detect."""
    narrow = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=60.0)
    wide = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    assert {r.hkl for r in narrow.reflections} <= {r.hkl for r in wide.reflections}
    assert wide.reflection_count > narrow.reflection_count


# --- the wavelength ---------------------------------------------------------


def test_a_pattern_needs_a_wavelength_and_will_not_invent_one():
    """**NOTHING DEFAULTS TO A LABORATORY TUBE.**

    A wavelength is a property of the experiment; no property of a
    structure supplies it, and the whole angle axis scales with it. This
    is the loading-density discipline from `domain/formulation.py`
    applied one module along: supplied, or refused.
    """
    crystal = _halite()
    assert crystal.radiation_wavelength is None
    with pytest.raises(ValueError, match="wavelength"):
        calculate_pattern(crystal)


def test_the_cifs_own_wavelength_is_used_when_it_states_one():
    """Store-the-inputs: the file's own experiment, not a constant."""
    text = HALITE_CIF.replace(
        "_cell_length_a 5.6402", "_diffrn_radiation_wavelength 0.71073\n_cell_length_a 5.6402"
    )
    crystal = read_cif(text)
    assert crystal.radiation_wavelength == pytest.approx(0.71073)
    assert calculate_pattern(crystal).wavelength == pytest.approx(0.71073)


def test_an_explicit_wavelength_overrides_the_files():
    text = HALITE_CIF.replace(
        "_cell_length_a 5.6402", "_diffrn_radiation_wavelength 0.71073\n_cell_length_a 5.6402"
    )
    pattern = calculate_pattern(read_cif(text), wavelength=CU_KA1)
    assert pattern.wavelength == pytest.approx(CU_KA1)


def test_the_wavelength_tag_stops_being_reported_as_unhandled():
    """`unhandled` is the honest record of what the reader IGNORES, so a
    tag that is now READ has to leave it or the record is wrong."""
    text = HALITE_CIF.replace(
        "_cell_length_a 5.6402", "_diffrn_radiation_wavelength 0.71073\n_cell_length_a 5.6402"
    )
    assert "_diffrn_radiation_wavelength" not in read_cif(text).unhandled


# --- what is deliberately absent --------------------------------------------


def test_the_pattern_carries_no_intensity_at_all():
    """The refusal is structural, not a column of zeros.

    A zero intensity would read as "this reflection is extinguished",
    which is a claim about the structure. Absent is the honest shape.
    """
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1)
    reflection = pattern.reflections[0]
    for forbidden in ("intensity", "i_rel", "relative_intensity", "structure_factor"):
        assert not hasattr(reflection, forbidden)


def test_every_pattern_says_why_it_has_no_intensities():
    pattern = calculate_pattern(_halite(), wavelength=CU_KA1)
    assert pattern.intensity_refusal == intensity_refusal()
    assert "Waasmaier" in pattern.intensity_refusal
    assert pattern.intensity_refusal in pattern.limitations


def test_the_limitations_name_the_idealisations_rather_than_implying_them():
    """Kinematic, no preferred orientation, no broadening, no peak shape.

    Asserted because "structure factor" reasonably reads as the full
    wavelength-dependent treatment, and a reader must not have to infer
    that extinction and anomalous dispersion are out of scope.
    """
    joined = " ".join(calculate_pattern(_halite(), wavelength=CU_KA1).limitations).lower()
    for claim in ("kinematic", "preferred orientation", "broadening", "peak shape"):
        assert claim in joined


def test_a_systematic_absence_is_not_described_as_an_experimental_absence():
    joined = " ".join(calculate_pattern(_halite(), wavelength=CU_KA1).limitations).lower()
    assert "statement about the space group" in joined


# --- the cap ----------------------------------------------------------------


def test_a_truncated_pattern_says_how_many_it_dropped():
    """**Never a silent cap.** A list of the first 40 that does not say so
    reads as the whole pattern -- and a large organic cell with Mo
    radiation genuinely holds tens of thousands out to 60 degrees."""
    full = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    capped = calculate_pattern(
        _halite(), wavelength=CU_KA1, max_two_theta=140.0, max_reflections=3
    )
    assert capped.reflection_count == 3
    assert capped.total_reflections == full.reflection_count
    assert capped.truncated_by == full.reflection_count - 3
    assert full.truncated_by == 0


def test_the_cap_keeps_the_LOWEST_angle_reflections():
    """The only honest ordering available without intensities."""
    full = calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=140.0)
    capped = calculate_pattern(
        _halite(), wavelength=CU_KA1, max_two_theta=140.0, max_reflections=3
    )
    assert [r.hkl for r in capped.reflections] == [r.hkl for r in full.reflections[:3]]


# --- refusals ---------------------------------------------------------------


@pytest.mark.parametrize("angle", [0.0, -5.0, 180.0, 200.0])
def test_an_impossible_angle_range_is_refused(angle):
    with pytest.raises(ValueError, match="max_two_theta"):
        calculate_pattern(_halite(), wavelength=CU_KA1, max_two_theta=angle)


def test_a_wavelength_too_long_to_diffract_gives_no_reflections_rather_than_raising():
    """d >= lambda/2 is required by Bragg, so a long enough wavelength
    genuinely has no accessible reflections. That is a RESULT about the
    experiment, not an error -- and it is why the refusal above is
    reserved for a wavelength that was never supplied."""
    pattern = calculate_pattern(_halite(), wavelength=20.0, max_two_theta=90.0)
    assert pattern.reflection_count == 0
    assert pattern.intensity_refusal


def test_it_runs_on_every_shipped_cif_fixture():
    """Six real depositions, all triclinic-to-monoclinic organics with
    their own stated wavelength -- the case the cubic acceptance test
    cannot cover."""
    import pathlib

    fixtures = sorted(pathlib.Path(__file__).parent.joinpath("fixtures/cif").glob("*.cif"))
    assert len(fixtures) >= 6
    for path in fixtures:
        crystal = read_cif(path.read_text(encoding="utf-8", errors="replace"))
        pattern = calculate_pattern(crystal, max_two_theta=30.0, max_reflections=20)
        assert pattern.wavelength == pytest.approx(crystal.radiation_wavelength)
        assert pattern.reflection_count > 0
        angles = [r.two_theta for r in pattern.reflections]
        assert angles == sorted(angles)


# --- reaching the user ------------------------------------------------------


def _report():
    from openchem.chem.crystal_report import build_crystal_report

    text = HALITE_CIF.replace(
        "_cell_length_a 5.6402",
        "_diffrn_radiation_wavelength 1.54056\n_cell_length_a 5.6402",
    )
    return build_crystal_report(read_cif(text))


def test_the_crystal_report_carries_the_powder_pattern():
    """**SHIPPED IS NOT REACHABLE**, and this branch is written after a
    session where a correct, sourced, tested report builder turned out to
    be called by nothing but its own test file. The pattern reaches a
    user through `build_crystal_report`, which a CIF import opens, so
    that is what this asserts."""
    labels = [f.label.strip() for f in _report().facts]
    assert "Powder pattern" in labels
    assert any(label.startswith("(") for label in labels)


def test_the_report_summary_is_STANDARD_so_the_depth_filter_cannot_hide_it():
    """Found by driving the app: with the summary marked ADVANCED too,
    the whole pattern vanished behind "16 advanced hidden" and nothing on
    screen said a powder pattern had been computed."""
    from openchem.domain.report import Detail

    summary = next(f for f in _report().facts if f.label.strip() == "Powder pattern")
    assert summary.detail is Detail.STANDARD


def test_the_individual_lines_stay_ADVANCED_so_they_do_not_bury_the_cell():
    """The narrow half. "Make it all STANDARD" satisfies the guard above
    and pushes the cell, the density and the coordination shells below
    twelve reflection rows."""
    from openchem.domain.report import Detail

    lines = [f for f in _report().facts if f.label.strip().startswith("(")]
    assert lines
    assert all(f.detail is Detail.ADVANCED for f in lines)


def test_every_reported_line_carries_the_intensity_refusal():
    """A reader looking at one row must not have to find the summary to
    learn that no height is claimed."""
    lines = [f for f in _report().facts if f.label.strip().startswith("(")]
    assert lines
    for fact in lines:
        assert any("Waasmaier" in note for note in fact.limitations)


def test_a_structure_with_no_wavelength_says_so_rather_than_going_quiet():
    """**A SILENTLY ABSENT SECTION READS AS "THIS STRUCTURE HAS NO
    PATTERN".** `calculate_pattern` refuses without a wavelength, and the
    report has to turn that refusal into a visible row."""
    from openchem.chem.crystal_report import build_crystal_report

    crystal = read_cif(HALITE_CIF)
    assert crystal.radiation_wavelength is None
    summary = next(
        f for f in build_crystal_report(crystal).facts
        if f.label.strip() == "Powder pattern"
    )
    assert "not calculated" in summary.display_value
    assert "wavelength" in summary.display_value


def test_the_report_says_how_many_lines_it_did_not_list():
    """**HALITE CANNOT TEST THIS, and reaching for it first was the
    mistake.** At Cu wavelength out to 60 degrees a rock-salt cell has
    five reflections, comfortably under the report's cap of twelve, so
    nothing is ever truncated and the assertion passed against no
    behaviour at all. A real deposition with Mo radiation has thousands.
    """
    import pathlib

    from openchem.chem.crystal_report import build_crystal_report

    path = pathlib.Path(__file__).parent / "fixtures/cif/1569411.cif"
    crystal = read_cif(path.read_text(encoding="utf-8", errors="replace"))
    facts = build_crystal_report(crystal).facts
    summary = next(f for f in facts if f.label.strip() == "Powder pattern")
    listed = [f for f in facts if f.label.strip().startswith("(")]
    # The setup assertion: this fixture must really overflow the cap, or
    # the claim below is about nothing.
    assert summary.value > len(listed)
    assert "not listed" in summary.display_value


def test_a_negative_index_is_written_so_it_reads_as_one_index():
    """`(1 0 -2)`, not three numbers that could be read as a triple with a
    stray minus. Checked because the label is what a screenshot shows."""
    from openchem.chem.powder_xrd import PowderReflection

    reflection = PowderReflection(
        h=1, k=0, l=-2, d_spacing=5.0, two_theta=10.0, multiplicity=2
    )
    assert reflection.label == "(1 0 -2)"
