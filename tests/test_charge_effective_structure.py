"""The 3D charge result carries the structure it was computed on, and one calculator serves both modes.

Measured 2026-09-17 before any of this existed, on the app Alex drove:

- the pH-dependent charges were drawn on the STORED conformer, so butyryl fentanyl's added N-H never
  appeared, and for an acid drawn as OC(=O)C the removed hydrogen renumbered the atoms after it --
  index 4 held a methyl hydrogen's charge while the stored conformer's atom 4 is the acidic hydrogen;
- every QEq result was logged "Not saving ... unknown_type: numpy.float64" and never saved;
- the as-drawn and pH results were two calculators, and so two answers side by side in Results.
"""

from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import geometry_charges as gc
from openchem.chem.engine import ChemistryEngine
from openchem.chem.result_structure import (
    EFFECTIVE_STRUCTURE,
    LEGACY_STORED_CONFORMER,
    display_structure,
    structure_fingerprint,
)
from openchem.domain import result_codec
from openchem.domain.calculator import (
    GEOMETRY,
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    active_parameters,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.result_store import RETIRED_RESULT_IDS, ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.scientific_result import PerAtomDataset
from openchem.services.calculator_registry import CalculatorRegistry

PH = {"ph_dependent": True, "pH": 7.4}
BUTYRYL_FENTANYL = "CCCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def _conformer(smiles: str, seed: int = 7) -> Chem.Mol:
    """As the app stores and resolves one: embedded with hydrogens, written to a molblock, read back."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    return ChemistryEngine().mol_from_molblock(Chem.MolToMolBlock(mol))


def _structure(dataset: PerAtomDataset) -> Chem.Mol:
    mol = Chem.MolFromMolBlock(dataset.structure_molblock, removeHs=False)
    assert mol is not None
    return mol


# --- A: the effective structure ------------------------------------------------------------------


def test_an_acid_whose_removed_hydrogen_is_not_last_keeps_every_value_on_its_own_atom():
    """M2. OC(=O)C: the acidic hydrogen is atom 4 and the methyl hydrogens 5-7, so removing it
    renumbers the methyl hydrogens to 4-6. Every value must sit on an atom of the carboxylate, and
    each hydrogen value on a hydrogen that exists there -- which the stored conformer cannot give,
    because its atom 4 is the hydrogen that left."""
    source = _conformer("OC(=O)C")
    assert [a.GetSymbol() for a in source.GetAtoms()] == ["O", "C", "O", "C", "H", "H", "H", "H"]
    assert source.GetAtomWithIdx(4).GetNeighbors()[0].GetSymbol() == "O"  # the acidic H, not last

    dataset = _registry().compute("geometry_partial_charge", source, "u", PH)
    assert dataset.cache_state == CacheState.COMPLETED, dataset.error
    species = _structure(dataset)
    assert Chem.GetFormalCharge(species) == -1
    assert set(dataset.values) == set(range(species.GetNumAtoms())) == set(range(7))
    hydrogens = [a for a in species.GetAtoms() if a.GetAtomicNum() == 1]
    assert len(hydrogens) == 3 and all(h.GetNeighbors()[0].GetSymbol() == "C" for h in hydrogens)
    # Identity, not just element: the carboxyl carbon is the carbon with two oxygen neighbours, and
    # its value is the one the solver gave the atom at that index of THIS structure.
    (carboxyl,) = [a.GetIdx() for a in species.GetAtoms()
                   if a.GetSymbol() == "C" and sum(n.GetSymbol() == "O" for n in a.GetNeighbors()) == 2]
    # Solved again from the RECORDED structure alone: if its atom order were not the dataset's,
    # the values would land on different indices here.
    from openchem.chem import charge_equilibration as ce

    again = ce.eem_charges([a.GetSymbol() for a in species.GetAtoms()],
                           np.array(species.GetConformer().GetPositions()), -1.0)
    expected = {again.solver_to_source[k]: float(again.charges[k]) for k in range(species.GetNumAtoms())}
    assert all(abs(dataset.values[i] - expected[i]) < 1e-6 for i in expected)
    assert dataset.values[carboxyl] > 0.3  # a carboxylate carbon, not a methyl carbon or a hydrogen
    # On the stored conformer, the index the dataset calls hydrogen 4 is the hydrogen that left.
    assert source.GetAtomWithIdx(4).GetNeighbors()[0].GetSymbol() == "O"
    assert species.GetAtomWithIdx(4).GetNeighbors()[0].GetSymbol() == "C"


def test_butyryl_fentanyl_at_ph_7_4_carries_its_protonated_piperidine():
    """The molecule Alex reported: the charges were right and the picture never showed why."""
    dataset = _registry().compute("geometry_partial_charge", _conformer(BUTYRYL_FENTANYL), "u", PH)
    assert dataset.cache_state == CacheState.COMPLETED, dataset.error
    species = _structure(dataset)
    assert Chem.GetFormalCharge(species) == 1
    (cation,) = [a for a in species.GetAtoms() if a.GetFormalCharge() != 0]
    assert cation.GetSymbol() == "N" and cation.GetFormalCharge() == 1 and cation.GetDegree() == 4
    assert species.GetNumAtoms() == 57
    assert abs(sum(dataset.values.values()) - 1.0) < 1e-8
    assert dataset.provenance.parameters["state_changed"] is True


def test_the_structure_is_the_solve_input_and_its_fingerprint_is_recorded_three_ways():
    source = _conformer("CN")
    dataset = gc.compute_geometry_charges(source, "u", PH)
    species = _structure(dataset)

    kept = source.GetNumAtoms()
    before = np.array(source.GetConformer().GetPositions())
    after = np.array(species.GetConformer().GetPositions())
    # Retained atoms came from a 4-decimal molblock and go back into one: identical.
    assert np.array_equal(after[:kept], before), "a retained atom moved"
    # Only the MMFF-placed hydrogen can lose precision, to the molblock's 4 decimals.
    placed = dataset.provenance.parameters["placed_hydrogens"]
    assert placed == [kept]
    fresh = gc.protonate_conformer(source, 7.4).mol.GetConformer().GetPositions()
    assert np.abs(after[kept] - fresh[kept]).max() <= 5e-5

    assert dataset.structure_fingerprint == structure_fingerprint(dataset.structure_molblock)
    assert dataset.provenance.parameters["effective_structure_fingerprint"] == dataset.structure_fingerprint


def test_as_drawn_records_the_input_conformer_as_its_structure():
    source = _conformer("CCO")
    dataset = gc.compute_geometry_charges(source, "u", {})
    species = _structure(dataset)
    assert [a.GetSymbol() for a in species.GetAtoms()] == [a.GetSymbol() for a in source.GetAtoms()]
    assert np.array_equal(species.GetConformer().GetPositions(), source.GetConformer().GetPositions())


def test_display_structure_prefers_the_result_and_says_when_it_fell_back():
    model = MoleculeModel()
    model.conformers = [ConformerModel(conformer_id="c1", molblock="STORED")]
    legacy = PerAtomDataset(property_id="x", name="x", units="e", method="m", molecule_uuid="u",
                            provenance=Provenance(created_by="core", method="m",
                                                  parameters={"input_source": "conformer", "input_conformer_id": "c1"}))
    assert display_structure(model, legacy) == ("STORED", LEGACY_STORED_CONFORMER)
    own = PerAtomDataset(property_id="x", name="x", units="e", method="m", molecule_uuid="u",
                         structure_molblock="OWN", provenance=legacy.provenance)
    assert display_structure(model, own) == ("OWN", EFFECTIVE_STRUCTURE)


# --- C: one calculator, and parameters that depend on another ------------------------------------


def _definition(*parameters: CalculatorParameter) -> CalculatorDefinition:
    return CalculatorDefinition(calculator_id="t", display_name="t", category="t", description="",
                                execution=RegistryExecution(compute=lambda mol, uuid, params: params),
                                parameters=list(parameters))


def test_enabled_by_is_validated_at_construction():
    flag = CalculatorParameter(name="flag", label="f", kind="bool", default=False)
    number = CalculatorParameter(name="n", label="n", kind="float", default=1.0)
    with pytest.raises(ValueError, match="names no parameter"):
        _definition(CalculatorParameter(name="x", label="x", kind="float", default=0.0, enabled_by="missing"))
    with pytest.raises(ValueError, match="is not a bool"):
        _definition(number, CalculatorParameter(name="x", label="x", kind="float", default=0.0, enabled_by="n"))
    with pytest.raises(ValueError, match="cycle"):
        _definition(CalculatorParameter(name="a", label="a", kind="bool", default=True, enabled_by="b"),
                    CalculatorParameter(name="b", label="b", kind="bool", default=True, enabled_by="a"))
    _definition(flag, CalculatorParameter(name="x", label="x", kind="float", default=0.0, enabled_by="flag"))


def test_a_greyed_out_parameter_never_reaches_the_calculator():
    definition = _definition(
        CalculatorParameter(name="flag", label="f", kind="bool", default=False),
        CalculatorParameter(name="x", label="x", kind="float", default=0.0, enabled_by="flag"),
    )
    assert active_parameters(definition, {"flag": False, "x": 9.0, "internal": 1}) == {"flag": False, "internal": 1}
    assert active_parameters(definition, {"x": 9.0}) == {}  # the controller's default is off
    assert active_parameters(definition, {"flag": True, "x": 9.0}) == {"flag": True, "x": 9.0}

    registry = CalculatorRegistry()
    registry.register(definition)
    assert registry.compute("t", None, "u", {"flag": False, "x": 9.0}) == {"flag": False}


def test_a_ph_changed_while_unticked_changes_nothing():
    source = _conformer("NCC(=O)O")
    registry = _registry()
    plain = registry.compute("geometry_partial_charge", source, "u", {"ph_dependent": False})
    unticked = registry.compute("geometry_partial_charge", source, "u", {"ph_dependent": False, "pH": 2.0})
    assert plain.values == unticked.values and plain.name == unticked.name
    assert "pH" not in unticked.provenance.parameters


# --- C: the retired result id --------------------------------------------------------------------


def _stored(result_id: str, result) -> StoredResult:
    return StoredResult(identity=ResultIdentity(molecule_uuid="m", result_id=result_id, calculation_input=GEOMETRY,
                                                input_fingerprint="f", producer=result_id),
                        result=result)


def test_an_old_ph_result_is_dropped_on_load_by_name_and_everything_else_survives():
    source = _conformer("NCC(=O)O")
    old = PerAtomDataset(property_id=gc.PROPERTY_ID_AT_PH, name="old", units="e", method="m",
                         molecule_uuid="m", values={0: 0.5})
    kept = gc.compute_geometry_charges(source, "m", {})
    store = SessionResultStore("p")
    store.put(_stored(gc.PROPERTY_ID_AT_PH, old))
    store.put(_stored(gc.PROPERTY_ID, kept))
    saved = store.to_dict()

    reloaded = SessionResultStore.from_dict(saved, "p")
    assert reloaded.load_problems["retired"] == 1 and gc.PROPERTY_ID_AT_PH in RETIRED_RESULT_IDS
    (only,) = reloaded.fresh_results("m", {GEOMETRY: "f"})
    assert only.identity.result_id == gc.PROPERTY_ID and only.result.values == kept.values

    again = SessionResultStore.from_dict(reloaded.to_dict(), "p")
    assert again.load_problems["retired"] == 0
    assert [s.identity.result_id for s in again.fresh_results("m", {GEOMETRY: "f"})] == [gc.PROPERTY_ID]


def test_an_unknown_but_unretired_result_id_is_still_restored():
    """Retirement is a named list: a plugin's result must not be dropped for being unregistered."""
    plugin = PerAtomDataset(property_id="some_plugin_charge", name="p", units="e", method="m",
                            molecule_uuid="m", values={0: 0.1})
    store = SessionResultStore("p")
    store.put(_stored("some_plugin_charge", plugin))
    reloaded = SessionResultStore.from_dict(store.to_dict(), "p")
    assert [s.identity.result_id for s in reloaded.fresh_results("m", {GEOMETRY: "f"})] == ["some_plugin_charge"]


# --- G: every result the calculator emits can be saved -----------------------------------------


def _numpy_in(value) -> list[str]:
    if isinstance(value, (np.generic, np.ndarray)):
        return [type(value).__name__]
    if isinstance(value, dict):
        return [n for k, v in value.items() for n in _numpy_in(k) + _numpy_in(v)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [n for v in value for n in _numpy_in(v)]
    return []


def _assert_saveable(result) -> None:
    assert _numpy_in(result.values) == [] and _numpy_in(result.provenance.parameters) == []
    back = result_codec.decode(result_codec.encode(result))
    assert back == result


@pytest.mark.parametrize("method", gc.GEOMETRY_CHARGE_METHODS)
@pytest.mark.parametrize("mode", [{}, PH])
@pytest.mark.parametrize("fold", [False, True])
def test_every_computed_result_round_trips_through_the_codec(method, mode, fold):
    """QEq's `final_metrics` carried numpy float64 until 2026-09-17, so no QEq result was ever saved."""
    result = _registry().compute("geometry_partial_charge", _conformer("NCC(=O)O"), "u",
                                 {"method": method, "include_hydrogens": fold, **mode})
    assert result.cache_state == CacheState.COMPLETED, result.error
    _assert_saveable(result)


@pytest.mark.parametrize("smiles,parameters", [
    ("[LiH]", {"method": gc.QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL}),  # not converged, with numpy metrics
    ("CS(C)=O", {"method": gc.EEM_IONESCU2013_E_MPA_631GS_GAS}),  # oxidised sulfur
    ("B(C)(C)C", {"method": gc.QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL}),  # no parameters
])
def test_every_refusal_round_trips_through_the_codec(smiles, parameters):
    result = _registry().compute("geometry_partial_charge", _conformer(smiles), "u", parameters)
    assert result.cache_state == CacheState.FAILED
    _assert_saveable(result)


def test_a_v1_dataset_from_a_saved_project_decodes_with_no_structure(monkeypatch):
    """The fixture project master saved before this change: its 3D charge result is v1."""
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parent / "fixtures" / "projects" / "master_charge_consumers.ocsproj"
    text = path.read_text(encoding="utf-8")
    assert '"__type__": "scientific_result.PerAtomDataset"' in text

    def datasets(node):
        if isinstance(node, dict):
            if node.get("__type__") == "scientific_result.PerAtomDataset":
                yield node
            for value in node.values():
                yield from datasets(value)
        elif isinstance(node, list):
            for value in node:
                yield from datasets(value)

    (raw,) = [d for d in datasets(json.loads(text)) if d.get("property_id") == gc.PROPERTY_ID]
    assert raw["__version__"] == 1
    decoded = result_codec.decode(raw)
    assert decoded.structure_molblock == "" and decoded.structure_fingerprint == "" and decoded.values


def test_a_build_that_reads_only_v1_refuses_a_dataset_that_carries_a_structure(monkeypatch):
    """What an older build does with a new project: refuse the dataset, never read its indices
    without the structure they refer to."""
    encoded = result_codec.encode(gc.compute_geometry_charges(_conformer("OC(=O)C"), "u", PH))
    assert encoded["__version__"] == 2
    monkeypatch.setitem(result_codec.TYPE_VERSIONS, "scientific_result.PerAtomDataset", 1)
    with pytest.raises(result_codec.CodecError) as refused:
        result_codec.decode(encoded)
    assert refused.value.problem == result_codec.UNSUPPORTED_VERSION


def test_a_drawing_refusal_round_trips_through_the_codec():
    result = gc.compute_geometry_charges(Chem.AddHs(Chem.MolFromSmiles("CCO")), "u", PH)
    assert result.provenance.parameters["refusal"] == gc.REFUSE_NO_3D_GEOMETRY
    _assert_saveable(result)
