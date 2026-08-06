from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QWidget,
)

from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.chem.identifiers import identifier_for_molblock
from openchem.chem.structure_clipboard import parse_structure_text
from openchem.commands.conformer_commands import AddConformerCommand, SetConformersCommand
from openchem.commands.docking_commands import SetDockingResultCommand
from openchem.commands.import_export_commands import ExportMoleculeCommand, ImportMoleculeCommand
from openchem.commands.macromolecule_commands import AddMacromoleculeCommand
from openchem.commands.molecule_commands import (
    AddMoleculeCommand,
    EditStructureCommand,
    RenameMoleculeCommand,
)
from openchem.commands.project_commands import OpenProjectCommand, SaveProjectCommand
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import (
    ConformersChanged,
    ConformersReady,
    DescriptorComputed,
    DockingResultReady,
    MoleculeChanged,
    MoleculeSelected,
    MoleculeSnapshotUpdated,
    PluginLoaded,
    PluginUnloaded,
    QuantumChemistryResultReady,
)
from openchem.plugins.manager import PluginManager
from openchem.services.container import ServiceContainer
from openchem.ui.dialogs.about_dialog import AboutDialog
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog
from openchem.ui.dialogs.help_dialog import HelpDialog
from openchem.ui.dialogs.structure_lookup_dialog import StructureLookupDialog
from openchem.ui.panels.console_panel import ConsolePanel
from openchem.ui.panels.alignment_panel import AlignmentPanel
from openchem.ui.panels.batch_panel import BatchPanel
from openchem.ui.panels.docking_panel import DockingPanel
from openchem.ui.panels.jobs_panel import JobsPanel
from openchem.ui.panels.project_explorer_panel import ProjectExplorerPanel
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel
from openchem.ui.visualization import build_interaction_layers
from openchem.ui.widgets.dock_title_bar import DockTitleBar
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget
from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget
from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend

logger = logging.getLogger("openchem.ui")

#: Dock objectName -> help topic key. Keyed on objectName rather than the
#: dock title because the title is user-visible text and a rename would
#: silently unwire the help; objectName is already load-bearing for Qt's
#: own state save/restore.
#:
#: Every key here is checked against the documents by tests/test_help.py,
#: so a topic anchor deleted during a documentation sweep fails the suite
#: rather than producing an empty help window.
HELP_TOPIC_BY_DOCK = {
    "Project_Explorer": "projects",
    "Properties": "properties",
    "Docking": "docking",
    "Quantum_Chemistry": "quantum-chemistry",
    "Batch": "batch",
    "3D_Alignment": "alignment",
    "Jobs": "jobs",
    "Console": "jobs",
}

#: Centre tab label -> topic, for when no panel with help is in front.
HELP_TOPIC_BY_CENTRE_TAB = {
    "2D Editor": "centre-tabs",
    "3D Viewer": "centre-tabs",
    "Macromolecule Viewer": "docking",
}


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
        #: Whether a docked pose is currently drawn into the
        #: macromolecule viewer, and which receptor it went into.
        self._showed_a_pose = False
        self._last_pose_receptor_uuid: str | None = None

        self.setWindowTitle("OpenChem Studio")
        self.resize(1280, 800)

        self._editor = MoleculeEditorWidget(
            services.chemistry_engine, services.event_bus, self._undo_stack, parent=self
        )
        self._viewer3d = MoleculeViewer3DWidget(
            services.conformer_service, services.measurement_service, services.event_bus, parent=self
        )
        # Sibling to Mol3DViewerBackend (small molecules) — Mol* is for
        # macromolecular/crystallographic structures (MacromoleculeModel),
        # a genuinely different content shape, so it gets its own tab
        # rather than being squeezed into the existing 3D Viewer widget.
        self._macromolecule_viewer = MolStarViewerBackend(parent=self)
        self._center_tabs = QTabWidget(self)
        self._center_tabs.addTab(self._editor, "2D Editor")
        self._center_tabs.addTab(self._viewer3d, "3D Viewer")
        self._center_tabs.addTab(self._macromolecule_viewer.widget(), "Macromolecule Viewer")
        self.setCentralWidget(self._center_tabs)

        self._project_explorer = ProjectExplorerPanel(
            services.event_bus,
            self._undo_stack,
            self,
            on_duplicate=self._duplicate_molecule,
            on_identify=self._identify_structure,
        )
        self._property_panel = PropertyPanel(
            services.event_bus,
            services.calculator_registry,
            services.descriptor_service,
            services.chemistry_engine,
            self,
            on_add_structure=self._add_generated_structure,
        )
        self._console_panel = ConsolePanel(self)
        self._docking_panel = DockingPanel(
            services.docking_service, services.chemistry_engine, self._settings, services.event_bus, self
        )
        self._quantum_chemistry_panel = QuantumChemistryPanel(
            services.quantum_chemistry_service,
            services.chemistry_engine,
            self._settings,
            services.event_bus,
            self,
            qm_surface_service=services.qm_surface_service,
        )
        self._alignment_panel = AlignmentPanel(services.alignment_service, services.event_bus, self)
        self._jobs_panel = JobsPanel(services.job_manager, self)
        self._batch_panel = BatchPanel(
            services.batch_service,
            services.calculator_registry,
            services.table_export_service,
            services.event_bus,
            services.chemistry_engine,
            self,
            on_analyse=self._show_batch_analysis,
            on_screen=self._show_virtual_screening,
        )

        # Connected after the panels exist, since the handler reads them.
        self._undo_stack.indexChanged.connect(self._on_undo_index_changed)

        self._add_dock("Project Explorer", self._project_explorer, Qt.DockWidgetArea.LeftDockWidgetArea)
        self._properties_dock = self._add_dock(
            "Properties", self._property_panel, Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._add_dock("Console", self._console_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        docking_dock = self._add_dock(
            "Docking", self._wrap_scrollable(self._docking_panel), Qt.DockWidgetArea.RightDockWidgetArea
        )
        quantum_chemistry_dock = self._add_dock(
            "Quantum Chemistry",
            self._wrap_scrollable(self._quantum_chemistry_panel),
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        alignment_dock = self._add_dock(
            "3D Alignment",
            self._wrap_scrollable(self._alignment_panel),
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        jobs_dock = self._add_dock("Jobs", self._jobs_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        batch_dock = self._add_dock(
            "Batch", self._wrap_scrollable(self._batch_panel), Qt.DockWidgetArea.RightDockWidgetArea
        )

        # All right-side panels share one tab group instead of stacking
        # vertically -- six-plus docks sharing a single column (this trio
        # plus every plugin panel added via add_panel()) left each one a
        # sliver too short to render its own controls without overlapping.
        # Tabbing keeps whichever panel is active at full height; plugin
        # panels join the same group below, in add_panel().
        self.tabifyDockWidget(self._properties_dock, docking_dock)
        self.tabifyDockWidget(self._properties_dock, quantum_chemistry_dock)
        self.tabifyDockWidget(self._properties_dock, alignment_dock)
        self.tabifyDockWidget(self._properties_dock, jobs_dock)
        self.tabifyDockWidget(self._properties_dock, batch_dock)
        self._properties_dock.raise_()

        self._build_menus()
        self._restore_window_state()

        services.event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        services.event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)
        services.event_bus.subscribe(ConformersReady, self._on_conformers_ready)
        services.event_bus.subscribe(ConformersChanged, self._on_conformers_changed)
        services.event_bus.subscribe(DockingResultReady, self._on_docking_result_ready)
        services.event_bus.subscribe(QuantumChemistryResultReady, self._on_quantum_chemistry_result_ready)
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

        # A "?" in the title bar, for the panels that have a help topic.
        # F1 already does this, but a keyboard shortcut is only useful to
        # someone who knows it exists -- which is the same discoverability
        # problem that made Copy SMILES look missing when it was there all
        # along, just on a context menu.
        #
        # Only for docks WITH a topic: a "?" that opened the wrong section
        # would be worse than none, and Console and Jobs have nothing
        # written about them.
        topic = HELP_TOPIC_BY_DOCK.get(dock.objectName())
        if topic is not None:
            title_bar = DockTitleBar(dock)
            title_bar.help_requested.connect(lambda topic=topic: self._show_help(topic))
            dock.setTitleBarWidget(title_bar)
        return dock

    def _show_help(self, topic_key: str = "") -> None:
        """Open the help window, on `topic_key` or on whatever is in front.

        One window, reused. A help dialog that stacks up a new copy per
        press of F1 is its own small annoyance, and this one is
        deliberately non-modal so it can be read while working.
        """
        if not isinstance(topic_key, str) or not topic_key:
            topic_key = self._help_topic_for_visible_panel()
        existing = getattr(self, "_help_dialog", None)
        if existing is None:
            existing = HelpDialog(self)
            self._help_dialog = existing
        existing.show_topic(topic_key)
        existing.show()
        existing.raise_()
        existing.activateWindow()

    def _help_topic_for_visible_panel(self) -> str:
        """The topic for whatever the user is currently working in.

        KEYBOARD FOCUS FIRST, not "the first visible dock". Several docks
        are visible at once -- Project Explorer on the left and Console at
        the bottom are always up, alongside whichever right-hand tab is
        in front -- so scanning `findChildren` for the first visible one
        returns whichever happened to be constructed first. Measured: it
        answered "docking" while the Project Explorer was in front, and
        "properties" while Docking was.

        Falling back to the front tab of the right-hand group, and then to
        the centre tab, means F1 always answers a question rather than
        opening an index.
        """
        widget = QApplication.focusWidget()
        while widget is not None:
            if isinstance(widget, QDockWidget) and widget.objectName() in HELP_TOPIC_BY_DOCK:
                return HELP_TOPIC_BY_DOCK[widget.objectName()]
            if widget is self._center_tabs:
                # Reached the editor/viewer without passing through a dock.
                # Checked HERE rather than as a last resort: the right-hand
                # panels are on screen too, so a plain "which dock is
                # visible" scan answers "Properties" to someone who pressed
                # F1 while drawing a structure.
                return HELP_TOPIC_BY_CENTRE_TAB.get(
                    self._center_tabs.tabText(self._center_tabs.currentIndex()), "centre-tabs"
                )
            widget = widget.parentWidget()

        # Only the front member of a tabified group reports visible, so
        # restricting the scan to that group makes `isVisible()` mean what
        # it needs to mean here.
        group = [self._properties_dock, *self.tabifiedDockWidgets(self._properties_dock)]
        for dock in group:
            if dock.isVisible() and dock.objectName() in HELP_TOPIC_BY_DOCK:
                return HELP_TOPIC_BY_DOCK[dock.objectName()]

        return HELP_TOPIC_BY_CENTRE_TAB.get(
            self._center_tabs.tabText(self._center_tabs.currentIndex()), "projects"
        )

    def _wrap_scrollable(self, widget: QWidget) -> QScrollArea:
        """Defensive floor for form-heavy panels (Docking, Quantum Chemistry):
        if a dock genuinely ends up too short even after tabifying, content
        scrolls instead of overlapping/truncating."""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _restore_window_state(self) -> None:
        """Mirror image of closeEvent()'s save -- both go through the same
        Settings.window_geometry/window_state keys, which existed since an
        earlier phase but were never actually wired up until now."""
        geometry = self._settings.window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        state = self._settings.window_state()
        if state:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        self._settings.set_window_geometry(self.saveGeometry())
        self._settings.set_window_state(self.saveState())
        super().closeEvent(event)

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
        file_menu.addAction("Import Macromolecule...", self._import_macromolecule)
        file_menu.addAction("Receptor Library...", self._open_receptor_library)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        undo_action = self._undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut("Ctrl+Z")
        redo_action = self._undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut("Ctrl+Y")
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()
        # Real Ketcher toolbar actions, same `trigger_toolbar_action`
        # bridge as the explicit-hydrogens/3D-viewer ones -- these mutate
        # the structure (Aromatize/Dearomatize/Layout/Clean Up) or run a
        # real calculation on it (Calculate CIP, Check Structure), so they
        # belong under Edit, not View. Ketcher reports the resulting
        # structure change through its own normal `change` event, which
        # already flows back through EditorBackend.edited ->
        # EditStructureCommand -> the undo stack, same as any in-canvas
        # edit -- no separate command needed here.
        for label, test_id in (
            ("Aromatize", "Aromatize button"),
            ("Dearomatize", "Dearomatize button"),
            ("Layout (Recalculate Coordinates)", "Layout button"),
            ("Clean Up", "Clean Up button"),
            ("Calculate CIP (Stereo Descriptors)", "Calculate CIP button"),
            ("Check Structure...", "Check Structure button"),
        ):
            edit_menu.addAction(label, lambda test_id=test_id: self._editor.trigger_toolbar_action(test_id))

        # Copying an identifier and renaming already existed, but ONLY on
        # the Project Explorer's right-click menu, where they were reported
        # as missing entirely -- a narrow dock with two entries gives you
        # very little to right-click, and `itemAt()` returns nothing for the
        # empty space below the list, so the menu simply never appeared.
        # Duplicated here rather than moved: the context menu is the faster
        # route once you know it exists, and the menu bar is how you find
        # out it does.
        edit_menu.addSeparator()
        structure_menu = edit_menu.addMenu("Copy Structure As")
        for label, kind in (
            ("SMILES", "smiles"),
            ("InChI", "inchi"),
            ("InChIKey", "inchikey"),
            ("Molfile (MDL molblock)", "molfile"),
        ):
            structure_menu.addAction(label, lambda kind=kind: self._copy_structure_as(kind))

        paste_action = edit_menu.addAction("Paste Structure", self._paste_structure)
        # NOT Ctrl+V. Ketcher owns that inside the drawing canvas for
        # pasting fragments, and stealing it would break in-canvas editing
        # to serve the rarer whole-structure case.
        paste_action.setShortcut("Ctrl+Shift+V")

        edit_menu.addSeparator()
        # Wrapped in a lambda, not passed directly: QAction.triggered emits
        # `checked` (False), which would arrive as the `molecule` argument
        # and read as "a molecule was supplied" everywhere except an
        # `is None` check.
        edit_menu.addAction("Duplicate Molecule", lambda: self._duplicate_molecule())
        edit_menu.addAction("Rename Molecule...", lambda: self._rename_molecule())

        self._view_menu = self.menuBar().addMenu("&View")
        for dock in self.findChildren(QDockWidget):
            self._view_menu.addAction(dock.toggleViewAction())
        self._view_menu.addSeparator()
        structure_display_menu = self._view_menu.addMenu("2D Structure Display")
        self._add_structure_display_toggle(
            structure_display_menu, "Show Carbon Labels", "carbonExplicitly", True, False
        )
        self._add_structure_display_toggle(
            structure_display_menu,
            "Show Valence (abnormal valence only)",
            "showValence",
            True,
            False,
        )
        structure_display_menu.addSeparator()
        # These two are real Ketcher toolbar buttons, not render options --
        # "explicit hydrogens" actually adds/removes atoms (confirmed live:
        # ethanol's 3-heavy-atom structure gained 6 real H atoms), and "3D
        # Viewer" opens Ketcher's own Miew dialog for the CURRENT structure
        # (confirmed live, not just for inserted 3D templates) -- see
        # KetcherEditorBackend.trigger_toolbar_action for why these go
        # through Ketcher's own button rather than `set_render_option`
        # (there's no public API for either).
        structure_display_menu.addAction(
            "Toggle Explicit Hydrogens",
            lambda: self._editor.trigger_toolbar_action("Add/Remove explicit hydrogens button"),
        )
        structure_display_menu.addAction(
            "Open 3D Viewer (Miew)...", lambda: self._editor.trigger_toolbar_action("3D Viewer button")
        )
        structure_display_menu.addAction("Send to 3D Viewer Tab", self._send_to_3d_viewer)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction("Identify Structure Online...", lambda: self._identify_structure())
        tools_menu.addAction("External Tools...", self._show_external_tools_dialog)

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
        # F1 is the conventional key, and it opens help for whichever panel
        # is in front rather than a table of contents -- the question being
        # asked is almost always about the thing currently on screen.
        contents_action = help_menu.addAction("Help for the Current Panel", self._show_help)
        contents_action.setShortcut("F1")
        for label, key in (
            ("User Guide", "projects"),
            ("Getting Started", "where-data-lives"),
            ("Scientific Limitations", "limits-nmr"),
        ):
            help_menu.addAction(label, lambda key=key: self._show_help(key))
        help_menu.addSeparator()
        help_menu.addAction("Open Log Folder", self._open_log_folder)
        help_menu.addAction("About OpenChem Studio", self._show_about)

    def _add_structure_display_toggle(
        self, menu: QMenu, label: str, option_name: str, checked_value: object, unchecked_value: object
    ) -> None:
        """Proxies one of Ketcher's own confirmed-live render options
        (`ketcher.editor.render.options` -- see KetcherEditorBackend.
        set_render_option) into a checkable View menu action, so it's
        reachable from the app's own menu chrome instead of only Ketcher's
        in-canvas UI. Fire-and-forget like the rest of the editor bridge --
        Ketcher applies the option and re-renders immediately, no
        confirmation round-trip.
        """
        action = QAction(label, self)
        action.setCheckable(True)
        action.toggled.connect(
            lambda checked: self._editor.set_render_option(
                option_name, checked_value if checked else unchecked_value
            )
        )
        menu.addAction(action)

    # --- project lifecycle --------------------------------------------------

    def _new_project(self) -> None:
        self._set_project(ProjectModel(name="Untitled project"))

    def _set_project(self, project: ProjectModel) -> None:
        self._session.set_project(project)
        self._project_explorer.set_project(project)
        self._docking_panel.set_project(project)
        self._quantum_chemistry_panel.set_project(project)
        self._property_panel.set_project(project)
        self._alignment_panel.set_project(project)
        self._batch_panel.set_project(project)
        self.setWindowTitle(f"OpenChem Studio - {project.name}")
        if not project.molecules:
            # A brand-new (or loaded-but-empty) project has nothing selected,
            # so the 2D editor's target molecule stays None and every edit is
            # silently discarded (MoleculeEditorWidget._on_editor_edited bails
            # when self._molecule is None) until the user does File > New
            # Molecule by hand. Auto-create one so drawing works immediately.
            self._new_molecule()

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
        project = self._session.project
        name = project.unique_molecule_name("New molecule") if project is not None else "New molecule"
        self.add_molecule(MoleculeModel(display_name=name))

    def add_molecule(self, molecule: MoleculeModel) -> None:
        if self._session.project is None:
            logger.warning("add_molecule called with no project open; ignoring")
            return
        command = AddMoleculeCommand(self._session.project, molecule, self._services.event_bus)
        self._undo_stack.push(command)
        self._project_explorer.refresh()
        self._refresh_molecule_combos()
        self._services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    def _add_generated_structure(self, molblock: str, label: str) -> None:
        """Take a structure a calculator generated -- a chosen
        stereoisomer, tautomer or resonance form -- into the project as a
        real molecule.

        Routed through `add_molecule` so it lands on the undo stack and
        selects the new molecule, exactly like importing one. The label
        the generator gave the entry becomes the display name, since
        "Isomer 3 (S,R)" is more use in the explorer than "Molecule 7".
        """
        molecule = MoleculeModel(display_name=label or "Generated structure")
        try:
            self._services.chemistry_engine.set_structure_from_molblock(molecule, molblock)
        except Exception:  # noqa: BLE001 - report, never crash the dialog that called in
            logger.exception("Could not add generated structure %r to the project", label)
            return
        self.add_molecule(molecule)

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
        self._refresh_molecule_combos()

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

    # --- macromolecule lifecycle -------------------------------------------------

    def _import_macromolecule(self) -> None:
        if self._session.project is None:
            return
        from openchem.chem.structure_io import STRUCTURE_FILE_FILTER, read_structure_file

        path_str, _ = QFileDialog.getOpenFileName(
            self, "Import Macromolecule", filter=STRUCTURE_FILE_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        # BinaryCIF and gzip are unpacked here rather than carried inward:
        # `read_structure_file` returns Mol*'s own format vocabulary (see
        # MacromoleculeModel's docstring), so there is still no naming
        # scheme to translate between and no consumer learns a new format.
        try:
            structure_text, source_format = read_structure_file(path)
        except (OSError, ValueError) as exc:
            logger.exception("Failed to read macromolecule file")
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        macromolecule = MacromoleculeModel(
            display_name=path.stem, structure_text=structure_text, source_format=source_format
        )
        self.add_macromolecule(macromolecule)

    def _open_receptor_library(self) -> None:
        """Browse the curated catalogue, then download and import a target.

        The download happens HERE rather than in the dialog, so the dialog
        stays a pure chooser and the import path is the same one
        `_import_macromolecule` already uses. The structure is fetched only
        after the user accepts -- browsing costs nothing.
        """
        if self._session.project is None:
            return
        from openchem.services.receptor_library_service import entry_metadata, fetch_structure
        from openchem.ui.dialogs.receptor_library_dialog import ReceptorLibraryDialog

        dialog = ReceptorLibraryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dialog.selected_entry()
        if entry is None:
            return

        # A first download of a large cryo-EM structure is a few seconds on
        # a slow link, and it blocks the GUI thread. A busy cursor is the
        # honest minimum; a JobManager job would be the right answer if
        # this ever grew to fetching several at once.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            structure_text, source_format = fetch_structure(entry.pdb_id)
        except Exception as exc:  # noqa: BLE001 - reported, never crashes the window
            logger.exception("Receptor library download failed for %s", entry.pdb_id)
            QMessageBox.critical(self, "Download failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.add_macromolecule(
            MacromoleculeModel(
                display_name=f"{entry.target} ({entry.pdb_id})",
                structure_text=structure_text,
                source_format=source_format,
                # Carries `ligand_code`, which is what lets the docking
                # panel place the search box without asking the user to
                # remember which component defined the site.
                metadata=entry_metadata(entry),
            )
        )

    def add_macromolecule(self, macromolecule: MacromoleculeModel) -> None:
        if self._session.project is None:
            logger.warning("add_macromolecule called with no project open; ignoring")
            return
        command = AddMacromoleculeCommand(self._session.project, macromolecule)
        self._undo_stack.push(command)
        self._macromolecule_viewer.load_macromolecule(
            macromolecule.structure_text, macromolecule.source_format
        )
        self._center_tabs.setCurrentWidget(self._macromolecule_viewer.widget())
        self._refresh_molecule_combos()

    def _on_undo_index_changed(self, _index: int) -> None:
        """Re-read the project into every dropdown after an undo or a redo.

        The panels are refreshed imperatively by whichever method pushed a
        command -- `add_molecule`, `add_macromolecule` and the import paths
        all call `_refresh_molecule_combos` themselves. Undo and redo do
        not go through any of those, so nothing told the panels the project
        had changed back.

        Measured: importing a receptor and pressing Ctrl+Z removed it from
        the project and LEFT IT IN the Docking panel's receptor list, where
        it could still be selected and docked against. `AddMacromoleculeCommand`
        publishes no event at all -- unlike its molecule counterpart -- so
        there was nothing to subscribe to.

        Hooked to the stack rather than fixing that one command, because
        this is a whole class: any command that changes what a dropdown
        lists has the same hole, and `repopulate` restores the current
        selection by uuid so a spurious refresh costs nothing.
        """
        self._refresh_molecule_combos()
        # The pose table is not a dropdown and is not rebuilt from the
        # project, so it needs telling separately.
        self._docking_panel.sync_with_project(self._session.project)
        self._clear_stale_pose_overlay()

    def _clear_stale_pose_overlay(self) -> None:
        """Drop the docked ligand and its binding-site colouring when the
        result they came from has been undone.

        The receptor itself is left loaded: it is still in the project, and
        reloading it would throw away the camera position for no reason.
        What must go is the pose drawn into it and the interaction layers
        painted from that pose -- a ligand shown sitting in a binding site
        is a claim, and it should not outlive the result that made it.
        """
        project = self._session.project
        if project is None or project.docking_results:
            return
        if not self._showed_a_pose:
            return
        self._showed_a_pose = False
        receptor_uuid = self._last_pose_receptor_uuid
        receptor = project.find_macromolecule(receptor_uuid) if receptor_uuid else None
        if receptor is not None:
            self._macromolecule_viewer.load_macromolecule(
                receptor.structure_text, receptor.source_format
            )
        else:
            self._macromolecule_viewer.clear()
        self._macromolecule_viewer.apply_visualizations([])

    def _refresh_molecule_combos(self) -> None:
        """DockingPanel's receptor/ligand combos and QuantumChemistryPanel's
        molecule combo are only populated when `set_project` runs (project
        open/new) -- confirmed live: a molecule or macromolecule added
        afterward (File > New Molecule, an import, a plugin search result,
        or the empty-project auto-create in `_set_project`) never appeared
        in either dropdown, making them look permanently broken/unusable.
        `set_project` just re-reads the current project's lists, so calling
        it again here is a cheap, correct refresh -- same project object,
        no re-selection side effects beyond what a combo repopulate implies.
        """
        self._docking_panel.set_project(self._session.project)
        self._quantum_chemistry_panel.set_project(self._session.project)
        self._alignment_panel.set_project(self._session.project)
        self._batch_panel.set_project(self._session.project)

    # --- event handlers --------------------------------------------------------

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._session.select_molecule(event.molecule_uuid)
        molecule = self._current_molecule()
        self._editor.set_molecule(molecule)
        self._viewer3d.set_molecule(molecule)
        if molecule is not None:
            self._services.descriptor_service.request_descriptors(molecule)
            self._publish_molecule_snapshot(molecule)

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        self._session.mark_dirty()
        molecule = self._current_molecule()
        if molecule is not None and molecule.uuid == event.molecule_uuid:
            self._services.descriptor_service.request_descriptors(molecule)
            self._publish_molecule_snapshot(molecule)

    def _publish_molecule_snapshot(self, molecule: MoleculeModel) -> None:
        """Gives plugins (which have no access to SessionManager/ProjectModel)
        a read-only view of identity fields DescriptorComputed/MoleculeChanged
        don't carry — see MoleculeSnapshotUpdated in events/events.py."""
        energies = [c.energy for c in molecule.conformers if c.energy is not None]
        self._services.event_bus.publish(
            MoleculeSnapshotUpdated(
                molecule_uuid=molecule.uuid,
                display_name=molecule.display_name,
                canonical_smiles=molecule.canonical_smiles,
                inchi=molecule.inchi,
                inchikey=molecule.inchikey,
                conformer_count=len(molecule.conformers),
                lowest_conformer_energy=min(energies) if energies else None,
            )
        )

    def _on_conformers_ready(self, event: ConformersReady) -> None:
        molecule = self._current_molecule()
        if molecule is None or molecule.uuid != event.molecule_uuid:
            return
        command = SetConformersCommand(molecule, event.conformers, self._services.event_bus)
        self._undo_stack.push(command)

    def _on_conformers_changed(self, event: ConformersChanged) -> None:
        # Fires after SetConformersCommand/AddConformerCommand redo AND
        # undo, and after ConformersInvalidated's own ConformersChanged
        # (EditStructureCommand) -- one handler covers "conformers just
        # appeared," "conformer generation was undone," and "structure
        # edited, conformers cleared" alike. Shape descriptors (Phase 10a)
        # need a real 3D conformer, not the flat 2D molblock, to compute for
        # real (see Phase 14b) -- RDKitConformerProvider sorts its results
        # ascending by energy (Phase 14c), so conformers[0] is the best one
        # to use when one exists; falling back to the plain molblock when
        # the list is empty naturally reverts descriptors to "needs a
        # conformer."
        molecule = self._current_molecule()
        if molecule is None or molecule.uuid != event.molecule_uuid:
            return
        best_molblock = molecule.conformers[0].molblock if molecule.conformers else None
        self._services.descriptor_service.request_descriptors(molecule, molblock=best_molblock)
        self._publish_molecule_snapshot(molecule)

    def _on_quantum_chemistry_result_ready(self, event: QuantumChemistryResultReady) -> None:
        # Descriptors reuse the EXISTING DescriptorComputed mechanism
        # (PropertyPanel already displays these) rather than inventing a
        # separate quantum-chemistry-specific display path -- descriptors
        # were never cached on the molecule to begin with (see
        # docs/ARCHITECTURE.md), so ORCA's results are just another provider's
        # values, not a special case.
        for descriptor in event.descriptors:
            self._services.event_bus.publish(DescriptorComputed(descriptor=descriptor))

        if event.conformer is None:
            return
        molecule = self._session.project.find_molecule(event.molecule_uuid) if self._session.project else None
        if molecule is None:
            return
        # AddConformerCommand, not SetConformersCommand -- an ORCA-optimized
        # geometry is added alongside whatever conformers already exist,
        # never wiping them out.
        command = AddConformerCommand(molecule, event.conformer, self._services.event_bus)
        self._undo_stack.push(command)

    def _on_docking_result_ready(self, event: DockingResultReady) -> None:
        if self._session.project is None:
            return
        command = SetDockingResultCommand(self._session.project, event.result)
        self._undo_stack.push(command)

        if not event.result.poses:
            return
        receptor = self._session.project.find_macromolecule(event.result.receptor_macromolecule_uuid)
        if receptor is None:
            return
        self._macromolecule_viewer.load_macromolecule(receptor.structure_text, receptor.source_format)
        best_pose = min(event.result.poses, key=lambda p: p.binding_affinity_kcal_mol)
        self._macromolecule_viewer.load_additional_structure(best_pose.pose_molblock, "mol", "docked ligand")
        # Colour the binding site from the interaction analysis this pose
        # already carries (chem/pose_analysis.py wrote it into metadata when
        # the job finished) -- blue where the ligand hydrogen-bonds, red
        # where it clashes. Empty for a pose with neither, which correctly
        # clears rather than leaving a previous pose's colouring behind.
        self._macromolecule_viewer.apply_visualizations(
            build_interaction_layers(best_pose.metadata)
        )
        self._showed_a_pose = True
        self._last_pose_receptor_uuid = receptor.uuid
        self._center_tabs.setCurrentWidget(self._macromolecule_viewer.widget())

    # --- structure clipboard ---------------------------------------------------

    def _copy_structure_as(self, kind: str) -> None:
        """Put one representation of the current structure on the clipboard.

        Most structures have no verified IUPAC name (the naming benchmark
        puts even PubChem's coverage well short of complete), so an
        identifier is routinely the only way to refer to a molecule at
        all -- which is why this is a menu action rather than an export
        dialog.
        """
        molecule = self._current_molecule()
        if molecule is None or not molecule.molblock:
            self.statusBar().showMessage("Select a molecule with a structure first.", 5000)
            return
        if kind == "molfile":
            text = molecule.molblock
        else:
            text = identifier_for_molblock(molecule.molblock, kind)
        if not text:
            # identifier_for_molblock returns "" for a structure it cannot
            # parse rather than raising, so an empty result is the normal
            # failure and belongs in the status bar, not a modal.
            self.statusBar().showMessage(f"Could not produce a {kind} for this structure.", 5000)
            return
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"Copied {kind} to the clipboard.", 3000)

    def _paste_structure(self) -> None:
        """Replace the current molecule's structure with whatever is on the clipboard.

        Accepts a molfile, an InChI or a SMILES without being told which
        (see chem/structure_clipboard.py). Routed through
        `EditStructureCommand` so it lands on the undo stack like any
        in-canvas edit -- pasting over a structure you meant to keep has to
        be Ctrl+Z-able.
        """
        molecule = self._current_molecule()
        if molecule is None:
            self.statusBar().showMessage("Select a molecule to paste into first.", 5000)
            return
        parsed = parse_structure_text(QGuiApplication.clipboard().text())
        if parsed is None:
            self.statusBar().showMessage(
                "The clipboard does not contain a structure (expected SMILES, InChI or a molfile).",
                6000,
            )
            return
        self._undo_stack.push(
            EditStructureCommand(
                self._services.chemistry_engine, molecule, parsed.molblock, self._services.event_bus
            )
        )
        self._editor.set_molecule(molecule)
        self.statusBar().showMessage(f"Pasted a structure from {parsed.source_format}.", 3000)

    def _duplicate_molecule(self, molecule: MoleculeModel | None = None) -> None:
        """Copy `molecule` (default: the selected one) into a new one, structure and all.

        This is the "draw aziridine, now make azirine from it" path: the
        alternative was redrawing the second molecule from scratch,
        because there was no way to get a structure out of one molecule
        and into another at all.

        Conformers are deliberately NOT copied. They belong to the
        geometry that produced them, and the reason to duplicate a
        molecule is almost always to change it -- carrying them over would
        leave conformers describing a structure that no longer exists,
        which is the same staleness `EditStructureCommand` already clears
        on an edit.
        """
        molecule = molecule if molecule is not None else self._current_molecule()
        if molecule is None:
            self.statusBar().showMessage("Select a molecule to duplicate first.", 5000)
            return
        project = self._session.project
        if project is None:
            return
        # "X copy", not "X 2": the plain numeric suffix is for new empty
        # molecules, and applying it here produced "New molecule 3 2",
        # which reads as a version number rather than a copy.
        copy = MoleculeModel(
            display_name=project.unique_molecule_name(f"{molecule.display_name} copy")
        )
        if molecule.molblock:
            self._services.chemistry_engine.set_structure_from_molblock(copy, molecule.molblock)
        self.add_molecule(copy)
        self.statusBar().showMessage(f"Duplicated as '{copy.display_name}'.", 3000)

    def _rename_molecule(self) -> None:
        molecule = self._current_molecule()
        if molecule is None:
            self.statusBar().showMessage("Select a molecule to rename first.", 5000)
            return
        new_name, accepted = QInputDialog.getText(
            self, "Rename Molecule", "Name:", text=molecule.display_name
        )
        new_name = new_name.strip()
        if not accepted or not new_name or new_name == molecule.display_name:
            return
        self._undo_stack.push(
            RenameMoleculeCommand(molecule, new_name, self._services.event_bus)
        )

    def _identify_structure(self, molecule: MoleculeModel | None = None) -> None:
        """Ask PubChem what this structure is.

        Opening the dialog sends nothing -- it shows what WOULD be sent and
        waits for a button, per the privacy policy stated in
        chem/naming_providers.py.
        """
        molecule = molecule if molecule is not None else self._current_molecule()
        if molecule is None or not molecule.molblock:
            self.statusBar().showMessage("Select a molecule with a structure first.", 5000)
            return
        smiles = identifier_for_molblock(molecule.molblock, "smiles")
        inchikey = identifier_for_molblock(molecule.molblock, "inchikey")
        if not smiles:
            self.statusBar().showMessage("This structure could not be read for lookup.", 5000)
            return
        StructureLookupDialog(smiles, inchikey, self).exec()

    def _current_molecule(self) -> MoleculeModel | None:
        if self._session.project is None or self._session.selected_molecule_uuid is None:
            return None
        return self._session.project.find_molecule(self._session.selected_molecule_uuid)

    def _send_to_3d_viewer(self) -> None:
        """Bridges the 2D Editor to the "3D Viewer" tab (3Dmol.js) --
        which already has style switching (stick/ball-stick/sphere/line,
        `MoleculeViewer3DWidget._style_combo`) and the LogP/partial-charge
        color-by/Property Inspector integration Ketcher's own Miew dialog
        doesn't have. If no conformer exists yet, requests one first (same
        provider/count/optimize choice "Generate Conformers..." already
        uses) rather than sending an empty 3D view.
        """
        molecule = self._current_molecule()
        if molecule is None:
            return
        if not molecule.conformers:
            self._services.conformer_service.request_conformers(molecule, 10, optimize=True)
        self._center_tabs.setCurrentWidget(self._viewer3d)

    # --- UIRegistry protocol (see plugins/ui_registry.py) -----------------------
    # PluginManager depends on these methods structurally, never on
    # MainWindow itself. `add_molecule` is the fifth one, defined above under
    # "molecule lifecycle" since it shares `_new_molecule`'s implementation.

    def add_panel(self, panel_id: str, widget_factory: Callable[[], QWidget]) -> None:
        if panel_id in self._plugin_panels:
            self.remove_panel(panel_id)
        widget = widget_factory()
        dock = self._add_dock(panel_id, widget, Qt.DockWidgetArea.RightDockWidgetArea)
        # Join the same tab group as Properties/Docking/Quantum Chemistry
        # rather than taking a fresh vertical slice of the right dock area.
        self.tabifyDockWidget(self._properties_dock, dock)
        self._plugin_panels[panel_id] = dock
        self._view_menu.addAction(dock.toggleViewAction())

    def remove_panel(self, panel_id: str) -> None:
        dock = self._plugin_panels.pop(panel_id, None)
        if dock is None:
            return
        self.removeDockWidget(dock)
        dock.deleteLater()

    def reveal_panel(self, panel_id: str) -> None:
        # Confirmed live: every plugin's "focus my panel" menu action
        # (Explain Selected Molecule, Search Chemical Databases, Predict
        # Reaction Products) only called `widget.setFocus()`, which is
        # invisible when that panel is hidden behind another tab in its
        # tabified dock group -- indistinguishable from the click doing
        # nothing at all. show()+raise_() actually switches to its tab.
        dock = self._plugin_panels.get(panel_id)
        if dock is None:
            return
        dock.show()
        dock.raise_()

    def add_menu_action(self, plugin_id: str, label: str, callback: Callable[[], None]) -> None:
        action = QAction(label, self)
        # QAction.triggered emits (checked: bool); the protocol promises
        # callers a zero-arg callback, so that bool must be swallowed here
        # rather than leaking into every caller's callback signature.
        action.triggered.connect(lambda checked=False: callback())
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

    def _show_batch_analysis(self, table) -> None:
        """Correlation / chemical space / clustering / distributions.

        Owned here rather than by `BatchPanel` for the same reason the
        Receptor Library download is: a panel that lives in a dock should
        not be the parent of a modal window, and the project the analytics
        need to read structures from is the session's, not the panel's.
        """
        from openchem.ui.dialogs.batch_analysis_dialog import BatchAnalysisDialog

        BatchAnalysisDialog(
            table, self._services.chemistry_engine, self._session.project, self
        ).exec()

    def _show_virtual_screening(self) -> None:
        from openchem.ui.dialogs.virtual_screening_dialog import VirtualScreeningDialog

        VirtualScreeningDialog(
            self._services.screening_service,
            self._services.event_bus,
            self._session.project,
            self,
        ).exec()

    def _show_external_tools_dialog(self) -> None:
        dialog = ExternalToolsDialog(self._settings, self)
        dialog.exec()

    def _open_log_folder(self) -> None:
        """A log nobody can find is barely better than no log at all --
        and the failure that motivated writing one to disk was reported by
        a user who had no reason to know a `logs` directory existed."""
        from openchem.app.logging_setup import log_directory

        directory = log_directory()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "No log folder", f"Could not open {directory}: {exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _show_about(self) -> None:
        # Settings is passed through so the dialog can report which external
        # tools are actually resolved -- a configured path that no longer
        # exists reads identically to a working one until something looks.
        AboutDialog(self._settings, self).exec()
