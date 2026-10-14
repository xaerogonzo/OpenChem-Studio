"""The scores a person defined, in the REAL main window's Results reader (`docs/DERIVED_SCORES_DESIGN.md` sections 5 and 8; slice 3b).

A real `MainWindow`, a real project with aspirin and ethanol, and the application's own always-on descriptors computing on selection, so 'current' is produced and
not asserted. Nothing here defines a score through a dialog (that is slice 3d); the service makes it, which is the call the dialog will make.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool

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
