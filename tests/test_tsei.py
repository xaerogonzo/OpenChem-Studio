"""Cao-Liu TSEI, checked against the values the paper prints.

**TWO ORACLES, AND THE EXACT ONE CARRIES THE WEIGHT.** The paper reports
correlations of 0.9912 and 0.9845 against biphenyl dihedral angles, and
those are a fine behavioural check -- but a correlation is a weak
transcription oracle, because plenty of systematically wrong
implementations still correlate strongly. Table 1 prints exact TSEI for
normal alkyls from n = 1 to 20, and Table 6 prints values for the
halogens, the ethers and the branched alkyls.

**THREE FIXTURE FAMILIES, BECAUSE EACH PROVES A DIFFERENT THING.**

    Table 1, n = 1..20     the CONSTANT. Every term collapses to 1/L^3 on
                           an all-carbon path, so this series is blind to
                           the radius term entirely -- it passed against
                           the eq-7 implementation that was wrong off it.
    a first-tier halogen   the RADIUS term. Cl = 1.4190 is derived in full
                           in the paper's own worked example.
    MeO and OEt            the TRAVERSAL. Neither of the above walks a
                           multi-bond path through a heteroatom, which is
                           where `l_i` stops being `L_i x l_CC` -- OEt's
                           third-tier carbon sits at 4.408 rather than
                           4.632, and its hydrogens at 5.480.

The tables below are TYPED FROM THE PAGE. Generating them from either
code path would make this file one implementation reading itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import tsei as tsei_module
from openchem.chem.tsei import (
    TseiRadiusError,
    covalent_radius,
    normal_alkyl_tsei,
    reference_values,
    substituent_atoms,
    substituent_tsei,
)

#: Cao & Liu, Table 1, "TSEI and delta-TSEI Values of Normal Alkyl".
#: Typed from the paper.
_TABLE_1 = {
    1: 1.0000, 2: 1.1250, 3: 1.1620, 4: 1.1777, 5: 1.1857,
    6: 1.1903, 7: 1.1932, 8: 1.1952, 9: 1.1965, 10: 1.1975,
    11: 1.1983, 12: 1.1989, 13: 1.1993, 14: 1.1997, 15: 1.2000,
    16: 1.2002, 17: 1.2004, 18: 1.2006, 19: 1.2007, 20: 1.2009,
}


def _chain(carbons: int) -> Chem.Mol:
    """A reaction centre (atom 0) with a straight chain hung off atom 1."""
    return Chem.MolFromSmiles("C" + "C" * carbons)


# --- the constant: Table 1 --------------------------------------------------


@pytest.mark.parametrize("carbons,expected", sorted(_TABLE_1.items()))
def test_the_closed_form_reproduces_table_1(carbons, expected):
    assert normal_alkyl_tsei(carbons) == pytest.approx(expected, abs=5e-5)


@pytest.mark.parametrize("carbons,expected", sorted(_TABLE_1.items()))
def test_walking_a_real_structure_reproduces_table_1(carbons, expected):
    """The route a caller actually takes, against the same printed values.

    Independent of `normal_alkyl_tsei`: this walks bonds and sums radii,
    that one sums a series. Both are checked against the page rather than
    against each other.
    """
    result = substituent_tsei(_chain(carbons), 0, 1)
    assert result.value == pytest.approx(expected, abs=5e-5)
    assert result.atoms == carbons


def test_the_series_converges_where_the_paper_says_it_does():
    """1.2009 at n = 20, and still 1.2009 far beyond it.

    The convergence is the shape that makes this table a good oracle: an
    implementation with the wrong exponent reproduces neither the early
    values nor the limit.
    """
    assert normal_alkyl_tsei(20) == pytest.approx(1.2009, abs=5e-5)
    assert normal_alkyl_tsei(200) == pytest.approx(1.2021, abs=5e-4)
    assert normal_alkyl_tsei(20) < normal_alkyl_tsei(200) < 1.21


# --- the radius term and the traversal: every other printed value -----------


def _printed_case(row: dict) -> float:
    mol = Chem.MolFromSmiles(row["smiles"])
    if row["hydrogens"]:
        mol = Chem.AddHs(mol)
    return substituent_tsei(mol, 0, 1, include_hydrogens=row["hydrogens"]).value


@pytest.mark.parametrize(
    "row", reference_values(), ids=lambda r: f"{r['label']}-table{r['table']}"
)
def test_every_printed_reference_value_reproduces(row):
    """18 values across Tables 2, 4 and 6.

    Tolerance is 2e-4 rather than 5e-5 because the paper TRUNCATES some
    rows and rounds others -- i-Bu is 1.199074 printed as 1.1990, while
    n-Bu is 1.177662 printed as 1.1777. Measured, not assumed.
    """
    assert _printed_case(row) == pytest.approx(row["tsei"], abs=2e-4)


def test_a_first_tier_chlorine_is_the_papers_own_worked_example():
    """THE CASE THE EQ-7 IMPLEMENTATION GOT WRONG, and the sharpest single
    check that the radius term is present.

    "Taking Rrc-Cl for example, Cl atom is located in the first tier of
    substituent. Its atomic covalent radius is 0.99 x 10-8 cm and the bond
    length of C-Cl is (0.772+0.99) x 10-8 cm." The paper then prints
    TSEI_Cl = 1.4190. Eq 7 -- `SUM 1/L^3` -- gives exactly 1.000 for any
    first-tier atom whatever it is, which is the bug: it cannot tell a
    chlorine from a carbon.
    """
    chlorine = substituent_tsei(Chem.MolFromSmiles("CCl"), 0, 1)
    assert chlorine.value == pytest.approx(1.4190, abs=5e-5)
    assert chlorine.value > 1.4, "a first-tier halogen has collapsed back to eq 7's 1.000"

    carbon = substituent_tsei(_chain(1), 0, 1)
    assert carbon.value == pytest.approx(1.0000, abs=5e-5)


def test_the_traversal_sums_bond_lengths_rather_than_counting_bonds():
    """OEt, WHICH IS THE ONLY FIXTURE THAT CAN SHOW THIS.

    A first-tier halogen proves the radius appears in the NUMERATOR and
    says nothing about `l_i`, because a one-bond path has nothing to sum.
    On -O-CH2-CH3 the third-tier carbon's path is
    (R_C+R_O) + (R_O+R_C) + (R_C+R_C) = 4.408, where counting bonds and
    multiplying by l_CC would give 3 x 1.544 = 4.632 -- a 5% error in a
    length, cubed.

    The paper prints 0.9939 for OEt and 0.9505 for MeO; both are matched
    to four decimals, and the assertion below fixes what makes them
    differ.
    """
    ethoxy = substituent_tsei(Chem.AddHs(Chem.MolFromSmiles("COCC")), 0, 1,
                              include_hydrogens=True)
    methoxy = substituent_tsei(Chem.AddHs(Chem.MolFromSmiles("COC")), 0, 1,
                               include_hydrogens=True)
    assert ethoxy.value == pytest.approx(0.9939, abs=5e-5)
    assert methoxy.value == pytest.approx(0.9505, abs=5e-5)

    # The topological-distance-only form would put the third-tier carbon
    # at 1/27; the summed-bond-length form puts it lower, because a C-O
    # bond is shorter than a C-C one.
    carbons = [i for i in ethoxy.increments if
               Chem.AddHs(Chem.MolFromSmiles("COCC")).GetAtomWithIdx(i).GetAtomicNum() == 6]
    third = min(ethoxy.increments[i] for i in carbons)
    assert third > 1.0 / 27.0, (
        "the third-tier carbon is not above 1/27, so the path is being counted "
        "in bonds rather than summed in bond lengths"
    )


def test_an_independently_computed_heteroatom_case():
    """The traversal, worked by hand rather than read off the page.

    -O-CH3 with hydrogens EXCLUDED, so only two terms exist and the
    arithmetic fits in a comment:

        O   R_rel = 0.66/0.772,  l = 0.772+0.66 = 1.432,  l_rel = 1.432/1.544
        C   R_rel = 1,           l = 2 x 1.432  = 2.864,  l_rel = 2.864/1.544

    This is the check the printed values cannot be: every one of them
    exercises the same code, so a fixture the code did not generate and
    the paper did not print is the only fully independent arm.
    """
    r_c, r_o = 0.772, 0.66
    l_cc = 2 * r_c
    oxygen = (r_o / r_c) ** 3 / (((r_c + r_o) / l_cc) ** 3)
    carbon = 1.0 / ((2 * (r_c + r_o) / l_cc) ** 3)
    expected = oxygen + carbon

    result = substituent_tsei(Chem.MolFromSmiles("COC"), 0, 1)
    assert result.value == pytest.approx(expected, abs=1e-12)
    assert result.atoms == 2
    # ... and it is NOT what counting bonds would give.
    assert result.value != pytest.approx(1.0 + 1.0 / 8.0, abs=1e-3)


# --- the crowded-branch correction -----------------------------------------


def test_tert_butyl_carries_the_papers_own_crowding_correction():
    """"when three next tier carbon atoms connected with one carbon atom,
    the total dTSEI of these three carbon atoms is 6.5 times of that of
    one next tier carbon atom".

    Every TSEI the paper publishes after that sentence uses it: t-Bu is
    1.8125 in Table 2 and 1.8395 in Table 6, never 1.3750.
    """
    assert substituent_tsei(
        Chem.MolFromSmiles("CC(C)(C)C"), 0, 1
    ).value == pytest.approx(1.8125, abs=5e-5)


def test_the_uncorrected_form_is_still_reachable_and_is_the_papers_variant_a():
    """Table 2 tabulates BOTH and labels them a and b, so the plain form
    is a published variant rather than a bug -- it is simply the one the
    paper's own correlation prefers less (R = 0.9411 against 1.0000)."""
    plain = substituent_tsei(
        Chem.MolFromSmiles("CC(C)(C)C"), 0, 1, crowded_branches=False
    )
    assert plain.value == pytest.approx(1.0 + 3 * 0.1250, abs=5e-5)


def test_two_branches_are_not_corrected_and_table_4_is_why():
    """The rule is stated for THREE and implemented for three only.

    i-Pr is 1.2500 in Table 2 and i-Bu is 1.1990 in Table 4, both plain
    sums over two second-tier carbons. Extending the correction to two
    would break both -- measured, i-Bu would become 1.2273.
    """
    assert substituent_tsei(
        Chem.MolFromSmiles("CC(C)C"), 0, 1
    ).value == pytest.approx(1.2500, abs=5e-5)
    assert substituent_tsei(
        Chem.MolFromSmiles("CCC(C)C"), 0, 1
    ).value == pytest.approx(1.1990, abs=2e-4)


def test_the_reaction_centres_own_neighbours_are_not_a_crowded_branch():
    """Three substituents crowding a centre is a different physical claim,
    and the paper does not make it: its rule is about crowding WITHIN one
    substituent. A centre with three methyls still reports 1.0000 for each
    of them, because each is asked about separately."""
    neopentane = Chem.MolFromSmiles("CC(C)(C)C")
    # atom 1 is the quaternary carbon; ask about one of ITS methyls with
    # the quaternary carbon as the centre.
    one_methyl = substituent_tsei(neopentane, 1, 0)
    assert one_methyl.atoms == 1
    assert one_methyl.value == pytest.approx(1.0000, abs=5e-5)


# --- the traversal's own rules ---------------------------------------------


def test_hydrogens_are_excluded_by_default_as_eq_6_simplifies():
    """"if the hydrogen atoms are ignored" -- eq 6 onward, and the
    convention of Tables 1, 2 and 4.

    Asserted through an EXPLICIT-hydrogen molecule, because that is the
    form where getting it wrong changes the answer, and a SMILES-only test
    could never tell.
    """
    implicit = substituent_tsei(_chain(3), 0, 1)
    explicit = substituent_tsei(Chem.AddHs(_chain(3)), 0, 1)
    assert explicit.value == pytest.approx(implicit.value, abs=1e-12)
    assert explicit.atoms == implicit.atoms == 3


def test_including_hydrogens_is_table_6s_convention_and_is_a_different_number():
    """Footnote c: Table 6's values "contain the steric effect of hydrogen
    atoms in all substituents". One paper, two conventions, each labelled
    -- so neither may be picked silently."""
    with_h = substituent_tsei(Chem.AddHs(_chain(1)), 0, 1, include_hydrogens=True)
    without = substituent_tsei(Chem.AddHs(_chain(1)), 0, 1)
    assert with_h.value == pytest.approx(1.0362, abs=5e-5)
    assert without.value == pytest.approx(1.0000, abs=5e-5)
    assert with_h.atoms == 4 and without.atoms == 1


def test_the_substituent_stops_at_the_reaction_centre():
    """A walk that crossed the centre would swallow the rest of the
    molecule and score the whole thing as one substituent."""
    mol = Chem.MolFromSmiles("C(C)C")
    first = substituent_atoms(mol, 0, 1)
    assert first == [1], f"the walk leaked past the reaction centre: {first}"


def test_a_ring_fused_to_the_centre_is_counted_whole():
    """Not an edge case being tolerated -- those atoms really do screen it.

    Cyclohexyl on a centre: six ring carbons, at 1, 2, 2, 3, 3, 4 bonds.
    All-carbon, so the eq-7 arithmetic is still the right expectation.
    """
    result = substituent_tsei(Chem.MolFromSmiles("C1CCCCC1C"), 6, 0)
    assert result.atoms == 6
    expected = 1 + 2 * (1 / 8) + 2 * (1 / 27) + 1 / 64
    assert result.value == pytest.approx(expected, abs=5e-5)


def test_the_path_is_the_shortest_one_through_a_ring():
    """A depth-first walk builds a spanning tree whose ring paths can be
    arbitrarily long, and every increment computed from it would be too
    small while still looking like a TSEI. The far carbon of a cyclohexyl
    is 3 bonds away the short way and 3 the other, but the atoms at 2 are
    4 bonds away round the back."""
    result = substituent_tsei(Chem.MolFromSmiles("C1CCCCC1C"), 6, 0)
    increments = sorted(result.increments.values(), reverse=True)
    assert increments[1] == pytest.approx(1 / 8, abs=5e-5), (
        "the second-nearest ring atom is not at 2 bonds, so the walk is not "
        "taking the shortest path"
    )


# --- the radius table -------------------------------------------------------


def test_the_two_radii_the_paper_prints_outright():
    """"the carbon atomic covalent radius RC is 0.772 x 10-8 cm" and, for
    chlorine, "Its atomic covalent radius is 0.99 x 10-8 cm".

    RDKit's `GetRcovalent` gives 0.760 and 1.02 -- the Cordero 2008 set,
    a different table. Substituting it puts the paper's own chlorine
    example at 1.5052 against a printed 1.4190, so this is not a
    precision quibble.
    """
    assert covalent_radius("C") == pytest.approx(0.772, abs=1e-9)
    assert covalent_radius("Cl") == pytest.approx(0.99, abs=1e-9)

    from rdkit.Chem import GetPeriodicTable

    table = GetPeriodicTable()
    assert table.GetRcovalent("C") != pytest.approx(0.772, abs=1e-3), (
        "RDKit now agrees with the paper; the warning above can be retired"
    )


#: `symbol -> the TSEI value the paper prints for a lone first-tier atom`.
#: Only the halogens: they are the substituents that ARE one atom, so eq
#: 8a collapses to a closed form that inverts.
_FIRST_TIER_HALOGENS = {"F": 0.7449, "Cl": 1.4190, "Br": 1.6957, "I": 2.0265}


@pytest.mark.parametrize("symbol,printed", sorted(_FIRST_TIER_HALOGENS.items()))
def test_the_transcribed_radius_agrees_with_the_one_the_paper_implies(symbol, printed):
    """TWO ROUTES THAT SHARE NO STEP, AND THIS IS THE LIVE CROSS-CHECK.

    The radii are transcribed from Lange's Handbook Table 4.7 now, but
    before that book was available they were RECOVERED by inverting these
    printed values: for a lone first-tier atom X, eq 8a collapses to
    `8 rho^3 / (1 + rho)^3` with `rho = R_X / R_C`.

    Keeping the inversion as a test rather than as history is what makes a
    mistyped radius fail: the transcription would have to be wrong in
    exactly the way that reproduces a number from a different paper.
    """
    radius_c = covalent_radius("C")
    q = (printed / 8.0) ** (1.0 / 3.0)  # rho / (1 + rho)
    implied = q / (1.0 - q) * radius_c
    assert covalent_radius(symbol) == pytest.approx(implied, abs=5e-5)


def test_hydrogen_and_oxygen_are_cross_checked_through_a_whole_substituent():
    """The other three of the seven, and they need more than a closed form.

    Methyl's 1.0362 is one carbon plus three hydrogens at the next tier;
    methoxy's 0.9505 is an oxygen, a carbon and three hydrogens. Both
    reproduce only if H = 0.30 and O = 0.66 as the book prints them, and
    OEt = 0.9939 exercises the pair together over a longer path.
    """
    assert covalent_radius("H") == pytest.approx(0.30, abs=1e-9)
    assert covalent_radius("O") == pytest.approx(0.66, abs=1e-9)

    def with_h(smiles):
        return substituent_tsei(
            Chem.AddHs(Chem.MolFromSmiles(smiles)), 0, 1, include_hydrogens=True
        ).value

    assert with_h("CC") == pytest.approx(1.0362, abs=5e-5)
    assert with_h("COC") == pytest.approx(0.9505, abs=5e-5)
    assert with_h("COCC") == pytest.approx(0.9939, abs=5e-5)


def test_every_shipped_radius_carries_its_row_from_the_book():
    """SO A FUTURE AUDIT RUNS AGAINST THE PAGE LINE BY LINE.

    The book prints picometres and the paper works in 1e-8 cm, so both are
    stored: the derived value and the number actually on the page.
    """
    payload = json.loads(
        (Path(tsei_module.__file__).parent / "data" / "tsei_radii.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["_source_key"] == "langes15"
    assert "cao2004" in payload["_supplementary_source_keys"]
    assert len(payload["radii"]) == 28

    for symbol, row in payload["radii"].items():
        assert row["element"], f"{symbol} lost the book's own element name"
        assert row["radius"] == pytest.approx(row["picometres"] / 100.0, abs=1e-9)
        assert row["radius"] > 0

    # Carbon's extra digit is what identifies the table: the book prints
    # 77.2 pm where a neighbouring set would round to 77.
    assert payload["radii"]["C"]["picometres"] == 77.2


def test_the_seven_cross_checked_radii_are_marked_as_such():
    """A radius with a second, independent route to it is a different kind
    of number from one that has only the book, and the data says which is
    which rather than leaving a reader to work it out."""
    payload = json.loads(
        (Path(tsei_module.__file__).parent / "data" / "tsei_radii.json").read_text(
            encoding="utf-8"
        )
    )
    checked = {s for s, row in payload["radii"].items() if row["cross_check"]}
    assert checked == {"C", "Cl", "H", "O", "F", "Br", "I"}


def test_nitrogen_sulfur_and_phosphorus_are_covered_now():
    """THEY WERE REFUSED UNTIL THE BOOK ARRIVED, which made the projection
    decline every amine, thiol and phosphine -- most of drug space.

    The paper prints no TSEI for any substituent containing them, so the
    inversion could never reach them; Table 4.7 simply has them.
    """
    assert covalent_radius("N") == pytest.approx(0.70, abs=1e-9)
    assert covalent_radius("S") == pytest.approx(1.04, abs=1e-9)
    assert covalent_radius("P") == pytest.approx(1.10, abs=1e-9)

    # A first-tier nitrogen screens LESS than a carbon, because it is
    # smaller -- 0.70 against 0.772. The chlorine case is the other side:
    # bigger, so 1.4190.
    nitrogen = substituent_tsei(Chem.MolFromSmiles("CN"), 0, 1).value
    carbon = substituent_tsei(Chem.MolFromSmiles("CC"), 0, 1).value
    chlorine = substituent_tsei(Chem.MolFromSmiles("CCl"), 0, 1).value
    assert nitrogen < carbon < chlorine
    assert carbon == pytest.approx(1.0, abs=5e-5)


def test_an_element_the_book_does_not_tabulate_is_refused():
    """Table 4.7 stops at 28 elements. Everything else -- the transition
    metals beyond Cu/Ag/Cd/Hg/Zn, the lanthanides, the actinides -- is
    refused by name rather than given a radius from a neighbouring set,
    which is what RDKit's would be."""
    with pytest.raises(TseiRadiusError, match="Pt"):
        covalent_radius("Pt")

    with pytest.raises(TseiRadiusError, match="Table 4.7"):
        covalent_radius("Fe")


def test_a_refused_element_refuses_the_whole_substituent():
    """A partial sum silently understates the screening and still returns
    a plausible TSEI. `atomic_polarizabilities` refuses the same way and
    for the same reason."""
    with pytest.raises(TseiRadiusError):
        substituent_tsei(Chem.MolFromSmiles("CCCC[Fe]"), 0, 1)


# --- the per-atom increments ------------------------------------------------


def test_the_index_is_reported_per_atom_as_the_paper_tabulates_it():
    """`delta-TSEI` is the paper's own column, and it is what makes a
    disagreement debuggable rather than merely wrong."""
    result = substituent_tsei(_chain(3), 0, 1)
    assert sorted(round(v, 6) for v in result.increments.values()) == sorted(
        round(1 / d**3, 6) for d in (1, 2, 3)
    )
    assert sum(result.increments.values()) == pytest.approx(result.value)


def test_the_one_printed_value_that_does_not_reproduce_is_recorded():
    """TABLE 6'S i-Pr = 1.3752, AND THIS TEST EXISTS SO IT IS NOT
    QUIETLY FORGOTTEN.

    The paper's own text says i-Pr is 1.2500 with hydrogens ignored, Table
    2 and Table 4 agree, and 1.2500 plus its seven hydrogens is 1.2801 --
    which is what this implementation gives. Reaching 1.3752 needs the two
    second-tier carbons scaled by 2.7611, a factor the paper never states
    and which Table 4's own two-branch rows refute. 1.3752 is within
    0.0002 of 1.3750, t-Bu's plain-additivity value in the table above.

    Asserted as a DISAGREEMENT rather than tolerated: if a future reading
    explains it, this test fails and the account above can be corrected.
    """
    computed = substituent_tsei(
        Chem.AddHs(Chem.MolFromSmiles("CC(C)C")), 0, 1, include_hydrogens=True
    ).value
    assert computed == pytest.approx(1.2801, abs=5e-5)
    assert abs(computed - 1.3752) > 0.09
    assert "1.3752" in (tsei_module.__doc__ or ""), (
        "the module no longer records the printed value it cannot reproduce"
    )


def test_summing_the_projection_over_atoms_has_no_referent():
    """WHY THE PROJECTION DECLINES A TOTAL, shown rather than asserted.

    A MUTATION FOUND THIS GAP. Declaring a plausible total --
    `declare_total(0.0, "TSEI projection total")` -- passed every guard in
    this file and in `tests/test_declared_totals.py`, because those check
    that a declaration exists and is WELL FORMED, never which answer is
    right. `test_the_two_meaningless_sums_are_declined_by_name` names this
    calculator now, and this test is the chemistry behind that name.

    Chloromethane is the clearest case. The carbon feels 1.4190 from the
    chlorine and the chlorine feels 0.6729 back, across the same bond --
    the increments are ASYMMETRIC, because `l_i` is a bond length and the
    radius sits in the numerator on one side only. So the sum over atoms
    is 2.0919: not either atom's answer, not twice anything, and not a
    property of the molecule.
    """
    from openchem.chem.tsei import compute_tsei_projection
    from openchem.domain.common import TOTAL

    result = compute_tsei_projection(Chem.MolFromSmiles("CCl"), "uuid")
    values = result.values
    assert values[0] == pytest.approx(1.4190, abs=5e-4)
    assert values[1] == pytest.approx(0.6729, abs=5e-4)

    total = sum(values.values())
    assert total == pytest.approx(2.0919, abs=1e-3)
    assert not any(
        total == pytest.approx(v, abs=1e-3) for v in values.values()
    ), "the sum coincides with an atom's own value, so this fixture cannot show it"

    declaration = result.provenance.parameters[TOTAL]
    assert declaration["declared"] is False
    assert "twice" in declaration["reason"]
