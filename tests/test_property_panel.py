from __future__ import annotations

from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import AlertResult
from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, MoleculeSelected
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


def test_same_bare_descriptor_id_from_different_providers_does_not_collide(qapp):
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(category="physicochemical")))

    assert panel._sections["physicochemical"]._toggle_button.isChecked() is True


def test_boolean_descriptor_renders_as_pass_fail(qapp):
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
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
    bus = EventBus()
    panel = PropertyPanel(bus)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    bus.publish(DescriptorComputed(descriptor=_descriptor()))
    assert len(panel._value_labels) == 1

    bus.publish(MoleculeSelected(molecule_uuid="mol-2"))
    assert len(panel._value_labels) == 0


def test_descriptor_for_a_different_molecule_is_ignored(qapp):
    bus = EventBus()
    panel = PropertyPanel(bus)
    bus.publish(MoleculeSelected(molecule_uuid="mol-1"))

    bus.publish(DescriptorComputed(descriptor=_descriptor(molecule_uuid="mol-2")))

    assert len(panel._value_labels) == 0
