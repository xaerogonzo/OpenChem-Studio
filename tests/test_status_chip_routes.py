"""Pressing a "Needs input" or "Needs setup" chip goes to where the thing is done.

Those two states are instructions -- enter these values, configure this tool -- so a press
used to land in a reader that could only describe them. Now "Needs input" opens the
calculator's settings with the missing values named and the cursor on the first, "Needs
setup" opens Settings > External Tools on the right tab, and "Run selected" (which uses
defaults) skips a calculator that has no usable default and says what it wants.

The settings dialog and the signal are exercised for real; only `exec()` is replaced,
because a modal loop cannot run in a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QLabel

import openchem.ui.panels.property_panel as property_panel_module
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.refusal_kinds import (
    INPUT_REQUIRED,
    SIDECAR_NOT_CONFIGURED,
    InputProblem,
    MissingInput,
    RefusalKind,
    refusal_parameters,
)
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.dialogs.calculator_settings_dialog import (
    CalculatorSettingsDialog,
    needed_input_phrases,
)
from openchem.ui.panels.property_panel import SETUP_TOOL_FOR_CALCULATOR, PropertyPanel
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose

DENSITY = CalculatorParameter(
    name="density", label="Loading density (g/cm³) — required", kind="float", default=0.0,
    minimum=0.0, maximum=3.0, required=True,
)
ENTHALPY = CalculatorParameter(
    name="enthalpy", label="Enthalpy of formation (kcal/mol) — required, measured", kind="float",
    default=-1000.0, minimum=-1000.0, maximum=500.0, required=True,
)
PLACES = CalculatorParameter(name="places", label="Decimal places", kind="int", default=2, minimum=0, maximum=6)

NEEDS = "needs_a_number"
SETUP = "solubility"  # a real id in SETUP_TOOL_FOR_CALCULATOR
PLAIN = "plain"


def _definition(calculator_id: str, parameters=()) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.replace("_", " ").title(),
        category="topology",
        description="Fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
        parameters=list(parameters),
    )


def _refusal(report_id, uuid, code, kind, missing=()) -> ReportResult:
    return ReportResult(
        molecule_uuid=uuid, report_id=report_id, name=report_id, category="topology",
        facts=(Fact(category=FactCategory.TOPOLOGY, label="x", value=1, display_value="1",
                    source="test", basis=Basis.DETERMINISTIC),),
        cache_state=CacheState.FAILED, inapplicable=False, error="refused",
        provenance=Provenance(created_by="core", method=report_id,
                              parameters=refusal_parameters(code, kind, tuple(missing))),
    )


class _RecordingSettings:
    """Stands in for the modal settings dialog: records what it was built with."""

    built: list[dict] = []

    def __init__(self, definition, parent=None, *, molecules=(), needed=()):
        self.real = CalculatorSettingsDialog(definition, parent, molecules=molecules, needed=needed)
        type(self).built.append({"definition": definition, "needed": tuple(needed), "dialog": self.real})

    def exec(self):
        return QDialog.DialogCode.Rejected  # the person cancels: nothing may run

    def parameters(self):
        return {}


@pytest.fixture
def rig(qapp, monkeypatch):
    _RecordingSettings.built = []
    monkeypatch.setattr(property_panel_module, "CalculatorSettingsDialog", _RecordingSettings)
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_definition(NEEDS, [PLACES, DENSITY, ENTHALPY]))
    registry.register(_definition(SETUP, [PLACES]))
    registry.register(_definition(PLAIN, [PLACES]))
    calls: list = []
    service = DescriptorService(bus, engine, calculator_registry=registry)
    monkeypatch.setattr(service, "run_calculator", lambda model, request: calls.append(request))
    panel = PropertyPanel(bus, registry, service, engine)
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    panel.set_project(ProjectModel(molecules=[molecule]))
    reader = ResultsView()
    panel.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    yield panel, bus, molecule, calls, reader
    dispose(reader)
    dispose(panel)


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def _notice(dialog):
    """The "Needs: ..." line above the form, or None when the dialog has none."""
    found = [w for w in dialog.findChildren(QLabel) if w.objectName() == "calculatorNeededInputs"]
    return found[0] if found else None


def _needs_input(bus, molecule, missing):
    _land(bus, _refusal(NEEDS, molecule.uuid, INPUT_REQUIRED, RefusalKind.NEEDS_INPUT, missing))


def test_a_needs_input_chip_opens_the_settings_with_the_missing_values_named(rig):
    panel, bus, molecule, calls, _reader = rig
    _needs_input(bus, molecule, [MissingInput("density", "g/cm³"), MissingInput("enthalpy", "kcal/mol")])
    chip = panel._calculator_status[NEEDS]
    assert chip.text().endswith("Needs input")

    chip.click()

    assert len(_RecordingSettings.built) == 1, "the settings dialog opened"
    built = _RecordingSettings.built[0]
    assert [m.parameter for m in built["needed"]] == ["density", "enthalpy"]
    assert calls == [], "opening the dialog computes nothing"


def test_the_dialog_says_what_it_needs_and_puts_the_cursor_on_the_first(qapp):
    definition = _definition(NEEDS, [PLACES, DENSITY, ENTHALPY])
    dialog = CalculatorSettingsDialog(
        definition, molecules=(), needed=[MissingInput("density", "g/cm³"), MissingInput("enthalpy")]
    )
    notice = _notice(dialog)
    assert "Loading density (g/cm³)" in notice.text()
    assert "Enthalpy of formation (kcal/mol)" in notice.text()
    assert "required" not in notice.text(), "the label's own gloss is not said twice"
    assert dialog.focus_parameter == "density"


def test_a_dialog_opened_by_the_calculators_own_button_has_no_needs_line(qapp):
    dialog = CalculatorSettingsDialog(_definition(NEEDS, [DENSITY]))
    assert _notice(dialog) is None
    assert dialog.focus_parameter is None


def test_units_are_not_said_twice_when_the_two_spell_them_differently():
    """Seen in the photographed dialog: 'Loading density (g/cm³) (g/cm3)'. The label
    spells the unit with a superscript and the refusal, which reaches ASCII-only places,
    does not, so comparing the strings appended both."""
    definition = _definition(NEEDS, [DENSITY])
    [phrase] = needed_input_phrases(definition, [MissingInput("density", "g/cm3")])
    assert phrase == "Loading density (g/cm³)"


def test_units_come_from_the_refusal_when_the_label_has_none():
    bare = CalculatorParameter(name="x", label="Reference energy", kind="float", default=0.0, required=True)
    [phrase] = needed_input_phrases(_definition(NEEDS, [bare]), [MissingInput("x", "kcal/mol")])
    assert phrase == "Reference energy (kcal/mol)"


def test_problems_are_worded_apart():
    definition = _definition(NEEDS, [DENSITY, ENTHALPY])
    phrases = needed_input_phrases(
        definition,
        [
            MissingInput("density", "g/cm³", InputProblem.INVALID),
            MissingInput("enthalpy", "kcal/mol", InputProblem.OUT_OF_DOMAIN),
            MissingInput("no_such_parameter"),
        ],
    )
    assert len(phrases) == 2, "a name the dialog does not have is skipped, not invented"
    assert "cannot be used" in phrases[0]
    assert "outside the range" in phrases[1]


def test_the_tooltip_names_what_is_needed_and_says_nothing_runs(rig):
    panel, bus, molecule, _calls, _reader = rig
    _needs_input(bus, molecule, [MissingInput("density", "g/cm³")])
    tip = panel._calculator_status[NEEDS].toolTip()
    assert "Needs: Loading density (g/cm³)" in tip
    assert "nothing runs until you confirm" in tip


def test_a_needs_setup_chip_asks_for_the_tools_tab_and_does_not_open_the_reader(rig):
    panel, bus, molecule, _calls, reader = rig
    asked: list[str] = []
    panel.tool_setup_requested.connect(asked.append)
    _land(bus, _refusal(SETUP, molecule.uuid, SIDECAR_NOT_CONFIGURED, RefusalKind.NEEDS_SETUP))
    chip = panel._calculator_status[SETUP]
    assert chip.text().endswith("Needs setup")

    chip.click()

    assert asked == [SETUP_TOOL_FOR_CALCULATOR[SETUP]]
    assert reader.focus() == "", "the reader was not the destination"


def test_a_needs_setup_calculator_with_no_known_tool_falls_through_to_the_reader(rig):
    """The routing must never make a press do nothing: an id the table does not know
    is served by the reader, as every press was before."""
    panel, bus, molecule, _calls, reader = rig
    asked: list[str] = []
    panel.tool_setup_requested.connect(asked.append)
    _land(bus, _refusal(PLAIN, molecule.uuid, SIDECAR_NOT_CONFIGURED, RefusalKind.NEEDS_SETUP))

    panel._calculator_status[PLAIN].click()

    assert asked == []
    assert reader.focus() == PLAIN


def test_a_ready_result_still_goes_to_the_reader(rig):
    panel, bus, molecule, _calls, reader = rig
    _land(bus, ReportResult(
        molecule_uuid=molecule.uuid, report_id=PLAIN, name=PLAIN, category="topology",
        facts=(Fact(category=FactCategory.TOPOLOGY, label="x", value=1, display_value="1",
                    source="test", basis=Basis.DETERMINISTIC),),
    ))
    panel._calculator_status[PLAIN].click()
    assert reader.focus() == PLAIN
    assert _RecordingSettings.built == []


def test_run_selected_skips_a_calculator_with_no_usable_default_and_says_what_it_wants(rig):
    panel, _bus, _molecule, calls, _reader = rig
    for calculator_id in (NEEDS, PLAIN):
        panel._calculator_ticks[calculator_id].setChecked(True)

    panel._on_run_selected()

    assert [c.calculator_id for c in calls] == [PLAIN], "only the one that can run on defaults"
    status = panel._batch_status.text()
    assert "Skipped, needs your input" in status
    assert "Loading density (g/cm³)" in status
    assert "Enthalpy of formation (kcal/mol)" in status
    assert "required" not in status


def test_run_selected_with_only_a_required_calculator_does_not_claim_it_is_already_running(rig):
    panel, _bus, _molecule, calls, _reader = rig
    panel._calculator_ticks[NEEDS].setChecked(True)

    panel._on_run_selected()

    assert calls == []
    assert "already running" not in panel._batch_status.text()
    assert "Skipped, needs your input" in panel._batch_status.text()


# --- the table is kept honest by the census -----------------------------------------------


def test_the_setup_table_is_exactly_the_calculators_the_census_saw_need_setup():
    """A seventh calculator that answers NEEDS_SETUP must say where its chip goes, and a
    calculator that stopped answering it must leave the table."""
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "calculator_census_baseline.json").read_text(encoding="utf-8")
    )
    needing_setup = {calculator for calculator, cells in baseline["matrix"].items() if "S" in cells}
    assert set(SETUP_TOOL_FOR_CALCULATOR) == needing_setup


def test_every_setup_target_is_a_real_external_tools_tab():
    from openchem.ui.dialogs import external_tool_catalog as catalog

    keys = {
        catalog.vina().key, catalog.orca().key, catalog.pkasolver().key,
        catalog.admet().key, catalog.java().key, catalog.nmr_database().key,
    }
    assert set(SETUP_TOOL_FOR_CALCULATOR.values()) <= keys


def test_every_named_missing_input_is_a_required_parameter_of_its_calculator():
    """A refusal that names a field the calculator does not mark required would let
    "Run selected" run it on defaults and earn a chip nobody asked for."""
    from openchem.chem import energetics
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    detonation = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "detonation")
    required = {p.name for p in detonation.parameters if p.required}
    for name, _units in energetics.DETONATION_INPUTS.values():
        assert name in required


def test_alignment_and_lewis_name_the_field_that_is_empty():
    from openchem.chem.alignment import compute_3d_alignment
    from openchem.chem.lewis_adduct import compute_lewis_adduct
    from openchem.domain.refusal_kinds import missing_inputs_of, refusal_kind_of_result
    from rdkit import Chem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    for compute, parameter in ((compute_3d_alignment, "reference_smiles"), (compute_lewis_adduct, "partner_smiles")):
        result = compute(mol, "u", {})
        assert refusal_kind_of_result(result) is RefusalKind.NEEDS_INPUT
        assert [m.parameter for m in missing_inputs_of(result)] == [parameter]
