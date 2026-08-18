"""Everything known about one atom, in one place.

A view over `AtomReport`, and only a view. The report is the deliverable
and this is its first consumer; the panel adds navigation, grouping and
export, and no chemistry.

**It never starts a calculation.** Results arrive by event and are
remembered; opening the panel, clicking an atom and switching molecules
are all free. An inspector that launches ORCA when you click an atom is a
calculator launcher, and people stop trusting it -- so the guarantee is
asserted in the tests rather than described here.

The TABLE is the primary navigation, not either viewer. Both viewers are
wired, but a molecule you have just drawn has no conformer -- which is
exactly when somebody wants to look at an atom -- so depending on them
would leave the panel unusable in the common case.

**What each viewer can actually report, measured against the real
builds rather than read off the wrappers:**

- Ketcher reports both ATOMS and BONDS, through `editor.selection()` on
  its `selectionChange` event. An earlier version of this docstring said
  it could report nothing, which was a fact about our wrapper and not
  about Ketcher.
- 3Dmol reports ATOMS ONLY. `setClickable` hands back an atom, and bonds
  drawn in stick mode are not separately selectable. So a bond is named in
  3D by clicking its two atoms -- see `_note_atom_for_bond`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.atom_report import build_atom_report
from openchem.chem.bond_report import bond_label, build_bond_report
from openchem.chem.molecule_report import build_molecule_report
from openchem.chem.engine import ChemistryEngine
from openchem.domain.bond_report import BondReport
from openchem.domain.molecule_report import MoleculeReport
from openchem.domain.atom_report import (
    CATEGORY_LABELS,
    DEFAULT_EXPANDED,
    AtomFact,
    AtomReport,
    FactLink,
)
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import (
    MoleculeSelected,
    PerAtomDataComputed,
    SpectrumComputed,
    StructureChecked,
)
from openchem.ui.report_format import report_header
from openchem.ui.widgets.collapsible_section import WrappedLabel
from openchem.ui.widgets.fact_view import FactView

_ATOM_COLUMNS = ("#", "Element", "Facts")
_BOND_COLUMNS = ("#", "Bond", "Facts")

#: What the report is ABOUT. A molecule has exactly one subject, so it
#: has no table -- selecting it hides the list rather than showing a
#: one-row table that cannot be interacted with.
_SUBJECTS = ("Atom", "Bond", "Molecule")

_INTRO = (
    "Everything already known about the selected atom. Nothing here runs a "
    "calculation -- a property you have not computed is absent rather than "
    "wrong, and appears as soon as its calculator has run."
)

_COPY_FORMATS = ("Markdown", "Plain text", "JSON", "CSV")


class AtomInspectorPanel(QWidget):
    """Pick an atom; see every fact any part of the app knows about it."""

    #: Emitted when the user follows a fact's cross-link. MainWindow owns
    #: the destinations -- the panel knows a link exists, not how to open a
    #: dialog, which keeps it testable without a window.
    link_activated = Signal(object)
    #: Emitted when the selected atom changes, so viewers can highlight it.
    atom_selected = Signal(int)
    #: The atoms a hovered fact is ABOUT, or `()` on the way out.
    #: Always bounds-checked; see `_on_highlight_requested`.
    atoms_highlighted = Signal(tuple)
    #: "Show me this atom's isotopes." **AN APPLICATION-OWNED DOOR TO THE
    #: NUCLIDE TABLE**, which is the invariant the Ketcher context-menu
    #: work is held to: the isotope feature must be reachable with no
    #: change to the editor bundle at all, so that injection is an
    #: addition rather than a dependency.
    isotopes_requested = Signal()

    def __init__(
        self,
        engine: ChemistryEngine,
        event_bus: EventBus,
        atom_fact_service=None,
        structure_check_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._event_bus = event_bus
        self._atom_fact_service = atom_fact_service
        self._structure_check_service = structure_check_service

        self._project: ProjectModel | None = None
        self._molecule_uuid: str | None = None
        self._atom_index: int | None = None
        self._bond_index: int | None = None
        #: First atom of a two-click bond pick in 3D, where the viewer can
        #: only report atoms. Cleared whenever the subject changes, so a
        #: half-finished pick cannot complete against a later click.
        self._pending_bond_atom: int | None = None
        self._subject = "Atom"

        #: molecule uuid -> everything that has arrived by event for it.
        self._context: dict[str, dict] = {}
        #: (molecule uuid, structure version, subject, index) -> report.
        #: One cache for all three kinds: the key already had to carry
        #: the version, and adding the subject to it is cheaper than
        #: three dicts that can fall out of step on invalidation.
        self._cache: dict[tuple[str, int, str, int], object] = {}
        self._sections: dict[str, CollapsibleSection] = {}

        self._atom_table = QTableWidget(0, len(_ATOM_COLUMNS), self)
        self._atom_table.setHorizontalHeaderLabels(_ATOM_COLUMNS)
        header = self._atom_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._atom_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._atom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._atom_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # One line per row and no wrapping: the Interactions panel shipped a
        # table whose wrapped cells made every row taller than the viewport,
        # so it rendered correct data as blank lines.
        self._atom_table.setWordWrap(False)
        self._atom_table.setSortingEnabled(True)
        self._atom_table.verticalHeader().setVisible(False)
        self._atom_table.setMaximumHeight(220)
        self._atom_table.itemSelectionChanged.connect(self._on_row_selected)

        self._subject_combo = QComboBox(self)
        self._subject_combo.addItems(_SUBJECTS)
        self._subject_combo.currentTextChanged.connect(self._on_subject_changed)

        # THE RENDERING IS NOT THIS PANEL'S ANY MORE. Sections, search,
        # the depth filter, per-fact basis, cross-links, copy, export and
        # the detached window all live in `FactView`, which knows no
        # chemistry and is shared with every other report surface. What is
        # left here is navigation: which subject, which atom or bond, and
        # building the report for it.
        self._facts = FactView(self)
        self._facts.link_activated.connect(self.link_activated)
        self._facts.highlight_requested.connect(self._on_highlight_requested)

        intro = WrappedLabel(_INTRO, self)
        intro.setStyleSheet("color: #666666; font-style: italic;")

        # Disabled until an ATOM is the subject: a bond has two elements
        # and a molecule has many, so "which isotopes" has no answer for
        # either, and a button that opened the table on something
        # arbitrary would be worse than one that says it cannot.
        self._isotopes_button = QPushButton("Isotopes...", self)
        self._isotopes_button.setToolTip(
            "Show this atom's isotopes in the periodic table."
        )
        self._isotopes_button.clicked.connect(lambda: self.isotopes_requested.emit())

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Show:", self))
        controls.addWidget(self._subject_combo)
        controls.addWidget(self._isotopes_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self._atom_table)
        layout.addLayout(controls)
        layout.addWidget(self._facts, 1)

        self._facts.clear(
            "No atom selected",
            "Draw or open a molecule, then pick an atom or bond here to see "
            "everything already known about it. Nothing is calculated by "
            "opening this panel.",
        )

        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)
        event_bus.subscribe(PerAtomDataComputed, self._on_per_atom_data)
        event_bus.subscribe(SpectrumComputed, self._on_spectrum)
        event_bus.subscribe(StructureChecked, self._on_structure_checked)

    # --- what it is showing -------------------------------------------------
    #
    # The panel still HAS a title and a status; `FactView` just draws them
    # now. Delegating keeps the two facts callers care about on the panel.

    def title_text(self) -> str:
        return self._facts.title_text()

    def status_text(self) -> str:
        return self._facts.status_text()

    def search_text(self) -> str:
        return self._facts.search_box().text()

    def set_search_text(self, text: str) -> None:
        self._facts.search_box().setText(text)

    def focus_search(self) -> None:
        box = self._facts.search_box()
        box.setFocus()
        box.selectAll()

    # --- project and events ------------------------------------------------

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._rebuild_atom_table()

    def _on_molecule_selected(self, event: MoleculeSelected) -> None:
        self._molecule_uuid = event.molecule_uuid
        self._atom_index = None
        self._rebuild_atom_table()

    def _context_for(self, molecule_uuid: str) -> dict:
        return self._context.setdefault(
            molecule_uuid, {"per_atom": {}, "spectra": {}, "issues": ()}
        )

    def _on_per_atom_data(self, event: PerAtomDataComputed) -> None:
        dataset = event.dataset
        self._context_for(dataset.molecule_uuid)["per_atom"][dataset.property_id] = dataset
        self._invalidate(dataset.molecule_uuid)

    def _on_spectrum(self, event: SpectrumComputed) -> None:
        spectrum = event.spectrum
        self._context_for(spectrum.molecule_uuid)["spectra"][spectrum.spectrum_type] = spectrum
        self._invalidate(spectrum.molecule_uuid)

    def _on_structure_checked(self, event: StructureChecked) -> None:
        result = event.result
        self._context_for(result.molecule_uuid)["issues"] = tuple(result.issues)
        self._invalidate(result.molecule_uuid)

    def _invalidate(self, molecule_uuid: str) -> None:
        """Drop cached reports for one molecule and redraw if it is showing.

        New knowledge arriving is exactly as much a reason to rebuild as an
        edit is -- a cached report that predates a calculation would show
        "not computed" for something that now exists.
        """
        self._cache = {key: report for key, report in self._cache.items() if key[0] != molecule_uuid}
        if molecule_uuid == self._molecule_uuid:
            self._render_facts()

    # --- the atom table ----------------------------------------------------

    def _molecule(self):
        if self._project is None or self._molecule_uuid is None:
            return None, None
        model = next((m for m in self._project.molecules if m.uuid == self._molecule_uuid), None)
        if model is None:
            return None, None
        try:
            return model, self._engine.mol_from_model(model)
        except Exception:  # noqa: BLE001 - an unreadable structure is a status, not a crash
            return model, None

    def _rebuild_atom_table(self) -> None:
        model, mol = self._molecule()
        self._atom_table.setSortingEnabled(False)
        self._atom_table.setRowCount(0)
        if mol is None:
            self._render_facts()
            self._atom_table.setSortingEnabled(True)
            return

        if self._subject == "Molecule":
            # One subject, so no list. Hidden rather than shown as a single
            # inert row that invites a click doing nothing.
            self._atom_table.setSortingEnabled(True)
            return

        if self._subject == "Bond":
            self._atom_table.setHorizontalHeaderLabels(_BOND_COLUMNS)
            self._atom_table.setRowCount(mol.GetNumBonds())
            for row in range(mol.GetNumBonds()):
                number = QTableWidgetItem()
                number.setData(Qt.ItemDataRole.DisplayRole, row + 1)
                number.setData(Qt.ItemDataRole.UserRole, row)
                self._atom_table.setItem(row, 0, number)
                self._atom_table.setItem(row, 1, QTableWidgetItem(bond_label(mol, row)))
                count = QTableWidgetItem()
                count.setData(
                    Qt.ItemDataRole.DisplayRole, len(self._report_for(row).facts)
                )
                self._atom_table.setItem(row, 2, count)
            self._atom_table.setSortingEnabled(True)
            return

        self._atom_table.setHorizontalHeaderLabels(_ATOM_COLUMNS)
        self._atom_table.setRowCount(mol.GetNumAtoms())
        for row, atom in enumerate(mol.GetAtoms()):
            index = atom.GetIdx()
            # 1-based for display, 0-based in the data -- the whole app
            # shows atoms 1-based and stores them 0-based.
            number = QTableWidgetItem()
            number.setData(Qt.ItemDataRole.DisplayRole, index + 1)
            number.setData(Qt.ItemDataRole.UserRole, index)
            self._atom_table.setItem(row, 0, number)
            self._atom_table.setItem(row, 1, QTableWidgetItem(atom.GetSymbol()))
            count = QTableWidgetItem()
            count.setData(Qt.ItemDataRole.DisplayRole, len(self._report_for(index).facts))
            self._atom_table.setItem(row, 2, count)
        self._atom_table.setSortingEnabled(True)

    def _index_is_addressable(self, mol, index: int) -> bool:
        """Does `index` name something in `mol`, for the current subject?

        Bonds are counted separately from atoms on purpose: a structure
        commonly has a different number of each, so an atom-only check
        would still let a stale bond index through on most molecules --
        and a bond report is the half where a wrong-but-in-range index
        describes a DIFFERENT bond rather than raising, which is the
        quieter failure.
        """
        if self._subject == "Molecule":
            return True
        limit = mol.GetNumBonds() if self._subject == "Bond" else mol.GetNumAtoms()
        return 0 <= index < limit

    def _report_for(self, index: int):
        """The report for one subject, cached by structure version.

        The version comes from `StructureCheckService`, the counter that
        already exists and already increments on every structure change.
        Reusing it means a report cannot outlive the structure it
        describes, and means there is one such mechanism rather than two.

        One function for all three kinds because the caching, the version
        and the provider list are identical for each -- only the builder
        differs, and branching on that is smaller than three copies of the
        surrounding logic.
        """
        model, mol = self._molecule()
        if mol is None or model is None:
            return AtomReport(molecule_uuid="", atom_index=index)

        # THE SELECTED INDEX CAN OUTLIVE THE STRUCTURE IT CAME FROM, and
        # the builders index straight into the molecule. Every structure
        # change -- an edit, an undo, adopting a conformer -- arrives here
        # through `_invalidate` while the previous selection is still
        # held, so `RuntimeError: Range Error` is raised from inside a Qt
        # signal handler and the whole dispatch unwinds.
        #
        # Seen in a real session as a wall of `Failed Expression: 8 < 6`
        # (atom 8 of a 6-atom structure) and `19 < 0` (any atom of an
        # empty one), repeated for every subscriber on the bus.
        #
        # `_on_highlight_requested` already learned this and bounds-checks
        # its own indices; this is the same lesson at the other entry
        # point, which is why the fix is a check and not a try/except --
        # there is a correct answer here, and it is "nothing is known
        # about that subject any more".
        if not self._index_is_addressable(mol, index):
            return AtomReport(molecule_uuid=model.uuid, atom_index=index)

        version = 0
        if self._structure_check_service is not None:
            version = self._structure_check_service.current_version(model.uuid)

        key = (model.uuid, version, self._subject, index)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        providers = ()
        if self._atom_fact_service is not None:
            providers = self._atom_fact_service.providers()
        context = self._context_for(model.uuid)
        common = {
            "molecule_uuid": model.uuid,
            "structure_version": version,
            "context": context,
            "providers": providers,
        }
        if self._subject == "Bond":
            report = build_bond_report(mol, index, **common)
        elif self._subject == "Molecule":
            report = build_molecule_report(
                mol, **{**common, "context": {**context, "display_name": model.display_name}}
            )
        else:
            report = build_atom_report(mol, index, **common)
        self._cache[key] = report
        return report

    def _on_row_selected(self) -> None:
        items = self._atom_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        cell = self._atom_table.item(row, 0)
        if cell is None:
            return
        index = cell.data(Qt.ItemDataRole.UserRole)
        if self._subject == "Bond":
            self._bond_index = index
        else:
            self._atom_index = index
            # Only atoms drive the viewers' highlight. Emitting a bond row
            # as an atom index would highlight an unrelated atom, which is
            # worse than highlighting nothing.
            self.atom_selected.emit(index)
        self._render_facts()

    def select_atom(self, atom_index: int) -> None:
        """Select an atom from outside -- the 3D viewer's click lands here.

        Finds the ROW holding that atom rather than assuming row == index,
        because the table is sortable and the two stop matching the moment
        somebody sorts by element.

        **In Bond mode this picks a BOND instead**, from two clicks. See
        `_note_atom_for_bond` for why that is the only option in 3D.
        """
        if not self._atom_is_in_report(atom_index):
            return
        if self._subject == "Bond":
            self._note_atom_for_bond(atom_index)
            return
        self._pending_bond_atom = None
        self._select_row_for(atom_index)

    def _atom_is_in_report(self, atom_index: int) -> bool:
        """Is this index one the report's molecule actually has?

        **The 3D viewer and the report do not always share an index space.**
        A conformer carries EXPLICIT hydrogens; the structure as drawn has
        implicit ones. Ethanol is 3 atoms in the report and 9 in the
        viewer, so clicking a hydrogen in 3D sends index 3-8 -- past the
        end. The heavy atoms line up only because `AddHs` appends, which is
        why the first three agree and nothing warned about the rest.

        Unguarded this is not a silent mismatch but a crash:
        `GetBondBetweenAtoms(1, 5)` raises `RuntimeError: Range Error`
        inside a Qt signal handler. Found by asking what a click on a
        hydrogen would do, during a live check that had not happened to hit
        one.

        **The 2D editor is no longer a source of out-of-range indices, and
        this message must not be read as saying it is.** It was: Ketcher
        sent pool ids rather than molfile positions, so clicking a CARBON in
        a benzene drawn after erasing another ring reported "Atom 9 ... pick
        a heavy atom". That is fixed in the editor's JS (`molfilePosition`
        in tools/ketcher-host/src/main.jsx). Anything still reaching here
        with a bad index is coming from the 3D viewer.
        """
        _model, mol = self._molecule()
        if mol is None:
            return False
        if 0 <= atom_index < mol.GetNumAtoms():
            return True
        self._facts.set_status(
            f"Atom {atom_index + 1} is in the 3D structure but not in the "
            "structure as drawn — the report covers heavy atoms and treats "
            "hydrogens as implicit. Pick a heavy atom."
        )
        return False

    def _note_atom_for_bond(self, atom_index: int) -> None:
        """Resolve a bond from two clicked atoms.

        **3Dmol has no bond picking.** Its `setClickable` callback receives
        an ATOM -- bonds drawn in stick mode are not separately selectable,
        and a click near one resolves to the nearest atom. So the only way
        to name a bond in 3D, using what the library actually provides, is
        two atoms that happen to be bonded.

        Deliberately NOT built on the viewer's existing multi-atom
        selection, which drives distance measurement: sharing that would
        make one gesture mean two things depending on a mode nobody set.
        This lives entirely in the inspector, and the subject selector
        already says which one the user wants.

        A second click on an atom that is NOT bonded to the first starts
        over from the new atom rather than failing, because that is what
        somebody who changed their mind mid-pick did.
        """
        _model, mol = self._molecule()
        if mol is None:
            return
        first = self._pending_bond_atom
        if first is not None and first != atom_index:
            bond = mol.GetBondBetweenAtoms(first, atom_index)
            if bond is not None:
                self._pending_bond_atom = None
                self.select_bond(bond.GetIdx())
                return
        self._pending_bond_atom = atom_index
        self._facts.set_status(
            f"Atom {atom_index + 1} picked. Click an atom bonded to it to "
            "select the bond between them."
        )

    def select_bond(self, bond_index: int) -> None:
        """Select a bond from outside, by index rather than by row.

        Same reason as `select_atom`, and it is not hypothetical here: a
        test that assumed row 0 held bond 0 got bond 16, because the table
        keeps whatever sort order was last applied.
        """
        self._pending_bond_atom = None
        _model, mol = self._molecule()
        if mol is not None and not (0 <= bond_index < mol.GetNumBonds()):
            # This guard cannot catch the mismatch that actually happened:
            # Ketcher used to send POOL IDS rather than molfile positions,
            # and a wrong bond index usually stays in range, so the panel
            # described a DIFFERENT bond and looked as though it worked.
            # Fixed in the editor's JS (`molfilePosition` in
            # tools/ketcher-host/src/main.jsx); kept here for the 3D
            # viewer, whose explicit hydrogens really do run off the end.
            self._facts.set_status(
                f"Bond {bond_index + 1} is not in the structure as drawn."
            )
            return
        self._select_row_for(bond_index)

    def _select_row_for(self, index: int) -> None:
        for row in range(self._atom_table.rowCount()):
            cell = self._atom_table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == index:
                self._atom_table.selectRow(row)
                return

    def _selected_index(self) -> int | None:
        """Which subject is showing, or None when nothing is selected.

        A molecule always has one, so it needs no selection -- returning 0
        here is what lets the render path stay identical for all three.
        """
        if self._subject == "Molecule":
            return 0 if self._molecule()[1] is not None else None
        if self._subject == "Bond":
            return self._bond_index
        return self._atom_index

    def _on_subject_changed(self, subject: str) -> None:
        self._subject = subject
        self._pending_bond_atom = None
        # A molecule has one subject, so the row list is meaningless for it
        # and is hidden rather than shown holding a single inert row.
        self._atom_table.setVisible(subject != "Molecule")
        self._rebuild_atom_table()
        self._render_facts()

    # --- rendering ---------------------------------------------------------

    def _render_facts(self) -> None:
        """Hand the current report to the view. That is the whole method.

        It used to be ninety lines of sections, filtering and rows, all of
        which now lives in `FactView`, where the bond, molecule, Lewis and
        regulatory surfaces get it too.
        """
        index = self._selected_index()
        if index is None:
            noun = self._subject.lower()
            self._facts.clear(
                f"No {noun} selected",
                f"Select a {noun} above to see what is known about it.",
            )
            return
        report = self._report_for(index)
        self._facts.set_report(report, report_header(report), _summary_line(report))

    def _on_highlight_requested(self, atom_indices: tuple) -> None:
        """Paint the atoms a hovered fact is about.

        BOUNDS-CHECKED against the report, not passed straight through. A
        conformer carries explicit hydrogens and a report usually does not
        -- ethanol is 3 atoms in a report and 9 in the 3D viewer -- and an
        out-of-range index raised `RuntimeError: Range Error` inside a Qt
        signal handler the last time this was assumed.
        """
        safe = tuple(i for i in atom_indices if self._atom_is_in_report(i))
        self.atoms_highlighted.emit(safe)

    # --- export ------------------------------------------------------------

    def _on_copy_clicked(self) -> None:
        """Copy, with a message the view could not have written.

        `FactView` knows no chemistry, so with nothing to show it can only
        say "Nothing selected." This panel knows whether the subject is an
        atom, a bond or a molecule, and says which.
        """
        if self._selected_index() is None:
            noun = self._subject.lower()
            article = "an" if noun[0] in "aeiou" else "a"
            self._facts.set_status(f"Select {article} {noun} first.")
            return
        self._facts._on_copy_clicked()



# The formatters moved to `ui/report_format.py` so `FactView` can reach
# them without importing a panel. Re-exported here so every existing
# `atom_inspector_panel.format_report` import keeps working.
from openchem.ui.report_format import format_report  # noqa: E402  (deliberately last)

__all__ = ["AtomInspectorPanel", "format_report", "report_header"]


#: The handful of values people want before anything else. Read off the
#: report's own facts by label -- NOT recomputed, so this cannot become a
#: second source of truth about what a molecule weighs.
_SUMMARY_LABELS = ("Formula", "Molecular weight", "TPSA", "LogP", "HBA", "HBD")


def _summary_line(report) -> str:
    """The pinned headline above the sections.

    Scientists want formula, weight and a few descriptors immediately, not
    after opening a category. Empty for atoms and bonds: their identity is
    already in the title, and repeating it would be noise.
    """
    if not isinstance(report, MoleculeReport):
        return ""
    by_label = {fact.label: fact.display_value for fact in report.facts}
    parts = [f"{label}: {by_label[label]}" for label in _SUMMARY_LABELS if label in by_label]
    return "   ".join(parts)
