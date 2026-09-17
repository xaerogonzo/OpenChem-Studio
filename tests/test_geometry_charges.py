"""The geometry-dependent charge calculator: EEM and QEq on the stored conformer.

`tests/test_charge_equilibration.py` holds the solver against its papers.
This file holds the CALCULATOR against its contract, through the registry:
what it refuses, which atom each value belongs to, that the snapshot it was
handed is the only thing it reads, and that its identity separates what must
not share a result.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import geometry_charges as gc
from openchem.chem.calculation_input import resolve_calculation_input
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import GEOMETRY, CalculationRequest, CalculatorDefinition, RegistryExecution
from openchem.domain.common import ATOM_BASIS, EXPLICIT_H, HEAVY_ATOMS, TOTAL, CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import PerAtomDataComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.services.result_cache import parameters_key

CALCULATOR = "geometry_partial_charge"


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def _conformer(smiles: str, seed: int = 7) -> Chem.Mol:
    """A conformer as the app stores and resolves one: embedded with hydrogens,
    written to a molblock, read back keeping them."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    return ChemistryEngine().mol_from_molblock(Chem.MolToMolBlock(mol))


def _renumbered(mol: Chem.Mol, order: list[int]) -> Chem.Mol:
    return Chem.RenumberAtoms(mol, order)


# --- registration and identity ------------------------------------------------


def test_registered_on_geometry_offering_eem_first_and_qeq_under_its_a8_code():
    definition = _registry().get(CALCULATOR)
    assert definition.calculation_input == GEOMETRY
    assert definition.category == "charge"
    (method,) = [p for p in definition.parameters if p.name == "method"]
    # Ionescu 2013's two shipped models are APPENDED (preregistration §10), so the default and
    # every stored result's identity are unchanged -- which the next test pins.
    assert method.choices == ["eem_bultinck2002_part1", "qeq_rg1991_lambda_half_h_experimental",
                              "eem_ionescu2013_e_mpa_631gs_gas", "eem_ionescu2013_e_mpa_631gss_gas"]
    assert method.choice_labels == ["EEM, Bultinck 2002", "QEq, Rappé–Goddard 1991",
                                    "EEM, Ionescu 2013, Mulliken 6-31G*", "EEM, Ionescu 2013, Mulliken 6-31G**"]
    assert method.default == "eem_bultinck2002_part1"
    # A8: neither the HF-fitted hydrogen set nor the pre-registered reading is offered.
    assert not any("hf" in choice or "preregistered" in choice for choice in method.choices)


def test_the_eem_default_identity_is_the_one_recorded_before_qeq_was_offered():
    """A stored EEM result from before A8 must still be found: its identity is
    parameters_key of the defaults, pinned here at its pre-A8 value."""
    definition = _registry().get(CALCULATOR)
    defaults = {p.name: p.default for p in definition.parameters}
    assert parameters_key(defaults) == "c8a6d189021bbd3d35d4621f5b102f37"


def test_eem_output_is_unchanged_by_adding_qeq():
    """Values captured from the calculator before QEq's dispatch existed."""
    before = {
        0: -0.543078958401, 1: -0.055275894735, 2: 0.055889984435, 3: -0.635941577885, 4: 0.164243918641,
        5: -0.43014364712, 6: 0.281988639174, 7: 0.149251900807, 8: 0.17202170245, 9: 0.134577620593,
        10: 0.301309946117, 11: 0.281918050611, 12: 0.123238315313,
    }
    result = gc.compute_geometry_charges(_conformer("OCC(N)C=O"), "u", {})
    assert result.name == "Partial Charge (EEM, Bultinck 2002, 3D)" and result.method == "eem_bultinck2002_part1"
    assert set(result.values) == set(before)
    assert all(abs(result.values[k] - v) <= 1e-11 for k, v in before.items())
    assert "validation" not in result.provenance.parameters and "iterations" not in result.provenance.parameters


def test_eem_refusals_are_unchanged_by_adding_qeq():
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    flat = gc.compute_geometry_charges(resolve_calculation_input(engine, model, GEOMETRY).mol, "u", {})
    assert flat.error == (
        "EEM needs 3D coordinates, and this molecule has no 3D conformer. "
        "Generate conformers first (Structure ▸ Generate Conformers...)."
    )
    sulfur = gc.compute_geometry_charges(_conformer("CS"), "u", {})
    assert sulfur.error == "Bultinck et al. 2002 part I Table 1 has no parameters for S." and sulfur.error_summary == "Element not parameterised"


def test_an_unknown_method_code_raises_rather_than_defaulting():
    with pytest.raises(ValueError):
        gc.compute_geometry_charges(_conformer("CO"), "u", {"method": "qeq_rg1991_h_experimental"})


def test_distinct_method_codes_and_hydrogen_options_are_distinct_identities():
    base = {"method": "eem_bultinck2002_part1", "include_hydrogens": False, "decimal_places": 2}
    assert parameters_key(base) != parameters_key({**base, "method": "qeq_rg1991_lambda_half_h_experimental"})
    assert parameters_key(base) != parameters_key({**base, "method": "qeq_rg1991_h_experimental"})
    assert parameters_key(base) != parameters_key({**base, "include_hydrogens": True})


def test_the_compute_function_can_only_see_the_molecule_it_is_handed():
    assert list(inspect.signature(gc.compute_geometry_charges).parameters) == ["mol", "molecule_uuid", "parameters"]


# --- what it computes -----------------------------------------------------------


def test_computes_through_the_registry_with_a_conserved_declared_total():
    mol = _conformer("CC(=O)Oc1ccccc1C(=O)O")
    result = _registry().compute(CALCULATOR, mol, "u", {})
    assert result.cache_state == CacheState.COMPLETED
    assert set(result.values) == set(range(mol.GetNumAtoms()))
    assert all(np.isfinite(v) for v in result.values.values())
    parameters = result.provenance.parameters
    assert parameters[ATOM_BASIS] == EXPLICIT_H
    assert parameters[TOTAL]["declared"] and abs(parameters[TOTAL]["value"]) < 1e-10
    assert parameters["parameter_set"] == "bultinck_2002_part_I_table_1"
    assert parameters["equation_convention"] == "bultinck2002_eq3_atomic_units"
    assert parameters["not_applied"] == "protonation at a pH"
    assert "only the sum equals it" in parameters["species"]


@pytest.mark.parametrize("smiles,net", [("CC(=O)[O-]", -1.0), ("C[NH3+]", 1.0), ("[NH3+]CC(=O)[O-]", 0.0), ("C[N+](=O)[O-]", 0.0)])
def test_the_net_charge_is_the_conformer_s_and_per_atom_formal_charges_are_not_kept(smiles, net):
    mol = _conformer(smiles)
    result = gc.compute_geometry_charges(mol, "u", {})
    assert result.provenance.parameters["net_charge"] == net
    assert abs(sum(result.values.values()) - net) < 1e-10
    charged = [a.GetIdx() for a in mol.GetAtoms() if a.GetFormalCharge()]
    assert any(abs(result.values[i] - mol.GetAtomWithIdx(i).GetFormalCharge()) > 0.1 for i in charged)


def test_the_charges_follow_the_geometry():
    """Why this calculator declares GEOMETRY: flatten z on the same atoms and
    hydrogens (the conformer still says 3D) and the charges move. The positive
    control is that an unchanged copy gives identical charges."""
    mol = _conformer("OCC(N)C=O")
    base = gc.compute_geometry_charges(mol, "u", {}).values
    same = gc.compute_geometry_charges(Chem.Mol(mol), "u", {}).values
    assert same == base
    flat = Chem.Mol(mol)
    conformer = flat.GetConformer()
    from rdkit.Geometry import Point3D

    for i in range(flat.GetNumAtoms()):
        p = conformer.GetAtomPosition(i)
        conformer.SetAtomPosition(i, Point3D(p.x, p.y, 0.0))
    assert conformer.Is3D()
    moved = gc.compute_geometry_charges(flat, "u", {}).values
    assert max(abs(moved[i] - base[i]) for i in base) > 1e-3


def test_folding_hydrogens_moves_their_charge_onto_the_parent_and_conserves_the_total():
    mol = _conformer("CCO")
    separate = gc.compute_geometry_charges(mol, "u", {"include_hydrogens": False})
    folded = gc.compute_geometry_charges(mol, "u", {"include_hydrogens": True})
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() != 1]
    assert set(folded.values) == set(heavy)
    assert folded.provenance.parameters[ATOM_BASIS] == HEAVY_ATOMS
    for index in heavy:
        hydrogens = [n.GetIdx() for n in mol.GetAtomWithIdx(index).GetNeighbors() if n.GetAtomicNum() == 1]
        assert folded.values[index] == pytest.approx(separate.values[index] + sum(separate.values[h] for h in hydrogens), abs=1e-12)
    assert abs(sum(folded.values.values())) < 1e-10
    # The mapping keeps every hydrogen whichever way the rows are presented.
    assert folded.provenance.parameters["solver_to_source"] == list(range(mol.GetNumAtoms()))


# --- atom identity --------------------------------------------------------------


def test_interleaved_hydrogens_carry_their_charges_with_them():
    """A conformer whose molblock interleaves hydrogens, built by a KNOWN
    permutation: every charge must move with its atom."""
    mol = _conformer("OCC(N)C=O")
    base = gc.compute_geometry_charges(mol, "u", {}).values
    order = list(np.random.default_rng(4).permutation(mol.GetNumAtoms()))
    shuffled = _renumbered(mol, [int(i) for i in order])
    assert any(shuffled.GetAtomWithIdx(i).GetAtomicNum() == 1 for i in range(5)), "the permutation interleaves"
    moved = gc.compute_geometry_charges(shuffled, "u", {}).values
    for new_index, old_index in enumerate(order):
        assert moved[new_index] == pytest.approx(base[int(old_index)], abs=1e-12)


def test_a_drawing_renumbered_before_generation_keys_values_to_that_drawing():
    drawing = Chem.MolFromSmiles("OCC(N)C=O")
    renumbered = _renumbered(drawing, [4, 2, 0, 5, 1, 3])
    conformer = Chem.AddHs(renumbered)
    AllChem.EmbedMolecule(conformer, randomSeed=3)
    conformer = ChemistryEngine().mol_from_molblock(Chem.MolToMolBlock(conformer))
    values = gc.compute_geometry_charges(conformer, "u", {"include_hydrogens": True}).values
    assert set(values) == set(range(renumbered.GetNumAtoms()))
    for index in range(renumbered.GetNumAtoms()):
        assert conformer.GetAtomWithIdx(index).GetSymbol() == renumbered.GetAtomWithIdx(index).GetSymbol()
    oxygens = [a.GetIdx() for a in renumbered.GetAtoms() if a.GetSymbol() == "O"]
    assert all(values[i] < -0.2 for i in oxygens)


# --- refusals -------------------------------------------------------------------


def test_the_drawing_fallback_is_refused():
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    resolved = resolve_calculation_input(engine, model, GEOMETRY)
    assert resolved.used != GEOMETRY
    result = _registry().compute(CALCULATOR, resolved.mol, model.uuid, {})
    assert result.inapplicable and result.provenance.parameters["refusal"] == gc.REFUSE_NO_3D_GEOMETRY
    assert not result.values


def test_implicit_hydrogens_are_refused_and_none_are_invented():
    mol = _conformer("CCO")
    heavy = ChemistryEngine().mol_from_molblock(Chem.MolToMolBlock(Chem.RemoveHs(mol)))
    result = gc.compute_geometry_charges(heavy, "u", {})
    assert result.provenance.parameters["refusal"] == gc.REFUSE_IMPLICIT_HYDROGENS
    assert "will not invent them" in result.error


def test_a_molecule_with_no_hydrogens_is_accepted():
    for smiles in ("O=C=O", "FC(F)(F)F"):
        result = gc.compute_geometry_charges(_conformer(smiles), "u", {})
        assert result.cache_state == CacheState.COMPLETED, smiles


def test_hydrogens_without_finite_coordinates_are_refused():
    mol = Chem.Mol(_conformer("CO"))
    hydrogen = next(a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 1)
    from rdkit.Geometry import Point3D

    mol.GetConformer().SetAtomPosition(hydrogen, Point3D(float("nan"), 0.0, 0.0))
    assert gc.compute_geometry_charges(mol, "u", {}).provenance.parameters["refusal"] == gc.REFUSE_MISSING_H_COORDINATES


def test_elements_outside_table_1_are_refused_by_name():
    result = gc.compute_geometry_charges(_conformer("CS"), "u", {})
    assert result.provenance.parameters["refusal"] == "REFUSE_ELEMENT_NOT_PARAMETERISED"
    assert "S" in result.error


def test_no_protonation_path_is_reachable(monkeypatch):
    import openchem.chem.pka_providers as pka

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the 3D charge calculator must not protonate")

    for name in ("dominant_microspecies", "compute_pka", "protonate_at_ph"):
        if hasattr(pka, name):
            monkeypatch.setattr(pka, name, forbidden)
    assert gc.compute_geometry_charges(_conformer("CC(=O)O"), "u", {}).cache_state == CacheState.COMPLETED


# --- the snapshot, through the real service -----------------------------------


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def test_a_conformer_search_finishing_mid_run_does_not_relabel_the_result(qapp):
    """The fingerprint and the conformer id must both name what was SUBMITTED.
    The id used to be read off the live model after the calculator returned."""
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    first = _conformer("CCO", seed=1)
    model.conformers = [ConformerModel(conformer_id="submitted", molblock=Chem.MolToMolBlock(first), energy=1.0)]
    submitted_fingerprint = resolve_calculation_input(engine, model, GEOMETRY).fingerprint
    replacement = ConformerModel(conformer_id="arrived-later", molblock=Chem.MolToMolBlock(_conformer("CCO", seed=99)), energy=0.1)

    def compute(mol, molecule_uuid, parameters):
        model.conformers = [replacement]  # the search lands while this runs
        return gc.compute_geometry_charges(mol, molecule_uuid, parameters)

    registry = CalculatorRegistry()
    registry.register(CalculatorDefinition(
        calculator_id=CALCULATOR, display_name="x", category="charge", description="",
        calculation_input=GEOMETRY, execution=RegistryExecution(compute=compute),
    ))
    bus = EventBus()
    events = []
    bus.subscribe(PerAtomDataComputed, events.append)
    DescriptorService(bus, engine, calculator_registry=registry).run_calculator(
        model, CalculationRequest(calculator_id=CALCULATOR, molecule_uuid=model.uuid)
    )
    _drain(qapp)
    (event,) = events
    assert event.input_fingerprint == submitted_fingerprint
    recorded = {k: v for k, v in event.dataset.provenance.parameters.items() if k.endswith("conformer_id")}
    assert list(recorded.values()) == ["submitted"]
    # And the result is now stale against the model as it stands.
    assert resolve_calculation_input(engine, model, GEOMETRY).fingerprint != submitted_fingerprint


# --- QEq (amendment A8) -----------------------------------------------------------

QEQ = {"method": "qeq_rg1991_lambda_half_h_experimental"}


def test_qeq_through_the_registry_is_the_solver_with_the_a8_reading():
    from openchem.chem import charge_equilibration as ce

    mol = _conformer("OCC(N)C=O")
    result = _registry().compute(CALCULATOR, mol, "u", QEQ)
    assert result.cache_state == CacheState.COMPLETED
    elements = [a.GetSymbol() for a in mol.GetAtoms()]
    direct = ce.qeq_charges(elements, mol.GetConformer().GetPositions(), 0.0, hydrogen="experimental", readings=ce.ADOPTED)
    assert all(abs(result.values[i] - direct.charges[i]) <= 1e-12 for i in range(mol.GetNumAtoms()))
    parameters = result.provenance.parameters
    assert parameters["parameter_set"] == "rappe_1991_table_I" and parameters["hydrogen_parameter_set"] == "experimental"
    assert parameters["zeta_parameterization"] == "rappe_1991_eq17_prime_lambda_half" and parameters["lambda"] == 0.5
    assert parameters["zeta_h_in_pairs"] is True and parameters["hydrogen_self_term"] == "eq21"
    assert parameters["integral_model"] == "ns_slater_exact" and parameters["iterations"] == direct.iterations
    assert parameters["validation"]["amendment"] == "A8" and "source discrepancy" in parameters["validation"]["scope"]
    assert "source_discrepancy" not in parameters
    assert abs(parameters[TOTAL]["value"]) < 1e-10 and result.name == "Partial Charge (QEq, Rappé–Goddard 1991, 3D)"


def test_qeq_charges_move_with_their_atoms():
    mol = _conformer("OCC(N)C=O")
    base = gc.compute_geometry_charges(mol, "u", QEQ).values
    order = [int(i) for i in np.random.default_rng(4).permutation(mol.GetNumAtoms())]
    moved = gc.compute_geometry_charges(_renumbered(mol, order), "u", QEQ).values
    for new_index, old_index in enumerate(order):
        assert moved[new_index] == pytest.approx(base[old_index], abs=1e-10)


def test_silicon_is_computed_by_qeq_with_its_source_discrepancy_and_refused_by_eem():
    silane = _conformer("[SiH4]")
    qeq = gc.compute_geometry_charges(silane, "u", QEQ)
    assert qeq.cache_state == CacheState.COMPLETED
    assert qeq.provenance.parameters["source_discrepancy"] == gc.QEQ_SILICON_NOTE
    hydrogens = [a.GetIdx() for a in silane.GetAtoms() if a.GetAtomicNum() == 1]
    assert all(qeq.values[h] < 0 for h in hydrogens)
    assert gc.compute_geometry_charges(silane, "u", {}).provenance.parameters["refusal"] == "REFUSE_ELEMENT_NOT_PARAMETERISED"


def test_qeq_refuses_what_it_has_no_parameters_for_and_the_drawing():
    boron = gc.compute_geometry_charges(_conformer("B(C)(C)C"), "u", QEQ)
    assert boron.provenance.parameters["refusal"] == "REFUSE_ELEMENT_NOT_PARAMETERISED" and "B" in boron.error
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    flat = gc.compute_geometry_charges(resolve_calculation_input(engine, model, GEOMETRY).mol, "u", QEQ)
    assert flat.provenance.parameters["refusal"] == gc.REFUSE_NO_3D_GEOMETRY and flat.error.startswith("QEq needs 3D")


def test_qeq_non_convergence_is_refused_with_its_diagnostics():
    """LiH, whose printed charge is not a solution of the equations (A7)."""
    lithium_hydride = _conformer("[LiH]")
    result = gc.compute_geometry_charges(lithium_hydride, "u", QEQ)
    assert result.inapplicable and not result.values
    parameters = result.provenance.parameters
    assert parameters["refusal"] == "REFUSE_NOT_CONVERGED" and result.error_summary == "Did not converge"
    assert parameters["iterations"] == 50 and parameters["trace_class"] and "dQ_H" in parameters["final_metrics"]
    assert "ever_clamped" in parameters


def _stub_qeq(monkeypatch, *, final_active=None, ever_clamped=False):
    """No measured molecule ends with an active bound or clamps only mid-loop
    (both searched for), so the refusal logic is exercised on constructed
    solver results, and says so."""
    from openchem.chem import charge_equilibration as ce

    real = ce.qeq_charges

    def constructed(elements, coords, net_charge=0.0, **kwargs):
        result = real(elements, coords, net_charge, **kwargs)
        result.final_active_atoms = dict(final_active or {})
        result.ever_clamped = ever_clamped
        return result

    monkeypatch.setattr(gc.ce, "qeq_charges", constructed)


def test_a_final_active_bound_is_refused_with_per_atom_diagnostics(monkeypatch):
    _stub_qeq(monkeypatch, final_active={0: -2.0}, ever_clamped=True)
    result = gc.compute_geometry_charges(_conformer("OCC(N)C=O"), "u", QEQ)
    assert result.inapplicable and not result.values
    parameters = result.provenance.parameters
    assert parameters["refusal"] == gc.REFUSE_BOUND_ACTIVE and result.error_summary == "Charge bound reached"
    (atom,) = parameters["final_active_atoms"]
    assert atom["atom"] == 0 and atom["element"] == "O" and atom["bound"] == -2.0 and "final_charge" in atom
    assert "O0" in result.error


def test_touching_a_bound_mid_loop_is_not_a_refusal(monkeypatch):
    """A8: only the FINAL active set refuses."""
    _stub_qeq(monkeypatch, final_active={}, ever_clamped=True)
    result = gc.compute_geometry_charges(_conformer("OCC(N)C=O"), "u", QEQ)
    assert result.cache_state == CacheState.COMPLETED and result.values
    assert result.provenance.parameters["ever_clamped"] is True
