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
from openchem.domain.result_store import ResultIdentity, StoredResult, result_id_of
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.events.events import (
    CalculationFinished,
    MoleculeSelected,
    RecalculationDue,
    ReportComputed,
    ResultRecorded,
    SpectrumComputed,
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


def _definition(calculator_id: str, display_name: str, **extra) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=display_name,
        category="topology",
        description=f"{display_name}. Runs nothing in this fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
        **extra,
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


def _spectrum(spectrum_type: str, uuid: str) -> NMRSpectrumResult:
    return NMRSpectrumResult(
        spectrum_type=spectrum_type, name="Alpha Spectrum", units="ppm", method="lookup",
        molecule_uuid=uuid, values={0: 18.0}, elements={0: "C"},
    )


def _produce(bus, result, producer, molecule_uuid):
    """What the dispatcher publishes: the result, then the envelope that alone names the producer."""
    bus.publish(SpectrumComputed(spectrum=result))
    QCoreApplication.processEvents()
    identity = ResultIdentity(
        molecule_uuid=molecule_uuid, result_id=result_id_of(result), calculation_input="drawing",
        input_fingerprint="f", producer=producer,
    )
    bus.publish(ResultRecorded(stored=StoredResult(identity=identity, result=result)))
    QCoreApplication.processEvents()


def test_a_result_filed_elsewhere_is_attributed_by_the_producer_the_record_carries(panel):
    """The case the test above leaves anonymous, once the dispatcher has said who made it.

    `ResultRecorded` is published after the result and carries the PRODUCER, so the chip no
    longer has to guess from a name: Ready (not Stale -- the summary carries the structure
    revision the raw spectrum does not), openable, and pressing it opens the entry the result
    is actually filed under (`alpha_spectrum`, not `alpha`)."""
    widget, bus, _reader, molecule, _versions = panel
    _produce(bus, _spectrum("alpha_spectrum", molecule.uuid), ALPHA, molecule.uuid)
    bus.publish(CalculationFinished(calculator_id=ALPHA, molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()

    chip = _chip(widget, ALPHA)
    assert not chip.isHidden()
    assert chip.text().endswith("Ready"), chip.text()
    assert chip.isEnabled()
    assert widget._reader_focus_for(ALPHA, widget._result_for(ALPHA)) == "alpha_spectrum"
    # Another calculator's chip is untouched by a result that is not its own.
    assert _chip(widget, BETA).text() == "Not run"


def test_a_later_producer_of_the_same_name_takes_the_result_away_from_the_first(panel):
    """`nmr_13c` is what several producers file under. When another one replaces the entry, the
    first calculator has no result to show -- not the other's."""
    widget, bus, _reader, molecule, _versions = panel
    _produce(bus, _spectrum("alpha_spectrum", molecule.uuid), ALPHA, molecule.uuid)
    assert widget._result_for(ALPHA) is not None
    _produce(bus, _spectrum("alpha_spectrum", molecule.uuid), BETA, molecule.uuid)
    assert widget._result_for(ALPHA) is None
    assert widget._result_for(BETA) is not None


def test_a_record_for_another_molecule_or_an_unregistered_producer_attributes_nothing(panel):
    widget, bus, _reader, molecule, _versions = panel
    result = _spectrum("alpha_spectrum", molecule.uuid)
    _produce(bus, result, ALPHA, "some-other-molecule")
    _produce(bus, result, "descriptor_provider_not_a_calculator", molecule.uuid)
    assert widget._produced_results == {}
    # A producer that files under its own id is already answered by `_reports`.
    _produce(bus, _spectrum(BETA, molecule.uuid), BETA, molecule.uuid)
    assert widget._produced_results == {}


def test_a_new_selection_forgets_who_produced_what(panel):
    widget, bus, _reader, molecule, _versions = panel
    _produce(bus, _spectrum("alpha_spectrum", molecule.uuid), ALPHA, molecule.uuid)
    assert ALPHA in widget._produced_results
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    assert widget._produced_results == {}


GAMMA = "gamma"
GAMMA_REASON = "Gamma has no group for an oxygen."


@pytest.fixture
def preflight_panel(qapp):
    """A panel whose calculator `gamma` declares a pre-flight that refuses anything with an oxygen."""
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(
        _definition(
            GAMMA, "Gamma",
            preflight=lambda mol: GAMMA_REASON if any(a.GetSymbol() == "O" for a in mol.GetAtoms()) else "",
        )
    )
    widget = PropertyPanel(
        bus, registry, DescriptorService(bus, engine, calculator_registry=registry), engine,
        structure_version_of=_Versions(),
    )
    ethanol = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(ethanol, "CCO")
    ethane = MoleculeModel(display_name="Ethane")
    engine.set_structure_from_smiles(ethane, "CC")
    widget.set_project(ProjectModel(molecules=[ethanol, ethane]))
    yield widget, bus, engine, ethanol, ethane
    dispose(widget)


def test_a_pre_flight_refusal_is_on_the_chip_before_anything_runs(preflight_panel):
    """Joback's case: the structure is outside the method's groups, and that is knowable now.

    "Not applicable", disabled (there is no result to open), and the tooltip says it was known
    before a run and why. The molecule that passes the hook still reads "Not run"."""
    widget, bus, _engine, ethanol, ethane = preflight_panel
    bus.publish(MoleculeSelected(molecule_uuid=ethanol.uuid))
    QCoreApplication.processEvents()
    chip = _chip(widget, GAMMA)
    assert not chip.isHidden()
    assert chip.text().endswith("Not applicable"), chip.text()
    assert not chip.isEnabled()
    assert GAMMA_REASON in chip.toolTip() and "before running" in chip.toolTip()

    bus.publish(MoleculeSelected(molecule_uuid=ethane.uuid))
    QCoreApplication.processEvents()
    assert chip.text() == "Not run"
    assert GAMMA_REASON not in chip.toolTip()


def test_a_pre_flight_claim_follows_an_edit_and_never_outranks_a_result(preflight_panel):
    widget, bus, engine, ethanol, _ethane = preflight_panel
    bus.publish(MoleculeSelected(molecule_uuid=ethanol.uuid))
    QCoreApplication.processEvents()
    assert _chip(widget, GAMMA).text().endswith("Not applicable")
    # Drawn into a molecule without oxygen: the claim goes.
    engine.set_structure_from_smiles(ethanol, "CC")
    bus.publish(RecalculationDue(molecule_uuid=ethanol.uuid))
    QCoreApplication.processEvents()
    assert _chip(widget, GAMMA).text() == "Not run"
    # And a real result is what the chip reports, whatever the hook said.
    widget._preflight_reasons[GAMMA] = GAMMA_REASON
    _land(bus, _report(GAMMA, "Gamma", ethanol.uuid))
    assert _chip(widget, GAMMA).text().endswith("Ready")
