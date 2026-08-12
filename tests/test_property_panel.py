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
    # A glyph as well as the colour: colour alone is invisible to a
    # colour-blind reader and is lost entirely in a copied plain-text
    # export, where "Pass" and "Fail" would otherwise be indistinguishable
    # from any other word.
    assert "Pass" in pass_label.text()
    assert pass_label.text().startswith("✓")

    bus.publish(
        DescriptorComputed(
            descriptor=_descriptor(
                descriptor_id="ghose_pass", category="medicinal_chemistry", value=False, units=""
            )
        )
    )
    fail_label = panel._value_labels[("rdkit", "ghose_pass")]
    assert "Fail" in fail_label.text()
    assert fail_label.text().startswith("✕")


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
    """"Clean" is a VERDICT, and only a catalog is entitled to give one.

    PAINS declares `Severity.WARNING`, so an empty match list really does
    mean "checked, nothing flagged". A report that happens to produce no
    lines has not cleared the molecule of anything -- see
    `test_a_report_with_nothing_to_say_does_not_claim_the_molecule_is_clean`.
    """
    from openchem.domain.structure_issue import Severity

    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid="mol-1",
                matched=[],
                severity=Severity.WARNING,
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "pains")]
    assert "Clean" in label.text()
    assert "medicinal_chemistry" in panel._sections


def test_a_report_with_nothing_to_say_does_not_claim_the_molecule_is_clean(qapp):
    """The other side of the verdict rule. An elemental analysis that
    produced no lines has checked nothing and cleared nothing, so it must
    not borrow the catalogs' green "Clean"."""
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="elemental_analysis",
                name="Elemental Analysis",
                molecule_uuid="mol-1",
                matched=[],
                category="identity",
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "elemental_analysis")]
    assert "Clean" not in label.text()


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


def _hint_texts(section) -> list[str]:
    from PySide6.QtWidgets import QLabel

    layout = section._calculators_layout
    return [
        layout.itemAt(i).widget().text()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), QLabel)
    ]


def test_empirical_only_section_points_at_its_ab_initio_counterpart(qapp):
    """Phase 23: Alex ran the empirical NMR estimate believing it was the
    real ORCA calculation, because nothing on screen said otherwise. An
    empirical-only section now points at the ab initio counterpart, matched
    on the Phase 21 dotted-calculator_id convention (orca.nmr -> "nmr")
    since the two deliberately live in different categories."""
    registry = CalculatorRegistry()
    empirical = CalculatorDefinition(
        calculator_id="nmr_empirical", display_name="NMR Shift", category="nmr",
        description="", execution=RegistryExecution(compute=lambda m, u, p: None),
        prediction_basis="empirical",
    )
    ab_initio = CalculatorDefinition(
        calculator_id="orca.nmr", display_name="NMR", category="quantum_chemistry",
        description="", execution=ServiceExecution(
            service_name="quantum_chemistry_service", panel_name="Quantum Chemistry panel"
        ),
        prediction_basis="ab_initio",
    )
    registry.register(empirical)
    registry.register(ab_initio)

    panel, _bus, _service = _make_panel(qapp, registry)

    hints = _hint_texts(panel._sections["nmr"])
    assert len(hints) == 1
    assert "empirical" in hints[0]
    assert "Quantum Chemistry panel" in hints[0]


def test_no_hint_when_there_is_no_ab_initio_counterpart(qapp):
    registry = CalculatorRegistry()
    registry.register(
        CalculatorDefinition(
            calculator_id="nmr_empirical", display_name="NMR Shift", category="nmr",
            description="", execution=RegistryExecution(compute=lambda m, u, p: None),
            prediction_basis="empirical",
        )
    )

    panel, _bus, _service = _make_panel(qapp, registry)

    assert _hint_texts(panel._sections["nmr"]) == []


def test_no_hint_for_a_section_that_is_not_empirical(qapp):
    """Charge/LogP/pKa have no prediction_basis set -- they must not grow a
    hint just because an ab initio calculator exists somewhere."""
    registry = CalculatorRegistry()
    registry.register(_calculator_definition("gasteiger_charge_at_ph", category="charge"))
    registry.register(
        CalculatorDefinition(
            calculator_id="orca.charge", display_name="QM Charge", category="quantum_chemistry",
            description="", execution=ServiceExecution(
                service_name="quantum_chemistry_service", panel_name="Quantum Chemistry panel"
            ),
            prediction_basis="ab_initio",
        )
    )

    panel, _bus, _service = _make_panel(qapp, registry)

    assert _hint_texts(panel._sections["charge"]) == []


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


def test_clicking_open_with_no_selection_says_so_instead_of_doing_nothing(qapp):
    """It still runs nothing -- but it no longer runs nothing SILENTLY.

    A button that produces no dialog, no message and no log line is
    indistinguishable from a broken one, which is the same complaint as
    "I can hit run on several things and nothing noticeable happens".
    """
    registry = CalculatorRegistry()
    definition = _calculator_definition("crippen_logp_contrib", category="logp")
    registry.register(definition)
    panel, _bus, service = _make_panel(qapp, registry)

    panel._open_calculator(definition)  # no project set, no molecule selected

    assert service.calls == []
    assert "Select a molecule" in panel._batch_status.text()


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
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None, **kwargs):
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


def test_matching_spectrum_result_opens_the_nmr_view_and_clears_pending(qapp, monkeypatch):
    """Phase 22: a RegistryExecution calculator can return a SpectrumResult
    (the empirical NMR estimator) instead of a PerAtomDataset -- matched
    by spectrum_type against _pending_calculator_id the same way
    property_id is matched for PerAtomDataComputed.

    Phase 23c: a spectrum now opens the dedicated NMR view rather than the
    generic Calculator Inspector, whose one-colour-per-atom layout has
    nowhere to put grouped signals, integrations and multiplicities.
    """
    from openchem.domain.scientific_result import NMRSpectrumResult
    from openchem.events.events import SpectrumComputed

    opened = []
    inspector_opened = []

    class _FakeNmrViewDialog:
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None, **kwargs):
            opened.append((molecule, result))

        def exec(self):
            return QDialog.DialogCode.Accepted

    class _FakeInspectorDialog:
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None):
            inspector_opened.append(result)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(property_panel_module, "NmrViewDialog", _FakeNmrViewDialog)
    monkeypatch.setattr(property_panel_module, "CalculatorInspectorDialog", _FakeInspectorDialog)

    panel, bus, _service = _make_panel(qapp)
    molecule = MoleculeModel(display_name="Ethanol")
    project = ProjectModel(molecules=[molecule])
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    panel._pending_calculator_id = "nmr_empirical"

    bus.publish(
        SpectrumComputed(
            spectrum=NMRSpectrumResult(
                spectrum_type="nmr_empirical",
                name="NMR Shift",
                units="ppm",
                method="smarts_lookup",
                molecule_uuid=molecule.uuid,
                values={0: 1.4},
            )
        )
    )

    assert len(opened) == 1
    assert opened[0][0] is molecule
    assert inspector_opened == []
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


def _lewis_registry(*, with_lewis: bool = True) -> CalculatorRegistry:
    registry = CalculatorRegistry()
    registry.register(
        CalculatorDefinition(
            calculator_id="pka", display_name="pKa", category="pka",
            description="", execution=RegistryExecution(compute=lambda m, u, p: None),
        )
    )
    if with_lewis:
        registry.register(
            CalculatorDefinition(
                calculator_id="lewis_sites", display_name="Lewis Sites", category="lewis",
                description="", execution=RegistryExecution(compute=lambda m, u, p: None),
                prediction_basis="empirical",
            )
        )
    return registry


def test_the_pka_section_points_at_the_lewis_section(qapp):
    """The whole reason the Lewis work exists: pKa answers whether
    something gives up a proton, and someone reading "pKa 15, not acidic"
    can reasonably conclude the molecule is unreactive. Carbon monoxide is
    a negligible Bronsted base and forms an isolable adduct with borane."""
    panel, _bus, _service = _make_panel(qapp, _lewis_registry())

    hints = _hint_texts(panel._sections["pka"])
    assert len(hints) == 1
    assert "PROTON" in hints[0]
    assert "Lewis" in hints[0]


def test_no_lewis_pointer_when_nothing_implements_lewis(qapp):
    """A stripped or plugin-reduced registry must not be left pointing at
    a section that does not exist."""
    panel, _bus, _service = _make_panel(qapp, _lewis_registry(with_lewis=False))

    assert _hint_texts(panel._sections["pka"]) == []


def test_the_lewis_section_does_not_point_back_at_pka(qapp):
    """One direction only. The pointer says "this answers a narrower
    question than you think"; the reverse is not true and two sections
    pointing at each other is noise."""
    panel, _bus, _service = _make_panel(qapp, _lewis_registry())

    assert not any("PROTON" in text for text in _hint_texts(panel._sections["lewis"]))


def test_the_lewis_section_points_at_its_ab_initio_counterpart(qapp):
    """Hardness and softness need a real quantum run, and `lewis_hsab` is
    registered so the existing empirical -> ab initio mechanism finds it by
    the shared "lewis" id prefix."""
    registry = _lewis_registry()
    registry.register(
        CalculatorDefinition(
            calculator_id="lewis_hsab", display_name="Hardness / Softness (HSAB)",
            category="lewis", description="",
            execution=ServiceExecution(
                service_name="quantum_chemistry_service", panel_name="Quantum Chemistry panel"
            ),
            prediction_basis="ab_initio",
        )
    )

    panel, _bus, _service = _make_panel(qapp, registry)

    hints = _hint_texts(panel._sections["lewis"])
    assert any("Quantum Chemistry panel" in text for text in hints)


def test_the_real_registry_wires_both_lewis_calculators(qapp):
    """Registered rather than merely defined -- through the real bootstrap,
    since a definition that never reaches the registry is invisible."""
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry
    ids = {d.calculator_id for d in registry.by_category("lewis")}
    assert ids == {"lewis_sites", "lewis_hsab", "lewis_adduct"}


def _long_alert(category: str, alert_id: str):
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import AlertResult
    from openchem.events.events import AlertComputed

    return AlertComputed(alert=AlertResult(
        alert_id=alert_id, name=alert_id, molecule_uuid="m1", category=category,
        matched=[
            "Pi system: 6 atoms, 6 pi electrons",
            "Total pi energy: 8.0000 beta",
            "Orbital energies (beta): +2.0000, +1.0000, +1.0000, -1.0000, -1.0000, -2.0000",
            "Note: simple Huckel treats every pi centre as an identical carbon. This molecule "
            "contains heteroatoms, whose real alpha/beta parameters differ -- densities on "
            "those atoms are indicative only.",
        ],
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(created_by="core", method="x"),
    ))


def _panel_in_a_scroll_area(qapp):
    """The real arrangement: the panel inside a height-limited scroll area,
    which is what MainWindow's `_wrap_scrollable` builds."""
    from PySide6.QtWidgets import QScrollArea
    from openchem.bootstrap import build_service_container

    container = build_service_container()
    panel = PropertyPanel(
        container.event_bus, container.calculator_registry,
        container.descriptor_service, container.chemistry_engine,
    )
    area = QScrollArea()
    area.setWidget(panel)
    area.setWidgetResizable(True)
    area.resize(340, 700)
    area.show()
    container.event_bus.publish(MoleculeSelected(molecule_uuid="m1"))
    return panel, container.event_bus, area


def test_a_long_result_does_not_squeeze_the_calculator_buttons(qapp):
    """A wrapped QLabel claims it needs ONE LINE however much text it has.

    That made the panel under-report its minimum height, so the scroll
    area pinned it to the viewport and the layout squeezed everything
    compressible instead: the "Open [Calculator]..." buttons dropped from
    20 pixels to 13, below their own minimum size hint.

    TWO sections expanded is the smallest case that reproduces it -- with
    one, nothing compresses and this test passes against the bug. See
    `_WrappedLabel` for why all three of its overrides are needed.
    """
    from PySide6.QtWidgets import QPushButton

    panel, bus, _area = _panel_in_a_scroll_area(qapp)
    for category in ("quantum", "lewis"):
        panel._sections[category]._toggle_button.setChecked(True)
    qapp.processEvents()

    bus.publish(_long_alert("quantum", "huckel_analysis"))
    bus.publish(_long_alert("lewis", "lewis_sites"))
    for _ in range(3):
        qapp.processEvents()

    for category in ("quantum", "lewis"):
        # findChildren, not direct layout items: each calculator button now
        # shares a row widget with its "run in a batch" tick box, so it is a
        # grandchild of the layout rather than a child. The guard is about
        # the BUTTON's height either way.
        section = panel._sections[category]
        # Identified by the CALCULATOR ID it carries, not by its label.
        # This used to look for text starting "Open ", which coupled a
        # test about button HEIGHT to the button's wording -- and broke
        # the moment the wording changed, reporting an empty list rather
        # than a squeezed button. The property is what the button is;
        # the text is what it happens to say today.
        heights = [
            button.height()
            for button in section.content.findChildren(QPushButton)
            if button.property("openchem_calculator_id")
        ]
        assert heights, category
        for height in heights:
            assert height >= 20, f"{category} button squeezed to {height}px"



def test_a_long_result_is_not_silently_clipped(qapp):
    """The second half of the same bug, and the worse half: part of a
    result was cut off with nothing to indicate it."""
    from PySide6.QtWidgets import QLabel

    panel, bus, _area = _panel_in_a_scroll_area(qapp)
    for category in ("quantum", "lewis"):
        panel._sections[category]._toggle_button.setChecked(True)
    qapp.processEvents()

    bus.publish(_long_alert("quantum", "huckel_analysis"))
    bus.publish(_long_alert("lewis", "lewis_sites"))
    for _ in range(3):
        qapp.processEvents()

    clipped = [
        label.text()[:40]
        for label in panel.findChildren(QLabel)
        if label.isVisible() and label.wordWrap() and label.width() > 0
        and label.height() < label.heightForWidth(label.width())
    ]
    assert clipped == []



# --- running several calculators at once ------------------------------------


#: Two atoms and no bonds -- enough to be a structure, small enough to
#: read. Used where a test needs a molecule that HAS a molblock.
_MINIMAL_MOLBLOCK = """
  Mrv  

  2  0  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 Na  0  3  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 Cl  0  5  0  0  0  0  0  0  0  0  0  0
M  CHG  2   1   1   2  -1
M  END
"""


class _RecordingService:
    """Records dispatches instead of running anything.

    The engine's concurrency is not under test here -- `run_calculator`
    already dispatches to `QThreadPool.globalInstance()` and always has.
    What is under test is the affordance on top of it.
    """

    def __init__(self) -> None:
        self.requests: list = []

    def run_calculator(self, model, request) -> None:
        self.requests.append(request)

    @property
    def requested_by_the_button(self) -> list:
        """Everything except the identity card's own dispatch.

        The card auto-runs `substance_analysis` on every molecule
        selection, because a header that appears only once somebody ticks
        a box is a result rather than a header. These tests are about the
        Run button, so they say so rather than counting whatever happens
        to be in the list.
        """
        return [r for r in self.requests if r.calculator_id != "substance_analysis"]

    def request_descriptors(self, *args, **kwargs) -> None:
        pass


def _panel_with_recorder(qapp):
    from openchem.bootstrap import build_service_container

    container = build_service_container()
    service = _RecordingService()
    panel = PropertyPanel(
        container.event_bus, container.calculator_registry, service, container.chemistry_engine
    )
    return panel, container.event_bus, service


def _select_molecule(panel, bus):
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel

    model = MoleculeModel(display_name="ethanol", canonical_smiles="CCO")
    panel.set_project(ProjectModel(molecules=[model]))
    bus.publish(MoleculeSelected(molecule_uuid=model.uuid))
    return model


def test_ticking_calculators_enables_running_them_together(qapp):
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)
    assert not panel._run_selected_button.isEnabled()

    chosen = list(panel._calculator_ticks)[:3]
    for calculator_id in chosen:
        panel._calculator_ticks[calculator_id].setChecked(True)

    assert panel._run_selected_button.isEnabled()
    assert "(3)" in panel._run_selected_button.text()

    panel._on_run_selected()
    assert {r.calculator_id for r in service.requested_by_the_button} == set(chosen)


def test_a_batch_run_uses_declared_defaults_and_opens_no_dialog(qapp):
    """Answering six settings dialogs to avoid clicking six buttons is not
    a saving. The per-calculator button is still there for anyone who needs
    non-default settings."""
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)

    with_params = next(
        cid for cid in panel._calculator_ticks
        if panel._calculator_registry.get(cid).parameters
    )
    panel._calculator_ticks[with_params].setChecked(True)
    panel._on_run_selected()

    request = next(r for r in service.requests if r.calculator_id == with_params)
    definition = panel._calculator_registry.get(with_params)
    assert request.parameters == {p.name: p.default for p in definition.parameters}


def test_the_same_calculator_is_not_queued_twice(qapp):
    """The pool would happily run it again and publish two results for one
    molecule."""
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)
    calculator_id = list(panel._calculator_ticks)[0]
    panel._calculator_ticks[calculator_id].setChecked(True)

    panel._on_run_selected()
    panel._on_run_selected()

    assert len(service.requested_by_the_button) == 1
    assert "already running" in panel._batch_status.text()


def test_a_result_arriving_lets_it_run_again(qapp):
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.scientific_result import AlertResult

    panel, bus, service = _panel_with_recorder(qapp)
    model = _select_molecule(panel, bus)
    calculator_id = "lewis_sites"
    panel._calculator_ticks[calculator_id].setChecked(True)
    panel._on_run_selected()

    bus.publish(AlertComputed(alert=AlertResult(
        alert_id=calculator_id, name="Lewis Sites", molecule_uuid=model.uuid,
        matched=["a line"], category="lewis",
        cache_state=CacheState.COMPLETED,
        provenance=Provenance(created_by="core", method="x"))))

    panel._on_run_selected()
    assert len(service.requested_by_the_button) == 2


def test_switching_molecule_clears_a_stuck_run(qapp):
    """Result ids are matched to calculator ids best-effort, so the backstop
    matters: the worst case must be "re-run after switching molecule", not
    "stuck for the session"."""
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)
    calculator_id = list(panel._calculator_ticks)[0]
    panel._calculator_ticks[calculator_id].setChecked(True)
    panel._on_run_selected()
    assert panel._running_calculator_ids

    _select_molecule(panel, bus)
    assert not panel._running_calculator_ids

    panel._on_run_selected()
    assert len(service.requested_by_the_button) == 2


def test_clearing_the_selection_unticks_everything(qapp):
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)
    for calculator_id in list(panel._calculator_ticks)[:2]:
        panel._calculator_ticks[calculator_id].setChecked(True)

    panel._on_clear_selection()

    assert not panel._selected_calculator_ids()
    assert not panel._run_selected_button.isEnabled()


def test_running_with_no_molecule_says_so(qapp):
    panel, _bus, service = _panel_with_recorder(qapp)
    panel._calculator_ticks[list(panel._calculator_ticks)[0]].setChecked(True)
    panel._on_run_selected()
    assert service.requests == []
    assert "Select a molecule" in panel._batch_status.text()


def test_a_batch_run_does_not_pop_open_inspectors(qapp):
    """`_pending_calculator_id` exists to open an inspector when a result
    lands. Six inspectors stacking up is not what anybody asked for."""
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)
    for calculator_id in list(panel._calculator_ticks)[:2]:
        panel._calculator_ticks[calculator_id].setChecked(True)

    panel._on_run_selected()

    assert panel._pending_calculator_id is None


# --- Phase 0: the panel says what happened ----------------------------------
#
# Every test below reproduces something Alex hit by running the app. Each
# failed before the fix it guards; the numbers in the docstrings were
# measured, not estimated.


def test_the_batch_row_does_not_swallow_the_panel(qapp):
    """The status label must not claim the panel's vertical space.

    `WrappedLabel`'s `MinimumExpanding` policy is load-bearing INSIDE the
    scroll area -- it is what stops the calculator buttons being squeezed
    (see `test_a_long_result_does_not_squeeze_the_calculator_buttons`).
    In the top-level batch row it does the opposite: the row claims the
    stretch and the sections are pushed off-screen.

    Measured on a bare Qt reproduction at 900x950: the same label is
    **461 px** tall with the policy and **20 px** without, moving the
    scroll area's top from y=478 to y=37. On screen that is a third of
    the panel occupied by one line of status text.
    """
    panel, bus, _area = _panel_in_a_scroll_area(qapp)
    panel._batch_status.setText(
        "Running 2 with default settings: Elemental Analysis, Regulatory Screen"
    )
    for _ in range(3):
        qapp.processEvents()

    assert panel._batch_status.height() <= 40, (
        f"the batch status label is {panel._batch_status.height()}px tall; "
        "it is a one-line status, not a panel"
    )


def test_a_failed_alert_shows_its_reason_rather_than_clean(qapp):
    """A FAILED result has an empty `matched` list, and empty used to mean
    "Clean" -- in green, with the real message discarded.

    Geometry is the case Alex hit: no 3D conformer, so
    `compute_geometry_analysis` returns FAILED carrying "This calculation
    needs a 3D conformer", and the panel reported success.
    """
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="geometry_analysis",
                name="Geometry",
                molecule_uuid="mol-1",
                matched=[],
                category="geometry",
                cache_state=CacheState.FAILED,
                error="This calculation needs a 3D conformer.",
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "geometry_analysis")]
    assert "3D conformer" in label.text()
    assert "Clean" not in label.text()


def test_an_informational_result_is_not_dressed_up_as_alerts(qapp):
    """20 of the 25 `alert_id`s in this codebase are reports, not alert
    catalogs -- elemental analysis, topology indices, Huckel energies,
    the IUPAC name. All of them rendered as
    `"8 alert(s): Formula: CHNO, Mass: 43.025, ..."` in alert red.

    Red is reserved for failed, dangerous or invalid. An elemental
    analysis is none of those.
    """
    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="elemental_analysis",
                name="Elemental Analysis",
                molecule_uuid="mol-1",
                matched=["Formula: CHNO", "Mass: 43.025", "C: 27.92%"],
                category="identity",
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "elemental_analysis")]
    assert "alert(s)" not in label.text()
    assert "Formula: CHNO" in label.text()
    assert "#c62828" not in label.styleSheet(), "informational results must not be alert red"


def test_a_real_alert_catalog_still_reads_as_a_warning(qapp):
    """The other half of the same change: PAINS is what `AlertResult` was
    written for, and a match there really is something to look at. It
    declares `Severity.WARNING` and keeps a warning colour."""
    from openchem.domain.structure_issue import Severity

    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="pains",
                name="PAINS",
                molecule_uuid="mol-1",
                matched=["rhod_sat_A(33)"],
                severity=Severity.WARNING,
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )

    label = panel._alert_labels[("core", "pains")]
    assert "rhod_sat_A(33)" in label.text()
    assert "1 alert(s)" in label.text()
    assert label.styleSheet() != ""


def test_a_batch_result_is_visible_without_opening_anything(qapp):
    """"I can hit run on several things, and nothing noticeable happens."

    `_on_run_selected` does not set `_pending_calculator_id` (six stacked
    inspectors is not a saving), and every per-atom handler returned
    early without it -- so a batch-run result was computed, published,
    and then rendered nowhere at all.
    """
    panel, bus, service = _panel_with_recorder(qapp)
    model = _select_molecule(panel, bus)

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="gasteiger_charge",
                name="Partial Charge (Gasteiger)",
                units="e",
                method="rdkit",
                molecule_uuid=model.uuid,
                values={0: -0.4, 1: 0.1, 2: 0.3},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )
    qapp.processEvents()

    texts = [label.text() for label in panel._result_labels.values()]
    assert texts, "a batch result left no trace in the panel"
    assert any("3 atoms" in text for text in texts), texts


def test_a_batch_run_says_when_it_has_finished(qapp):
    """The status read "Running 2 with default settings: ..." forever --
    it was set on dispatch and never updated when the results landed."""
    panel, bus, service = _panel_with_recorder(qapp)
    model = _select_molecule(panel, bus)

    # A really-registered calculator, taken from the registry rather than
    # spelled by hand -- a direct-import test once passed here against an
    # id nothing was registered under.
    calculator_id = "gasteiger_charge_at_ph"
    panel._calculator_ticks[calculator_id].setChecked(True)
    panel._on_run_selected()
    assert "Running" in panel._batch_status.text()

    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id=calculator_id,
                name="Partial Charge (Gasteiger)",
                units="e",
                method="rdkit",
                molecule_uuid=model.uuid,
                values={0: -0.4},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )
    qapp.processEvents()

    assert "Running" not in panel._batch_status.text()


def test_a_value_can_be_selected_and_copied(qapp):
    """Nothing in the panel was copyable: plain QLabels are not even
    text-selectable, and there was no context menu. `result_to_text`
    already existed and five other surfaces already used it."""
    from PySide6.QtCore import Qt

    panel, bus, _service = _make_panel(qapp)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    bus.publish(DescriptorComputed(descriptor=_descriptor()))

    label = panel._value_labels[("rdkit", "mol_wt")]
    assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert panel.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_the_status_glyphs_really_render(qapp):
    """A glyph is only accessible if something in the font chain HAS it.

    Qt falls back per font on Windows, and a codepoint no font supplies
    draws as a tofu box -- worse than no glyph, because it reads as a
    rendering bug rather than as a status.

    TWO THINGS THIS TEST HAD TO GET PAST, both measured:

    1. `QFontMetrics.inFont()` is NOT the answer. It reports **False for
       all three of these glyphs** even though they render perfectly,
       because it asks about the one nominated font rather than the
       fallback chain Qt actually paints with.
    2. "it drew some ink" is not the answer either -- a tofu box is ink.

    So the control is a Private Use Area codepoint, which by definition no
    font assigns. Whatever tofu looks like on this machine, that is what it
    looks like; a real glyph must render DIFFERENTLY from it.
    """
    from PySide6.QtWidgets import QLabel

    from openchem.ui.panels.property_panel import (
        _FAILURE_GLYPH,
        _SUCCESS_GLYPH,
        _WARNING_GLYPH,
    )
    from tests.conftest import painted

    def pixels(text: str) -> bytes:
        image = painted(QLabel(text), 60, 28)
        return image.constBits().tobytes()

    unsupported = pixels("")
    blank = pixels(" ")
    # THE CONTROL IS WHAT "NO GLYPH" LOOKS LIKE HERE, and it is not the
    # same everywhere. A Private Use Area codepoint has no glyph in any
    # font; Windows draws nothing at all for it, byte-identical to a
    # space, while a Linux runner draws the familiar tofu box.
    #
    # This used to assert `unsupported == blank` and then compare each
    # glyph against `blank` -- which pinned the test to the Windows
    # regime and failed on Linux naming exactly that reason. The
    # docstring above already described the right check ("whatever tofu
    # looks like on this machine, that is what it looks like; a real
    # glyph must render DIFFERENTLY from it"); the code compared against
    # the wrong baseline. Comparing against `unsupported` is the
    # docstring's check, and it is correct in BOTH regimes: where tofu
    # draws nothing the two are identical, and where it draws a box this
    # is the only comparison that can tell a glyph from it.
    tofu_is_drawn = unsupported != blank

    for name, glyph in (
        ("failure", _FAILURE_GLYPH),
        ("warning", _WARNING_GLYPH),
        ("success", _SUCCESS_GLYPH),
    ):
        drawn = pixels(glyph)
        assert drawn != blank, (
            f"the {name} glyph {glyph!r} drew nothing -- no font in the "
            "fallback chain supplies it, so the status is invisible"
        )
        assert drawn != unsupported, (
            f"the {name} glyph {glyph!r} rendered identically to an "
            f"unsupported codepoint"
            + (
                " (a tofu box on this platform), so no font in the fallback "
                "chain supplies it"
                if tofu_is_drawn
                else ", which draws nothing here"
            )
        )


def test_the_identity_card_uses_the_molecule_s_real_name(qapp):
    """**A `getattr` default hid a typo.** The first version read
    `getattr(molecule, "name", "")` -- the field is `display_name` -- so
    every card rendered "(not named)" for a molecule the project explorer
    was calling "New molecule" three inches away, and nothing raised.
    """
    panel, bus, _service = _panel_with_recorder(qapp)
    model = _select_molecule(panel, bus)

    assert model.display_name
    assert panel._selected_molecule_name() == model.display_name


def test_editing_a_structure_re_perceives_it(qapp):
    """Found by running the app. A new molecule has no molblock, so the
    header is correctly empty; pasting a structure into it fires
    `MoleculeChanged`, NOT `MoleculeSelected`. Without this the card read
    "No structure selected" while the properties below it showed
    Mwt 58.44 and formula ClNa.

    Every other test publishes a selection for a molecule that already has
    its molblock -- the one order in which this cannot happen.
    """
    from openchem.events.events import MoleculeChanged

    panel, bus, service = _panel_with_recorder(qapp)
    model = _select_molecule(panel, bus)
    before = [r for r in service.requests if r.calculator_id == "substance_analysis"]

    model.molblock = _MINIMAL_MOLBLOCK
    bus.publish(MoleculeChanged(molecule_uuid=model.uuid))
    qapp.processEvents()

    after = [r for r in service.requests if r.calculator_id == "substance_analysis"]
    assert len(after) > len(before)


def test_a_molecule_with_no_structure_is_not_dispatched(qapp):
    """This is the only calculator that runs unasked, so it is the only
    one that can be handed a molecule with nothing in it. Live, that
    logged `InvalidStructureError: Molecule ... has no molblock` as a
    calculator FAILURE and printed the traceback in red in the Console
    panel, on every startup."""
    panel, bus, service = _panel_with_recorder(qapp)
    _select_molecule(panel, bus)

    assert not [r for r in service.requests if r.calculator_id == "substance_analysis"]


def test_an_explicitly_run_row_result_is_scrolled_into_view(qapp):
    """The ADMET complaint: "the calculator produces nothing".

    It produced everything -- the sidecar ran, the model returned its
    endpoints, and the row rendered correctly about 900 px down a panel
    whose viewport is 372 px, inside a section collapsed by default near
    the bottom of twenty-odd others. Confirmed by driving the app and
    scrolling down to find `hERG blockade: 0.82` sitting there.

    Four of the six result shapes already answer a button press
    unmissably -- a per-atom dataset, a spectrum, a structure set and a pH
    curve each open a dialog when they match `_pending_calculator_id`. The
    two that render INLINE had no such handling, so the more a result had
    to say, the better it was hidden.
    """
    registry = CalculatorRegistry()
    definition = _calculator_definition("admet_ml", category="admet")
    registry.register(definition)
    panel, bus, service = _make_panel(qapp, registry)
    molecule = MoleculeModel(display_name="Ethanol")
    panel.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    section = panel._section_for("admet")
    section.set_expanded(False)
    panel._open_calculator(definition)
    assert panel._pending_calculator_id == "admet_ml"

    # Spy on the CALL, not on `valueChanged`: an unshown panel has no
    # scroll range, so a real setValue would be a silent no-op here and
    # the test would pass whatever the code did.
    revealed: list[int] = []
    panel._scroll_area.verticalScrollBar().setValue = revealed.append
    horizontal: list[int] = []
    panel._scroll_area.horizontalScrollBar().setValue = horizontal.append

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="admet_ml",
                name="ADMET (ADMET-AI)",
                category="admet",
                matched=["hERG blockade: 0.82"],
                molecule_uuid=molecule.uuid,
                cache_state=CacheState.COMPLETED,
                provenance=Provenance(created_by="admet_ai", method="chemprop"),
            )
        )
    )
    qapp.processEvents()
    qapp.processEvents()

    assert section.is_expanded(), "a collapsed section hides the result it was asked for"
    assert revealed, "the row was never scrolled into view"
    assert not horizontal, (
        "the panel scrolled SIDEWAYS, which this project treats as worse "
        "than the invisibility it is fixing"
    )
    assert panel._pending_calculator_id is None, "the request was not consumed"


def test_a_result_nobody_asked_for_does_not_hijack_the_scroll(qapp):
    """A batch run publishes many results and must not yank the panel
    around per result -- `_on_run_selected` deliberately leaves
    `_pending_calculator_id` unset, and that is what distinguishes the
    two cases."""
    registry = CalculatorRegistry()
    definition = _calculator_definition("admet_ml", category="admet")
    registry.register(definition)
    panel, bus, service = _make_panel(qapp, registry)
    molecule = MoleculeModel(display_name="Ethanol")
    panel.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    # Spy on the CALL, not on `valueChanged`: an unshown panel has no
    # scroll range, so a real setValue would be a silent no-op here and
    # the test would pass whatever the code did.
    revealed: list[int] = []
    panel._scroll_area.verticalScrollBar().setValue = revealed.append
    horizontal: list[int] = []
    panel._scroll_area.horizontalScrollBar().setValue = horizontal.append

    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="admet_ml",
                name="ADMET (ADMET-AI)",
                category="admet",
                matched=["hERG blockade: 0.82"],
                molecule_uuid=molecule.uuid,
                cache_state=CacheState.COMPLETED,
                provenance=Provenance(created_by="admet_ai", method="chemprop"),
            )
        )
    )
    qapp.processEvents()
    qapp.processEvents()

    assert not revealed
