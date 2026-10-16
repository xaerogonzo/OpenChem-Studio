"""The scores a person defined, in the REAL main window's Results reader (`docs/DERIVED_SCORES_DESIGN.md` sections 5 and 8; slice 3b).

A real `MainWindow`, a real project with aspirin and ethanol, and the application's own always-on descriptors computing on selection, so 'current' is produced and
not asserted. Nothing here defines a score through a dialog (that is slice 3d); the service makes it, which is the call the dialog will make.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool, Qt

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import MoleculeChanged, MoleculeSelected

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
LABEL = "Window blend (user-defined, unvalidated)"
SCORE = "score:user.window_blend"


@pytest.fixture
def window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


@pytest.fixture
def pair(window):
    engine = window._services.chemistry_engine
    aspirin, ethanol = MoleculeModel(display_name="Aspirin"), MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(aspirin, ASPIRIN)
    engine.set_structure_from_smiles(ethanol, "CCO")
    project = ProjectModel(name="scores")
    project.molecules.extend([aspirin, ethanol])
    window._set_project(project)
    return aspirin, ethanol


def _drain(qapp):
    QThreadPool.globalInstance().waitForDone(60_000)
    for _ in range(60):
        qapp.processEvents()


def _select(window, qapp, model):
    window._services.event_bus.publish(MoleculeSelected(molecule_uuid=model.uuid))
    _drain(qapp)


def _make(window, **changes):
    arguments = dict(
        label="Window blend", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1",
        inputs=[("psa", "descriptor:tpsa"), ("logp", "descriptor:mol_logp")],
    )
    arguments.update(changes)
    return window._services.score_service.create(**arguments)


def _report(window):
    return window._results_view.merged().report_for(SCORE)


def _entries(window) -> list[str]:
    reader = window._results_view
    return [reader._focus_box.itemText(i) for i in range(reader._focus_box.count())]


# --- it is in Results, labelled, and has the number the real descriptors give --------------------------------------------------------


def test_before_any_score_is_defined_results_has_none(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    assert not any("user-defined" in text for text in _entries(window)) and _report(window) is None


def test_a_defined_score_is_in_results_for_the_selected_molecule_with_its_value(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window)
    _drain(qapp)
    report = _report(window)
    assert report is not None and report.molecule_uuid == aspirin.uuid and LABEL in _entries(window)
    (fact,) = report.facts
    assert fact.label == LABEL and 0.0 < fact.value < 1.0, "TPSA 63.6 and logP 1.31 are inside the ramps: a number strictly between 0 and 1"
    assert fact.value == pytest.approx(window._services.score_service.values_for(aspirin)[0].value)


def test_the_number_is_what_the_formula_gives_for_the_applications_own_descriptors(window, pair, qapp):
    """Computed here by hand from the two descriptors the application stored, so the score is not checked against itself."""
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window)
    _drain(qapp)
    by_id = {s.result.descriptor_id: s.result.value for s in window._services.result_store_service.store.all_results(aspirin.uuid) if hasattr(s.result, "descriptor_id")}
    ramp_psa = min(1.0, max(0.0, (by_id["tpsa"] - 140) / (60 - 140)))
    ramp_logp = min(1.0, max(0.0, (by_id["mol_logp"] - 5) / (2 - 5)))
    assert _report(window).facts[0].value == pytest.approx(ramp_psa * ramp_logp)


def test_a_score_made_while_the_molecule_is_shown_appears_without_reselecting(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    assert _report(window) is None
    _make(window)
    qapp.processEvents()
    assert _report(window) is not None


def test_removing_a_score_takes_it_out_of_the_open_reader(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    made = _make(window)
    _drain(qapp)
    assert _report(window) is not None
    window._services.score_service.remove(made.score_id)
    qapp.processEvents()
    assert _report(window) is None and LABEL not in _entries(window)


def test_editing_a_score_changes_the_shown_number(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    made = _make(window)
    _drain(qapp)
    before = _report(window).facts[0].value
    window._services.score_service.update(made.score_id, formula="ramp(logp, 5, 2)", inputs=(("logp", "descriptor:mol_logp"),), constants=())
    qapp.processEvents()
    after = _report(window).facts[0].value
    assert after != before and after == pytest.approx(min(1.0, max(0.0, (1.31 - 5) / (2 - 5))), abs=0.01)


def test_each_molecule_has_its_own_value(window, pair, qapp):
    aspirin, ethanol = pair
    _make(window)
    _select(window, qapp, aspirin)
    on_aspirin = _report(window).facts[0].value
    _select(window, qapp, ethanol)
    report = _report(window)
    assert report.molecule_uuid == ethanol.uuid and report.facts[0].value != on_aspirin


# --- no number, and why ------------------------------------------------------------------------------------------------------------------


def test_a_score_whose_inputs_have_not_been_calculated_says_so_in_results(window, pair, qapp):
    aspirin, _ = pair
    window._services.descriptor_service.request_descriptors = lambda *args, **kwargs: None
    _make(window)
    _select(window, qapp, aspirin)
    report = _report(window)
    assert report is not None and not report.facts
    assert "psa (descriptor:tpsa)" in report.error and "has not been calculated for this molecule" in report.error
    assert report.error_summary == "no value: an input cannot be read"


def test_a_calculator_finishing_gives_a_score_that_was_waiting_for_it_its_number(window, pair, qapp):
    """Found by driving the real application: the score evaluated when the result's own event reached the reader, before the store had the result, and was never
    told to look again. A result recorded for the molecule shown must make the reader read the scores once more."""
    from openchem.domain.calculator import CalculationRequest

    aspirin, _ = pair
    window._services.descriptor_service.request_descriptors = lambda *args, **kwargs: None
    _make(
        window, label="Needs a calculator", formula="ob", result_unit="%", inputs=[("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)")],
    )
    _select(window, qapp, aspirin)
    waiting = window._results_view.merged().report_for("score:user.needs_a_calculator")
    assert waiting is not None and not waiting.facts and "has not been calculated" in waiting.error

    definition = window._services.calculator_registry.get("oxygen_balance")
    window._services.descriptor_service.run_calculator(
        aspirin,
        CalculationRequest(
            calculator_id="oxygen_balance", molecule_uuid=aspirin.uuid, parameters={p.name: p.default for p in definition.parameters}
        ),
    )
    _drain(qapp)
    done = window._results_view.merged().report_for("score:user.needs_a_calculator")
    assert done.facts and done.facts[0].value == pytest.approx(-79.93, abs=0.05) and done.facts[0].units == "%"


def test_a_burst_of_recorded_results_is_one_refresh_of_the_reader(window, pair, qapp):
    aspirin, _ = pair
    _make(window)
    _select(window, qapp, aspirin)
    panel = window._property_panel
    counted = []
    real = panel._refresh_reader
    panel._refresh_reader = lambda *args, **kwargs: (counted.append(1), real(*args, **kwargs))[1]
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.result_store import ResultIdentity, StoredResult
    from openchem.events.events import ResultRecorded

    fingerprint = window._services.result_store_service.fingerprints_for(aspirin)["drawing"]
    for i in range(30):
        result = DescriptorValue(f"x{i}", f"x{i}", "", "c", "rdkit", aspirin.uuid, value=1.0, cache_state=CacheState.COMPLETED)
        stored = StoredResult(ResultIdentity(aspirin.uuid, f"descriptor:rdkit:x{i}", "drawing", fingerprint, "rdkit"), result)
        window._services.event_bus.publish(ResultRecorded(stored=stored))
    counted.clear()
    qapp.processEvents()
    assert len(counted) <= 1


def test_editing_the_structure_makes_the_score_refuse_and_say_why(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window)
    _drain(qapp)
    assert _report(window).facts, "a number first"
    window._services.chemistry_engine.set_structure_from_smiles(aspirin, "CCO")
    window._services.event_bus.publish(MoleculeChanged(molecule_uuid=aspirin.uuid, during_edit=False))
    window._property_panel._request_substance_perception = lambda: None
    qapp.processEvents()
    report = _report(window)
    assert report is not None and not report.facts
    assert "earlier structure" in report.error or "has not been calculated" in report.error


# --- it is a projection: never stored, never a calculator -----------------------------------------------------------------------------------


def test_a_score_is_not_a_stored_result(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window)
    _drain(qapp)
    stored_ids = {s.identity.result_id for s in window._services.result_store_service.store.all_results(aspirin.uuid)}
    assert stored_ids and SCORE not in stored_ids and not any(i.startswith(("score:", "user.")) for i in stored_ids)


def test_a_score_is_not_a_registered_calculator(window, pair):
    _make(window)
    ids = {d.calculator_id for d in window._services.calculator_registry.definitions()}
    assert not any(i.startswith(("user.", "score:")) for i in ids)
    assert not any(d.display_name.endswith("(user-defined, unvalidated)") for d in window._services.calculator_registry.definitions())


def test_a_reader_that_cannot_read_the_scores_still_shows_everything_else(window, pair, qapp, caplog):
    aspirin, _ = pair

    def broken(*_args):
        raise RuntimeError("unreadable")

    window._property_panel.attach_score_answers(broken)
    _select(window, qapp, aspirin)
    assert _entries(window) != [] and "Could not read the scores for" in caplog.text


# --- the Derived Scores window (slice 3d) -----------------------------------------------------------------------------------------------------


_KEEP_ALIVE: list = []


def _tools_actions(window) -> dict[str, object]:
    [tools] = [a for a in window.menuBar().actions() if a.text().replace("&", "") == "Tools"]
    # PySide deletes the menu when the wrapper of the menu-bar action that owns it is collected, and a temporary menu takes its actions' wrappers with it.
    menu = tools.menu()
    _KEEP_ALIVE.extend([tools, menu])
    found = {a.text().replace("&", ""): a for a in menu.actions() if not a.isSeparator()}
    _KEEP_ALIVE.extend(found.values())
    return found


def test_the_tools_menu_has_the_derived_scores_entry_and_it_opens_one_window(window, pair, qapp):
    action = _tools_actions(window)["Derived Scores..."]
    action.trigger()
    first = window._score_dialog
    assert first is not None and first.isVisible()
    action.trigger()
    assert window._score_dialog is first, "there is never a second window"
    first.close()


def test_the_window_makes_a_score_that_reaches_results_and_marks_the_project_unsaved(window, pair, qapp):
    from openchem.domain.score_editor import Draft, InputRow

    aspirin, _ = pair
    _select(window, qapp, aspirin)
    window._session.mark_clean()
    dialog = window.show_scores()
    dialog.set_draft(
        Draft(label="Window blend", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", inputs=(InputRow("psa", "descriptor:tpsa"), InputRow("logp", "descriptor:mol_logp")))
    )
    assert dialog.save() is not None
    _drain(qapp)
    assert window._session.is_dirty, "a score is project data: closing without saving must ask"
    report = _report(window)
    assert report is not None and report.facts and 0.0 < report.facts[0].value < 1.0
    dialog.close()


def test_the_open_window_follows_a_score_made_elsewhere_and_a_project_change(window, pair, qapp):
    dialog = window.show_scores()
    assert dialog.snapshot()["scores"] == []
    _make(window)
    qapp.processEvents()
    assert dialog.snapshot()["scores"] == [LABEL]
    window._set_project(ProjectModel(name="another"))
    qapp.processEvents()
    assert dialog.snapshot()["scores"] == [] and dialog.current_score_id() is None
    dialog.close()


def test_the_open_window_reads_its_preview_again_when_the_molecule_or_a_result_changes(window, pair, qapp):
    from openchem.domain.score_editor import Draft, InputRow

    aspirin, ethanol = pair
    window._services.descriptor_service.request_descriptors = lambda *args, **kwargs: None
    _select(window, qapp, aspirin)
    dialog = window.show_scores()
    dialog.set_draft(Draft(label="Weight", formula="mw", result_unit="g/mol", inputs=(InputRow("mw", "descriptor:mol_wt"),)))
    assert "no value" in dialog.snapshot()["preview"] and "Aspirin" in dialog.snapshot()["preview"]
    _select(window, qapp, ethanol)
    assert "Ethanol" in dialog.snapshot()["preview"], "the preview follows the molecule selected in the project"
    _select(window, qapp, aspirin)

    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.result_store import ResultIdentity, StoredResult
    from openchem.events.events import ResultRecorded

    fingerprint = window._services.result_store_service.fingerprints_for(aspirin)["drawing"]
    result = DescriptorValue("mol_wt", "mol_wt", "g/mol", "c", "rdkit", aspirin.uuid, value=180.16, cache_state=CacheState.COMPLETED)
    stored = StoredResult(ResultIdentity(aspirin.uuid, "descriptor:rdkit:mol_wt", "drawing", fingerprint, "rdkit"), result)
    window._services.result_store_service.store.put(stored)
    window._services.event_bus.publish(ResultRecorded(stored=stored))
    qapp.processEvents()
    assert dialog.snapshot()["preview"] == "For Aspirin: 180.2 g/mol", "a result arriving while the window is open gives the preview its number"
    dialog.close()


def test_a_closed_window_is_not_refreshed_or_reopened_by_events(window, pair, qapp):
    dialog = window.show_scores()
    dialog.close()
    calls = []
    real = dialog.refresh
    dialog.refresh = lambda: (calls.append(1), real())[1]
    _make(window)
    qapp.processEvents()
    assert calls == [] and dialog.isHidden()


def test_the_window_has_no_way_to_start_a_calculation(window, pair, qapp):
    """Reading `descriptor_service` is not enough: the window is built from a host that holds no service, so this checks that typing and saving ask for nothing."""
    from openchem.domain.score_editor import Draft, InputRow

    aspirin, _ = pair
    asked = []
    window._services.descriptor_service.request_descriptors = lambda *args, **kwargs: asked.append("descriptors")
    window._services.descriptor_service.run_calculator = lambda *args, **kwargs: asked.append("calculator")
    _select(window, qapp, aspirin)
    asked.clear()
    dialog = window.show_scores()
    dialog.set_draft(Draft(label="Weight", formula="mw", result_unit="g/mol", inputs=(InputRow("mw", "descriptor:mol_wt"),)))
    dialog._formula.setText("mw + mw")
    dialog.refresh_preview()
    assert asked == []
    dialog.close()


def test_a_saved_score_stays_clean_while_results_arrive_and_choosing_another_does_not_ask(window, pair, qapp, monkeypatch):
    """Found by driving: Delete on another score asked 'discard unsaved changes?' about a form nobody had touched, after a calculator finished."""
    from PySide6.QtWidgets import QMessageBox

    from openchem.domain.calculator import CalculationRequest
    from openchem.domain.score_editor import Draft, InputRow

    aspirin, _ = pair
    _select(window, qapp, aspirin)
    dialog = window.show_scores()
    dialog.set_draft(Draft(label="Polar window", formula="ramp(psa, 140, 60)", inputs=(InputRow("psa", "descriptor:tpsa"),)))
    dialog.save()
    dialog.start_new()
    dialog.set_draft(Draft(label="Needs a calculator", formula="ob", result_unit="%", inputs=(InputRow("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)"),)))
    dialog.save()
    assert not dialog.dirty
    definition = window._services.calculator_registry.get("oxygen_balance")
    window._services.descriptor_service.run_calculator(
        aspirin, CalculationRequest(calculator_id="oxygen_balance", molecule_uuid=aspirin.uuid, parameters={p.name: p.default for p in definition.parameters})
    )
    _drain(qapp)
    assert dialog.snapshot()["preview"].startswith("For Aspirin: -79.9")
    assert not dialog.dirty, (dialog.draft(), dialog._saved)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[1]) or QMessageBox.StandardButton.Yes))
    window.show_scores()
    dialog._list.setCurrentRow(0)
    assert asked == [] and dialog.current_score_id() == "user.polar_window"
    dialog.close()


# --- what the mutation run found missing (slice 3d) -----------------------------------------------------------------------------------------


def test_a_person_asking_for_the_scores_window_gets_it_raised_and_focused(window, qapp, monkeypatch):
    from openchem.ui.dialogs.score_dialog import ScoreDialog

    calls = []
    monkeypatch.setattr(ScoreDialog, "activateWindow", lambda self: calls.append("activate"))
    monkeypatch.setattr(ScoreDialog, "raise_", lambda self: calls.append("raise"))
    dialog = window.show_scores()
    assert calls == ["raise", "activate"] and dialog.isVisible()
    assert not dialog.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    dialog.close()


def test_a_driven_run_shows_the_scores_window_without_taking_the_keyboard(window, qapp, monkeypatch):
    """A script that opens the window on a timer must not take the keyboard from whatever a person is typing in: their next keys would land in the Name field."""
    from openchem.ui.dialogs.score_dialog import ScoreDialog

    calls = []
    monkeypatch.setattr(ScoreDialog, "activateWindow", lambda self: calls.append("activate"))
    monkeypatch.setattr(ScoreDialog, "raise_", lambda self: calls.append("raise"))
    dialog = window.show_scores(activate=False)
    assert calls == [] and dialog.isVisible() and dialog.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert window.show_scores(activate=False) is dialog and calls == [], "opened again it is still not activated"
    dialog.close()


def test_a_window_closed_while_scores_changed_shows_them_when_it_is_opened_again(window, pair, qapp):
    dialog = window.show_scores()
    dialog.close()
    _make(window)
    qapp.processEvents()
    assert dialog.snapshot()["scores"] == [], "a closed window is not refreshed, which is what makes opening it a re-read"
    assert window.show_scores() is dialog and dialog.snapshot()["scores"] == [LABEL]
    dialog.close()


def test_the_window_says_there_is_no_project_when_the_score_service_has_none(window, pair):
    host = window._score_host()
    assert host.has_project()
    window._services.score_service.set_project(None)
    assert not host.has_project()


def test_a_molecule_the_project_does_not_have_is_not_previewed(window, pair):
    from openchem.domain.score_editor import Draft, InputRow

    definition = Draft(label="Polar", formula="psa", result_unit="Å^2", inputs=(InputRow("psa", "descriptor:tpsa"),)).to_definition()
    host = window._score_host()
    assert host.preview(definition, "no-such-molecule") is None
    assert host.preview(definition, pair[0].uuid) is not None


def test_the_window_lists_what_this_build_cannot_use_and_knows_the_calculators_names(window, pair):
    from openchem.domain.score_definition_store import ENVELOPE_VERSION, ScoreDefinitionStore

    block = {"version": ENVELOPE_VERSION, "definitions": [{"score_id": "user.future", "label": "From later", "schema_version": 999}]}
    service = window._services.score_service
    service.set_project(window._session.project, ScoreDefinitionStore.from_dict(block, window._session.project.uuid))
    host = window._score_host()
    assert [entry.label for entry in host.kept()] == ["From later"]
    assert "dipole_moment" in host.reserved_names()
    dialog = window.show_scores()
    assert dialog.snapshot()["scores"][0].startswith("From later: ")
    dialog.close()


def test_a_name_close_to_a_calculators_is_refused_in_the_window(window, pair):
    from openchem.domain.score_editor import Draft, InputRow

    dialog = window.show_scores()
    dialog.set_draft(Draft(label="Dipole moment", formula="psa", result_unit="Å^2", inputs=(InputRow("psa", "descriptor:tpsa"),)))
    assert dialog.snapshot()["where"] == "label" and "too close" in dialog.snapshot()["message"]
    dialog.close()


def test_a_closed_window_is_not_asked_to_read_its_preview(window, pair, qapp):
    dialog = window.show_scores()
    dialog.close()
    calls = []
    real = dialog.refresh_preview
    dialog.refresh_preview = lambda: (calls.append(1), real())[1]
    window._services.event_bus.publish(MoleculeSelected(molecule_uuid=pair[1].uuid))
    qapp.processEvents()
    assert calls == []
    dialog.show()
    window._services.event_bus.publish(MoleculeChanged(molecule_uuid=pair[1].uuid, during_edit=False))
    assert calls, "an open window is"
    dialog.close()


def test_the_window_reads_its_preview_again_for_each_of_the_three_events(window):
    """Each event is its own subscription: selecting a molecule publishes more than one, so the behaviour of a selection cannot show that one is missing."""
    from openchem.events.events import ResultRecorded

    bus = window._services.event_bus
    handler = window._refresh_scores_preview
    for event_type in (MoleculeSelected, MoleculeChanged, ResultRecorded):
        assert any(entry.matches(handler) for entry in bus._handlers[event_type]), event_type.__name__


# --- the project table's score column (slice 3c) ----------------------------------------------------------------------------------------------


def _with_a_conformer(window, qapp, model):
    """A conformer for `model`, and the descriptors asked for on it, as the window does when conformers change (`_on_conformers_changed`)."""
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.domain.calculator import GEOMETRY
    from openchem.domain.conformer import ConformerModel

    engine = window._services.chemistry_engine
    mol, _energy = RDKitConformerProvider().generate_conformers(engine.mol_from_model(model), num_conformers=1, optimize=False)[0]
    model.conformers.append(ConformerModel(molblock=engine.mol_to_molblock(mol), energy=-1.0))
    window._services.descriptor_service.request_descriptors(model, GEOMETRY)
    _drain(qapp)


def _run_batch(window, qapp, molecules, descriptor_ids, calculator_ids):
    from openchem.domain.batch import BatchRequest
    from openchem.services.batch_service import BatchProgress

    events = []
    window._services.event_bus.subscribe(BatchProgress, events.append)
    window._services.batch_service.request_batch(
        BatchRequest(molecule_uuids=[m.uuid for m in molecules], descriptor_ids=list(descriptor_ids), calculator_ids=list(calculator_ids)), molecules
    )
    _drain(qapp)
    assert events and events[-1].table is not None
    return events[-1]


def test_every_approved_output_reads_the_same_in_the_table_as_in_results_for_a_molecule_that_has_a_conformer(window, pair, qapp):
    """The reason the table's own cells are safe to read: before #330 the project run handed a conformer to every descriptor, so seven of these seventeen differed.

    Both sides are the application's own: Results is the stored results the Properties panel made (the conformer's request included), the table is a real batch run over
    the same molecule. Every approved output of both kinds is compared, state and number.
    """
    from openchem.domain.calculator import CalculationRequest
    from openchem.domain.score_outputs import APPROVED
    from openchem.domain.score_table import read_cell_output
    from openchem.domain.score_value import InputState, read_output

    aspirin, ethanol = pair
    _select(window, qapp, aspirin)
    _with_a_conformer(window, qapp, aspirin)
    descriptor_ids = [e.output_id.partition(":")[2] for e in APPROVED if e.output_id.startswith("descriptor:")]
    calculator_ids = sorted({e.output_id.split(":")[1] for e in APPROVED if e.output_id.startswith("calculator:")})
    for calculator_id in calculator_ids:
        definition = window._services.calculator_registry.get(calculator_id)
        window._services.descriptor_service.run_calculator(
            aspirin, CalculationRequest(calculator_id=calculator_id, molecule_uuid=aspirin.uuid, parameters={p.name: p.default for p in definition.parameters})
        )
    _drain(qapp)
    event = _run_batch(window, qapp, [aspirin, ethanol], descriptor_ids, calculator_ids)
    entries = window._services.score_service._classified_results(aspirin)
    assert aspirin.conformers, "the molecule has a conformer, which is the case #330 was about"
    compared = 0
    for output in APPROVED:
        in_results = read_output(output.output_id, entries)
        in_table = read_cell_output(output.output_id, event.table, aspirin.uuid)
        assert (in_table.state, in_table.carried_as) == (in_results.state, in_results.carried_as), output.output_id
        if in_results.state is InputState.READ:
            assert in_table.value == pytest.approx(in_results.value, rel=1e-9), output.output_id
            compared += 1
    assert compared >= len(descriptor_ids), "the sweep compared the descriptors at least, and not nothing"
    sa = read_cell_output("descriptor:sa_score", event.table, aspirin.uuid).value
    assert sa == pytest.approx(1.58, abs=0.05), "the drawing's value, not the conformer's 6.445"


def test_a_score_defined_after_a_project_run_is_a_column_of_the_table_at_once_and_follows_its_edits(window, pair, qapp):
    aspirin, ethanol = pair
    event = _run_batch(window, qapp, [aspirin, ethanol], ["tpsa", "mol_logp"], [])
    view = window._results_workspace.table_view
    window._results_workspace.begin_project_run(type("Plan", (), {"run_id": "run-1"})())
    view.apply_progress(event, adopt=True)
    assert not any(c.source == "score" for c in view.table().columns)

    made = _make(window)
    qapp.processEvents()
    column = next(c for c in view.table().columns if c.source == "score")
    assert column.label == LABEL and column.column_id == f"score:{made.score_id}"
    from openchem.domain.score_table import score_value_in_table

    for molecule in (aspirin, ethanol):
        assert view.table().cell(molecule.uuid, column.column_id).value == pytest.approx(score_value_in_table(made, event.table, molecule.uuid).value)
    window._services.score_service.update(made.score_id, formula="ramp(psa, 100, 60)", inputs=(("psa", "descriptor:tpsa"),), constants=())
    qapp.processEvents()
    assert view.table().cell(aspirin.uuid, column.column_id).value == pytest.approx(0.0, abs=1.0) and view.table().cell(aspirin.uuid, column.column_id).value != view.table().cell(
        ethanol.uuid, column.column_id
    ).value
    window._services.score_service.remove(made.score_id)
    qapp.processEvents()
    assert not any(c.source == "score" for c in view.table().columns)


def test_a_score_the_run_did_not_compute_the_inputs_of_is_named_in_the_table_not_shown_as_a_column_of_dashes(window, pair, qapp):
    aspirin, ethanol = pair
    event = _run_batch(window, qapp, [aspirin, ethanol], ["tpsa"], [])
    view = window._results_workspace.table_view
    window._results_workspace.begin_project_run(type("Plan", (), {"run_id": "run-1"})())
    view.apply_progress(event, adopt=True)
    _make(window)
    qapp.processEvents()
    assert not any(c.source == "score" for c in view.table().columns)
    assert not view._score_note.isHidden() and "mol_logp" in view._score_note.text() and LABEL in view._score_note.text()


# --- a score over the polarizability (the first report calculator typed for scores) -------------------------------------------------------

_ALPHA = "calculator:polarizability:Molecular polarizability"


def _run_polarizability(window, qapp, model, **parameters):
    """The calculator as the Properties panel runs it for one molecule, with its registered defaults and then `parameters` over them."""
    from openchem.domain.calculator import CalculationRequest

    definition = window._services.calculator_registry.get("polarizability")
    arguments = {p.name: p.default for p in definition.parameters}
    arguments.update(parameters)
    window._services.descriptor_service.run_calculator(model, CalculationRequest(calculator_id="polarizability", molecule_uuid=model.uuid, parameters=arguments))
    _drain(qapp)


def _recorded_alpha(window, model) -> float:
    """The number the calculator recorded in its own provenance, unrounded: the figure the score has to read."""
    held = [
        s.result.provenance.parameters["polarizability_a3"]
        for s in window._services.result_store_service.store.all_results(model.uuid)
        if getattr(s.result, "report_id", "") == "polarizability"
    ]
    assert held, "the calculator's result is stored for the molecule"
    return held[-1]


def test_a_score_over_the_polarizability_is_the_formula_of_the_number_the_calculator_recorded(window, pair, qapp):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    made = _make(window, label="Polarisable", formula="ramp(alpha, 25, 10)", inputs=[("alpha", _ALPHA)])
    before = window._services.score_service.values_for(aspirin)[0]
    assert before.value is None and "has not been calculated" in before.reason
    _run_polarizability(window, qapp, aspirin)
    alpha = _recorded_alpha(window, aspirin)
    assert 12.0 < alpha < 22.0, "aspirin's polarizability is about 16 A^3: a sanity bound on the number, independent of the typing"
    value = window._services.score_service.values_for(aspirin)[0]
    assert value.status.value == "value" and value.value == pytest.approx(min(1.0, max(0.0, (25.0 - alpha) / 15.0)), abs=1e-12)
    assert value.inputs[0].value == alpha, "the exact number the calculator recorded, not the two-decimal text of its line"
    assert made.score_id == value.definition.score_id


@pytest.mark.parametrize("ask", [{"method": "Miller ahp"}, {"method": "Miller ahc"}, {"major_microspecies": True, "pH": 7.4}])
def test_a_polarizability_from_another_method_or_structure_gives_the_score_no_number(window, pair, qapp, ask):
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window, label="Polarisable", formula="ramp(alpha, 25, 10)", inputs=[("alpha", _ALPHA)])
    _run_polarizability(window, qapp, aspirin, **ask)
    value = window._services.score_service.values_for(aspirin)[0]
    assert value.value is None and value.status.value == "refused" and _ALPHA in value.reason, value.reason


def test_the_project_table_cell_of_the_score_is_the_same_number_as_the_reader_gives(window, pair, qapp):
    from openchem.domain.batch import BatchRequest
    from openchem.services.batch_service import BatchProgress

    aspirin, ethanol = pair
    _select(window, qapp, aspirin)
    made = _make(window, label="Polarisable", formula="ramp(alpha, 25, 10)", inputs=[("alpha", _ALPHA)])
    _run_polarizability(window, qapp, aspirin)
    events = []
    window._services.event_bus.subscribe(BatchProgress, events.append)
    window._services.batch_service.request_batch(BatchRequest(molecule_uuids=[m.uuid for m in pair], descriptor_ids=[], calculator_ids=["polarizability"]), list(pair))
    _drain(qapp)
    table = events[-1].table
    from openchem.domain.score_table import score_value_in_table

    for molecule in pair:
        in_table = score_value_in_table(window._services.score_service.store.definitions()[0], table, molecule.uuid)
        assert in_table.status.value == "value", (molecule.display_name, in_table.reason)
    assert score_value_in_table(window._services.score_service.store.definitions()[0], table, aspirin.uuid).value == pytest.approx(
        window._services.score_service.values_for(aspirin)[0].value
    )
    assert made.score_id


# --- a score over the topology indices (the second report calculator typed for scores) ---------------------------------------------------------

_WIENER = "calculator:topology_analysis:Wiener index"
_RANDIC = "calculator:topology_analysis:Randic index"


def _run_topology(window, qapp, model, **parameters):
    """The calculator as the Properties panel runs it for one molecule, with its registered defaults and then `parameters` over them."""
    from openchem.domain.calculator import CalculationRequest

    definition = window._services.calculator_registry.get("topology_analysis")
    arguments = {p.name: p.default for p in definition.parameters}
    arguments.update(parameters)
    window._services.descriptor_service.run_calculator(model, CalculationRequest(calculator_id="topology_analysis", molecule_uuid=model.uuid, parameters=arguments))
    _drain(qapp)


def _recorded_fact(window, model, label):
    """The fact the calculator recorded in its stored result, which carries the number and the rounded text the line shows."""
    held = [
        fact
        for s in window._services.result_store_service.store.all_results(model.uuid)
        if getattr(s.result, "report_id", "") == "topology_analysis"
        for fact in s.result.facts
        if fact.label == label
    ]
    assert held, f"the calculator's {label} is stored for the molecule"
    return held[-1]


def test_a_score_over_a_topology_index_is_the_formula_of_the_exact_number_and_not_of_the_rounded_line(window, pair, qapp):
    """Asked for no decimal places the line reads `Randic index: 6`; the score has to be made from 6.109..., which is the whole point of typing the number."""
    aspirin, _ = pair
    _select(window, qapp, aspirin)
    _make(window, label="Branching", formula="ramp(randic, 10, 2)", inputs=[("randic", _RANDIC)])
    before = window._services.score_service.values_for(aspirin)[0]
    assert before.value is None and "has not been calculated" in before.reason
    _run_topology(window, qapp, aspirin, decimal_places=0)
    fact = _recorded_fact(window, aspirin, "Randic index")
    assert fact.display_value == "6" and 6.1 < fact.value < 6.12, "the line is rounded to nothing and the number is not"
    value = window._services.score_service.values_for(aspirin)[0]
    assert value.status.value == "value" and value.inputs[0].value == fact.value
    assert value.value == pytest.approx((10.0 - fact.value) / 8.0, abs=1e-12)
    assert value.value != pytest.approx(0.5, abs=1e-3), "a score made from the text '6' would be 0.5"


def test_a_score_over_a_topology_index_reads_the_drawings_graph_when_the_molecule_has_a_conformer(window, pair, qapp):
    """A conformer carries explicit hydrogens, and a Wiener index over 21 atoms is a different number from one over 13: the score must read the drawing's, in Results and in the table."""
    from rdkit import Chem

    from openchem.domain.score_table import score_value_in_table

    aspirin, ethanol = pair
    _select(window, qapp, aspirin)
    _with_a_conformer(window, qapp, aspirin)
    assert aspirin.conformers
    _make(window, label="Compact", formula="ramp(wiener, 400, 100)", inputs=[("wiener", _WIENER)])
    _run_topology(window, qapp, aspirin)
    value = window._services.score_service.values_for(aspirin)[0]
    assert value.status.value == "value" and value.inputs[0].value == 246.0, "aspirin's heavy-atom graph (13 atoms)"
    explicit = window._services.chemistry_engine.mol_from_model(aspirin)
    on_a_conformer = window._services.calculator_registry.compute("topology_analysis", Chem.AddHs(explicit), "uuid", {})
    other = [f.value for f in on_a_conformer.facts if f.label == "Wiener index"][0]
    assert other != 246 and other > 246, "the same calculator on the explicit-hydrogen graph is another number, which the score must never read"
    event = _run_batch(window, qapp, [aspirin, ethanol], [], ["topology_analysis"])
    definition = window._services.score_service.store.definitions()[0]
    in_table = score_value_in_table(definition, event.table, aspirin.uuid)
    assert in_table.status.value == "value" and in_table.inputs[0].value == 246.0 and in_table.value == pytest.approx(value.value)
    assert score_value_in_table(definition, event.table, ethanol.uuid).inputs[0].value == 4.0


# --- the Batch panel's own table ---------------------------------------------------------------------------------------------------------


def _press_batch_run(window, qapp, *property_ids):
    """The Batch panel's REAL Fill-table button, with only these properties ticked, and the run waited out."""
    panel = window._batch_panel
    panel._clear_selection()
    for property_id in property_ids:
        panel.check(property_id)
    assert panel._run_button.isEnabled(), "the Fill table button is pressable"
    panel._run_button.click()
    _drain(qapp)
    return panel


def _batch_grid(panel) -> dict[str, dict[str, str]]:
    grid = panel._results
    headers = [grid.horizontalHeaderItem(i).text() for i in range(grid.columnCount())]
    return {grid.item(r, 0).text(): {headers[c]: grid.item(r, c).text() for c in range(1, grid.columnCount())} for r in range(grid.rowCount())}


def test_a_score_is_a_column_of_the_batch_panel_s_own_table_after_its_real_run_and_agrees_with_the_results_reader(window, pair, qapp):
    aspirin, ethanol = pair
    made = _make(window)
    panel = _press_batch_run(window, qapp, "tpsa", "mol_logp")
    column = next(c for c in panel._view.table().columns if c.source == "score")
    assert column.label == LABEL and column.column_id == f"score:{made.score_id}"
    shown = _batch_grid(panel)
    assert set(shown) == {"Aspirin", "Ethanol"}
    for molecule in (aspirin, ethanol):
        assert shown[molecule.display_name][LABEL] != "—"
        _select(window, qapp, molecule)
        assert float(shown[molecule.display_name][LABEL]) == pytest.approx(_report(window).facts[0].value, abs=5e-3)


def test_a_score_defined_while_the_batch_panel_holds_a_table_joins_it_at_once_and_a_removed_one_leaves(window, pair, qapp):
    panel = _press_batch_run(window, qapp, "tpsa", "mol_logp")
    assert not any(c.source == "score" for c in panel._view.table().columns)
    made = _make(window)
    qapp.processEvents()
    assert any(c.source == "score" for c in panel._view.table().columns) and LABEL in _batch_grid(panel)["Aspirin"]
    window._services.score_service.remove(made.score_id)
    qapp.processEvents()
    assert not any(c.source == "score" for c in panel._view.table().columns) and LABEL not in _batch_grid(panel)["Aspirin"]


def test_the_batch_panel_and_the_results_dock_hold_the_same_score_columns_for_the_same_run(window, pair, qapp):
    aspirin, ethanol = pair
    _make(window)
    panel = _press_batch_run(window, qapp, "tpsa", "mol_logp")
    dock = window._results_workspace.table_view
    event = _run_batch(window, qapp, [aspirin, ethanol], ["tpsa", "mol_logp"], [])
    window._results_workspace.begin_project_run(type("Plan", (), {"run_id": "run-1"})())
    dock.apply_progress(event, adopt=True)
    batch_cells = _batch_grid(panel)
    dock_grid = dock._results
    dock_headers = [dock_grid.horizontalHeaderItem(i).text() for i in range(dock_grid.columnCount())]
    column = dock_headers.index(LABEL)
    for r in range(dock_grid.rowCount()):
        assert dock_grid.item(r, column).text() == batch_cells[dock_grid.item(r, 0).text()][LABEL]


# --- ticking what the scores read, in the real window ------------------------------------------------------------------------------------


def test_the_real_windows_presets_menu_offers_what_the_scores_read_and_it_ticks_and_runs_them_into_the_table(window, pair, qapp):
    panel = window._property_panel
    menu, actions = panel.build_presets_menu()
    assert "tick_scores" not in actions, "no scores yet, so no entry"
    menu.deleteLater()
    _make(window, label="Oxidation window", formula="ramp(psa, 140, 60) * ramp(ob, -100, 0)", inputs=[("psa", "descriptor:tpsa"), ("ob", "calculator:oxygen_balance:Oxygen balance (CO basis)")])
    menu, actions = panel.build_presets_menu()
    assert actions["tick_scores"].text() == "Tick what my scores read (1)"
    actions["tick_scores"].trigger()
    menu.deleteLater()
    assert panel._selected_calculator_ids() == ["oxygen_balance"]
    from openchem.ui.panels.property_panel import _SCOPE_ALL

    panel.set_scope(_SCOPE_ALL)
    panel._run_selected_button.click()
    _drain(qapp)
    table = window._results_workspace.table_view.table()
    assert any(c.source == "score" and c.label.startswith("Oxidation window") for c in table.columns)
