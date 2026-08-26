"""Look the current structure up on PubChem, and link out to ChemSpider.

CONSENT IS THE POINT OF THE FIRST SCREEN. `chem/naming_providers.py`
states the policy this implements: a PubChem lookup sends the structure to
NCBI's public servers, which matters for unpublished work, so it happens
only on an explicit user action and never automatically. The dialog
therefore opens showing exactly what WOULD be sent and does nothing until
the button is pressed -- opening it costs nothing and reveals nothing.

The lookup runs on the thread pool rather than inline. It is two HTTP
round trips, and a frozen window for a couple of seconds reads as a hang.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.naming_providers import (
    PUBCHEM_PRIVACY_NOTE,
    NamingError,
    StructureIdentification,
    chemspider_search_url,
    pubchem_identify_smiles,
)

logger = logging.getLogger("openchem.ui")


class _LookupSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _LookupTask(QRunnable):
    """Runs one identification off the GUI thread.

    Takes a SMILES string rather than an RDKit Mol: the mol belongs to the
    GUI thread's molecule and RDKit objects are not something to hand
    across threads casually. Re-parsing a canonical SMILES is microseconds
    against a network round trip.
    """

    def __init__(self, smiles: str) -> None:
        super().__init__()
        self.signals = _LookupSignals()
        self._smiles = smiles

    def run(self) -> None:
        try:
            self.signals.finished.emit(pubchem_identify_smiles(self._smiles))
        except NamingError as exc:
            # The expected failure -- unknown structure, offline, rate
            # limited. Its message is written for the user, so it is shown
            # verbatim rather than wrapped.
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never let a worker kill the pool
            logger.exception("Structure lookup failed")
            self.signals.failed.emit(f"Lookup failed: {exc}")


class StructureLookupDialog(QDialog):
    def __init__(self, smiles: str, inchikey: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Identify Structure Online")
        self.resize(560, 420)
        self._smiles = smiles
        self._inchikey = inchikey
        self._result: StructureIdentification | None = None

        query = QPlainTextEdit(self)
        query.setPlainText(f"SMILES:   {smiles}\nInChIKey: {inchikey}")
        query.setReadOnly(True)
        query.setFixedHeight(60)

        privacy = QLabel(PUBCHEM_PRIVACY_NOTE, self)
        privacy.setWordWrap(True)

        self._search_button = QPushButton("Search PubChem", self)
        self._search_button.clicked.connect(self._start_lookup)
        self._chemspider_button = QPushButton("Open in ChemSpider", self)
        self._chemspider_button.setToolTip(
            "Opens a ChemSpider search in your browser. ChemSpider's API needs a "
            "registered key, so this is a link rather than a built-in lookup."
        )
        self._chemspider_button.clicked.connect(self._open_in_chemspider)
        self._open_button = QPushButton("Open PubChem Page", self)
        self._open_button.setEnabled(False)
        self._open_button.clicked.connect(self._open_pubchem)
        self._copy_button = QPushButton("Copy Result", self)
        self._copy_button.setEnabled(False)
        self._copy_button.clicked.connect(self._copy_result)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._results = QPlainTextEdit(self)
        self._results.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._search_button)
        buttons.addWidget(self._open_button)
        buttons.addWidget(self._chemspider_button)
        buttons.addWidget(self._copy_button)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("This structure will be sent as:", self))
        layout.addWidget(query)
        layout.addWidget(privacy)
        layout.addLayout(buttons)
        layout.addWidget(self._status)
        layout.addWidget(self._results, 1)
        layout.addWidget(close_box)

    def _start_lookup(self) -> None:
        self._search_button.setEnabled(False)
        self._status.setText("Searching PubChem...")
        self._results.clear()
        task = _LookupTask(self._smiles)
        task.signals.finished.connect(self._on_finished)
        task.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(task)

    def _on_finished(self, result: StructureIdentification) -> None:
        self._result = result
        self._search_button.setEnabled(True)
        self._open_button.setEnabled(True)
        self._copy_button.setEnabled(True)
        self._status.setText(f"Exact structure match: CID {result.cid}")
        lines = [
            f"PubChem CID:      {result.cid}",
            f"IUPAC name:       {result.iupac_name or '(none recorded)'}",
            f"Formula:          {result.molecular_formula or '(none recorded)'}",
            f"Molecular weight: {result.molecular_weight if result.molecular_weight is not None else '(none recorded)'}",
            f"URL:              {result.url}",
        ]
        if result.synonyms:
            lines.append("")
            lines.append("Also known as:")
            lines.extend(f"  {s}" for s in result.synonyms)
        self._results.setPlainText("\n".join(lines))

    def _on_failed(self, message: str) -> None:
        self._search_button.setEnabled(True)
        self._status.setText(message)
        # Spelled out because "no match" is routinely misread as "this
        # compound is unknown", when what it means is that PubChem has no
        # record of this EXACT connectivity and stereochemistry.
        self._results.setPlainText(
            "PubChem was searched for this exact structure.\n\n"
            "A no-match does not mean the compound is unknown -- a different "
            "tautomer, a missing stereocentre, or a salt form is a different "
            "structure to this search. Try ChemSpider, or search PubChem for a "
            "name instead."
        )

    def _open_in_chemspider(self, _checked: bool = False) -> None:
        """Bound methods, never self-capturing lambdas -- both rooted this
        dialog for the life of the process. Measured: it leaked."""
        QDesktopServices.openUrl(QUrl(chemspider_search_url(self._inchikey)))

    def _copy_result(self, _checked: bool = False) -> None:
        QGuiApplication.clipboard().setText(self._results.toPlainText())

    def _open_pubchem(self) -> None:
        if self._result is not None:
            QDesktopServices.openUrl(QUrl(self._result.url))
