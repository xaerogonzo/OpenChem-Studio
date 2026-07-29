from __future__ import annotations

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.events.base import EventBus
from openchem.events.events import DescriptorComputed, MoleculeSelected
from openchem.ui.panels.property_panel import PropertyPanel


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

    assert panel._table.rowCount() == 2
