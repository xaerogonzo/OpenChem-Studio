from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

import keyring
import keyring.errors

from openchem.app.settings import Settings
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import Event, EventBus
from openchem.plugins.interfaces import (
    ConformerProvider,
    DescriptorProvider,
    DockingProvider,
    Exporter,
    Importer,
    MenuProvider,
    PanelProvider,
    QuantumEngineProvider,
)
from openchem.plugins.ui_registry import UIRegistry
from openchem.services.container import ServiceContainer

TEvent = TypeVar("TEvent", bound=Event)
Rollback = Callable[[], None]


class _PluginSettings:
    """Namespaced view over Settings — a plugin can only read/write keys
    under plugins/<plugin_id>/, never the app's own settings or another
    plugin's."""

    def __init__(self, settings: Settings, plugin_id: str) -> None:
        self._settings = settings
        self._prefix = f"plugins/{plugin_id}/"

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(self._prefix + key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings.set(self._prefix + key, value)


class _PluginSecrets:
    """Namespaced view over the OS keychain (via `keyring`) — a plugin can
    only read/write its own credentials, never another plugin's.

    Not tracked in the rollback list: a stored credential is expected to
    persist across reload/unload, same as `context.settings`.
    """

    def __init__(self, plugin_id: str) -> None:
        self._service_name = f"openchem-plugin-{plugin_id}"

    def get(self, key: str) -> str | None:
        return keyring.get_password(self._service_name, key)

    def set(self, key: str, value: str) -> None:
        keyring.set_password(self._service_name, key, value)

    def delete(self, key: str) -> None:
        try:
            keyring.delete_password(self._service_name, key)
        except keyring.errors.PasswordDeleteError:
            pass  # already absent — deleting a not-there secret isn't an error


class _PluginMolecules:
    """Lets a plugin add a molecule to the current project — e.g. a database
    search result or a predicted reaction product — through the same
    undoable path `MainWindow._new_molecule()` uses. Not tracked for
    rollback: an added molecule is real project data, same treatment as a
    molecule added via File > New, not a registration to unwind on unload.
    """

    def __init__(self, ui_registry: UIRegistry) -> None:
        self._ui_registry = ui_registry

    def add(self, molecule: MoleculeModel) -> None:
        self._ui_registry.add_molecule(molecule)


class _DescriptorRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, provider: DescriptorProvider) -> None:
        self._service.register_provider(provider)
        self._rollbacks.append(lambda: self._service.unregister_provider(provider.provider_id))


class _ConformerRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, provider: ConformerProvider) -> None:
        self._service.register_provider(provider)
        self._rollbacks.append(lambda: self._service.unregister_provider(provider.provider_id))


class _DockingRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, provider: DockingProvider) -> None:
        self._service.register_provider(provider)
        self._rollbacks.append(lambda: self._service.unregister_provider(provider.provider_id))


class _QuantumChemistryRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, provider: QuantumEngineProvider) -> None:
        self._service.register_provider(provider)
        self._rollbacks.append(lambda: self._service.unregister_provider(provider.provider_id))


class _ImporterRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, importer: Importer) -> None:
        self._service.register_importer(importer)
        self._rollbacks.append(lambda: self._service.unregister_importer(importer))


class _ExporterRegistrar:
    def __init__(self, service, rollbacks: list[Rollback]) -> None:
        self._service = service
        self._rollbacks = rollbacks

    def register(self, exporter: Exporter) -> None:
        self._service.register_exporter(exporter)
        self._rollbacks.append(lambda: self._service.unregister_exporter(exporter))


class _PanelRegistrar:
    def __init__(self, ui_registry: UIRegistry, rollbacks: list[Rollback]) -> None:
        self._ui_registry = ui_registry
        self._rollbacks = rollbacks

    def register(self, provider: PanelProvider) -> None:
        panel_id = provider.panel_id
        self._ui_registry.add_panel(panel_id, provider.create_panel)
        self._rollbacks.append(lambda: self._ui_registry.remove_panel(panel_id))

    def reveal(self, panel_id: str) -> None:
        """Bring a registered panel's tab to the front -- call this from a
        menu action before focusing/prefilling the panel's own widget, or
        the action is invisible whenever that panel isn't the active tab."""
        self._ui_registry.reveal_panel(panel_id)


class _MenuRegistrar:
    def __init__(self, ui_registry: UIRegistry, plugin_id: str, rollbacks: list[Rollback]) -> None:
        self._ui_registry = ui_registry
        self._plugin_id = plugin_id
        self._rollbacks = rollbacks

    def register(self, provider: MenuProvider) -> None:
        for label, action_id in provider.menu_entries():
            self._ui_registry.add_menu_action(
                self._plugin_id, label, lambda aid=action_id: provider.handle_menu_action(aid)
            )
        # One rollback per register() call is fine even if called more than
        # once — remove_menu_actions(plugin_id) removing an already-empty
        # set is a no-op, not an error.
        self._rollbacks.append(lambda: self._ui_registry.remove_menu_actions(self._plugin_id))


class _EventRegistrar:
    def __init__(self, event_bus: EventBus, rollbacks: list[Rollback]) -> None:
        self._event_bus = event_bus
        self._rollbacks = rollbacks

    def subscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], None]) -> None:
        self._event_bus.subscribe(event_type, handler)
        self._rollbacks.append(lambda: self._event_bus.unsubscribe(event_type, handler))

    def unsubscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], None]) -> None:
        self._event_bus.unsubscribe(event_type, handler)


class PluginContext:
    """Passed to `Plugin.activate()`. Everything registered through this
    object is tracked so `PluginManager` can unwind it exactly — on
    `unload()`, or automatically if `activate()` itself raises partway
    through (transactional activation, see `PluginManager`).

    Grouped into small namespaces (`descriptors`, `conformers`, `docking`,
    `quantum_chemistry`, `importers`, `exporters`, `panels`, `menus`,
    `events`, `settings`, `secrets`, `molecules`) rather than one flat pile
    of `register_*` methods on this class directly.

    Deliberately does not expose the raw `EventBus`, `ServiceContainer`, or
    any concrete window/UI object — only these narrow registration
    namespaces. A plugin subscribing to events or connecting Qt signals
    directly, outside of `events.subscribe`, would leak on unload.
    """

    def __init__(
        self,
        plugin_id: str,
        plugin_dir: Path,
        services: ServiceContainer,
        ui_registry: UIRegistry,
        settings: Settings,
    ) -> None:
        self.plugin_id = plugin_id
        self.logger = logging.getLogger(f"openchem.plugin.{plugin_id}")
        self._plugin_dir = plugin_dir
        self._rollbacks: list[Rollback] = []

        self.descriptors = _DescriptorRegistrar(services.descriptor_service, self._rollbacks)
        self.conformers = _ConformerRegistrar(services.conformer_service, self._rollbacks)
        self.docking = _DockingRegistrar(services.docking_service, self._rollbacks)
        self.quantum_chemistry = _QuantumChemistryRegistrar(services.quantum_chemistry_service, self._rollbacks)
        self.importers = _ImporterRegistrar(services.import_service, self._rollbacks)
        self.exporters = _ExporterRegistrar(services.export_service, self._rollbacks)
        self.panels = _PanelRegistrar(ui_registry, self._rollbacks)
        self.menus = _MenuRegistrar(ui_registry, plugin_id, self._rollbacks)
        self.events = _EventRegistrar(services.event_bus, self._rollbacks)
        self.settings = _PluginSettings(settings, plugin_id)
        self.secrets = _PluginSecrets(plugin_id)
        self.molecules = _PluginMolecules(ui_registry)

    def resource_path(self, relative: str) -> Path:
        """Path to a file bundled alongside this plugin (icons, templates, etc.)."""
        return self._plugin_dir / relative

    def unwind(self) -> None:
        """Reverse every registration/subscription made through this
        context, most-recent-first. Used for both a clean unload() and for
        rolling back a partially-failed activate()."""
        for rollback in reversed(self._rollbacks):
            try:
                rollback()
            except Exception:
                self.logger.exception("Error while unwinding a plugin registration")
        self._rollbacks.clear()
