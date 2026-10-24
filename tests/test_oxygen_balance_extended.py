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
    for _, smiles, *_ in MEYER + CONKLING_UNITS + BORATES + SHREEVE:
        pinned.update(a.GetSymbol() for a in _mol(smiles).GetAtoms())
    pinned |= {"B", "Ti", "Mg", "Mo", "Fe", "Cu", "Ce", "Br"}  # the mixtures, charge-matched and Tsang/Lease tests below
    accepted = set(E._PRODUCTS) | set(E._HALOGENS) | set(E._CHARGE_MATCHED)
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


#: He, Hooper & Shreeve, Inorg. Chem. 2016, 55, 12844, Table 2: iodine-rich
#: imidazolium iodates (13, 14, 17, 18) and periodates (19, 22, 23), with the
#: formula the paper prints for each and its printed balance. **THAT BALANCE IS
#: THE CO BASIS** -- "OB = 1600(c - b/2 - a)/MW", carbon taking ONE oxygen --
#: so the test adds a x 1600/MW to the CO2 figure this module returns. What it
#: pins is that iodine asks for no oxygen. The paper prints whole numbers.
SHREEVE = [
    ("13 triiodo iodate", "Cn1c(I)c(I)[n+](C)c1I.[O-]I(=O)=O", "C5H6I4N2O3", -12),
    ("14 diiodo iodate", "Cn1c(I)c(I)[n+](C)c1.[O-]I(=O)=O", "C5H7I3N2O3", -17),
    ("17 amino iodate", "Cn1c[n+](N)c(I)c1I.[O-]I(=O)=O", "C4H6I3N3O3", -12),
    ("18 diamino iodate", "Nn1c[n+](N)c(I)c1I.[O-]I(=O)=O", "C3H5I3N4O3", -8),
    ("19 dimethyl periodate", "Cn1c[n+](C)c(I)c1I.[O-]I(=O)(=O)=O", "C5H7I3N2O4", -13),
    ("22 amino periodate", "Cn1c[n+](N)c(I)c1I.[O-]I(=O)(=O)=O", "C4H6I3N3O4", -9),
    ("23 diamino periodate", "Nn1c[n+](N)c(I)c1I.[O-]I(=O)(=O)=O", "C3H5I3N4O4", -4),
]


@pytest.mark.parametrize("name,smiles,formula,printed", SHREEVE, ids=[r[0] for r in SHREEVE])
def test_shreeves_iodine_rich_salts_with_iodine_left_as_I2(name, smiles, formula, printed):
    mol = _mol(smiles)
    assert _elements(rdMolDescriptors.CalcMolFormula(Chem.AddHs(mol)).replace("+", "").replace("-", "")) \
        == _elements(formula)
    result = E.extended_oxygen_balance(mol)
    assert result.applicable, E.refusal_text(result)
    co_basis = result.to_full_oxidation + result.count("C") * 1600 / result.molecular_weight
    assert co_basis == pytest.approx(printed, abs=0.5)
    # and the paper's own closed form, term for term: iodine does not appear in it
    a, b, c = result.count("C"), result.count("H"), result.count("O")
    assert co_basis == pytest.approx(1600 * (c - b / 2 - a) / result.molecular_weight, abs=1e-9)


def test_iodine_takes_no_hydrogen_unlike_chlorine():
    """Iodoform is CHI3: iodine left as I2 asks for nothing, so only the carbon
    and hydrogen are counted. Chloroform's chlorine takes the hydrogen as HCl
    and then has two more with nothing to take them, so it is refused."""
    iodoform = E.extended_oxygen_balance(_mol("IC(I)I"))
    assert iodoform.applicable and iodoform.oxygen_needed == pytest.approx(2.5)
    assert not E.extended_oxygen_balance(_mol("ClC(Cl)Cl")).applicable


# ---------------------------------------------------------------------------
# 1b2 cerium: ceric ammonium nitrate and stearic acid (Dufter-Muenster thesis)
# ---------------------------------------------------------------------------

CAN = "[NH4+].[NH4+].[Ce+4]" + (".[O-][N+](=O)[O-]" * 6)
STEARIC_ACID = "CCCCCCCCCCCCCCCCCC(=O)O"


def test_ceric_ammonium_nitrate_is_35_02_with_cerium_to_ceO2():
    """'Ceric ammonium nitrate (CAN) has an oxygen balance of 35.02 % assuming
    combustion to cerium(IV) oxide.' Cerium is not in the C/H/N/O function, so
    this is the extended accounting."""
    result = E.extended_oxygen_balance(_mol(CAN))
    assert result.applicable, E.refusal_text(result)
    assert result.to_full_oxidation == pytest.approx(35.02, abs=0.01)
    assert ("Ce", "CeO2") in result.products


def test_the_theses_stearic_acid_and_its_15_to_1_mixture():
    """Stearic acid -292.46% (a C/H/O check of the same passage), and a 15:1
    CAN/stearic acid mixture at 14.55%: the mass-weighted sum, since a balance
    is per gram."""
    stearic = E.oxygen_balance(_mol(STEARIC_ACID)).to_carbon_dioxide
    assert stearic == pytest.approx(-292.46, abs=0.01)
    can = E.extended_oxygen_balance(_mol(CAN)).to_full_oxidation
    assert (15 * can + stearic) / 16 == pytest.approx(14.55, abs=0.01)


# ---------------------------------------------------------------------------
# 1c  Persson, Holmberg & Lee's closed form (Eq. 4.43), term for term
# ---------------------------------------------------------------------------

#: Eq. 4.43, "32 (3/4 al + 3/4 b + 1 c + 1/2 ca - 1/4 cl - 1/4 f + 1/4 h + 1/4 k
#: + 0 n + 1/4 na - 1/2 o) / M", read from the page image. Atom counts times
#: these, in units of 32 g of oxygen.
PERSSON_COEFFICIENTS = {
    "Al": 0.75, "B": 0.75, "C": 1.0, "Ca": 0.5, "Cl": -0.25, "F": -0.25,
    "H": 0.25, "K": 0.25, "N": 0.0, "Na": 0.25, "O": -0.5,
}


def _persson(smiles: str) -> float:
    mol = Chem.AddHs(_mol(smiles))
    mass = sum(a.GetMass() for a in mol.GetAtoms())
    total = sum(PERSSON_COEFFICIENTS[a.GetSymbol()] for a in mol.GetAtoms())
    return -32 * total / mass * 100


#: Every one meets the book's assumption that "there is enough hydrogen ... to
#: bind chlorine and fluorine", or has none of either.
PERSSON_CASES = [
    ("TNT (printed -73.98)", "Cc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]"),
    ("nitroglycerine (printed +3.52)", "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]"),
    ("ammonium nitrate", f"[NH4+].{NITRATE}"),
    ("ammonium perchlorate", f"[NH4+].{PERCHLORATE}"),
    ("aluminum", "[Al]"),
    ("boron", "[B]"),
    ("tris(2-nitroethyl) borate", "B(OCC[N+](=O)[O-])(OCC[N+](=O)[O-])OCC[N+](=O)[O-]"),
    ("sodium nitrate", f"[Na+].{NITRATE}"),
    ("potassium nitrate", f"[K+].{NITRATE}"),
    ("potassium perchlorate", f"[K+].{PERCHLORATE}"),
    ("calcium nitrate", f"[Ca+2].{NITRATE}.{NITRATE}"),
    ("chlorobenzene", "Clc1ccccc1"),
    ("PVC unit", "C=CCl"),
    ("Viton unit", "C=C(F)F"),
    ("fluorobenzene", "Fc1ccccc1"),
    ("guanidinium perchlorate", f"NC(N)=[NH2+].{PERCHLORATE}"),
]


@pytest.mark.parametrize("name,smiles", PERSSON_CASES, ids=[r[0] for r in PERSSON_CASES])
def test_persson_equation_4_43_agrees_with_the_calculator_term_for_term(name, smiles):
    ours = E.extended_oxygen_balance(_mol(smiles))
    assert ours.applicable, E.refusal_text(ours)
    assert ours.to_full_oxidation == pytest.approx(_persson(smiles), abs=1e-6)


def test_persson_prints_tnt_and_nitroglycerine():
    """Section 4.4 (p110-111): 'These have oxygen balances -73.98%, +3.52%,
    and -0.04%' for TNT, nitroglycerin and ANFO (the last a mixture)."""
    # TNT is 0.014 off the printed digits: Persson's own table uses M = 227.14
    # where this module computes 227.13, and -73.96 is what that mass gives.
    assert _persson(PERSSON_CASES[0][1]) == pytest.approx(-73.98, abs=0.03)
    assert _persson(PERSSON_CASES[1][1]) == pytest.approx(3.52, abs=0.01)


def test_persson_assumes_hydrogen_for_its_halogens_and_the_calculator_refuses_without():
    """The closed form gives Teflon a number by assuming hydrogen that is not
    there; no source says what the fluorine becomes without it, so the
    calculator refuses."""
    assert E.extended_oxygen_balance(_mol("FC(F)=C(F)F")).refusal is not None


# ---------------------------------------------------------------------------
# 1d  the Cl2 figure the Encyclopedia prints, shown beside the HCl answer
# ---------------------------------------------------------------------------

#: Klapötke, Energetic Materials Encyclopedia 2nd ed.: the entries whose
#: formula carries a hydrogen-taken chlorine. The value is what the
#: Encyclopedia prints, and it is the Cl2 figure (HCl gives Meyer's).
CL2_ENTRIES = [
    ("guanidinium perchlorate", f"NC(N)=[NH2+].{PERCHLORATE}", -10.0, -5.0),
    ("hydrazinium perchlorate", f"N[NH3+].{PERCHLORATE}", +18.1, +24.1),
    ("trinitrochlorobenzene", "Clc1c(cc(cc1[N+](=O)[O-])[N+](=O)[O-])[N+](=O)[O-]", -45.24, -42.0),
]


@pytest.mark.parametrize("name,smiles,cl2,hcl", CL2_ENTRIES, ids=[r[0] for r in CL2_ENTRIES])
def test_the_encyclopedias_cl2_figure_is_reported_beside_the_hcl_answer(name, smiles, cl2, hcl):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.to_full_oxidation == pytest.approx(hcl, abs=0.1)
    assert result.chlorine_as_cl2 == pytest.approx(cl2, abs=0.05)
    report = E.compute_oxygen_balance(_mol(smiles), "uuid-1")
    balance = next(f for f in report.facts if f.units == "%")
    assert any("Cl2" in line and f"{cl2:+.1f}" in line for line in balance.limitations)


@pytest.mark.parametrize("name,smiles", [
    ("potassium perchlorate", f"[K+].{PERCHLORATE}"),
    ("sodium chlorate", f"[Na+].{CHLORATE}"),
    ("barium perchlorate", f"[Ba+2].{PERCHLORATE}.{PERCHLORATE}"),
])
def test_a_chlorine_taken_by_a_metal_has_no_cl2_alternative(name, smiles):
    """KCl is the product whichever way it is written, and the Encyclopedia's
    potassium and sodium perchlorate values (+46.2, +52.3) equal ours."""
    assert E.extended_oxygen_balance(_mol(smiles)).chlorine_as_cl2 is None


# ---------------------------------------------------------------------------
# 2  where the book disagrees with itself, recorded rather than fitted
# ---------------------------------------------------------------------------


def test_picryl_chloride_is_the_one_chlorine_value_that_ignores_HCl():
    """The book prints -45.3% for picryl chloride (C6H2N3O6Cl). Its own
    stated rule -- chlorine to HCl, which five other printed values follow --
    gives -42.0; -45.2 is what leaving the chlorine as Cl2 gives, and the
    Encyclopedia prints that Cl2 figure too (-45.24). The code follows the
    stated rule and reports the Cl2 figure beside it."""
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


# ---------------------------------------------------------------------------
# 2b  iron and copper: the oxide of the drawn charge
# ---------------------------------------------------------------------------
#
# No source states this as a rule. Every value any of them prints follows it:
# Meyer's two iron values are iron(II) to FeO and iron(III) to Fe2O3 to the
# printed digit, and Conkling prints a figure for each of copper's two oxides.

FERROCENE = "[CH-]1C=CC=C1.[CH-]1C=CC=C1.[Fe+2]"
FE_ACAC = "CC(=O)/C=C(/C)[O-].CC(=O)/C=C(/C)[O-].CC(=O)/C=C(/C)[O-].[Fe+3]"


def test_meyers_ferrocene_is_iron_II_to_FeO():
    """Printed -223.6% for C10H10Fe."""
    result = E.extended_oxygen_balance(_mol(FERROCENE))
    assert result.to_full_oxidation == pytest.approx(-223.6, abs=0.05)
    assert result.charge_products == (("Fe", "FeO"),)


def test_meyers_iron_acetylacetonate_is_iron_III_to_Fe2O3():
    """Printed '+163.1%' for C15H21O6Fe. The sign is a misprint -- six oxygens
    in 353 g/mol cannot burn 36 oxygens' worth of carbon and hydrogen to
    anything positive -- and the MAGNITUDE is Fe2O3 to the digit, where FeO
    gives 160.8. This used to be filed as the book disagreeing with itself:
    it was the iron's oxidation state."""
    result = E.extended_oxygen_balance(_mol(FE_ACAC))
    assert result.to_full_oxidation == pytest.approx(-163.1, abs=0.05)
    assert result.charge_products == (("Fe", "Fe2O3"),)


@pytest.mark.parametrize("name,smiles,printed", [
    ("copper(I) to Cu2O", "[Cu+]", 7.94),
    ("copper(II) to CuO", "[Cu+2]", 3.97),
])
def test_conklings_two_copper_oxides_are_the_two_copper_states(name, smiles, printed):
    """Table 3.4 prints 'Cu2O/CuO' with '7.94/3.97' grams of fuel per gram of O."""
    balance = E.extended_oxygen_balance(_mol(smiles)).to_full_oxidation
    assert 100 / -balance == pytest.approx(printed, abs=0.01)


def test_the_other_oxide_is_reported_beside_the_answer():
    ferrocene = E.extended_oxygen_balance(_mol(FERROCENE))
    assert [(e, p) for e, p, _ in ferrocene.alternatives] == [("Fe", "Fe2O3")]
    assert ferrocene.alternatives[0][2] == pytest.approx(-227.9, abs=0.05)
    report = E.compute_oxygen_balance(_mol(FERROCENE), "uuid-1")
    balance = next(f for f in report.facts if f.units == "%")
    assert any("Fe2O3" in line and "-227.9" in line for line in balance.limitations)
    assert any("FeO" in line for line in balance.limitations)


@pytest.mark.parametrize("name,smiles,fragment", [
    ("iron drawn with no charge", "[Fe]", "no charge"),
    ("iron(IV)", "[Fe+4]", "+4"),
    ("copper drawn with no charge", "[Cu]", "no charge"),
    ("copper(III)", "[Cu+3]", "+3"),
])
def test_a_charge_the_sources_have_no_oxide_for_is_refused_by_name(name, smiles, fragment):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert fragment in result.detail
    assert "Fe(II)" in result.detail or "Cu(I)" in result.detail


@pytest.mark.parametrize("smiles,metal", [
    ("[Fe+3].[Cl-].[Cl-].[Cl-]", "Fe"),
    ("[Fe+2].[Cl-].[Cl-]", "Fe"),
    ("[Cu+2].[Cl-].[Cl-]", "Cu"),
    ("[Cu+].[Cl-]", "Cu"),
])
def test_a_charge_matched_metal_takes_its_chlorides_like_any_other_metal(smiles, metal):
    """FeCl3 balances at zero: the metal's valence is the chlorine count."""
    assert E.extended_oxygen_balance(_mol(smiles)).to_full_oxidation == pytest.approx(0.0, abs=1e-9)


def test_a_metal_with_more_chlorine_than_its_charge_holds_is_refused():
    assert not E.extended_oxygen_balance(_mol("[Fe+2].[Cl-].[Cl-].[Cl-]")).applicable


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
    ("a selenium compound", "C[Se]C", "Se"),
    ("a manganese salt", "[Mn+2].[O-][N+](=O)[O-].[O-][N+](=O)[O-]", "Mn"),
    ("manganese dioxide", "O=[Mn]=O", "Mn"),
])
def test_an_element_the_book_gives_no_product_for_is_refused_by_name(name, smiles, element):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert element in result.detail
    assert element in E.refusal_text(result)


# ---------------------------------------------------------------------------
# 4b  bromine: HBr, from Tsang & Domalski (1974) and Lease et al. (2023)
# ---------------------------------------------------------------------------
#
# Tsang & Domalski write the product as HBr and print propargyl bromide; Lease's
# Table 3 prints three brominated PETN derivatives. Neither prints a metal
# bromide, nor any bromine compound on a metal.

#: (name, SMILES, printed balance), Tsang & Domalski's Table 4 (p14), whose
#: formula sets the halogen to HX and sparing half an oxygen per halogen.
TSANG_HALOGENS = [
    ("propargyl bromide", "C#CCBr", -94.1),
    ("vinyl chloride", "C=CCl", -128.0),
    ("ethyl chloride", "CCCl", -148.8),
]


@pytest.mark.parametrize("name,smiles,printed", TSANG_HALOGENS, ids=[r[0] for r in TSANG_HALOGENS])
def test_tsangs_halogen_rows_reproduce(name, smiles, printed):
    result = E.extended_oxygen_balance(_mol(smiles))
    assert result.applicable, E.refusal_text(result)
    assert result.to_full_oxidation == pytest.approx(printed, abs=0.06)


def _petn_derivative(n: int, halogen: str) -> str:
    """PETN with n of its four nitrate esters replaced by the halogen."""
    arms = ["CO[N+](=O)[O-]"] * (4 - n) + [f"C{halogen}"] * n
    return "C(" + ")(".join(arms[:3]) + ")" + arms[3]


@pytest.mark.parametrize("n,printed", [(1, -21.6), (2, -32.0), (3, -41.4)])
def test_leases_brominated_petn_derivatives_reproduce_with_hbr(n, printed):
    """Table 3 of Lease et al. The paper gives no atomic masses and the values
    sit 0.0, 0.2 and 0.3 from the arithmetic, so the tolerance is 0.35. Br2
    left over would be 2.4, 4.4 and 6.2 out, which is what tells them apart."""
    result = E.extended_oxygen_balance(_mol(_petn_derivative(n, "Br")))
    assert result.applicable, E.refusal_text(result)
    assert result.to_full_oxidation == pytest.approx(printed, abs=0.35)
    # what Br2 would have given, so the convention test has a witness
    br2 = result.to_full_oxidation - 1600 * 0.5 * n / result.molecular_weight
    assert abs(br2 - printed) > 2.0


@pytest.mark.parametrize("bromo,chloro", [
    ("CBr", "CCl"),
    ("OC(=O)c1ccccc1Br", "OC(=O)c1ccccc1Cl"),
    ("[NH4+].[Br-]", "[NH4+].[Cl-]"),
    ("[Na+].[Br-]", "[Na+].[Cl-]"),
])
def test_bromine_is_counted_as_chlorine_is_with_its_own_mass(bromo, chloro):
    """Same accounting, so the OXYGEN NEEDED is identical; only the molar mass
    differs. Checked by rescaling the two balances to the same denominator."""
    b = E.extended_oxygen_balance(_mol(bromo))
    c = E.extended_oxygen_balance(_mol(chloro))
    assert b.applicable and c.applicable
    assert b.oxygen_needed == pytest.approx(c.oxygen_needed)
    assert b.to_full_oxidation * b.molecular_weight == pytest.approx(
        c.to_full_oxidation * c.molecular_weight)


def test_a_bromine_a_metal_takes_is_said_to_follow_the_chlorides():
    """No source prints a metal bromide, so the result says it is counted like
    the chlorides; a bromine on carbon says nothing of the kind."""
    metal = E.extended_oxygen_balance(_mol("[Na+].[Br-]"))
    assert metal.to_full_oxidation == pytest.approx(0.0, abs=1e-9)
    assert metal.bromine_on_metal == 1
    assert E.extended_oxygen_balance(_mol("CBr")).bromine_on_metal == 0
    report = E.compute_oxygen_balance(_mol("[Na+].[Br-]"), "uuid-1")
    fact = next(f for f in report.facts if f.units == "%")
    assert any("metal as its bromide" in line for line in fact.limitations)
    carbon = E.compute_oxygen_balance(_mol("CCBr"), "uuid-2")
    cfact = next(f for f in carbon.facts if f.units == "%")
    assert not any("metal as its bromide" in line for line in cfact.limitations)


def test_bromine_beyond_what_hydrogen_and_metals_can_take_is_refused():
    """Bromoform has one hydrogen for three bromines; neither source says what
    the rest becomes."""
    result = E.extended_oxygen_balance(_mol("C(Br)(Br)Br"))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "3 bromine" in result.detail


def test_the_result_names_tsang_and_lease_as_what_pins_bromine():
    report = E.compute_oxygen_balance(_mol("CCBr"), "uuid-1")
    fact = next(f for f in report.facts if f.units == "%")
    text = " ".join(fact.limitations)
    assert "Tsang" in text and "Lease" in text and "ESTIMATE" not in text


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
