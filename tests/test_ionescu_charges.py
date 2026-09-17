"""Ionescu et al. 2013's EEM as a shipped calculator: its two E-MPA gas models, through the registry.

`tests/test_ionescu_eem_instrument.py` holds the benchmark instrument against the paper. This file
holds the SHIPPED path against that instrument and against the decisions in
`benchmarks/charges/models/ionescu_src_preregistration.md` §10: which models ship, what is refused,
what every result records, and that its identity never collides with Bultinck's EEM or QEq.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import charge_equilibration as ce
from openchem.chem import charge_evaluation as cev
from openchem.chem import geometry_charges as gc
from openchem.chem.engine import ChemistryEngine
from openchem.domain import result_codec
from openchem.domain.common import TOTAL, CacheState
from openchem.services.result_cache import parameters_key

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ionescu_eem_check", ROOT / "benchmarks" / "charges" / "models" / "ionescu_eem_check.py")
ie = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("ionescu_eem_check", ie)
_spec.loader.exec_module(ie)
_bspec = importlib.util.spec_from_file_location("build_ionescu_parameters", ROOT / "tools" / "build_ionescu_parameters.py")
builder = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(builder)

#: One calculator since 2026-09-17: the pH mode is its `ph_dependent` option.
CALCULATORS = ("geometry_partial_charge",)
SHIPPED = {
    "eem_ionescu2013_e_mpa_631gs_gas": "E-MPA/6-31G*/gas",
    "eem_ionescu2013_e_mpa_631gss_gas": "E-MPA/6-31G**/gas",
}
#: The instrument reproduced the SI to 4e-4 e at worst (TRIAGE 2.8); the two paths here share no code,
#: so they agree to solver precision.
CROSS_PATH_TOLERANCE = 1e-9


def _registry():
    from openchem.bootstrap import build_service_container

    return build_service_container().calculator_registry


def _conformer(smiles: str, seed: int = 7) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    return ChemistryEngine().mol_from_molblock(Chem.MolToMolBlock(mol))


def _elements(mol) -> list[str]:
    return [a.GetSymbol() for a in mol.GetAtoms()]


# --- what ships -------------------------------------------------------------------------------------


@pytest.mark.parametrize("calculator", CALCULATORS)
def test_both_charge_calculators_offer_exactly_the_two_shipped_models(calculator):
    (method,) = [p for p in _registry().get(calculator).parameters if p.name == "method"]
    offered = [c for c in method.choices if "ionescu" in c]
    assert offered == list(SHIPPED), f"{calculator} offers {offered}"
    assert method.default == gc.EEM_BULTINCK2002_PART1


def test_codes_schemes_and_parameter_sets_are_one_to_one():
    assert gc.IONESCU_SCHEMES == SHIPPED
    assert set(ce.ionescu_parameters()) == set(SHIPPED.values())
    assert tuple(SHIPPED.values()) == builder.SHIPPED
    for code in SHIPPED:
        assert code in gc.GEOMETRY_CHARGE_METHOD_LABELS and code in gc._METHOD_SHORT
    labels = list(gc.GEOMETRY_CHARGE_METHOD_LABELS.values())
    assert len(set(labels)) == len(labels), "two methods share an on-screen label"


def test_the_consumers_do_not_offer_ionescu_which_is_out_of_scope():
    """The dipole and ESP views are a separate decision (plan A.3); the code must not offer it by accident."""
    assert not any("ionescu" in key for key in cev.CHARGE_MODELS)
    assert set(cev.SOURCE_KEYS) == set(cev.CHARGE_MODELS) == set(cev.INPUT_REQUIREMENT)


def test_every_method_is_a_distinct_identity_and_the_label_is_never_stored():
    keys = {parameters_key({"method": m, "include_hydrogens": False, "decimal_places": 3}) for m in gc.GEOMETRY_CHARGE_METHODS}
    assert len(keys) == len(gc.GEOMETRY_CHARGE_METHODS)
    mol = _conformer("OCC(N)C=O")
    for code in SHIPPED:
        result = _registry().compute("geometry_partial_charge", mol, "u", {"method": code})
        stored = json.dumps(result_codec.encode(result), ensure_ascii=False)
        assert gc.GEOMETRY_CHARGE_METHOD_LABELS[code] not in stored.replace(result.name, ""), code


# --- the parameter file -------------------------------------------------------------------------------


def test_the_shipped_json_is_exactly_what_the_builder_makes_from_the_fixture():
    on_disk = json.loads(ce.IONESCU_PARAMETERS_PATH.read_text(encoding="utf-8"))
    assert on_disk == builder.build(), "eem_ionescu2013.json is stale or hand-edited"
    assert on_disk["_source_key"] == "ionescu2013"


def test_the_shipped_numbers_are_the_printed_fixture_strings():
    fixture = ie.table_s1()
    for scheme, model in ce.ionescu_parameters().items():
        assert model["kappa"] == fixture[scheme]["kappa"]
        assert model["types"] == {e: list(v) for e, v in fixture[scheme]["types"].items()}, scheme
        # Exactly the E typing's elements, spelt as element symbols: anything else is refused by name.
        assert set(model["types"]) == {"H", "C", "N", "O", "S", "Ca"}, scheme
        assert model["kappa"] > 0


def test_the_recorded_checksum_is_recomputable_from_the_file():
    mol = _conformer("CSC")
    for code, scheme in SHIPPED.items():
        recorded = gc.compute_geometry_charges(mol, "u", {"method": code}).provenance.parameters["parameter_checksum"]
        raw = json.loads(ce.IONESCU_PARAMETERS_PATH.read_text(encoding="utf-8"))["models"][scheme]
        assert recorded == ce.payload_checksum(raw)
    a, b = (ce.payload_checksum(ce.ionescu_parameters()[s]) for s in SHIPPED.values())
    assert a != b, "one model's parameters recorded for the other"


# --- the system -------------------------------------------------------------------------------------


def test_the_assembled_system_keeps_x_as_an_unknown():
    mol = _conformer("OCC(N)C=O")
    n = mol.GetNumAtoms()
    matrix, rhs = ce.ionescu_system(_elements(mol), mol.GetConformer().GetPositions(), "E-MPA/6-31G*/gas", -1.0)
    assert matrix.shape == (n + 1, n + 1) and rhs.shape == (n + 1,)
    assert np.all(matrix[:n, n] == -1.0) and np.all(matrix[n, :n] == 1.0) and matrix[n, n] == 0.0
    assert rhs[n] == -1.0
    model = ce.ionescu_parameters()["E-MPA/6-31G*/gas"]
    positions = mol.GetConformer().GetPositions()
    r01 = np.linalg.norm(positions[0] - positions[1])
    assert matrix[0, 1] == pytest.approx(model["kappa"] / r01, rel=1e-12), "the kappa / r_ij (angstrom) term"
    assert matrix[0, 0] == model["types"]["O"][1] and rhs[0] == -model["types"]["O"][0]


@pytest.mark.parametrize("smiles,net", [("OCC(N)C=O", 0.0), ("CSC", 0.0), ("CCC(=O)[O-]", -1.0), ("C[NH3+]", 1.0)])
@pytest.mark.parametrize("code", list(SHIPPED))
def test_cross_path_gate_against_the_benchmark_instrument_by_atom_identity(code, smiles, net):
    """The registry's answer against `ionescu_eem_check.eem_charges`, which reproduced the SI 36/36.

    Identity is checked BEFORE any value: element per source atom through `solver_to_source`, so a
    permuted but otherwise matching answer cannot pass.
    """
    mol = _conformer(smiles)
    result = _registry().compute("geometry_partial_charge", mol, "u", {"method": code})
    assert result.cache_state == CacheState.COMPLETED, result.error
    parameters = result.provenance.parameters
    elements = _elements(mol)
    assert [elements[s] for s in parameters["solver_to_source"]] == elements
    assert parameters["method"] == result.method == code and parameters["scheme"] == SHIPPED[code]
    assert parameters["source"].startswith("ionescu2013 ") and parameters["applicability"] == "extrapolation"
    assert parameters["net_charge"] == net and abs(parameters[TOTAL]["value"] - net) < 1e-9

    expected = ie.eem_charges(elements, mol.GetConformer().GetPositions(), net, ie.table_s1()[SHIPPED[code]], "R_angstrom")
    worst = max(abs(result.values[i] - expected[i]) for i in range(len(elements)))
    assert worst <= CROSS_PATH_TOLERANCE, f"{code} on {smiles}: registry differs from the instrument by {worst:.3g} e"


def test_the_bohr_reading_is_not_what_ships():
    mol = _conformer("OCC(N)C=O")
    scheme = SHIPPED["eem_ionescu2013_e_mpa_631gs_gas"]
    shipped = gc.compute_geometry_charges(mol, "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"}).values
    bohr = ie.eem_charges(_elements(mol), mol.GetConformer().GetPositions(), 0.0, ie.table_s1()[scheme], "R_bohr")
    assert max(abs(shipped[i] - bohr[i]) for i in range(mol.GetNumAtoms())) > 1e-3


def test_the_two_models_and_bultinck_give_different_answers_so_none_substitutes_for_another():
    mol = _conformer("OCC(N)C=O")
    answers = {m: gc.compute_geometry_charges(mol, "u", {"method": m}).values for m in
               (gc.EEM_BULTINCK2002_PART1, *SHIPPED)}
    codes = list(answers)
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            assert max(abs(answers[a][k] - answers[b][k]) for k in answers[a]) > 1e-3, f"{a} == {b}"


def test_an_ionescu_request_never_reaches_bultinck_or_qeq(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Ionescu dispatched to another model's solver")

    monkeypatch.setattr(ce, "eem_charges", forbidden)
    monkeypatch.setattr(ce, "qeq_charges", forbidden)
    for code in SHIPPED:
        assert gc.compute_geometry_charges(_conformer("CSC"), "u", {"method": code}).cache_state == CacheState.COMPLETED


# --- what every result records --------------------------------------------------------------------------


def _hessian_kind(elements, positions, scheme) -> str:
    """The constrained Hessian's sign, independently of `ionescu_stationary_point`'s B shortcut."""
    matrix, _ = ce.ionescu_system(elements, positions, scheme)
    n = len(elements)
    hessian = matrix[:n, :n]
    basis = np.linalg.svd(np.ones((1, n)))[2][1:].T  # an orthonormal basis of sum q = 0
    return "saddle" if np.linalg.eigvalsh(basis.T @ hessian @ basis).min() < 0 else "minimum"


@pytest.mark.parametrize("smiles", ["CSC", "OCC(N)C=O", "CCO"])
@pytest.mark.parametrize("code", list(SHIPPED))
def test_the_recorded_stationary_point_is_the_hessian_s(code, smiles):
    mol = _conformer(smiles)
    recorded = gc.compute_geometry_charges(mol, "u", {"method": code}).provenance.parameters["stationary_point"]
    assert recorded == _hessian_kind(_elements(mol), mol.GetConformer().GetPositions(), SHIPPED[code])


def test_sulfur_makes_the_published_model_a_saddle():
    """Recorded rather than hidden: S has a negative B in both shipped models (preregistration §3)."""
    for scheme in SHIPPED.values():
        assert ce.ionescu_parameters()[scheme]["types"]["S"][1] < 0
    assert gc.compute_geometry_charges(_conformer("CSC"), "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"}).provenance.parameters["stationary_point"] == "saddle"


def test_the_scope_and_units_survive_the_codec():
    result = _registry().compute("geometry_partial_charge", _conformer("CSC"), "u", {"method": "eem_ionescu2013_e_mpa_631gss_gas"})
    back = result_codec.decode(json.loads(json.dumps(result_codec.encode(result))))
    parameters = back.provenance.parameters
    assert parameters["validation"]["scope_id"] == gc.IONESCU_SCOPE_ID == "ionescu2013_protein_fragment_validation_v1"
    assert parameters["validation"]["preregistration"] == "benchmarks/charges/models/ionescu_src_preregistration.md"
    assert parameters["applicability"] == "extrapolation"
    assert parameters["charge_bound"] == ce.IONESCU_CHARGE_BOUND == 2.051
    assert "equalized_electronegativity_ev" not in parameters, "the paper's units are not eV"
    assert np.isfinite(parameters["equalized_electronegativity_paper_units"])
    assert back.method == "eem_ionescu2013_e_mpa_631gss_gas" and back.values == result.values


def test_the_ph_dependent_option_carries_the_same_model_identity():
    result = _registry().compute("geometry_partial_charge", _conformer("CC(=O)O"), "u",
                                 {"method": "eem_ionescu2013_e_mpa_631gs_gas", "ph_dependent": True, "pH": 7.4})
    assert result.cache_state == CacheState.COMPLETED, result.error
    parameters = result.provenance.parameters
    assert result.property_id == gc.PROPERTY_ID and parameters["scheme"] == "E-MPA/6-31G*/gas"
    assert parameters["net_charge"] == -1.0 and parameters["validation"]["scope_id"] == gc.IONESCU_SCOPE_ID


# --- refusals ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("smiles,oxidised", [("CS(C)=O", [1]), ("CS(=O)(=O)C", [1]), ("NS(=O)(=O)c1ccccc1", [1]),
                                             ("OS(=O)(=O)O", [1])])
@pytest.mark.parametrize("code", list(SHIPPED))
def test_sulfur_bonded_to_oxygen_is_refused_before_any_solve(code, smiles, oxidised, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("solved a molecule that should have been refused from its bonds")

    monkeypatch.setattr(ce, "ionescu_charges", forbidden)
    result = _registry().compute("geometry_partial_charge", _conformer(smiles), "u", {"method": code})
    assert result.inapplicable and result.cache_state == CacheState.FAILED and not result.values
    assert result.provenance.parameters["refusal"] == gc.REFUSE_OXIDISED_SULFUR
    assert result.provenance.parameters["oxidised_sulfur_atoms"] == oxidised
    assert result.error_summary == "Sulfur bonded to oxygen" and "S1" in result.error


def test_sulfur_not_bonded_to_oxygen_is_computed():
    for smiles in ("CSC", "CSSC", "C1CCSC1", "CSc1ccc(O)cc1"):
        result = gc.compute_geometry_charges(_conformer(smiles), "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"})
        assert result.cache_state == CacheState.COMPLETED, (smiles, result.error)


@pytest.mark.parametrize("code", list(SHIPPED))
def test_an_unparameterised_element_is_refused_by_name_and_never_computed_as_another(code):
    for smiles, element in (("CCl", "Cl"), ("CBr", "Br"), ("C[Si](C)(C)C", "Si")):
        result = _registry().compute("geometry_partial_charge", _conformer(smiles), "u", {"method": code})
        assert result.inapplicable and result.provenance.parameters["refusal"] == ce.REFUSE_ELEMENT_NOT_PARAMETERISED
        assert f"no parameters for {element}" in result.error and SHIPPED[code] in result.error


def test_a_runaway_charge_is_refused_with_the_atom_named(monkeypatch):
    """The bound is only reachable off-domain, so it is lowered here to a value this molecule exceeds."""
    mol = _conformer("OCC(N)C=O")
    computed = gc.compute_geometry_charges(mol, "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"}).values
    largest = max(abs(v) for v in computed.values())
    monkeypatch.setattr(ce, "IONESCU_CHARGE_BOUND", largest - 1e-6)
    result = gc.compute_geometry_charges(mol, "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"})
    assert result.inapplicable and result.provenance.parameters["refusal"] == ce.REFUSE_CHARGE_BOUND_EXCEEDED
    assert result.error_summary == "Runaway charge" and not result.values
    monkeypatch.setattr(ce, "IONESCU_CHARGE_BOUND", largest + 1e-6)
    assert gc.compute_geometry_charges(mol, "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"}).cache_state == CacheState.COMPLETED


def test_the_drawing_is_refused_as_for_every_other_method():
    mol = Chem.AddHs(Chem.MolFromSmiles("CSC"))
    result = gc.compute_geometry_charges(mol, "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"})
    assert result.provenance.parameters["refusal"] == gc.REFUSE_NO_3D_GEOMETRY
    assert "Ionescu EEM needs 3D coordinates" in result.error


def test_the_reader_is_told_it_is_an_extrapolation_and_when_it_is_a_saddle():
    """`summary` is the provenance field the reader shows as its "Finding" row; nothing else reaches the screen."""
    from openchem.ui.result_adapters import _producer_finding  # the reader's own projection
    from openchem.domain.report import FactCategory

    saddle = gc.compute_geometry_charges(_conformer("CSC"), "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"})
    minimum = gc.compute_geometry_charges(_conformer("CCO"), "u", {"method": "eem_ionescu2013_e_mpa_631gs_gas"})
    for result, saddle_expected in ((saddle, True), (minimum, False)):
        (finding,) = _producer_finding(result, next(iter(FactCategory)))
        assert gc.IONESCU_EXTRAPOLATION_NOTE in finding.display_value
        assert (gc.IONESCU_SADDLE_NOTE in finding.display_value) is saddle_expected
    bultinck = gc.compute_geometry_charges(_conformer("CCO"), "u", {})
    assert "summary" not in bultinck.provenance.parameters
