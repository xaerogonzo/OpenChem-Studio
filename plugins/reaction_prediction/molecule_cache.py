from __future__ import annotations

from openchem.events.events import MoleculeSelected, MoleculeSnapshotUpdated


class SelectedMoleculeCache:
    """Tracks just the selected molecule's display name + canonical SMILES,
    purely from subscribed events — same pattern as `ai_assistant`'s
    `MoleculeContextCache` (never holds a `MoleculeModel` reference), but
    simpler since reaction prediction only needs a SMILES to prefill the
    first reactant box, not a full descriptor context block.
    """

    def __init__(self) -> None:
        self._display_name: str | None = None
        self._canonical_smiles: str | None = None

    def on_molecule_selected(self, event: MoleculeSelected) -> None:
        # Only clears on explicit deselection — see ai_assistant's
        # MoleculeContextCache.on_molecule_selected for why: MainWindow
        # publishes MoleculeSnapshotUpdated from inside its own
        # MoleculeSelected handler, so that nested publish (and this
        # cache's on_snapshot_updated) already ran by the time this handler
        # gets its turn in the same dispatch loop.
        if event.molecule_uuid is None:
            self._display_name = None
            self._canonical_smiles = None

    def on_snapshot_updated(self, event: MoleculeSnapshotUpdated) -> None:
        self._display_name = event.display_name
        self._canonical_smiles = event.canonical_smiles

    def has_molecule(self) -> bool:
        return self._canonical_smiles is not None

    def display_name(self) -> str:
        return self._display_name or "(no molecule selected)"

    def canonical_smiles(self) -> str | None:
        return self._canonical_smiles
