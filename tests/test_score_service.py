"""The score service over a real project: definitions made, changed and removed; values read from the stored results (`services/score_service.py`).

Two kinds of test. The rules (a label may not look like a calculator, a bad formula stores nothing and says nothing, an edit keeps the id) run on records put
in the store directly, with the fingerprint the engine gives. And one runs the application's own path -- the real always-on descriptors through the real service
-- so a score is read from results the application made and not only from results this test dressed up.
"""

from __future__ import annotations

import datetime

import pytest

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition_store import ScoreDefinitionStore
from openchem.domain.score_formula import FormulaError, Problem
from openchem.domain.score_value import InputState, ScoreStatus
from openchem.events.events import ScoreDefinitionsChanged
from openchem.services.score_service import ScoreService

_PSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"


@pytest.fixture()
def services():
    return build_service_container()


@pytest.fixture()
def project(services):
    project = ProjectModel(name="Scores")
    model = MoleculeModel(display_name="Aspirin")
    services.chemistry_engine.set_structure_from_smiles(model, "CC(=O)Oc1ccccc1C(=O)O")
    project.molecules.append(model)
    services.result_store_service.set_project(project)
    return project


@pytest.fixture()
def scores(services, project):
    service = ScoreService(
        services.event_bus, services.result_store_service, services.calculator_registry, today=lambda: datetime.date(2026, 10, 14)
    )
    service.set_project(project)
    return service


@pytest.fixture()
def events(services):
    seen: list[ScoreDefinitionsChanged] = []
    services.event_bus.subscribe(ScoreDefinitionsChanged, seen.append)
    return seen


def _put(services, model, descriptor_id, value, units="", *, fingerprint=None):
    """A stored always-on descriptor of `model`, as the application's own recording would key it."""
    fingerprint = fingerprint or services.result_store_service.fingerprints_for(model)[DRAWING]
    result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", model.uuid, value=value, cache_state=CacheState.COMPLETED)
    services.result_store_service.store.put(StoredResult(ResultIdentity(model.uuid, f"descriptor:rdkit:{descriptor_id}", DRAWING, fingerprint, "rdkit"), result))


def _make(scores, **changes):
    arguments = dict(
        label="My blend", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1", inputs=[("psa", _PSA), ("logp", _LOGP)],
        owner="Alex", note="first",
    )
    arguments.update(changes)
    return scores.create(**arguments)


# --- making a score --------------------------------------------------------------------------------------------------------------


def test_a_new_score_gets_an_id_from_its_label_and_todays_date_and_is_stored(scores):
    definition = _make(scores)
    assert definition.score_id == "user.my_blend" and definition.created == "2026-10-14" and definition.owner == "Alex"
    assert scores.store.get("user.my_blend") is definition and definition.display_label == "My blend (user-defined, unvalidated)"


def test_two_scores_with_one_label_get_two_ids(scores):
    assert _make(scores).score_id == "user.my_blend"
    assert _make(scores).score_id == "user.my_blend_2"


def test_making_a_score_says_so_on_the_bus(scores, events, project):
    definition = _make(scores)
    assert events == [ScoreDefinitionsChanged(project_uuid=project.uuid, score_ids=(definition.score_id,))]


def test_a_score_that_does_not_check_is_not_stored_and_says_nothing(scores, events):
    with pytest.raises(FormulaError) as caught:
        _make(scores, formula="ramp(psa, 140, 60) *")
    assert caught.value.problem is Problem.SYNTAX
    assert len(scores.store) == 0 and events == []


@pytest.mark.parametrize("label", ["Dipole moment", "dipole_moment", "My dipole moment score", "logd", "LogD again"])
def test_a_label_close_to_a_registered_calculators_name_is_refused(scores, label):
    with pytest.raises(FormulaError, match="too close to") as caught:
        _make(scores, label=label)
    assert caught.value.problem is Problem.DEFINITION and len(scores.store) == 0


def test_every_registered_calculators_id_and_display_name_is_reserved(scores, services):
    names = set(scores.reserved_names())
    for definition in services.calculator_registry.definitions():
        assert definition.calculator_id in names and definition.display_name in names


def test_a_score_needs_a_project(services):
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry)
    with pytest.raises(ValueError, match="no open project"):
        service.create(label="x score", formula="logp", result_unit="1", inputs=[("logp", _LOGP)])


def test_check_runs_the_same_rules_without_storing(scores):
    from openchem.domain.score_definition import ScoreDefinition

    good = ScoreDefinition("user.t", "Tester", "logp", "1", (("logp", _LOGP),))
    assert scores.check(good).text == "logp"
    with pytest.raises(FormulaError):
        scores.check(ScoreDefinition("user.t", "Tester", "logp", "%", (("logp", _LOGP),)))
    assert len(scores.store) == 0


# --- changing and removing -------------------------------------------------------------------------------------------------------


def test_an_edit_keeps_the_id_and_the_date_and_changes_the_digest(scores, events):
    made = _make(scores)
    changed = scores.update(made.score_id, label="Renamed blend", formula="ramp(psa, 150, 60) * ramp(logp, 5, 2)")
    assert changed.score_id == made.score_id and changed.created == made.created and changed.label == "Renamed blend"
    assert changed.digest != made.digest and scores.store.get(made.score_id) is changed
    assert [e.score_ids for e in events] == [(made.score_id,), (made.score_id,)]


def test_renaming_alone_keeps_the_digest(scores):
    made = _make(scores)
    assert scores.update(made.score_id, label="Another name", note="changed").digest == made.digest


def test_an_edit_that_does_not_check_leaves_the_score_as_it_was_and_says_nothing(scores, events):
    made = _make(scores)
    events.clear()
    with pytest.raises(FormulaError):
        scores.update(made.score_id, result_unit="%")
    assert scores.store.get(made.score_id) is made and events == []


@pytest.mark.parametrize("field", ["schema_version", "created"])
def test_the_format_and_the_date_cannot_be_edited(scores, field):
    made = _make(scores)
    with pytest.raises(ValueError, match="cannot be changed"):
        scores.update(made.score_id, **{field: "x"})


def test_editing_a_score_that_is_not_there_is_a_key_error(scores):
    with pytest.raises(KeyError):
        scores.update("user.nothing", label="x")


def test_removing_a_score_says_so_and_removing_twice_does_not(scores, events):
    made = _make(scores)
    events.clear()
    assert scores.remove(made.score_id) is True and scores.remove(made.score_id) is False
    assert len(scores.store) == 0 and [e.score_ids for e in events] == [(made.score_id,)]


def test_a_score_that_was_kept_unread_cannot_be_edited_or_removed(services, project):
    newer = {"schema_version": 99, "score_id": "user.future", "label": "From the future"}
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry)
    service.set_project(project, ScoreDefinitionStore.from_dict({"version": 1, "definitions": [newer]}, project.uuid))
    with pytest.raises(KeyError):
        service.update("user.future", label="x")
    assert service.remove("user.future") is False and service.store.to_dict()["definitions"] == [newer]


# --- the lifecycle -------------------------------------------------------------------------------------------------------------------


def test_set_project_swaps_the_definitions_with_the_project(scores, services):
    _make(scores)
    other = ProjectModel(name="Other")
    scores.set_project(other)
    assert len(scores.store) == 0 and scores.store.project_uuid == other.uuid and scores.project is other


def test_a_store_for_another_project_is_ignored(scores, services, caplog):
    stranger = ScoreDefinitionStore("some-other-project")
    with caplog.at_level("WARNING", logger="openchem.scores"):
        scores.set_project(ProjectModel(name="Here"), stranger)
    assert scores.store is not stranger and len(scores.store) == 0
    assert any("Ignoring score definitions" in r.getMessage() for r in caplog.records)


def test_a_store_for_this_project_is_taken_as_it_is(services, project):
    store = ScoreDefinitionStore(project.uuid)
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry)
    service.set_project(project, store)
    assert service.store is store


# --- reading ---------------------------------------------------------------------------------------------------------------------------


def test_values_are_read_from_the_stored_results(scores, services, project):
    model = project.molecules[0]
    _make(scores)
    _put(services, model, "tpsa", 100.0, "Å²")
    _put(services, model, "mol_logp", 3.5)
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(0.25) and value.definition.score_id == "user.my_blend"


def test_nothing_is_calculated_by_reading(scores, services, project):
    model = project.molecules[0]
    _make(scores)
    before = len(services.result_store_service.store.all_results(model.uuid))
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.REFUSED and all(i.state is InputState.NOT_RUN for i in value.inputs)
    assert len(services.result_store_service.store.all_results(model.uuid)) == before


def test_editing_the_structure_makes_the_inputs_not_current(scores, services, project):
    model = project.molecules[0]
    _make(scores)
    _put(services, model, "tpsa", 100.0, "Å²")
    _put(services, model, "mol_logp", 3.5)
    services.chemistry_engine.set_structure_from_smiles(model, "CCO")
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.REFUSED and {i.state for i in value.inputs} == {InputState.NOT_CURRENT}
    assert "earlier structure" in value.reason


def test_another_molecule_has_its_own_results(scores, services, project):
    _make(scores)
    first = project.molecules[0]
    second = MoleculeModel(display_name="Ethanol")
    services.chemistry_engine.set_structure_from_smiles(second, "CCO")
    project.molecules.append(second)
    _put(services, first, "tpsa", 100.0, "Å²")
    _put(services, first, "mol_logp", 3.5)
    assert scores.values_for(first)[0].status is ScoreStatus.VALUE
    assert scores.values_for(second)[0].status is ScoreStatus.REFUSED


def test_a_molecule_with_nothing_drawn_refuses_every_score(scores, services, project):
    _make(scores)
    blank = MoleculeModel(display_name="Blank")
    project.molecules.append(blank)
    (value,) = scores.values_for(blank)
    assert value.status is ScoreStatus.REFUSED and value.value is None


def test_no_definitions_means_no_values_and_no_reading(scores, project):
    assert scores.values_for(project.molecules[0]) == ()


def test_constants_reach_the_value(scores, services, project):
    model = project.molecules[0]
    _make(scores, label="Wide window", formula="ramp(psa, hi, lo)", inputs=[("psa", _PSA)], constants=[Constant("hi", 140, "Å^2"), Constant("lo", 60, "Å^2")])
    _put(services, model, "tpsa", 100.0, "Å²")
    assert scores.values_for(model)[0].value == pytest.approx(0.5)


# --- the second policy ------------------------------------------------------------------------------------------------------------------


def test_a_score_made_with_a_default_is_the_second_policy_in_format_two_and_one_without_is_as_it_always_was(scores):
    plain = _make(scores)
    assert plain.on_missing == "refuse" and plain.schema_version == 1 and plain.defaults == ()
    defaulting = _make(scores, label="With a default", defaults=[("logp", 2)])
    assert defaulting.on_missing == "default" and defaulting.schema_version == 2 and defaulting.defaults == (("logp", 2.0),)
    assert isinstance(defaulting.defaults[0][1], float) and hash(defaulting), "the shape a file gives back, so the parsed-formula cache can key on it"


def test_a_default_for_an_input_the_score_does_not_read_is_refused_and_stores_nothing(scores, events):
    with pytest.raises(FormulaError, match="not one of the inputs"):
        _make(scores, defaults=[("ghost", 1.0)])
    assert len(scores.store) == 0 and events == []


def test_a_default_that_is_not_a_finite_number_is_refused(scores):
    with pytest.raises(FormulaError, match="finite number"):
        _make(scores, defaults=[("logp", float("nan"))])
    with pytest.raises(ValueError, match="bool"):
        _make(scores, defaults=[("logp", True)])
    assert len(scores.store) == 0


def test_editing_the_defaults_moves_the_policy_and_the_format_with_them_and_keeps_the_id(scores, events):
    made = _make(scores)
    gained = scores.update(made.score_id, defaults=[("logp", 3.5)])
    assert gained.score_id == made.score_id and (gained.on_missing, gained.schema_version) == ("default", 2) and gained.defaults == (("logp", 3.5),)
    assert scores.store.get(made.score_id) is gained and events[-1].score_ids == (made.score_id,)
    lost = scores.update(made.score_id, defaults=[])
    assert (lost.on_missing, lost.schema_version, lost.defaults) == ("refuse", 1, ()) and lost.digest == made.digest, "no defaults is the definition it was before"


def test_an_edit_that_leaves_a_default_for_an_input_it_removed_is_refused(scores):
    made = _make(scores, defaults=[("logp", 2.0)])
    with pytest.raises(FormulaError, match="not one of the inputs"):
        scores.update(made.score_id, formula="ramp(psa, 140, 60)", inputs=[("psa", _PSA)])
    assert scores.store.get(made.score_id) is made


def test_the_policy_cannot_be_edited_apart_from_the_defaults(scores):
    made = _make(scores)
    with pytest.raises(ValueError, match="cannot be changed.*follows the defaults"):
        scores.update(made.score_id, on_missing="default")


def test_a_default_stands_in_for_a_calculator_nobody_ran_and_the_value_says_so(scores, services, project):
    model = project.molecules[0]
    _make(scores, defaults=[("logp", 3.5)])
    _put(services, model, "tpsa", 100.0, "Å²")
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(0.25)
    assert [item.name for item in value.defaulted] == ["logp"] and {i.name: i.state for i in value.inputs}["psa"] is InputState.READ
    (answer,) = scores.answers_for(model.uuid, 1)
    assert "default used for logp" in answer.facts[0].display_value


def test_a_preview_of_a_draft_with_defaults_is_the_value_a_saved_one_has(scores, services, project):
    from openchem.domain.score_definition import ScoreDefinition

    model = project.molecules[0]
    _put(services, model, "tpsa", 100.0, "Å²")
    draft = ScoreDefinition("user.draft", "Draft", "ramp(psa, 140, 60) * ramp(logp, 5, 2)", "1", (("psa", _PSA), ("logp", _LOGP)), schema_version=2, on_missing="default", defaults=(("logp", 3.5),))
    value = scores.preview(draft, model)
    assert value.status is ScoreStatus.VALUE and value.defaulted[0].name == "logp" and len(scores.store) == 0


# --- through the application's own path -----------------------------------------------------------------------------------------------


def test_a_score_reads_what_the_real_always_on_descriptors_recorded(scores, services, project, qapp):
    from PySide6.QtCore import QThreadPool

    model = project.molecules[0]
    _make(scores)
    services.descriptor_service.request_descriptors(model, DRAWING)
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(50):
        qapp.processEvents()
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.VALUE, value.reason
    by_name = {item.name: item for item in value.inputs}
    assert by_name["psa"].value == pytest.approx(63.6, abs=0.1) and by_name["logp"].value == pytest.approx(1.31, abs=0.01)
    assert by_name["psa"].carried_as == "Å²" and by_name["psa"].result_id == "descriptor:rdkit:tpsa"
    assert 0.0 <= value.value <= 1.0


# --- the reader entries ------------------------------------------------------------------------------------------------------------------


def test_the_reader_entries_are_stamped_with_the_molecule_and_the_version_they_were_asked_for(scores, services, project):
    model = project.molecules[0]
    _make(scores)
    _put(services, model, "tpsa", 100.0, "\u00c5\u00b2")
    _put(services, model, "mol_logp", 3.5)
    (answer,) = scores.answers_for(model.uuid, 9)
    assert answer.molecule_uuid == model.uuid and answer.structure_version == 9 and answer.score_id == "user.my_blend"
    assert answer.facts[0].value == pytest.approx(0.25)


def test_a_molecule_the_project_does_not_have_has_no_reader_entries(scores):
    _make(scores)
    assert scores.answers_for("not-in-this-project", 0) == ()


def test_with_no_project_there_are_no_reader_entries(services):
    service = ScoreService(services.event_bus, services.result_store_service, services.calculator_registry)
    assert service.answers_for("anything", 0) == ()


# --- a draft's preview ---------------------------------------------------------------------------------------------------------------


def test_a_preview_is_the_value_a_saved_score_would_have_and_stores_nothing(scores, services, project, events):
    from openchem.domain.score_definition import ScoreDefinition

    model = project.molecules[0]
    _put(services, model, "tpsa", 100.0, "\u00c5\u00b2")
    draft = ScoreDefinition("user.draft", "Draft", "ramp(psa, 140, 60)", "1", (("psa", _PSA),))
    value = scores.preview(draft, model)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(0.5)
    assert len(scores.store) == 0 and events == []
    saved = _make(scores, label="Same thing", formula="ramp(psa, 140, 60)", inputs=[("psa", _PSA)])
    assert scores.values_for(model)[0].value == value.value and saved.digest == draft.digest


def test_a_preview_refuses_in_the_same_words_a_saved_score_does(scores, project):
    from openchem.domain.score_definition import ScoreDefinition

    draft = ScoreDefinition("user.draft", "Draft", "ramp(psa, 140, 60)", "1", (("psa", _PSA),))
    value = scores.preview(draft, project.molecules[0])
    assert value.status is ScoreStatus.REFUSED and "has not been calculated for this molecule" in value.reason


def test_a_preview_of_a_definition_that_does_not_check_is_a_refusal_not_an_exception(scores, project):
    from openchem.domain.score_definition import ScoreDefinition

    draft = ScoreDefinition("user.draft", "Draft", "ramp(psa, 140", "1", (("psa", _PSA),))
    value = scores.preview(draft, project.molecules[0])
    assert value.status is ScoreStatus.REFUSED and "no longer checks" in value.reason


# --- an edit stores the shapes `create` stores (found by the project table's drive) ---------------------------------------------------------------


def test_an_edit_given_lists_stores_tuples_so_the_definition_is_hashable_and_equal_to_one_read_back(scores):
    made = _make(scores)
    changed = scores.update(
        made.score_id, inputs=[("psa", _PSA)], constants=[Constant("hi", 140.0, "Å^2")], formula="ramp(psa, hi, 60)"
    )
    assert changed.inputs == (("psa", _PSA),) and isinstance(changed.inputs, tuple) and isinstance(changed.inputs[0], tuple)
    assert changed.constants == (Constant("hi", 140.0, "Å^2"),) and isinstance(changed.constants, tuple)
    assert hash(changed) == hash(scores.store.get(made.score_id)), "a definition is a dict key, as the parsed-formula cache uses it"


def test_an_edit_given_lists_can_still_be_read_for_a_molecule(scores, services, project):
    model = project.molecules[0]
    _put(services, model, "tpsa", 100.0, "Å²")
    made = _make(scores)
    scores.update(made.score_id, inputs=[("psa", _PSA)], constants=[], formula="ramp(psa, 140, 60)")
    (value,) = scores.values_for(model)
    assert value.status is ScoreStatus.VALUE and value.value == pytest.approx(0.5)
