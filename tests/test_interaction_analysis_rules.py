"""Interaction Analysis: the five contacts that were wrong in chemistry terms, measured 2026-10-11, and the rules that fix them.

Every case runs through the REGISTERED calculator (`CALCULATOR_DEFINITIONS`), not the function it was written as: the
registration is what the application calls, and a test of the import alone has passed before while the registry bound
something else. Each case also MEASURES ITS OWN PRECONDITION from the conformer's coordinates -- that the nitro nitrogen
really is within the cation-pi cutoff of its ring, that the two ether oxygens really are within 3.5 A -- so a platform
whose embedding differs fails loudly instead of passing because the defect never had a chance to appear.
"""

from __future__ import annotations

import re

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import interaction_analysis as ia
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.pose_analysis import (
    CATION_PI_CUTOFF,
    HBOND_DISTANCE_CUTOFF,
    metal_bond_window,
    PI_STACKING_CUTOFF,
    SALT_BRIDGE_CUTOFF,
)
from openchem.domain.calculator import GEOMETRY
from openchem.domain.result_store import (
    CURRENT_METHOD_VERSIONS,
    INTERACTION_METHOD,
    LEGACY_METHOD_VERSIONS,
    SessionResultStore,
    StoredResult,
)

_DEFINITION = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "interaction_analysis")


def _report(mol: Chem.Mol):
    return _DEFINITION.execution.compute(mol, "m", {"decimals": 2})


def _lines(mol: Chem.Mol, label: str) -> list[str]:
    return [line for line in _report(mol).matched if line.startswith(f"{label}:")]


def _pairs(mol: Chem.Mol, label: str) -> list[tuple[int, int]]:
    return [tuple(int(n) for n in re.search(r"atoms (\d+)-(\d+)", line).groups()) for line in _lines(mol, label)]


def _conformers(smiles: str, count: int = 12, seed: int = 7) -> list[Chem.Mol]:
    """MMFF94-relaxed conformers, one molecule each (the seed the explainer's measurements used)."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    ids = list(AllChem.EmbedMultipleConfs(mol, count, randomSeed=seed))
    assert ids, f"{smiles} did not embed"
    AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=2000)
    return [Chem.Mol(mol, confId=i) for i in ids]


def _xyz(mol: Chem.Mol) -> np.ndarray:
    return mol.GetConformer().GetPositions()


def _centroids(mol: Chem.Mol) -> list[np.ndarray]:
    positions = _xyz(mol)
    return [positions[list(ring)].mean(axis=0) for ring in ia._aromatic_rings(mol)]


def _metal_beside(smiles: str, donor_symbol: str, distance: float) -> tuple[Chem.Mol, int, int]:
    """An embedded `metal.fragment` with the metal moved to `distance` angstroms from the first `donor_symbol` atom,
    on the side facing away from the rest of the molecule. Disconnected pieces are embedded on top of each other, so the
    metal is placed by hand and the distance is the one the test states, not one the embedding happened to give."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    conformer = mol.GetConformer()
    metal = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in ("Zn", "Na", "K"))
    donor = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == donor_symbol)
    positions = conformer.GetPositions()
    outward = positions[donor] - np.delete(positions, [metal, donor], axis=0).mean(axis=0)
    outward /= np.linalg.norm(outward)
    conformer.SetAtomPosition(metal, (positions[donor] + outward * distance).tolist())
    return mol, metal, donor


# --- 1. a charge-separated drawing of a neutral group is not an ion ------------------------------------------------


def _symbols(mol: Chem.Mol, indices) -> list[str]:
    return sorted(mol.GetAtomWithIdx(i).GetSymbol() for i in indices)


@pytest.mark.parametrize(
    "smiles",
    [
        "c1ccccc1[N+](=O)[O-]",  # nitrobenzene
        "[O-]C(=O)c1cccc(c1)[N+](=O)[O-]",  # 3-nitrobenzoate
        "[O-][N+](=O)c1ccc(cc1)-c1ccc(cc1)[N+](=O)[O-]",  # 4,4'-dinitrobiphenyl
        "C[S+]([O-])c1ccccc1",  # a sulfoxide drawn with charges
        "[N-]=[N+]=Nc1ccccc1",  # phenyl azide
        "C[N+](C)([O-])CCc1ccccc1",  # an N-oxide
    ],
)
def test_a_charge_separated_neutral_group_is_not_a_cation_over_the_ring(smiles):
    near = 0
    for mol in _conformers(smiles):
        rings = _centroids(mol)
        positions = _xyz(mol)
        ring_atoms = {i for ring in ia._aromatic_rings(mol) for i in ring}
        if any(
            np.linalg.norm(positions[a.GetIdx()] - c) <= CATION_PI_CUTOFF
            for a in mol.GetAtoms()
            if a.GetFormalCharge() > 0 and a.GetIdx() not in ring_atoms
            for c in rings
        ):
            near += 1
            assert _lines(mol, "Cation-π") == [], smiles
    assert near, f"{smiles}: no conformer put the charged atom within {CATION_PI_CUTOFF} A of a ring, so nothing was tested"


def test_the_nitro_nitrogen_is_not_a_salt_bridge_partner_for_a_neighbouring_carboxylate():
    """2-nitrobenzoate measured a salt bridge of 2.74 A between the nitro nitrogen and the carboxylate oxygen."""
    tested = 0
    for mol in _conformers("[O-]C(=O)c1ccccc1[N+](=O)[O-]"):
        nitro_n = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N")
        carboxylate_o = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "O" and a.GetFormalCharge() < 0 and
                             a.GetNeighbors()[0].GetSymbol() == "C")
        if np.linalg.norm(_xyz(mol)[nitro_n] - _xyz(mol)[carboxylate_o]) <= SALT_BRIDGE_CUTOFF:
            tested += 1
            assert _lines(mol, "Salt bridge") == []
    assert tested, "no conformer put the nitro nitrogen within the salt-bridge cutoff of the carboxylate"


@pytest.mark.parametrize(
    "smiles, positive, negative",
    [
        ("CC[NH3+]", ["N"], []),  # an ammonium is a cation
        ("CC(=O)[O-]", [], ["O"]),  # a carboxylate oxygen is an anion
        ("[NH3+]CC([O-])=O", ["N"], ["O"]),  # a zwitterion's charges are not adjacent: both stay
        ("c1ccccc1[N+](=O)[O-]", [], []),  # nitro
        ("C[N+](C)(C)[O-]", [], []),  # N-oxide
        ("CS(C)=O", [], []),  # drawn neutral, for the baseline
        ("C[S+]([O-])C", [], []),  # sulfoxide drawn with charges
        ("[N-]=[N+]=NC", [], []),  # azide
        ("C=[N+]=[N-]", [], []),  # diazo
        ("C[P+](C)(C)[CH2-]", [], []),  # ylide
        ("C[N+]#[C-]", [], []),  # isocyanide
        # Nitrate nets -1: a real anion. Excluding every charge next to an opposite one would erase it.
        ("[O-][N+](=O)[O-]", [], ["O", "O"]),
    ],
)
def test_which_formal_charges_are_ion_sites(smiles, positive, negative):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    cations, anions = ia._formal_charge_sites(mol)

    assert (_symbols(mol, cations), _symbols(mol, anions)) == (positive, negative)


def test_a_nitrate_salt_still_reports_its_anion_and_never_the_nitrogen():
    """The cluster rule, through the calculator. The two pieces are embedded on top of each other (a known limit of
    separate fragments), which is enough: the question is which atoms are sites."""
    (mol,) = _conformers("C[NH3+].[O-][N+](=O)[O-]", count=1)
    ammonium_n = next(a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge() > 0 and a.GetSymbol() == "N")
    nitrate_n = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "N" and a.GetIdx() != ammonium_n)
    pairs = _pairs(mol, "Salt bridge")

    assert pairs, "the nitrate oxygens were erased as ion sites"
    assert all(ammonium_n in pair and nitrate_n not in pair for pair in pairs)


# --- 2. two acceptors are not a hydrogen bond ----------------------------------------------------------------------


def _acceptor_pair_in_range(mol: Chem.Mol, first: str = "O", second: str = "O") -> bool:
    positions = _xyz(mol)
    topological = Chem.GetDistanceMatrix(mol)
    atoms = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() in (first, second)]
    return any(
        np.linalg.norm(positions[i] - positions[j]) <= HBOND_DISTANCE_CUTOFF and topological[i][j] >= 3
        for n, i in enumerate(atoms)
        for j in atoms[n + 1 :]
    )


@pytest.mark.parametrize("smiles", ["COCCOC", "COCCOCCOC", "C1COCCOCCOCCOCCOCCO1"])
def test_two_ether_oxygens_are_not_a_hydrogen_bond(smiles):
    tested = 0
    for mol in _conformers(smiles):
        if _acceptor_pair_in_range(mol):
            tested += 1
            assert _lines(mol, "Hydrogen bond") == [], smiles
    assert tested, f"{smiles}: no conformer put two oxygens within {HBOND_DISTANCE_CUTOFF} A"


@pytest.mark.parametrize("smiles", ["OCCO", "COCCO", "OC(=O)c1ccccc1O", "NCCO"])
def test_a_hydrogen_bond_with_a_donor_is_still_found(smiles):
    """The same rule keeps every pair where one atom carries a hydrogen: glycol (the textbook five-ring), the half ether
    and salicylic acid's six-ring, in at least one conformer each."""
    assert any(_lines(mol, "Hydrogen bond") for mol in _conformers(smiles)), smiles


def test_an_acceptor_pair_too_close_is_a_clash_and_no_longer_hidden_as_a_hydrogen_bond():
    """The clash list excludes only what IS a hydrogen bond. Two acceptors 2.2 A apart (diglyme's end oxygens, 6 bonds
    apart, moved together by hand) used to be swallowed as a hydrogen bond; now they are what they are, a clash."""
    mol = Chem.AddHs(Chem.MolFromSmiles("COCCOCCOC"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    first, _, last = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "O"]
    conformer = mol.GetConformer()
    conformer.SetAtomPosition(last, (np.array(conformer.GetAtomPosition(first)) + np.array([2.2, 0.0, 0.0])).tolist())

    assert (first, last) in _pairs(mol, "Steric clash")
    assert (first, last) not in _pairs(mol, "Hydrogen bond")


# --- 3. directly joined rings are not a stack ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles",
    ["c1ccccc1-c1ccccc1", "c1ccccc1Cc1ccccc1", "c1ccnc(c1)-c1ccccn1", "c1ccccc1C(c1ccccc1)c1ccccc1"],
)
def test_rings_joined_directly_or_through_one_atom_are_not_stacked(smiles):
    tested = 0
    for mol in _conformers(smiles):
        centroids = _centroids(mol)
        if any(np.linalg.norm(a - b) <= PI_STACKING_CUTOFF for n, a in enumerate(centroids) for b in centroids[n + 1 :]):
            tested += 1
            assert _lines(mol, "π-π stacking") == [], smiles
    assert tested, f"{smiles}: no conformer had two ring centres within {PI_STACKING_CUTOFF} A"


def test_rings_two_linking_atoms_apart_still_stack_when_folded():
    """Bibenzyl's rings are 3 bonds apart and fold over each other in some conformers (the existing conformer test
    asserts both outcomes); here the boundary is pinned from the other side, so a separation of 4 would fail it."""
    assert any(_lines(mol, "π-π stacking") for mol in _conformers("c1ccccc1CCc1ccccc1", count=30))


def test_in_ortho_terphenyl_only_the_two_outer_rings_can_stack():
    """The middle ring is joined to both outer rings, so neither pair that includes it counts; the outer rings are 3
    bonds apart through the middle one."""
    seen_outer = False
    for mol in _conformers("c1ccccc1-c1ccccc1-c1ccccc1", count=20):
        topological = Chem.GetDistanceMatrix(mol)
        for line in _lines(mol, "π-π stacking"):
            groups = [[int(n) for n in group.split(",")] for group in re.findall(r"\[([\d, ]+)\]", line)]
            assert min(topological[i][j] for i in groups[0] for j in groups[1]) >= 3, line
            seen_outer = True
    assert seen_outer, "no conformer stacked the outer rings, so the boundary at 3 was not exercised"


# --- 4. a thiolate sulfur coordinates a metal ----------------------------------------------------------------------


def test_a_thiolate_sulfur_coordinates_zinc():
    """The exact structure reported: `[Zn+2].[S-]CCN` listed the amine nitrogen only."""
    mol, metal, sulfur = _metal_beside("[Zn+2].[S-]CCN", "S", 2.35)

    assert (metal, sulfur) in _pairs(mol, "Metal coordination")


@pytest.mark.parametrize("smiles", ["[Zn+2].CSC", "[Zn+2].CSSC", "[Zn+2].CC(=S)N"])
def test_other_divalent_sulfur_donors_count_too(smiles):
    mol, metal, sulfur = _metal_beside(smiles, "S", 2.35)

    assert (metal, sulfur) in _pairs(mol, "Metal coordination")


@pytest.mark.parametrize("smiles", ["[Zn+2].CS(C)(=O)=O", "[Na+].CS(C)=O", "[Zn+2].Cc1ccc(cc1)S(=O)(=O)N"])
def test_a_sulfone_sulfoxide_or_sulfonamide_sulfur_is_not_a_donor(smiles):
    """Valence 4 or 6: no lone pair to give, and its oxygens are the donors there."""
    mol, metal, sulfur = _metal_beside(smiles, "S", 2.35)
    coordinating = {pair for pair in _pairs(mol, "Metal coordination")}

    assert (metal, sulfur) not in coordinating and (sulfur, metal) not in coordinating


def test_the_metal_window_is_the_shared_one():
    """2.8 A used to be a literal here, then one shared constant. Now it is the shared per-metal window: just inside
    zinc's longest Zn-S bond coordinates, just outside does not."""
    longest = metal_bond_window("ZN", "S")[1]
    inside, metal, sulfur = _metal_beside("[Zn+2].[S-]CCN", "S", longest - 0.05)
    outside, _, _ = _metal_beside("[Zn+2].[S-]CCN", "S", longest + 0.05)

    assert (metal, sulfur) in _pairs(inside, "Metal coordination")
    assert (metal, sulfur) not in _pairs(outside, "Metal coordination")


def test_the_window_depends_on_the_metal_and_the_donor_not_one_number():
    """Zinc to an amine nitrogen at 2.7 A was inside the old single 2.8 A cutoff; Harding's bond is 2.03 A and the
    window ends at 2.53. Potassium to oxygen at 3.4 A was outside it; K-O is 2.82 A and the window runs to 3.57."""
    far, zinc, nitrogen = _metal_beside("[Zn+2].CCN", "N", 2.7)
    near, _, _ = _metal_beside("[Zn+2].CCN", "N", 2.4)
    potassium_mol, potassium, oxygen = _metal_beside("[K+].CC[O-]", "O", 3.4)

    assert (zinc, nitrogen) not in _pairs(far, "Metal coordination")
    assert (zinc, nitrogen) in _pairs(near, "Metal coordination")
    assert (potassium, oxygen) in _pairs(potassium_mol, "Metal coordination")


# --- 5. a hydrophobic contact has a lower bound -------------------------------------------------------------------


def _carbon_radii_sum() -> float:
    return 2 * ia._vdw_radius("C")


def test_the_peri_methyls_of_dimethylnaphthalene_are_crowding_not_a_hydrophobic_contact():
    tested = 0
    for mol in _conformers("Cc1cccc2cccc(C)c12"):
        methyls = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C" and not a.GetIsAromatic()]
        positions = _xyz(mol)
        if np.linalg.norm(positions[methyls[0]] - positions[methyls[1]]) < _carbon_radii_sum():
            tested += 1
            assert tuple(methyls) not in _pairs(mol, "Hydrophobic contact"), "reported as attraction"
    assert tested, "no conformer put the peri methyls closer than the van der Waals contact"


@pytest.mark.parametrize(
    "smiles",
    [
        "Cc1cccc2cccc(C)c12",
        "CC(C)(C)C1CCCC(C1)C(C)(C)C",
        "CC(C)CCCC(C)C1CCC2C1(CCC3C2CC=C4C3(CCC(C4)O)C)C",  # cholesterol: syn-axial methyls at 3.2-3.4 A
    ],
)
def test_no_hydrophobic_contact_is_nearer_than_the_van_der_Waals_contact(smiles):
    for mol in _conformers(smiles, count=8):
        for line in _lines(mol, "Hydrophobic contact"):
            assert float(re.search(r"\(([\d.]+) Å\)", line).group(1)) >= round(_carbon_radii_sum(), 2) - 0.005, line


def test_a_contact_beyond_the_van_der_Waals_distance_is_still_reported():
    """The bound is a floor, not a removal of the kind: the tert-butyl groups of cis-1,3-di-tert-butylcyclohexane (the
    meso, S,R isomer) still report contacts from 3.56 to 4.49 A over twenty conformers, the part of the old behaviour
    the documentation keeps as a limit: nearer than 4 A is crowding by any chemist's reading, and a distance alone
    cannot say so."""
    base = Chem.MolFromSmiles("CC(C)(C)[C@H]1CCC[C@H](C1)C(C)(C)C")
    assert sorted(label for _, label in Chem.FindMolChiralCenters(base, useLegacyImplementation=False)) == ["R", "S"]
    distances = [
        float(re.search(r"\(([\d.]+) Å\)", line).group(1))
        for mol in _conformers("CC(C)(C)[C@H]1CCC[C@H](C1)C(C)(C)C", count=20)
        for line in _lines(mol, "Hydrophobic contact")
    ]
    assert distances and min(distances) >= 3.4 and min(distances) < 4.0


# --- the method is part of the identity ---------------------------------------------------------------------------


def test_a_result_records_its_method_and_the_identity_carries_it():
    from openchem.services.result_identity import make_identity

    result = _report(_conformers("CCO", count=1)[0])
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )

    assert result.provenance.parameters["method"] == INTERACTION_METHOD == "interactions-v4"
    assert identity.method_version == INTERACTION_METHOD == CURRENT_METHOD_VERSIONS["interaction_analysis"]


def test_an_interaction_result_saved_before_the_change_is_kept_and_labelled():
    """The old lines said nitrobenzene's nitro nitrogen was a cation over its own ring. A project saved then is
    restored under its own label and slot, never replayed as the current method."""
    from openchem.services.result_identity import make_identity

    result = _report(_conformers("CCO", count=1)[0])
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    saved = store.to_dict()
    (entry,) = saved["molecules"]["m"]["results"]
    entry.pop("method_version")

    (restored,) = SessionResultStore.from_dict(saved, "project").fresh_results("m", {GEOMETRY: "fp"})

    legacy, label = LEGACY_METHOD_VERSIONS["interaction_analysis"]
    assert restored.identity.method_version == legacy == "legacy-contact-rules-v1"
    assert restored.result.name == label and label.startswith("Interaction Analysis") and "previous method" in label
    assert restored.identity.method_version != CURRENT_METHOD_VERSIONS["interaction_analysis"]


def test_an_interactions_v2_result_is_kept_beside_the_v3_one_and_labelled():
    """v3 (2026-10-12) made the metal window per metal and per donor. A project saved by v2 keeps its lines under their
    own label and is not replayed as the current method."""
    from openchem.services.result_identity import make_identity

    result = _report(_conformers("CCO", count=1)[0])
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    saved = store.to_dict()
    saved["molecules"]["m"]["results"][0]["method_version"] = "interactions-v2"
    reloaded = SessionResultStore.from_dict(saved, "project")

    (restored,) = reloaded.fresh_results("m", {GEOMETRY: "fp"})
    assert restored.identity.method_version == "interactions-v2"
    assert restored.result.name.startswith("Interaction Analysis (previous method")

    reloaded.put(StoredResult(identity=identity, result=result))
    replayed = {s.identity.method_version for s in reloaded.fresh_results("m", {GEOMETRY: "fp"})}
    kept = {entry.get("method_version", "") for entry in reloaded.to_dict()["molecules"]["m"]["results"]}
    assert replayed == {"interactions-v4"} and kept == {"interactions-v2", "interactions-v4"}


def test_an_interactions_v3_result_is_kept_beside_the_v4_one_and_labelled():
    """v4 (2026-10-12) stopped counting fluorine as a donor to the transition metals. A project saved by v3 keeps its
    lines under their own label."""
    from openchem.services.result_identity import make_identity

    result = _report(_conformers("CCO", count=1)[0])
    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY, input_fingerprint="fp", producer="core"
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    saved = store.to_dict()
    saved["molecules"]["m"]["results"][0]["method_version"] = "interactions-v3"
    reloaded = SessionResultStore.from_dict(saved, "project")

    (restored,) = reloaded.fresh_results("m", {GEOMETRY: "fp"})
    assert restored.identity.method_version == "interactions-v3"
    assert "fluorine" in restored.result.name and restored.result.name.startswith("Interaction Analysis (previous method")

    reloaded.put(StoredResult(identity=identity, result=result))
    kept = {entry.get("method_version", "") for entry in reloaded.to_dict()["molecules"]["m"]["results"]}
    assert kept == {"interactions-v3", "interactions-v4"}
