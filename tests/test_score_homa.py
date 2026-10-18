"""Scores over HOMA's two extremes, read only from an ORCA-optimised geometry (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

What is pinned, because each was a way to ship a wrong number:

* **The extremes are one ring's own value each**, reproduced here from Krygowski's parameter table and the conformer's bond lengths without the producer's code, and never a sum or a mean (the report
  declines a total because it would average the rings' local character away). They exist only when every ring has a value, so "the highest" can never quietly leave a ring out.
* **A force-field conformer is not a measurement of the rings.** Its bond lengths are the force field's own, so HOMA on it says what the force field was told: a score reads the extremes only from a
  conformer a quantum calculation optimised (`ApprovedOutput.needs_quantum_geometry`), refuses any other with the reason and the cure, and refuses a result that does not say what made its geometry.
* **The evidence names the level of theory**, because the level moves the number (naphthalene's rings: 0.94 on MMFF94, 0.66 at HF/STO-3G, 0.77 at HF/def2-SVP, 0.74 at B3LYP/def2-SVP, measured with
  real ORCA), and says so when it was not recorded.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.chem import aromaticity
from openchem.chem.aromaticity import HIGHEST_RING_LABEL, LOWEST_RING_LABEL, compute_aromaticity
from openchem.chem.calculation_input import (
    CONFORMER_METHOD_KEY,
    LEVEL_OF_THEORY_KEY,
    canonical_conformer,
    geometry_provenance,
)
from openchem.domain.calculator import GEOMETRY, CalculationRequest
from openchem.domain.common import RUN_METHOD_BASIS, CacheState, Provenance
from openchem.domain.conformer import ORCA_OPTIMIZED, ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_outputs import APPROVED, approved_output
from openchem.domain.score_value import (
    CONFORMER_METHOD_KEY as DOMAIN_METHOD_KEY,
)
from openchem.domain.score_value import (
    EARLIER_GEOMETRY,
    LEVEL_OF_THEORY_KEY as DOMAIN_LEVEL_KEY,
    NEEDS_AN_ORCA_GEOMETRY,
    InputState,
    ScoreStatus,
    evaluate_score,
    geometry_text,
    not_applicable_reason,
    read_output,
)
from openchem.services.score_service import ScoreService
from tests.test_score_value import _entries

_HIGHEST = f"calculator:homa_aromaticity:{HIGHEST_RING_LABEL}"
_LOWEST = f"calculator:homa_aromaticity:{LOWEST_RING_LABEL}"
_OUTPUTS = [approved_output(_HIGHEST), approved_output(_LOWEST)]
_PARAMETERS = json.loads((Path(aromaticity.__file__).parent / "data" / "homa_parameters.json").read_text(encoding="utf-8"))
_INDOLE = "c1ccc2[nH]ccc2c1"  # two rings of different HOMA: a benzene ring and a pyrrole ring


def _drain(qapp):
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(60):
        qapp.processEvents()


@pytest.fixture()
def services():
    return build_service_container()


def _embedded(smiles: str, seed: int = 7, *, relax: bool = True) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    if relax:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    return mol


def _by_hand(mol: Chem.Mol) -> list[float]:
    """HOMA of every ring of `mol`, from Krygowski's table and the conformer's bond lengths alone: 1 - (1/n) * sum alpha * (R_opt - R)^2 over the ring's bonds."""
    table = {frozenset(row["elements"]): row for row in _PARAMETERS["bonds"].values() if not row.get("deprecated")}
    positions = mol.GetConformer().GetPositions()
    values = []
    for ring in mol.GetRingInfo().AtomRings():
        total = 0.0
        for k in range(len(ring)):
            i, j = ring[k], ring[(k + 1) % len(ring)]
            row = table[frozenset((mol.GetAtomWithIdx(i).GetSymbol(), mol.GetAtomWithIdx(j).GetSymbol()))]
            total += row["alpha"] * (row["R_opt"] - float(((positions[i] - positions[j]) ** 2).sum() ** 0.5)) ** 2
        values.append(1.0 - total / len(ring))
    return values


def _facts(mol: Chem.Mol, places: int = 6) -> dict[str, Fact]:
    result = compute_aromaticity(Chem.Mol(mol), "m", {"decimal_places": places})
    return {fact.label: fact for fact in result.facts}


# --- the two extremes are one ring's own value each ------------------------------------------------------------------------------------------


def test_one_ring_has_equal_extremes_and_they_are_its_own_value():
    mol = _embedded("c1ccccc1")
    facts = _facts(mol)
    (ring_value,) = _by_hand(mol)
    assert facts[HIGHEST_RING_LABEL].value == pytest.approx(ring_value, rel=1e-9) == pytest.approx(facts[LOWEST_RING_LABEL].value, rel=1e-9)


@pytest.mark.parametrize("smiles", [_INDOLE, "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "c1ccc2ccccc2c1", "O=C1C=CC(=O)C=C1c1ccccc1"])
def test_the_extremes_are_the_highest_and_the_lowest_ring_value_by_hand(smiles):
    mol = _embedded(smiles)
    by_hand = _by_hand(mol)
    facts = _facts(mol)
    assert len(by_hand) >= 2
    assert facts[HIGHEST_RING_LABEL].value == pytest.approx(max(by_hand), rel=1e-9)
    assert facts[LOWEST_RING_LABEL].value == pytest.approx(min(by_hand), rel=1e-9)


def test_two_different_rings_give_two_different_extremes_and_neither_is_their_mean():
    mol = _embedded(_INDOLE)
    by_hand = _by_hand(mol)
    facts = _facts(mol)
    assert max(by_hand) - min(by_hand) > 0.05, "the premise: the rings differ, or this could not tell an extreme from a mean"
    mean = sum(by_hand) / len(by_hand)
    assert facts[HIGHEST_RING_LABEL].value > mean + 1e-3 and facts[LOWEST_RING_LABEL].value < mean - 1e-3


def test_each_extreme_is_a_typed_number_without_a_unit_and_highlights_the_ring_that_holds_it():
    mol = _embedded(_INDOLE)
    facts = _facts(mol)
    for label in (HIGHEST_RING_LABEL, LOWEST_RING_LABEL):
        assert isinstance(facts[label].value, float) and facts[label].units == "" and facts[label].basis is Basis.DETERMINISTIC
        assert "Not a sum or a mean" in " ".join(facts[label].limitations)
    rings = {tuple(sorted(ring)): value for ring, value in zip(mol.GetRingInfo().AtomRings(), _by_hand(mol))}
    assert rings[tuple(sorted(facts[HIGHEST_RING_LABEL].highlight))] == pytest.approx(facts[HIGHEST_RING_LABEL].value, rel=1e-9)
    assert rings[tuple(sorted(facts[LOWEST_RING_LABEL].highlight))] == pytest.approx(facts[LOWEST_RING_LABEL].value, rel=1e-9)


def test_the_displayed_extremes_follow_the_decimal_places_and_the_typed_value_does_not():
    mol = _embedded(_INDOLE)
    coarse, fine = _facts(mol, 1), _facts(mol, 5)
    assert coarse[HIGHEST_RING_LABEL].display_value == f"{coarse[HIGHEST_RING_LABEL].value:.1f}"
    assert coarse[HIGHEST_RING_LABEL].value == fine[HIGHEST_RING_LABEL].value, "a score is made from the number and never from the rounded line"


def test_a_ring_with_no_parameters_leaves_both_extremes_without_a_number_and_says_why():
    """A silicon ring has no HOMA parameters. The highest of the others would leave it out without saying so, so neither extreme is given."""
    mol = _embedded("c1ccccc1[Si]1CCCC1", seed=11)
    result = compute_aromaticity(Chem.Mol(mol), "m", {})
    facts = {fact.label: fact for fact in result.facts}
    assert result.cache_state is CacheState.COMPLETED
    assert any(fact.value is not None for fact in result.facts if fact.label not in facts or fact.label.endswith("C6")), "the benzene ring still has its own value"
    for label in (HIGHEST_RING_LABEL, LOWEST_RING_LABEL):
        assert facts[label].value is None and facts[label].display_value == "not available" and "no HOMA value" in " ".join(facts[label].limitations)


def test_a_structure_with_no_ring_is_refused_and_has_no_extreme():
    result = compute_aromaticity(_embedded("CCCCO"), "m", {})
    assert result.cache_state is CacheState.FAILED and not result.facts and "no rings" in result.error


def test_the_report_still_declines_a_total():
    from openchem.domain.common import TOTAL

    result = compute_aromaticity(_embedded(_INDOLE), "m", {})
    assert TOTAL in result.provenance.parameters, "an extreme is not a total: the report still declines one"


# --- what a force-field conformer is not -------------------------------------------------------------------------------------------------------


def _record(**overrides):
    values = {CONFORMER_METHOD_KEY: ORCA_OPTIMIZED, LEVEL_OF_THEORY_KEY: "B3LYP def2-SVP"}
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


@pytest.mark.parametrize("entry", _OUTPUTS, ids=lambda entry: entry.output_id)
def test_a_conformer_that_orca_optimised_is_read(entry):
    assert not_applicable_reason(entry, _record()) == ""
    assert not_applicable_reason(entry, _record(**{LEVEL_OF_THEORY_KEY: None})) == "", "an unrecorded level is named as unrecorded and does not stop the read"


@pytest.mark.parametrize("method", ["mmff94", "etkdg", "uff", "", "orca"])
@pytest.mark.parametrize("entry", _OUTPUTS, ids=lambda entry: entry.output_id)
def test_a_conformer_that_orca_did_not_optimise_is_declined_with_the_reason_and_the_cure(entry, method):
    reason = not_applicable_reason(entry, _record(**{CONFORMER_METHOD_KEY: method}))
    assert "ORCA did not optimise" in reason and "force field's own" in reason and "optimise the molecule in ORCA, then run it again" in reason


@pytest.mark.parametrize("method", [None, 3, True, ["orca_opt"]])
@pytest.mark.parametrize("entry", _OUTPUTS, ids=lambda entry: entry.output_id)
def test_a_result_that_does_not_say_what_made_its_geometry_is_declined_and_not_read_as_measured(entry, method):
    values = _record()
    values.pop(CONFORMER_METHOD_KEY)
    if method is not None:
        values[CONFORMER_METHOD_KEY] = method
    assert "does not say what made the geometry" in not_applicable_reason(entry, values)


def test_only_the_two_extremes_ask_what_made_the_geometry():
    for entry in APPROVED:
        if entry in _OUTPUTS or entry.input != GEOMETRY or entry.run_with:
            continue  # a number that asks which settings the calculator ran with has its own record to read: tests/test_score_dipole_surface.py
        values = {CONFORMER_METHOD_KEY: "mmff94", "input_fragments": 1, "input_geometry": "g", "measured_geometry": "g", "radius_scale": 1.0}
        assert not_applicable_reason(entry, values) == "", entry.output_id


def test_homa_has_no_fragment_or_settings_question_because_a_rings_value_does_not_depend_on_either():
    for entry in _OUTPUTS:
        assert not entry.whole_structure and not entry.measured_as and entry.unit == "1" and entry.carried_as == ""
        assert not_applicable_reason(entry, _record(**{"input_fragments": 3})) == ""


# --- what the evidence and the not-calculated notes say --------------------------------------------------------------------------------------


def test_the_evidence_names_the_level_of_theory_of_an_orca_conformer_and_says_so_when_it_was_not_recorded():
    base = {"input_conformer_id": "1a2b3c4d5e6f", "input_conformer_index": 1, "input_conformer_energy": None, "input_force_field": None}
    assert geometry_text({**base, CONFORMER_METHOD_KEY: ORCA_OPTIMIZED, LEVEL_OF_THEORY_KEY: "B3LYP def2-SVP"}) == "conformer 2 (id 1a2b3c4d, ORCA-optimised at B3LYP def2-SVP)"
    assert geometry_text({**base, CONFORMER_METHOD_KEY: ORCA_OPTIMIZED}) == "conformer 2 (id 1a2b3c4d, ORCA-optimised)"
    assert "ORCA" not in geometry_text({**base, CONFORMER_METHOD_KEY: "mmff94", "input_conformer_energy": -4.5, "input_force_field": "MMFF94"})
    assert geometry_text(base) == "conformer 2 (id 1a2b3c4d)", "an older result that names no method says what it always said"


def test_the_not_calculated_notes_say_the_conformer_must_be_one_orca_optimised():
    entry_note = lambda conformers: read_output(_HIGHEST, _entries(), conformers).note  # noqa: E731
    assert entry_note(0) == NEEDS_AN_ORCA_GEOMETRY and "optimised in ORCA" in NEEDS_AN_ORCA_GEOMETRY
    assert entry_note(3).startswith("it has not been calculated on this molecule's conformer yet") and "a force-field conformer is declined" in entry_note(3)
    assert entry_note(None) == "it has not been calculated for this molecule"
    assert "ORCA" not in read_output("calculator:geometry_analysis:Max projection area", _entries(), 3).note, "the other geometry outputs say what they always said"


# --- the stamp -------------------------------------------------------------------------------------------------------------------------------


def test_the_two_spellings_of_each_key_are_one():
    assert CONFORMER_METHOD_KEY == DOMAIN_METHOD_KEY == "input_conformer_method"
    assert LEVEL_OF_THEORY_KEY == DOMAIN_LEVEL_KEY == "input_level_of_theory"


def _model_with(*conformers: ConformerModel) -> MoleculeModel:
    model = MoleculeModel(display_name="m")
    model.conformers = list(conformers)
    return model


def _block(mol: Chem.Mol) -> str:
    return Chem.MolToMolBlock(mol)


def test_a_force_field_conformer_records_its_method_and_no_level():
    stamp = geometry_provenance(_model_with(ConformerModel(molblock=_block(_embedded("CCO")), energy=-2.0, method="mmff94")), GEOMETRY)
    assert stamp[CONFORMER_METHOD_KEY] == "mmff94" and LEVEL_OF_THEORY_KEY not in stamp


def test_an_orca_conformer_records_its_method_and_the_level_the_run_was_made_at():
    run = Provenance(created_by="orca", method="orca", parameters={RUN_METHOD_BASIS: "HF STO-3G"})
    stamp = geometry_provenance(_model_with(ConformerModel(molblock=_block(_embedded("CCO")), energy=None, method=ORCA_OPTIMIZED, provenance=run)), GEOMETRY)
    assert stamp[CONFORMER_METHOD_KEY] == ORCA_OPTIMIZED and stamp[LEVEL_OF_THEORY_KEY] == "HF STO-3G"


def test_an_orca_conformer_with_no_recorded_level_leaves_the_level_out_and_a_drawing_result_has_neither():
    model = _model_with(ConformerModel(molblock=_block(_embedded("CCO")), energy=None, method=ORCA_OPTIMIZED))
    stamp = geometry_provenance(model, GEOMETRY)
    assert stamp[CONFORMER_METHOD_KEY] == ORCA_OPTIMIZED and LEVEL_OF_THEORY_KEY not in stamp
    assert CONFORMER_METHOD_KEY not in geometry_provenance(model, "drawing")


# --- through `read_output`, with results put in the store directly ---------------------------------------------------------------------------


def _stored(label, value, *, fingerprint="gfp-now", **record):
    fact = Fact(FactCategory.STRUCTURE, label, value, f"{value:.3f}", "homa_aromaticity", Basis.DETERMINISTIC, units="")
    provenance = Provenance(created_by="core", method="krygowski_1993_homa", parameters={
        "input_conformer_id": "1a2b3c4d5e6f", "input_conformer_index": 0, "input_conformer_energy": None, "input_force_field": None, **_record(**record),
    })
    result = ReportResult(molecule_uuid="m", report_id="homa_aromaticity", name="Aromaticity (HOMA)", facts=(fact,), cache_state=CacheState.COMPLETED, provenance=provenance)
    return StoredResult(ResultIdentity("m", "homa_aromaticity", GEOMETRY, fingerprint, "homa_aromaticity"), result)


def test_an_orca_result_is_read_and_names_its_level():
    read = read_output(_HIGHEST, _entries(_stored(HIGHEST_RING_LABEL, 0.74)), 3)
    assert read.state is InputState.READ and read.value == pytest.approx(0.74)
    assert read.geometry == "conformer 1 (id 1a2b3c4d, ORCA-optimised at B3LYP def2-SVP)"


def test_a_force_field_result_gives_no_number_and_the_score_says_what_to_do():
    stored = _stored(HIGHEST_RING_LABEL, 0.94, **{CONFORMER_METHOD_KEY: "mmff94"})
    read = read_output(_HIGHEST, _entries(stored), 3)
    assert read.state is InputState.NOT_APPLICABLE and read.value is None and "optimise the molecule in ORCA" in read.note
    from openchem.domain.score_definition import ScoreDefinition

    score = ScoreDefinition(score_id="user.t", label="Ring ceiling", formula="h", result_unit="1", inputs=(("h", _HIGHEST),))
    value = evaluate_score(score, _entries(stored), 3)
    assert value.status is ScoreStatus.REFUSED and value.value is None and "ORCA did not optimise" in value.reason


def test_a_result_of_an_earlier_geometry_is_refused_as_such_even_when_it_was_orca():
    read = read_output(_HIGHEST, _entries(_stored(HIGHEST_RING_LABEL, 0.74, fingerprint="gfp-old")), 3)
    assert read.state is InputState.NOT_CURRENT and read.note == EARLIER_GEOMETRY


# --- through the real services, with a conformer a quantum calculation produced --------------------------------------------------------------


def _model(services, smiles: str = _INDOLE) -> MoleculeModel:
    engine = services.chemistry_engine
    model = MoleculeModel(display_name="Indole")
    engine.set_structure_from_smiles(model, smiles)
    mol = _embedded(smiles)
    model.conformers = [ConformerModel(molblock=engine.mol_to_molblock(mol), energy=-1.0, method="mmff94")]
    return model


def _orca_standin(services, model: MoleculeModel, level: str = "B3LYP def2-SVP") -> ConformerModel:
    """What an ORCA optimisation leaves behind: the same atoms at other bond lengths, no force-field energy, the run's level in its provenance. (A real ORCA run is the drive's job.)"""
    engine = services.chemistry_engine
    mol = engine.mol_from_molblock(canonical_conformer(model).molblock)
    AllChem.UFFOptimizeMolecule(mol, maxIters=2000)
    run = Provenance(created_by="orca", method="orca", parameters={RUN_METHOD_BASIS: level})
    return ConformerModel(molblock=engine.mol_to_molblock(mol), energy=None, method=ORCA_OPTIMIZED, provenance=run)


def _scored(services, model):
    project = ProjectModel(name="homa")
    project.molecules.append(model)
    services.result_store_service.set_project(project)
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry, today=lambda: datetime.date(2026, 10, 17))
    service.set_project(project)
    service.create(label="Ring ceiling", formula="h", result_unit="1", inputs=[("h", _HIGHEST)])
    service.create(label="Ring floor", formula="l", result_unit="1", inputs=[("l", _LOWEST)])
    return service


def _run_homa(services, qapp, model):
    services.descriptor_service.run_calculator(model, CalculationRequest(calculator_id="homa_aromaticity", molecule_uuid=model.uuid, parameters={"decimal_places": 3}))
    _drain(qapp)


def test_a_score_reads_the_extremes_only_after_an_orca_geometry_and_follows_it(services, qapp):
    model = _model(services)
    service = _scored(services, model)
    ceiling, floor = service.values_for(model)
    assert all(value.status is ScoreStatus.REFUSED and "a force-field conformer is declined" in value.reason for value in (ceiling, floor))

    _run_homa(services, qapp, model)
    ceiling, floor = service.values_for(model)
    assert all(value.status is ScoreStatus.REFUSED and "ORCA did not optimise" in value.reason for value in (ceiling, floor)), "the force-field conformer's HOMA is a result, and is not read"
    force_field = canonical_conformer(model)

    orca = _orca_standin(services, model)
    model.conformers.append(orca)
    assert canonical_conformer(model) is orca
    assert all(value.status is ScoreStatus.REFUSED and EARLIER_GEOMETRY in value.reason for value in service.values_for(model)), "the force-field result is of an earlier geometry now"

    _run_homa(services, qapp, model)
    ceiling, floor = service.values_for(model)
    by_hand = _by_hand(services.chemistry_engine.mol_from_molblock(orca.molblock))
    assert ceiling.status is ScoreStatus.VALUE and floor.status is ScoreStatus.VALUE, (ceiling.reason, floor.reason)
    assert ceiling.value == pytest.approx(max(by_hand), abs=5e-4) and floor.value == pytest.approx(min(by_hand), abs=5e-4)
    assert ceiling.value > floor.value
    assert f"id {orca.conformer_id[:8]}" in ceiling.inputs[0].geometry and "ORCA-optimised at B3LYP def2-SVP" in ceiling.inputs[0].geometry
    force_field_values = _by_hand(services.chemistry_engine.mol_from_molblock(force_field.molblock))
    assert abs(max(force_field_values) - ceiling.value) > 1e-3, "the premise: the ORCA stand-in has other bond lengths, so the number moved with the geometry"

    model.conformers.remove(orca)  # Undo of the optimisation
    assert all(value.status is ScoreStatus.REFUSED and "ORCA did not optimise" in value.reason for value in service.values_for(model)), "back on the force-field conformer: its result is current again, and still not read"


def test_an_orca_conformer_with_no_recorded_level_is_read_and_says_it_is_orca_without_a_level(services, qapp):
    model = _model(services)
    service = _scored(services, model)
    orca = _orca_standin(services, model)
    model.conformers.append(ConformerModel(molblock=orca.molblock, energy=None, method=ORCA_OPTIMIZED))
    _run_homa(services, qapp, model)
    ceiling, _floor = service.values_for(model)
    assert ceiling.status is ScoreStatus.VALUE and ceiling.inputs[0].geometry.endswith("ORCA-optimised)")


def test_a_molecule_with_no_ring_says_so_and_a_salt_is_not_asked_about_fragments(services, qapp):
    model = _model(services, "CCCCO")
    service = _scored(services, model)
    model.conformers.append(_orca_standin(services, model))
    _run_homa(services, qapp, model)
    ceiling, _floor = service.values_for(model)
    assert ceiling.status is ScoreStatus.REFUSED and "no rings" in ceiling.reason

    salt = _model(services, "c1ccccc1C(=O)[O-].[Na+]")
    service_two = _scored(services, salt)
    salt.conformers.append(_orca_standin(services, salt))
    _run_homa(services, qapp, salt)
    value, _ = service_two.values_for(salt)
    assert value.status is ScoreStatus.VALUE, value.reason


def test_the_assistant_is_told_what_the_gate_means(services, qapp):
    from openchem.domain.result_envelope import SCORES_NOTE, score_envelope_of

    model = _model(services)
    service = _scored(services, model)
    _run_homa(services, qapp, model)
    item = score_envelope_of(service.values_for(model)[0])["inputs"][0]
    assert item["state"] == "not_applicable" and "ORCA did not optimise" in item["note"] and "value" not in item
    assert "The two HOMA outputs read bond lengths, so they are read only from a conformer a quantum calculation optimised" in SCORES_NOTE and "level of theory" in SCORES_NOTE
