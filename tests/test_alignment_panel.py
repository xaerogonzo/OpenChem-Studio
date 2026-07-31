from __future__ import annotations

from PySide6.QtCore import Qt

from openchem.chem.engine import ChemistryEngine
from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import AlignmentJobStateChanged, EnsembleAlignmentReady
from openchem.services.alignment_service import AlignmentService
from openchem.ui.panels.alignment_panel import AlignmentPanel

IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
NAPROXEN = "COc1ccc2cc(ccc2c1)C(C)C(=O)O"


class _RecordingService(AlignmentService):
    def __init__(self, bus: EventBus, engine: ChemistryEngine) -> None:
        super().__init__(bus, engine)
        self.calls: list[tuple[str, list[str], str, str]] = []

    def request_alignment(self, reference, probes, method="atom_types", accuracy="Normal") -> None:
        self.calls.append(
            (reference.display_name, [p.display_name for p in probes], method, accuracy)
        )


def _project(engine: ChemistryEngine, *names_and_smiles: tuple[str, str]) -> ProjectModel:
    project = ProjectModel(name="test")
    for name, smiles in names_and_smiles:
        model = MoleculeModel(display_name=name)
        engine.set_structure_from_smiles(model, smiles)
        project.molecules.append(model)
    return project


def _panel(qapp) -> tuple[AlignmentPanel, _RecordingService, EventBus, ChemistryEngine]:
    bus = EventBus()
    engine = ChemistryEngine()
    service = _RecordingService(bus, engine)
    return AlignmentPanel(service, bus), service, bus, engine


def test_reference_combo_lists_every_molecule_and_the_probe_list_excludes_it(qapp):
    panel, _service, _bus, engine = _panel(qapp)
    panel.set_project(_project(engine, ("A", IBUPROFEN), ("B", NAPROXEN), ("C", "CCO")))

    assert panel._reference_combo.count() == 3
    # The reference cannot be aligned onto itself, so it is not offered.
    probes = [panel._probe_list.item(i).text() for i in range(panel._probe_list.count())]
    assert probes == ["B", "C"]


def test_changing_the_reference_moves_it_out_of_the_probe_list(qapp):
    panel, _service, _bus, engine = _panel(qapp)
    panel.set_project(_project(engine, ("A", IBUPROFEN), ("B", NAPROXEN)))

    panel._reference_combo.setCurrentIndex(1)

    probes = [panel._probe_list.item(i).text() for i in range(panel._probe_list.count())]
    assert probes == ["A"]


def test_ticked_probes_survive_a_project_refresh(qapp):
    """set_project runs on every project mutation, so a rebuild must not
    silently drop the user's selection because an unrelated molecule was
    renamed."""
    panel, _service, _bus, engine = _panel(qapp)
    project = _project(engine, ("A", IBUPROFEN), ("B", NAPROXEN), ("C", "CCO"))
    panel.set_project(project)
    panel._probe_list.item(1).setCheckState(Qt.CheckState.Checked)

    panel.set_project(project)

    still_checked = [
        panel._probe_list.item(i).text()
        for i in range(panel._probe_list.count())
        if panel._probe_list.item(i).checkState() == Qt.CheckState.Checked
    ]
    assert still_checked == ["C"]


def test_align_passes_the_chosen_reference_probes_and_options_through(qapp):
    panel, service, _bus, engine = _panel(qapp)
    panel.set_project(_project(engine, ("A", IBUPROFEN), ("B", NAPROXEN), ("C", "CCO")))
    panel._probe_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._method_combo.setCurrentText("Common scaffold (MCS)")
    panel._accuracy_combo.setCurrentText("Fast")

    panel._align_button.click()

    assert service.calls == [("A", ["B"], "mcs", "Fast")]


def test_align_with_nothing_ticked_says_so_instead_of_running(qapp):
    panel, service, _bus, engine = _panel(qapp)
    panel.set_project(_project(engine, ("A", IBUPROFEN), ("B", NAPROXEN)))

    panel._align_button.click()

    assert service.calls == []
    assert "at least one" in panel._status_label.text()


def test_the_button_is_disabled_while_a_run_is_active(qapp):
    panel, _service, bus, _engine = _panel(qapp)

    bus.publish(AlignmentJobStateChanged(reference_uuid="u", state=CacheState.RUNNING))
    assert not panel._align_button.isEnabled()

    bus.publish(AlignmentJobStateChanged(reference_uuid="u", state=CacheState.COMPLETED))
    assert panel._align_button.isEnabled()


def test_results_table_shows_the_reference_a_success_and_a_failure_distinctly(qapp):
    panel, _service, bus, _engine = _panel(qapp)

    bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="u",
            entries=[
                EnsembleEntry(label="ref", molblock="REF"),
                EnsembleEntry(
                    label="ok", molblock="OK", score=1.25, rmsd=0.5, matched_atoms=12, typing="MMFF"
                ),
                EnsembleEntry(label="bad", molblock="", error="Could not embed"),
            ],
            method="atom_types",
            accuracy="Fast",
        )
    )

    table = panel._result_table
    assert table.rowCount() == 3
    # The reference defines the frame, so it has no score against anything.
    assert table.item(0, 1).text() == "-"
    assert table.item(1, 1).text() == "1.25"
    assert table.item(1, 2).text() == "0.500"
    assert table.item(1, 3).text() == "12"
    # A failure states the reason across the numeric columns rather than
    # leaving blanks that would read as zeros.
    assert table.item(2, 1).text() == "Could not embed"
    assert table.columnSpan(2, 1) == 3


def test_the_failed_entry_is_not_sent_to_the_viewer_and_colours_stay_aligned(qapp):
    """The table's row index and the viewer's model index diverge as soon
    as one entry fails -- this pins that they still agree on which colour
    belongs to which molecule."""
    panel, _service, bus, _engine = _panel(qapp)
    sent: list[list[tuple[str, str]]] = []
    panel._viewer.load_ensemble = lambda entries: sent.append(list(entries))

    bus.publish(
        EnsembleAlignmentReady(
            reference_uuid="u",
            entries=[
                EnsembleEntry(label="ref", molblock="REF"),
                EnsembleEntry(label="bad", molblock="", error="nope"),
                EnsembleEntry(label="ok", molblock="OK", score=1.0, rmsd=0.2, matched_atoms=5),
            ],
            method="atom_types",
            accuracy="Fast",
        )
    )

    assert [molblock for molblock, _color in sent[0]] == ["REF", "OK"]
    colors = {molblock: color for molblock, color in sent[0]}
    assert panel._result_table.item(0, 0).foreground().color().name() == colors["REF"]
    assert panel._result_table.item(2, 0).foreground().color().name() == colors["OK"]
