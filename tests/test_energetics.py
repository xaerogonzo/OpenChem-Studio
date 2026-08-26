"""Oxygen balance, gated against Klapötke's own reference table.

**THE FIXTURE CARRIES THE BOOK'S PRINTED FORMULA AS WELL AS ITS PRINTED
VALUE, AND THAT IS NOT DECORATION.** Table 4.1 gives both, so the formula
is an independent check on the SMILES written here -- and it earned its
place immediately: the first HNS fixture was 2,x-dinitrostilbene rather than
the 2,2',4,4',6,6'-hexanitro compound, giving C14H10N2O4 against the book's
C14H6N6O12. Without the formula check that would have read as a 104
percentage-point failure of the CODE.

A fixture is not "big enough" or "small". It is right or wrong about what it
claims to be, and only a second printed quantity can say which.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.chem import energetics as E

#: Klapötke, Chemistry of High-Energy Materials 4th ed., Table 4.1 (p128).
#: (name, SMILES, the formula the book prints, the Omega_CO2 the book prints)
TABLE_4_1 = [
    ("ammonium nitrate", "[N+](=O)([O-])[O-].[NH4+]", "H4N2O3", +20.0),
    ("nitroglycerine", "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]", "C3H5N3O9", +3.5),
    ("PETN",
     "C(C(CO[N+](=O)[O-])(CO[N+](=O)[O-])CO[N+](=O)[O-])O[N+](=O)[O-]", "C5H8N4O12", -10.1),
    ("RDX", "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]", "C3H6N6O6", -21.6),
    ("HMX",
     "O=[N+]([O-])N1CN(CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "C4H8N8O8", -21.6),
    ("nitroguanidine", "NC(=N)N[N+](=O)[O-]", "CH4N4O2", -30.7),
    ("picric acid", "Oc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "C6H3N3O7", -45.4),
    ("hexanitrostilbene",
     "[O-][N+](=O)c1cc([N+](=O)[O-])cc([N+](=O)[O-])c1/C=C/c1c([N+](=O)[O-])"
     "cc([N+](=O)[O-])cc1[N+](=O)[O-]", "C14H6N6O12", -67.6),
    ("TNT", "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "C7H5N3O6", -74.0),
]

IDS = [row[0] for row in TABLE_4_1]


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"the fixture SMILES {smiles!r} does not parse"
    return mol


# ---------------------------------------------------------------------------
# 1  the source's own reference table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,smiles,formula,printed", TABLE_4_1, ids=IDS)
def test_the_fixture_really_is_the_compound_the_book_names(name, smiles, formula, printed):
    """Checked BEFORE the value, because a wrong structure produces a wrong
    number and the number is what a reader would go looking at."""
    assert rdMolDescriptors.CalcMolFormula(_mol(smiles)) == formula


@pytest.mark.parametrize("name,smiles,formula,printed", TABLE_4_1, ids=IDS)
def test_table_4_1_reproduces(name, smiles, formula, printed):
    result = E.oxygen_balance(_mol(smiles))
    assert result.applicable
    # 0.1 pp, which is the book's own one-decimal printing.
    assert result.to_carbon_dioxide == pytest.approx(printed, abs=0.1)


def test_the_table_spans_both_signs_and_is_not_all_one_kind():
    """Asserts its own setup. A fixture set that was all negative could not
    tell a sign error from a correct implementation."""
    values = [row[3] for row in TABLE_4_1]
    assert max(values) > 0 and min(values) < 0
    assert len(TABLE_4_1) == 9


def test_a_carbon_free_substance_is_handled():
    """Ammonium nitrate has a = 0, and a formula indexed on carbon could get
    it wrong while every other row still passed."""
    result = E.oxygen_balance(_mol("[N+](=O)([O-])[O-].[NH4+]"))
    assert result.carbon == 0
    assert result.to_carbon_dioxide == pytest.approx(20.0, abs=0.1)


# ---------------------------------------------------------------------------
# 2  the sign convention, which a review got backwards
# ---------------------------------------------------------------------------


def test_there_is_no_leading_minus():
    """THE EXPRESSION IS `(d - 2a - b/2) x 1600 / M`, WITH NO LEADING MINUS.

    A review of this work supplied `-[d - 2a - b/2](1600/M)` while quoting
    TNT at -74% in the same sentence. Checked on two compounds with OPPOSITE
    signs, because one case cannot distinguish a sign error from a different
    convention -- the negated form gives TNT +73.97 and nitroglycerin -3.52,
    both exactly backwards.
    """
    tnt = E.oxygen_balance(_mol(TABLE_4_1[-1][1])).to_carbon_dioxide
    ng = E.oxygen_balance(_mol(TABLE_4_1[1][1])).to_carbon_dioxide
    assert tnt < 0 and ng > 0
    assert tnt == pytest.approx(-74.0, abs=0.1)
    assert ng == pytest.approx(+3.5, abs=0.1)


# ---------------------------------------------------------------------------
# 3  two conventions, and they are different quantities
# ---------------------------------------------------------------------------


def test_the_two_bases_are_different_quantities():
    """TNT is -74.0% to CO2 and -24.7% to CO -- a factor of three. Reporting
    either as a bare "oxygen balance" is the ambiguity the naming prevents."""
    result = E.oxygen_balance(_mol(TABLE_4_1[-1][1]))
    assert result.to_carbon_dioxide == pytest.approx(-74.0, abs=0.1)
    assert result.to_carbon_monoxide == pytest.approx(-24.7, abs=0.1)


@pytest.mark.parametrize("name,smiles", [("RDX", TABLE_4_1[3][1]), ("HMX", TABLE_4_1[4][1])])
def test_the_nitramines_are_exactly_balanced_to_CO(name, smiles):
    """An EXACT zero, which is the sharpest thing separating the two formulas.

    RDX is C3H6N6O6: d - a - b/2 = 6 - 3 - 3 = 0 precisely. The CO2 basis is
    -21.6 for the same molecule, so a test that only read one of them could
    not see the two expressions swap.
    """
    result = E.oxygen_balance(_mol(smiles))
    assert result.to_carbon_monoxide == pytest.approx(0.0, abs=1e-9)
    assert result.to_carbon_dioxide == pytest.approx(-21.6, abs=0.1)


def test_a_substance_can_be_positive_on_one_basis_and_negative_on_the_other():
    """PETN: -10.1% to CO2 and +15.2% to CO. The sign itself flips, so the
    choice of basis is not a refinement -- it changes the verdict."""
    result = E.oxygen_balance(_mol(TABLE_4_1[2][1]))
    assert result.to_carbon_dioxide < 0 < result.to_carbon_monoxide


# ---------------------------------------------------------------------------
# 4  scope: formula arithmetic, not a fragmentation
# ---------------------------------------------------------------------------


def test_a_salt_is_accepted_because_this_reads_a_FORMULA():
    """`chem/joback.py` refuses a disconnected structure -- it has to
    decompose a molecule and the union of two is not a pure component. This
    has no such need, and ammonium nitrate is the source's OWN fixture, so
    refusing salts here would refuse the reference table."""
    mol = _mol("[N+](=O)([O-])[O-].[NH4+]")
    assert len(Chem.GetMolFrags(mol)) == 2, "the fixture must really be two fragments"
    assert E.oxygen_balance(mol).applicable


NON_CHNO = [
    ("a thiol", "CCS", "S"),
    ("a chloride", "ClCCl", "Cl"),
    ("a perchlorate salt", "[O-]Cl(=O)(=O)=O.[NH4+]", "Cl"),
    ("a metal salt", "[Na+].[N+](=O)([O-])[O-]", "Na"),
]


@pytest.mark.parametrize("name,smiles,element", NON_CHNO, ids=[c[0] for c in NON_CHNO])
def test_non_chno_is_refused_with_the_element_named(name, smiles, element):
    """The published formula is stated for CaHbNcOd. Ignoring a sulfur or a
    chlorine would give a confident wrong number for exactly the substances
    somebody would ask about -- ammonium perchlorate among them."""
    result = E.oxygen_balance(_mol(smiles))
    assert not result.applicable
    assert result.refusal is E.OxygenBalanceRefusal.NOT_CHNO
    assert element in result.detail
    assert result.to_carbon_dioxide is None
    assert result.to_carbon_monoxide is None


def test_refusal_text_is_generated_in_one_place():
    assert E.refusal_text(E.oxygen_balance(_mol("CC"))) == ""
    text = E.refusal_text(E.oxygen_balance(_mol("CCS")))
    assert "C/H/N/O" in text and "S" in text
    assert "wrong number" in text


def test_an_unreadable_structure_says_so():
    assert E.oxygen_balance(None).refusal is E.OxygenBalanceRefusal.NOT_A_STRUCTURE


# ---------------------------------------------------------------------------
# 5  hydrogens are counted, all of them
# ---------------------------------------------------------------------------


def test_implicit_hydrogens_are_counted():
    """A drawn structure carries most of its hydrogens implicitly, and `b` is
    every one of them. Methane is the smallest case where forgetting would be
    invisible in the formula and fatal in the value."""
    result = E.oxygen_balance(_mol("C"))
    assert result.hydrogen == 4
    # CH4: (0 - 2 - 2) x 1600 / 16.043
    assert result.to_carbon_dioxide == pytest.approx(-399.0, abs=1.0)


def test_an_explicit_hydrogen_structure_gives_the_same_answer():
    """The same substance drawn either way is the same substance."""
    implicit = E.oxygen_balance(_mol("CCO"))
    explicit = E.oxygen_balance(Chem.AddHs(_mol("CCO")))
    assert implicit.to_carbon_dioxide == pytest.approx(explicit.to_carbon_dioxide, abs=1e-9)
    assert implicit.hydrogen == explicit.hydrogen == 6


# ---------------------------------------------------------------------------
# 6  the reported result
# ---------------------------------------------------------------------------


def test_the_calculator_reports_both_bases_as_separate_named_facts():
    """NOT one value behind a `basis` parameter. A parameter lets a
    screenshot collapse back to "oxygen balance: -74%", which is the
    ambiguity the two names exist to prevent."""
    report = E.compute_oxygen_balance(_mol(TABLE_4_1[-1][1]), "uuid-1")
    labels = [f.label for f in report.facts]
    assert any("CO₂" in l for l in labels), labels
    assert any("CO basis" in l for l in labels), labels
    assert report.category == "energetic"


def test_every_reported_value_carries_its_unit():
    report = E.compute_oxygen_balance(_mol("CC"), "uuid-1")
    for fact in report.facts:
        if isinstance(fact.value, float):
            assert fact.units == "%"


def test_the_sign_is_shown_explicitly():
    """"+3.5" and "3.5" read differently for a quantity whose whole point is
    which side of zero it falls on."""
    report = E.compute_oxygen_balance(_mol(TABLE_4_1[1][1]), "uuid-1")
    shown = [f.display_value for f in report.facts if isinstance(f.value, float)]
    assert all(v.startswith(("+", "-")) for v in shown), shown


def test_a_refused_structure_reports_FAILED_and_says_why():
    report = E.compute_oxygen_balance(_mol("CCS"), "uuid-1")
    from openchem.domain.common import CacheState

    assert report.cache_state is CacheState.FAILED
    assert not report.facts
    assert "C/H/N/O" in report.error


def test_the_calculator_declines_a_total():
    """Two conventions for one substance are not two components of a sum."""
    from openchem.domain.common import TOTAL

    report = E.compute_oxygen_balance(_mol("CC"), "uuid-1")
    declaration = report.provenance.parameters[TOTAL]
    assert declaration["declared"] is False
    assert declaration["reason"]


# ===========================================================================
# Kamlet-Jacobs detonation properties
# ===========================================================================
#
# TWO ORACLES, DELIBERATELY FROM OPPOSITE ENDS. Table III supplies N, M, Q
# and rho0 AND the P and D that Eqs. (8) and (9) give from them, so it tests
# the arithmetic with no thermochemistry involved. Table VI supplies N, M and
# P for compounds decomposed by the paper's own arbitrary, so it tests the
# path from a structure. One oracle could not separate a broken equation
# from a broken decomposition.

#: Kamlet & Jacobs Table III (p26): rho0, N, M, Q, P_calc Eq.(8), D_calc Eq.(9)
TABLE_III = [
    ("HMX", 1.903, 0.0338, 27.20, 1496, 384.7, 9.157),
    ("RDX", 1.712, 0.0339, 27.15, 1496, 311.9, 8.512),
    ("TNT", 1.468, 0.0263, 27.94, 1258, 165.5, 6.512),
    ("Tetryl", 1.643, 0.0276, 30.06, 1411, 239.1, 7.548),
    ("Explosive D", 1.720, 0.0285, 28.27, 1098, 231.4, 7.312),
    ("Picramide", 1.770, 0.0265, 29.89, 1250, 250.0, 7.541),
    ("R-salt", 1.520, 0.0345, 23.08, 1397, 223.0, 7.478),
    ("DINA", 1.660, 0.0335, 26.93, 1450, 284.2, 8.203),
]


@pytest.mark.parametrize("name,rho,n,m,q,pressure,velocity", TABLE_III,
                         ids=[r[0] for r in TABLE_III])
def test_table_iii_reproduces(name, rho, n, m, q, pressure, velocity):
    """Eqs. (8) and (9) alone, against the paper's own printed results."""
    result = E.detonation_from_parameters(n, m, q, rho)
    assert result.applicable
    assert result.pressure_kbar == pytest.approx(pressure, abs=0.1)
    assert result.velocity_mm_per_us == pytest.approx(velocity, abs=0.02)


def test_the_pressure_constant_is_the_papers_and_not_the_textbooks():
    """K = 15.58, FOUR times in the paper -- the abstract, Eq. (8), the slope
    of Fig. 1, and the Table III page. Klapotke's textbook prints 15.88
    twice, and that is the value a future reader is most likely to "correct"
    this to.

    IT CANNOT BE CAUGHT DOWNSTREAM. 15.88 puts HMX at 392.1 kbar against the
    paper's own 384.7 -- a 1.9% shift that is entirely plausible on its own.
    Only the source separates them, so the constant is pinned by name.
    """
    assert E.DETONATION_PRESSURE_K == 15.58
    assert E.DETONATION_VELOCITY_A == 1.01
    assert E.DETONATION_VELOCITY_B == 1.30

    wrong = 15.88 * 1.903 ** 2 * (0.0338 * math.sqrt(27.20) * math.sqrt(1496))
    assert wrong == pytest.approx(392.1, abs=0.5)
    assert abs(wrong - 384.7) > 5


#: Kamlet & Jacobs Table VI: N and M from the H2O-CO2 arbitrary.
#: (name, a, b, c, d, N, M)
TABLE_VI_GAS = [
    ("TATB", 6, 6, 6, 6, 0.0291, 27.20),
    ("R-salt", 3, 6, 6, 3, 0.0345, 23.00),
    ("TNB", 6, 3, 3, 6, 0.0246, 32.00),
    ("TNA", 6, 4, 4, 6, 0.0263, 30.00),
]


@pytest.mark.parametrize("name,a,b,c,d,n,m", TABLE_VI_GAS, ids=[r[0] for r in TABLE_VI_GAS])
def test_the_arbitrary_reproduces_the_papers_own_N_and_M(name, a, b, c, d, n, m):
    got_n, got_m = E.arbitrary_gas(a, b, c, d)
    assert got_n == pytest.approx(n, abs=5e-5)
    assert got_m == pytest.approx(m, abs=0.01)


@pytest.mark.parametrize("name,a,b,c,d,n,m", TABLE_VI_GAS, ids=[r[0] for r in TABLE_VI_GAS])
def test_equation_14_IS_MISPRINTED_AND_THE_PAPERS_TABLES_PROVE_IT(name, a, b, c, d, n, m):
    """Eq. (14) is printed as (56c - 88d - 8b)/(2c + 2d + b), with two minus
    signs -- read at 3x magnification, where the typeface makes a minus
    plainly distinct from the bold plus of Eq. (13) directly above it, and
    the text layer agrees.

    That form is impossible. It gives these four compounds detonation gases
    of -8.00, 1.00, -18.29 and -14.00 g/mol, while the form derived from
    Eq. (12) gives the paper's own printed 27.20, 23.00, 32.00 and 30.00.
    Four for four.

    So this is a typesetting error in the source rather than a reading error
    here -- and BOTH halves are asserted, because "our formula matches" alone
    would not establish that the printed one is the broken one.
    """
    as_printed = (56 * c - 88 * d - 8 * b) / (2 * c + 2 * d + b)
    as_derived = (56 * c + 88 * d - 8 * b) / (2 * c + 2 * d + b)

    assert as_derived == pytest.approx(m, abs=0.01)
    assert abs(as_printed - m) > 1.0
    assert as_printed < 2.0, "the printed form gives a negative or absurd molar mass"
    assert E.arbitrary_gas(a, b, c, d)[1] == pytest.approx(as_derived, abs=1e-9)


def test_the_heat_of_detonation_carries_its_thousand():
    """Eq. (15b)'s numerator is kcal/mol over a denominator in g/mol, so the
    quotient is kcal/g while Eq. (8) wants cal/g.

    Checked by inverting the paper's own printed Q: TATB at 1075 cal/g
    implies a condensed-phase enthalpy of formation of -37.05 kcal/mol,
    against a literature value near -36.9. Losing the factor would give 1.075
    and a detonation pressure about thirty times too small.
    """
    q = E.heat_of_detonation(6, 6, 6, 6, -37.05)
    assert q == pytest.approx(1075, abs=1.0)
    assert q > 100, "a kcal/g answer would be about 1.075"


#: Table VI entry 23: TATB, at every density the paper prints.
TATB = "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]"
TATB_ENTHALPY = -37.05
TATB_PRESSURES = [(1.000, 77.5), (1.200, 111.7), (1.400, 152.0),
                  (1.600, 198.5), (1.841, 262.8), (1.895, 278.4), (1.938, 291.2)]


@pytest.mark.parametrize("rho,printed", TATB_PRESSURES, ids=[str(r[0]) for r in TATB_PRESSURES])
def test_end_to_end_from_a_smiles_against_table_vi(rho, printed):
    """Structure -> N, M -> Q -> P, at seven loading densities."""
    result = E.detonation(_mol(TATB), rho, TATB_ENTHALPY)
    assert result.applicable, result.refusal
    assert result.pressure_kbar == pytest.approx(printed, rel=3e-3)


def test_the_end_to_end_intermediates_match_the_paper_too():
    """Not just the answer -- N, M, Q and G each independently, so a
    compensating pair of errors cannot pass."""
    result = E.detonation(_mol(TATB), 1.895, TATB_ENTHALPY)
    assert result.moles_gas_per_gram == pytest.approx(0.0291, abs=5e-5)
    assert result.mean_gas_mass == pytest.approx(27.20, abs=0.01)
    assert result.heat_of_detonation == pytest.approx(1075, abs=1.0)
    assert result.g_factor == pytest.approx(0.791, abs=0.002)


def test_pressure_goes_as_the_square_of_the_density():
    """Which is why the density may not be guessed at."""
    low = E.detonation(_mol(TATB), 1.0, TATB_ENTHALPY).pressure_kbar
    high = E.detonation(_mol(TATB), 2.0, TATB_ENTHALPY).pressure_kbar
    assert high / low == pytest.approx(4.0, rel=1e-9)


def test_the_fixture_really_is_TATB():
    assert rdMolDescriptors.CalcMolFormula(_mol(TATB)) == "C6H6N6O6"


# --- refusals --------------------------------------------------------------


def test_a_missing_loading_density_is_refused_and_named():
    result = E.detonation(_mol(TATB), None, TATB_ENTHALPY)
    assert result.refusal is E.DetonationRefusal.NO_LOADING_DENSITY
    text = E.detonation_refusal_text(result)
    assert "crystal density" in text
    assert "square" in text


def test_a_missing_enthalpy_is_refused_and_says_why_it_is_not_estimated():
    result = E.detonation(_mol(TATB), 1.8, None)
    assert result.refusal is E.DetonationRefusal.NO_ENTHALPY_OF_FORMATION
    text = E.detonation_refusal_text(result)
    assert "ideal-gas" in text
    assert "rotor" in text


def test_an_over_oxidised_explosive_is_outside_the_arbitrary():
    """Nitroglycerin, C3H5N3O9. Eq. (12) is stated for a compound with no
    more oxygen than is required to convert carbon to CO2, and NG has more --
    its solid-carbon term goes negative. The arbitrary does not model the
    excess O2 that really forms, so this refuses rather than extrapolates.

    Asserts its own setup: NG must really be over-oxidised, or the guard is
    testing nothing.
    """
    ng = _mol("C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]")
    balance = E.oxygen_balance(ng)
    a, b, d = balance.carbon, balance.hydrogen, balance.oxygen
    assert d > 2 * a + b / 2, "the fixture must really be over-oxidised"

    result = E.detonation(ng, 1.6, -88.6)
    assert result.refusal is E.DetonationRefusal.OUTSIDE_THE_ARBITRARY
    assert "over-oxidised" in result.detail
    assert "arbitrary" in E.detonation_refusal_text(result)


def test_a_non_chno_explosive_is_refused():
    result = E.detonation(_mol("ClCCl"), 1.5, 0.0)
    assert result.refusal is E.DetonationRefusal.NOT_CHNO


# --- the RUBY correction, which must never be a default --------------------


def test_the_ruby_correction_is_off_by_default():
    """Eq. (16) is for matching the RUBY code and, in the paper's own words,
    "not necessarily applicable for the prediction of actual detonation
    parameters". So it is an opt-in that says so."""
    # Table VI entry 1: TNM, N=0.0306, M=32.67, Q=525, G=1.000, rho0=1.640.
    # The paper prints BOTH the plain 167.8 and the corrected 157.7 for it, so
    # this is its own worked example of the correction rather than a fixture
    # chosen here. HMX will NOT do -- its G is 0.919, below the threshold,
    # which is what the first version of this test got wrong.
    plain = E.detonation_from_parameters(0.0306, 32.67, 525, 1.640)
    assert plain.g_factor > E.RUBY_CORRECTION_G_THRESHOLD, "fixture must trip the threshold"
    assert plain.phi == pytest.approx(4.007, abs=0.002)
    assert plain.pressure_kbar == pytest.approx(167.8, abs=0.2)

    corrected = E.detonation_from_parameters(0.0306, 32.67, 525, 1.640, ruby_correction=True)
    assert corrected.pressure_kbar == pytest.approx(157.7, abs=0.3)


def test_the_ruby_correction_does_nothing_below_its_threshold():
    """It is keyed on G = N x M, not applied unconditionally."""
    low = E.detonation_from_parameters(0.0291, 27.20, 1075, 1.895)
    assert low.g_factor < E.RUBY_CORRECTION_G_THRESHOLD
    with_flag = E.detonation_from_parameters(0.0291, 27.20, 1075, 1.895, ruby_correction=True)
    assert with_flag.pressure_kbar == pytest.approx(low.pressure_kbar, rel=1e-12)


# --- the reported result ---------------------------------------------------


def test_the_calculator_refuses_until_both_inputs_are_supplied():
    from openchem.domain.common import CacheState

    for params, expected in (
        ({}, "LOADING DENSITY"),
        ({"loading_density_g_cm3": 1.8}, "enthalpy of formation"),
    ):
        report = E.compute_detonation(_mol(TATB), "uuid-1", params)
        assert report.cache_state is CacheState.FAILED
        assert expected in report.error


def test_a_supplied_enthalpy_of_exactly_zero_is_not_read_as_missing():
    """Zero is a legitimate enthalpy of formation, so it cannot double as the
    unset sentinel -- that would compute a confident number from a value
    nobody entered."""
    from openchem.domain.common import CacheState

    report = E.compute_detonation(_mol(TATB), "uuid-1", {
        "loading_density_g_cm3": 1.8, "enthalpy_of_formation_kcal_mol": 0.0})
    assert report.cache_state is CacheState.COMPLETED
    assert report.provenance.parameters["enthalpy_of_formation_kcal_mol"] == 0.0


def test_the_report_records_where_the_enthalpy_came_from():
    """A reader cannot otherwise tell a supplied value from an estimated one,
    and there is no estimated route here at all."""
    report = E.compute_detonation(_mol(TATB), "uuid-1", {
        "loading_density_g_cm3": 1.895, "enthalpy_of_formation_kcal_mol": TATB_ENTHALPY})
    assert report.provenance.parameters["enthalpy_source"] == "supplied_by_user"
    assert report.provenance.parameters["K"] == 15.58


def test_the_reported_pressure_and_velocity_carry_their_units():
    report = E.compute_detonation(_mol(TATB), "uuid-1", {
        "loading_density_g_cm3": 1.895, "enthalpy_of_formation_kcal_mol": TATB_ENTHALPY})
    units = {f.label: f.units for f in report.facts}
    assert units["Detonation pressure (C-J)"] == "kbar"
    assert units["Detonation velocity"] == "mm/us"
    assert units["Heat of detonation"] == "cal/g"
