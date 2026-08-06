"""The Structure Checker: what is wrong, why we think so, and what to do.

Modelled on Marvin's structure checker, with one structural difference that
is forced on us. Marvin highlights the offending atoms in its own canvas;
ours is vendored Ketcher, whose build has no highlighting API at all
(`setHighlights` appears zero times in the bundle). So selecting an issue
highlights in OUR depiction, drawn beside the list -- which turns out to
carry its own advantage, since the depiction stays put while the canvas is
being edited.

Three things the list says that a bare message would not:

- **Which category.** "This valence is impossible" and "these labels
  overlap" are grouped apart, so a real problem is not buried among
  cosmetic ones.
- **What the verdict rests on.** Deterministic or heuristic, in words. A
  threshold somebody chose says so, out loud, next to its own finding.
- **What a fix would cost.** Safe, reversible or lossy, on the button
  itself, before it is pressed.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QMenu,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine
from openchem.domain.structure_issue import (
    CATEGORY_LABELS,
    Basis,
    CheckerResult,
    Severity,
    StructureIssue,
)
from openchem.events.base import EventBus
from openchem.events.events import StructureChecked
from openchem.services.structure_check_service import StructureCheckService

#: severity -> (label, colour). The same Okabe-Ito pair the status
#: indicator uses, for the same colour-vision reason, and always beside a
#: word rather than instead of one.
_SEVERITY = {
    Severity.ERROR: ("Error", "#d55e00"),
    Severity.WARNING: ("Warning", "#e69f00"),
    Severity.INFO: ("Note", "#0072b2"),
}

_BASIS_WORDS = {
    Basis.DETERMINISTIC: "Definite -- this follows from the structure itself.",
    Basis.HEURISTIC: "Judgement -- this uses a threshold somebody chose, so a correct drawing can trip it.",
}

#: What the depiction paints the atoms an issue names.
_HIGHLIGHT = {
    Severity.ERROR: "#d55e00",
    Severity.WARNING: "#e69f00",
    Severity.INFO: "#0072b2",
}

_EMPTY_MESSAGE = (
    "Nothing to report.\n\n"
    "Every check that could run, ran. Anything that could not is listed as skipped, "
    "with the reason."
)


class StructureCheckPanel(QWidget):
    """Grouped findings for the selected molecule, with a fix per issue."""

    def __init__(
        self,
        check_service: StructureCheckService,
        chemistry_engine: ChemistryEngine,
        event_bus: EventBus,
        parent: QWidget | None = None,
        on_apply_fix: Callable[[str, str], None] | None = None,
        on_recheck: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = check_service
        self._engine = chemistry_engine
        self._on_apply_fix = on_apply_fix
        self._on_recheck = on_recheck
        self._result: CheckerResult | None = None
        self._molblock = ""
        #: Why oxidation states were not assigned, when they were not.
        self._refusal = ""

        self._summary = QLabel(_EMPTY_MESSAGE, self)
        self._summary.setWordWrap(True)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["Finding", "Severity"])
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu_requested)
        self._tree.setColumnWidth(0, 360)

        self._depiction = QSvgWidget(self)
        self._depiction.setMinimumHeight(200)

        self._detail = QLabel("", self)
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.TextFormat.RichText)

        # The oxidation-state overlay lives here rather than in the drawing
        # canvas because the canvas is Ketcher and cannot be annotated. It
        # is mirrored as a View menu item, which is the same redundancy
        # Copy SMILES needed: the checkbox is faster once you know it is
        # here, and the menu is how you find out.
        self._oxidation_states = QCheckBox("Show oxidation states", self)
        self._oxidation_states.toggled.connect(self._on_oxidation_states_toggled)

        self._fix_button = QPushButton("Fix", self)
        self._fix_button.setEnabled(False)
        self._fix_button.clicked.connect(self._apply_selected_fix)

        self._recheck_button = QPushButton("Check again", self)
        self._recheck_button.clicked.connect(self._request_recheck)

        buttons = QHBoxLayout()
        buttons.addWidget(self._fix_button)
        buttons.addWidget(self._recheck_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._tree, 1)
        layout.addWidget(self._depiction)
        layout.addWidget(self._oxidation_states)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)

        event_bus.subscribe(StructureChecked, self._on_structure_checked)

    # --- incoming results ---------------------------------------------------

    def set_molblock(self, molblock: str) -> None:
        """The structure the depiction draws. Kept separate from the result
        because a fix needs the molblock and the result only carries
        indices into it."""
        self._molblock = molblock

    def _on_structure_checked(self, event: StructureChecked) -> None:
        """Discard anything the structure has already moved past.

        The whole reason `CheckerResult` carries a version. Editing is
        faster than checking, and a result that arrives after the next edit
        describes atoms that have since been renumbered -- so its
        highlights would point somewhere arbitrary.
        """
        if not self._service.is_current(event.result):
            return
        self.show_result(event.result)

    def show_result(self, result: CheckerResult) -> None:
        self._result = result
        self._tree.clear()
        self._detail.clear()
        self._fix_button.setEnabled(False)
        self._depiction.load(b"")

        grouped = result.by_category()
        for category, issues in grouped.items():
            worst = min(issues, key=lambda i: list(_SEVERITY).index(i.severity)).severity
            parent = QTreeWidgetItem(
                self._tree,
                [f"{CATEGORY_LABELS[category]} ({len(issues)})", _SEVERITY[worst][0]],
            )
            parent.setExpanded(True)
            for issue in issues:
                child = QTreeWidgetItem(parent, [issue.message, _SEVERITY[issue.severity][0]])
                child.setForeground(1, Qt.GlobalColor.black)
                child.setData(0, Qt.ItemDataRole.UserRole, issue)

        if result.skipped:
            skipped_root = QTreeWidgetItem(
                self._tree, [f"Not checked ({len(result.skipped)})", ""]
            )
            skipped_root.setExpanded(False)
            for skipped in result.skipped:
                QTreeWidgetItem(skipped_root, [f"{skipped.checker_id} -- {skipped.reason}", ""])

        self._summary.setText(self._summary_text(result))
        self._render_depiction({})

    def _summary_text(self, result: CheckerResult) -> str:
        if not result.issues and not result.skipped:
            return _EMPTY_MESSAGE
        errors = len(result.errors)
        warnings = len(result.warnings)
        notes = len(result.issues) - errors - warnings
        parts = []
        if errors:
            parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
        if warnings:
            parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
        if notes:
            parts.append(f"{notes} note" + ("s" if notes != 1 else ""))
        headline = ", ".join(parts) if parts else "No issues found"

        explained = [i for i in result.issues if i.explains_editor_warning]
        if explained:
            # The one honest thing we can say about the canvas's own
            # warnings. Ketcher exposes no way to enumerate them, so a
            # general "3 editor warnings ignored" counter is not
            # implementable -- but we DO know when our own correction rules
            # fired, and that is the useful direction anyway.
            headline += (
                f". {len(explained)} valence the editor flags "
                f"{'is' if len(explained) == 1 else 'are'} accepted here -- select "
                "it to see why."
            )
        return headline

    # --- selection ----------------------------------------------------------

    def _on_selection_changed(self) -> None:
        issue = self._selected_issue()
        if issue is None:
            self._detail.clear()
            self._fix_button.setEnabled(False)
            self._fix_button.setText("Fix")
            self._render_depiction({})
            return

        label, colour = _SEVERITY[issue.severity]
        lines = [
            f"<b style='color:{colour}'>{label}</b> &nbsp; <i>{issue.checker_id}</i>",
            issue.message,
            f"<small>{_BASIS_WORDS[issue.basis]}</small>",
        ]
        fix = self._service.fix_for(issue.fix_id)
        if fix is not None:
            lines.append(f"<small><b>{fix.label}</b> ({fix.safety.value}): {fix.description}</small>")
            self._fix_button.setText(f"{fix.label} ({fix.safety.value})")
            self._fix_button.setEnabled(bool(self._molblock))
        else:
            self._fix_button.setText("Fix")
            self._fix_button.setEnabled(False)
        self._detail.setText("<br>".join(lines))

        self._render_depiction({index: _HIGHLIGHT[issue.severity] for index in issue.atom_indices})

    def _selected_issue(self) -> StructureIssue | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        return data if isinstance(data, StructureIssue) else None

    # --- the oxidation-state overlay ----------------------------------------

    def set_oxidation_states_visible(self, visible: bool) -> None:
        """For the View menu item, which mirrors the checkbox."""
        if self._oxidation_states.isChecked() != visible:
            self._oxidation_states.setChecked(visible)

    def oxidation_states_visible(self) -> bool:
        return self._oxidation_states.isChecked()

    def _on_oxidation_states_toggled(self, checked: bool) -> None:
        issue = self._selected_issue()
        colors = (
            {index: _HIGHLIGHT[issue.severity] for index in issue.atom_indices}
            if issue is not None
            else {}
        )
        self._render_depiction(colors)
        if checked and self._refusal:
            # A refusal is the answer, so it has to be visible. Silently
            # drawing nothing would read as the toggle being broken.
            self._detail.setText(
                f"<b>Oxidation states not assigned.</b><br>{self._refusal}"
                "<br><small>An oxidation state is a bookkeeping formalism, not a "
                "measurement, and it describes the structure as drawn.</small>"
            )

    def _oxidation_labels(self) -> dict[int, str]:
        """Atom labels for the overlay, or nothing plus a recorded reason."""
        self._refusal = ""
        if not self._molblock:
            return {}
        try:
            from openchem.chem.oxidation_states import assign, format_state

            mol = self._engine.mol_from_molblock(self._molblock)
            result = assign(mol)
        except Exception as exc:
            self._refusal = f"This structure could not be read for it ({exc})."
            return {}
        if result.refused:
            self._refusal = result.reason
            return {}
        return {
            index: format_state(state)
            for index, state in result.states.items()
            if mol.GetAtomWithIdx(index).GetAtomicNum() != 1
        }

    def _render_depiction(self, atom_colors: dict[int, str]) -> None:
        """Draw the structure with the selected issue's atoms picked out.

        Wrapped because half the structures worth checking are ones RDKit
        refuses -- an unsanitizable molblock is precisely when the checker
        has the most to say, and it is also when the depiction can fail. A
        blank drawing beside a readable message is a much better outcome
        than an exception that takes the whole panel down.
        """
        if not self._molblock:
            self._depiction.load(b"")
            return
        labels = self._oxidation_labels() if self._oxidation_states.isChecked() else {}
        try:
            svg = self._engine.render_2d_svg(
                self._molblock, atom_colors=atom_colors or None, atom_labels=labels or None
            )
        except Exception:
            self._depiction.load(b"")
            return
        self._depiction.load(svg.encode("utf-8"))

    # --- the findings context menu -------------------------------------------

    def _on_context_menu_requested(self, position) -> None:
        """Right-click a finding.

        This is the only place suppression can be reached. `CheckerResult`
        has carried `suppressed` since the engine was written -- query
        atoms, reaction templates and teaching examples are drawn wrong on
        purpose -- but until now nothing in the UI could set it, which made
        the field a promise the app did not keep.
        """
        item = self._tree.itemAt(position)
        if item is not None:
            self._tree.setCurrentItem(item)
        issue = self._selected_issue()
        if issue is None:
            return

        menu = QMenu(self._tree)
        fix = self._service.fix_for(issue.fix_id)
        fix_action = (
            menu.addAction(f"{fix.label} ({fix.safety.value})")
            if fix is not None and self._molblock
            else None
        )
        copy_action = menu.addAction("Copy message")
        menu.addSeparator()
        suppress_action = menu.addAction(f"Ignore '{issue.checker_id}' for this molecule")

        chosen = menu.exec(self._tree.mapToGlobal(position))
        if chosen is None:
            return
        if chosen is fix_action:
            self._apply_selected_fix()
        elif chosen is copy_action:
            QGuiApplication.clipboard().setText(issue.message)
        elif chosen is suppress_action:
            self._suppress(issue.checker_id)

    def _suppress(self, checker_id: str) -> None:
        """Waive a check for the molecule on screen, and re-check at once.

        Waiving is recorded rather than hidden -- the checker reappears
        under "Not checked" with "suppressed for this molecule", so a later
        reader can tell a waived check from a passed one.
        """
        if self._result is None:
            return
        self._service.suppress(self._result.molecule_uuid, checker_id)
        self._request_recheck()

    # --- actions ------------------------------------------------------------

    def _apply_selected_fix(self) -> None:
        issue = self._selected_issue()
        if issue is None or not self._molblock or self._on_apply_fix is None:
            return
        self._on_apply_fix(issue.fix_id, self._molblock)

    def _request_recheck(self) -> None:
        if self._on_recheck is not None:
            self._on_recheck()
