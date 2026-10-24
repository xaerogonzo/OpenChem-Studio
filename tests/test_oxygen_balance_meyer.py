"""Oxygen balance beyond C/H/N/O, held to Meyer's own printed balances.

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
    result = E.meyer_oxygen_balance(_mol(smiles))
    assert result.applicable, E.refusal_text(result)
    assert result.to_full_oxidation == pytest.approx(printed, abs=tol)


def test_every_accepted_element_is_pinned_by_a_printed_value():
    """An element in the table with no fixture would be a product nobody
    checked against the book -- exactly what this work exists not to ship."""
    pinned: set[str] = set()
    for _, smiles, *_ in MEYER:
        pinned.update(a.GetSymbol() for a in _mol(smiles).GetAtoms())
    accepted = set(E._MEYER_ELEMENTS) | {"Cl"}
    assert accepted - pinned - {"C", "H", "N"} == set()


def test_the_fixtures_cover_both_signs_and_every_kind_of_partner():
    values = [row[3] for row in MEYER]
    assert min(values) < -100 and max(values) > 50
    assert len(MEYER) == 35


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
    assert E.meyer_oxygen_balance(mol).to_full_oxidation == pytest.approx(-42.0, abs=0.05)


@pytest.mark.parametrize("name,anhydrous,water,printed", [
    ("barium chlorate monohydrate", f"[Ba+2].{CHLORATE}.{CHLORATE}", 1, +31.55),
    ("barium perchlorate trihydrate", f"[Ba+2].{PERCHLORATE}.{PERCHLORATE}", 3, +38.1),
])
def test_two_hydrates_were_printed_for_the_anhydrous_salt(name, anhydrous, water, printed):
    """The entries name a hydrate and print the anhydrous salt's balance,
    while lead styphnate's and lead acetylsalicylate's include their water
    (fixtures above). So the code balances what is DRAWN and says so."""
    dry = E.meyer_oxygen_balance(_mol(anhydrous))
    wet = E.meyer_oxygen_balance(_mol(anhydrous + ".O" * water))
    assert dry.to_full_oxidation == pytest.approx(printed, abs=0.05)
    assert wet.to_full_oxidation < dry.to_full_oxidation - 1.0
    assert wet.has_water and not dry.has_water


@pytest.mark.parametrize("name,smiles", [
    ("ferrocene, printed -223.6% (FeO)", "[CH-]1C=CC=C1.[CH-]1C=CC=C1.[Fe+2]"),
    ("iron acetylacetonate, printed 163.1% (Fe2O3)", ("CC(=O)/C=C(/C)[O-].CC(=O)/C=C(/C)[O-]."
     "CC(=O)/C=C(/C)[O-].[Fe+3]")),
])
def test_iron_is_refused_because_the_book_uses_two_oxides(name, smiles):
    result = E.meyer_oxygen_balance(_mol(smiles))
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
    assert E.meyer_oxygen_balance(_mol(smiles)).to_full_oxidation == pytest.approx(
        printed, abs=0.01)


def test_mercury_is_where_the_two_books_differ_and_the_report_says_by_how_much():
    """Meyer: mercury fulminate -11.2%, mercury left as the metal. Akhavan:
    -16.86%, mercury to HgO. Meyer's is shipped; Akhavan's is printed in the
    result as a number, so neither reader is left with an unexplained gap."""
    fulminate = _mol("[Hg+2].[C-]#[N+][O-].[C-]#[N+][O-]")
    assert E.meyer_oxygen_balance(fulminate).to_full_oxidation == pytest.approx(-11.2, abs=0.05)
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
    result = E.meyer_oxygen_balance(mol)
    # O8 against H4 (2 O) + K (0.5 O) - Cl (0.5 O) = 2 O needed.
    assert result.oxygen_needed == pytest.approx(2.0)


def test_more_chlorine_than_anything_can_take_is_refused():
    """Carbon tetrachloride has no hydrogen or metal for its chlorine, and the
    source never says what the rest becomes."""
    result = E.meyer_oxygen_balance(_mol("ClC(Cl)(Cl)Cl"))
    assert result.refusal is E.OxygenBalanceRefusal.UNCOVERED_ATOM
    assert "4 chlorine" in result.detail
    assert result.to_full_oxidation is None


def test_mercury_cannot_take_a_chlorine():
    """Left unoxidised, mercury has no valence to give a chlorine, so a bare
    mercury chloride has nothing to balance it against."""
    assert not E.meyer_oxygen_balance(_mol("Cl[Hg]Cl")).applicable


# ---------------------------------------------------------------------------
# 4  what stays refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,smiles,element", [
    ("a fluoride", "FC(F)F", "F"),
    ("a bromide", "CBr", "Br"),
    ("a boron ester", "B(OC)(OC)OC", "B"),
    ("a phosphate", "OP(=O)(O)O", "P"),
    ("magnesium", "[Mg]", "Mg"),
    ("copper azide", "[Cu+2].[N-]=[N+]=[N-].[N-]=[N+]=[N-]", "Cu"),
])
def test_an_element_the_book_gives_no_product_for_is_refused_by_name(name, smiles, element):
    result = E.meyer_oxygen_balance(_mol(smiles))
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
    extended = E.meyer_oxygen_balance(_mol(CHNO_SMILES[name])).to_full_oxidation
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
    assert report.provenance.method == "oxygen_balance_meyer"
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
