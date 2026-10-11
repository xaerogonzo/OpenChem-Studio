"""Molecular Surface Area (3D): the radii, the solvent probe, the van der Waals surface, the microspecies.

**THE ANCHORS ARE CLOSED FORMS AND AN INDEPENDENT ROUTINE, NEVER ANOTHER MOLECULE.** Until
2026-10-10 the accessible surface was computed with a radius of zero for every atom, because
`rdFreeSASA.classifyAtoms` returns zeros for a molecule that did not come from a PDB file. Ethanol
read 97 A^2 against 199 and benzene 127 against 234, and every test passed, because the tests
compared one molecule with another (a longer chain reads larger -- true at any radius). A lone
sphere has an exact answer, two spheres have one, and the analytic double-cubic-lattice routine
is an independent second computation of the same surface.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.projection_geometry import van_der_waals_surface_area
from openchem.chem.surface_analysis import (
    DEFAULT_SOLVENT_RADIUS,
    compute_sasa_dataset,
    compute_surface_analysis,
    per_atom_sasa,
    solvent_radius,
    surface_areas,
)
from openchem.domain.calculator import GEOMETRY

_TABLE = Chem.GetPeriodicTable()
CHLORINE = _TABLE.GetRvdw(17)


def _atoms(*positions, element: int = 17) -> Chem.Mol:
    """Atoms of one element at exact coordinates, bonded in a chain: a molecule whose surface is a closed form."""
    editable = Chem.RWMol()
    for _ in positions:
        editable.AddAtom(Chem.Atom(element))
    for index in range(len(positions) - 1):
        editable.AddBond(index, index + 1, Chem.BondType.SINGLE)
    conformer = Chem.Conformer(len(positions))
    for index, position in enumerate(positions):
        conformer.SetAtomPosition(index, position)
    conformer.Set3D(True)
    editable.AddConformer(conformer)
    mol = editable.GetMol()
    Chem.SanitizeMol(mol)
    return mol


def _embedded(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=1) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _brute(mol: Chem.Mol, probe: float, per_atom: int = 60_000, seed: int = 11) -> float:
    """The accessible surface by RANDOM test points: a different point set and a different generator
    from the routine under test, so agreement is not two uses of one idea. About 0.3% statistical error."""
    import numpy as np

    positions = np.array(mol.GetConformer().GetPositions())
    reach = np.array([_TABLE.GetRvdw(atom.GetAtomicNum()) for atom in mol.GetAtoms()]) + probe
    generator = np.random.default_rng(seed)
    total = 0.0
    for index in range(len(reach)):
        direction = generator.normal(size=(per_atom, 3))
        direction /= np.linalg.norm(direction, axis=1)[:, None]
        point = positions[index] + reach[index] * direction
        gap = np.linalg.norm(point[:, None, :] - positions[None, :, :], axis=2)
        covered = gap < reach[None, :] - 1e-9
        covered[:, index] = False
        total += 4 * math.pi * reach[index] ** 2 * float((~covered.any(axis=1)).mean())
    return total


# --- the radii: the defect this guards --------------------------------------------------------------------


@pytest.mark.parametrize("probe", [0.0, 1.4, 2.0])
def test_a_lone_sphere_has_the_surface_of_its_sphere_whatever_the_probe(probe):
    sphere = _atoms((0.0, 0.0, 0.0))

    assert sum(per_atom_sasa(sphere, probe).values()) == pytest.approx(4 * math.pi * (CHLORINE + probe) ** 2, rel=1e-9)


@pytest.mark.parametrize("probe", [0.0, 1.4])
def test_two_spheres_are_within_the_sampling_error_of_their_closed_form(probe):
    """Two equal spheres a distance d apart: 4 pi R^2 + 2 pi R d, with R = r + probe. Sampled, so within 1%."""
    distance = 2.0
    radius = CHLORINE + probe
    pair = _atoms((0.0, 0.0, 0.0), (distance, 0.0, 0.0))

    assert sum(per_atom_sasa(pair, probe).values()) == pytest.approx(
        4 * math.pi * radius**2 + 2 * math.pi * radius * distance, rel=0.01
    )


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "O"])
def test_the_accessible_surface_agrees_with_an_independent_brute_force_reference(smiles):
    """The zero-radius defect read 40-55% of this; rdFreeSASA's slicing read 3.8% low on flat benzene."""
    mol = _embedded(smiles)

    assert surface_areas(mol)["asa"] == pytest.approx(_brute(mol, DEFAULT_SOLVENT_RADIUS), rel=0.015)


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1"])
def test_with_no_probe_it_is_the_van_der_waals_surface(smiles):
    mol = _embedded(smiles)

    assert sum(per_atom_sasa(mol, 0.0).values()) == pytest.approx(van_der_waals_surface_area(mol), rel=1e-9)
    assert van_der_waals_surface_area(mol) == pytest.approx(_brute(mol, 0.0), rel=0.015)


def test_the_total_does_not_depend_on_how_the_molecule_is_turned():
    """The failure mode of slicing algorithms on a flat molecule; point sampling has no preferred axis."""
    import numpy as np
    from rdkit.Chem import rdMolTransforms

    mol = _embedded("c1ccccc1")
    totals = []
    for seed in range(5):
        turned = Chem.Mol(mol)
        q, _ = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
        matrix = np.eye(4)
        matrix[:3, :3] = q
        rdMolTransforms.TransformConformer(turned.GetConformer(), matrix)
        totals.append(surface_areas(turned)["asa"])

    assert (max(totals) - min(totals)) / min(totals) < 0.01


def test_a_repeat_run_gives_exactly_the_same_number():
    mol = _embedded("CC(=O)Oc1ccccc1C(=O)O")

    assert surface_areas(mol)["asa"] == surface_areas(mol)["asa"]


def test_the_atomic_radii_are_not_zero():
    """The line that would have caught it, in one assertion."""
    from openchem.chem.surface_analysis import atomic_radii

    assert all(radius > 0 for radius in atomic_radii(_embedded("CCO")))


# --- the solvent probe ---------------------------------------------------------------------------------------


def test_a_bigger_probe_always_reaches_a_bigger_surface():
    mol = _embedded("CC(=O)Oc1ccccc1C(=O)O")
    totals = [surface_areas(mol, probe)["asa"] for probe in (0.0, 0.7, 1.4, 2.1, 2.8)]

    assert totals == sorted(totals) and len(set(totals)) == len(totals)


def test_the_probe_is_the_one_the_report_names():
    mol = _embedded("CCO")

    default = compute_surface_analysis(mol, "m", {})
    larger = compute_surface_analysis(mol, "m", {"solvent_radius": 2.0})

    assert default.matched[0].startswith("ASA (solvent accessible):")
    assert larger.matched[0].startswith("ASA (solvent accessible, 2 Å probe):")
    assert larger.provenance.parameters["solvent_radius"] == 2.0


@pytest.mark.parametrize("stored", [-1, 99, "x", None])
def test_an_unusable_probe_reads_as_the_default(stored):
    assert solvent_radius({"solvent_radius": stored}) == DEFAULT_SOLVENT_RADIUS


def test_the_per_atom_surface_takes_the_probe_too_and_still_sums_to_the_total():
    mol = _embedded("CCO")

    dataset = compute_sasa_dataset(mol, "m", {"solvent_radius": 2.0})

    assert sum(dataset.values.values()) == pytest.approx(surface_areas(mol, 2.0)["asa"], rel=1e-9)
    assert dataset.provenance.parameters["solvent_radius"] == 2.0


# --- the van der Waals surface -----------------------------------------------------------------------------------


def test_a_lone_sphere_has_the_van_der_waals_surface_of_its_sphere():
    assert van_der_waals_surface_area(_atoms((0.0, 0.0, 0.0))) == pytest.approx(4 * math.pi * CHLORINE**2, rel=1e-9)


def test_the_report_gives_the_van_der_waals_surface_and_volume_together():
    report = compute_surface_analysis(_embedded("CCO"), "m", {})

    line = next(text for text in report.matched if text.startswith("van der Waals surface area"))
    assert line.endswith("Å²")
    assert any(text.startswith("van der Waals volume") for text in report.matched)


# --- the major microspecies ----------------------------------------------------------------------------------------


def test_by_default_there_is_no_microspecies_and_no_note():
    report = compute_surface_analysis(_embedded("CC(=O)O"), "m", {})

    assert not any("microspecies" in text for text in report.matched)


def test_acetic_acid_at_ph_74_is_computed_on_its_carboxylate_with_the_heavy_atoms_where_they_were():
    mol = _embedded("CC(=O)O")
    acid = compute_surface_analysis(mol, "m", {})
    anion = compute_surface_analysis(mol, "m", {"major_microspecies": True, "pH": 7.4})

    assert any("major microspecies at pH 7.4" in text for text in anion.matched)
    assert any("differs from the structure as it is" in text for text in anion.matched)
    assert anion.provenance.parameters["state_changed"] is True
    assert anion.matched[0] != acid.matched[0]


def test_at_a_ph_where_it_is_already_the_dominant_form_it_says_so():
    report = compute_surface_analysis(_embedded("CC(=O)O"), "m", {"major_microspecies": True, "pH": 1.0})

    assert any("already the dominant form" in text for text in report.matched)
    assert report.provenance.parameters["state_changed"] is False


def test_a_structure_that_cannot_be_protonated_is_a_refusal_that_says_why(monkeypatch):
    from openchem.chem import surface_analysis
    from openchem.chem.protonation_geometry import ProtonatedConformer

    monkeypatch.setattr(
        surface_analysis, "protonate_conformer",
        lambda mol, ph: ProtonatedConformer(refusal="REFUSE_PROTONATION_FAILED", message="no state for this molecule"),
    )

    report = compute_surface_analysis(_embedded("CC(=O)O"), "m", {"major_microspecies": True})

    assert report.cache_state.name == "FAILED" and report.error == "no state for this molecule"


def test_the_microspecies_is_computed_on_a_copy():
    from openchem.chem.geometry_preparation import geometry_fingerprint

    mol = _embedded("CC(=O)O")
    before = geometry_fingerprint(mol)

    compute_surface_analysis(mol, "m", {"major_microspecies": True, "pH": 10.0})

    assert geometry_fingerprint(mol) == before


def test_a_two_d_structure_is_still_refused_for_the_microspecies_too():
    flat = Chem.MolFromSmiles("CC(=O)O")
    AllChem.Compute2DCoords(flat)

    report = compute_surface_analysis(flat, "m", {"major_microspecies": True})

    assert report.cache_state.name == "FAILED"


# --- the method version -----------------------------------------------------------------------------------------------


def _stored(result, result_id_fingerprint="fp"):
    from openchem.domain.result_store import SessionResultStore, StoredResult
    from openchem.services.result_identity import make_identity

    identity = make_identity(
        molecule_uuid="m", result=result, calculation_input=GEOMETRY,
        input_fingerprint=result_id_fingerprint, producer="core",
    )
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=result))
    return store, identity


@pytest.mark.parametrize("producer, expected_name", [
    (lambda mol: compute_surface_analysis(mol, "m", {}), "Molecular Surface Area (3D)"),
    (lambda mol: compute_sasa_dataset(mol, "m", {}), "Accessible Surface Area (per atom)"),
])
def test_a_surface_result_saved_with_zero_radii_is_kept_but_labelled_withdrawn(producer, expected_name):
    from openchem.domain.result_store import LEGACY_METHOD_VERSIONS, SURFACE_METHOD, SessionResultStore

    store, identity = _stored(producer(_embedded("CCO")))
    assert identity.method_version == SURFACE_METHOD == "surface-v2"
    saved = store.to_dict()
    (entry,) = saved["molecules"]["m"]["results"]
    entry.pop("method_version")

    (restored,) = SessionResultStore.from_dict(saved, "project").fresh_results("m", {GEOMETRY: "fp"})

    legacy, label = LEGACY_METHOD_VERSIONS[identity.result_id]
    assert restored.identity.method_version == legacy == "legacy-zero-radii-v1"
    assert restored.result.name == label and label.startswith(expected_name) and "withdrawn" in label
