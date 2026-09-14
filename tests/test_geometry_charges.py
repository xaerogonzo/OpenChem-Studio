"""The geometry-dependent charge calculator: EEM on the stored conformer.

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


def test_registered_on_geometry_offering_only_the_gated_method_by_code():
    definition = _registry().get(CALCULATOR)
    assert definition.calculation_input == GEOMETRY
    assert definition.category == "charge"
    (method,) = [p for p in definition.parameters if p.name == "method"]
    assert method.choices == ["eem_bultinck2002_part1"]
    assert method.choice_labels == ["EEM, Bultinck 2002"]
    assert not any("qeq" in choice for choice in method.choices), "QEq stopped at its gate"


def test_an_unknown_method_code_raises_rather_than_defaulting():
    with pytest.raises(ValueError):
        gc.compute_geometry_charges(_conformer("CO"), "u", {"method": "qeq_rg1991_h_experimental"})


def test_distinct_method_codes_and_hydrogen_options_are_distinct_identities():
    base = {"method": "eem_bultinck2002_part1", "include_hydrogens": False, "decimal_places": 2}
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
