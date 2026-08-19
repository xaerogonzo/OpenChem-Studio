"""Browse the curated receptor catalogue and import a target.

The layout follows what the user is actually deciding. The left side is
"which target", filtered by a search box and grouped by family. The right
side is everything needed to judge whether that particular structure is
the right one -- resolution, method, state, what was bound to it, and the
caveat -- because picking between three mu-opioid entries is the step
that was hard, not finding the family.

Downloading is explicit and one-way: nothing is fetched by browsing.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.receptor_library import RECEPTOR_LIBRARY, ReceptorEntry, families, search
from openchem.services.receptor_library_service import is_cached
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

logger = logging.getLogger("openchem.ui")

#: ONE control -- the Import/Cancel pair is a `QDialogButtonBox` and the
#: clear button is Qt's own, both excluded by `tooltip_inventory`.
#:
#: The placeholder already suggested three example queries, which is a
#: good hint and not a contract: it says what to type and nothing about
#: WHICH FIELDS are searched, that a match may not straddle two of them,
#: or that browsing downloads nothing.
_HELP: dict[str, HelpTooltip] = {
    "search": HelpTooltip(
        text=(
            "Filters the catalogue on target, family, PDB ID, bound ligand "
            "and state -- a substring of any ONE of those, never across two "
            "of them.\n\n"
            "Searching the LIGAND is the part a plain RCSB search handles "
            "badly, and is how people usually arrive at a structure: what "
            "has fentanyl bound to it, what has a benzodiazepine site. "
            "Greek letters fold both ways, so 'alpha-2A' and the symbol "
            "form find the same entry. Nothing is downloaded by searching; "
            "the structure is fetched when you import it."
        ),
        tier=1,
        help_id="receptor_library.search",
        topic="docking",
    ),
}

#: Marks the entry carried on a tree item. Entries live on the item rather
#: than being looked up by label, so two structures of the same target
#: (there are three mu-opioid ones) can never be confused.
_ENTRY_ROLE = Qt.ItemDataRole.UserRole


class ReceptorLibraryDialog(QDialog):
    """Pick a catalogued receptor. `selected_entry()` is the result."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Receptor Library")
        self.resize(920, 560)
        self._selected: ReceptorEntry | None = None

        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Search target, PDB ID or bound ligand - try 'opioid', 'fentanyl', 'hERG'"
        )
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._repopulate)
        apply_help_tooltip(self._search, _HELP["search"])

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Target", "PDB", "Resolution", "Bound ligand"])
        self._tree.setColumnWidth(0, 250)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        # Double-click is "pick this one and go" -- the whole flow is one
        # decision, so it should not need a trip to the button row.
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)

        self._details = QLabel("Select a receptor to see its details.")
        self._details.setWordWrap(True)
        self._details.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._details.setOpenExternalLinks(True)
        self._details.setMinimumWidth(300)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._tree)
        splitter.addWidget(left)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import Receptor")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        note = QLabel(
            f"{len(RECEPTOR_LIBRARY)} structures from the RCSB Protein Data Bank. "
            "The chosen structure is downloaded when you import it, and cached "
            "for later. Each entry names the ligand that was crystallised with "
            "it, so the docking search box can be placed on a real binding site."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._buttons)
        layout.addLayout(row)

        self._repopulate()

    # --- population -------------------------------------------------------

    def _repopulate(self) -> None:
        matches = search(self._search.text())
        self._tree.clear()
        for family in families():
            in_family = [entry for entry in matches if entry.family == family]
            if not in_family:
                continue  # an empty group is noise, not information
            parent = QTreeWidgetItem([f"{family} ({len(in_family)})"])
            # Family rows are containers, not choices -- selecting one must
            # not enable Import.
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._tree.addTopLevelItem(parent)
            for entry in in_family:
                parent.addChild(self._make_item(entry))
            parent.setExpanded(True)
        self._update_buttons()

    def _make_item(self, entry: ReceptorEntry) -> QTreeWidgetItem:
        target = entry.target + (f" ({entry.state})" if entry.state else "")
        item = QTreeWidgetItem([
            target,
            entry.pdb_id,
            f"{entry.resolution_angstrom:.2f} A",
            entry.ligand_name,
        ])
        item.setData(0, _ENTRY_ROLE, entry)
        if is_cached(entry.pdb_id):
            # Worth surfacing: a cached entry imports instantly and works
            # with no network, which changes whether it is a good pick
            # right now.
            item.setText(1, f"{entry.pdb_id}  (downloaded)")
        return item

    # --- selection --------------------------------------------------------

    def _on_selection_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        entry = current.data(0, _ENTRY_ROLE) if current is not None else None
        self._selected = entry
        self._details.setText(self._describe(entry) if entry else "Select a receptor.")
        self._update_buttons()

    def _on_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, _ENTRY_ROLE) is not None:
            self.accept()

    def _update_buttons(self) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self._selected is not None
        )

    def _describe(self, entry: ReceptorEntry) -> str:
        rows = [
            f"<h3>{entry.target}</h3>",
            f"<p><b>PDB ID:</b> {entry.pdb_id}<br>",
            f"<b>Resolution:</b> {entry.resolution_angstrom:.2f} A<br>",
            f"<b>Method:</b> {entry.method}<br>",
        ]
        if entry.state:
            rows.append(f"<b>State:</b> {entry.state}<br>")
        rows.append(
            f"<b>Bound ligand:</b> {entry.ligand_name} "
            f"(<code>{entry.ligand_code}</code>)</p>"
        )
        rows.append(
            "<p>The docking search box will be placed on this ligand's "
            "position, which is a real, occupied binding site.</p>"
        )
        if entry.caveat:
            # Not buried: these are the things that change how a result
            # should be read, and none of them appear in a PDB title.
            rows.append(f"<p><b>Worth knowing:</b> {entry.caveat}</p>")
        rows.append(
            f'<p><a href="https://www.rcsb.org/structure/{entry.pdb_id}">'
            f"View {entry.pdb_id} on RCSB</a></p>"
        )
        if is_cached(entry.pdb_id):
            rows.append("<p><i>Already downloaded - imports immediately.</i></p>")
        return "".join(rows)

    def selected_entry(self) -> ReceptorEntry | None:
        return self._selected


def _demo() -> None:  # pragma: no cover - manual inspection only
    app = QApplication([])
    dialog = ReceptorLibraryDialog()
    dialog.show()
    app.exec()


if __name__ == "__main__":  # pragma: no cover
    _demo()
