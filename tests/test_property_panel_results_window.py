"""The merged results window, driven through the panel that owns it.

**LIFECYCLE, NOT MERGING.** `test_merged_results_dialog.py` holds the
window's own behaviour; this file holds the things only the panel can be
wrong about -- which window exists, when it is fed, and what happens when
it closes. An ordinary Qt lifetime bug is exactly the class the merge
being correct cannot catch, and this repository has paid for the
self-capturing-lambda form of it four times.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.merged_results_dialog import STALE_MARK
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose


def _fact(label: str) -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )


def _report(report_id: str, name: str, label: str, uuid: str, version: int = 0):
    return ReportResult(
        molecule_uuid=uuid,
        report_id=report_id,
        name=name,
        facts=(_fact(label),),
        structure_version=version,
    )


class _Versions:
    """A stand-in for `StructureCheckService.current_version`.

    A callable rather than the service, which is what the panel takes --
    so a fixture does not have to build a checker to have a version."""

    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    versions = _Versions()
    widget = PropertyPanel(
        bus,
        CalculatorRegistry(),
        DescriptorService(bus, engine, calculator_registry=CalculatorRegistry()),
        engine,
        structure_version_of=versions,
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    project = ProjectModel(molecules=[molecule])
    widget.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    yield widget, bus, molecule, project, versions
    dispose(widget)


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def test_one_window_per_molecule_and_asking_twice_reuses_it(panel):
    """**KEYED ON THE UUID, NOT ON OBJECT IDENTITY.** Two windows for one
    molecule is how a reader ends up comparing a result with itself, and
    only one of them would be receiving updates."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    first = widget._results_window
    widget._open_results_window()
    assert widget._results_window is first
    first.close()


def test_a_second_molecule_gets_a_second_window(panel):
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    first = widget._results_window
    assert first.molecule_uuid() == molecule.uuid

    other = MoleculeModel()
    ChemistryEngine().set_structure_from_smiles(other, "CCC")
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    _land(bus, _report("a", "A", "Formula", other.uuid))
    widget._open_results_window()
    second = widget._results_window
    assert second is not None
    assert second.molecule_uuid() == other.uuid
    second.close()


def test_a_result_arriving_updates_the_OPEN_window(panel):
    """**THE FEATURE, NOT THE MERGE.** Proving a freshly-opened window can
    merge is easy and is not the complaint: the window has to accumulate
    while it is open, which is why it is modeless in the first place."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    assert [f.label for f in window.merged().facts] == ["Formula"]

    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid))
    assert [f.label for f in window.merged().facts] == ["Formula", "Donor sites"]
    window.close()


def test_the_stale_marks_follow_the_structure_in_an_open_window(panel):
    widget, bus, molecule, _project, versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid, version=0))
    widget._open_results_window()
    window = widget._results_window
    assert STALE_MARK not in window._focus_box.itemText(1)

    versions.version = 3
    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid, version=3))
    labels = [window._focus_box.itemText(i) for i in range(window._focus_box.count())]
    assert "Elemental Analysis" + STALE_MARK in labels
    assert "Lewis Sites" in labels
    window.close()


def test_closing_the_window_disconnects_it(panel):
    """**A CLOSED WINDOW MUST NOT KEEP RECEIVING RESULTS.** Writing into a
    deleted widget is the ordinary Qt lifetime bug that correctness of the
    merge cannot catch -- and the handle has to be dropped, or the next
    open would raise on a dead C++ object."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    window.close()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    assert widget._results_window is None

    # Another result lands with no window open: nothing to write into, and
    # nothing may raise.
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    assert widget._results_window is None


def test_reopening_after_a_close_gives_a_live_window_and_not_a_duplicate(panel):
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    widget._results_window.close()
    QCoreApplication.processEvents()

    widget._open_results_window()
    reopened = widget._results_window
    assert reopened is not None
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    assert len(reopened.merged().facts) == 2
    reopened.close()


def test_selecting_another_molecule_closes_a_window_that_no_longer_describes_it(panel):
    """A window left open would show the previous molecule's results under
    the new molecule's name."""
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    assert widget._results_window is not None

    other = MoleculeModel()
    ChemistryEngine().set_structure_from_smiles(other, "CCC")
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    assert widget._results_window is None


def test_the_window_is_modeless_so_the_panel_stays_usable(panel):
    """The old dialog used `exec()`, which blocks -- and with the panel
    blocked you could never run the second calculator whose results the
    window exists to accumulate."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._open_results_window()
    window = widget._results_window
    assert not window.isModal()
    window.close()
