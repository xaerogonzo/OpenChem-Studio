"""Scores over a conformer's geometry: the ten shape descriptors, read from the conformer every calculation uses (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

Four things are pinned, because each was a way to ship a wrong number:

* **The declared units are what the numbers do.** Four of the ten had no unit although they are not dimensionless (the three principal moments are amu*Å^2, the inertial shape factor
  its inverse); a score over one would have passed the unit check while adding a moment of inertia to a plain number.
* **An output has one input, and only a result of that input is read for it.** A drawing's result is never read for a geometry output, and a geometry result is current only for the
  conformer every calculation uses NOW, so a number of another conformer is never offered in its place.
* **The refusals say what is true**: a molecule with no conformer needs one; a result measured for an earlier geometry says so.
* **Through the real services**, with a conformer that really changes (the lowest-energy one, and an ORCA-optimised one landing), the score follows the geometry and the old number is refused
  until the descriptors have been measured again.
"""

from __future__ import annotations

import datetime
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors3D

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import canonical_conformer, geometry_provenance
from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.descriptor_providers import SHAPE_DESCRIPTOR_UNITS, RDKitDescriptorProvider
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ORCA_OPTIMIZED, ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.score_answer import project_score_answers
from openchem.domain.score_definition import ScoreDefinition
from openchem.domain.score_formula import FormulaError
from openchem.domain.score_outputs import APPROVED, READ_FROM, approved_output, check_inputs, unit_of
from openchem.domain.score_value import (
    EARLIER_GEOMETRY,
    NEEDS_A_CONFORMER,
    InputState,
    ScoreStatus,
    evaluate_score,
    geometry_text,
    read_output,
)
from openchem.services.score_service import ScoreService
from tests.test_score_value import _FP, _entries

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sweep_score_outputs as sweep_tool  # noqa: E402

_GEOMETRY_ENTRIES = [entry for entry in APPROVED if entry.input == GEOMETRY]
_RG = "descriptor:radius_of_gyration"
_ID = "1a2b3c4d5e6f"


# --- the declared units are what the numbers do --------------------------------------------------------------------------------------


def _embedded(smiles: str = "CCCCO", seed: int = 7):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _shape_values(mol) -> dict[str, float]:
    return {v.descriptor_id: v.value for v in RDKitDescriptorProvider().compute(mol, "m") if v.descriptor_id in SHAPE_DESCRIPTOR_UNITS}


def _lengths_scaled(mol, factor: float):
    scaled = Chem.Mol(mol)
    conformer = scaled.GetConformer()
    for index in range(scaled.GetNumAtoms()):
        point = conformer.GetAtomPosition(index)
        conformer.SetAtomPosition(index, (point.x * factor, point.y * factor, point.z * factor))
    return scaled


def test_the_providers_declared_unit_is_the_one_the_approved_entry_carries():
    for entry in _GEOMETRY_ENTRIES:
        assert SHAPE_DESCRIPTOR_UNITS[entry.output_id.partition(":")[2]] == entry.carried_as, entry.output_id


@pytest.mark.parametrize("smiles", ["CCCCO", "c1ccccc1C(=O)O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"])
def test_each_numbers_length_dependence_is_the_one_its_declared_unit_says(smiles):
    """Double every length: a quantity of dimension length^n becomes 2^n times as large. The unit of each entry names its Å exponent, so a unit that is not what the number does fails here."""
    mol = _embedded(smiles)
    base, doubled = _shape_values(mol), _shape_values(_lengths_scaled(mol, 2.0))
    for entry in _GEOMETRY_ENTRIES:
        descriptor_id = entry.output_id.partition(":")[2]
        exponent = dict(unit_of(entry).parts).get("Å", 0)
        if base[descriptor_id] == 0:
            continue  # a flat ring's plane of best fit is zero to rounding and has no ratio
        assert doubled[descriptor_id] / base[descriptor_id] == pytest.approx(2.0**exponent, rel=1e-6), (entry.output_id, exponent)


def test_the_principal_moments_are_the_mass_weighted_inertia_tensor_in_amu_angstrom_squared():
    """Not an assumption: an inertia tensor built by hand from the atomic masses (amu) and the coordinates (Å) has RDKit's three numbers as its eigenvalues. That is the mass half
    of `amu*Å^2`, and it makes the inertial shape factor (the middle moment over the product of the other two) its inverse."""
    import numpy as np

    mol = _embedded()
    conformer = mol.GetConformer()
    masses = np.array([atom.GetMass() for atom in mol.GetAtoms()])
    xyz = np.array([[conformer.GetAtomPosition(i).x, conformer.GetAtomPosition(i).y, conformer.GetAtomPosition(i).z] for i in range(mol.GetNumAtoms())])
    offsets = xyz - (masses[:, None] * xyz).sum(0) / masses.sum()
    tensor = sum(m * ((v @ v) * np.eye(3) - np.outer(v, v)) for m, v in zip(masses, offsets))
    by_hand = np.sort(np.linalg.eigvalsh(tensor))
    values = _shape_values(mol)
    assert [values["pmi1"], values["pmi2"], values["pmi3"]] == pytest.approx(list(by_hand), rel=1e-6)
    assert values["inertial_shape_factor"] == pytest.approx(values["pmi2"] / (values["pmi1"] * values["pmi3"]), rel=1e-9)
    assert values["npr1"] == pytest.approx(values["pmi1"] / values["pmi3"], rel=1e-9) and values["npr2"] == pytest.approx(values["pmi2"] / values["pmi3"], rel=1e-9)
    assert values["radius_of_gyration"] == pytest.approx(Descriptors3D.RadiusOfGyration(mol), rel=1e-12)


def test_a_moment_of_inertia_cannot_be_added_to_a_ratio_but_the_moments_compose():
    """The reason the units had to be declared: with no unit these four read as dimensionless, and a moment of inertia added to a ratio (or to the shape factor's inverse) would have been
    accepted. A bare number in a formula takes the unit of what it is added to, so the check bites on two OUTPUTS of different units, which is what is tried here."""
    from openchem.domain.score_definition import check_computation

    def definition(formula, inputs, unit):
        return ScoreDefinition(score_id="user.t", label="Wide or narrow", formula=formula, result_unit=unit, inputs=tuple(inputs))

    moment = ("p", "descriptor:pmi1")
    with pytest.raises(FormulaError):
        check_computation(definition("p + r", [moment, ("r", "descriptor:npr1")], "amu*Å^2"))
    check_computation(definition("p + 1", [moment], "amu*Å^2"))
    check_computation(definition("p + q", [moment, ("q", "descriptor:pmi3")], "amu*Å^2"))
    check_computation(definition("p / q", [moment, ("q", "descriptor:pmi3")], "1"))
    check_computation(definition("s * q", [("s", "descriptor:inertial_shape_factor"), ("q", "descriptor:pmi2")], "1"))
    with pytest.raises(FormulaError):
        check_computation(definition("s + r", [("s", "descriptor:inertial_shape_factor"), ("r", "descriptor:npr2")], "1"))


def test_two_different_shape_outputs_may_share_a_formula_and_the_ratios_of_moments_are_expressible():
    check_inputs([("a", "descriptor:pmi1"), ("b", "descriptor:pmi2"), ("c", "descriptor:pmi3"), ("rg", _RG), ("pbf", "descriptor:pbf")])


# --- what a geometry result says about itself ----------------------------------------------------------------------------------------


def test_geometry_text_reads_exactly_the_keys_geometry_provenance_writes():
    model = MoleculeModel(display_name="m")
    model.conformers = [ConformerModel(molblock="a", energy=2.0, method="mmff94"), ConformerModel(molblock="b", energy=-3.5, method="mmff94")]
    written = geometry_provenance(model, GEOMETRY)
    text = geometry_text(written)
    assert text.startswith("conformer 2 (id ") and written["input_conformer_id"][:8] in text and "energy -3.50 kcal/mol" in text


def test_geometry_text_says_less_when_the_provenance_says_less():
    assert geometry_text(None) == "" and geometry_text({}) == "" and geometry_text({"input_source": "drawing"}) == ""
    assert geometry_text({"input_conformer_id": _ID, "input_conformer_index": 0, "input_conformer_energy": None, "input_force_field": None}) == f"conformer 1 (id {_ID[:8]})"
    assert geometry_text({"input_conformer_id": _ID}) == f"a conformer (id {_ID[:8]})"
    assert geometry_text({"input_conformer_id": _ID, "input_conformer_index": 3, "input_conformer_energy": 1.234, "input_force_field": "MMFF94"}) == f"conformer 4 (id {_ID[:8]}, MMFF94 energy 1.23 kcal/mol)"
    assert "energy" not in geometry_text({"input_conformer_id": _ID, "input_conformer_index": 0, "input_conformer_energy": float("nan")})


# --- the reading rule, on results put in the store directly ---------------------------------------------------------------------------


def _shape(descriptor_id, value, units, *, calculation_input=GEOMETRY, fingerprint="gfp-now", index=1, energy=-12.3456, state=CacheState.COMPLETED, error=None, summary=None):
    provenance = Provenance(
        created_by="core", method="rdkit",
        parameters={"input_conformer_id": _ID, "input_conformer_index": index, "input_conformer_energy": energy, "input_force_field": "MMFF94"},
    )
    result = DescriptorValue(descriptor_id, descriptor_id, units, "shape", "rdkit", "m", value=value, cache_state=state, error=error, error_summary=summary, provenance=provenance)
    return StoredResult(ResultIdentity("m", f"descriptor:rdkit:{descriptor_id}", calculation_input, fingerprint, "rdkit"), result)


def _score(formula="2 * rg", inputs=(("rg", _RG),), unit="Å"):
    return ScoreDefinition(score_id="user.t", label="Wide or narrow", formula=formula, result_unit=unit, inputs=tuple(inputs))


def test_a_current_geometry_result_is_read_and_names_the_conformer_it_was_measured_on():
    value = evaluate_score(_score(), _entries(_shape("radius_of_gyration", 2.5, "Å")), 3)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(5.0)
    (item,) = value.inputs
    assert item.state is InputState.READ and item.calculation_input == GEOMETRY
    assert item.geometry == f"conformer 2 (id {_ID[:8]}, MMFF94 energy -12.35 kcal/mol)"
    line = next(line for line in project_score_answers([value], viewing="m", structure_version=1)[0].facts[0].evidence if line.startswith("rg = "))
    assert f"computed on {item.geometry}" in line and "the drawing" not in line


def test_a_drawing_input_still_says_it_was_computed_on_the_drawing():
    value = evaluate_score(_score("psa", (("psa", "descriptor:tpsa"),), "Å^2"), _entries(_shape("tpsa", 63.6, "Å²", calculation_input=DRAWING, fingerprint="fp-now")), 3)
    assert value.status is ScoreStatus.VALUE and value.inputs[0].calculation_input == READ_FROM and value.inputs[0].geometry == ""
    line = next(line for line in project_score_answers([value], viewing="m", structure_version=1)[0].facts[0].evidence if line.startswith("psa = "))
    assert "computed on the drawing" in line


def test_a_result_of_the_drawing_is_never_read_for_a_geometry_output_even_when_it_is_a_number():
    """The always-on descriptors used to be stored under both inputs; a drawing's number of a shape descriptor must not stand in for the conformer's."""
    entries = _entries(_shape("radius_of_gyration", 9.99, "Å", calculation_input=DRAWING, fingerprint="fp-now"))
    read = read_output(_RG, entries, 3)
    assert read.state is InputState.NOT_RUN and read.value is None
    assert evaluate_score(_score(), entries, 3).status is ScoreStatus.REFUSED


def test_a_result_of_a_geometry_is_never_read_for_a_drawing_output():
    entries = _entries(_shape("tpsa", 77.0, "Å²", calculation_input=GEOMETRY, fingerprint="gfp-now"))
    assert read_output("descriptor:tpsa", entries, 3).state is InputState.NOT_RUN


def test_a_number_measured_on_an_earlier_geometry_is_refused_and_never_offered():
    entries = _entries(_shape("radius_of_gyration", 2.5, "Å", fingerprint="gfp-old"))
    assert _FP[GEOMETRY] == "gfp-now"
    read = read_output(_RG, entries, 3)
    assert read.state is InputState.NOT_CURRENT and read.value is None and read.note == EARLIER_GEOMETRY
    value = evaluate_score(_score(), entries, 3)
    assert value.status is ScoreStatus.REFUSED and value.value is None and EARLIER_GEOMETRY in value.reason


def test_the_current_result_is_read_beside_an_earlier_one():
    # `fresh` names the record the application would replay: the one for the conformer used now.
    current = _shape("radius_of_gyration", 3.5, "Å")
    older = _shape("radius_of_gyration", 2.5, "Å", fingerprint="gfp-old")
    entries = _entries(older, current, fresh=[current])
    assert read_output(_RG, entries, 3).value == pytest.approx(3.5)


@pytest.mark.parametrize(
    ("conformers", "note"),
    [(0, NEEDS_A_CONFORMER), (3, "it has not been calculated on this molecule's conformer yet"), (None, "it has not been calculated for this molecule")],
)
def test_a_molecule_with_no_result_says_why_by_whether_it_has_a_conformer(conformers, note):
    read = read_output(_RG, _entries(), conformers)
    assert read.state is InputState.NOT_RUN and read.note == note


def test_a_drawing_output_never_says_it_needs_a_conformer():
    assert read_output("descriptor:tpsa", _entries(), 0).note == "it has not been calculated for this molecule"


def test_the_refusal_a_shape_descriptor_gives_a_flat_molecule_is_kept_and_says_so():
    stored = _shape("radius_of_gyration", None, "Å", state=CacheState.FAILED, error="This descriptor is measured from a real 3D conformer", summary="Needs a 3D conformer")
    read = read_output(_RG, _entries(stored), 3)
    assert read.state in (InputState.REFUSED, InputState.FAILED) and read.value is None and "Needs a 3D conformer" in read.note


def test_a_copy_that_carries_no_unit_is_refused_by_the_unit_rule_and_nothing_is_converted():
    """What a project saved before the units were declared holds for a principal moment."""
    read = read_output("descriptor:pmi1", _entries(_shape("pmi1", 268.3, "")), 3)
    assert read.state is InputState.UNIT and read.value is None and "nothing is converted" in read.note
    assert read_output("descriptor:pmi1", _entries(_shape("pmi1", 268.3, "amu·Å²")), 3).state is InputState.READ


# --- through the real services, with a conformer that really changes ------------------------------------------------------------------


def _drain(qapp):
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(60):
        qapp.processEvents()


@pytest.fixture()
def services():
    return build_service_container()


def _molecule_with_conformers(services, count: int = 4):
    """Hexanol with `count` real MMFF conformers, ordered so that the one with the SMALLEST radius of gyration is the lowest in energy."""
    engine = services.chemistry_engine
    model = MoleculeModel(display_name="Hexanol")
    engine.set_structure_from_smiles(model, "CCCCCCO")
    generated = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformers(engine.mol_from_model(model), num_conformers=count, optimize=True)
    blocks = [engine.mol_to_molblock(mol) for mol, _energy in generated]
    radii = [Descriptors3D.RadiusOfGyration(engine.mol_from_molblock(block)) for block in blocks]
    order = sorted(range(len(blocks)), key=lambda i: radii[i])
    model.conformers = [ConformerModel(molblock=blocks[i], energy=float(rank), method="mmff94") for rank, i in enumerate(order)]
    spread = radii[order[-1]] - radii[order[0]]
    assert spread > 1e-3, "the premise: the conformers differ in size, or this test could not tell one from another"
    return model


@pytest.fixture()
def scored(services, qapp):
    model = _molecule_with_conformers(services)
    project = ProjectModel(name="Shapes")
    project.molecules.append(model)
    services.result_store_service.set_project(project)
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry, today=lambda: datetime.date(2026, 10, 17))
    service.set_project(project)
    definition = service.create(label="Wide or narrow", formula="2 * rg", result_unit="Å", inputs=[("rg", _RG)])
    return services, service, model, definition


def _measure(services, qapp, model):
    services.descriptor_service.request_descriptors(model, GEOMETRY)
    _drain(qapp)


def _radius_of(services, conformer) -> float:
    return Descriptors3D.RadiusOfGyration(services.chemistry_engine.mol_from_molblock(conformer.molblock))


def test_before_the_shape_descriptors_are_measured_the_score_says_so_not_that_it_needs_a_conformer(scored):
    _services, service, model, _definition = scored
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.REFUSED and "not been calculated on this molecule's conformer yet" in value.reason


def test_a_molecule_with_no_conformer_needs_one(scored):
    services, service, model, _definition = scored
    model.conformers = []
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.REFUSED and NEEDS_A_CONFORMER in value.reason


def test_the_score_is_twice_the_radius_of_gyration_of_the_conformer_every_calculation_uses(scored, qapp):
    services, service, model, _definition = scored
    _measure(services, qapp, model)
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.VALUE, value.reason
    canonical = canonical_conformer(model)
    assert value.value == pytest.approx(2 * _radius_of(services, canonical), rel=1e-9), "an independent measurement of the same conformer"
    (item,) = value.inputs
    assert item.calculation_input == GEOMETRY and f"id {canonical.conformer_id[:8]}" in item.geometry and item.geometry.startswith("conformer 1 ")


def test_when_another_conformer_becomes_the_one_every_calculation_uses_the_old_number_is_refused_until_it_is_measured_again(scored, qapp):
    services, service, model, _definition = scored
    _measure(services, qapp, model)
    before = service.values_for(model)[0].value
    first, last = model.conformers[0], model.conformers[-1]
    first.energy, last.energy = last.energy, first.energy  # the largest conformer is now the lowest
    assert canonical_conformer(model) is last

    (refused,) = service.values_for(model)
    assert refused.status is ScoreStatus.REFUSED and refused.value is None and EARLIER_GEOMETRY in refused.reason, "the stale number is never offered"

    _measure(services, qapp, model)
    (after,) = service.values_for(model)
    assert after.status is ScoreStatus.VALUE and after.value == pytest.approx(2 * _radius_of(services, last), rel=1e-9)
    assert abs(after.value - before) > 1e-3, "and it is a different number: the score follows the geometry"
    assert f"id {last.conformer_id[:8]}" in after.inputs[0].geometry and after.inputs[0].geometry.startswith(f"conformer {len(model.conformers)} ")


def test_an_orca_optimized_geometry_landing_becomes_the_one_the_score_reads(scored, qapp):
    """The consequence the design record names: after an optimisation the canonical conformer changes, and a score over a shape descriptor changes with it."""
    services, service, model, _definition = scored
    _measure(services, qapp, model)
    before = service.values_for(model)[0].value
    other = model.conformers[-1]
    optimized = ConformerModel(molblock=other.molblock, energy=None, method=ORCA_OPTIMIZED)
    model.conformers.append(optimized)
    assert canonical_conformer(model) is optimized

    assert service.values_for(model)[0].status is ScoreStatus.REFUSED
    _measure(services, qapp, model)
    (after,) = service.values_for(model)
    assert after.status is ScoreStatus.VALUE and after.value == pytest.approx(2 * _radius_of(services, optimized), rel=1e-9)
    assert after.value != pytest.approx(before, abs=1e-3)


def test_a_drawings_number_for_the_same_descriptor_id_is_not_what_a_score_over_the_conformer_reads(scored, qapp):
    services, service, model, _definition = scored
    fingerprint = services.result_store_service.fingerprints_for(model)[DRAWING]
    drawing = DescriptorValue("radius_of_gyration", "Radius of Gyration", "Å", "shape", "rdkit", model.uuid, value=99.0, cache_state=CacheState.COMPLETED)
    services.result_store_service.store.put(StoredResult(ResultIdentity(model.uuid, "descriptor:rdkit:radius_of_gyration", DRAWING, fingerprint, "rdkit"), drawing))
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.REFUSED
    _measure(services, qapp, model)
    assert service.values_for(model)[0].value == pytest.approx(2 * _radius_of(services, canonical_conformer(model)), rel=1e-9) != 198.0


def test_the_results_reader_entry_names_the_conformer_in_its_evidence(scored, qapp):
    services, service, model, definition = scored
    _measure(services, qapp, model)
    (answer,) = service.answers_for(model.uuid, 1)
    (fact,) = answer.facts
    evidence = "\n".join(fact.evidence)
    assert f"computed on conformer 1 (id {canonical_conformer(model).conformer_id[:8]}" in evidence and fact.units == "Å"


# --- a project saved before the units were declared -----------------------------------------------------------------------------------


def test_only_a_shape_copy_in_an_old_unit_is_obsolete(services):
    check = services.descriptor_service.is_unit_superseded_shape_result
    assert check(_shape("pmi1", 268.3, "")) and check(_shape("inertial_shape_factor", 0.0353, ""))
    assert not check(_shape("pmi1", 268.3, "amu·Å²")) and not check(_shape("inertial_shape_factor", 0.0353, "1/(amu·Å²)"))
    assert not check(_shape("npr1", 0.1, "")), "a ratio declares no unit, and an empty one is right"
    assert not check(_shape("radius_of_gyration", 1.9, "Å")) and check(_shape("radius_of_gyration", 1.9, ""))
    assert not check(_shape("tpsa", 63.6, "Å²", calculation_input=DRAWING)), "not a shape descriptor"
    other = _shape("pmi1", 268.3, "")
    assert not check(StoredResult(ResultIdentity("m", "descriptor:other:pmi1", GEOMETRY, "gfp-now", "other"), other.result)), "a producer that is not the RDKit provider"


def test_opening_a_project_drops_a_shape_copy_in_an_old_unit_and_keeps_the_rest(services):
    model = MoleculeModel(display_name="Old")
    services.chemistry_engine.set_structure_from_smiles(model, "CCO")
    project = ProjectModel(name="old")
    project.molecules.append(model)
    store = SessionResultStore(project.uuid)
    old, fine = _shape("pmi1", 268.3, ""), _shape("pbf", 0.5, "Å")
    store.put(StoredResult(ResultIdentity(model.uuid, "descriptor:rdkit:pmi1", GEOMETRY, "gfp", "rdkit"), old.result))
    store.put(StoredResult(ResultIdentity(model.uuid, "descriptor:rdkit:pbf", GEOMETRY, "gfp", "rdkit"), fine.result))
    services.result_store_service.set_project(project, store)
    kept = {stored.result.descriptor_id for stored in services.result_store_service.store.all_results(model.uuid)}
    assert kept == {"pbf"}
    assert services.result_store_service.store.load_problems["retired"] == 1


def test_every_approved_geometry_output_resolves_to_a_descriptor_the_provider_makes_with_that_unit():
    provider = RDKitDescriptorProvider()
    for entry in _GEOMETRY_ENTRIES:
        descriptor_id = entry.output_id.partition(":")[2]
        assert descriptor_id in provider.geometric_descriptor_ids()
        assert approved_output(entry.output_id) is entry
    assert {entry.output_id.partition(":")[2] for entry in _GEOMETRY_ENTRIES} == set(provider.geometric_descriptor_ids())


# --- the surfaces that say what an output is read from -------------------------------------------------------------------------------------


def test_the_assistants_list_of_outputs_says_geometry_for_the_ten_and_nothing_for_the_rest():
    from openchem.domain.result_envelope import FULL, score_outputs_envelope

    rows = {row["output_id"]: row for row in score_outputs_envelope(APPROVED, FULL)["outputs"]}
    assert {output_id for output_id, row in rows.items() if row.get("input") == "geometry"} == {entry.output_id for entry in _GEOMETRY_ENTRIES}
    assert all("input" not in row for output_id, row in rows.items() if approved_output(output_id).input == READ_FROM), "a row with no input is the drawing's"
    assert rows["descriptor:pmi1"]["unit"] == "amu*Å^2" and rows["descriptor:pmi1"]["endpoint"] == "principal_moment_1"
    assert len(rows) == len(APPROVED)


def test_a_score_the_assistant_reads_says_which_conformer_a_shape_input_came_from_and_stays_silent_for_the_drawing():
    from openchem.domain.result_envelope import SCORES_NOTE, score_envelope_of

    shape = score_envelope_of(evaluate_score(_score(), _entries(_shape("radius_of_gyration", 2.5, "Å")), 3))["inputs"][0]
    assert shape["calculation_input"] == GEOMETRY and shape["conformer"].startswith("conformer 2 (id ") and shape["state"] == "read"
    drawing = score_envelope_of(evaluate_score(_score("psa", (("psa", "descriptor:tpsa"),), "Å^2"), _entries(_shape("tpsa", 63.6, "Å²", calculation_input=DRAWING, fingerprint="fp-now")), 3))["inputs"][0]
    assert "calculation_input" not in drawing and "conformer" not in drawing
    assert "never a conformer's" not in SCORES_NOTE, "that sentence was true until the shape outputs"
    assert "geometry" in SCORES_NOTE and "no conformer" in SCORES_NOTE and "earlier conformer" in SCORES_NOTE


def test_the_editors_picker_marks_what_needs_a_conformer():
    from openchem.domain.score_editor import output_choices

    choices = {choice.output_id: choice for choice in output_choices()}
    assert {output_id for output_id, choice in choices.items() if choice.input == GEOMETRY} == {entry.output_id for entry in _GEOMETRY_ENTRIES}
    assert choices["descriptor:pmi1"].text.endswith("[needs a conformer]") and "amu*Å^2" in choices["descriptor:pmi1"].text
    assert not choices["descriptor:tpsa"].text.endswith("[needs a conformer]")


def _swept(output_id, rows, calc_input, units=""):
    sweep = sweep_tool.Sweep()
    candidate = sweep_tool.Candidate(output_id, "label", "descriptor", output_id.partition(":")[2])
    candidate.observations = [(f"row{i}", calc_input, float(i + 1), units) for i in range(rows)]
    sweep.candidates[output_id] = candidate
    return sweep


def test_the_sweep_judges_a_geometry_entry_on_the_geometry_rows_and_no_others():
    entry = approved_output("descriptor:pmi1")
    census = {"support": {}}
    assert sweep_tool.entry_problems(entry, _swept(entry.output_id, 5, GEOMETRY, entry.carried_as), census) == []
    only_drawing = sweep_tool.entry_problems(entry, _swept(entry.output_id, 9, DRAWING, entry.carried_as), census)
    assert any("never a finite typed number on the geometry input" in problem for problem in only_drawing)
    assert any("at least 5 are needed" in problem for problem in sweep_tool.entry_problems(entry, _swept(entry.output_id, 3, GEOMETRY, entry.carried_as), census))
    wrong = sweep_tool.entry_problems(entry, _swept(entry.output_id, 5, GEOMETRY, ""), census)
    assert any("carries the units" in problem for problem in wrong), "the old, unit-less spelling is caught by the census"


def test_the_copy_guard_compares_outputs_of_one_input_only():
    first, second = approved_output("descriptor:pmi1"), approved_output("descriptor:pmi2")
    same = [1.0, 2.0, 3.0, 4.0, 5.0]

    def both(second_entry):
        sweep = sweep_tool.Sweep()
        for entry in (first, second_entry):
            candidate = sweep_tool.Candidate(entry.output_id, "label", "descriptor", entry.output_id.partition(":")[2])
            candidate.observations = [(f"row{i}", entry.input, value, "") for i, value in enumerate(same)]
            sweep.candidates[entry.output_id] = candidate
        return sweep

    copy = replace(second, endpoint="principal_moment_2")
    assert [(a.output_id, b.output_id) for a, b in sweep_tool.identical_pairs([first, copy], both(copy))] == [(first.output_id, copy.output_id)]
    on_the_drawing = replace(copy, input=DRAWING)
    assert sweep_tool.identical_pairs([first, on_the_drawing], both(on_the_drawing)) == [], "a number of the drawing and of a conformer are two measurements even where they agree"
