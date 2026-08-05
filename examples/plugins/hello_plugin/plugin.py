from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget
from rdkit import Chem

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.plugins.context import PluginContext
from openchem.plugins.interfaces import DescriptorProvider, MenuProvider, PanelProvider, Plugin


class HelloDescriptorProvider(DescriptorProvider):
    """One descriptor: fraction of heavy atoms that are in a ring.

    Descriptor id is namespaced ("hello.ring_fraction", not "ring_fraction")
    so it can never collide with another provider's descriptor of the same
    short name — see docs/PLUGIN_SDK.md.
    """

    provider_id = "hello"

    def descriptor_ids(self) -> list[str]:
        return ["hello.ring_fraction"]

    def compute(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
        heavy = mol.GetNumHeavyAtoms()
        ring_atoms = sum(1 for atom in mol.GetAtoms() if atom.IsInRing())
        fraction = 0.0 if heavy == 0 else ring_atoms / heavy
        return [
            DescriptorValue(
                descriptor_id="hello.ring_fraction",
                name="Ring Fraction",
                units="",
                category="topology",
                provider=self.provider_id,
                molecule_uuid=molecule_uuid,
                value=round(fraction, 3),
                cache_state=CacheState.COMPLETED,
            )
        ]


class HelloPanelWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Hello from a plugin!"))


class HelloPanelProvider(PanelProvider):
    panel_id = "Hello Plugin"

    def create_panel(self) -> QWidget:
        return HelloPanelWidget()


class HelloMenuProvider(MenuProvider):
    def menu_entries(self) -> list[tuple[str, str]]:
        return [("Say Hello", "hello.say_hi")]

    def handle_menu_action(self, action_id: str) -> None:
        if action_id == "hello.say_hi":
            QMessageBox.information(None, "Hello Plugin", "Hello from hello_plugin!")


class HelloPlugin(Plugin):
    """Ties the descriptor/panel/menu providers together. See
    docs/PLUGIN_SDK.md for what each `context.*` namespace does.
    """

    def activate(self, context: PluginContext) -> None:
        context.descriptors.register(HelloDescriptorProvider())
        context.panels.register(HelloPanelProvider())
        context.menus.register(HelloMenuProvider())
        context.logger.info("hello_plugin activated")

    def deactivate(self) -> None:
        pass


def create_plugin() -> Plugin:
    return HelloPlugin()
