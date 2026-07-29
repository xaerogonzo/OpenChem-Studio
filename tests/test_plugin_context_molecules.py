from __future__ import annotations

from openchem.domain.molecule import MoleculeModel
from openchem.plugins.context import _PluginMolecules


class _FakeUIRegistry:
    def __init__(self) -> None:
        self.added: list[MoleculeModel] = []

    def add_molecule(self, molecule: MoleculeModel) -> None:
        self.added.append(molecule)


def test_plugin_molecules_add_delegates_to_ui_registry():
    ui_registry = _FakeUIRegistry()
    molecules = _PluginMolecules(ui_registry)

    molecule = MoleculeModel(display_name="Aspirin")
    molecules.add(molecule)

    assert ui_registry.added == [molecule]
