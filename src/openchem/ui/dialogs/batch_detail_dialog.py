"""One molecule's batch results, rendered the way Properties renders them.

**THIS IS THE POINT OF THE WHOLE BATCH REBUILD.** A calculator that is one
coherent result in the Properties panel had become N unrelated numeric
columns here, with no Details view and no inspector -- and `FactView` was
sitting three docks away, already generic, already the Properties panel's
"Details..." for sixteen calculators, its own docstring saying it knows no
chemistry and takes anything with `facts` / `by_category()` / `find()`.

So there is no rendering in this file. It merges the molecule's retained
results into one report (`BatchResultStore.merged_report`) and hands that
over. Building a second renderer for the same facts is exactly the
divergence this change exists to end -- and two renderers of one thing is a
mistake this repo has paid for four times.

Results a report cannot show -- a per-atom dataset, a spectrum, a structure
set -- are listed separately with their own inspector, because those have a
real view and a table cell was never it.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.batch import BatchResultStore
from openchem.domain.molecule import MoleculeModel
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

logger = logging.getLogger("openchem.ui")

#: Carried on the button rather than closed over. **NEVER A LAMBDA
#: CAPTURING `self`** -- PySide6 holds a connected plain callable STRONGLY
#: and a QObject's bound method weakly, so a self-capturing lambda roots
#: the whole dialog for the life of the process. This repo has paid for
#: that in the Property panel (one per registered calculator), the periodic
#: table (118 cells) and the external-tools dialog.
_CALCULATOR_PROPERTY = "openchem_calculator_id"

_HELP: dict[str, HelpTooltip] = {
    "inspect": HelpTooltip(
        text=(
            "Open this result in its own inspector.\n\n"
            "A per-atom dataset, a spectrum or a set of structures has no "
            "single number, so a table cell can only name it. The "
            "inspector is where the values are actually shown -- coloured "
            "onto the structure, or plotted.\n\n"
            "A limited number can be open at once; past that the next one "
            "is refused rather than opened, and it says so."
        ),
        tier=2,
        help_id="batch.open_inspector",
        topic="batch",
    ),
}


class BatchDetailDialog(QDialog):
    """Every retained result for one molecule of a batch run."""

    def __init__(
        self,
        engine,
        molecule: MoleculeModel,
        store: BatchResultStore,
        structure_version: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._molecule = molecule
        self._store = store
        self._structure_version = structure_version

        self.setWindowTitle(f"Batch results - {molecule.display_name}")
        self.resize(560, 680)
        layout = QVBoxLayout(self)

        report = store.merged_report(molecule.uuid, structure_version)
        if report is None:
            # NOT an empty FactView. "Nothing has been computed for this
            # molecule" and "every calculator ran and had nothing to say"
            # are different statements, and an empty report says the
            # second one.
            layout.addWidget(
                QLabel(
                    f"Nothing has been computed for {molecule.display_name} yet.\n\n"
                    "Tick the properties you want and open this molecule again, "
                    "or run them over the whole project.",
                    self,
                )
            )
        else:
            from openchem.ui.widgets.fact_view import FactView

            view = FactView(self)
            view.set_report(report, f"{molecule.display_name}")
            layout.addWidget(view, 1)

        extra = store.non_scalar_results(molecule.uuid, structure_version)
        if extra:
            layout.addWidget(self._inspector_box(extra))

    def _inspector_box(self, extra: dict[str, object]) -> QWidget:
        box = QGroupBox("Results with their own view", self)
        rows = QVBoxLayout(box)
        for calculator_id, result in sorted(extra.items()):
            row = QHBoxLayout()
            name = getattr(result, "name", "") or calculator_id
            row.addWidget(QLabel(str(name), box))
            row.addStretch(1)
            button = QPushButton("Inspect...", box)
            button.setProperty(_CALCULATOR_PROPERTY, calculator_id)
            button.clicked.connect(self._on_inspect_clicked)
            apply_help_tooltip(button, _HELP["inspect"])
            row.addWidget(button)
            rows.addLayout(row)
        return box

    def _on_inspect_clicked(self) -> None:
        button = self.sender()
        if button is None:
            return
        calculator_id = button.property(_CALCULATOR_PROPERTY)
        results = self._store.for_molecule(self._molecule.uuid, self._structure_version)
        result = results.get(calculator_id)
        if result is None:
            return
        self.open_inspector(result)

    def open_inspector(self, result) -> bool:
        """Open one result's inspector, or refuse and say why.

        **THE REFUSAL IS THE FEATURE.** Every inspector holds a
        `Mol3DViewerBackend`, which is a `QWebEngineView` and therefore a
        Chromium process of its own -- measured, exactly one each. Opening
        one per row of a 200-molecule batch is how this project hung a
        machine once already.
        """
        from openchem.chem.calculation_input import canonical_conformer
        from openchem.ui.dialogs.calculator_inspector_dialog import (
            CalculatorInspectorDialog,
            inspector_budget_message,
        )

        refusal = inspector_budget_message()
        if refusal is not None:
            QMessageBox.information(self, "Too many inspectors open", refusal)
            return False

        best = canonical_conformer(self._molecule)
        dialog = CalculatorInspectorDialog(
            self._engine,
            self._molecule,
            result,
            best.molblock if best is not None else None,
            self,
        )
        # Modeless, so several can stand side by side -- which is the whole
        # request. `exec()` would make the cap meaningless by allowing
        # exactly one.
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.show()
        return True
