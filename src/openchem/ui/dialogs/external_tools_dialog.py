from __future__ import annotations

import os

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import Settings
from openchem.chem.admet_providers import describe_admet_test
from openchem.chem.naming_providers import describe_opsin_status
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING, describe_pka_status
from openchem.plugins.async_task import run_async
from openchem.services.pkasolver_setup import (
    APPROX_DISK_GB,
    APPROX_DOWNLOAD_MB,
    PKASOLVER_REPO,
    PkasolverSetupError,
    SetupProgress,
    TORCH_VERSION,
    default_install_root,
    describe_prerequisites,
    find_fallback_python,
    find_uv,
    install,
)
from openchem.services.tool_download_service import (
    ORCA_DOCS_PAGE,
    ORCA_DOWNLOAD_PAGE,
    VinaReleaseAsset,
    describe_orca_platform_hint,
    describe_vina_status,
    download_vina_asset,
    fetch_latest_vina_release,
)

logger = logging.getLogger("openchem.ui")


# A sidecar path must be an INTERPRETER, not any file in the environment.
# Without this filter a stored path of "...\pkasolver\.codecov.yml" was
# selectable, and produced only "[WinError 193] %1 is not a valid Win32
# application" at the point of use.
_INTERPRETER_FILTER = (
    "Python interpreter (python.exe python3.exe python python3);;All files (*)"
    if os.name == "nt"
    else "Python interpreter (python python3 python3.*);;All files (*)"
)

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
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None, focus: str = "vina") -> None:
        super().__init__(parent)
        self.setWindowTitle("External Tools")
        self.resize(560, 380)
        self._settings = settings

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_vina_tab(), "AutoDock Vina")
        self._tabs.addTab(self._build_orca_tab(), "ORCA")
        self._tabs.addTab(self._build_pkasolver_tab(), "pkasolver (pKa)")
        # Grouped with pkasolver rather than with the executables above:
        # both are "a Python interpreter, not an executable", and making
        # them look different would imply a difference that is not there.
        self._tabs.addTab(self._build_admet_tab(), "ADMET (hERG/CYP)")
        self._tabs.addTab(self._build_java_tab(), "Java (Temurin)")
        self._tabs.addTab(self._build_nmr_database_tab(), "NMR Database")
        self._tabs.addTab(self._build_storage_tab(), "Storage")
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

    # --- Locating an executable without making the user dig ------------------

    def _browse_for(self, title: str, finder, description: str) -> str | None:
        """Ask for a FOLDER and find the program inside it.

        A folder is far easier to point at than a file buried three levels
        down: a pkasolver interpreter sits at
        `pkasolver_env/.venv/Scripts/python.exe`, next to a `pkasolver/`
        directory that looks equally plausible, and picking wrong gives
        "[WinError 193] %1 is not a valid Win32 application". Pointing at
        the environment -- or at the whole data folder -- is enough.
        """
        chosen = QFileDialog.getExistingDirectory(self, title)
        if not chosen:
            return None
        found = finder(Path(chosen))
        if found is None:
            QMessageBox.warning(
                self,
                "Nothing found",
                f"No {description} was found in\n{chosen}\n\n"
                "Pick the folder the tool was installed into, or a folder above it.",
            )
            return None
        return str(found)

    def _auto_locate(self, root: Path, finder, description: str) -> str | None:
        """Look where this app would have installed it, with no dialog.

        The application put it there; it should not have to ask.
        """
        found = finder(root) if root.exists() else None
        if found is None:
            QMessageBox.information(
                self,
                "Not found automatically",
                f"No {description} was found in\n{root}\n\n"
                "Use 'Set Up Automatically' to install it, or Browse if it is elsewhere.",
            )
            return None
        return str(found)

    # --- Vina tab -----------------------------------------------------------

    def _build_vina_tab(self) -> QWidget:
        tab = QWidget(self)

        self._vina_path_edit = QLineEdit(tab)
        self._vina_path_edit.setText(self._settings.get("docking/vina_executable_path", ""))
        self._vina_path_edit.editingFinished.connect(self._on_vina_path_edited)
        browse_button = QPushButton("Browse...", tab)
        browse_button.clicked.connect(self._on_vina_browse_clicked)
        path_row = QHBoxLayout()
        path_row.addWidget(self._vina_path_edit)
        path_row.addWidget(browse_button)

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
        form.addRow("Executable:", path_row)
        form.addRow("Status:", self._vina_status_label)

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addWidget(self._vina_download_button)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _on_vina_path_edited(self) -> None:
        self._settings.set("docking/vina_executable_path", self._vina_path_edit.text())
        self._refresh_vina_status()

    def _on_vina_browse_clicked(self) -> None:
        from openchem.services.sidecar_env import find_program

        path_str = self._browse_for(
            "Select the folder containing Vina",
            lambda root: find_program(root, ("vina",)),
            "Vina executable",
        )
        if path_str:
            self._vina_path_edit.setText(path_str)
            self._on_vina_path_edited()

    def _refresh_vina_status(self) -> None:
        self._vina_status_label.setText(describe_vina_status(self._vina_path_edit.text()))

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
        self._vina_path_edit.setText(str(path))
        self._on_vina_path_edited()
        QMessageBox.information(self, "Download complete", f"AutoDock Vina installed to:\n{path}")

    def _on_vina_download_failed(self, message: str) -> None:
        self._vina_download_button.setEnabled(True)
        self._vina_download_button.setText("Check for Updates / Download...")
        QMessageBox.critical(self, "Download failed", message)

    # --- ORCA tab -------------------------------------------------------------

    def _build_orca_tab(self) -> QWidget:
        tab = QWidget(self)

        self._orca_path_edit = QLineEdit(tab)
        self._orca_path_edit.setText(self._settings.get("orca/executable_path", ""))
        self._orca_path_edit.editingFinished.connect(self._on_orca_path_edited)
        browse_button = QPushButton("Browse...", tab)
        browse_button.clicked.connect(self._on_orca_browse_clicked)
        path_row = QHBoxLayout()
        path_row.addWidget(self._orca_path_edit)
        path_row.addWidget(browse_button)

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
        form.addRow("Executable:", path_row)

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addLayout(get_orca_row)
        layout.addWidget(identity_note)
        layout.addWidget(which_build_note)
        layout.addWidget(after_download_note)
        layout.addStretch(1)
        return tab

    def _on_orca_path_edited(self) -> None:
        self._settings.set("orca/executable_path", self._orca_path_edit.text())

    def _on_orca_browse_clicked(self) -> None:
        from openchem.services.sidecar_env import find_program

        path_str = self._browse_for(
            "Select the folder ORCA is installed in",
            lambda root: find_program(root, ("orca",)),
            "ORCA executable",
        )
        if path_str:
            self._orca_path_edit.setText(path_str)
            self._on_orca_path_edited()

    # --- pkasolver tab --------------------------------------------------------


    # --- Storage ------------------------------------------------------------

    def _build_storage_tab(self) -> QWidget:
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
        # Deliberately NOT measured here. Sizing the data directory walks
        # every file in two sidecar environments -- 18.9 seconds, paid on
        # every construction of this dialog, before this was made lazy.
        self._storage_measured = False
        self._refresh_storage_labels()
        self._tabs.currentChanged.connect(self._on_tab_changed)
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
                button.clicked.connect(
                    lambda _checked=False, key=component.key: self._on_remove_component(key)
                )
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
        button.clicked.connect(lambda _checked=False: self._on_remove_component(key))
        return button

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
        to avoid."""
        from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
        from openchem.services import java_setup, nmr_database_setup

        self._pkasolver_path_edit.setText(self._settings.get(PKASOLVER_PYTHON_SETTING, ""))
        self._pkasolver_status_label.setText("Not checked - press Test to verify")
        self._java_status_label.setText(java_setup.describe_status())
        self._nmr_db_status_label.setText(nmr_database_setup.describe_status())
        self._vina_path_edit.setText(self._settings.get("docking/vina_executable_path", ""))
        self._refresh_vina_status()

    def _refresh_storage(self) -> None:
        self._refresh_storage_labels()
        self._measure_storage()

    def _on_storage_move_clicked(self) -> None:
        from openchem.services import storage_service

        chosen = QFileDialog.getExistingDirectory(self, "Choose a new location for OpenChem Studio data")
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

    def _on_storage_progress(self, progress) -> None:
        QTimer.singleShot(
            0,
            lambda: self._storage_status_label.setText(
                f"[{progress.step}/{progress.total}] {progress.message}..."
            ),
        )

    def _on_storage_moved(self, destination: Path) -> None:
        self._storage_move_button.setEnabled(True)
        self._refresh_storage()
        QMessageBox.information(
            self, "Data moved", f"Everything now lives in\n{destination}"
        )

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


    # --- Java ---------------------------------------------------------------

    def _build_java_tab(self) -> QWidget:
        import openchem.services.java_setup as java_setup

        tab = QWidget(self)
        self._java_status_label = QLabel(java_setup.describe_status(), tab)
        self._java_status_label.setWordWrap(True)

        self._java_setup_button = QPushButton("Set Up Automatically...", tab)
        self._java_setup_button.clicked.connect(self._on_java_setup_clicked)
        self._java_refresh_button = QPushButton("Re-check", tab)
        self._java_refresh_button.clicked.connect(self._on_java_refresh_clicked)

        why_note = QLabel(
            "OPSIN needs Java: it is a Java library, reached through py2opsin, and "
            "OPSIN (name-to-structure) is a Java library. Without it both are unavailable, and "
            "the error each gives on its own names neither Java nor the fix.",
            tab,
        )
        why_note.setWordWrap(True)

        portable_note = QLabel(
            "Eclipse Temurin publishes PORTABLE archives, so this extracts a runtime into this "
            "app's data folder rather than running an installer. Nothing is registered, no "
            "system setting is changed, and deleting the folder removes it completely. A Java "
            "already on this machine is always preferred over installing another.",
            tab,
        )
        portable_note.setWordWrap(True)
        portable_note.setStyleSheet("color: #666666;")

        row = QHBoxLayout()
        row.addWidget(self._java_setup_button)
        self._java_remove_button = self._remove_button(tab, 'java', 'the Java runtime')
        row.addWidget(self._java_remove_button)
        row.addWidget(self._java_refresh_button)
        row.addStretch(1)

        layout = QVBoxLayout(tab)
        layout.addWidget(self._java_status_label)
        layout.addLayout(row)
        layout.addWidget(why_note)
        layout.addWidget(portable_note)
        layout.addStretch(1)
        return tab

    def _on_java_refresh_clicked(self) -> None:
        import openchem.services.java_setup as java_setup

        self._java_status_label.setText(java_setup.describe_status())

    def _on_java_setup_clicked(self) -> None:
        import openchem.services.java_setup as java_setup

        existing = java_setup.system_java_home()
        if existing is not None:
            QMessageBox.information(
                self, "Java already available", f"Java is already installed at {existing}."
            )
            return
        root = java_setup.default_install_root()
        answer = QMessageBox.question(
            self,
            "Install a Java runtime",
            (
                "Download a portable Java runtime?\n\n"
                f"Source: Eclipse Temurin {java_setup.FEATURE_VERSION} (JRE), via the official "
                "Adoptium release API\n"
                f"Download: about {java_setup.APPROX_DOWNLOAD_MB} MB\n"
                f"Location: {root}\n\n"
                "Extracted, not installed - no installer runs and no system setting changes. "
                "This unblocks OPSIN (name-to-structure parsing).\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._java_setup_button.setEnabled(False)
        self._java_status_label.setText("Starting...")
        run_async(
            lambda: java_setup.install(root, on_progress=self._on_java_setup_progress),
            java_setup.JavaSetupError,
            self._on_java_setup_finished,
            self._on_java_setup_failed,
        )

    def _on_java_setup_progress(self, progress) -> None:
        QTimer.singleShot(
            0,
            lambda: self._java_status_label.setText(
                f"[{progress.step}/{progress.total}] {progress.message}..."
            ),
        )

    def _on_java_setup_finished(self, home: Path) -> None:
        self._java_setup_button.setEnabled(True)
        self._java_status_label.setText(f"Installed and verified: {home}")
        # A prerequisite line may have said "no Java" a moment ago; it is
        # refreshed here so the two tabs cannot disagree with each other.
        QMessageBox.information(
            self,
            "Java ready",
            f"Runtime installed at\n{home}\n\nOPSIN can now run.",
        )

    def _on_java_setup_failed(self, message: str) -> None:
        self._java_setup_button.setEnabled(True)
        self._java_status_label.setText(f"Setup failed: {message}")
        QMessageBox.critical(self, "Java setup failed", message)

    # --- NMR shift database -------------------------------------------------

    def _build_nmr_database_tab(self) -> QWidget:
        import openchem.services.nmr_database_setup as nmr_setup

        tab = QWidget(self)
        self._nmr_db_status_label = QLabel(nmr_setup.describe_status(), tab)
        self._nmr_db_status_label.setWordWrap(True)

        self._nmr_db_build_button = QPushButton("Build Index...", tab)
        self._nmr_db_build_button.clicked.connect(self._on_nmr_database_build_clicked)
        self._nmr_db_refresh_button = QPushButton("Re-check", tab)
        self._nmr_db_refresh_button.clicked.connect(self._on_nmr_database_refresh_clicked)

        why_note = QLabel(
            "Predicts NMR shifts by looking each atom's environment up in assigned experimental "
            "spectra, rather than computing them - instant, where the ab initio path takes "
            "minutes. It also reports a per-atom confidence earned from how many measurements "
            "matched and how well they agree.",
            tab,
        )
        why_note.setWordWrap(True)

        accuracy_note = QLabel(
            "Held-out accuracy, measured on molecules excluded from the index: 1.12 ppm mean "
            "error on atoms rated 'good', 3.36 on 'medium', 10.00 on 'rough'. The rating is "
            "worth reading - it is the difference between a number to trust and one to check. "
            "Coverage is not universal: an environment the database has never seen gets no "
            "prediction rather than a guess.",
            tab,
        )
        accuracy_note.setWordWrap(True)
        accuracy_note.setStyleSheet("color: #666666;")

        row = QHBoxLayout()
        row.addWidget(self._nmr_db_build_button)
        row.addWidget(self._nmr_db_refresh_button)
        self._nmr_db_remove_button = self._remove_button(tab, 'nmr_index', 'the NMR shift database')
        row.addWidget(self._nmr_db_remove_button)
        row.addStretch(1)

        layout = QVBoxLayout(tab)
        layout.addWidget(self._nmr_db_status_label)
        layout.addLayout(row)
        layout.addWidget(why_note)
        layout.addWidget(accuracy_note)
        layout.addStretch(1)
        return tab

    def _on_nmr_database_refresh_clicked(self) -> None:
        import openchem.services.nmr_database_setup as nmr_setup

        self._nmr_db_status_label.setText(nmr_setup.describe_status())

    def _on_nmr_database_build_clicked(self) -> None:
        import openchem.services.nmr_database_setup as nmr_setup

        answer = QMessageBox.question(
            self,
            "Build the NMR shift index",
            (
                "Download nmrshiftdb2 and build the shift index?\n\n"
                f"Source: {nmr_setup.SOURCE_FILE} from the nmrshiftdb2 project on SourceForge "
                "(open content)\n"
                f"Download: about {nmr_setup.APPROX_DOWNLOAD_MB} MB\n"
                "Kept afterwards: about 15 MB - the download is discarded once indexed\n\n"
                "Indexing takes a few minutes: every assigned atom is coded at six environment "
                "depths, so a lookup can widen when the most specific one has too little "
                "evidence.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._nmr_db_build_button.setEnabled(False)
        self._nmr_db_status_label.setText("Starting...")
        run_async(
            lambda: nmr_setup.build(on_progress=self._on_nmr_database_progress),
            nmr_setup.NmrDatabaseSetupError,
            self._on_nmr_database_finished,
            self._on_nmr_database_failed,
        )

    def _on_nmr_database_progress(self, progress) -> None:
        QTimer.singleShot(
            0,
            lambda: self._nmr_db_status_label.setText(
                f"[{progress.step}/{progress.total}] {progress.message}..."
            ),
        )

    def _on_nmr_database_finished(self, stats) -> None:
        import openchem.services.nmr_database_setup as nmr_setup

        self._nmr_db_build_button.setEnabled(True)
        self._nmr_db_status_label.setText(nmr_setup.describe_status())
        QMessageBox.information(
            self,
            "NMR index built",
            (
                f"{stats.molecules:,} molecules\n"
                f"{stats.measurements:,} assigned shifts\n"
                f"{stats.environments:,} environments indexed"
            ),
        )

    def _on_nmr_database_failed(self, message: str) -> None:
        self._nmr_db_build_button.setEnabled(True)
        self._nmr_db_status_label.setText(f"Build failed: {message}")
        QMessageBox.critical(self, "NMR index build failed", message)


    def _build_pkasolver_tab(self) -> QWidget:
        tab = QWidget(self)

        self._pkasolver_path_edit = QLineEdit(tab)
        self._pkasolver_path_edit.setText(self._settings.get(PKASOLVER_PYTHON_SETTING, ""))
        self._pkasolver_path_edit.editingFinished.connect(self._on_pkasolver_path_edited)
        browse_button = QPushButton("Browse...", tab)
        browse_button.clicked.connect(self._on_pkasolver_browse_clicked)
        path_row = QHBoxLayout()
        path_row.addWidget(self._pkasolver_path_edit)
        path_row.addWidget(browse_button)

        self._pkasolver_status_label = QLabel("Not checked", tab)
        self._pkasolver_status_label.setWordWrap(True)
        test_button = QPushButton("Test (predicts acetic acid's pKa)...", tab)
        test_button.clicked.connect(self._on_pkasolver_test_clicked)

        self._pkasolver_locate_button = QPushButton("Locate Installed", tab)
        self._pkasolver_locate_button.setToolTip(
            "Look where this app installs it, without asking you to find anything."
        )
        self._pkasolver_locate_button.clicked.connect(self._on_pkasolver_locate_clicked)
        self._pkasolver_setup_button = QPushButton("Set Up Automatically...", tab)
        self._pkasolver_setup_button.clicked.connect(self._on_pkasolver_setup_clicked)
        self._pkasolver_prereq_label = QLabel(describe_prerequisites(), tab)
        self._pkasolver_prereq_label.setWordWrap(True)
        self._pkasolver_prereq_label.setStyleSheet("color: #666666;")

        why_note = QLabel(
            "Unlike Vina and ORCA this is a Python interpreter, not an executable. "
            "pkasolver needs numpy<2 while OpenChem Studio runs numpy 2.x, so it "
            "runs out of process in its own virtual environment rather than being "
            "installed alongside the app.",
            tab,
        )
        why_note.setWordWrap(True)

        setup_note = QLabel(
            "'Set Up Automatically' builds the whole environment for you and fills in the "
            "path above — it will show you exactly what gets downloaded first. If you would "
            "rather do it by hand: a Python 3.10–3.12 environment (NOT this app's own 3.13 — "
            "PyTorch 2.3.0 publishes no wheels for it) containing torch==2.3.0 (CPU), "
            "torch-geometric==2.0.1, torch-scatter and torch-sparse from "
            "https://data.pyg.org/whl/torch-2.3.0+cpu.html (prebuilt, no compiler needed), "
            "numpy<2, scipy<1.14, pandas, rdkit, plus github.com/mayrf/pkasolver on its "
            "import path. Those exact pins matter — newer torch-geometric cannot load "
            "pkasolver's trained models at all.",
            tab,
        )
        setup_note.setWordWrap(True)

        without_note = QLabel(
            "Without this, pH-dependent protonation (Charge category) still works via "
            "Dimorphite-DL, and LogD falls back to a clearly-labelled approximation.",
            tab,
        )
        without_note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Python interpreter:", path_row)
        form.addRow("Status:", self._pkasolver_status_label)

        action_row = QHBoxLayout()
        action_row.addWidget(self._pkasolver_setup_button)
        self._pkasolver_remove_button = self._remove_button(tab, 'pkasolver', 'the pkasolver environment')
        action_row.addWidget(self._pkasolver_remove_button)
        action_row.addWidget(self._pkasolver_locate_button)
        action_row.addWidget(test_button)
        action_row.addStretch()

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addLayout(action_row)
        layout.addWidget(self._pkasolver_prereq_label)
        layout.addWidget(why_note)
        layout.addWidget(setup_note)
        layout.addWidget(without_note)
        layout.addStretch(1)
        return tab


    def _build_admet_tab(self) -> QWidget:
        """Deliberately the same shape as the pkasolver tab.

        Both are "a Python interpreter, not an executable", and making them
        look different would imply a difference that is not there. This one
        is the simpler of the two: no pinned scientific stack to explain,
        because admet-ai resolves against modern Python with nothing to
        fight, and its weights ship inside the wheel.
        """
        from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
        from openchem.services import admet_setup

        tab = QWidget(self)

        self._admet_path_edit = QLineEdit(tab)
        self._admet_path_edit.setText(self._settings.get(ADMET_PYTHON_SETTING, ""))
        self._admet_path_edit.editingFinished.connect(self._on_admet_path_edited)
        browse_button = QPushButton("Browse...", tab)
        browse_button.clicked.connect(self._on_admet_browse_clicked)
        path_row = QHBoxLayout()
        path_row.addWidget(self._admet_path_edit)
        path_row.addWidget(browse_button)

        self._admet_status_label = QLabel("Not checked", tab)
        self._admet_status_label.setWordWrap(True)
        test_button = QPushButton("Test (predicts astemizole's hERG)...", tab)
        test_button.clicked.connect(self._on_admet_test_clicked)

        self._admet_locate_button = QPushButton("Locate Installed", tab)
        self._admet_locate_button.setToolTip(
            "Look where this app installs it, without asking you to find anything."
        )
        self._admet_locate_button.clicked.connect(self._on_admet_locate_clicked)
        self._admet_setup_button = QPushButton("Set Up Automatically...", tab)
        self._admet_setup_button.clicked.connect(self._on_admet_setup_clicked)
        self._admet_prereq_label = QLabel(admet_setup.describe_prerequisites(), tab)
        self._admet_prereq_label.setWordWrap(True)
        self._admet_prereq_label.setStyleSheet("color: #666666;")

        why_note = QLabel(
            "ADMET-AI predicts hERG blockade, CYP450 inhibition and Ames mutagenicity "
            "-- endpoints that genuinely need a trained model, with no honest "
            "rule-based substitute. Like pkasolver this is a Python interpreter rather "
            "than an executable: it needs PyTorch (~490 MB), which has no business in "
            "this application's own dependency tree or in the frozen build, so it runs "
            "out of process in its own environment.",
            tab,
        )
        why_note.setWordWrap(True)

        honesty_note = QLabel(
            "These are PREDICTIONS, not measurements. Measured against drugs withdrawn "
            "for QT prolongation, the model separates them cleanly from safe ones "
            "(astemizole 0.995, cisapride 0.977, terfenadine 0.970; metformin 0.049, "
            "paracetamol 0.096) -- but every value carries real uncertainty, and each "
            "is shown as a probability rather than a verdict.",
            tab,
        )
        honesty_note.setWordWrap(True)
        honesty_note.setStyleSheet("color: #8a6d3b;")

        without_note = QLabel(
            "Without this, the rule-based 'hERG Risk Factors (not a prediction)' "
            "checklist still works -- it reports which structural correlates of hERG "
            "liability are present, offline and instantly, instead of guessing a "
            "probability. The two answer different questions and both stay available.",
            tab,
        )
        without_note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Python interpreter:", path_row)
        form.addRow("Status:", self._admet_status_label)

        action_row = QHBoxLayout()
        action_row.addWidget(self._admet_setup_button)
        self._admet_remove_button = self._remove_button(tab, "admet", "the ADMET environment")
        action_row.addWidget(self._admet_remove_button)
        action_row.addWidget(self._admet_locate_button)
        action_row.addWidget(test_button)
        action_row.addStretch()

        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addLayout(action_row)
        layout.addWidget(self._admet_prereq_label)
        layout.addWidget(why_note)
        layout.addWidget(honesty_note)
        layout.addWidget(without_note)
        layout.addStretch(1)
        return tab

    def _on_admet_setup_clicked(self) -> None:
        from openchem.services import admet_setup

        if not admet_setup.find_uv() and not admet_setup.find_fallback_python():
            QMessageBox.warning(
                self, "Cannot set up automatically", admet_setup.describe_prerequisites()
            )
            return

        root = admet_setup.default_install_root()
        # Same policy every downloader in this dialog follows: show what,
        # from where and how big, then wait for an explicit yes.
        answer = QMessageBox.question(
            self,
            "Set up ADMET-AI",
            (
                f"Build an ADMET-AI environment?\n\n"
                f"Location: {root}\n"
                f"Downloads: roughly {admet_setup.APPROX_DOWNLOAD_MB} MB\n"
                f"Disk space when finished: about {admet_setup.APPROX_DISK_GB} GB\n\n"
                f"Sources:\n"
                f"  - admet-ai and PyTorch, from PyPI\n"
                f"  - Trained weights ship inside the admet-ai wheel, so there is no "
                f"separate model download to fail.\n\n"
                f"{admet_setup.describe_prerequisites()}\n\n"
                f"This takes several minutes. Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._admet_setup_button.setEnabled(False)
        self._admet_status_label.setText("Starting...")
        run_async(
            lambda: admet_setup.install(root, on_progress=self._on_admet_setup_progress),
            admet_setup.AdmetSetupError,
            self._on_admet_setup_finished,
            self._on_admet_setup_failed,
        )

    def _on_admet_setup_progress(self, progress) -> None:
        # Called from the worker thread; hops back to the GUI thread via the
        # same single-shot-timer idiom every other sidecar here uses.
        QTimer.singleShot(
            0,
            lambda: self._admet_status_label.setText(
                f"[{progress.step}/{progress.total}] {progress.message}..."
            ),
        )

    def _on_admet_setup_finished(self, interpreter: Path) -> None:
        self._admet_setup_button.setEnabled(True)
        self._admet_path_edit.setText(str(interpreter))
        self._on_admet_path_edited()
        self._admet_status_label.setText(
            "Set up and verified - hERG, CYP and Ames predictions are now available."
        )
        QMessageBox.information(
            self,
            "ADMET-AI ready",
            f"Environment built and verified with a real prediction.\n\n{interpreter}",
        )

    def _on_admet_setup_failed(self, message: str) -> None:
        self._admet_setup_button.setEnabled(True)
        self._admet_status_label.setText(f"Setup failed: {message}")
        QMessageBox.critical(self, "ADMET setup failed", message)

    def _on_admet_path_edited(self) -> None:
        from openchem.chem.admet_providers import ADMET_PYTHON_SETTING

        self._settings.set(ADMET_PYTHON_SETTING, self._admet_path_edit.text())
        self._admet_status_label.setText("Not checked - press Test to verify")

    def _on_admet_browse_clicked(self) -> None:
        from openchem.services.sidecar_env import find_interpreter

        path_str = self._browse_for(
            "Select the ADMET environment folder", find_interpreter, "Python interpreter"
        )
        if path_str:
            self._admet_path_edit.setText(path_str)
            self._on_admet_path_edited()

    def _on_admet_locate_clicked(self) -> None:
        from openchem.services.admet_setup import default_install_root
        from openchem.services.sidecar_env import find_interpreter

        path_str = self._auto_locate(default_install_root(), find_interpreter, "Python interpreter")
        if path_str:
            self._admet_path_edit.setText(path_str)
            self._on_admet_path_edited()
            self._admet_status_label.setText(f"Found: {path_str} - press Test to verify")

    def _on_admet_test_clicked(self) -> None:
        # A real prediction, which loads the model ensemble and takes a
        # while -- kept off the GUI thread like every other Test here.
        self._admet_status_label.setText("Testing (loading the model, this can take a minute)...")
        path = self._admet_path_edit.text()
        run_async(
            lambda: describe_admet_test(path),
            Exception,
            self._admet_status_label.setText,
            lambda message: self._admet_status_label.setText(f"Test failed: {message}"),
        )

    def _on_pkasolver_setup_clicked(self) -> None:
        if not find_uv() and not find_fallback_python():
            QMessageBox.warning(self, "Cannot set up automatically", describe_prerequisites())
            return

        root = default_install_root()
        # Same policy the Vina downloader follows: never fetch anything
        # without showing what, from where, and how big, then waiting for
        # an explicit yes. This one is multi-gigabyte, so it matters more.
        answer = QMessageBox.question(
            self,
            "Set up pkasolver",
            (
                f"Build a pkasolver environment?\n\n"
                f"Location: {root}\n"
                f"Downloads: roughly {APPROX_DOWNLOAD_MB} MB\n"
                f"Disk space when finished: about {APPROX_DISK_GB} GB\n\n"
                f"Sources:\n"
                f"  • PyTorch {TORCH_VERSION} (CPU) — download.pytorch.org\n"
                f"  • torch-scatter / torch-sparse — data.pyg.org (prebuilt wheels)\n"
                f"  • torch-geometric, numpy, scipy, pandas, rdkit — PyPI\n"
                f"  • pkasolver + trained models — {PKASOLVER_REPO}\n\n"
                f"{describe_prerequisites()}\n\n"
                f"This takes several minutes. Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._pkasolver_setup_button.setEnabled(False)
        self._pkasolver_status_label.setText("Starting…")
        run_async(
            lambda: install(root, on_progress=self._on_pkasolver_setup_progress),
            PkasolverSetupError,
            self._on_pkasolver_setup_finished,
            self._on_pkasolver_setup_failed,
        )

    def _on_pkasolver_setup_progress(self, progress: SetupProgress) -> None:
        # Called from the worker thread. setText on a QLabel from a non-GUI
        # thread is not safe in general, so this hops back via the same
        # single-shot-timer idiom Qt sanctions for cross-thread UI updates.
        QTimer.singleShot(
            0,
            lambda: self._pkasolver_status_label.setText(
                f"[{progress.step}/{progress.total}] {progress.message}…"
            ),
        )

    def _on_pkasolver_setup_finished(self, interpreter: Path) -> None:
        self._pkasolver_setup_button.setEnabled(True)
        self._pkasolver_path_edit.setText(str(interpreter))
        self._on_pkasolver_path_edited()
        self._pkasolver_status_label.setText(
            "Set up and verified — numeric pKa and Henderson-Hasselbalch LogD are now available."
        )
        QMessageBox.information(
            self,
            "pkasolver ready",
            f"Environment built and verified with a real prediction.\n\n{interpreter}",
        )

    def _on_pkasolver_setup_failed(self, message: str) -> None:
        self._pkasolver_setup_button.setEnabled(True)
        self._pkasolver_status_label.setText(f"Setup failed: {message}")
        QMessageBox.critical(self, "pkasolver setup failed", message)

    def _on_pkasolver_path_edited(self) -> None:
        self._settings.set(PKASOLVER_PYTHON_SETTING, self._pkasolver_path_edit.text())
        self._pkasolver_status_label.setText("Not checked — press Test to verify")

    def _on_pkasolver_browse_clicked(self) -> None:
        from openchem.services.sidecar_env import find_interpreter

        path_str = self._browse_for(
            "Select the pkasolver environment folder", find_interpreter, "Python interpreter"
        )
        if path_str:
            self._pkasolver_path_edit.setText(path_str)
            self._on_pkasolver_path_edited()

    def _on_pkasolver_locate_clicked(self) -> None:
        from openchem.services.pkasolver_setup import default_install_root
        from openchem.services.sidecar_env import find_interpreter

        path_str = self._auto_locate(
            default_install_root(), find_interpreter, "Python interpreter"
        )
        if path_str:
            self._pkasolver_path_edit.setText(path_str)
            self._on_pkasolver_path_edited()
            self._pkasolver_status_label.setText(f"Found: {path_str} - press Test to verify")

    def _on_pkasolver_test_clicked(self) -> None:
        # Runs a real prediction, which loads a ~105 MB model ensemble and
        # takes a while -- kept off the GUI thread via the same run_async
        # helper the Vina release lookup uses.
        self._pkasolver_status_label.setText("Testing (loading models, this can take a minute)...")
        path = self._pkasolver_path_edit.text()
        run_async(
            lambda: describe_pka_status(path),
            RuntimeError,
            self._pkasolver_status_label.setText,
            lambda message: self._pkasolver_status_label.setText(f"Test failed: {message}"),
        )

