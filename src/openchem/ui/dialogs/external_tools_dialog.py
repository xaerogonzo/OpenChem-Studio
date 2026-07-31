from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
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
        path_str, _ = QFileDialog.getOpenFileName(self, "Select Vina executable")
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
        path_str, _ = QFileDialog.getOpenFileName(self, "Select ORCA executable")
        if path_str:
            self._orca_path_edit.setText(path_str)
            self._on_orca_path_edited()

    # --- pkasolver tab --------------------------------------------------------

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
        path_str, _ = QFileDialog.getOpenFileName(self, "Select the pkasolver environment's Python interpreter")
        if path_str:
            self._pkasolver_path_edit.setText(path_str)
            self._on_pkasolver_path_edited()

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
