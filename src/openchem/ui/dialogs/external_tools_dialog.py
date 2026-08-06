from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import Settings
from openchem.plugins.async_task import run_async
from openchem.services.tool_download_service import (
    ORCA_DOCS_PAGE,
    ORCA_DOWNLOAD_PAGE,
    VinaReleaseAsset,
    describe_orca_platform_hint,
    describe_vina_status,
    download_vina_asset,
    fetch_latest_vina_release,
)
from openchem.ui.dialogs import external_tool_catalog as catalog
from openchem.ui.dialogs.external_tool_tabs import (
    InterpreterSidecarTab,
    ManagedAssetTab,
    PathRow,
    ToolTab,
    progress_reporter,
)

logger = logging.getLogger("openchem.ui")


#: Qt property carrying which sidecar a "Remove from Disk" button removes.
_COMPONENT_KEY_PROPERTY = "openchem_component_key"


class _AdmetSidecarTab(InterpreterSidecarTab):
    """ADMET, plus the one thing it does differently from every other tab.

    A failed setup must not lose an environment that got built. The
    expensive part is ~1 GB of PyTorch; verification is a few seconds on
    top. When only the check fails -- a cold first model load, a transient
    timeout -- the environment is on disk and usable, and throwing its
    path away leaves the user to hunt for it in a file browser. Recording
    it costs nothing and is honest, because `describe_admet_status`
    already reports a configured but non-working environment as exactly
    that rather than as working.

    This is also the only place that writes a setup outcome to the log.
    Nothing did before, so a failure left no trace anywhere once the
    message box was dismissed -- and that is precisely the state that made
    one real failure impossible to diagnose after the fact.

    Deliberately NOT promoted to the shared path. pkasolver's install is
    larger still and would arguably benefit, but that is a behaviour
    change, and this refactor is meant to be one you can verify by
    inspection.
    """

    def _failed(self, message: str) -> None:
        from openchem.services.admet_setup import default_install_root, interpreter_for

        self.setup_button.setEnabled(True)
        logger.error("ADMET setup failed: %s", message)

        built = interpreter_for(default_install_root())
        if built.is_file():
            self.path_row.set_path(str(built))
            self.status_label.setText(
                f"Setup reported a failure, but an environment exists at the path "
                f"above - press Test to retry the check. ({message})"
            )
            logger.info("ADMET setup: keeping the built environment at %s", built)
            QMessageBox.warning(
                self,
                "ADMET setup incomplete",
                f"{message}\n\nThe environment itself was built, at:\n{built}\n\n"
                "Its path has been kept, so press Test to retry the check, or "
                "run Set Up again to repair it.",
            )
            return

        super()._failed(message)


class ExternalToolsDialog(QDialog):
    """Single home for configuring/obtaining external chemistry tools --
    replaces the two previously-separate `_VinaPathDialog`
    (docking_panel.py) and `_OrcaPathDialog` (quantum_chemistry_panel.py).

    Vina's releases are public, Apache-2.0-licensed GitHub release assets
    (confirmed against the user's own installed `vina_1.2.7_win.exe`), so
    it gets a real Download/Update button. ORCA is registration/EULA-gated
    with no public direct-download URL, so it only ever gets a Browse
    button plus a link to the official download page -- automating that
    isn't possible, and pretending otherwise would be misleading.

    Four of the seven tabs are built from descriptors in
    `external_tool_catalog`, because they were two tabs written twice; see
    `external_tool_tabs`. The three that remain hand-built are the three
    with one implementation each -- Vina's two-phase download, ORCA's
    can't-be-automated tab, and Storage, which is not a tool at all.
    """

    def __init__(
        self, settings: Settings, parent: QWidget | None = None, focus: str = "vina"
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("External Tools")
        self.resize(560, 380)
        self._settings = settings
        # Set before the Storage tab is built, which reads it.
        self._storage_measured = False
        self._tool_tabs: list[ToolTab] = []

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_vina_tab(), "AutoDock Vina")
        self._tabs.addTab(self._build_orca_tab(), "ORCA")
        self._add_sidecar_tab(catalog.pkasolver(), InterpreterSidecarTab)
        # Grouped with pkasolver rather than with the executables above:
        # both are "a Python interpreter, not an executable", and making
        # them look different would imply a difference that is not there.
        self._add_sidecar_tab(catalog.admet(), _AdmetSidecarTab)
        self._add_managed_asset_tab(catalog.java())
        self._add_managed_asset_tab(catalog.nmr_database())
        self._tabs.addTab(self._build_storage_tab(), "Storage")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        if focus == "orca":
            self._tabs.setCurrentIndex(1)
        elif focus == "pkasolver":
            self._tabs.setCurrentIndex(2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)
        layout.addWidget(buttons)

        self._refresh_vina_status()

    # --- Descriptor-driven tabs ---------------------------------------------

    def _add_managed_asset_tab(self, descriptor) -> None:
        tab = ManagedAssetTab(descriptor, self, remove_button_factory=self._remove_button)
        self._register_tab(descriptor, tab)

    def _add_sidecar_tab(self, descriptor, tab_class) -> None:
        tab = tab_class(
            descriptor,
            self,
            settings=self._settings,
            remove_button_factory=self._remove_button,
        )
        self._register_tab(descriptor, tab)

    def _register_tab(self, descriptor, tab: ToolTab) -> None:
        self._tool_tabs.append(tab)
        self._tabs.addTab(tab, descriptor.title)
        self._alias_widgets(descriptor.key, tab)

    # These aliases exist ONLY so `tests/test_external_tools_dialog.py`
    # could stay byte-identical across this refactor -- an untouched suite
    # is the whole safety net for a change that rewrites the file it
    # tests. The widgets themselves live on the tab objects, which is
    # where new code should reach for them.
    _ALIAS_PREFIXES = {
        "pkasolver": "_pkasolver",
        "admet": "_admet",
        "java": "_java",
        "nmr_index": "_nmr_db",
    }

    def _alias_widgets(self, key: str, tab: ToolTab) -> None:
        prefix = self._ALIAS_PREFIXES[key]
        setattr(self, f"{prefix}_status_label", tab.status_label)
        setattr(self, f"{prefix}_setup_button", tab.setup_button)
        setattr(self, f"{prefix}_remove_button", tab.remove_button)
        if isinstance(tab, InterpreterSidecarTab):
            setattr(self, f"{prefix}_path_edit", tab.path_row.edit)
            setattr(self, f"{prefix}_locate_button", tab.locate_button)

    def _tab_for(self, key: str) -> ToolTab:
        for tab in self._tool_tabs:
            if tab.descriptor.key == key:
                return tab
        raise KeyError(key)

    def _on_pkasolver_path_edited(self) -> None:
        self._tab_for("pkasolver").path_row.commit()

    def _on_admet_path_edited(self) -> None:
        self._tab_for("admet").path_row.commit()

    # --- Vina tab -----------------------------------------------------------

    def _build_vina_tab(self) -> QWidget:
        from openchem.services.sidecar_env import find_program

        tab = QWidget(self)

        self._vina_row = PathRow(
            tab,
            settings=self._settings,
            setting_key="docking/vina_executable_path",
            browse_title="Select the folder containing Vina",
            finder=lambda root: find_program(root, ("vina",)),
            description="Vina executable",
            on_changed=self._refresh_vina_status,
        )
        self._vina_path_edit = self._vina_row.edit

        self._vina_status_label = QLabel("Checking...", tab)
        self._vina_download_button = QPushButton("Check for Updates / Download...", tab)
        self._vina_download_button.clicked.connect(self._on_vina_download_clicked)

        note = QLabel(
            "AutoDock Vina's official releases are public, Apache-2.0-licensed "
            "executables published on GitHub (ccsb-scripps/AutoDock-Vina) -- "
            "downloading one here is the same file you'd get from the releases "
            "page yourself.",
            tab,
        )
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Executable:", self._vina_row)
        form.addRow("Status:", self._vina_status_label)

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addWidget(self._vina_download_button)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _refresh_vina_status(self) -> None:
        self._vina_status_label.setText(describe_vina_status(self._vina_row.text()))

    def _on_vina_download_clicked(self) -> None:
        self._vina_download_button.setEnabled(False)
        self._vina_download_button.setText("Checking GitHub for the latest release...")
        run_async(
            fetch_latest_vina_release,
            RuntimeError,
            self._on_vina_release_fetched,
            self._on_vina_download_failed,
        )

    def _on_vina_release_fetched(self, asset: VinaReleaseAsset) -> None:
        self._vina_download_button.setEnabled(True)
        self._vina_download_button.setText("Check for Updates / Download...")

        # Per this app's own download policy: never fetch a file without
        # showing the exact filename/source/size and getting an explicit
        # yes first -- run_async's background fetch above only *looked up*
        # release metadata, nothing has been downloaded yet.
        size_mb = asset.size_bytes / (1024 * 1024)
        answer = QMessageBox.question(
            self,
            "Download AutoDock Vina",
            (
                f"Download AutoDock Vina {asset.version}?\n\n"
                f"File: {asset.name}\n"
                f"Source: {asset.download_url}\n"
                f"Size: {size_mb:.1f} MB\n\n"
                "It will be saved to OpenChem Studio's own tools folder and "
                "configured automatically."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._vina_download_button.setEnabled(False)
        self._vina_download_button.setText(f"Downloading {asset.name}...")
        run_async(
            lambda: download_vina_asset(asset),
            RuntimeError,
            self._on_vina_download_finished,
            self._on_vina_download_failed,
        )

    def _on_vina_download_finished(self, path: Path) -> None:
        self._vina_download_button.setEnabled(True)
        self._vina_download_button.setText("Check for Updates / Download...")
        self._vina_row.set_path(str(path))
        QMessageBox.information(self, "Download complete", f"AutoDock Vina installed to:\n{path}")

    def _on_vina_download_failed(self, message: str) -> None:
        self._vina_download_button.setEnabled(True)
        self._vina_download_button.setText("Check for Updates / Download...")
        QMessageBox.critical(self, "Download failed", message)

    # --- ORCA tab -------------------------------------------------------------

    def _build_orca_tab(self) -> QWidget:
        from openchem.services.sidecar_env import find_program

        tab = QWidget(self)

        self._orca_row = PathRow(
            tab,
            settings=self._settings,
            setting_key="orca/executable_path",
            browse_title="Select the folder ORCA is installed in",
            finder=lambda root: find_program(root, ("orca",)),
            description="ORCA executable",
        )
        self._orca_path_edit = self._orca_row.edit

        get_orca_button = QPushButton("Get ORCA (FACCTS account required)...", tab)
        get_orca_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ORCA_DOWNLOAD_PAGE)))
        docs_button = QPushButton("ORCA Documentation...", tab)
        docs_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ORCA_DOCS_PAGE)))
        get_orca_row = QHBoxLayout()
        get_orca_row.addWidget(get_orca_button)
        get_orca_row.addWidget(docs_button)

        identity_note = QLabel(
            'This is the quantum-chemistry program named "ORCA" from FACCTS '
            "GmbH -- a genuinely generic name, easy to confuse with unrelated "
            "software. Its downloads used to live on a Max Planck-hosted "
            '"orcaforum" site; that link is now dead. FACCTS\' own customer '
            "portal (free registration required) is the current, correct "
            "source -- OpenChem Studio can't fetch it automatically because "
            "ORCA's license doesn't allow automated/redirected downloads.",
            tab,
        )
        identity_note.setWordWrap(True)

        which_build_note = QLabel(describe_orca_platform_hint(), tab)
        which_build_note.setWordWrap(True)

        after_download_note = QLabel(
            "After installing, Browse to the ORCA executable above -- it's "
            'usually named "orca.exe" (Windows) or "orca" (Linux/macOS) '
            "inside wherever you extracted/installed it.",
            tab,
        )
        after_download_note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Executable:", self._orca_row)

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addLayout(get_orca_row)
        layout.addWidget(identity_note)
        layout.addWidget(which_build_note)
        layout.addWidget(after_download_note)
        layout.addStretch(1)
        return tab

    # --- Removal, shared by the tool tabs and the Storage table ---------------

    def _remove_button(self, parent: QWidget, key: str, label: str) -> QPushButton:
        """A "Remove from Disk" button for one sidecar's OWN tab.

        The Storage tab has had a working Remove for every component all
        along, but nobody standing on a tool's own tab -- having just been
        told that tool is missing -- thinks to go looking under Storage for
        it. The decision to remove a tool is made where you learn you do
        not want it, so the button belongs there too.

        Same `_on_remove_component` behind both: one confirmation, one set
        of paths, one refresh path. A second implementation is how the two
        would drift.
        """
        button = QPushButton("Remove from Disk...", parent)
        button.setToolTip(f"Delete {label} and free the space it uses.")
        # A bound method, never a lambda capturing `self`: PySide6 holds a
        # connected plain callable strongly and a QObject's bound method
        # weakly, so the lambda form roots this object for the life of the
        # process -- past refcounting AND past the cyclic collector. See
        # property_panel._section_for for the measurement.
        button.setProperty(_COMPONENT_KEY_PROPERTY, key)
        button.clicked.connect(self._on_remove_button_clicked)
        return button

    def _on_remove_button_clicked(self, _checked: bool = False) -> None:
        button = self.sender()
        if button is not None:
            self._on_remove_component(button.property(_COMPONENT_KEY_PROPERTY))

    def _on_remove_component(self, key: str) -> None:
        from openchem.services import sidecar_inventory

        component = sidecar_inventory.find(key, self._settings)
        answer = QMessageBox.question(
            self,
            f"Remove {component.label}",
            (
                f"Delete {component.label}?\n\n"
                f"Frees: {sidecar_inventory._human(component.size_bytes())}\n"
                + "\n".join(f"Removes: {path}" for path in component.paths)
                + f"\n\n{component.reinstall_hint}\n\nThis cannot be undone. Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            freed = sidecar_inventory.uninstall(component, self._settings)
        except sidecar_inventory.UninstallError as exc:
            QMessageBox.critical(self, "Could not remove", str(exc))
            self._refresh_storage()
            return
        self._refresh_storage()
        # The tool's own tab still shows its old path/status until told.
        self._refresh_tool_tabs()
        QMessageBox.information(
            self,
            "Removed",
            f"{component.label} removed, freeing {sidecar_inventory._human(freed)}.",
        )

    def _refresh_tool_tabs(self) -> None:
        """Re-read every tool's status after a removal.

        Without this the pkasolver tab would keep showing the interpreter
        path that was just deleted and cleared from settings -- the same
        confusing configured-but-broken state this whole feature exists
        to avoid.

        Iterating the tabs rather than naming them one by one is not
        tidiness: the hand-written version listed pkasolver, Java, NMR and
        Vina and SILENTLY OMITTED ADMET, so removing the ADMET environment
        left its own tab showing the path that had just been deleted --
        exactly the state this method exists to prevent.
        """
        for tab in self._tool_tabs:
            tab.refresh()
        self._vina_row.reload()
        self._refresh_vina_status()

    # --- Storage ------------------------------------------------------------

    def _build_storage_tab(self) -> QWidget:
        """Not a sidecar, and deliberately not forced into their shape.

        The other six tabs configure or obtain one tool. This one manages
        where ALL of them live: it owns the components table, the
        move/reset flow, and the lazy sizing below.
        """
        from openchem.services import storage_service

        tab = QWidget(self)
        self._storage_status_label = QLabel(storage_service.describe_status(), tab)
        self._storage_status_label.setWordWrap(True)

        self._storage_usage_label = QLabel("", tab)
        self._storage_usage_label.setWordWrap(True)
        self._storage_usage_label.setStyleSheet("font-family: monospace;")
        self._storage_usage_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._storage_move_button = QPushButton("Change Location...", tab)
        self._storage_move_button.clicked.connect(self._on_storage_move_clicked)
        self._storage_reset_button = QPushButton("Use System Default", tab)
        self._storage_reset_button.clicked.connect(self._on_storage_reset_clicked)
        self._storage_refresh_button = QPushButton("Refresh", tab)
        self._storage_refresh_button.clicked.connect(self._refresh_storage)

        why_note = QLabel(
            "The sidecar environments are large - a pkasolver install is around 2.3 GB and a "
            "the ADMET one about 1 GB - and by default they sit in the per-user data folder, which on "
            "Windows is on the system drive. None of it is data the OS needs to manage, so it "
            "can live anywhere. Changing the location MOVES what is already there.",
            tab,
        )
        why_note.setWordWrap(True)

        caveat_note = QLabel(
            "Only a few bytes stay behind, in the config folder, recording where everything "
            "went. Moving is safe for the Python sidecars: a virtual environment records its "
            "BASE interpreter, which does not move. Interpreter paths stored in settings are "
            "rewritten to follow.",
            tab,
        )
        caveat_note.setWordWrap(True)
        caveat_note.setStyleSheet("color: #666666;")

        row = QHBoxLayout()
        row.addWidget(self._storage_move_button)
        row.addWidget(self._storage_reset_button)
        row.addWidget(self._storage_refresh_button)
        row.addStretch(1)

        self._components_table = QTableWidget(0, 4, tab)
        self._components_table.setHorizontalHeaderLabels(["Component", "Size", "", "Status"])
        self._components_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._components_table.horizontalHeader().setStretchLastSection(True)
        self._components_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._components_table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(tab)
        layout.addWidget(self._storage_status_label)
        layout.addLayout(row)
        layout.addWidget(self._storage_usage_label)
        layout.addWidget(QLabel("Installed components:", tab))
        layout.addWidget(self._components_table)
        layout.addWidget(why_note)
        layout.addWidget(caveat_note)
        layout.addStretch(1)
        # Sizes are deliberately NOT measured here. Sizing the data
        # directory walks every file in two sidecar environments -- 18.9
        # seconds, paid on every construction of this dialog, before this
        # was made lazy.
        self._refresh_storage_labels()
        return tab

    def _on_tab_changed(self, index: int) -> None:
        if self._tabs.tabText(index) == "Storage" and not self._storage_measured:
            self._measure_storage()

    def _refresh_storage_labels(self) -> None:
        """Everything that costs nothing to know."""
        from openchem.services import sidecar_inventory, storage_service

        self._storage_status_label.setText(storage_service.describe_status())
        self._storage_reset_button.setEnabled(
            storage_service.app_paths.configured_data_root() is not None
        )
        items = sidecar_inventory.components(self._settings)
        self._populate_components([(component, None) for component in items])

    def _measure_storage(self) -> None:
        """Walk the disk for real sizes, off the GUI thread."""
        from openchem.services import sidecar_inventory

        self._storage_usage_label.setText("Calculating sizes...")
        run_async(
            lambda: sidecar_inventory.measure(self._settings),
            Exception,
            self._on_storage_measured,
            lambda message: self._storage_usage_label.setText(f"Could not read sizes: {message}"),
        )

    def _on_storage_measured(self, measured) -> None:
        from openchem.services import sidecar_inventory

        self._storage_measured = True
        total = sum(size for _component, size in measured)
        self._storage_usage_label.setText(f"Total: {sidecar_inventory._human(total)}")
        self._populate_components(measured)

    def _populate_components(self, measured) -> None:
        from openchem.services import sidecar_inventory

        self._components_table.setRowCount(len(measured))
        for row, (component, size) in enumerate(measured):
            self._components_table.setItem(row, 0, QTableWidgetItem(component.label))
            if not component.present:
                size_text = "-"
            elif size is None:
                size_text = "..."
            else:
                size_text = sidecar_inventory._human(size)
            self._components_table.setItem(row, 1, QTableWidgetItem(size_text))
            if component.present:
                button = QPushButton("Remove", self._components_table)
                # Same reason as the other button above: a lambda capturing
                # `self` here roots this dialog permanently.
                button.setProperty(_COMPONENT_KEY_PROPERTY, component.key)
                button.clicked.connect(self._on_remove_button_clicked)
                self._components_table.setCellWidget(row, 2, button)
            else:
                self._components_table.setCellWidget(row, 2, None)
                self._components_table.setItem(row, 2, QTableWidgetItem(""))
            # Says WHY a row has no Remove button -- "not installed" and
            # "yours, not ours" are different situations and a blank cell
            # would read the same for both.
            status = (
                component.unmanaged_reason
                if not component.is_managed
                else (component.description if component.present else "Not installed")
            )
            self._components_table.setItem(row, 3, QTableWidgetItem(status))

    def _refresh_storage(self) -> None:
        self._refresh_storage_labels()
        self._measure_storage()

    def _on_storage_move_clicked(self) -> None:
        from openchem.services import storage_service

        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a new location for OpenChem Studio data"
        )
        if not chosen:
            return
        destination = Path(chosen)
        # An empty folder the user picked is fine; a populated one they
        # picked by accident is not, and the service refuses it. Naming a
        # subfolder is the friendlier default for "I picked D:\".
        if destination.exists() and any(destination.iterdir()):
            destination = destination / storage_service.DEFAULT_FOLDER_NAME

        current = storage_service.usage()
        answer = QMessageBox.question(
            self,
            "Move data",
            (
                f"Move OpenChem Studio's data?\n\n"
                f"From: {current.root}\n"
                f"To:   {destination}\n"
                f"Size: {storage_service._human(current.total_bytes)}\n\n"
                "Everything already installed is moved, and the app is pointed at the new "
                "location. Across drives this is a copy-then-delete and can take a while.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._storage_move_button.setEnabled(False)
        self._storage_status_label.setText("Moving...")
        run_async(
            lambda: storage_service.move_data_root(
                destination, self._settings, on_progress=self._on_storage_progress
            ),
            storage_service.StorageError,
            self._on_storage_moved,
            self._on_storage_move_failed,
        )

    def _on_storage_progress(self, progress: Any) -> None:
        progress_reporter(self._storage_status_label)(progress)

    def _on_storage_moved(self, destination: Path) -> None:
        self._storage_move_button.setEnabled(True)
        self._refresh_storage()
        QMessageBox.information(self, "Data moved", f"Everything now lives in\n{destination}")

    def _on_storage_move_failed(self, message: str) -> None:
        self._storage_move_button.setEnabled(True)
        self._refresh_storage()
        QMessageBox.critical(self, "Move failed", message)

    def _on_storage_reset_clicked(self) -> None:
        from openchem.services import storage_service

        default = storage_service.app_paths.default_data_root()
        answer = QMessageBox.question(
            self,
            "Use the system default",
            (
                f"Move data back to the default location?\n\n"
                f"To: {default}\n\n"
                "On Windows that is on the system drive."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._storage_move_button.setEnabled(False)
        run_async(
            lambda: storage_service.move_data_root(
                default, self._settings, on_progress=self._on_storage_progress
            ),
            storage_service.StorageError,
            self._on_storage_reset_done,
            self._on_storage_move_failed,
        )

    def _on_storage_reset_done(self, destination: Path) -> None:
        # move_data_root records the destination as a custom root; going
        # back to the default means clearing the pointer entirely, so the
        # app follows the OS if that location ever changes.
        from openchem.services import storage_service

        storage_service.app_paths.set_data_root(None)
        self._storage_move_button.setEnabled(True)
        self._refresh_storage()
        QMessageBox.information(self, "Data moved", f"Back to the default location\n{destination}")
