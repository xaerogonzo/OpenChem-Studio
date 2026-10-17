"""Scores over Geometry Analysis's eight sizes, and the two refusals every geometry number now has (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

What is pinned, because each was a way to ship a wrong number:

* **The eight numbers are what their endpoint texts say.** Each is reproduced here by a route that shares no code with the producer: the two radii from the centroid by numpy over the atom
  positions, and the six projection numbers by rasterising the union of Bondi circles at the direction the producer reports (the area), by minimising the largest `distance + radius` over circle
  centres (the enclosing circle) and by the extent along that direction (the size), with a sweep of other directions to show no view is smaller or larger.
* **A structure of several fragments has no shape of its own.** The embedder packs the pieces together at an arbitrary offset, so the eight outputs (Geometry Analysis measures the whole structure) are
  declined for one, from the result's own record, in Results and in the project table alike. A result that does not record a count (an earlier build's) is declined as unknown, not read as one piece. The
  ten always-on shape descriptors are NOT asked: they are computed on the ChEMBL parent compound and refused by the producer when there is none, so a salt is handled where they are made.
* **Only a number measured on the stored conformer, as it is, is the conformer's.** Geometry Analysis can measure a generated or a relaxed geometry, or scale its radii; its record says which, and a
  score reads none of them.
"""

from __future__ import annotations

import datetime
import math

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem
from rdkit.Chem import AllChem
from scipy.optimize import minimize

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import FRAGMENTS_KEY, canonical_conformer, fragment_count, geometry_provenance
from openchem.chem.projection_geometry import shape_descriptors
from openchem.domain.calculator import GEOMETRY, CalculationRequest
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_definition import ScoreDefinition
from openchem.domain.score_outputs import APPROVED, AS_STORED, AS_STORED_UNSCALED, approved_output
from openchem.domain.score_value import FRAGMENTS_KEY as DOMAIN_FRAGMENTS_KEY
from openchem.domain.score_value import (
    InputState,
    ScoreStatus,
    evaluate_score,
    not_applicable_reason,
    read_output,
)
from openchem.services.score_service import ScoreService
from tests.test_score_value import _entries

_GEOMETRY_OUTPUTS = [entry for entry in APPROVED if entry.input == GEOMETRY]
_SIZES = [entry for entry in _GEOMETRY_OUTPUTS if entry.output_id.startswith("calculator:geometry_analysis:")]
_BONDI = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52}  # Bondi's radii for the elements the molecules below hold, written out here and not read from the producer's table
_MOLECULES = ["CCCCO", "c1ccccc1C(=O)O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"]
_AREA = "calculator:geometry_analysis:Max projection area"
_MAX_RADIUS = "calculator:geometry_analysis:Max radius (from centroid)"


def _drain(qapp):
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(60):
        qapp.processEvents()


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture()
def services():
    return build_service_container()


def _embedded(smiles: str, seed: int = 7, *, relax: bool = True):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    if relax:
        AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _sizes(registry, mol, **parameters):
    """Geometry Analysis through the registry, as the batch and the Properties panel call it, with `parameters` over its defaults."""
    definition = registry.get("geometry_analysis")
    arguments = {p.name: p.default for p in definition.parameters} | parameters
    result = registry.compute("geometry_analysis", Chem.Mol(mol), "m", arguments)
    return {fact.label: fact for fact in result.facts}, result


# --- the eight numbers are what their endpoint texts say -------------------------------------------------------------------------------------


@pytest.mark.parametrize("smiles", _MOLECULES)
def test_the_two_radii_are_the_distances_of_every_atom_from_the_unweighted_centroid(registry, smiles):
    mol = _embedded(smiles)
    xyz = mol.GetConformer().GetPositions()
    assert mol.GetNumAtoms() > mol.GetNumHeavyAtoms(), "the hydrogens are atoms of the conformer"
    distances = np.linalg.norm(xyz - xyz.mean(axis=0), axis=1)
    facts, _ = _sizes(registry, mol)
    assert facts["Max radius (from centroid)"].value == pytest.approx(distances.max(), rel=1e-9)
    assert facts["Mean radius (from centroid)"].value == pytest.approx(distances.mean(), rel=1e-9)
    masses = np.array([atom.GetMass() for atom in mol.GetAtoms()])
    weighted = np.linalg.norm(xyz - (masses[:, None] * xyz).sum(0) / masses.sum(), axis=1)
    assert facts["Max radius (from centroid)"].value != pytest.approx(weighted.max(), rel=1e-4), "unweighted, which is what the endpoint text says"


def _atoms(mol):
    return mol.GetConformer().GetPositions(), np.array([_BONDI[atom.GetSymbol()] for atom in mol.GetAtoms()])


def _plane(direction):
    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    helper = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(d, helper)
    u /= np.linalg.norm(u)
    return d, u, np.cross(d, u)


def _shadow_area(xyz, radii, direction, cell):
    """The area of the union of the atoms' circles seen along `direction`, counted on a grid of `cell` Å."""
    _d, u, v = _plane(direction)
    px, py = xyz @ u, xyz @ v
    xs = np.arange((px - radii).min(), (px + radii).max() + cell, cell) + cell / 2
    ys = np.arange((py - radii).min(), (py + radii).max() + cell, cell) + cell / 2
    gx, gy = np.meshgrid(xs, ys)
    covered = np.zeros(gx.shape, dtype=bool)
    for x, y, r in zip(px, py, radii):
        covered |= (gx - x) ** 2 + (gy - y) ** 2 <= r * r
    return covered.sum() * cell * cell


def _enclosing_radius(xyz, radii, direction):
    """The smallest circle that contains every atom's circle: the least over centres of the largest (distance to an atom + its radius)."""
    _d, u, v = _plane(direction)
    points = np.column_stack([xyz @ u, xyz @ v])
    start = points.mean(axis=0)
    # The epigraph form (minimise R subject to R >= distance + radius for every atom) is smooth, which a simplex search over a maximum of cones is not: it stalls short of the minimum.
    constraints = [{"type": "ineq", "fun": lambda z, i=i: z[2] - (np.hypot(z[0] - points[i, 0], z[1] - points[i, 1]) + radii[i])} for i in range(len(radii))]
    z0 = np.array([start[0], start[1], float(np.max(np.linalg.norm(points - start, axis=1) + radii))])
    found = minimize(lambda z: z[2], z0, jac=lambda z: np.array([0.0, 0.0, 1.0]), constraints=constraints, method="SLSQP", options={"ftol": 1e-13, "maxiter": 1000})
    assert found.success, found.message
    return float(found.x[2])


def _hemisphere(count):
    """`count` directions spread over a hemisphere (a shadow is the same from either side)."""
    index = np.arange(count) + 0.5
    z = index / count
    angle = math.pi * (1 + 5**0.5) * index
    ring = np.sqrt(1 - z * z)
    return np.column_stack([ring * np.cos(angle), ring * np.sin(angle), z])


@pytest.mark.parametrize("smiles", _MOLECULES)
def test_the_six_projection_numbers_are_what_the_endpoint_texts_say(registry, smiles):
    mol = _embedded(smiles)
    xyz, radii = _atoms(mol)
    shape = shape_descriptors(mol)
    facts, _ = _sizes(registry, mol)
    for kind, label in (("min", "Min"), ("max", "Max")):
        direction = getattr(shape, f"{kind}_projection_direction")
        d = _plane(direction)[0]
        assert facts[f"{label} projection area"].value == pytest.approx(_shadow_area(xyz, radii, direction, 0.01), rel=5e-3), kind
        assert facts[f"{label} projection radius"].value == pytest.approx(_enclosing_radius(xyz, radii, direction), rel=1e-4), kind
        assert facts[f"Size perpendicular to the {kind} projection"].value == pytest.approx(float((xyz @ d + radii).max() - (xyz @ d - radii).min()), rel=1e-9), kind


@pytest.mark.parametrize("smiles", _MOLECULES)
def test_no_viewing_direction_has_a_smaller_or_larger_shadow_than_the_two_the_numbers_name(registry, smiles):
    """Not the producer's own search again: a sweep made here, in a coarser grid, so the margin is the grid's."""
    mol = _embedded(smiles)
    xyz, radii = _atoms(mol)
    facts, _ = _sizes(registry, mol)
    areas = [_shadow_area(xyz, radii, direction, 0.05) for direction in _hemisphere(200)]
    assert min(areas) >= facts["Min projection area"].value * 0.97
    assert max(areas) <= facts["Max projection area"].value * 1.03


def test_the_eight_outputs_are_the_eight_facts_of_one_report_each_typed_in_the_unit_the_entry_carries(registry):
    facts, _ = _sizes(registry, _embedded("CCCCO"))
    for entry in _SIZES:
        label = entry.output_id.partition(":")[2].partition(":")[2]
        assert facts[label].units == entry.carried_as and isinstance(facts[label].value, float), entry.output_id
    assert len(_SIZES) == 8


# --- what a result records about itself: the stamp the reader decides by ---------------------------------------------------------------------------


def test_the_two_spellings_of_the_fragments_key_are_one():
    assert FRAGMENTS_KEY == DOMAIN_FRAGMENTS_KEY == "input_fragments"


@pytest.mark.parametrize(("smiles", "pieces"), [("CCO", 1), ("CC(=O)[O-].[Na+]", 2), ("CN(C)C(=N)N=C(N)N.Cl", 2), ("O.O.[Na+].[Cl-]", 4)])
def test_a_conformer_says_how_many_separate_pieces_it_is(smiles, pieces):
    mol = _embedded(smiles, relax=False)
    assert fragment_count(Chem.MolToMolBlock(mol)) == pieces


def test_the_count_is_none_when_the_molblock_cannot_be_read_and_the_stamp_then_leaves_the_key_out():
    assert fragment_count("") is None and fragment_count("not a molblock") is None
    model = MoleculeModel(display_name="m")
    model.conformers = [ConformerModel(molblock="not a molblock", energy=1.0, method="mmff94")]
    assert FRAGMENTS_KEY not in geometry_provenance(model, GEOMETRY), "unknown is left out, and the reader refuses what does not say"


def test_the_stamp_counts_the_conformer_every_calculation_uses():
    model = MoleculeModel(display_name="salt")
    model.conformers = [ConformerModel(molblock=Chem.MolToMolBlock(_embedded("CC(=O)[O-].[Na+]", relax=False)), energy=-1.0, method="mmff94")]
    assert geometry_provenance(model, GEOMETRY)[FRAGMENTS_KEY] == 2
    assert FRAGMENTS_KEY not in geometry_provenance(model, "drawing"), "a drawing result has no conformer to count"


# --- the reading rule --------------------------------------------------------------------------------------------------------------------------------


def _record(**overrides):
    values = {FRAGMENTS_KEY: 1, "input_geometry": "gfp-handed", "measured_geometry": "gfp-handed", "radius_scale": 1.0}
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


@pytest.mark.parametrize("entry", _GEOMETRY_OUTPUTS, ids=lambda entry: entry.output_id)
def test_one_piece_measured_on_the_stored_conformer_is_read_for_every_geometry_output(entry):
    assert not_applicable_reason(entry, _record()) == ""


@pytest.mark.parametrize("entry", _SIZES, ids=lambda entry: entry.output_id)
@pytest.mark.parametrize("pieces", [2, 3])
def test_several_fragments_are_declined_for_every_size_and_the_reason_says_how_many(entry, pieces):
    reason = not_applicable_reason(entry, _record(**{FRAGMENTS_KEY: pieces}))
    assert f"{pieces} separate fragments" in reason and "score the parent structure" in reason and "whole structure" in reason


@pytest.mark.parametrize("count", [None, 0, -1, True, "1", 1.0])
@pytest.mark.parametrize("entry", _SIZES, ids=lambda entry: entry.output_id)
def test_a_size_that_does_not_say_how_many_pieces_is_declined_and_not_read_as_one(entry, count):
    reason = not_applicable_reason(entry, _record(**{FRAGMENTS_KEY: count}))
    assert "does not say how many separate pieces" in reason and "run it again" in reason


@pytest.mark.parametrize("entry", [entry for entry in _GEOMETRY_OUTPUTS if entry not in _SIZES], ids=lambda entry: entry.output_id)
@pytest.mark.parametrize("count", [None, 2, 5])
def test_a_shape_descriptor_is_never_asked_about_fragments(entry, count):
    """It is computed on the ChEMBL parent compound (`chem/components.py`), or refused by the producer when there is none: a salt is handled where the descriptor is made, and a count on the whole
    conformer says nothing about the structure it was measured on."""
    assert not entry.whole_structure
    assert not_applicable_reason(entry, _record(**{FRAGMENTS_KEY: count})) == ""


def test_a_drawing_output_has_none_of_these_questions():
    assert not_applicable_reason(approved_output("descriptor:tpsa"), {FRAGMENTS_KEY: 5}) == ""
    assert not_applicable_reason(approved_output("descriptor:tpsa"), None) == ""


@pytest.mark.parametrize("entry", _SIZES, ids=lambda entry: entry.output_id)
def test_a_geometry_that_is_not_the_stored_one_is_declined_for_every_size(entry):
    reason = not_applicable_reason(entry, _record(measured_geometry="gfp-other"))
    assert "another geometry than the stored conformer" in reason and "default settings" in reason


def test_the_reason_names_how_it_was_not_the_stored_conformer():
    entry = approved_output(_MAX_RADIUS)
    assert "relaxed with MMFF94" in not_applicable_reason(entry, _record(measured_geometry="x", optimise_projection=True))
    assert "the lowest of several" in not_applicable_reason(entry, _record(measured_geometry="x", conformer_policy="always"))


@pytest.mark.parametrize("missing", ["input_geometry", "measured_geometry"])
@pytest.mark.parametrize("entry", _SIZES, ids=lambda entry: entry.output_id)
def test_a_size_whose_record_does_not_say_which_geometry_it_measured_is_declined(entry, missing):
    assert "does not say which geometry" in not_applicable_reason(entry, _record(**{missing: None}))


def test_the_ten_shape_descriptors_are_not_asked_which_geometry_a_calculator_measured():
    """A descriptor is computed on the conformer it is handed and has no options that change that; only the fragment question applies to it."""
    assert not_applicable_reason(approved_output("descriptor:pmi1"), _record(measured_geometry="x", radius_scale=3.0)) == ""


@pytest.mark.parametrize("entry", [entry for entry in _SIZES if entry.measured_as == AS_STORED_UNSCALED], ids=lambda entry: entry.output_id)
@pytest.mark.parametrize("scale", [1.2, 0.5, 3.0])
def test_a_projection_measured_with_scaled_radii_is_declined_and_says_by_how_much(entry, scale):
    assert f"scaled by {scale:g}" in not_applicable_reason(entry, _record(radius_scale=scale))


@pytest.mark.parametrize("entry", [entry for entry in _SIZES if entry.measured_as == AS_STORED_UNSCALED], ids=lambda entry: entry.output_id)
@pytest.mark.parametrize("scale", [None, True, "1.0"])
def test_a_projection_whose_record_does_not_say_its_scale_is_declined(entry, scale):
    assert "does not say how the van der Waals radii were scaled" in not_applicable_reason(entry, _record(radius_scale=scale))


def test_a_scale_of_exactly_one_is_read_whether_it_was_stored_as_a_float_or_an_integer():
    entry = approved_output(_AREA)
    assert not_applicable_reason(entry, _record(radius_scale=1)) == "" and not_applicable_reason(entry, _record(radius_scale=1.0)) == ""


@pytest.mark.parametrize("entry", [entry for entry in _SIZES if entry.measured_as == AS_STORED], ids=lambda entry: entry.output_id)
def test_the_radii_from_the_centroid_do_not_depend_on_the_projection_scale(entry):
    """`radius_scale` rescales the projection figures only; the radii from the centroid are distances between atom centres."""
    assert not_applicable_reason(entry, _record(radius_scale=2.5)) == ""


def test_the_two_asking_levels_are_what_the_entries_say():
    assert {entry.measured_as for entry in _SIZES} == {AS_STORED, AS_STORED_UNSCALED}
    assert [entry.measured_as for entry in _SIZES].count(AS_STORED) == 2
    assert all(entry.whole_structure for entry in _SIZES) and not any(entry.whole_structure for entry in APPROVED if entry not in _SIZES)


# --- through `read_output`, with results put in the store directly --------------------------------------------------------------------------------


def _stored(label, value, units="A", *, key="", fingerprint="gfp-now", **record):
    fact = Fact(FactCategory.GEOMETRY, label, value, f"{value:.2f}", "Geometry", Basis.DETERMINISTIC, units=units)
    provenance = Provenance(created_by="core", method="rdkit", parameters={
        "input_conformer_id": "1a2b3c4d5e6f", "input_conformer_index": 0, "input_conformer_energy": -4.5, "input_force_field": "MMFF94", **_record(**record),
    })
    result = ReportResult(molecule_uuid="m", report_id="geometry_analysis", name="Geometry", facts=(fact,), cache_state=CacheState.COMPLETED, provenance=provenance)
    return StoredResult(ResultIdentity("m", "geometry_analysis", GEOMETRY, fingerprint, "geometry_analysis", key), result)


_MAX_AREA_LABEL = "Max projection area"


def test_a_current_size_is_read_and_names_its_conformer():
    read = read_output(_AREA, _entries(_stored(_MAX_AREA_LABEL, 51.4, "A^2")), 3)
    assert read.state is InputState.READ and read.value == pytest.approx(51.4)
    assert read.geometry.startswith("conformer 1 (id 1a2b3c4d") and "MMFF94 energy -4.50 kcal/mol" in read.geometry


def test_a_result_with_scaled_radii_is_set_aside_and_the_unscaled_one_beside_it_is_read():
    """Two current results of one calculator under different settings used to be `AMBIGUOUS` when their numbers differed; a scaled one is not a candidate at all."""
    plain = _stored(_MAX_AREA_LABEL, 51.4, "A^2", key="plain")
    scaled = _stored(_MAX_AREA_LABEL, 60.0, "A^2", key="scaled", radius_scale=1.2)
    read = read_output(_AREA, _entries(plain, scaled), 3)
    assert read.state is InputState.READ and read.value == pytest.approx(51.4)


def test_a_scaled_result_alone_gives_no_number_and_says_why():
    read = read_output(_AREA, _entries(_stored(_MAX_AREA_LABEL, 60.0, "A^2", radius_scale=1.2)), 3)
    assert read.state is InputState.NOT_APPLICABLE and read.value is None and "scaled by 1.2" in read.note
    value = evaluate_score(_definition("a", [("a", _AREA)]), _entries(_stored(_MAX_AREA_LABEL, 60.0, "A^2", radius_scale=1.2)), 3)
    assert value.status is ScoreStatus.REFUSED and value.value is None and "scaled by 1.2" in value.reason


def test_the_same_scaled_result_is_no_obstacle_to_the_radii_from_the_centroid():
    stored = _stored("Max radius (from centroid)", 4.9, radius_scale=1.2)
    assert read_output(_MAX_RADIUS, _entries(stored), 3).state is InputState.READ


def test_a_salt_gives_no_size_whatever_the_calculator_measured():
    stored = _stored(_MAX_AREA_LABEL, 18.9, "A^2", **{FRAGMENTS_KEY: 2})
    read = read_output(_AREA, _entries(stored), 3)
    assert read.state is InputState.NOT_APPLICABLE and read.value is None and "2 separate fragments" in read.note


def test_a_unit_other_than_the_one_approved_is_still_refused_and_nothing_is_converted():
    read = read_output(_AREA, _entries(_stored(_MAX_AREA_LABEL, 51.4, "Å^2")), 3)
    assert read.state is InputState.UNIT and read.value is None


def _definition(formula, inputs, unit="Å^2", label="Footprint"):
    return ScoreDefinition(score_id="user.t", label=label, formula=formula, result_unit=unit, inputs=tuple(inputs))


# --- through the real services ----------------------------------------------------------------------------------------------------------------------


def _model(services, smiles, *, relax: bool = True, name: str = "m"):
    """A molecule with one conformer, MMFF94-relaxed or as the embedder left it."""
    engine = services.chemistry_engine
    model = MoleculeModel(display_name=name)
    engine.set_structure_from_smiles(model, smiles)
    mol = _embedded(smiles, relax=relax)
    model.conformers = [ConformerModel(molblock=engine.mol_to_molblock(mol), energy=-1.0 if relax else None, method="mmff94" if relax else "etkdg")]
    return model


def _scored(services, model, *definitions):
    project = ProjectModel(name="sizes")
    project.molecules.append(model)
    services.result_store_service.set_project(project)
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry, today=lambda: datetime.date(2026, 10, 17))
    service.set_project(project)
    return service, [service.create(**definition) for definition in definitions]


def _run(services, qapp, model, **parameters):
    definition = services.calculator_registry.get("geometry_analysis")
    arguments = {p.name: p.default for p in definition.parameters} | parameters
    services.descriptor_service.run_calculator(model, CalculationRequest(calculator_id="geometry_analysis", molecule_uuid=model.uuid, parameters=arguments))
    _drain(qapp)


_FOOTPRINT = dict(label="Footprint ratio", formula="a / b", result_unit="1", inputs=[("a", _AREA), ("b", "calculator:geometry_analysis:Min projection area")])
_REACH = dict(label="Reach", formula="2 * a", result_unit="Å", inputs=[("a", _MAX_RADIUS)])


def test_a_score_over_the_sizes_is_the_formula_of_the_numbers_of_the_conformer_every_calculation_uses(services, qapp):
    model = _model(services, "CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    service, _ = _scored(services, model, _FOOTPRINT, _REACH)
    assert all(value.status is ScoreStatus.REFUSED and "not been calculated on this molecule's conformer yet" in value.reason for value in service.values_for(model))
    _run(services, qapp, model)
    mol = services.chemistry_engine.mol_from_molblock(canonical_conformer(model).molblock)
    xyz, radii = _atoms(mol)
    shape = shape_descriptors(mol)
    footprint, reach = service.values_for(model)
    assert footprint.status is ScoreStatus.VALUE and reach.status is ScoreStatus.VALUE
    assert reach.value == pytest.approx(2 * np.linalg.norm(xyz - xyz.mean(axis=0), axis=1).max(), rel=1e-9)
    assert footprint.value == pytest.approx(shape.max_projection_area / shape.min_projection_area, rel=1e-9)
    assert f"id {canonical_conformer(model).conformer_id[:8]}" in reach.inputs[0].geometry, "the conformer is named in the evidence"


def test_a_geometry_analysis_run_with_scaled_radii_is_not_what_a_score_reads_and_the_default_run_is(services, qapp):
    model = _model(services, "CCCCO")
    service, _ = _scored(services, model, _FOOTPRINT, _REACH)
    _run(services, qapp, model, radius_scale=1.2)
    footprint, reach = service.values_for(model)
    assert footprint.status is ScoreStatus.REFUSED and "scaled by 1.2" in footprint.reason
    assert reach.status is ScoreStatus.VALUE, "the radii from the centroid are not rescaled by it"
    _run(services, qapp, model)
    (footprint, _reach) = service.values_for(model)
    assert footprint.status is ScoreStatus.VALUE, "two stored results, two settings: the unscaled one is read and the scaled one is no obstacle"
    mol = services.chemistry_engine.mol_from_molblock(canonical_conformer(model).molblock)
    shape = shape_descriptors(mol)
    assert footprint.value == pytest.approx(shape.max_projection_area / shape.min_projection_area, rel=1e-9)


@pytest.mark.parametrize(
    ("parameters", "how"),
    [({"optimise_projection": True}, "relaxed with MMFF94"), ({"conformer_policy": "always"}, "the lowest of several")],
)
def test_a_geometry_analysis_run_on_another_geometry_than_the_stored_conformer_is_refused_by_the_score(services, qapp, parameters, how):
    """The raw embedding is not a minimum, so relaxing a copy of it, or choosing the lowest of several, measures another geometry than the one every calculation uses."""
    model = _model(services, "CCCCCCCC(=O)O", relax=False)
    service, _ = _scored(services, model, _FOOTPRINT, _REACH)
    _run(services, qapp, model, **parameters)
    footprint, reach = service.values_for(model)
    for value in (footprint, reach):
        assert value.status is ScoreStatus.REFUSED and value.value is None, value.definition.label
        assert how in value.reason and "default settings" in value.reason
    _run(services, qapp, model)
    assert all(value.status is ScoreStatus.VALUE for value in service.values_for(model)), "the default run beside it is read, and the other is no obstacle"


def test_a_salt_has_no_size_and_its_parent_has_one(services, qapp):
    salt = _model(services, "CC(=O)[O-].[Na+]", relax=False, name="Sodium acetate")
    service, _ = _scored(services, salt, _REACH)
    _run(services, qapp, salt)
    (value,) = service.values_for(salt)
    assert value.status is ScoreStatus.REFUSED and value.value is None
    assert "2 separate fragments" in value.reason and "score the parent structure" in value.reason
    parent = _model(services, "CC(=O)[O-]", relax=False, name="Acetate")
    service_two, _ = _scored(services, parent, _REACH)
    _run(services, qapp, parent)
    assert service_two.values_for(parent)[0].status is ScoreStatus.VALUE


def test_a_salts_shape_descriptor_is_the_producers_to_decide_and_a_size_of_the_same_salt_is_declined_here(services, qapp):
    """The two outputs of one structure, answered by two different rules. The always-on shape descriptors are computed on the ChEMBL parent compound, so metformin hydrochloride's radius of gyration is
    metformin's and is read; Geometry Analysis measures the whole structure, so its size of the same conformer is declined."""
    salt = _model(services, "CN(C)C(=N)N=C(N)N.Cl", relax=False, name="Metformin hydrochloride")
    service, _ = _scored(services, salt, _REACH, dict(label="Spread", formula="2 * rg", result_unit="Å", inputs=[("rg", "descriptor:radius_of_gyration")]))
    _run(services, qapp, salt)
    services.descriptor_service.request_descriptors(salt, GEOMETRY)
    _drain(qapp)
    reach, spread = service.values_for(salt)
    assert reach.status is ScoreStatus.REFUSED and "2 separate fragments" in reach.reason
    assert spread.status is ScoreStatus.VALUE, spread.reason

    mixture = _model(services, "CC(=O)[O-].[Na+]", relax=False, name="Sodium acetate")
    service_two, _ = _scored(services, mixture, dict(label="Spread", formula="2 * rg", result_unit="Å", inputs=[("rg", "descriptor:radius_of_gyration")]))
    services.descriptor_service.request_descriptors(mixture, GEOMETRY)
    _drain(qapp)
    (refused,) = service_two.values_for(mixture)
    assert refused.status is ScoreStatus.REFUSED and "Mixture: no single parent" in refused.reason, "the producer's own refusal, which is not this rule's"


def test_the_assistant_is_told_the_state_and_why(services, qapp):
    from openchem.domain.result_envelope import SCORES_NOTE, score_envelope_of

    model = _model(services, "CC(=O)[O-].[Na+]", relax=False)
    service, _ = _scored(services, model, _REACH)
    _run(services, qapp, model)
    (value,) = service.values_for(model)
    item = score_envelope_of(value)["inputs"][0]
    assert item["state"] == "not_applicable" and "2 separate fragments" in item["note"] and "value" not in item
    assert "not_applicable" in SCORES_NOTE and "Geometry Analysis" in SCORES_NOTE
