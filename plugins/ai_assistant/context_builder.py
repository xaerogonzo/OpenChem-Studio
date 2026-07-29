from __future__ import annotations

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.events.events import DescriptorComputed, MoleculeSelected, MoleculeSnapshotUpdated


class MoleculeContextCache:
    """Accumulates just enough about the currently selected molecule to
    build an AI request context block — purely from events the panel
    already subscribes to via `context.events.subscribe`, the same way
    `ui/panels/property_panel.py` tracks descriptors without ever holding a
    `MoleculeModel` reference. No access to services/session needed.
    """

    def __init__(self) -> None:
        self._snapshot: MoleculeSnapshotUpdated | None = None
        self._descriptors: dict[str, DescriptorValue] = {}

    def on_molecule_selected(self, event: MoleculeSelected) -> None:
        # Only clears on explicit deselection (molecule_uuid is None).
        # MainWindow publishes MoleculeSnapshotUpdated from inside its own
        # MoleculeSelected handler whenever a real molecule is selected —
        # since EventBus dispatch is synchronous and re-entrant, that nested
        # publish already runs (and this cache's on_snapshot_updated already
        # fires) before this handler gets its turn in the MoleculeSelected
        # dispatch loop. Clearing unconditionally here would race it and
        # wipe out the snapshot that was just set.
        if event.molecule_uuid is None:
            self._snapshot = None
            self._descriptors.clear()

    def on_snapshot_updated(self, event: MoleculeSnapshotUpdated) -> None:
        self._snapshot = event
        self._descriptors.clear()  # stale values until fresh ones recompute and arrive

    def on_descriptor_computed(self, event: DescriptorComputed) -> None:
        descriptor = event.descriptor
        if self._snapshot is None or descriptor.molecule_uuid != self._snapshot.molecule_uuid:
            return
        if descriptor.cache_state == CacheState.COMPLETED:
            self._descriptors[descriptor.descriptor_id] = descriptor

    def has_molecule(self) -> bool:
        return self._snapshot is not None

    def display_name(self) -> str:
        return self._snapshot.display_name if self._snapshot else "(no molecule selected)"

    def build_context_text(self) -> str:
        if self._snapshot is None:
            return "No molecule is currently selected."

        lines = [
            f"Molecule: {self._snapshot.display_name}",
            f"Canonical SMILES: {self._snapshot.canonical_smiles or 'unknown'}",
            f"InChI: {self._snapshot.inchi or 'unknown'}",
            f"InChIKey: {self._snapshot.inchikey or 'unknown'}",
        ]
        if self._descriptors:
            lines.append("Computed descriptors:")
            for descriptor_id in sorted(self._descriptors):
                descriptor = self._descriptors[descriptor_id]
                unit_suffix = f" {descriptor.units}" if descriptor.units else ""
                lines.append(f"  - {descriptor.name}: {descriptor.value}{unit_suffix}")
        if self._snapshot.conformer_count:
            energy_text = (
                f", lowest energy {self._snapshot.lowest_conformer_energy:.2f} kcal/mol"
                if self._snapshot.lowest_conformer_energy is not None
                else ""
            )
            lines.append(f"Conformers: {self._snapshot.conformer_count} generated{energy_text}")
        return "\n".join(lines)
