"""Scores over the dipole's magnitude and five surface numbers, and the one rule they add: a number is read only at the settings that make it one quantity (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

What is pinned, because each was a way to ship a wrong number:

* **The dipole is Gasteiger's, of a species with no net charge.** One fact label ("Dipole") carries three charge models whose answers differ by a factor of up to five on one molecule (aspirin 0.89, 4.76 and 3.60 D), and a
  charged species has a dipole that depends on where the origin is put (acetate: 4.0 D about its centre of mass, 7.7 D about the centroid of its atoms). The result's own record says which, and a number made the other
  way is declined naming it.
* **The accessible areas are of the default probe, on the structure as it is.** Only the label of the accessible area carries the probe, so the other two would silently change with it; the van der Waals area and volume
  touch no probe and are read from a result made with any. The major microspecies is a different structure under the same labels, and it is declined for all five.
* **A structure of several fragments has neither** (the eight sizes' rule, `whole_structure`): where one ion sits beside the other is arbitrary.

Each is held in three places: the rule on a bare record, the reader on stored results, and the real services end to end, where the store keeps ONE result per geometry and method and so the settings of the last run are what a score
meets.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool

from openchem.bootstrap import build_service_container
from openchem.chem import charge_evaluation, surface_analysis
from openchem.chem.calculation_input import FRAGMENTS_KEY
from openchem.domain.calculator import GEOMETRY, CalculationRequest
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_envelope import SCORES_NOTE, score_envelope_of
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_outputs import approved_output
from openchem.domain.score_value import (
    CHARGE_MODEL_KEY,
    DEFAULT_PROBE,
    GASTEIGER_MODEL,
    MICROSPECIES_KEY,
    ORIGIN_INDEPENDENT_KEY,
    PH_KEY,
    SOLVENT_RADIUS_KEY,
    InputState,
    ScoreStatus,
    not_applicable_reason,
    read_output,
)
from tests.test_dipole_typed import _gasteiger_dipole
from tests.test_score_geometry_sizes import _model, _scored
from tests.test_score_value import _entries

EEM = "eem_bultinck2002_part1"
QEQ = "qeq_rg1991_lambda_half_h_experimental"

_DIPOLE = "calculator:dipole_moment:Dipole"
_PREFIX = "calculator:surface_analysis:"
_ASA, _HYDROPHOBIC, _POLAR = _PREFIX + "ASA (solvent accessible)", _PREFIX + "ASA_H (hydrophobic)", _PREFIX + "ASA_P (polar)"
_VDW_AREA, _VDW_VOLUME = _PREFIX + "van der Waals surface area", _PREFIX + "van der Waals volume"
_ACCESSIBLE = [_ASA, _HYDROPHOBIC, _POLAR]
_FUSED = [_VDW_AREA, _VDW_VOLUME]

_UNSET = object()


def _drain(qapp):
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(60):
        qapp.processEvents()


@pytest.fixture()
def services():
    return build_service_container()


# --- the keys and the two literals are the producers' -----------------------------------------------------------------------------------------------


def test_the_domain_reads_the_literals_the_producers_write():
    assert GASTEIGER_MODEL == charge_evaluation.GASTEIGER
    assert DEFAULT_PROBE == surface_analysis.DEFAULT_SOLVENT_RADIUS


def test_the_provenance_keys_are_the_ones_a_real_result_records(services):
    from rdkit import Chem

    from tests.conformer_panel import panel

    registry = services.calculator_registry
    glycine = panel()["glycine"]
    dipole = registry.compute("dipole_moment", Chem.Mol(glycine), "m", {}).provenance.parameters
    assert dipole[CHARGE_MODEL_KEY] == GASTEIGER_MODEL and dipole[ORIGIN_INDEPENDENT_KEY] is True
    surface = registry.compute("surface_analysis", Chem.Mol(glycine), "m", {}).provenance.parameters
    assert surface[SOLVENT_RADIUS_KEY] == DEFAULT_PROBE and MICROSPECIES_KEY not in surface
    species = registry.compute("surface_analysis", Chem.Mol(glycine), "m", {"major_microspecies": True, "pH": 6.0}).provenance.parameters
    assert species[MICROSPECIES_KEY] is True and species[PH_KEY] == 6.0


# --- the rule on a bare record -----------------------------------------------------------------------------------------------------------------------


def _dipole_record(**overrides):
    values = {FRAGMENTS_KEY: 1, CHARGE_MODEL_KEY: GASTEIGER_MODEL, ORIGIN_INDEPENDENT_KEY: True}
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not _UNSET}


def _surface_record(**overrides):
    values = {FRAGMENTS_KEY: 1, SOLVENT_RADIUS_KEY: 1.4}
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not _UNSET}


def test_a_gasteiger_dipole_of_a_neutral_species_in_one_piece_is_read():
    assert not_applicable_reason(approved_output(_DIPOLE), _dipole_record()) == ""


@pytest.mark.parametrize("model", [EEM, QEQ, "from_a_later_version"])
def test_a_dipole_of_another_charge_model_is_declined_and_names_it(model):
    reason = not_applicable_reason(approved_output(_DIPOLE), _dipole_record(**{CHARGE_MODEL_KEY: model}))
    assert model in reason and "only the Gasteiger dipole" in reason and "run it again with the Gasteiger charge model" in reason


@pytest.mark.parametrize("model", [_UNSET, None, 3, True, ["gasteiger"]])
def test_a_dipole_that_does_not_say_its_charge_model_is_declined_and_not_read_as_gasteiger(model):
    assert "does not say which charge model" in not_applicable_reason(approved_output(_DIPOLE), _dipole_record(**{CHARGE_MODEL_KEY: model}))


def test_the_dipole_of_a_species_with_a_net_charge_is_declined_and_says_why():
    reason = not_applicable_reason(approved_output(_DIPOLE), _dipole_record(**{ORIGIN_INDEPENDENT_KEY: False}))
    assert "net charge" in reason and "origin" in reason and "centre of mass" in reason and "neutral species only" in reason


@pytest.mark.parametrize("flag", [_UNSET, None, 1, 0, "True", [True]])
def test_a_dipole_that_does_not_say_whether_the_species_is_neutral_is_declined_and_not_read_as_neutral(flag):
    assert "does not say whether the species has a net charge" in not_applicable_reason(approved_output(_DIPOLE), _dipole_record(**{ORIGIN_INDEPENDENT_KEY: flag}))


def test_the_dipole_is_asked_about_fragments_first_then_the_model_then_the_charge():
    entry = approved_output(_DIPOLE)
    assert "2 separate fragments" in not_applicable_reason(entry, _dipole_record(**{FRAGMENTS_KEY: 2, CHARGE_MODEL_KEY: EEM, ORIGIN_INDEPENDENT_KEY: False}))
    reason = not_applicable_reason(entry, _dipole_record(**{CHARGE_MODEL_KEY: EEM, ORIGIN_INDEPENDENT_KEY: False}))
    assert EEM in reason and "net charge" not in reason


@pytest.mark.parametrize("output_id", _ACCESSIBLE + _FUSED)
def test_a_surface_number_at_the_default_probe_on_the_structure_as_it_is_is_read(output_id):
    assert not_applicable_reason(approved_output(output_id), _surface_record()) == ""
    assert not_applicable_reason(approved_output(output_id), _surface_record(**{MICROSPECIES_KEY: False})) == ""


@pytest.mark.parametrize("output_id", _ACCESSIBLE)
@pytest.mark.parametrize("probe", [1.2, 0.0, 2.0, 1, 1.4000001])
def test_an_accessible_area_made_with_another_probe_is_declined_and_names_it(output_id, probe):
    reason = not_applicable_reason(approved_output(output_id), _surface_record(**{SOLVENT_RADIUS_KEY: probe}))
    assert f"probe of radius {float(probe):g} Å" in reason and "only the 1.4 Å probe" in reason and "with the default probe" in reason


@pytest.mark.parametrize("output_id", _FUSED)
@pytest.mark.parametrize("probe", [1.2, 0.0, 2.0, _UNSET, None])
def test_the_van_der_waals_numbers_touch_no_probe_so_any_probe_is_read(output_id, probe):
    assert not_applicable_reason(approved_output(output_id), _surface_record(**{SOLVENT_RADIUS_KEY: probe})) == ""


@pytest.mark.parametrize("output_id", _ACCESSIBLE)
@pytest.mark.parametrize("probe", [_UNSET, None, True, "1.4", [1.4]])
def test_an_accessible_area_that_does_not_say_its_probe_is_declined_and_not_read_as_the_default(output_id, probe):
    assert "does not say which probe radius" in not_applicable_reason(approved_output(output_id), _surface_record(**{SOLVENT_RADIUS_KEY: probe}))


@pytest.mark.parametrize("output_id", _ACCESSIBLE + _FUSED)
def test_a_surface_number_of_the_major_microspecies_is_declined_for_all_five_and_names_the_ph(output_id):
    reason = not_applicable_reason(approved_output(output_id), _surface_record(**{MICROSPECIES_KEY: True, PH_KEY: 7.4}))
    assert "major microspecies at pH 7.4" in reason and "not the structure as it is" in reason and "without that option" in reason
    assert "major microspecies," in not_applicable_reason(approved_output(output_id), _surface_record(**{MICROSPECIES_KEY: True})), "with no pH recorded it still says what it is"


def test_an_accessible_area_of_the_microspecies_at_another_probe_names_the_probe_and_a_van_der_waals_one_names_the_microspecies():
    values = _surface_record(**{MICROSPECIES_KEY: True, PH_KEY: 7.4, SOLVENT_RADIUS_KEY: 2.0})
    assert "probe of radius 2 Å" in not_applicable_reason(approved_output(_ASA), values)
    assert "major microspecies" in not_applicable_reason(approved_output(_VDW_VOLUME), values)


@pytest.mark.parametrize("output_id", [_DIPOLE, *_ACCESSIBLE, *_FUSED])
def test_every_one_of_the_six_declines_a_salt_before_asking_anything_else(output_id):
    record = _dipole_record(**{FRAGMENTS_KEY: 2}) if output_id == _DIPOLE else _surface_record(**{FRAGMENTS_KEY: 2})
    reason = not_applicable_reason(approved_output(output_id), record)
    assert "2 separate fragments" in reason and "score the parent structure" in reason


def test_a_drawing_output_is_not_asked_about_any_of_these_settings():
    assert not_applicable_reason(approved_output("descriptor:tpsa"), {CHARGE_MODEL_KEY: EEM, SOLVENT_RADIUS_KEY: 9.0, MICROSPECIES_KEY: True}) == ""
    assert not_applicable_reason(approved_output("descriptor:pmi1"), {CHARGE_MODEL_KEY: EEM, SOLVENT_RADIUS_KEY: 9.0, MICROSPECIES_KEY: True}) == "", "a shape descriptor has no settings either"


# --- through `read_output`, with results put in the store directly ------------------------------------------------------------------------------------


def _stored(report_id, facts, *, key="", fingerprint="gfp-now", method="rdkit", **record):
    provenance = Provenance(created_by="core", method=method, parameters={
        "input_conformer_id": "1a2b3c4d5e6f", "input_conformer_index": 0, "input_conformer_energy": -4.5, "input_force_field": "MMFF94", **record,
    })
    result = ReportResult(molecule_uuid="m", report_id=report_id, name=report_id, facts=tuple(facts), cache_state=CacheState.COMPLETED, provenance=provenance)
    return StoredResult(ResultIdentity("m", report_id, GEOMETRY, fingerprint, report_id, key), result)


def _fact(label, value, units):
    return Fact(FactCategory.GEOMETRY, label, value, f"{value:.2f}", "Molecular Surface Area (3D)", Basis.HEURISTIC, units=units)


def _dipole(value=1.62, *, key="", method="rdkit", units="Debye", **record):
    base = {FRAGMENTS_KEY: 1, CHARGE_MODEL_KEY: GASTEIGER_MODEL, ORIGIN_INDEPENDENT_KEY: True, **record}
    return _stored("dipole_moment", [_fact("Dipole", value, units)], key=key, method=method, **base)


def _surface(*, key="", **record):
    facts = [_fact("ASA (solvent accessible)", 361.3, "Å²"), _fact("ASA_H (hydrophobic)", 239.1, "Å²"), _fact("ASA_P (polar)", 122.2, "Å²"),
             _fact("van der Waals surface area", 196.2, "Å²"), _fact("van der Waals volume", 155.1, "Å³")]
    return _stored("surface_analysis", facts, key=key, **{FRAGMENTS_KEY: 1, SOLVENT_RADIUS_KEY: 1.4, **record})


def test_a_current_dipole_is_read_and_names_its_conformer():
    read = read_output(_DIPOLE, _entries(_dipole(1.62)), 3)
    assert read.state is InputState.READ and read.value == pytest.approx(1.62)
    assert read.geometry.startswith("conformer 1 (id 1a2b3c4d") and "MMFF94 energy -4.50 kcal/mol" in read.geometry


def test_an_eem_dipole_alone_gives_no_number_and_a_gasteiger_one_beside_it_is_read():
    """The store keeps ONE dipole per geometry (`SessionResultStore.put` keys on the result id, the input, the fingerprint and the method version, and the charge model is none of those), so the application's own
    runs never leave an EEM and a Gasteiger result side by side. If two were held (a saved file from another build), the one a score cannot read is set aside and is no obstacle to the one it can."""
    eem = _dipole(4.76, key="eem", method=EEM, **{CHARGE_MODEL_KEY: EEM})
    alone = read_output(_DIPOLE, _entries(eem), 3)
    assert alone.state is InputState.NOT_APPLICABLE and alone.value is None and EEM in alone.note
    both = read_output(_DIPOLE, _entries(_dipole(0.89), eem), 3)
    assert both.state is InputState.READ and both.value == pytest.approx(0.89)


def test_the_dipole_of_a_charged_species_alone_gives_no_number():
    read = read_output(_DIPOLE, _entries(_dipole(4.0, **{ORIGIN_INDEPENDENT_KEY: False})), 3)
    assert read.state is InputState.NOT_APPLICABLE and "net charge" in read.note


def test_a_dipole_that_carries_another_unit_is_refused_and_nothing_is_converted():
    assert read_output(_DIPOLE, _entries(_dipole(1.62, units="D")), 3).state is InputState.UNIT


def test_one_result_made_with_another_probe_is_declined_for_the_accessible_areas_and_read_for_the_van_der_Waals_numbers():
    entries = _entries(_surface(**{SOLVENT_RADIUS_KEY: 1.2}))
    for output_id in _ACCESSIBLE:
        read = read_output(output_id, entries, 3)
        assert read.state is InputState.NOT_APPLICABLE and "probe of radius 1.2 Å" in read.note, output_id
    for output_id in _FUSED:
        assert read_output(output_id, entries, 3).state is InputState.READ, output_id


def test_the_microspecies_result_is_declined_for_all_five_and_the_plain_one_is_read():
    species = _entries(_surface(**{MICROSPECIES_KEY: True, PH_KEY: 7.4}))
    assert {read_output(output_id, species, 3).state for output_id in _ACCESSIBLE + _FUSED} == {InputState.NOT_APPLICABLE}
    plain = _entries(_surface())
    values = {output_id: read_output(output_id, plain, 3) for output_id in _ACCESSIBLE + _FUSED}
    assert {read.state for read in values.values()} == {InputState.READ}
    assert values[_VDW_VOLUME].value == pytest.approx(155.1) and values[_ASA].value == pytest.approx(361.3)


# --- through the real services ------------------------------------------------------------------------------------------------------------------------


def _run(services, qapp, model, calculator, **parameters):
    definition = services.calculator_registry.get(calculator)
    arguments = {p.name: p.default for p in definition.parameters} | parameters
    services.descriptor_service.run_calculator(model, CalculationRequest(calculator_id=calculator, molecule_uuid=model.uuid, parameters=arguments))
    _drain(qapp)


def _score(label, formula, unit, output_id):
    return dict(label=label, formula=formula, result_unit=unit, inputs=[("a", output_id)])


_DOUBLE_DIPOLE = _score("Twice the moment", "2 * a", "D", _DIPOLE)
_REACH_OF_ASA = _score("Accessible twice", "2 * a", "Å^2", _ASA)
_VOLUME_SCORE = _score("Volume doubled", "2 * a", "Å^3", _VDW_VOLUME)


def _conformer(services, model):
    from openchem.chem.calculation_input import canonical_conformer

    return services.chemistry_engine.mol_from_molblock(canonical_conformer(model).molblock)


def test_a_score_over_the_dipole_is_the_formula_of_the_gasteiger_dipole_of_the_conformer_every_calculation_uses(services, qapp):
    model = _model(services, "CC(=O)Oc1ccccc1C(=O)O", name="Aspirin")
    service, _ = _scored(services, model, _DOUBLE_DIPOLE)
    assert service.values_for(model)[0].status is ScoreStatus.REFUSED
    _run(services, qapp, model, "dipole_moment")
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.VALUE
    assert value.value == pytest.approx(2 * _gasteiger_dipole(_conformer(services, model)), rel=1e-5)
    from openchem.chem.calculation_input import canonical_conformer

    assert f"id {canonical_conformer(model).conformer_id[:8]}" in value.inputs[0].geometry, "the conformer is named in the evidence"


def test_a_charged_species_has_a_surface_and_no_dipole(services, qapp):
    model = _model(services, "CC(=O)[O-]", relax=False, name="Acetate")
    service, _ = _scored(services, model, _DOUBLE_DIPOLE, _VOLUME_SCORE)
    _run(services, qapp, model, "dipole_moment")
    _run(services, qapp, model, "surface_analysis")
    dipole, volume = service.values_for(model)
    assert dipole.status is ScoreStatus.REFUSED and "net charge" in dipole.reason and "neutral species only" in dipole.reason
    assert volume.status is ScoreStatus.VALUE, "the surface of an ion is its own, and the van der Waals volume of it is read"


def test_the_zwitterion_has_no_net_charge_so_its_dipole_is_read(services, qapp):
    model = _model(services, "[NH3+]CC(=O)[O-]", name="Glycine zwitterion")
    service, _ = _scored(services, model, _DOUBLE_DIPOLE)
    _run(services, qapp, model, "dipole_moment")
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(2 * _gasteiger_dipole(_conformer(services, model)), rel=1e-5)


def test_an_eem_run_replaces_the_gasteiger_dipole_and_a_score_then_says_to_run_gasteiger_again(services, qapp):
    """The store keeps one dipole per geometry, and the charge model is not part of its slot: running EEM REPLACES the Gasteiger result, exactly as a surface run with another probe replaces the default one.
    The score then has no number, says which model made the dipole and what to do, and has its number again when Gasteiger is run again."""
    model = _model(services, "CC(C)=O", name="Acetone")
    service, _ = _scored(services, model, _DOUBLE_DIPOLE)
    _run(services, qapp, model, "dipole_moment")
    (first,) = service.values_for(model)
    assert first.status is ScoreStatus.VALUE and first.value == pytest.approx(2 * _gasteiger_dipole(_conformer(services, model)), rel=1e-5)
    _run(services, qapp, model, "dipole_moment", charge_model=EEM)
    (replaced,) = service.values_for(model)
    assert replaced.status is ScoreStatus.REFUSED and replaced.value is None
    assert EEM in replaced.reason and "only the Gasteiger dipole" in replaced.reason and "run it again with the Gasteiger charge model" in replaced.reason
    _run(services, qapp, model, "dipole_moment", charge_model=QEQ)
    assert service.values_for(model)[0].status is ScoreStatus.REFUSED
    _run(services, qapp, model, "dipole_moment")
    (again,) = service.values_for(model)
    assert again.status is ScoreStatus.VALUE and again.value == pytest.approx(first.value, rel=1e-12)


def test_a_surface_run_with_another_probe_is_not_what_an_accessible_score_reads_and_the_default_run_is(services, qapp):
    model = _model(services, "CC(=O)Oc1ccccc1C(=O)O", name="Aspirin")
    service, _ = _scored(services, model, _REACH_OF_ASA, _VOLUME_SCORE)
    _run(services, qapp, model, "surface_analysis", solvent_radius=1.2)
    accessible, volume = service.values_for(model)
    assert accessible.status is ScoreStatus.REFUSED and "probe of radius 1.2 Å" in accessible.reason and "default probe" in accessible.reason
    assert volume.status is ScoreStatus.VALUE, "the van der Waals volume touches no probe"
    _run(services, qapp, model, "surface_analysis")
    accessible_default, volume_default = service.values_for(model)
    assert accessible_default.status is ScoreStatus.VALUE, "the store keeps one result per geometry, so the default run replaces the other and the score has its number again"
    assert volume_default.value == pytest.approx(volume.value, rel=1e-12)
    assert accessible_default.value > 0 and accessible_default.value != pytest.approx(volume.value)


def test_a_surface_run_on_the_major_microspecies_is_not_read_and_the_default_run_is(services, qapp):
    model = _model(services, "CC(=O)Oc1ccccc1C(=O)O", name="Aspirin")
    service, _ = _scored(services, model, _REACH_OF_ASA, _VOLUME_SCORE)
    _run(services, qapp, model, "surface_analysis", major_microspecies=True, pH=7.4)
    for value in service.values_for(model):
        assert value.status is ScoreStatus.REFUSED and "major microspecies at pH 7.4" in value.reason, value.definition.label
    _run(services, qapp, model, "surface_analysis")
    assert all(value.status is ScoreStatus.VALUE for value in service.values_for(model))


def test_a_ratio_of_the_polar_to_the_whole_accessible_area_is_a_plain_number(services, qapp):
    model = _model(services, "CC(=O)Oc1ccccc1C(=O)O", name="Aspirin")
    ratio = dict(label="Polar share", formula="polar / whole", result_unit="1", inputs=[("polar", _POLAR), ("whole", _ASA)])
    service, _ = _scored(services, model, ratio)
    _run(services, qapp, model, "surface_analysis")
    (value,) = service.values_for(model)
    assert value.status is ScoreStatus.VALUE and 0.2 < value.value < 0.5
    assert value.value == pytest.approx(122.23 / 361.27, rel=0.02), "aspirin's recorded split: 122.23 of 361.27 Å²"


@pytest.mark.parametrize("calculator", ["dipole_moment", "surface_analysis"])
def test_a_salt_has_neither_a_dipole_nor_a_surface_and_its_parent_has_both(services, qapp, calculator):
    salt = _model(services, "CC(=O)[O-].[Na+]", relax=False, name="Sodium acetate")
    definitions = [_DOUBLE_DIPOLE] if calculator == "dipole_moment" else [_REACH_OF_ASA, _VOLUME_SCORE]
    service, _ = _scored(services, salt, *definitions)
    _run(services, qapp, salt, calculator)
    for value in service.values_for(salt):
        assert value.status is ScoreStatus.REFUSED and value.value is None
        assert "2 separate fragments" in value.reason and "score the parent structure" in value.reason
    parent = _model(services, "CC(=O)O", name="Acetic acid")
    service_two, _ = _scored(services, parent, *definitions)
    _run(services, qapp, parent, calculator)
    assert all(value.status is ScoreStatus.VALUE for value in service_two.values_for(parent))


def _dichloroethane(services, name: str, dihedral: float):
    """1,2-dichloroethane with the Cl-C-C-Cl angle set by hand: 180 is anti, 65 is gauche."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolTransforms

    from openchem.domain.conformer import ConformerModel

    mol = Chem.AddHs(Chem.MolFromSmiles("ClCCCl"))
    AllChem.EmbedMolecule(mol, randomSeed=3)
    AllChem.MMFFOptimizeMolecule(mol)
    rdMolTransforms.SetDihedralDeg(mol.GetConformer(), 0, 1, 2, 3, dihedral)
    model = _model(services, "ClCCCl", name=name)
    model.conformers = [ConformerModel(molblock=services.chemistry_engine.mol_to_molblock(mol), energy=-1.0, method="mmff94")]
    return model


def test_a_dipole_of_one_conformer_is_not_the_dipole_of_another(services, qapp):
    """1,2-dichloroethane is nothing anti and about 2 D gauche: the number is the conformer's, which is why the evidence names which conformer it is."""
    values = {}
    for name, angle in (("anti", 180.0), ("gauche", 65.0)):
        model = _dichloroethane(services, name, angle)
        service, _ = _scored(services, model, _DOUBLE_DIPOLE)
        _run(services, qapp, model, "dipole_moment")
        (value,) = service.values_for(model)
        assert value.status is ScoreStatus.VALUE
        assert value.value == pytest.approx(2 * _gasteiger_dipole(_conformer(services, model)), rel=1e-5, abs=1e-6)
        values[name] = value.value / 2
    assert values["anti"] == pytest.approx(0.0, abs=0.05) and values["gauche"] > 1.5, values


# --- what the assistant is told ------------------------------------------------------------------------------------------------------------------


def test_the_assistant_is_told_what_the_dipole_and_the_surface_numbers_are_read_as():
    assert "The dipole is read only as the magnitude from Gasteiger charges of a species with no net charge" in SCORES_NOTE
    assert "the accessible areas only at the 1.4 Å probe on the structure as it is" in SCORES_NOTE
    assert "a dipole is of one conformer, and a flexible molecule's differs between its conformers" in SCORES_NOTE
    assert "the dipole was not Gasteiger's or is of a charged species" in SCORES_NOTE and "another probe than 1.4 Å or on the major microspecies" in SCORES_NOTE


def test_the_assistant_gets_the_state_and_the_reason_of_a_dipole_it_may_not_read(services, qapp):
    model = _model(services, "CC(C)=O", name="Acetone")
    service, _ = _scored(services, model, _DOUBLE_DIPOLE)
    _run(services, qapp, model, "dipole_moment", charge_model=EEM)
    (value,) = service.values_for(model)
    item = score_envelope_of(value)["inputs"][0]
    assert item["state"] == "not_applicable" and EEM in item["note"] and "value" not in item
