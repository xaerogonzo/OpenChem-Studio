"""Optimizing a conformer you CHOSE: the Conformer box, the 3D viewer's button, the Tools entry and the badges.

Before this, an ORCA optimization always ran on the conformer every calculation uses, so the one you were looking at
could never be the one optimized. These pin the doors that now point the Quantum Chemistry panel at a chosen conformer
(and start nothing), what a Run on that panel then submits, and the two places that say a molecule holds an ORCA
geometry.
"""

from __future__ import annotations

import pytest

from openchem.chem.calculation_input import (
    canonical_conformer,
    geometry_fingerprint,
    resolve_calculation_input,
    resolve_conformer_input,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import RUN_METHOD_BASIS, Provenance
from openchem.domain.conformer import (
    ORCA_OPTIMIZED,
    ConformerModel,
    conformer_choice_text,
    quantum_optimized_note,
)
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged

import conftest
from tests import test_orca_landing_in_slot as landing
from tests.test_quantum_chemistry_panel import _make_panel, _panel_with_conformers


def _orca(level: str = "HF STO-3G", molblock: str = "orca", timestamp: float | None = None) -> ConformerModel:
    provenance = Provenance(created_by="core", method="orca", parameters={RUN_METHOD_BASIS: level} if level else {})
    conformer = ConformerModel(molblock=molblock, method=ORCA_OPTIMIZED, provenance=provenance)
    if timestamp is not None:
        conformer.timestamp = timestamp
    return conformer


def _forcefield(count: int) -> list[ConformerModel]:
    return [ConformerModel(molblock=f"ff-{i}", energy=float(i) / 2, method="mmff94", timestamp=1.0) for i in range(count)]


# --- the resolver: any conformer gets the validation the canonical one always had ------------------------------------


@pytest.fixture
def real_molecule():
    engine = ChemistryEngine()
    model = MoleculeModel(display_name="Hexanol")
    engine.set_structure_from_smiles(model, "CCCCCCO")
    from openchem.chem.conformer_providers import RDKitConformerProvider

    generated = RDKitConformerProvider(random_seed=0xC0FFEE).generate_conformers(
        engine.mol_from_model(model), num_conformers=3, optimize=True
    )
    model.conformers = [
        ConformerModel(molblock=engine.mol_to_molblock(mol), energy=energy + index, method="mmff94")
        for index, (mol, energy) in enumerate(generated)
    ]
    return engine, model


def test_a_chosen_conformer_is_handed_over_with_its_own_identity(real_molecule):
    engine, model = real_molecule
    chosen = model.conformers[-1]
    assert chosen is not canonical_conformer(model), "the premise: not the one every calculation uses"

    resolved = resolve_conformer_input(engine, model, chosen)

    assert resolved.used == GEOMETRY
    assert resolved.fingerprint == geometry_fingerprint(chosen)
    assert resolved.fingerprint != geometry_fingerprint(canonical_conformer(model))
    handed = resolved.mol.GetConformer().GetAtomPosition(0)
    expected = engine.mol_from_molblock(chosen.molblock).GetConformer().GetAtomPosition(0)
    assert (handed.x, handed.y, handed.z) == (expected.x, expected.y, expected.z), "its own coordinates"


def test_the_canonical_conformer_resolves_exactly_as_it_did_before(real_molecule):
    engine, model = real_molecule

    chosen = resolve_conformer_input(engine, model, canonical_conformer(model))
    legacy = resolve_calculation_input(engine, model, GEOMETRY)

    assert (chosen.fingerprint, chosen.used) == (legacy.fingerprint, legacy.used)


def test_an_unusable_chosen_conformer_falls_back_to_the_drawing_and_says_so(real_molecule):
    engine, model = real_molecule
    broken = ConformerModel(molblock="this is not a molblock", method="mmff94")

    resolved = resolve_conformer_input(engine, model, broken)

    assert resolved.used == DRAWING, "never presented as the conformer that was asked for"
    assert resolved.fingerprint == resolve_calculation_input(engine, model, DRAWING).fingerprint


def test_a_flat_chosen_conformer_is_the_drawing_too(real_molecule):
    engine, model = real_molecule
    flat = ConformerModel(molblock=model.molblock, method="drawing")

    assert resolve_conformer_input(engine, model, flat).used == DRAWING


def test_no_conformer_at_all_is_the_drawing(real_molecule):
    engine, model = real_molecule

    assert resolve_conformer_input(engine, model, None).used == DRAWING


# --- the words that name a conformer ------------------------------------------------------------------------------------


def test_a_conformer_reads_as_its_number_and_how_far_above_the_lowest_it_is():
    conformers = _forcefield(3)

    assert [conformer_choice_text(conformers, i) for i in range(3)] == [
        "1 - lowest energy", "2 - +0.50 kcal/mol", "3 - +1.00 kcal/mol",
    ]


def test_an_orca_geometry_says_so_and_never_claims_a_force_field_energy():
    conformers = [*_forcefield(2), _orca()]

    assert conformer_choice_text(conformers, 2) == "3 - ORCA optimized (HF STO-3G)"
    assert conformer_choice_text([*_forcefield(1), _orca(level="")], 1) == "2 - ORCA optimized", "no level is invented"


def test_a_conformer_with_no_energy_says_so():
    assert conformer_choice_text([ConformerModel(molblock="x", method="imported")], 0) == "1 - no energy"


def test_the_badge_names_one_geometry_or_counts_several_and_names_the_newest_level():
    assert quantum_optimized_note(_forcefield(3)) == ""
    assert quantum_optimized_note([*_forcefield(2), _orca()]) == "ORCA-optimized geometry (HF STO-3G)"
    assert quantum_optimized_note([_orca(level="")]) == "ORCA-optimized geometry"
    older, newer = _orca(level="HF STO-3G", timestamp=1.0), _orca(level="B3LYP def2-SVP", timestamp=2.0)
    assert quantum_optimized_note([newer, *_forcefield(1), older]) == "2 ORCA-optimized conformers (newest: B3LYP def2-SVP)"
    assert quantum_optimized_note([_orca(level="", timestamp=1.0), _orca(level="", timestamp=2.0)]) == (
        "2 ORCA-optimized conformers"
    ), "an unrecorded level is left out, never guessed"


# --- the Quantum Chemistry panel's Conformer box ------------------------------------------------------------------------


def _optimizing_panel(count: int):
    """A panel set to Geometry Optimization, the only calculation a chosen conformer applies to."""
    panel, service, molecule = _panel_with_conformers(count)
    panel.select_calculation_type("opt")
    return panel, service, molecule


def _items(panel) -> list[tuple[str, str]]:
    combo = panel._conformer_combo
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


def test_the_conformer_box_offers_automatic_and_every_conformer_by_number(qapp):
    panel, _service, molecule = _optimizing_panel(3)
    try:
        items = _items(panel)

        assert items[0][1] == "" and items[0][0].startswith("Automatic (conformer 1 of 3)")
        assert [data for _text, data in items[1:]] == [c.conformer_id for c in molecule.conformers]
        assert [text.split(" - ")[0] for text, _data in items[1:]] == ["1", "2", "3"]
        assert panel._conformer_combo.isEnabled()
    finally:
        conftest.dispose(panel)


def test_automatic_names_the_conformer_every_calculation_uses_even_when_it_is_not_first(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        molecule.conformers[2].energy = -5.0
        for other in molecule.conformers[:2]:
            other.energy = 1.0
        panel._refresh_conformer_combo()

        assert _items(panel)[0][0].startswith("Automatic (conformer 3 of 3)")
    finally:
        conftest.dispose(panel)


def test_with_no_conformers_the_box_says_so_and_is_disabled(qapp):
    panel, _engine, _service = _make_panel()
    try:
        assert panel._conformer_combo.currentText().startswith("None yet")
        assert not panel._conformer_combo.isEnabled()
    finally:
        conftest.dispose(panel)


def test_a_run_on_a_chosen_conformer_is_submitted_with_that_conformers_geometry_identity_and_slot(qapp):
    panel, service, molecule = _optimizing_panel(3)
    try:
        chosen = molecule.conformers[1]
        assert panel.choose_conformer(molecule.uuid, chosen.conformer_id)

        panel._on_run_clicked()

        request = service.requests[0]
        assert request["input_fingerprint"] == geometry_fingerprint(chosen)
        assert request["source_slot"] == 2, "its number when Run was pressed"
        assert request["calculation_input"] == GEOMETRY
        assert request["structure_identity"] == molecule.canonical_smiles != ""
    finally:
        conftest.dispose(panel)


def test_automatic_still_runs_on_the_conformer_every_calculation_uses(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        molecule.conformers.append(_orca(molblock=molecule.conformers[0].molblock))
        panel._refresh_conformer_combo()

        panel._on_run_clicked()

        assert service.requests[0]["input_fingerprint"] == geometry_fingerprint(canonical_conformer(molecule))
        assert service.requests[0]["source_slot"] == 4
    finally:
        conftest.dispose(panel)


def test_averaging_over_the_conformers_has_no_single_conformer_to_choose(qapp):
    panel, service, molecule = _optimizing_panel(3)
    try:
        panel.choose_conformer(molecule.uuid, molecule.conformers[1].conformer_id)

        panel._boltzmann_check.setChecked(True)

        assert not panel._conformer_combo.isEnabled()
        assert "every conformer" in panel._conformer_combo.toolTip()
        panel._on_run_clicked()
        assert service.requests == [] and len(service.boltzmann_requests) == 1, "the ensemble path, not a chosen one"
        panel._boltzmann_check.setChecked(False)
        assert panel._conformer_combo.isEnabled(), "and it comes back"
    finally:
        conftest.dispose(panel)


def test_the_box_applies_to_every_single_calculation_and_is_greyed_only_for_averaging(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        for label in ("Single Point", "Geometry Optimization", "Optimization + Frequency", "NMR (raw shielding)"):
            panel._calc_type_combo.setCurrentText(label)
            assert panel._conformer_combo.isEnabled(), label
        panel._boltzmann_check.setChecked(True)
        assert not panel._conformer_combo.isEnabled()
    finally:
        conftest.dispose(panel)


def test_a_pick_survives_a_change_of_calculation_and_the_next_run_uses_it(qapp):
    panel, service, molecule = _optimizing_panel(3)
    try:
        chosen = molecule.conformers[1]
        panel.choose_conformer(molecule.uuid, chosen.conformer_id)

        panel._calc_type_combo.setCurrentText("Single Point")

        assert panel._conformer_combo.currentData() == chosen.conformer_id
        panel._on_run_clicked()
        assert service.requests[0]["input_fingerprint"] == geometry_fingerprint(chosen)
        assert service.requests[0]["calc_type"] == "sp"
    finally:
        conftest.dispose(panel)


def test_a_conformer_can_be_chosen_for_any_calculation_not_only_an_optimization(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        assert panel._calc_type_combo.currentText() == "Single Point"

        assert panel.choose_conformer(molecule.uuid, molecule.conformers[1].conformer_id) is True
        assert panel._conformer_combo.currentData() == molecule.conformers[1].conformer_id
    finally:
        conftest.dispose(panel)


# --- a result computed on a conformer that is not the one every calculation uses says so --------------------------


def _result_event(molecule, conformer):
    from openchem.events.events import QuantumChemistryResultReady

    return QuantumChemistryResultReady(
        molecule_uuid=molecule.uuid, descriptors=[], conformer=None,
        input_fingerprint=geometry_fingerprint(conformer), structure_identity=molecule.canonical_smiles,
    )


def _single_point_on(panel, molecule, conformer):
    panel._calc_type_combo.setCurrentText("Single Point")
    if conformer is not None:
        assert panel.choose_conformer(molecule.uuid, conformer.conformer_id)
    panel._on_run_clicked()
    panel._on_result_ready(_result_event(molecule, conformer or canonical_conformer(molecule)))


def test_a_single_point_on_another_conformer_says_where_it_went(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        molecule.conformers[0].energy = 1.0
        molecule.conformers[1].energy = 0.0  # the one every calculation uses
        molecule.conformers[2].energy = 2.0
        panel._refresh_conformer_combo()

        _single_point_on(panel, molecule, molecule.conformers[2])

        text = panel._results_label.text()
        assert "Computed on conformer 3, not the one every calculation uses (conformer 2)" in text
        assert "run history" in text and "does not come back" in text
    finally:
        conftest.dispose(panel)


def test_automatic_a_chosen_canonical_conformer_and_an_optimization_carry_no_note(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        molecule.conformers[1].energy = 0.0
        molecule.conformers[0].energy = 1.0
        molecule.conformers[2].energy = 2.0
        panel._refresh_conformer_combo()

        _single_point_on(panel, molecule, None)
        assert "Computed on conformer" not in panel._results_label.text(), "Automatic"
        _single_point_on(panel, molecule, molecule.conformers[1])
        assert "Computed on conformer" not in panel._results_label.text(), "the canonical one, chosen by hand"
        panel._calc_type_combo.setCurrentText("Geometry Optimization")
        panel.choose_conformer(molecule.uuid, molecule.conformers[2].conformer_id)
        panel._on_run_clicked()
        panel._on_result_ready(_result_event(molecule, molecule.conformers[2]))
        assert "Computed on conformer" not in panel._results_label.text(), "an optimization replaces its source instead"
    finally:
        conftest.dispose(panel)


def test_the_note_belongs_to_the_run_that_earned_it_and_never_leaks_to_the_next(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        molecule.conformers[1].energy = 0.0
        molecule.conformers[0].energy = 1.0
        molecule.conformers[2].energy = 2.0
        panel._refresh_conformer_combo()
        _single_point_on(panel, molecule, molecule.conformers[2])
        assert "Computed on conformer 3" in panel._results_label.text()

        panel._conformer_combo.setCurrentIndex(0)  # back to Automatic
        panel._boltzmann_check.setChecked(True)
        panel._on_run_clicked()
        panel._on_result_ready(_result_event(molecule, molecule.conformers[1]))

        assert "Computed on conformer" not in panel._results_label.text()
    finally:
        conftest.dispose(panel)


def test_choosing_selects_only_and_names_what_it_could_not_find(qapp):
    panel, service, molecule = _optimizing_panel(3)
    try:
        assert panel.choose_conformer(molecule.uuid, molecule.conformers[2].conformer_id) is True
        assert panel._conformer_combo.currentData() == molecule.conformers[2].conformer_id
        assert panel.choose_conformer(molecule.uuid, "not-a-conformer") is False
        assert panel.choose_conformer("not-a-molecule", molecule.conformers[0].conformer_id) is False
        assert service.requests == [] and service.boltzmann_requests == []
    finally:
        conftest.dispose(panel)


def test_preparing_an_optimization_sets_the_panel_up_and_starts_nothing(qapp):
    panel, service, molecule = _panel_with_conformers(3)
    try:
        panel._boltzmann_check.setChecked(True)
        panel._calc_type_combo.setCurrentText("Single Point")
        chosen = molecule.conformers[1]

        assert panel.prepare_optimization(molecule.uuid, chosen.conformer_id) is True

        assert panel._calc_type_combo.currentText() == "Geometry Optimization"
        assert panel._conformer_combo.currentData() == chosen.conformer_id
        assert not panel._boltzmann_check.isChecked(), "an averaged run has no single conformer to optimize"
        assert "conformer 2 of 3" in panel._status_label.text() and "Run" in panel._status_label.text()
        assert service.requests == [] and service.boltzmann_requests == [], "NOTHING is started"
        assert panel._run_button.isEnabled(), "and Run is still the person's to press"
    finally:
        conftest.dispose(panel)


def test_preparing_an_optimization_of_a_conformer_that_is_gone_changes_nothing(qapp):
    panel, _service, molecule = _panel_with_conformers(3)
    try:
        panel._calc_type_combo.setCurrentText("Single Point")

        assert panel.prepare_optimization(molecule.uuid, "gone") is False

        assert panel._calc_type_combo.currentText() == "Single Point"
    finally:
        conftest.dispose(panel)


def test_a_chosen_conformer_that_is_replaced_falls_back_to_automatic_and_the_box_says_so(qapp):
    """The optimization replaced it in its slot (or the conformers were generated again). What Run will do is always
    what the box reads."""
    panel, service, molecule = _optimizing_panel(3)
    try:
        chosen = molecule.conformers[1]
        panel.choose_conformer(molecule.uuid, chosen.conformer_id)
        molecule.conformers[1] = _orca(molblock=chosen.molblock)

        panel._on_conformers_changed(ConformersChanged(molecule_uuid=molecule.uuid))

        assert panel._conformer_combo.currentData() == "", "back to Automatic"
        assert panel._conformer_combo.currentText().startswith("Automatic")
        panel._on_run_clicked()
        assert service.requests[0]["input_fingerprint"] == geometry_fingerprint(canonical_conformer(molecule))
    finally:
        conftest.dispose(panel)


def test_conformers_changing_on_another_molecule_leaves_the_box_alone(qapp):
    panel, _service, molecule = _optimizing_panel(3)
    try:
        panel.choose_conformer(molecule.uuid, molecule.conformers[1].conformer_id)

        panel._on_conformers_changed(ConformersChanged(molecule_uuid="someone-else"))

        assert panel._conformer_combo.currentData() == molecule.conformers[1].conformer_id
    finally:
        conftest.dispose(panel)


# --- the 3D viewer's button -----------------------------------------------------------------------------------------------


def _viewer(count: int = 4):
    from tests.test_molecule_viewer3d_widget import _gallery_widget

    return _gallery_widget(None, count=count)


def test_the_button_is_off_until_there_is_a_conformer_to_optimize(qapp):
    from tests.test_molecule_viewer3d_widget import _make_widget

    widget, _backend, _bus = _make_widget(qapp)
    try:
        assert not widget._orca_button.isEnabled()
        widget.set_molecule(MoleculeModel(display_name="Bare"))
        assert not widget._orca_button.isEnabled()
    finally:
        conftest.dispose(widget)


def test_the_button_asks_for_the_conformer_on_screen_by_id(qapp):
    widget, _backend, molecule = _viewer(4)
    asked: list[tuple[str, str]] = []
    widget.orca_optimize_requested.connect(lambda uuid, conformer_id: asked.append((uuid, conformer_id)))
    try:
        assert widget._orca_button.isEnabled()
        widget._show_next_conformer()
        widget._show_next_conformer()  # 3 of 4

        widget._orca_button.click()

        assert asked == [(molecule.uuid, molecule.conformers[2].conformer_id)]
    finally:
        conftest.dispose(widget)


def test_in_the_gallery_the_button_acts_on_the_cell_that_was_clicked(qapp):
    widget, _backend, molecule = _viewer(8)
    asked: list[str] = []
    widget.orca_optimize_requested.connect(lambda _uuid, conformer_id: asked.append(conformer_id))
    try:
        widget._gallery_check.setChecked(True)
        widget._on_grid_cell_clicked(4)  # the fifth cell of the first page

        widget._orca_button.click()

        assert asked == [molecule.conformers[4].conformer_id]
    finally:
        conftest.dispose(widget)


def test_the_viewer_says_which_conformer_it_shows_for_a_molecule_and_none_for_another(qapp):
    widget, _backend, molecule = _viewer(4)
    try:
        widget._show_next_conformer()

        assert widget.conformer_id_on_screen(molecule) == molecule.conformers[1].conformer_id
        assert widget.conformer_id_on_screen(MoleculeModel(display_name="Other")) is None
    finally:
        conftest.dispose(widget)


# --- the window: the button and the menu both set the panel up and start nothing ------------------------------------------


@pytest.fixture(autouse=True)
def _close_landing_windows():
    yield
    while landing._WINDOWS:
        landing._WINDOWS.pop().close()


def _the_action(window, text: str):
    for action in window.menuBar().findChildren(type(window._recalculate_action)):
        if action.text() == text:
            return action
    raise AssertionError(f"no menu action {text!r}")


def _window(qapp, tmp_path):
    window, services, molecule, recorder = landing._window_with(qapp, tmp_path)
    window._viewer3d.set_molecule(molecule)
    landing._drain(qapp)
    return window, services, molecule, recorder


def test_the_viewers_button_sets_the_panel_up_on_the_conformer_it_shows_and_starts_nothing(qapp, tmp_path):
    window, services, molecule, _recorder = _window(qapp, tmp_path)
    viewer, panel = window._viewer3d, window._quantum_chemistry_panel
    viewer._show_next_conformer()
    viewer._show_next_conformer()
    shown = molecule.conformers[2]

    viewer._orca_button.click()
    landing._drain(qapp)

    assert panel._molecule_combo.currentData() == molecule.uuid
    assert panel._conformer_combo.currentData() == shown.conformer_id
    assert panel._calc_type_combo.currentText() == "Geometry Optimization"
    assert not services.quantum_chemistry_service._active_jobs, "no job was started"
    assert "press Run" in window.statusBar().currentMessage()


def test_the_tools_entry_does_the_same_for_the_conformer_the_viewer_shows(qapp, tmp_path):
    window, services, molecule, _recorder = _window(qapp, tmp_path)
    window._viewer3d._show_next_conformer()
    shown = molecule.conformers[1]

    _the_action(window, "ORCA Geometry Optimization...").trigger()
    landing._drain(qapp)

    assert window._quantum_chemistry_panel._conformer_combo.currentData() == shown.conformer_id
    assert window._quantum_chemistry_panel._calc_type_combo.currentText() == "Geometry Optimization"
    assert not services.quantum_chemistry_service._active_jobs


def test_the_tools_entry_falls_back_to_the_conformer_every_calculation_uses_when_the_viewer_shows_another_molecule(
    qapp, tmp_path
):
    window, _services, molecule, _recorder = _window(qapp, tmp_path)
    window._viewer3d.set_molecule(MoleculeModel(display_name="Elsewhere"))
    window._viewer3d._conformer_index = 0
    molecule.conformers[3].energy = -9.0  # make the fourth the canonical one

    _the_action(window, "ORCA Geometry Optimization...").trigger()
    landing._drain(qapp)

    assert window._quantum_chemistry_panel._conformer_combo.currentData() == molecule.conformers[3].conformer_id


def test_the_tools_entry_with_nothing_to_optimize_says_what_to_do_and_leaves_the_panel_alone(qapp, tmp_path):
    window, _services, molecule, _recorder = _window(qapp, tmp_path)
    molecule.conformers = []
    panel = window._quantum_chemistry_panel
    panel._calc_type_combo.setCurrentText("Single Point")

    _the_action(window, "ORCA Geometry Optimization...").trigger()

    assert "generate some first" in window.statusBar().currentMessage()
    assert panel._calc_type_combo.currentText() == "Single Point"


def test_a_request_for_a_conformer_that_vanished_says_so_instead_of_pretending(qapp, tmp_path):
    window, _services, molecule, _recorder = _window(qapp, tmp_path)

    window._on_orca_optimize_requested(molecule.uuid, "gone")

    assert "no longer there" in window.statusBar().currentMessage()


def test_pressing_run_after_the_button_optimizes_that_conformer_in_its_slot(qapp, tmp_path):
    """The whole route with a real service and a stand-in engine: button -> panel -> Run -> job -> landing."""
    window, services, molecule, _recorder = _window(qapp, tmp_path)
    viewer, panel = window._viewer3d, window._quantum_chemistry_panel
    viewer._show_next_conformer()
    viewer._show_next_conformer()  # conformer 3 of 20
    source = molecule.conformers[2]
    viewer._orca_button.click()
    landing._drain(qapp)

    import sys

    service = services.quantum_chemistry_service
    service.register_provider(landing._optimizing_stand_in(sleep_seconds=0.2))
    service._settings.set("orca/executable_path", sys.executable)
    request: dict = {}
    original = service.request_calculation

    def capture(**kwargs):
        # The panel asks for the "orca" engine; the stand-in is registered as "fake_opt".
        request.update(kwargs)
        return original(**{**kwargs, "provider_id": "fake_opt"})

    service.request_calculation = capture
    runs: list = []
    from openchem.events.events import QuantumChemistryRunCompleted

    services.event_bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    panel._on_run_clicked()
    landing._wait_for_the_run(qapp, runs)

    assert request["input_fingerprint"] == geometry_fingerprint(source)
    assert len(molecule.conformers) == 20
    assert molecule.conformers[2].method == ORCA_OPTIMIZED, "it replaced conformer 3 in ITS slot"
    assert [c.method for i, c in enumerate(molecule.conformers) if i != 2] == ["mmff94"] * 19
    assert viewer._conformer_index == 2, "and the viewer is on it"


# --- the badges -----------------------------------------------------------------------------------------------------------


def _explorer(project: ProjectModel):
    from PySide6.QtGui import QUndoStack

    from openchem.ui.panels.project_explorer_panel import ProjectExplorerPanel

    bus = EventBus()
    panel = ProjectExplorerPanel(bus, QUndoStack())
    panel.set_project(project)
    return panel, bus


def _row_texts(panel) -> list[str]:
    return [panel._list.item(i).text() for i in range(panel._list.count())]


def test_a_molecule_with_an_orca_geometry_wears_the_badge_in_the_project_list(qapp):
    plain = MoleculeModel(display_name="Plain", conformers=_forcefield(2))
    optimized = MoleculeModel(display_name="Optimized", conformers=[*_forcefield(1), _orca()])
    panel, _bus = _explorer(ProjectModel(name="P", molecules=[plain, optimized]))
    try:
        assert _row_texts(panel) == ["Plain", "Optimized  [ORCA-optimized]"]
        assert "HF STO-3G" in panel._list.item(1).toolTip()
        assert panel._list.item(0).toolTip() == ""
    finally:
        conftest.dispose(panel)


def test_the_badge_follows_the_geometry_arriving_and_leaving_without_touching_the_selection(qapp):
    molecule = MoleculeModel(display_name="Subject", conformers=_forcefield(2))
    other = MoleculeModel(display_name="Other", conformers=_forcefield(2))
    panel, bus = _explorer(ProjectModel(name="P", molecules=[molecule, other]))
    try:
        panel._list.setCurrentRow(1)
        molecule.conformers[0] = _orca()
        bus.publish(ConformersChanged(molecule_uuid=molecule.uuid))
        assert _row_texts(panel) == ["Subject  [ORCA-optimized]", "Other"]
        assert panel._list.currentRow() == 1, "the selection did not move"

        molecule.conformers[0] = ConformerModel(molblock="ff", energy=0.0, method="mmff94")
        bus.publish(ConformersChanged(molecule_uuid=molecule.uuid))
        assert _row_texts(panel) == ["Subject", "Other"]
    finally:
        conftest.dispose(panel)


def test_the_badge_is_not_part_of_the_name_a_rename_stores(qapp):
    molecule = MoleculeModel(display_name="Old", conformers=[_orca()])
    panel, _bus = _explorer(ProjectModel(name="P", molecules=[molecule]))
    try:
        panel._list.item(0).setText("New name  [ORCA-optimized]")

        assert molecule.display_name == "New name"
    finally:
        conftest.dispose(panel)


def test_conformers_changing_for_a_molecule_the_list_does_not_hold_is_ignored(qapp):
    panel, bus = _explorer(ProjectModel(name="P", molecules=[MoleculeModel(display_name="A")]))
    try:
        bus.publish(ConformersChanged(molecule_uuid="not-in-the-project"))

        assert _row_texts(panel) == ["A"]
    finally:
        conftest.dispose(panel)


def test_the_properties_header_card_shows_and_hides_a_badge_of_its_own(qapp):
    from openchem.ui.widgets.substance_card import SubstanceCard, SubstanceCardData

    card = SubstanceCard()
    try:
        assert card.badge_text() == ""
        card.set_badge("ORCA-optimized geometry (HF STO-3G)")
        card.set_data(SubstanceCardData(name="Ethanol", formula="C2H6O", classification="Molecule"))
        assert card.badge_text() == "ORCA-optimized geometry (HF STO-3G)", "a new report does not wipe it"
        assert "ORCA-optimized geometry (HF STO-3G)" in card.summary_text()
        card.clear()
        assert card.badge_text() == ""
    finally:
        conftest.dispose(card)


def test_the_header_badge_follows_the_selected_molecules_geometry_through_the_whole_window(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    card = window._property_panel._substance_card
    from openchem.events.events import MoleculeSelected

    services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    landing._drain(qapp)
    assert card.badge_text() == "", "a molecule with only force-field conformers wears none"

    event, _optimized = landing._orca_result(molecule.conformers[landing.SLOT], molecule)
    landing._land(qapp, services, event)
    assert card.badge_text() == "ORCA-optimized geometry", "the landed conformer carries no run record here, so no level"

    window._undo_stack.undo()
    landing._drain(qapp)
    assert card.badge_text() == "", "Undo takes it back"

    window._undo_stack.redo()
    landing._drain(qapp)
    assert card.badge_text() == "ORCA-optimized geometry"
    services.event_bus.publish(MoleculeSelected(molecule_uuid=None))
    landing._drain(qapp)
    assert card.badge_text() == "", "and nothing selected shows none"


def test_the_project_list_in_the_window_badges_the_molecule_when_the_geometry_lands(qapp, tmp_path):
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    explorer = window._project_explorer

    event, _optimized = landing._orca_result(molecule.conformers[landing.SLOT], molecule)
    landing._land(qapp, services, event)

    assert any(text.endswith("[ORCA-optimized]") for text in _row_texts(explorer))
    window._undo_stack.undo()
    landing._drain(qapp)
    assert not any(text.endswith("[ORCA-optimized]") for text in _row_texts(explorer))


def test_selecting_a_molecule_that_already_holds_an_orca_geometry_shows_the_badge_at_once(qapp, tmp_path):
    """Nothing landed while it was on screen, so no event announces it: selecting is the only moment to read it."""
    window, services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    molecule.conformers[landing.SLOT] = _orca(molblock=molecule.conformers[landing.SLOT].molblock)
    plain = MoleculeModel(display_name="Plain", conformers=_forcefield(2))
    window._session.project.molecules.append(plain)
    card = window._property_panel._substance_card
    from openchem.events.events import MoleculeSelected

    services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    landing._drain(qapp)
    assert card.badge_text() == "ORCA-optimized geometry (HF STO-3G)"

    services.event_bus.publish(MoleculeSelected(molecule_uuid=plain.uuid))
    landing._drain(qapp)
    assert card.badge_text() == "", "another molecule does not inherit it"
