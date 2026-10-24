"""Oxygen balance beyond C/H/N/O, held to the sources' own printed values.

Meyer's Explosives first (most of the elements), then Conkling & Mocella's
Table 2.5 and the boron sources for what Meyer never prints.

Meyer, Köhler & Homburg, *Explosives*, 7th ed. [source:meyer2016]. The
definition (p247) names the products -- "CO2, H2O, SO2, Al2O3, etc." -- and
the thermodynamic entry (p321) adds "Chlorine will be converted into HCl" and
the alkaline-earth oxides. WHICH oxide every other metal forms is never
written; it is what the book's printed balances use. So every element the
code accepts is pinned here by at least one printed value, and each fixture
carries the formula the book prints beside the value, because a SMILES that
is the wrong compound reads as a failure of the code (see `test_energetics`).

The Oxygen Balance entry and its Table 21 are p247, the thermodynamic
statement p321 (the book's printed page numbers).
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.chem import energetics as E
from openchem.domain.common import CacheState
from tests.test_energetics import TABLE_4_1

NITRATE = "[O-][N+](=O)[O-]"
CHLORATE = "[O-]Cl(=O)=O"
PERCHLORATE = "[O-]Cl(=O)(=O)=O"
AZIDE = "[N-]=[N+]=[N-]"
PICRATE = "[O-]c1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"
STYPHNATE = "[O-]c1c(cc(c([O-])c1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"
NITROTETRAZOLATE = "[O-][N+](=O)c1nn[n-]n1"
ACETYLSALICYLATE = "CC(=O)Oc1ccccc1C(=O)[O-]"
ETHYLHEXANOATE = "CCCCC(CC)C(=O)[O-]"

#: (name of the book's entry -- it is alphabetical, so the name is the
#: locator -- SMILES, the formula the book prints, the balance it prints,
#: tolerance). The tolerance is the book's own printing -- one decimal is
#: +/-0.05 and the code's largest miss is 0.08 -- except where a row says
#: otherwise.
MEYER = [
    # -- chlorine taken by hydrogen, as HCl ---------------------------------
    ("ammonium chloride", "[NH4+].[Cl-]", "H4NCl", -44.9, 0.1),
    ("ammonium perchlorate", f"[NH4+].{PERCHLORATE}", "H4NClO4", +34.04, 0.1),
    ("1-chloro-2,4-dinitrobenzene", "Clc1ccc(cc1[N+](=O)[O-])[N+](=O)[O-]",
     "C6H3N2O4Cl", -71.1, 0.1),
    ("guanidinium perchlorate", f"NC(N)=[NH2+].{PERCHLORATE}", "CH6N3O4Cl", -5.0, 0.1),
    ("hydrazinium perchlorate", f"N[NH3+].{PERCHLORATE}", "H5N2O4Cl", +24.1, 0.1),
    # -- chlorine taken by a metal, as its chloride --------------------------
    ("potassium chlorate", f"[K+].{CHLORATE}", "KClO3", +39.2, 0.1),
    ("potassium perchlorate", f"[K+].{PERCHLORATE}", "KClO4", +46.2, 0.1),
    ("sodium chlorate", f"[Na+].{CHLORATE}", "NaClO3", +45.1, 0.1),
    ("sodium perchlorate", f"[Na+].{PERCHLORATE}", "NaClO4", +52.3, 0.1),
    ("lithium perchlorate", f"[Li+].{PERCHLORATE}", "LiClO4", +60.2, 0.1),
    # -- metals to their oxides -------------------------------------------------
    ("aluminum (Table 21)", "[Al]", "Al", -89.0, 0.1),
    ("potassium nitrate", f"[K+].{NITRATE}", "KNO3", +39.6, 0.1),
    ("sodium nitrate", f"[Na+].{NITRATE}", "NaNO3", +47.1, 0.1),
    ("lithium nitrate", f"[Li+].{NITRATE}", "LiNO3", +58.1, 0.1),
    ("calcium nitrate", f"[Ca+2].{NITRATE}.{NITRATE}", "CaN2O6", +48.8, 0.1),
    ("barium nitrate", f"[Ba+2].{NITRATE}.{NITRATE}", "BaN2O6", +30.6, 0.1),
    ("strontium nitrate", f"[Sr+2].{NITRATE}.{NITRATE}", "SrN2O6", +37.8, 0.1),
    ("lead nitrate", f"[Pb+2].{NITRATE}.{NITRATE}", "PbN2O6", +24.2, 0.1),
    ("lead azide", f"[Pb+2].{AZIDE}.{AZIDE}", "PbN6", -5.5, 0.1),
    ("lead dioxide", "O=[Pb]=O", "PbO2", +6.7, 0.1),
    ("lead picrate", f"[Pb+2].{PICRATE}.{PICRATE}", "C12H4N6O14Pb", -31.4, 0.1),
    ("lead 2-ethylhexanoate", f"[Pb+2].{ETHYLHEXANOATE}.{ETHYLHEXANOATE}",
     "C16H30O4Pb", -142.6, 0.1),
    ("zinc peroxide", "[Zn+2].[O-][O-]", "ZnO2", +16.43, 0.01),
    ("ammonium dichromate", "[NH4+].[NH4+].[O-][Cr](=O)(=O)O[Cr](=O)(=O)[O-]",
     "H8N2Cr2O7", 0.0, 0.1),
    ("lead chromate", "[Pb+2].[O-][Cr](=O)(=O)[O-]", "PbCrO4", +7.43, 0.01),
    ("BNCP", f"[Co+3].N.N.N.N.{NITROTETRAZOLATE}.{NITROTETRAZOLATE}.{PERCHLORATE}",
     "C2ClCoH12N14O8", -8.8, 0.1),
    # The book prints this one to the nearest whole percent.
    ("calcium potassium styphnate", f"[Ca+2].[K+].[K+].{STYPHNATE}.{STYPHNATE}",
     "C12H2CaK2N6O16", -29.0, 0.5),
    # -- mercury and silver are left as the metal -------------------------------
    ("mercury fulminate", "[Hg+2].[C-]#[N+][O-].[C-]#[N+][O-]", "C2N2O2Hg", -11.2, 0.1),
    ("silver azide", f"[Ag+].{AZIDE}", "AgN3", 0.0, 0.1),
    ("silver acetylide", "[Ag]C#C[Ag]", "Ag2C2", -26.7, 0.1),
    # -- sulfur to SO2 ------------------------------------------------------------
    ("hexanitrodiphenyl sulfide",
     ("O=[N+]([O-])c1cc([N+](=O)[O-])c(Sc2c([N+](=O)[O-])cc([N+](=O)[O-])cc2[N+](=O)[O-])"
     "c([N+](=O)[O-])c1"), "C12H4N6O12S", -56.1, 0.1),
    ("hexanitrodiphenyl sulfone",
     ("O=[N+]([O-])c1cc([N+](=O)[O-])c(S(=O)(=O)c2c([N+](=O)[O-])cc([N+](=O)[O-])cc2"
     "[N+](=O)[O-])c([N+](=O)[O-])c1"), "C12H4N6O14S", -45.8, 0.1),
    # Table 21's element rows were computed with whole-number atomic masses:
    # 2 x 16 / 32 is exactly 100.0, where 32.06 gives 99.8. Carbon's -266.7
    # is 32/12 against 266.4 the same way.
    ("sulfur (Table 21)", "[S]", "S", -100.0, 0.25),
    # -- hydrates the book printed WITH their water ------------------------------
    ("lead styphnate monohydrate", f"[Pb+2].{STYPHNATE}.O", "C6H3N3O9Pb", -18.8, 0.1),
    ("lead acetylsalicylate monohydrate",
     f"[Pb+2].{ACETYLSALICYLATE}.{ACETYLSALICYLATE}.O", "C18H16O9Pb", -98.7, 0.1),
]

IDS = [row[0] for row in MEYER]


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, f"the fixture SMILES {smiles!r} does not parse"
    return mol


def _elements(formula: str) -> dict[str, int]:
    import re

    out: dict[str, int] = {}
    for element, count in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        out[element] = out.get(element, 0) + (int(count) if count else 1)
    return out


# ---------------------------------------------------------------------------
# 1  the book's own printed balances
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,smiles,formula,printed,tol", MEYER, ids=IDS)
def test_the_fixture_really_is_the_compound_the_book_names(name, smiles, formula, printed, tol):
    drawn = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol(smiles)))
    assert _elements(drawn.replace("+", "").replace("-", "")) == _elements(formula), drawn


@pytest.mark.parametrize("name,smiles,formula,printed,tol", MEYER, ids=IDS)
def test_meyers_printed_balance_reproduces(name, smiles, formula, printed, tol):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.applicable, E.refusal_text(result)
    assert result.to_full_oxidation == pytest.approx(printed, abs=tol)


#: Accepted on a source's STATEMENT, with no printed BALANCE using the
#: element; each is held to the book's numeric column instead
#: (`test_conklings_grams_of_fuel_per_gram_of_oxygen`).
STATED_ONLY = {"Si", "Zr", "P", "W"}


def test_every_accepted_element_is_pinned_by_a_printed_value():
    """An element in the table with no fixture would be a product nobody
    checked against a source -- exactly what this work exists not to ship."""
    pinned: set[str] = set()
    for _, smiles, *_ in MEYER + CONKLING_UNITS + BORATES:
        pinned.update(a.GetSymbol() for a in _mol(smiles).GetAtoms())
    pinned |= {"B", "Ti", "Mg", "Mo"}  # the mixtures below
    accepted = set(E._PRODUCTS) | set(E._HALOGENS)
    assert accepted - pinned - {"C", "H", "N"} == STATED_ONLY


def test_the_fixtures_cover_both_signs_and_every_kind_of_partner():
    values = [row[3] for row in MEYER]
    assert min(values) < -100 and max(values) > 50
    assert len(MEYER) == 35


# ---------------------------------------------------------------------------
# 1b  Conkling & Mocella's pyro valences, and the boron sources
# ---------------------------------------------------------------------------
#
# A pyro valence is the oxygen a formula needs in HALF-oxygens, so the book's
# numbers convert exactly: valence = -balance x M / 800, and for a mixture
# the valence of 100 g is -(mass-weighted balance) / 8.


def _valence(smiles: str) -> float:
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.applicable, E.refusal_text(result)
    return -result.to_full_oxidation * result.molecular_weight / 800


def _valence_per_100_g(*parts: tuple[float, str]) -> float:
    return -sum(grams / 100 * E.extended_oxygen_balance(_mol(s)).to_full_oxidation
                for grams, s in parts) / 8


#: Conkling & Mocella's printed net valences (Tables 2.6, 2.7 and 3.7): the
#: whole formula, or a polymer's repeat unit drawn as its monomer.
CONKLING_UNITS = [
    ("potassium perchlorate", f"[K+].{PERCHLORATE}", "KClO4", -8),
    ("potassium chlorate", f"[K+].{CHLORATE}", "KClO3", -6),
    ("potassium nitrate", f"[K+].{NITRATE}", "KNO3", -5),
    ("ammonium perchlorate", f"[NH4+].{PERCHLORATE}", "H4NClO4", -5),
    ("barium nitrate", f"[Ba+2].{NITRATE}.{NITRATE}", "BaN2O6", -10),
    ("barium chromate", "[Ba+2].[O-][Cr](=O)(=O)[O-]", "BaCrO4", -3),
    ("ammonium nitrate", f"[NH4+].{NITRATE}", "H4N2O3", -2),
    ("TNT", "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", "C7H5N3O6", +21),
    ("RDX", "O=[N+]([O-])N1CN(CN(C1)[N+](=O)[O-])[N+](=O)[O-]", "C3H6N6O6", +6),
    ("EGDN", "C(CO[N+](=O)[O-])O[N+](=O)[O-]", "C2H4N2O6", 0),
    ("nitroglycerine", "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]", "C3H5N3O9", -1),
    ("glucose", "OCC1OC(O)C(O)C(O)C1O", "C6H12O6", +24),
    ("PVC, per unit", "C=CCl", "C2H3Cl", +10),
    ("Viton, per unit", "C=C(F)F", "C2H2F2", +8),
]


@pytest.mark.parametrize("name,smiles,formula,printed", CONKLING_UNITS,
                         ids=[r[0] for r in CONKLING_UNITS])
def test_conklings_printed_net_valences_reproduce(name, smiles, formula, printed):
    drawn = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol(smiles)))
    assert _elements(drawn.replace("+", "").replace("-", "")) == _elements(formula)
    assert _valence(smiles) == pytest.approx(printed, abs=1e-6)


def test_conklings_titanium_mixtures():
    """KClO4/Ti 80/20 is printed at -2.95 per 100 g, and 60/35/5 with PMMA
    at +0.66 (p27-28)."""
    kp, ti, pmma = f"[K+].{PERCHLORATE}", "[Ti]", "CC(=C)C(=O)OC"
    assert _valence_per_100_g((80, kp), (20, ti)) == pytest.approx(-2.95, abs=0.005)
    assert _valence_per_100_g((60, kp), (35, ti), (5, pmma)) == pytest.approx(0.66, abs=0.005)


def test_conklings_magnesium_flare_and_its_stoichiometric_point():
    """45/35/20 Ba(NO3)2/Mg/PVC is printed as -1.72, +2.88 and +3.20 per
    100 g (p31); NaNO3/Mg is stoichiometric at 58.4/41.6, the book's
    percentages being rounded to 0.1."""
    assert _valence_per_100_g((45, f"[Ba+2].{NITRATE}.{NITRATE}")) == pytest.approx(-1.72, abs=0.005)
    assert _valence_per_100_g((35, "[Mg]")) == pytest.approx(2.88, abs=0.005)
    assert _valence_per_100_g((20, "C=CCl")) == pytest.approx(3.20, abs=0.005)
    assert _valence_per_100_g((58.4, f"[Na+].{NITRATE}"), (41.6, "[Mg]")) == pytest.approx(0, abs=0.02)


#: Klapötke, Chemistry of High-Energy Materials 4th ed., the borate esters
#: of its Introduction. -59.70 is the largest miss of any fixture here
#: (-59.79); leaving the boron out gives -51.2, so B2O3 is what was used.
BORATES = [
    ("tris(2-nitroethyl) borate", "B(OCC[N+](=O)[O-])(OCC[N+](=O)[O-])OCC[N+](=O)[O-]",
     "C6H12BN3O9", -59.70, 0.1),
    ("tris(2,2,2-trinitroethyl) borate",
     "B(OCC([N+](=O)[O-])([N+](=O)[O-])[N+](=O)[O-])(OCC([N+](=O)[O-])([N+](=O)[O-])"
     "[N+](=O)[O-])OCC([N+](=O)[O-])([N+](=O)[O-])[N+](=O)[O-]", "C6H6BN9O21", +13.07, 0.01),
]


@pytest.mark.parametrize("name,smiles,formula,printed,tol", BORATES, ids=[r[0] for r in BORATES])
def test_klapotkes_borates_reproduce_with_boron_to_B2O3(name, smiles, formula, printed, tol):
    drawn = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol(smiles)))
    assert _elements(drawn.replace("+", "").replace("-", "")) == _elements(formula)
    assert E.extended_oxygen_balance(_mol(smiles)).to_full_oxidation == pytest.approx(printed, abs=tol)


def test_the_patents_boron_igniter():
    """US 6,599,380 B2, Comparative Example 1: 26 parts boron, 74 potassium
    nitrate, -28.4%. Oxygen balance is per gram, so a mixture's is the
    mass-weighted sum of its components'."""
    boron = E.extended_oxygen_balance(_mol("[B]")).to_full_oxidation
    nitrate = E.extended_oxygen_balance(_mol(f"[K+].{NITRATE}")).to_full_oxidation
    assert 0.26 * boron + 0.74 * nitrate == pytest.approx(-28.4, abs=0.05)


#: Conkling & Mocella's Tables 3.4 and 3.5: "grams of fuel consumed per gram
#: of O" for the element burned to the product beside it. The number is the
#: book's own, so it pins the product's OXYGEN COUNT whether or not any
#: balance is printed. (Fe and Cu are in the table and left out: iron's
#: product depends on its role and copper's is printed as Cu2O/CuO.)
FUEL_PER_GRAM_OF_OXYGEN = [
    ("Al", "[Al]", 1.12), ("B", "[B]", 0.45), ("C", "[C]", 0.38), ("Mg", "[Mg]", 1.52),
    ("P (red)", "[P]", 0.78), ("Si", "[Si]", 0.88), ("S", "[S]", 1.00), ("Ti", "[Ti]", 1.50),
    ("W", "[W]", 3.83), ("Zn", "[Zn]", 4.09), ("Zr", "[Zr]", 2.85),
]


@pytest.mark.parametrize("name,smiles,printed", FUEL_PER_GRAM_OF_OXYGEN,
                         ids=[r[0] for r in FUEL_PER_GRAM_OF_OXYGEN])
def test_conklings_grams_of_fuel_per_gram_of_oxygen(name, smiles, printed):
    """Grams of fuel per gram of O is 100 / -balance. The book rounds to two
    places and used rounded atomic weights (phosphorus 31.0: 0.775 to 0.78
    where 30.97 gives 0.774), so the tolerance is one printed unit."""
    balance = E.extended_oxygen_balance(_mol(smiles)).to_full_oxidation
    assert 100 / -balance == pytest.approx(printed, abs=0.0075)


def test_conklings_molybdenum_delay_composition():
    """Exercise 4 (p29): BaCrO4/KClO4/Mo at 67.9/10.0/22.1 is the stoichiometric
    mixture with Mo to MoO3, a valence of +6 "obtained by analysis of the formula
    of the reaction product". Its valences sum to zero to the printed digits."""
    total = _valence_per_100_g(
        (67.9, "[Ba+2].[O-][Cr](=O)(=O)[O-]"), (10.0, f"[K+].{PERCHLORATE}"), (22.1, "[Mo]"))
    assert total == pytest.approx(0, abs=0.01)
    assert E._PRODUCTS["Mo"].product == "MoO3" and E._PRODUCTS["Mo"].valence == 6


def test_phosphorus_is_p2o5_in_both_books_that_say_so():
    """Conkling's Table 3.5 and Shimizu's "4 P + 5 O2 --> 2 P2O5" (p80)."""
    assert (E._PRODUCTS["P"].product, E._PRODUCTS["P"].valence) == ("P2O5", 5)
    # Phosphoric acid IS the fully burned product (P2O5 + 3 H2O), so it balances at zero.
    phosphoric = E.extended_oxygen_balance(_mol("OP(=O)(O)O")).to_full_oxidation
    assert phosphoric == pytest.approx(0.0, abs=1e-9)


def test_the_statement_only_elements_are_the_tables_rows():
    """Silicon and zirconium have no printed balance to test against, so they
    are held to Table 2.5's rows: +4 to SiO2, +4 to ZrO2."""
    assert (E._PRODUCTS["Si"].product, E._PRODUCTS["Si"].valence) == ("SiO2", 4)
    assert (E._PRODUCTS["Zr"].product, E._PRODUCTS["Zr"].valence) == ("ZrO2", 4)


# ---------------------------------------------------------------------------
# 2  where the book disagrees with itself, recorded rather than fitted
# ---------------------------------------------------------------------------


def test_picryl_chloride_is_the_one_chlorine_value_that_ignores_HCl():
    """The book prints -45.3% for picryl chloride (C6H2N3O6Cl). Its own
    stated rule -- chlorine to HCl, which five other printed values follow --
    gives -42.0; -45.2 is what leaving the chlorine as Cl2 gives. The code
    follows the stated rule."""
    mol = _mol("Clc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]")
    assert rdMolDescriptors.CalcMolFormula(mol) == "C6H2ClN3O6"
    assert E.extended_oxygen_balance(mol).to_full_oxidation == pytest.approx(-42.0, abs=0.05)


@pytest.mark.parametrize("name,anhydrous,water,printed", [
    ("barium chlorate monohydrate", f"[Ba+2].{CHLORATE}.{CHLORATE}", 1, +31.55),
    ("barium perchlorate trihydrate", f"[Ba+2].{PERCHLORATE}.{PERCHLORATE}", 3, +38.1),
])
def test_two_hydrates_were_printed_for_the_anhydrous_salt(name, anhydrous, water, printed):
    """The entries name a hydrate and print the anhydrous salt's balance,
    while lead styphnate's and lead acetylsalicylate's include their water
    (fixtures above). So the code balances what is DRAWN and says so."""
    dry = E.extended_oxygen_balance(_mol(anhydrous))
    wet = E.extended_oxygen_balance(_mol(anhydrous + ".O" * water))
    assert dry.to_full_oxidation == pytest.approx(printed, abs=0.05)
    assert wet.to_full_oxidation < dry.to_full_oxidation - 1.0
    assert wet.has_water and not dry.has_water


@pytest.mark.parametrize("name,smiles", [
    ("ferrocene, printed -223.6% (FeO)", "[CH-]1C=CC=C1.[CH-]1C=CC=C1.[Fe+2]"),
    ("iron acetylacetonate, printed 163.1% (Fe2O3)", ("CC(=O)/C=C(/C)[O-].CC(=O)/C=C(/C)[O-]."
     "CC(=O)/C=C(/C)[O-].[Fe+3]")),
])
def test_iron_is_refused_because_the_book_uses_two_oxides(name, smiles):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "FeO" in result.detail and "Fe2O3" in result.detail


#: Akhavan, The Chemistry of Explosives, 3rd ed. [source:akhavan2011], Table
#: 5.2 (p88): the only rows beyond C/H/N/O, as an independent check on the
#: products. Signs are the book's (its text layer drops the minus).
AKHAVAN = [
    ("silver azide", f"[Ag+].{AZIDE}", "AgN3", 0.00),
    ("lead azide", f"[Pb+2].{AZIDE}.{AZIDE}", "PbN6", -5.49),
    ("lead styphnate", f"[Pb+2].{STYPHNATE}.O", "PbC6H3N3O9", -18.79),
]


@pytest.mark.parametrize("name,smiles,formula,printed", AKHAVAN, ids=[r[0] for r in AKHAVAN])
def test_akhavans_table_agrees_on_silver_and_lead(name, smiles, formula, printed):
    drawn = rdMolDescriptors.CalcMolFormula(Chem.AddHs(_mol(smiles)))
    assert _elements(drawn.replace("+", "").replace("-", "")) == _elements(formula)
    assert E.extended_oxygen_balance(_mol(smiles)).to_full_oxidation == pytest.approx(
        printed, abs=0.01)


def test_mercury_is_where_the_two_books_differ_and_the_report_says_by_how_much():
    """Meyer: mercury fulminate -11.2%, mercury left as the metal. Akhavan:
    -16.86%, mercury to HgO. Meyer's is shipped; Akhavan's is printed in the
    result as a number, so neither reader is left with an unexplained gap."""
    fulminate = _mol("[Hg+2].[C-]#[N+][O-].[C-]#[N+][O-]")
    assert E.extended_oxygen_balance(fulminate).to_full_oxidation == pytest.approx(-11.2, abs=0.05)
    report = E.compute_oxygen_balance(fulminate, "uuid-1")
    balance = next(f for f in report.facts if f.units == "%")
    assert any("HgO" in line and "-16.9%" in line for line in balance.limitations)
    lead = E.compute_oxygen_balance(_mol(f"[Pb+2].{AZIDE}.{AZIDE}"), "uuid-1")
    assert not any("HgO" in line for f in lead.facts for line in f.limitations)


# ---------------------------------------------------------------------------
# 3  the chlorine rule
# ---------------------------------------------------------------------------


def test_a_chlorine_counts_the_same_whichever_partner_takes_it():
    """HCl spares one hydrogen's half-oxygen; KCl spares one potassium's. So
    potassium perchlorate and ammonium perchlorate need no order between
    hydrogen and metal, and neither does a salt holding both."""
    mol = _mol(f"[K+].[NH4+].{PERCHLORATE}.{NITRATE}")
    result = E.extended_oxygen_balance(mol)
    # O8 against H4 (2 O) + K (0.5 O) - Cl (0.5 O) = 2 O needed.
    assert result.oxygen_needed == pytest.approx(2.0)


def test_teflon_has_no_partner_for_its_fluorine_and_is_refused():
    """Conkling prints Teflon at -4 with its carbon left as C, a product the
    calculator's carbon row does not use; and no source says what fluorine
    with neither hydrogen nor metal becomes."""
    result = E.extended_oxygen_balance(_mol("FC(F)=C(F)F"))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "4 fluorine" in result.detail


@pytest.mark.parametrize("name,smiles", [
    ("phosphorus trichloride", "ClP(Cl)Cl"),
    ("molybdenum pentachloride", "Cl[Mo](Cl)(Cl)(Cl)Cl"),
    ("tungsten hexachloride", "Cl[W](Cl)(Cl)(Cl)(Cl)Cl"),
])
def test_a_halide_of_phosphorus_molybdenum_or_tungsten_is_refused(name, smiles):
    """No source says how many halogens their halides hold, so their oxide
    valence is not offered to a halogen."""
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "chlorine" in result.detail


def test_more_chlorine_than_anything_can_take_is_refused():
    """Carbon tetrachloride has no hydrogen or metal for its chlorine, and the
    source never says what the rest becomes."""
    result = E.extended_oxygen_balance(_mol("ClC(Cl)(Cl)Cl"))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "4 chlorine" in result.detail
    assert result.to_full_oxidation is None


def test_mercury_cannot_take_a_chlorine():
    """Left unoxidised, mercury has no valence to give a chlorine, so a bare
    mercury chloride has nothing to balance it against."""
    assert not E.extended_oxygen_balance(_mol("Cl[Hg]Cl")).applicable


# ---------------------------------------------------------------------------
# 4  what stays refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,smiles,element", [
    ("a bromide", "CBr", "Br"),
    ("an iodide", "CI", "I"),
    ("a copper salt", "[Cu+2].[O-][N+](=O)[O-].[O-][N+](=O)[O-]", "Cu"),
    ("copper azide", "[Cu+2].[N-]=[N+]=[N-].[N-]=[N+]=[N-]", "Cu"),
    ("manganese dioxide", "O=[Mn]=O", "Mn"),
])
def test_an_element_the_book_gives_no_product_for_is_refused_by_name(name, smiles, element):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert element in result.detail
    assert element in E.refusal_text(result)


# ---------------------------------------------------------------------------
# 5  C/H/N/O is unchanged
# ---------------------------------------------------------------------------

#: The calculator's two values for each Table 4.1 compound and three more,
#: recorded from master's module (fb65056a) before this work, by repr.
BEFORE = {
    "ammonium nitrate": (19.989255775020926, 19.989255775020926),
    "nitroglycerine": (3.5229099235968917, 24.660369465178242),
    "PETN": (-10.12225789615196, 15.18338684422794),
    "RDX": (-21.61023244506274, 0.0),
    "HMX": (-21.61023244506274, 0.0),
    "nitroguanidine": (-30.748830103104673, -15.374415051552337),
    "picric acid": (-45.39423144074307, -3.4918639569802363),
    "hexanitrostilbene": (-67.52074486042748, -17.768617068533548),
    "TNT": (-73.96579962312664, -24.655266541042216),
    "methane": (-398.9278813189553, -299.1959109892165),
    "ethanol": (-208.38307755757666, -138.9220517050511),
    "carbon": (-266.4224460910832, -133.2112230455416),
}
CHNO_SMILES = {row[0]: row[1] for row in TABLE_4_1} | {
    "methane": "C", "ethanol": "CCO", "carbon": "[C]"}


@pytest.mark.parametrize("name", list(BEFORE))
def test_a_chno_substance_gets_exactly_the_report_it_got_before(name):
    report = E.compute_oxygen_balance(_mol(CHNO_SMILES[name]), "uuid-1")
    assert report.provenance.method == "oxygen_balance_chno"
    values = tuple(f.value for f in report.facts if isinstance(f.value, float))
    assert values == BEFORE[name]


@pytest.mark.parametrize("name", list(BEFORE))
def test_the_extended_accounting_IS_klapotkes_on_chno(name):
    """Not what the calculator relies on -- C/H/N/O never reaches it -- but
    a valence table that disagreed with Klapötke on the four elements they
    share would be wrong about everything else too."""
    extended = E.extended_oxygen_balance(_mol(CHNO_SMILES[name])).to_full_oxidation
    assert extended == pytest.approx(BEFORE[name][0], abs=1e-9)


def test_kamlet_jacobs_and_formulations_still_refuse_what_they_cannot_model():
    """Both read `oxygen_balance`, which stays C/H/N/O: Kamlet-Jacobs is
    stated for C-H-N-O explosives in all four of its papers."""
    ap = _mol(f"[NH4+].{PERCHLORATE}")
    assert E.oxygen_balance(ap).refusal is E.OxygenBalanceRefusal.NOT_CHNO
    assert E.detonation(ap, 1.9, -70.7).refusal is E.DetonationRefusal.NOT_CHNO


# ---------------------------------------------------------------------------
# 6  the reported result
# ---------------------------------------------------------------------------


def test_the_report_names_each_product_it_assumed():
    report = E.compute_oxygen_balance(_mol(f"[K+].{PERCHLORATE}"), "uuid-1")
    assert report.cache_state is not CacheState.FAILED
    assert report.provenance.method == "oxygen_balance_extended"
    balance = next(f for f in report.facts if f.units == "%")
    assert balance.label == "Oxygen balance (CO₂ basis)"
    assert balance.display_value == "+46.2"
    assert any("Cl to HCl" in line for line in balance.limitations)
    assert any("K to K2O" in line for line in balance.limitations)
    assert any("K to K2O" in line for line in balance.evidence)


def test_the_co_basis_is_said_not_to_be_reported_rather_than_computed():
    report = E.compute_oxygen_balance(_mol("[S]"), "uuid-1")
    assert not any("CO basis" in f.label for f in report.facts)
    assert any("Only the CO2 basis" in line and "S" in line for line in report.limitations)


def test_a_hydrate_is_told_its_water_was_counted():
    dry = E.compute_oxygen_balance(_mol(f"[Ba+2].{CHLORATE}.{CHLORATE}"), "uuid-1")
    wet = E.compute_oxygen_balance(_mol(f"[Ba+2].{CHLORATE}.{CHLORATE}.O"), "uuid-1")
    assert not any("water" in line for line in dry.limitations)
    assert any("water" in line for line in wet.limitations)


def test_a_refusal_is_a_limit_named_by_its_code():
    report = E.compute_oxygen_balance(_mol("FC(F)F"), "uuid-1")
    assert report.cache_state is CacheState.FAILED
    assert report.inapplicable
    assert report.provenance.parameters["refusal"] == "UNCOVERED_ATOM"
    assert "F" in report.error
