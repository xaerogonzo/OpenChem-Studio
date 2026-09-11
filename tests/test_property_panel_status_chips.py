"""What the launcher says beside each calculator once it stops showing values.

**THE CHIP IS THE ONLY THING LEFT SAYING WHETHER THERE IS ANYTHING TO
READ**, so its two failure modes are both silent: a state that never
updates, and a state that claims something the panel cannot know.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication

from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import (
    CalculationFinished,
    MoleculeSelected,
    ReportComputed,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.panels.property_panel import (
    _FAILURE_STYLE,
    _INFORMATION_STYLE,
    _SUCCESS_STYLE,
    _WARNING_STYLE,
    PropertyPanel,
)
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose

ALPHA = "alpha"
BETA = "beta"


def _definition(calculator_id: str, display_name: str) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=display_name,
        category="topology",
        description=f"{display_name}. Runs nothing in this fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
    )


def _report(report_id: str, name: str, uuid: str, version: int = 0, **kwargs) -> ReportResult:
    fields = dict(
        molecule_uuid=uuid,
        report_id=report_id,
        name=name,
        category="topology",
        facts=(
            Fact(
                category=FactCategory.TOPOLOGY,
                label="Wiener index",
                value=1,
                display_value="1",
                source="RDKit",
                basis=Basis.DETERMINISTIC,
            ),
        ),
        structure_version=version,
    )
    fields.update(kwargs)
    return ReportResult(**fields)


class _Versions:
    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_definition(ALPHA, "Alpha"))
    registry.register(_definition(BETA, "Beta"))
    versions = _Versions()
    widget = PropertyPanel(
        bus,
        registry,
        DescriptorService(bus, engine, calculator_registry=registry),
        engine,
        structure_version_of=versions,
    )
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    widget.set_project(ProjectModel(molecules=[molecule]))
    reader = ResultsView()
    widget.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    yield widget, bus, reader, molecule, versions
    dispose(reader)
    dispose(widget)


def _chip(widget, calculator_id):
    return widget._calculator_status[calculator_id]


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def test_every_calculator_has_a_chip_and_it_starts_at_not_run(panel):
    """The resting appearance of the whole panel: ~60 calculators nobody
    has asked anything of yet. It must not look like an error."""
    widget, _bus, _reader, _molecule, _versions = panel
    for calculator_id in (ALPHA, BETA):
        chip = _chip(widget, calculator_id)
        assert chip.text() == "Not run"
        assert _FAILURE_STYLE not in chip.styleSheet()
        # Nothing to open, and a disabled control says so rather than
        # accepting a press and doing nothing.
        assert not chip.isEnabled()


def test_a_dispatched_calculator_says_it_is_running(panel):
    """Through `_set_running`, which the panel's own docstring names as the
    ONE place the button path and "Run selected" share -- the batch path
    used to own the running set alone, which is why a single click showed
    nothing at all."""
    widget, _bus, _reader, _molecule, _versions = panel
    widget._set_running(ALPHA, True)
    assert _chip(widget, ALPHA).text() == "Running..."
    assert _chip(widget, BETA).text() == "Not run", "only the one dispatched"


def test_a_landed_result_turns_its_chip_ready_and_openable(panel):
    widget, bus, _reader, molecule, _versions = panel
    _land(bus, _report(ALPHA, "Alpha", molecule.uuid))
    chip = _chip(widget, ALPHA)
    assert chip.text().endswith("Ready")
    assert _SUCCESS_STYLE in chip.styleSheet()
    assert chip.isEnabled()
    assert _chip(widget, BETA).text() == "Not run"


def test_pressing_a_chip_shows_that_result_in_the_reader(panel):
    """**THE WIRING, THROUGH THE REAL BUTTON.** `_on_status_chip_clicked`
    reads which calculator it means off `sender()`, so calling it directly
    passes `sender() is None` and proves nothing -- the rule `jobs_cancel`
    already follows."""
    widget, bus, reader, molecule, _versions = panel
    _land(bus, _report(ALPHA, "Alpha", molecule.uuid))
    _land(bus, _report(BETA, "Beta", molecule.uuid))
    assert reader.focus() == "", "setup: nothing focused yet"

    _chip(widget, BETA).click()
    assert reader.focus() == BETA


def test_a_chip_with_nothing_to_open_cannot_be_pressed(panel):
    """The narrow half of the press. An enabled chip that quietly does
    nothing is the silent no-op 0g exists to forbid."""
    widget, _bus, reader, _molecule, _versions = panel
    chip = _chip(widget, ALPHA)
    assert not chip.isEnabled()
    chip.click()
    assert reader.focus() == ""


def test_a_refusal_is_not_painted_as_a_fault(panel):
    """A refusal travels AS a FAILED cache state, so the chip has to tell
    them apart -- this project reported two working calculators as broken
    for exactly this reason."""
    widget, bus, _reader, molecule, _versions = panel
    _land(
        bus,
        _report(
            ALPHA,
            "Alpha",
            molecule.uuid,
            cache_state=CacheState.FAILED,
            inapplicable=True,
            error="no group for a ring tertiary amine",
        ),
    )
    chip = _chip(widget, ALPHA)
    assert chip.text().endswith("Not applicable")
    assert _FAILURE_STYLE not in chip.styleSheet()
    assert _INFORMATION_STYLE in chip.styleSheet()


def test_an_editing_molecule_turns_a_result_stale_on_the_chip(panel):
    widget, bus, _reader, molecule, versions = panel
    _land(bus, _report(ALPHA, "Alpha", molecule.uuid, version=0))
    assert _chip(widget, ALPHA).text().endswith("Ready")

    versions.version = 4
    widget._refresh_reader()
    chip = _chip(widget, ALPHA)
    assert chip.text().endswith("Stale")
    assert _WARNING_STYLE in chip.styleSheet()


def test_a_calculator_whose_result_is_filed_elsewhere_CLAIMS_NOTHING(panel):
    """**THE AWKWARD CASE, AND BOTH TEMPTING ANSWERS ARE LIES.**

    Two of the sixty publish under a name that is not their own --
    `nmr_database` publishes `nmr_13c`, `gasteiger_charge_at_ph` publishes
    `gasteiger_charge` -- and no result type carries a `calculator_id`, so
    this panel cannot attribute one. "Not run" for something somebody just
    ran is the plausible-looking lie; "Ready" asserts a success
    `CalculationFinished` does not promise, being published in a `finally`
    that fires for a calculator which failed or raised.

    So the chip is REMOVED: an absence of a claim rather than a false one.
    """
    widget, bus, _reader, molecule, _versions = panel
    bus.publish(CalculationFinished(calculator_id=ALPHA, molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    # Its answer, filed under a name that is not its own.
    _land(bus, _report("alpha_spectrum", "Alpha Spectrum", molecule.uuid))

    assert widget._result_for(ALPHA) is None, "setup: nothing is filed under its id"
    assert _chip(widget, ALPHA).isHidden()
    # ...and a calculator nobody asked for still says so.
    assert _chip(widget, BETA).text() == "Not run"
    assert not _chip(widget, BETA).isHidden()
