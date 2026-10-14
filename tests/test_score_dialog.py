"""The Derived Scores window: what it shows while a person types, and what each button does (`docs/DERIVED_SCORES_DESIGN.md` section 11, slice 3d).

A real `ScoreService` over a real project, behind the same `ScoreHost` the main window builds, so every message is the rules' own and every preview is read from
results the application's recording would have stored. Nothing here starts a calculation: the window cannot.
"""

from __future__ import annotations

import datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.score_constants import MAX_CONSTANTS
from openchem.domain.score_definition import DISPLAY_SUFFIX, MAX_OWNER
from openchem.domain.score_definition_store import ENVELOPE_VERSION, ScoreDefinitionStore
from openchem.domain.score_editor import SHOWN_AS, ConstantRow, Draft, InputRow
from openchem.domain.score_formula import MAX_INPUTS
from openchem.domain.score_outputs import APPROVED
from openchem.services.score_service import ScoreService
from openchem.ui.dialogs.score_dialog import _BAD_COLOUR, _OK_COLOUR, ScoreDialog, ScoreHost

_PSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"
_BLEND = Draft(
    label="Blend", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1",
    inputs=(InputRow("psa", _PSA), InputRow("logp", _LOGP)),
)


class World:
    """The host side: a real service over a real project, and the molecule the window is looking at."""

    def __init__(self):
        self.services = build_service_container()
        self.project = ProjectModel(name="Scores")
        self.aspirin = MoleculeModel(display_name="Aspirin")
        self.services.chemistry_engine.set_structure_from_smiles(self.aspirin, "CC(=O)Oc1ccccc1C(=O)O")
        self.project.molecules.append(self.aspirin)
        self.services.result_store_service.set_project(self.project)
        self.service = ScoreService(
            self.services.event_bus, self.services.result_store_service, self.services.calculator_registry, today=lambda: datetime.date(2026, 10, 14)
        )
        self.service.set_project(self.project)
        self.has_project = True
        self.selected: MoleculeModel | None = self.aspirin

    def put(self, descriptor_id, value, units=""):
        model = self.aspirin
        fingerprint = self.services.result_store_service.fingerprints_for(model)[DRAWING]
        result = DescriptorValue(descriptor_id, descriptor_id, units, "c", "rdkit", model.uuid, value=value, cache_state=CacheState.COMPLETED)
        identity = ResultIdentity(model.uuid, f"descriptor:rdkit:{descriptor_id}", DRAWING, fingerprint, "rdkit")
        self.services.result_store_service.store.put(StoredResult(identity, result))

    def host(self) -> ScoreHost:
        def preview(definition, uuid):
            found = self.project.find_molecule(uuid)
            return self.service.preview(definition, found) if found is not None else None

        return ScoreHost(
            has_project=lambda: self.has_project,
            scores=lambda: self.service.store.definitions(),
            kept=lambda: self.service.store.kept(),
            reserved_names=self.service.reserved_names,
            molecule=lambda: (self.selected.display_name, self.selected.uuid) if self.selected is not None else None,
            preview=preview,
            create=self.service.create,
            update=self.service.update,
            remove=self.service.remove,
        )


@pytest.fixture
def world():
    return World()


@pytest.fixture
def dialog(qapp, world):
    built = ScoreDialog(world.host())
    yield built
    built.close()
    built.deleteLater()


def _answer(monkeypatch, button):
    asked = []

    def question(parent, title, text, *args, **kwargs):
        asked.append((title, text))
        return button

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


# --- before there is anything --------------------------------------------------------------------------------------------------------------


def test_without_a_project_the_window_says_so_and_offers_nothing(qapp, world):
    world.has_project = False
    shown = ScoreDialog(world.host())
    snap = shown.snapshot()
    assert not shown._empty.isHidden() and "project" in shown._empty.text()
    assert not snap["save_enabled"] and not snap["delete_enabled"]
    assert not shown._new.isEnabled() and not shown._add_input.isEnabled() and not shown._add_constant.isEnabled()
    shown.close()


def test_an_empty_form_asks_for_the_three_things_and_cannot_be_saved(dialog):
    snap = dialog.snapshot()
    assert "name" in snap["message"] and "formula" in snap["message"] and snap["where"] == ""
    assert not snap["save_enabled"] and not snap["ok"]


def test_the_label_is_shown_as_it_will_be_read_everywhere(dialog):
    dialog._label.setText("My blend")
    assert dialog.snapshot()["shown_as"].endswith(f"My blend {DISPLAY_SUFFIX}")
    dialog._label.setText("")
    assert "(no name yet)" in dialog.snapshot()["shown_as"] and DISPLAY_SUFFIX in dialog.snapshot()["shown_as"]


# --- what it says while a person types ---------------------------------------------------------------------------------------------


def test_a_draft_that_checks_says_what_unit_the_formula_works_out_to_and_can_be_saved(dialog):
    dialog.set_draft(_BLEND)
    snap = dialog.snapshot()
    assert snap["ok"] and snap["works_out"] == "1" and "The formula checks" in snap["message"] and snap["save_enabled"]
    assert dialog._works_out.text() == "The formula works out to 1."


def test_a_syntax_error_names_the_formula_and_points_at_the_place(dialog):
    dialog.set_draft(Draft(label="Blend", formula="ramp(psa, 140, 60) *", inputs=(InputRow("psa", _PSA),)))
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "formula" and snap["message"].startswith("Formula:")
    assert snap["position"] is not None and snap["caret"] == snap["position"]
    excerpt, caret_line = snap["pointer"].split("\n")
    assert excerpt == "ramp(psa, 140, 60) *" and caret_line == " " * snap["position"] + "^"
    assert not dialog._pointer.isHidden()
    assert not snap["save_enabled"]
    assert "border" in dialog._formula.styleSheet() and dialog._label.styleSheet() == ""


def test_a_unit_clash_in_the_formula_marks_the_formula_and_points_at_it(dialog):
    dialog.set_draft(Draft(label="Blend", formula="psa + logp", result_unit="1", inputs=(InputRow("psa", _PSA), InputRow("logp", _LOGP))))
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "formula" and snap["problem"] == "unit"
    assert snap["caret"] is not None and "border" in dialog._formula.styleSheet() and dialog._unit.styleSheet() == ""


def test_a_unit_that_is_not_what_the_formula_works_out_to_is_refused_in_the_unit_field(dialog):
    dialog.set_draft(Draft(label="Blend", formula="psa", result_unit="g/mol", inputs=(InputRow("psa", _PSA),)))
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "unit" and snap["works_out"] != "" and snap["works_out"] != "g/mol"
    assert "border" in dialog._unit.styleSheet()


def test_a_constant_typed_half_way_is_a_problem_of_the_constants_not_the_formula(dialog):
    dialog.set_draft(
        Draft(label="Blend", formula="ramp(psa, lo, hi)", inputs=(InputRow("psa", _PSA),),
              constants=(ConstantRow("lo", "60", "Å^2"), ConstantRow("hi", "14", "Å^2x")))
    )
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "constants" and snap["message"].startswith("Constants:")
    assert "border" in dialog._constants_host.styleSheet() and dialog._formula.styleSheet() == ""


def test_a_constant_with_its_own_unit_is_checked_strictly(dialog):
    base = dict(label="Blend", formula="ramp(psa, lo, hi)", inputs=(InputRow("psa", _PSA),))
    dialog.set_draft(Draft(**base, constants=(ConstantRow("lo", "60", "Å^2"), ConstantRow("hi", "140", "Å^2"))))
    assert dialog.snapshot()["ok"]
    dialog.set_draft(Draft(**base, constants=(ConstantRow("lo", "60", "Å^2"), ConstantRow("hi", "140", "nm^2"))))
    assert not dialog.snapshot()["ok"]


def test_a_bare_number_takes_the_unit_of_what_it_is_compared_with(dialog):
    dialog.set_draft(Draft(label="Blend", formula="ramp(psa, 140, 60)", inputs=(InputRow("psa", _PSA),)))
    assert dialog.snapshot()["ok"]


def test_two_inputs_that_estimate_one_quantity_are_refused_in_the_inputs(dialog):
    by_endpoint: dict[str, list[str]] = {}
    for entry in APPROVED:
        by_endpoint.setdefault(entry.endpoint, []).append(entry.output_id)
    pair = next(ids for ids in by_endpoint.values() if len(ids) >= 2)
    dialog.set_draft(Draft(label="Blend", formula="a + b", inputs=(InputRow("a", pair[0]), InputRow("b", pair[1]))))
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "inputs" and "border" in dialog._inputs_host.styleSheet()


def test_a_label_close_to_a_calculators_name_is_refused_in_the_name(dialog):
    dialog.set_draft(Draft(_BLEND.label, _BLEND.formula, _BLEND.result_unit, _BLEND.inputs))
    assert dialog.snapshot()["ok"]
    dialog._label.setText("Dipole moment")
    snap = dialog.snapshot()
    assert not snap["ok"] and snap["where"] == "label" and snap["message"].startswith("Name:") and "too close" in snap["message"]
    assert not snap["save_enabled"]


def test_typing_in_a_field_checks_again_at_once(dialog):
    dialog.set_draft(_BLEND)
    assert dialog.snapshot()["ok"]
    dialog._formula.setText("ramp(psa, 140, 60) * ramp(logp, 5, 2) *")
    assert not dialog.snapshot()["ok"]
    dialog._formula.setText("ramp(psa, 140, 60) * ramp(logp, 5, 2)")
    assert dialog.snapshot()["ok"]


def test_removing_an_input_the_formula_uses_says_so(dialog):
    dialog.set_draft(_BLEND)
    dialog._input_rows[1].remove_button.click()
    snap = dialog.snapshot()
    assert not snap["ok"] and len(dialog.draft().inputs) == 1 and "logp" in snap["message"]


# --- the rows ---------------------------------------------------------------------------------------------------------------------------


def test_adding_inputs_suggests_names_that_do_not_collide(dialog):
    dialog._add_input.click()
    dialog._add_input.click()
    names = [row.name for row in dialog.draft().inputs]
    assert len(names) == 2 and len(set(names)) == 2 and all(names)


def test_a_score_reads_at_most_the_limit_of_inputs(dialog):
    for _ in range(MAX_INPUTS + 3):
        dialog._add_input.click()
    assert len(dialog.draft().inputs) == MAX_INPUTS
    assert str(MAX_INPUTS) in dialog._message.text()


def test_an_output_that_is_no_longer_approved_is_shown_as_it_is_and_refused(dialog):
    dialog.set_draft(Draft(label="Blend", formula="x", inputs=(InputRow("x", "descriptor:not_an_output"),)))
    assert dialog.draft().inputs[0].output_id == "descriptor:not_an_output"
    assert "(not approved)" in dialog._input_rows[0].output.currentText()
    assert not dialog.snapshot()["ok"] and dialog.snapshot()["where"] == "inputs"


# --- saving ------------------------------------------------------------------------------------------------------------------------------


def test_save_makes_the_score_lists_it_and_leaves_the_form_clean(dialog, world):
    dialog.set_draft(_BLEND)
    made = dialog.save()
    assert made is not None and made.score_id == "user.blend"
    assert world.service.store.get("user.blend") is made
    snap = dialog.snapshot()
    assert snap["scores"] == [f"Blend {DISPLAY_SUFFIX}"] and snap["current"] == "user.blend"
    assert not snap["dirty"] and not snap["save_enabled"] and snap["delete_enabled"]


def test_save_on_a_draft_that_does_not_check_stores_nothing(dialog, world):
    dialog.set_draft(Draft(label="Blend", formula="ramp(psa, 140", inputs=(InputRow("psa", _PSA),)))
    assert dialog.save() is None
    assert len(world.service.store) == 0


def test_the_save_button_is_what_saves(dialog, world):
    dialog.set_draft(_BLEND)
    assert dialog._save.isEnabled()
    dialog._save.click()
    assert len(world.service.store) == 1


def test_editing_a_saved_score_and_saving_keeps_its_id(dialog, world):
    dialog.set_draft(_BLEND)
    first = dialog.save()
    assert first is not None
    dialog._formula.setText("ramp(psa, 140, 60) + ramp(logp, 5, 2)")
    assert dialog.snapshot()["dirty"] and dialog._save.isEnabled() and dialog._revert.isEnabled()
    second = dialog.save()
    assert second.score_id == first.score_id and len(world.service.store) == 1
    assert world.service.store.get(first.score_id).formula == "ramp(psa, 140, 60) + ramp(logp, 5, 2)"
    assert not dialog.snapshot()["dirty"]


def test_revert_puts_the_saved_score_back(dialog):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog._formula.setText("psa")
    dialog._label.setText("Something else")
    dialog._revert.click()
    assert dialog.draft() == Draft.from_definition(dialog._host.scores()[0]) and not dialog.snapshot()["dirty"]


def test_a_refusal_from_the_service_is_shown_and_the_form_keeps_what_was_typed(dialog, world):
    dialog.set_draft(_BLEND)

    def refuse(**_fields):
        raise ValueError("this project already has 100 scores")

    dialog._host.create = refuse
    assert dialog.save() is None
    assert "100 scores" in dialog._message.text() and dialog.draft().label == "Blend"


# --- moving between scores --------------------------------------------------------------------------------------------------------------


def _two_scores(dialog):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog.start_new()
    dialog.set_draft(Draft(label="Weight", formula="mw / one", inputs=(InputRow("mw", "descriptor:mol_wt"),),
                           constants=(ConstantRow("one", "1", "g/mol"),)))
    dialog.save()


def test_choosing_another_score_loads_it(dialog):
    _two_scores(dialog)
    assert dialog.current_score_id() == "user.weight"
    dialog._list.setCurrentRow(0)
    assert dialog.current_score_id() == "user.blend" and dialog.draft().label == "Blend" and not dialog.snapshot()["dirty"]


def test_choosing_another_score_with_unsaved_changes_asks_and_no_keeps_them(dialog, monkeypatch):
    _two_scores(dialog)
    dialog._formula.setText("mw")
    asked = _answer(monkeypatch, QMessageBox.StandardButton.No)
    dialog._list.setCurrentRow(0)
    assert len(asked) == 1 and dialog.current_score_id() == "user.weight" and dialog.draft().formula == "mw"
    assert dialog._list.currentRow() == 1


def test_choosing_another_score_with_unsaved_changes_and_yes_discards_them(dialog, monkeypatch):
    _two_scores(dialog)
    dialog._formula.setText("mw")
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog._list.setCurrentRow(0)
    assert dialog.current_score_id() == "user.blend" and dialog.draft().label == "Blend"


def test_new_score_with_unsaved_changes_asks_first(dialog, monkeypatch):
    _two_scores(dialog)
    dialog._formula.setText("mw")
    asked = _answer(monkeypatch, QMessageBox.StandardButton.No)
    dialog._new.click()
    assert len(asked) == 1 and dialog.current_score_id() == "user.weight"
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog._new.click()
    assert dialog.current_score_id() is None and dialog.draft().is_blank


def test_a_blank_new_form_is_never_asked_about(dialog, monkeypatch):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog.start_new()
    asked = _answer(monkeypatch, QMessageBox.StandardButton.No)
    dialog._list.setCurrentRow(0)
    assert asked == [] and dialog.current_score_id() == "user.blend"


# --- deleting -----------------------------------------------------------------------------------------------------------------------------


def test_delete_asks_and_no_keeps_the_score(dialog, world, monkeypatch):
    dialog.set_draft(_BLEND)
    dialog.save()
    asked = _answer(monkeypatch, QMessageBox.StandardButton.No)
    dialog._delete.click()
    assert len(asked) == 1 and len(world.service.store) == 1 and dialog.current_score_id() == "user.blend"


def test_delete_with_yes_removes_the_definition_and_empties_the_form(dialog, world, monkeypatch):
    dialog.set_draft(_BLEND)
    dialog.save()
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog._delete.click()
    assert len(world.service.store) == 0 and dialog.snapshot()["scores"] == [] and dialog.current_score_id() is None and dialog.draft().is_blank


def test_delete_is_off_for_a_score_that_is_not_saved_yet(dialog):
    dialog.set_draft(_BLEND)
    assert not dialog._delete.isEnabled()


# --- entries this build cannot use -----------------------------------------------------------------------------------------------------


def test_an_entry_this_build_cannot_use_is_listed_with_the_reason_and_cannot_be_chosen(dialog, world):
    block = {
        "version": ENVELOPE_VERSION,
        "definitions": [{"score_id": "user.future", "label": "From the future", "schema_version": 999}, "garbage"],
    }
    world.service.set_project(world.project, ScoreDefinitionStore.from_dict(block, world.project.uuid))
    assert len(world.service.store.kept()) == 2
    dialog.refresh()
    texts = dialog.snapshot()["scores"]
    assert len(texts) == 2
    assert texts[0].startswith("From the future: ") and texts[1].startswith("An entry: ")
    for row in range(dialog._list.count()):
        item = dialog._list.item(row)
        assert not item.flags() & Qt.ItemFlag.ItemIsSelectable and not item.flags() & Qt.ItemFlag.ItemIsEnabled
    assert world.service.store.to_dict() == block, "listing them changes nothing about what is written back"


# --- refreshing ---------------------------------------------------------------------------------------------------------------------------


def test_refresh_never_overwrites_what_is_being_typed(dialog, world):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog._formula.setText("ramp(psa, 140, 60) + ramp(logp, 5, 2)")
    world.service.update("user.blend", note="changed elsewhere")
    dialog.refresh()
    assert dialog.draft().formula == "ramp(psa, 140, 60) + ramp(logp, 5, 2)" and dialog.snapshot()["dirty"]


def test_refresh_shows_a_change_made_elsewhere_when_the_form_is_clean(dialog, world):
    dialog.set_draft(_BLEND)
    dialog.save()
    world.service.update("user.blend", note="changed elsewhere")
    dialog.refresh()
    assert dialog.draft().note == "changed elsewhere" and not dialog.snapshot()["dirty"]


def test_a_score_removed_elsewhere_while_shown_empties_the_form(dialog, world):
    dialog.set_draft(_BLEND)
    dialog.save()
    world.service.remove("user.blend")
    dialog.refresh()
    assert dialog.current_score_id() is None and dialog.draft().is_blank and dialog.snapshot()["scores"] == []


def test_refresh_preview_leaves_the_form_the_list_and_the_focus_alone(dialog, world):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog._formula.setText("ramp(psa, 140, 60) + ramp(logp, 5, 2)")
    before = (dialog.draft(), dialog.current_score_id(), dialog.snapshot()["scores"])
    dialog.refresh_preview()
    assert (dialog.draft(), dialog.current_score_id(), dialog.snapshot()["scores"]) == before


# --- the preview -------------------------------------------------------------------------------------------------------------------------


def test_a_draft_that_checks_shows_the_value_for_the_selected_molecule(dialog, world):
    world.put("tpsa", 100.0, "Å²")
    world.put("mol_logp", 3.5)
    dialog.set_draft(_BLEND)
    assert dialog.snapshot()["preview"].startswith("For Aspirin: ")
    assert dialog._preview.text() == f"For Aspirin: {0.5 * 0.5:.4g}"


def test_a_score_whose_input_has_not_been_calculated_says_which_instead_of_a_number(dialog):
    dialog.set_draft(_BLEND)
    text = dialog.snapshot()["preview"]
    assert text.startswith("For Aspirin: no value.") and "has not been calculated for this molecule" in text


def test_the_preview_reads_again_when_a_result_arrives(dialog, world):
    dialog.set_draft(_BLEND)
    assert "no value" in dialog.snapshot()["preview"]
    world.put("tpsa", 100.0, "Å²")
    world.put("mol_logp", 3.5)
    dialog.refresh_preview()
    assert dialog.snapshot()["preview"] == f"For Aspirin: {0.25:.4g}"


def test_with_no_molecule_selected_it_says_to_select_one(dialog, world):
    world.selected = None
    dialog.set_draft(_BLEND)
    assert dialog.snapshot()["preview"] == "Select a molecule to see what this score gives for it."


def test_a_draft_that_does_not_check_shows_no_preview(dialog):
    dialog.set_draft(Draft(label="Blend", formula="ramp(psa, 140", inputs=(InputRow("psa", _PSA),)))
    assert dialog.snapshot()["preview"] == ""


def test_a_score_with_a_unit_shows_the_unit_beside_its_value(dialog, world):
    world.put("mol_wt", 180.16, "g/mol")
    dialog.set_draft(Draft(label="Weight", formula="mw", result_unit="g/mol", inputs=(InputRow("mw", "descriptor:mol_wt"),)))
    assert dialog.snapshot()["preview"] == "For Aspirin: 180.2 g/mol"


def test_previewing_stores_nothing_and_starts_nothing(dialog, world):
    before = len(world.service.store)
    dialog.set_draft(_BLEND)
    dialog.refresh_preview()
    assert len(world.service.store) == before == 0


# --- what the mutation run found missing (slice 3d) -----------------------------------------------------------------------------------------


def test_with_a_project_the_no_project_notice_is_not_there(dialog):
    assert dialog._empty.isHidden() and dialog._splitter.isEnabled()


def test_when_the_project_goes_away_nothing_can_be_started_or_changed(dialog, world):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog._formula.setText("ramp(psa, 140, 60) + ramp(logp, 5, 2)")
    snap = dialog.snapshot()
    assert snap["dirty"] and dialog._save.isEnabled() and dialog._revert.isEnabled() and dialog._delete.isEnabled()
    world.has_project = False
    dialog.refresh()
    assert not dialog._empty.isHidden() and not dialog._splitter.isEnabled()
    for button in (dialog._save, dialog._revert, dialog._delete, dialog._new, dialog._add_input, dialog._add_constant):
        assert not button.isEnabled(), button.text()


def test_without_a_project_a_result_arriving_reads_nothing(dialog, world):
    asked = []
    real = dialog._host.preview
    dialog._host.preview = lambda definition, uuid: asked.append(uuid) or real(definition, uuid)
    dialog.set_draft(_BLEND)
    asked.clear()
    world.has_project = False
    dialog.refresh_preview()
    assert asked == []
    world.has_project = True
    dialog.refresh_preview()
    assert len(asked) == 1


def test_a_score_reads_at_most_the_limit_of_constants(dialog):
    for _ in range(MAX_CONSTANTS + 3):
        dialog._add_constant.click()
    assert len(dialog.draft().constants) == MAX_CONSTANTS and str(MAX_CONSTANTS) in dialog._message.text()


def test_a_saved_score_emptied_of_everything_is_still_an_unsaved_change(dialog, monkeypatch):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog.set_draft(Draft())
    assert dialog.dirty and dialog.draft().is_blank
    asked = _answer(monkeypatch, QMessageBox.StandardButton.No)
    dialog._new.click()
    assert len(asked) == 1 and dialog.current_score_id() == "user.blend"


def test_choosing_the_score_already_shown_does_not_reload_it(dialog, monkeypatch):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog._formula.setText("ramp(psa, 140, 60) + ramp(logp, 5, 2)")
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    dialog._on_list_changed(dialog._list.currentItem(), None)
    assert asked == [] and dialog.draft().formula == "ramp(psa, 140, 60) + ramp(logp, 5, 2)"


def test_after_a_refresh_the_shown_score_is_still_the_selected_row(dialog):
    _two_scores(dialog)
    dialog._list.setCurrentRow(0)
    dialog.refresh()
    assert dialog._list.currentRow() == 0 and dialog._list.currentItem().text() == "Blend (user-defined, unvalidated)"


def test_a_long_label_elides_in_the_list_instead_of_scrolling_it_sideways(dialog):
    assert dialog._list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    dialog.set_draft(_BLEND)
    dialog.save()
    assert dialog._list.item(0).toolTip() == "Blend (user-defined, unvalidated)"


def test_a_new_form_is_clean_and_has_nothing_to_revert(dialog):
    dialog.set_draft(_BLEND)
    dialog.save()
    dialog.start_new()
    assert not dialog.dirty and not dialog._revert.isEnabled() and dialog.current_score_id() is None


def test_a_service_key_error_is_shown_and_the_form_keeps_what_was_typed(dialog):
    dialog.set_draft(_BLEND)

    def refuse(**_fields):
        raise KeyError("user.gone")

    dialog._host.create = refuse
    assert dialog.save() is None
    assert "user.gone" in dialog._message.text() and dialog.draft().label == "Blend"


def test_the_owner_and_the_note_are_saved_with_the_score(dialog, world):
    dialog.set_draft(Draft(_BLEND.label, _BLEND.formula, _BLEND.result_unit, _BLEND.inputs, owner="Alex", note="the default window"))
    made = dialog.save()
    stored = world.service.store.get(made.score_id)
    assert (stored.owner, stored.note) == ("Alex", "the default window")


def test_the_constants_are_saved_with_the_score(dialog, world):
    dialog.set_draft(
        Draft(label="Blend", formula="ramp(psa, hi, 60)", inputs=(InputRow("psa", _PSA),), constants=(ConstantRow("hi", "140", "Å^2"),))
    )
    made = dialog.save()
    assert [(c.name, c.value, c.unit) for c in world.service.store.get(made.score_id).constants] == [("hi", 140.0, "Å^2")]


def test_saving_a_draft_whose_constant_is_not_a_number_is_a_refusal_not_a_crash(dialog, world):
    dialog.set_draft(
        Draft(label="Blend", formula="ramp(psa, hi, 60)", inputs=(InputRow("psa", _PSA),), constants=(ConstantRow("hi", "abc", "Å^2"),))
    )
    assert dialog.save() is None and len(world.service.store) == 0


def test_removing_a_constant_takes_that_row_out(dialog):
    dialog.set_draft(
        Draft(label="Blend", formula="ramp(psa, lo, hi)", inputs=(InputRow("psa", _PSA),),
              constants=(ConstantRow("lo", "60", "Å^2"), ConstantRow("hi", "140", "Å^2")))
    )
    dialog._constant_rows[0].remove_button.click()
    assert [row.name for row in dialog.draft().constants] == ["hi"]
    assert len(dialog._constant_rows) == 1


def test_the_label_is_shown_as_it_will_be_stored_without_its_spaces(dialog):
    dialog._label.setText("  Polar window  ")
    assert dialog.snapshot()["shown_as"] == f"{SHOWN_AS} Polar window {DISPLAY_SUFFIX}"


def test_a_problem_is_red_and_a_clean_draft_is_green_and_an_empty_form_is_neither(dialog):
    assert dialog._message.styleSheet() == ""
    dialog.set_draft(_BLEND)
    assert _OK_COLOUR in dialog._message.styleSheet()
    dialog._formula.setText("ramp(")
    assert _BAD_COLOUR in dialog._message.styleSheet()


def test_the_caret_row_is_there_only_while_it_points_at_something(dialog):
    assert dialog._pointer.isHidden()
    dialog.set_draft(_BLEND)
    assert dialog._pointer.isHidden()
    dialog._formula.setText("ramp(psa, 140, 60) *")
    assert not dialog._pointer.isHidden()
    dialog._formula.setText("ramp(psa, 140, 60) * ramp(logp, 5, 2)")
    assert dialog._pointer.isHidden()


def test_a_problem_with_the_name_or_the_owner_outlines_that_box(dialog):
    dialog.set_draft(Draft(_BLEND.label, _BLEND.formula, _BLEND.result_unit, _BLEND.inputs))
    dialog._label.setText("Dipole moment")
    assert "border" in dialog._label.styleSheet() and dialog._owner.styleSheet() == ""
    dialog._label.setText("Blend")
    assert dialog._label.styleSheet() == ""
    dialog._owner.setText("o" * (MAX_OWNER + 1))
    assert "border" in dialog._owner.styleSheet() and dialog._label.styleSheet() == ""
