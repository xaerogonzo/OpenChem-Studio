"""Track 3: the dominant state at a pH, carried onto a conformer.

`benchmarks/charges/protonation/preregistration.md` is the contract. There is NO oracle for the
charges; what is tested here is which atom is which, which proton moved, and that nothing except an
added hydrogen moves in space -- asserted as byte equality, never a tolerance.
"""

from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import protonation_geometry as pg


def conformer_for(smiles: str, seed: int = 20260915) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def positions(mol: Chem.Mol) -> np.ndarray:
    return np.array(mol.GetConformer().GetPositions(), dtype=float)


# --- the three cases the pre-registration names ---------------------------------------------------


def test_acetic_acid_loses_one_proton_and_no_atom_moves():
    source = conformer_for("CC(=O)O")
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    assert Chem.GetFormalCharge(result.mol) == -1
    assert len(result.site_changes) == 1
    change = result.site_changes[0]
    assert (change.delta_h, change.delta_charge) == (-1, -1)
    assert source.GetAtomWithIdx(change.heavy_atom).GetSymbol() == "O"
    assert source.GetAtomWithIdx(change.removed_hydrogen).GetSymbol() == "H"
    assert result.placed_hydrogens == ()
    # Every surviving atom keeps its coordinates BIT for bit.
    kept = [index for index in range(source.GetNumAtoms()) if index != change.removed_hydrogen]
    assert np.array_equal(positions(result.mol), positions(source)[kept])


def test_methylamine_gains_a_proton_that_is_a_real_atom_with_coordinates():
    source = conformer_for("CN")
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    assert Chem.GetFormalCharge(result.mol) == 1
    assert [(c.delta_h, c.delta_charge) for c in result.site_changes] == [(1, 1)]
    assert len(result.placed_hydrogens) == 1
    added = result.placed_hydrogens[0]
    assert result.mol.GetAtomWithIdx(added).GetSymbol() == "H"
    neighbours = [n.GetIdx() for n in result.mol.GetAtomWithIdx(added).GetNeighbors()]
    assert result.mol.GetAtomWithIdx(neighbours[0]).GetSymbol() == "N"
    # It was PLACED, not left at the origin, and at a chemically sane distance.
    bond = np.linalg.norm(positions(result.mol)[added] - positions(result.mol)[neighbours[0]])
    assert 0.9 < bond < 1.2, bond
    assert np.array_equal(positions(result.mol)[: source.GetNumAtoms()], positions(source))


def test_glycine_records_both_sites_and_they_cancel():
    """The case per-site records exist for: a zwitterion nets zero, so a total-only record would
    call it "no change"."""
    source = conformer_for("NCC(=O)O")
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    assert Chem.GetFormalCharge(result.mol) == 0
    assert len(result.site_changes) == 2
    assert sorted(c.delta_h for c in result.site_changes) == [-1, 1]
    assert sum(c.delta_h for c in result.site_changes) == 0 == sum(c.delta_charge for c in result.site_changes)
    for change in result.site_changes:
        assert change.delta_h == change.delta_charge
        element = source.GetAtomWithIdx(change.heavy_atom).GetSymbol()
        assert (element, change.delta_h) in {("N", 1), ("O", -1)}
    assert Chem.MolToSmiles(Chem.RemoveHs(result.mol)) == "[NH3+]CC(=O)[O-]"


# --- the no-change case ---------------------------------------------------------------------------


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1"])
def test_a_molecule_with_no_ionisable_centre_is_untouched_and_places_no_hydrogen(smiles, monkeypatch):
    called = []
    monkeypatch.setattr(pg, "_place_hydrogens", lambda *args: called.append(args) or "")
    source = conformer_for(smiles)
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    assert result.site_changes == () and result.placed_hydrogens == ()
    assert not result.changed
    assert called == [], "the placement force field ran on a molecule with nothing to place"
    assert np.array_equal(positions(result.mol), positions(source))
    assert Chem.GetFormalCharge(result.mol) == Chem.GetFormalCharge(source)


def test_applying_the_same_ph_twice_changes_nothing_the_second_time():
    first = pg.protonate_conformer(conformer_for("CC(=O)O"), 7.4)
    second = pg.protonate_conformer(first.mol, 7.4)
    assert not second.refusal
    assert second.site_changes == ()
    assert np.array_equal(positions(second.mol), positions(first.mol))


# --- which hydrogen, and when it refuses ----------------------------------------------------------


def test_equivalent_hydrogens_separates_an_ammonium_from_a_prochiral_methylene():
    ammonium = conformer_for("C[NH3+]")
    nitrogen = [a.GetIdx() for a in ammonium.GetAtoms() if a.GetSymbol() == "N"][0]
    hydrogens = [n.GetIdx() for n in ammonium.GetAtomWithIdx(nitrogen).GetNeighbors() if n.GetAtomicNum() == 1]
    assert len(hydrogens) == 3
    assert pg._equivalent_hydrogens(ammonium, nitrogen, hydrogens)

    # A CH2 next to a stereocentre: its two hydrogens are pro-R and pro-S, so they are NOT the same
    # atom under the drawing, and choosing between them would invent an answer.
    # The CH2 of C[C@H](N)CO: pro-R and pro-S, and RDKit's canonical ranking calls them the same,
    # which is the trap `_equivalent_hydrogens` documents.
    prochiral = conformer_for("C[C@H](N)CO")
    carbon = [a.GetIdx() for a in prochiral.GetAtoms()
              if a.GetSymbol() == "C" and sum(1 for n in a.GetNeighbors() if n.GetAtomicNum() == 1) == 2][0]
    pair = [n.GetIdx() for n in prochiral.GetAtomWithIdx(carbon).GetNeighbors() if n.GetAtomicNum() == 1]
    assert len(pair) == 2
    assert not pg._equivalent_hydrogens(prochiral, carbon, pair)


def test_a_state_that_removes_an_inequivalent_hydrogen_refuses(monkeypatch):
    """Dimorphite does not deprotonate a carbon, so the refusal is reached with a stand-in state:
    the point under test is the rule, not the library's chemistry."""
    source = conformer_for("C[C@H](N)CO")
    carbon = [a.GetIdx() for a in source.GetAtoms()
              if a.GetSymbol() == "C" and sum(1 for n in a.GetNeighbors() if n.GetAtomicNum() == 1) == 2][0]

    real = pg.dominant_microspecies

    def deprotonate_the_methylene(flat, ph):
        selected = real(flat, ph)
        edit = Chem.RWMol(selected.mol)
        heavy = [a.GetIdx() for a in source.GetAtoms() if a.GetAtomicNum() != 1]
        atom = edit.GetAtomWithIdx(heavy.index(carbon))
        atom.SetNumExplicitHs(atom.GetTotalNumHs() - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
        return type(selected)(mol=edit.GetMol(), formal_charge=0, corrected_atoms=())

    monkeypatch.setattr(pg, "dominant_microspecies", deprotonate_the_methylene)
    result = pg.protonate_conformer(source, 7.4)
    assert result.refusal == pg.REFUSE_AMBIGUOUS_H_IDENTITY
    assert "not equivalent" in result.message
    assert result.mol is None


def test_an_equivalent_choice_is_recorded_because_the_rule_made_it(monkeypatch):
    source = conformer_for("C[NH3+]")
    nitrogen = [a.GetIdx() for a in source.GetAtoms() if a.GetSymbol() == "N"][0]
    real = pg.dominant_microspecies

    def deprotonate_the_ammonium(flat, ph):
        selected = real(flat, ph)
        edit = Chem.RWMol(selected.mol)
        heavy = [a.GetIdx() for a in source.GetAtoms() if a.GetAtomicNum() != 1]
        atom = edit.GetAtomWithIdx(heavy.index(nitrogen))
        atom.SetNumExplicitHs(atom.GetTotalNumHs() - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
        return type(selected)(mol=edit.GetMol(), formal_charge=0, corrected_atoms=())

    monkeypatch.setattr(pg, "dominant_microspecies", deprotonate_the_ammonium)
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    assert len(result.recorded_choices) == 1
    site, hydrogen = result.recorded_choices[0]
    assert site == nitrogen
    assert source.GetAtomWithIdx(hydrogen).GetSymbol() == "H"


# --- identity -------------------------------------------------------------------------------------


def test_the_state_id_follows_the_ph_the_sites_and_the_policy_version(monkeypatch):
    acid = conformer_for("CC(=O)O")
    ionised = pg.protonate_conformer(acid, 7.4)
    neutral = pg.protonate_conformer(acid, 1.0)
    assert ionised.state_id != neutral.state_id
    assert neutral.site_changes == ()

    monkeypatch.setattr(pg, "PROTONATION_SELECTION_POLICY_VERSION", pg.PROTONATION_SELECTION_POLICY_VERSION + 1)
    assert pg.protonate_conformer(acid, 7.4).state_id != ionised.state_id


def test_the_heavy_map_is_a_bijection_onto_the_result():
    source = conformer_for("NCC(=O)O")
    result = pg.protonate_conformer(source, 7.4)
    heavy = [a.GetIdx() for a in source.GetAtoms() if a.GetAtomicNum() != 1]
    assert [pair[0] for pair in result.source_heavy_map] == heavy
    assert len({pair[1] for pair in result.source_heavy_map}) == len(heavy)
    for source_index, target_index in result.source_heavy_map:
        assert source.GetAtomWithIdx(source_index).GetSymbol() == result.mol.GetAtomWithIdx(target_index).GetSymbol()
        assert np.array_equal(positions(result.mol)[target_index], positions(source)[source_index])


def test_an_atom_map_number_survives_the_state_change():
    source = conformer_for("CC(=O)O")
    for atom in source.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    result = pg.protonate_conformer(source, 7.4)
    assert not result.refusal
    for source_index, target_index in result.source_heavy_map:
        assert result.mol.GetAtomWithIdx(target_index).GetAtomMapNum() == source_index + 1


# --- through the registry -------------------------------------------------------------------------


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def test_the_ph_calculator_is_registered_beside_the_plain_one_and_keeps_its_identity():
    """A separate calculator id, deliberately: the plain 3D calculator's stored results are keyed by
    its parameter defaults, so adding a parameter there would orphan every EEM result saved before."""
    registry = _registry()
    plain = registry.get("geometry_partial_charge")
    at_ph = registry.get("geometry_partial_charge_at_ph")
    assert {p.name for p in plain.parameters} == {"method", "include_hydrogens", "decimal_places"}
    assert {p.name for p in at_ph.parameters} == {"method", "pH", "include_hydrogens", "decimal_places"}
    assert at_ph.calculation_input == plain.calculation_input
    assert at_ph.category == "charge"


def test_the_registered_ph_calculator_computes_the_zwitterion_and_records_both_sites():
    dataset = _registry().get("geometry_partial_charge_at_ph").execution.compute(
        conformer_for("NCC(=O)O"), "uuid-glycine", {"pH": 7.4})
    parameters = dataset.provenance.parameters
    assert parameters["protonation"] == "at_ph" and parameters["pH"] == 7.4
    assert parameters["state_changed"] is True
    assert sorted(site["delta_h"] for site in parameters["site_changes"]) == [-1, 1]
    assert parameters["selection_policy_version"] == pg.PROTONATION_SELECTION_POLICY_VERSION
    assert "ionization states only" in parameters["tautomers"]
    assert "pH 7.4" in dataset.name
    assert abs(sum(dataset.values.values())) < 1e-8  # the zwitterion is neutral overall


def test_with_nothing_to_ionise_the_values_equal_the_as_drawn_calculator_under_a_distinct_identity():
    """Scientific equivalence, separate request: the charges ARE the as-drawn ones, and the result is
    still a different calculator's, so the store keeps both rather than treating one as the other."""
    source = conformer_for("CCO")
    registry = _registry()
    drawn = registry.get("geometry_partial_charge").execution.compute(source, "u", {})
    at_ph = registry.get("geometry_partial_charge_at_ph").execution.compute(source, "u", {"pH": 7.4})
    assert set(drawn.values) == set(at_ph.values)
    assert all(abs(drawn.values[k] - at_ph.values[k]) < 1e-12 for k in drawn.values)
    assert drawn.provenance.parameters["species"] != at_ph.provenance.parameters["species"]
    assert at_ph.provenance.parameters["state_changed"] is False
    assert drawn.name != at_ph.name


def test_every_protonation_refusal_has_a_sentence_and_a_cell(monkeypatch):
    from openchem.chem import geometry_charges as gc

    for code in (pg.REFUSE_AMBIGUOUS_H_IDENTITY, pg.REFUSE_NOT_IONISATION_ONLY,
                 pg.REFUSE_H_PLACEMENT, pg.REFUSE_PROTONATION_FAILED):
        assert code in gc.REFUSAL_MESSAGES and code in gc._SHORT

    monkeypatch.setattr(gc, "protonate_conformer",
                        lambda mol, ph: pg.ProtonatedConformer(refusal=pg.REFUSE_AMBIGUOUS_H_IDENTITY, message="x"))
    dataset = gc.compute_geometry_charges_at_ph(conformer_for("CC(=O)O"), "u", {"pH": 7.4})
    assert dataset.values == {}
    assert dataset.provenance.parameters["refusal"] == pg.REFUSE_AMBIGUOUS_H_IDENTITY


# --- the guards the mutations aim at ---------------------------------------------------------------


def test_the_policy_version_covers_the_decision_table():
    """THE RATCHET for `PROTONATION_SELECTION_POLICY_VERSION`. It hashes the functions that decide
    which state is taken and which hydrogen goes, so changing a rule without bumping the version
    turns this red. Fix it by bumping the version (and saying so), never by re-recording the hash."""
    import hashlib
    import inspect

    table = "".join(inspect.getsource(function) for function in
                    (pg._site_changes, pg._equivalent_hydrogens, pg.protonate_conformer))
    digest = hashlib.sha256(table.encode("utf-8")).hexdigest()
    assert (pg.PROTONATION_SELECTION_POLICY_VERSION, digest[:16]) == (1, "81562533ab746a37"), (
        "the protonation decision table changed; bump PROTONATION_SELECTION_POLICY_VERSION and "
        f"record the new digest {digest[:16]!r}")


def test_the_force_field_is_pinned_to_mmff94_and_nothing_falls_back(monkeypatch):
    assert pg.MMFF_VARIANT == "MMFF94" and pg.MMFF_MAX_ITERATIONS == 2000
    seen = []
    real = pg.AllChem.MMFFGetMoleculeProperties
    monkeypatch.setattr(pg.AllChem, "MMFFGetMoleculeProperties",
                        lambda mol, mmffVariant: seen.append(mmffVariant) or real(mol, mmffVariant=mmffVariant))
    result = pg.protonate_conformer(conformer_for("CN"), 7.4)
    assert not result.refusal and seen == ["MMFF94"]

    # A species MMFF cannot type refuses; it never reaches for another force field.
    monkeypatch.setattr(pg.AllChem, "MMFFGetMoleculeProperties", lambda mol, mmffVariant: None)
    refused = pg.protonate_conformer(conformer_for("CN"), 7.4)
    assert refused.refusal == pg.REFUSE_H_PLACEMENT and refused.mol is None


def test_the_added_hydrogen_is_minimised_and_not_left_where_addhs_guessed(monkeypatch):
    """`AddHs(addCoords=True)` already puts the hydrogen somewhere plausible, so a bond-length check
    passes even if the force field never runs -- measured: skipping the minimisation survived every
    other test here. MMFF moves it about 0.08 A, and that is what this asserts."""
    source = conformer_for("CN")
    placed = pg.protonate_conformer(source, 7.4)

    monkeypatch.setattr(pg, "_place_hydrogens", lambda mol, fixed: "")
    unplaced = pg.protonate_conformer(source, 7.4)

    moved = np.linalg.norm(
        np.array(placed.mol.GetConformer().GetPositions())[list(placed.placed_hydrogens)]
        - np.array(unplaced.mol.GetConformer().GetPositions())[list(unplaced.placed_hydrogens)], axis=1).max()
    assert moved > 0.01, f"the placement did not move the added hydrogen ({moved:.4f} A)"


def test_the_two_calculators_produce_datasets_under_DIFFERENT_property_ids():
    """**FOUND BY DRIVING THE APP, WITH EVERY UNIT TEST GREEN.** The Properties panel keys retained
    results by `dataset.property_id`, not by calculator id, so while both calculators emitted the
    same id the pH result overwrote the as-drawn one: `result_report` for the pH calculator came
    back `{}` and the Atom Inspector held one result where two had been computed."""
    from openchem.chem import geometry_charges as gc

    source = conformer_for("NCC(=O)O")
    drawn = gc.compute_geometry_charges(source, "u", {})
    at_ph = gc.compute_geometry_charges_at_ph(source, "u", {"pH": 7.4})
    assert drawn.property_id == "geometry_partial_charge"
    assert at_ph.property_id == "geometry_partial_charge_at_ph"
    assert drawn.property_id != at_ph.property_id

    # A refusal must carry the same id as the result it replaces, or the panel files it elsewhere.
    refused = gc._refusal(pg.REFUSE_H_PLACEMENT, "n", gc.EEM_BULTINCK2002_PART1, 4, "u",
                          property_id=gc.PROPERTY_ID_AT_PH)
    assert refused.property_id == "geometry_partial_charge_at_ph"
