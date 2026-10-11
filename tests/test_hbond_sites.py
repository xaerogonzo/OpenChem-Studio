"""The hydrogen-bond site table: which atoms, held to the count; which change with pH.

What is guarded:

* **the atoms are exactly the ones the H-Bond Donors and Acceptors counts count.** RDKit exposes no list of
  the atoms behind `CalcNumHBD` and `CalcNumHBA`, so the definitions are written out as patterns and held to
  the counts over a corpus, in the drawing's form AND with explicit hydrogens (an explicit hydrogen is a
  neighbour that changes what the acceptor pattern says about a hydroxyl, which is why the table matches on
  a hydrogen-free copy);
* **the roles are the chemistry a reader would check by eye**: an acid's hydroxyl donates and does not accept,
  an amide nitrogen donates and does not accept, a pyridine nitrogen accepts, an N-methyl pyrrole does not;
* **at a pH, each role is carried back to the atom it is about**, which the microspecies does not number like
  the drawing, so the same molecule written in two atom orders must give the same answer for the same atoms.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.chem import hbond_sites
from openchem.chem.hbond_sites import BOTH, compute_hbond_sites, counts, find_sites, sites_at_ph

_PANEL = Path(__file__).parent / "fixtures" / "census_panel.toml"

_CORPUS = re.findall(r'smiles\s*=\s*"([^"]+)"', _PANEL.read_text(encoding="utf-8")) + """
CCCCCCCC CC(C)Cc1ccc(cc1)C(C)C(=O)O CC(=O)Oc1ccccc1C(=O)O CC(=O)Nc1ccc(O)cc1 CN1C=NC2=C1C(=O)N(C)C(=O)N2C
c1ccc(cc1)-c1ccccc1 CC#CC C#CCC FC(F)(F)CC O=C(N)CCC NC(=O)NCC CNC(=O)OCC CC(=O)N(C)CC NC(=N)NCC CC(=[NH2+])NCC CS(=O)(=O)NCC
OCCOCCO CC(C)Oc1ccccc1 CCN(CC)CC c1ccccc1C(=O)NC O=C1CCCN1CC CCSCC CCS CCSSCC NCCN OCCO CC(C)CC(C)C
CN1CCC23C4C1CC5=C2C(=C(C=C5)O)OC3C(C=C4)O O=C(O)c1ccccc1O N#CCC [O-][N+](=O)CC [NH3+]CC(=O)[O-] CC(C)(C)OC(=O)NCC
c1ccc2c(c1)[nH]c1ccccc12 c1cc[nH]c1 c1ccncc1 c1cnc[nH]1 c1ccoc1 c1ccsc1 Cn1cccc1 CC(=O)[O-] C[N+](C)(C)C [NH4+] O S [OH-] CC(=O)O CCOC(=O)C
NC(=O)c1ccccc1 O=S(=O)(N)c1ccccc1 OP(=O)(O)O CP(=O)(O)O C=O C=NC CN=NC C[N+](=O)[O-] CC(=O)C=C
NS(=O)(=O)c1ccc(N)cc1 O=C1NC(=O)C=C1 Cc1nnc(o1)C c1nnn[nH]1 CCC(=O)N1CCNCC1
c1cncnc1 c1cnccn1 Cn1cnc2ccccc21 c1ccc2ncccc2c1 c1cc[n+]([O-])cc1 C[n+]1ccccc1 c1cnoc1 c1cscn1 c1cocn1 c1ncc2nc[nH]c2n1 Cn1ccnc1 c1ccc2[nH]ncc2c1
Cc1ccc2c(c1)n(C)c(=O)c1ccccc12 O=c1cc[nH]cc1 Nc1ncnc2[nH]cnc12 CN(C)c1ccccc1 CC1=NOC(=C1)C
O=S(C)C CS(=O)(=O)C COP(=O)(OC)OC C1CCOC1 C1COCCN1 C1CNCCN1 C1CCSC1 CC#N CNC#N N=C=O CC(=O)NN NN CON C[S-] C(=O)([O-])[O-]""".split()


def _sites(smiles: str) -> dict[int, hbond_sites.Site]:
    return find_sites(Chem.MolFromSmiles(smiles))


def _roles(smiles: str) -> dict[str, str]:
    """`{atom label: role}` using the symbol and 1-based number, e.g. {'O4': 'donor'}."""
    mol = Chem.MolFromSmiles(smiles)
    return {f"{mol.GetAtomWithIdx(i).GetSymbol()}{i + 1}": site.role for i, site in find_sites(mol).items()}


def _facts(report) -> dict:
    return {fact.label: fact for fact in report.facts}


# --- the definition, held to RDKit's own count ------------------------------------------------------------------


def test_the_corpus_is_large_enough_to_mean_something():
    assert len(_CORPUS) >= 120


@pytest.mark.parametrize("smiles", _CORPUS)
def test_the_listed_atoms_are_exactly_as_many_as_the_counts(smiles):
    drawing = Chem.MolFromSmiles(smiles)
    if drawing is None:
        pytest.skip("not a valid structure in this RDKit")
    want = (rdMolDescriptors.CalcNumHBD(drawing), rdMolDescriptors.CalcNumHBA(drawing))

    assert counts(find_sites(drawing)) == want, "on the drawing (implicit hydrogens)"
    assert counts(find_sites(Chem.AddHs(drawing))) == want, "with explicit hydrogens"


def test_the_same_atoms_are_listed_in_both_forms():
    drawing = Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")

    assert set(find_sites(Chem.AddHs(drawing))) == set(find_sites(drawing))


def test_the_counts_are_the_always_on_properties_values():
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    provider = RDKitDescriptorProvider()
    for smiles in ("CC(=O)Nc1ccc(O)cc1", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C", "NCCCC(=O)O"):
        mol = Chem.MolFromSmiles(smiles)
        values = {v.descriptor_id: v.value for v in provider.compute(mol, "u")}
        donors, acceptors = counts(find_sites(mol))

        assert (donors, acceptors) == (values["num_hbd"], values["num_hba"])


# --- the roles --------------------------------------------------------------------------------------------------------


def test_an_alcohol_oxygen_both_donates_and_accepts():
    assert _roles("CCO") == {"O3": BOTH}


def test_an_acids_hydroxyl_donates_and_does_not_accept_while_its_carbonyl_accepts():
    assert _roles("CC(=O)O") == {"O3": "acceptor", "O4": "donor"}


def test_an_amide_nitrogen_is_a_donor_and_not_an_acceptor():
    assert _roles("CC(=O)NC") == {"O3": "acceptor", "N4": "donor"}


def test_a_primary_amine_is_one_donor_atom_with_two_hydrogens_and_it_accepts_too():
    sites = _sites("CCN")
    (site,) = sites.values()

    assert (site.donor, site.acceptor, site.hydrogens) == (True, True, 2)
    assert counts(sites) == (1, 1), "atoms, not hydrogens"


def test_a_tertiary_amine_only_accepts():
    assert _roles("CCN(C)C") == {"N3": "acceptor"}


def test_ring_nitrogens_split_by_their_connections():
    assert _roles("c1ccncc1") == {"N4": "acceptor"}
    assert _roles("c1cc[nH]c1") == {"N4": "donor"}
    assert _roles("Cn1cccc1") == {}, "an N-methyl pyrrole has no lone pair to give"


def test_caffeine_has_three_acceptors_and_no_donor():
    assert counts(_sites("Cn1cnc2c1c(=O)n(C)c(=O)n2C")) == (0, 3)


def test_an_ammonium_donates_and_does_not_accept_and_a_carboxylate_accepts_twice():
    assert _roles("C[NH3+]") == {"N2": "donor"}
    assert _roles("CC(=O)[O-]") == {"O3": "acceptor", "O4": "acceptor"}


def test_a_molecule_with_neither_has_an_empty_table_that_still_answers():
    report = compute_hbond_sites(Chem.MolFromSmiles("CCCC"), "m", {})

    assert report.cache_state.name != "FAILED"
    assert [f.label for f in report.facts] == ["Donors", "Acceptors"]
    assert [f.display_value for f in report.facts] == ["0", "0"]


# --- the table ---------------------------------------------------------------------------------------------------------


def test_the_table_names_each_atom_by_its_canvas_number_with_its_role_and_hydrogens():
    facts = _facts(compute_hbond_sites(Chem.MolFromSmiles("NCCCC(=O)O"), "m", {}))

    assert facts["Donors"].display_value == "2" and facts["Acceptors"].display_value == "2"
    assert facts["N1"].display_value == "donor (2 H) and acceptor"
    assert facts["O6"].display_value == "acceptor"
    assert facts["O7"].display_value == "donor (1 H)"


def test_every_row_says_what_the_definition_is_and_is_not():
    report = compute_hbond_sites(Chem.MolFromSmiles("CC(=O)NC"), "m", {})

    for fact in report.facts:
        assert any("CAN take part" in line and "ATOMS" in line for line in fact.limitations)
    assert any("delocalised" in line for line in _facts(report)["N4"].limitations)


def test_by_default_there_is_no_ph_and_no_mention_of_one():
    report = compute_hbond_sites(Chem.MolFromSmiles("CC(=O)O"), "m", {})

    assert not any("pH" in fact.label or "pH" in fact.display_value for fact in report.facts)
    assert report.provenance.parameters["major_microspecies"] is False


# --- at a pH --------------------------------------------------------------------------------------------------------------


def test_acetic_acid_at_ph_74_loses_its_donor_and_its_hydroxyl_oxygen_becomes_an_acceptor():
    facts = _facts(compute_hbond_sites(Chem.MolFromSmiles("CC(=O)O"), "m", {"major_microspecies": True, "pH": 7.4}))

    assert (facts["Donors"].display_value, facts["Donors at pH 7.4"].display_value) == ("1", "0")
    assert (facts["Acceptors"].display_value, facts["Acceptors at pH 7.4"].display_value) == ("1", "2")
    assert facts["O4"].display_value == "acceptor at pH 7.4 (as drawn: donor (1 H))"
    assert facts["O3"].display_value == "acceptor (unchanged at pH 7.4)"


def test_gaba_at_ph_74_is_a_zwitterion_whose_ammonium_donates_three_hydrogens():
    facts = _facts(compute_hbond_sites(Chem.MolFromSmiles("NCCCC(=O)O"), "m", {"major_microspecies": True, "pH": 7.4}))

    assert facts["N1"].display_value == "donor (3 H) at pH 7.4 (as drawn: donor (2 H) and acceptor)"
    assert facts["O7"].display_value == "acceptor at pH 7.4 (as drawn: donor (1 H))"


def test_at_a_ph_where_nothing_ionises_every_row_is_unchanged():
    report = compute_hbond_sites(Chem.MolFromSmiles("CC(=O)O"), "m", {"major_microspecies": True, "pH": 1.0})

    assert all("unchanged at pH 1" in f.display_value for f in report.facts if f.label[0] in "NO")


def test_the_same_molecule_in_another_atom_order_gives_the_same_roles_on_the_same_atoms():
    """The microspecies is not numbered like the drawing, so this is what proves the roles go home."""

    def by_symbol_and_neighbours(smiles):
        mol = Chem.MolFromSmiles(smiles)
        at_ph = sites_at_ph(mol, 7.4)
        return sorted(
            (mol.GetAtomWithIdx(i).GetSymbol(), tuple(sorted(n.GetSymbol() for n in mol.GetAtomWithIdx(i).GetNeighbors())), s.role)
            for i, s in at_ph.items()
        )

    assert by_symbol_and_neighbours("OC(=O)c1ccc(N)cc1") == by_symbol_and_neighbours("Nc1ccc(cc1)C(=O)O")
    assert by_symbol_and_neighbours("OC(=O)c1ccc(N)cc1") == by_symbol_and_neighbours("c1cc(ccc1N)C(O)=O")


def test_the_role_lands_on_the_atom_that_ionised_not_a_lookalike():
    """4-aminobenzoic acid: the acid's OH is atom 1 here and the amine is atom 8."""
    mol = Chem.MolFromSmiles("OC(=O)c1ccc(N)cc1")
    at_ph = sites_at_ph(mol, 7.4)
    drawn = find_sites(mol)

    assert drawn[0].donor and not at_ph[0].donor and at_ph[0].acceptor
    assert at_ph[7].donor == drawn[7].donor and at_ph[7].hydrogens == drawn[7].hydrogens


def test_the_ph_is_clamped_and_recorded():
    report = compute_hbond_sites(Chem.MolFromSmiles("CC(=O)O"), "m", {"major_microspecies": True, "pH": 99})

    assert report.provenance.parameters["pH"] == 14.0 and "Donors at pH 14" in _facts(report)


def test_a_structure_that_cannot_be_built_at_the_ph_still_gets_its_drawn_table(monkeypatch):
    def refuse(_mol, _ph):
        raise ValueError("no state for this molecule")

    monkeypatch.setattr(hbond_sites, "sites_at_ph", refuse)

    report = compute_hbond_sites(Chem.MolFromSmiles("CC(=O)O"), "m", {"major_microspecies": True})
    facts = _facts(report)

    assert report.cache_state.name != "FAILED"
    assert facts["At pH 7.4"].display_value == "not available: no state for this molecule"
    assert facts["O4"].display_value == "donor (1 H)" and "Donors at pH 7.4" not in facts


# --- registration -----------------------------------------------------------------------------------------------------------


def test_it_is_registered_beside_the_curve_with_the_microspecies_pair_and_a_reason(qapp):
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry
    definition = registry.get("hbond_sites")
    ids = [d.calculator_id for d in registry.by_category("topology")]

    assert definition.category == "topology" and ids.index("hbond_sites") == ids.index("hbond_vs_ph") + 1
    assert [p.name for p in definition.parameters] == ["major_microspecies", "pH"]
    assert definition.support.stage.value == "limited" and definition.support.support_reason


def test_through_the_registry_a_salt_is_read_on_its_parent_and_named_by_the_drawings_numbers(qapp):
    """GABA hydrochloride: Cl is atom 1 of the drawing, so the amine is N2 and the acid's oxygens O7 and O8, not N1, O6, O7."""
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry

    result = registry.compute("hbond_sites", Chem.MolFromSmiles("Cl.NCCCC(=O)O"), "m", {})

    assert {f.label for f in result.facts} >= {"N2", "O7", "O8"}
    assert not {"N1", "O6"} & {f.label for f in result.facts}


def test_a_microspecies_whose_atoms_are_numbered_differently_still_puts_each_role_on_its_own_atom(monkeypatch):
    """`dominant_microspecies` happens to hand its atoms back in the drawing's order today (measured on a dozen
    acids and amines), so the correspondence step is invisible. This renumbers them on purpose, which is
    what a change in that function would do, and the roles must still land where the unshuffled ones did."""
    from openchem.chem import pka_providers

    mol = Chem.MolFromSmiles("OC(=O)c1ccc(N)cc1")
    want = {i: (s.donor, s.acceptor, s.hydrogens) for i, s in sites_at_ph(mol, 7.4).items()}
    real = pka_providers.dominant_microspecies

    def shuffled(molecule, ph):
        species = real(molecule, ph)
        order = list(reversed(range(species.mol.GetNumAtoms())))
        return pka_providers.Microspecies(
            mol=Chem.RenumberAtoms(species.mol, order), formal_charge=species.formal_charge
        )

    monkeypatch.setattr(pka_providers, "dominant_microspecies", shuffled)

    got = {i: (s.donor, s.acceptor, s.hydrogens) for i, s in sites_at_ph(mol, 7.4).items()}

    assert got == want and want, "a role on the wrong atom is the defect this step exists to prevent"


def test_an_atom_that_is_a_site_only_at_the_ph_still_gets_a_row_that_says_it_was_not_one(monkeypatch):
    mol = Chem.MolFromSmiles("CCC")
    monkeypatch.setattr(
        hbond_sites, "sites_at_ph", lambda _mol, _ph: {1: hbond_sites.Site(atom=1, donor=False, acceptor=True, hydrogens=0)}
    )

    facts = _facts(compute_hbond_sites(mol, "m", {"major_microspecies": True}))

    assert facts["C2"].display_value == "acceptor at pH 7.4 (as drawn: none)"
