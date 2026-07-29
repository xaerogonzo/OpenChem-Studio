from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QUndoStack
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMainWindow, QMessageBox, QTabWidget, QWidget

from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.commands.conformer_commands import SetConformersCommand
from openchem.commands.import_export_commands import ExportMoleculeCommand, ImportMoleculeCommand
from openchem.commands.molecule_commands import AddMoleculeCommand
from openchem.commands.project_commands import OpenProjectCommand, SaveProjectCommand
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import (
    ConformersReady,
    MoleculeChanged,
    MoleculeSelected,
    PluginLoaded,
    PluginUnloaded,
)
from openchem.plugins.manager import PluginManager
from openchem.services.container import ServiceContainer
from openchem.ui.panels.console_panel import ConsolePanel
from openchem.ui.panels.project_explorer_panel import ProjectExplorerPanel
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget

logger = logging.getLogger("openchem.ui")


class MainWindow(QMainWindow):
    """QMainWindow: menu bar, dock layout, owns the QUndoStack.

    Panels are constructed with the injected ServiceContainer/EventBus and
    never touch `chem/` directly — this class is the composition point
    where UI meets services/commands.
    """

    def __init__(self, services: ServiceContainer, settings: Settings, session: SessionManager) -> None:
        super().__init__()
        self._services = services
        self._settings = settings
        self._session = session
        self._undo_stack = QUndoStack(self)
        self._plugin_panels: dict[str, QDockWidget] = {}
        self._plugin_menu_actions: dict[str, list[QAction]] = {}

        self.setWindowTitle("OpenChem Studio")
        self.resize(1280, 800)

        self._editor = MoleculeEditorWidget(
            services.chemistry_engine, services.event_bus, self._undo_stack, parent=self
        )
        self._viewer3d = MoleculeViewer3DWidget(
            services.conformer_service, services.measurement_service, services.event_bus, parent=self
        )
        self._center_tabs = QTabWidget(self)
        self._center_tabs.addTab(self._editor, "2D Editor")
        self._center_tabs.addTab(self._viewer3d, "3D Viewer")
        self.setCentralWidget(self._center_tabs)

        self._project_explorer = ProjectExplorerPanel(services.event_bus, self)
        self._property_panel = PropertyPanel(services.event_bus, self)
        self._console_panel = ConsolePanel(self)

        self._add_dock("Project Explorer", self._project_explorer, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Properties", self._property_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Console", self._console_panel, Qt.DockWidgetArea.BottomDockWidgetArea)

        self._build_menus()

        services.event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        services.event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)
        services.event_bus.subscribe(ConformersReady, self._on_conformers_ready)
        services.event_bus.subscribe(PluginLoaded, self._on_plugins_state_changed)
        services.event_bus.subscribe(PluginUnloaded, self._on_plugins_state_changed)

        self._new_project()

        # Constructed last: PluginManager depends only on the UIRegistry
        # protocol (add_panel/remove_panel/add_menu_action/remove_menu_actions
        # below), not on MainWindow itself — see plugins/ui_registry.py.
        self._plugin_manager = PluginManager(services, self, settings)
        self._plugin_manager.load_all()
        self._refresh_installed_plugins_menu()

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title.replace(" ", "_"))
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("New Project", self._new_project)
        file_menu.addAction("Open Project...", self._open_project)
        file_menu.addAction("Save Project...", self._save_project)
        file_menu.addSeparator()
        file_menu.addAction("New Molecule", self._new_molecule)
        file_menu.addAction("Import Molecule...", self._import_molecule)
        file_menu.addAction("Export Molecule...", self._export_molecule)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        undo_action = self._undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut("Ctrl+Z")
        redo_action = self._undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut("Ctrl+Y")
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)

        self._view_menu = self.menuBar().addMenu("&View")
        for dock in self.findChildren(QDockWidget):
            self._view_menu.addAction(dock.toggleViewAction())

        self._plugins_menu = self.menuBar().addMenu("&Plugins")
        self._plugins_menu.addAction("Reload Plugins", self._reload_plugins)
        self._plugins_menu.addAction(
            "Open Project Plugins Folder", lambda: self._open_plugins_folder(project=True)
        )
        self._plugins_menu.addAction(
            "Open User Plugins Folder", lambda: self._open_plugins_folder(project=False)
        )
        self._plugins_menu.addSeparator()
        self._installed_plugins_menu = self._plugins_menu.addMenu("Installed Plugins")
        self._plugins_menu.addSeparator()
        # Plugin-contributed menu entries (via context.menus.register(...))
        # are appended directly to this menu, below the separator above.

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction("About OpenChem Studio", self._show_about)

    # --- project lifecycle --------------------------------------------------

    def _new_project(self) -> None:
        self._set_project(ProjectModel(name="Untitled project"))

    def _set_project(self, project: ProjectModel) -> None:
        self._session.set_project(project)
        self._project_explorer.set_project(project)
        self.setWindowTitle(f"OpenChem Studio - {project.name}")

    def _open_project(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open Project", filter="OpenChem Project (*.ocsproj)")
        if not path_str:
            return
        command = OpenProjectCommand(self._services.project_service, Path(path_str))
        self._undo_stack.push(command)
        if command.loaded_project is not None:
            self._set_project(command.loaded_project)

    def _save_project(self) -> None:
        if self._session.project is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(self, "Save Project", filter="OpenChem Project (*.ocsproj)")
        if not path_str:
            return
        if not path_str.endswith(".ocsproj"):
            path_str += ".ocsproj"
        command = SaveProjectCommand(self._services.project_service, self._session.project, Path(path_str))
        self._undo_stack.push(command)

    # --- molecule lifecycle --------------------------------------------------

    def _new_molecule(self) -> None:
        if self._session.project is None:
            return
        molecule = MoleculeModel(display_name="New molecule")
        command = AddMoleculeCommand(self._session.project, molecule, self._services.event_bus)
        self._undo_stack.push(command)
        self._project_explorer.refresh()
        self._services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    def _import_molecule(self) -> None:
        if self._session.project is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Import Molecule",
            filter="Molecule files (*.mol *.sdf *.smi *.smiles *.inchi *.mol2 *.pdb *.xyz *.cml)",
        )
        if not path_str:
            return
        try:
            command = ImportMoleculeCommand(
                self._services.import_service, self._session.project, Path(path_str), self._services.event_bus
            )
            self._undo_stack.push(command)
        except Exception as exc:  # noqa: BLE001 - surface to the user, don't crash the app
            logger.exception("Import failed")
            QMessageBox.critical(self, "Import failed", str(exc))
        self._project_explorer.refresh()

    def _export_molecule(self) -> None:
        molecule = self._current_molecule()
        if molecule is None:
            QMessageBox.information(self, "Export Molecule", "Select a molecule first.")
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Export Molecule", filter="MOL (*.mol);;SDF (*.sdf);;SMILES (*.smi)"
        )
        if not path_str:
            return
        try:
            command = ExportMoleculeCommand(self._services.export_service, molecule, Path(path_str))
            self._undo_stack.push(command)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Export failed")
            QMessageBox.critical(self, "Export failed", str(exc))

    # --- event handlers --------------------------------------------------------

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._session.select_molecule(event.molecule_uuid)
        molecule = self._current_molecule()
        self._editor.set_molecule(molecule)
        self._viewer3d.set_molecule(molecule)
        if molecule is not None:
            self._services.descriptor_service.request_descriptors(molecule)

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        self._session.mark_dirty()
        molecule = self._current_molecule()
        if molecule is not None and molecule.uuid == event.molecule_uuid:
            self._services.descriptor_service.request_descriptors(molecule)

    def _on_conformers_ready(self, event: ConformersReady) -> None:
        molecule = self._current_molecule()
        if molecule is None or molecule.uuid != event.molecule_uuid:
            return
        command = SetConformersCommand(molecule, event.conformers, self._services.event_bus)
        self._undo_stack.push(command)

    def _current_molecule(self) -> MoleculeModel | None:
        if self._session.project is None or self._session.selected_molecule_uuid is None:
            return None
        return self._session.project.find_molecule(self._session.selected_molecule_uuid)

    # --- UIRegistry protocol (see plugins/ui_registry.py) -----------------------
    # PluginManager depends on these four methods structurally, never on
    # MainWindow itself.

    def add_panel(self, panel_id: str, widget_factory: Callable[[], QWidget]) -> None:
        if panel_id in self._plugin_panels:
            self.remove_panel(panel_id)
        widget = widget_factory()
        dock = self._add_dock(panel_id, widget, Qt.DockWidgetArea.RightDockWidgetArea)
        self._plugin_panels[panel_id] = dock
        self._view_menu.addAction(dock.toggleViewAction())

    def remove_panel(self, panel_id: str) -> None:
        dock = self._plugin_panels.pop(panel_id, None)
        if dock is None:
            return
        self.removeDockWidget(dock)
        dock.deleteLater()

    def add_menu_action(self, plugin_id: str, label: str, callback: Callable[[], None]) -> None:
        action = QAction(label, self)
        action.triggered.connect(callback)
        self._plugins_menu.addAction(action)
        self._plugin_menu_actions.setdefault(plugin_id, []).append(action)

    def remove_menu_actions(self, plugin_id: str) -> None:
        actions = self._plugin_menu_actions.pop(plugin_id, [])
        for action in actions:
            self._plugins_menu.removeAction(action)
            action.deleteLater()

    # --- plugin menu ------------------------------------------------------------

    def _reload_plugins(self) -> None:
        self._plugin_manager.reload_all()
        self._refresh_installed_plugins_menu()

    def _open_plugins_folder(self, project: bool) -> None:
        directories = self._plugin_manager.plugin_directories
        directory = directories[0] if project else directories[1]
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _on_plugins_state_changed(self, event) -> None:
        self._refresh_installed_plugins_menu()

    def _refresh_installed_plugins_menu(self) -> None:
        self._installed_plugins_menu.clear()
        manifests = self._plugin_manager.discover_manifests()
        if not manifests:
            placeholder = self._installed_plugins_menu.addAction("(none found)")
            placeholder.setEnabled(False)
            return
        disabled = self._plugin_manager.disabled_ids()
        for manifest in manifests:
            action = QAction(manifest.display_name, self)
            action.setCheckable(True)
            action.setChecked(manifest.plugin_id not in disabled)
            action.toggled.connect(
                lambda checked, plugin_id=manifest.plugin_id: self._plugin_manager.set_enabled(
                    plugin_id, checked
                )
            )
            self._installed_plugins_menu.addAction(action)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About OpenChem Studio",
            "OpenChem Studio\nAn open-source, plugin-based chemistry workstation.",
        )
