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
