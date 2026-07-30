from __future__ import annotations

from PySide6.QtWidgets import QDialog

import openchem.ui.panels.property_panel as property_panel_module
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    CalculationRequest,
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, MoleculeSelected, PerAtomDataComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import PropertyPanel


def _descriptor(**overrides) -> DescriptorValue:
    defaults = dict(
        descriptor_id="mol_wt",
        name="Molecular Weight",
        units="g/mol",
        category="physicochemical",
        provider="rdkit",
        molecule_uuid="mol-1",
        value=78.11,
        cache_state=CacheState.COMPLETED,
    )
    defaults.update(overrides)
    return DescriptorValue(**defaults)


class _FakeDescriptorService:
    """Records run_calculator calls instead of scheduling real QRunnable
    work -- these tests are about PropertyPanel's own wiring, not
    DescriptorService's (already covered in test_descriptor_service.py)."""

    def __init__(self) -> None:
        self.calls: list[tuple[MoleculeModel, CalculationRequest]] = []

    def run_calculator(self, model: MoleculeModel, request: CalculationRequest) -> None:
        self.calls.append((model, request))


def _make_panel(qapp, calculator_registry: CalculatorRegistry | None = None):
    bus = EventBus()
    registry = calculator_registry if calculator_registry is not None else CalculatorRegistry()
    descriptor_service = _FakeDescriptorService()
    engine = ChemistryEngine()
    panel = PropertyPanel(bus, registry, descriptor_service, engine)
    return panel, bus, descriptor_service


def test_same_bare_descriptor_id_from_different_providers_does_not_collide(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="value",
                name="From RDKit",
                units="",
                category="",
                provider="rdkit",
                molecule_uuid="mol-1",
                value=1,
                cache_state=CacheState.COMPLETED,
            )
        )
    )
    bus.publish(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="value",
                name="From Plugin",
                units="",
                category="",
                provider="myplugin",
                molecule_uuid="mol-1",
                value=2,
                cache_state=CacheState.COMPLETED,
            )
        )
    )

    assert len(panel._value_labels) == 2


def test_descriptor_creates_a_section_for_its_category(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(category="shape", descriptor_id="pbf")))

    assert "shape" in panel._sections
    # Widgets never get shown in these headless construction-only tests, so
    # QWidget.isVisible() always reports False regardless of section state
    # (it requires the whole ancestor chain, including a shown top-level
    # window, to be real) -- the toggle button's checked state is this
    # section's actual logical expanded/collapsed source of truth.
    assert panel._sections["shape"]._toggle_button.isChecked() is False  # not in the default-expanded set


def test_default_expanded_categories_start_visible(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(category="physicochemical")))

    assert panel._sections["physicochemical"]._toggle_button.isChecked() is True


def test_boolean_descriptor_renders_as_pass_fail(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        DescriptorComputed(
            descriptor=_descriptor(
                descriptor_id="lipinski_pass", category="medicinal_chemistry", value=True, units=""
            )
        )
    )
    pass_label = panel._value_labels[("rdkit", "lipinski_pass")]
    assert pass_label.text() == "Pass"

    bus.publish(
        DescriptorComputed(
            descriptor=_descriptor(
                descriptor_id="ghose_pass", category="medicinal_chemistry", value=False, units=""
            )
        )
    )
    fail_label = panel._value_labels[("rdkit", "ghose_pass")]
    assert fail_label.text() == "Fail"


def test_failed_descriptor_shows_error_message(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        DescriptorComputed(
            descriptor=_descriptor(
                descriptor_id="pbf",
                category="shape",
                value=None,
                cache_state=CacheState.FAILED,
                error="Needs a real 3D conformer.",
            )
        )
    )

    label = panel._value_labels[("rdkit", "pbf")]
    assert label.text() == "Needs a real 3D conformer."


def test_alert_computed_shows_clean_when_nothing_matched(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid="mol-1",
                matched=[],
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "pains")]
    assert label.text() == "Clean"
    assert "medicinal_chemistry" in panel._sections


def test_alert_computed_lists_matches(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid="mol-1",
                matched=["rhod_sat_A(33)"],
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "pains")]
    assert "rhod_sat_A(33)" in label.text()


def test_selecting_a_new_molecule_clears_previous_rows(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    bus.publish(DescriptorComputed(descriptor=_descriptor()))
    assert len(panel._value_labels) == 1

    bus.publish(MoleculeSelected(molecule_uuid="mol-2"))
    assert len(panel._value_labels) == 0


def test_a_descriptor_whose_category_changes_moves_to_the_new_section(qapp):
    """Regression test for the category-bucketing bug: a placeholder
    published with one category (e.g. "" before the real category was
    known) must not permanently strand the row in that section once a
    later event for the same (provider, descriptor_id) reports the real
    one."""
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(category="", cache_state=CacheState.QUEUED, value=None)))
    assert panel._row_sections[("rdkit", "mol_wt")] is panel._sections["other"]

    bus.publish(DescriptorComputed(descriptor=_descriptor(category="physicochemical")))

    assert panel._row_sections[("rdkit", "mol_wt")] is panel._sections["physicochemical"]
    label = panel._value_labels[("rdkit", "mol_wt")]
    assert label.text() == "78.11"
    # The row must appear exactly once in the new section's layout, not
    # duplicated, and must be gone from the old one.
    assert panel._sections["physicochemical"].content_layout().rowCount() == 1
    assert panel._sections["other"].content_layout().rowCount() == 0


def test_descriptor_for_a_different_molecule_is_ignored(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(molecule_uuid="mol-2")))

    assert len(panel._value_labels) == 0


# --- Phase 18: CalculatorRegistry integration --------------------------------


def _calculator_definition(calculator_id: str, category: str, parameters=None) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.replace("_", " ").title(),
        category=category,
        description="test calculator",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        parameters=parameters or [],
    )


def _service_calculator_definition(calculator_id: str, category: str) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.replace("_", " ").title(),
        category=category,
        description="run from its own panel",
        execution=ServiceExecution(service_name="some_service", panel_name="Some Panel"),
    )


def test_a_registered_category_gets_a_section_eagerly_even_with_no_scalar_descriptor(qapp):
    """Regression test: pKa has no scalar descriptor to otherwise trigger
    section creation via _on_descriptor_computed -- the section (and its
    "Open pKa..." button) must still exist right after construction."""
    registry = CalculatorRegistry()
    registry.register(_calculator_definition("pka", category="pka"))

    panel, _bus, _service = _make_panel(qapp, registry)

    assert "pka" in panel._sections


def test_section_gets_one_open_button_per_registered_calculator_in_its_category(qapp):
    registry = CalculatorRegistry()
    registry.register(_calculator_definition("calc_a", category="charge"))
    registry.register(_calculator_definition("calc_b", category="charge"))

    panel, _bus, _service = _make_panel(qapp, registry)

    section = panel._sections["charge"]
    assert section._calculators_layout.count() == 2


def test_a_service_execution_only_category_gets_no_section(qapp):
    """Phase 21: Docking/QuantumChemistry are registered for discovery only
    (ServiceExecution) -- an all-external category must not produce an
    empty, unusable section in a per-molecule panel that has no generic
    way to run them."""
    registry = CalculatorRegistry()
    registry.register(_service_calculator_definition("docking.vina", category="docking"))

    panel, _bus, _service = _make_panel(qapp, registry)

    assert "docking" not in panel._sections


def test_a_mixed_category_gets_exactly_one_open_button_for_the_registry_calculator(qapp):
    """A category with one ServiceExecution and one RegistryExecution
    calculator gets a section (since it has a runnable entry), but only
    ONE "Open..." row -- proves the external skip is targeted, not
    accidentally hiding the whole category."""
    registry = CalculatorRegistry()
    registry.register(_service_calculator_definition("orca.sp", category="quantum_chemistry"))
    registry.register(_calculator_definition("runnable_calc", category="quantum_chemistry"))

    panel, _bus, _service = _make_panel(qapp, registry)

    assert "quantum_chemistry" in panel._sections
    section = panel._sections["quantum_chemistry"]
    assert section._calculators_layout.count() == 1


def test_clicking_open_on_a_zero_parameter_calculator_runs_it_directly(qapp):
    registry = CalculatorRegistry()
    definition = _calculator_definition("crippen_logp_contrib", category="logp")
    registry.register(definition)

    panel, bus, service = _make_panel(qapp, registry)
    molecule = MoleculeModel(display_name="Ethanol")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    panel._open_calculator(definition)

    assert len(service.calls) == 1
    called_model, request = service.calls[0]
    assert called_model is molecule
    assert request.calculator_id == "crippen_logp_contrib"
    assert request.parameters == {}
    assert panel._pending_calculator_id == "crippen_logp_contrib"


def test_clicking_open_with_no_project_or_selection_is_a_no_op(qapp):
    registry = CalculatorRegistry()
    definition = _calculator_definition("crippen_logp_contrib", category="logp")
    registry.register(definition)
    panel, _bus, service = _make_panel(qapp, registry)

    panel._open_calculator(definition)  # no project set, no molecule selected

    assert service.calls == []


def test_clicking_open_on_a_parameterized_calculator_uses_the_settings_dialog(qapp, monkeypatch):
    registry = CalculatorRegistry()
    definition = _calculator_definition(
        "gasteiger_charge_at_ph",
        category="charge",
        parameters=[CalculatorParameter(name="pH", label="pH", kind="float", default=7.4)],
    )
    registry.register(definition)

    class _FakeSettingsDialog:
        def __init__(self, definition, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def parameters(self):
            return {"pH": 2.0}

    monkeypatch.setattr(property_panel_module, "CalculatorSettingsDialog", _FakeSettingsDialog)

    panel, bus, service = _make_panel(qapp, registry)
    molecule = MoleculeModel(display_name="Acetic acid")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    panel._open_calculator(definition)

    assert len(service.calls) == 1
    _called_model, request = service.calls[0]
    assert request.parameters == {"pH": 2.0}


def test_cancelling_the_settings_dialog_does_not_run_the_calculator(qapp, monkeypatch):
    registry = CalculatorRegistry()
    definition = _calculator_definition(
        "gasteiger_charge_at_ph",
        category="charge",
        parameters=[CalculatorParameter(name="pH", label="pH", kind="float", default=7.4)],
    )
    registry.register(definition)

    class _FakeCancelledDialog:
        def __init__(self, definition, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(property_panel_module, "CalculatorSettingsDialog", _FakeCancelledDialog)

    panel, bus, service = _make_panel(qapp, registry)
    molecule = MoleculeModel(display_name="Acetic acid")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    panel._open_calculator(definition)

    assert service.calls == []


def test_matching_result_opens_the_inspector_and_clears_pending(qapp, monkeypatch):
    opened = []

    class _FakeInspectorDialog:
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None):
            opened.append((molecule, result))

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(property_panel_module, "CalculatorInspectorDialog", _FakeInspectorDialog)

    panel, bus, _service = _make_panel(qapp)
    molecule = MoleculeModel(display_name="Ethanol")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    panel._pending_calculator_id = "crippen_logp_contrib"

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution",
                units="",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: 0.1},
            )
        )
    )

    assert len(opened) == 1
    assert opened[0][0] is molecule
    assert panel._pending_calculator_id is None


def test_unrelated_per_atom_data_does_not_open_the_inspector(qapp, monkeypatch):
    """The always-on eager batch publishes PerAtomDataComputed for
    crippen_logp_contrib/crippen_mr_contrib/gasteiger_charge on every
    molecule selection -- without a pending calculator_id, that must NOT
    pop a dialog open on its own."""
    opened = []

    class _FakeInspectorDialog:
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None):
            opened.append(result)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(property_panel_module, "CalculatorInspectorDialog", _FakeInspectorDialog)

    panel, bus, _service = _make_panel(qapp)
    molecule = MoleculeModel(display_name="Ethanol")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    # No _pending_calculator_id set -- simulates the eager batch's own publish.

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="crippen_logp_contrib",
                name="LogP Contribution",
                units="",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: 0.1},
            )
        )
    )

    assert opened == []


# --- Phase 19: ADMET/toxicity -------------------------------------------------


def test_admet_alert_routes_to_the_admet_section(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="brenk",
                name="BRENK (Reactive/Unstable Groups)",
                molecule_uuid="mol-1",
                matched=["aldehyde"],
                provenance=Provenance(created_by="core", method="rdkit"),
                category="admet",
            )
        )
    )

    label = panel._alert_labels[("core", "brenk")]
    assert "aldehyde" in label.text()
    assert "admet" in panel._sections
    assert "medicinal_chemistry" not in panel._sections  # PAINS never published in this test


def test_pains_still_routes_to_medicinal_chemistry_by_default(qapp):
    """Regression guard: AlertResult.category's default must not silently
    change PAINS's existing section."""
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid="mol-1",
                matched=[],
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    assert "medicinal_chemistry" in panel._sections
    assert "admet" not in panel._sections


def test_admet_scalar_descriptor_lands_in_the_admet_section(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(descriptor_id="esol_logs", category="admet", value=-2.09)))

    assert "admet" in panel._sections
    label = panel._value_labels[("rdkit", "esol_logs")]
    assert label.text() == "-2.09"


def test_admet_section_has_no_open_row_since_nothing_is_registered_there(qapp):
    panel, bus, _service = _make_panel(qapp)  # empty CalculatorRegistry
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(descriptor_id="esol_logs", category="admet", value=-2.09)))

    section = panel._sections["admet"]
    assert section._calculators_layout.count() == 0


# --- Phase 20: functional groups + hERG risk factors + extended filters -----


def test_functional_groups_alert_lands_in_admet_section(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="functional_groups",
                name="Functional Groups",
                molecule_uuid="mol-1",
                matched=["Ester (1)", "Benzene Ring (1)"],
                provenance=Provenance(created_by="core", method="rdkit"),
                category="admet",
            )
        )
    )

    assert "admet" in panel._sections
    label = panel._alert_labels[("core", "functional_groups")]
    assert "Ester (1)" in label.text()


def test_herg_risk_factors_alert_lands_in_admet_section(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="herg_risk_factors",
                name="hERG Risk Factors (not a prediction)",
                molecule_uuid="mol-1",
                matched=["Basic amine present"],
                provenance=Provenance(created_by="core", method="rdkit"),
                category="admet",
            )
        )
    )

    label = panel._alert_labels[("core", "herg_risk_factors")]
    assert "Basic amine present" in label.text()


def test_pfizer_gsk_rule_of_three_land_in_medicinal_chemistry(qapp):
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    for descriptor_id in ("pfizer_375_pass", "gsk_400_pass", "rule_of_three_pass"):
        bus.publish(
            DescriptorComputed(
                descriptor=_descriptor(descriptor_id=descriptor_id, category="medicinal_chemistry", value=True)
            )
        )

    for descriptor_id in ("pfizer_375_pass", "gsk_400_pass", "rule_of_three_pass"):
        assert panel._row_sections[("rdkit", descriptor_id)] is panel._sections["medicinal_chemistry"]
