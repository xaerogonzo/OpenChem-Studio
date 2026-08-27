"""State an energetic FORMULATION: components, mass fractions, loading density.

The creation surface for `domain.formulation.FormulationModel`. It exists
because the arithmetic had none: `build_formulation_report` shipped
correct, sourced and tested, and **nothing a user could press reached
it** -- the same gap PR #41 shipped for four whole modules, recurring one
level down inside a module that was itself perfectly reachable. See
`tests/test_calculator_reachability.py`.

## IT COLLECTS WHAT CANNOT BE DERIVED, and that is most of it

Three of the four inputs are refusals turned into fields, and each is
sourced in `chem/energetics.py` rather than being a gap nobody got round
to filling:

    mass fractions     stated, never normalised -- 94.5 + 5.0 renormalises
                       to an ordinary-looking recipe nobody meant
    component dHf      supplied, never estimated -- the published Trouton
                       bridge to the condensed phase excludes every
                       classic energetic material, its domain stopping at
                       two internal rotors where the nitro groups ARE the
                       rotors
    loading density    MEASURED, never a weighted average of the
                       components' crystal densities

The last is the dangerous one, and the dialog says so on its face rather
than only in a tooltip: detonation pressure goes as the SQUARE of it, so
the plausible substitution is wrong by a large factor while producing a
number that looks entirely ordinary.

## MASS IN, MOLES FOR THE FORMULA

Proportions are MASS fractions, because that is how a recipe is mixed.
The composite CaHbNcOd is per-mole and the compositing converts. The
error to guard is treating one as the other, and it is silent -- measured
on ANFO, both forms land inside Kamlet-Jacobs' arbitrary and differ by
about 3% in oxygen. The mass-fraction tooltip carries that, because a
reader typing 0.945 needs to know which quantity they typed.

## IT KNOWS NO CHEMISTRY

Components arrive as plain `(name, smiles)` pairs. Deriving a SMILES from
a drawn molecule needs RDKit, which `tests/test_layering.py` forbids
here, so the caller does that and this dialog only collects. That is also
what lets it be built with no arguments at all, which is what puts it in
the bare-context half of `ui/dialogs/inventory.py`.
"""

from __future__ import annotations

from openchem.domain.formulation import (
    FRACTION_TOLERANCE,
    FormulationComponent,
    FormulationModel,
)
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

#: Columns of the recipe table, in order.
_NAME_COLUMN = 0
_SMILES_COLUMN = 1
_FRACTION_COLUMN = 2
_ENTHALPY_COLUMN = 3

#: `loading_density` is `float | None` and a spin box has no null, so
#: zero is the sentinel and is displayed as "Not stated". A charge of
#: zero density is not a thing, so no real value is lost, and the report
#: refuses rather than guessing when it is absent.
_DENSITY_NOT_STATED = 0.0

#: A packed charge runs roughly 0.8 (ANFO) to 1.9 (pressed RDX/TNT)
#: g/cm3. The range is generous either side rather than tight: it is a
#: typo guard, not a claim about what densities are achievable.
_MIN_DENSITY = 0.0
_MAX_DENSITY = 5.0


_HELP: dict[str, HelpTooltip] = {
    "name": HelpTooltip(
        text=(
            "What to call this formulation in the project.\n\n"
            "A label only: it names the recipe and takes no part in any "
            "calculation."
        ),
        tier=1,
        help_id="formulation.name",
    ),
    "component_name": HelpTooltip(
        text=(
            "What to call this component in the report.\n\n"
            "A label only. The structure is taken from the SMILES beside "
            "it, so a blank name costs nothing but readability."
        ),
        tier=1,
        help_id="formulation.component_name",
    ),
    "component_structure": HelpTooltip(
        text=(
            "The component's structure, as SMILES.\n\n"
            "This supplies the element counts the composite formula is "
            "built from, so a component whose SMILES does not parse is "
            "refused rather than quietly skipped. It is stored as SMILES "
            "rather than as a reference to a molecule in the project, so "
            "the formulation still opens once that list has been edited."
        ),
        tier=2,
        help_id="formulation.component_structure",
    ),
    "mass_fraction": HelpTooltip(
        text=(
            "The component's proportion by MASS, as a fraction of 1 "
            "(ANFO's ammonium nitrate is 0.945).\n\n"
            "MASS, NOT MOLES, and the distinction changes the answer. The "
            "composite CaHbNcOd is a per-mole quantity, so the "
            "compositing converts these to mole fractions, while the heat "
            "of detonation is per gram and stays mass-weighted. Measured "
            "on ANFO, treating these as mole fractions moves the oxygen "
            "count about 3% and still lands inside the method's window, "
            "so no domain check catches it. The composite formula on the "
            "report is what lets you verify the arithmetic.\n\n"
            "The stated fractions must sum to 1. They are checked rather "
            "than normalised: 94.5 + 5.0 rescales to a perfectly ordinary "
            "recipe that is not the one you meant."
        ),
        tier=3,
        help_id="formulation.mass_fraction",
    ),
    "component_enthalpy": HelpTooltip(
        text=(
            "The component's CONDENSED-PHASE standard enthalpy of "
            "formation, in kcal/mol.\n\n"
            "Condensed phase means the solid or liquid as loaded, not the "
            "ideal gas. It is required and deliberately never estimated: "
            "Joback gives the ideal-gas value, and the published bridge "
            "from gas to condensed phase excludes every classic energetic "
            "material, its domain stopping at two internal rotors where "
            "the nitro groups ARE the rotors.\n\n"
            "CHNO explosives run roughly -200 to +200 kcal/mol. It enters "
            "the heat of detonation divided by the mean molar mass, so an "
            "error here moves Q, and Q moves both the pressure and the "
            "velocity."
        ),
        tier=3,
        help_id="formulation.component_enthalpy",
    ),
    "add": HelpTooltip(
        text=(
            "Adds an empty component row to the recipe.\n\n"
            "Fill in its structure, mass fraction and enthalpy; the "
            "running total below updates as you type."
        ),
        tier=1,
        help_id="formulation.add_component",
    ),
    "remove": HelpTooltip(
        text=(
            "Removes the selected component row from the recipe.\n\n"
            "The remaining fractions are left exactly as typed rather "
            "than rescaled, so the total will no longer sum to 1 until "
            "you restate them."
        ),
        tier=1,
        help_id="formulation.remove_component",
    ),
    "pick": HelpTooltip(
        text=(
            "Adds a component row from a molecule already in the "
            "project.\n\n"
            "Fills in the name and the SMILES only. The mass fraction and "
            "the enthalpy of formation still have to be stated, because "
            "neither can be derived from the structure."
        ),
        tier=1,
        help_id="formulation.add_from_project",
    ),
    "loading_density": HelpTooltip(
        text=(
            "The MEASURED bulk density the charge was loaded to, in "
            "g/cm3. Leave at zero for 'not stated'.\n\n"
            "THIS IS THE DENSITY OF THE ACTUAL CHARGE, never a weighted "
            "average of the components' crystal densities. That "
            "substitution is arithmetically reasonable and wrong: a "
            "packed charge is nowhere near its ingredients' crystals, and "
            "detonation pressure goes as the SQUARE of this number, so "
            "the error is not a small one. There is no source-backed "
            "route from a recipe to it, so it is supplied or the pressure "
            "and velocity are refused.\n\n"
            "Range 0 to 5 g/cm3, which is a typo guard rather than a "
            "claim about achievable densities."
        ),
        tier=3,
        help_id="formulation.loading_density",
    ),
}


class FormulationDialog(QDialog):
    """States a formulation, or edits one already in the project.

    Built with no arguments for an empty recipe, or handed an existing
    `FormulationModel` to edit. `molecules` is a sequence of
    `(display_name, smiles)` pairs offered in the picker -- plain tuples
    rather than `MoleculeModel`s, because turning a drawing into a SMILES
    needs RDKit and this layer may not import it.
    """

    def __init__(
        self,
        formulation: FormulationModel | None = None,
        *,
        molecules: tuple[tuple[str, str], ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Energetic Formulation")
        self.resize(640, 460)
        # The uuid is carried through an edit rather than regenerated, so
        # editing a formulation updates it instead of quietly producing a
        # second one under the same name.
        self._uuid = formulation.uuid if formulation is not None else None
        self._notes = formulation.notes if formulation is not None else ""
        self._metadata = dict(formulation.metadata) if formulation is not None else {}

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("ANFO, Composition B, ...")
        apply_help_tooltip(self._name_edit, _HELP["name"])

        self._table = QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels(
            ["Component", "SMILES", "Mass fraction", "dHf (kcal/mol)"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(
            _SMILES_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        # A column header is a documentable control in its own right (see
        # `tooltip_inventory`), and these four are where both traps live,
        # so the contracts go here rather than on the table.
        for column, key in (
            (_NAME_COLUMN, "component_name"),
            (_SMILES_COLUMN, "component_structure"),
            (_FRACTION_COLUMN, "mass_fraction"),
            (_ENTHALPY_COLUMN, "component_enthalpy"),
        ):
            apply_help_tooltip(self._table.horizontalHeaderItem(column), _HELP[key])
        self._table.itemChanged.connect(self._on_item_changed)

        self._add_button = QPushButton("Add component", self)
        apply_help_tooltip(self._add_button, _HELP["add"])
        self._add_button.clicked.connect(self._add_blank_component)

        self._remove_button = QPushButton("Remove", self)
        apply_help_tooltip(self._remove_button, _HELP["remove"])
        self._remove_button.clicked.connect(self._remove_selected_component)

        self._pick_combo = QComboBox(self)
        self._pick_combo.addItem("Add from project...", None)
        for display_name, smiles in molecules:
            self._pick_combo.addItem(display_name, smiles)
        self._pick_combo.setEnabled(bool(molecules))
        apply_help_tooltip(self._pick_combo, _HELP["pick"])
        self._pick_combo.activated.connect(self._on_molecule_picked)

        self._density_spin = QDoubleSpinBox(self)
        self._density_spin.setRange(_MIN_DENSITY, _MAX_DENSITY)
        self._density_spin.setDecimals(3)
        self._density_spin.setSingleStep(0.05)
        self._density_spin.setSuffix(" g/cm3")
        self._density_spin.setSpecialValueText("Not stated")
        self._density_spin.setValue(_DENSITY_NOT_STATED)
        apply_help_tooltip(self._density_spin, _HELP["loading_density"])

        self._total_label = QLabel(self)
        self._total_label.setWordWrap(True)

        # Says the two quiet parts out loud, because a tooltip is absent
        # from every screenshot and these are the two errors that produce
        # a plausible wrong number rather than an obvious one.
        note = QLabel(
            "Proportions are by MASS. The loading density is the measured bulk "
            "density of the charge, never an average of the components' crystal "
            "densities, since pressure goes as its square.",
            self,
        )
        note.setWordWrap(True)

        # No parent argument: `QDialogButtonBox`'s second positional is an
        # ORIENTATION, and the layout parents it a few lines below anyway.
        # Same construction as `ConformerOptionsDialog`.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Bound methods, never a self-capturing lambda: PySide6 holds a
        # connected plain callable STRONGLY. See CLAUDE.md.
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self._add_button)
        row.addWidget(self._remove_button)
        row.addWidget(self._pick_combo)
        row.addStretch(1)

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Loading density:", self._density_spin)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._table, 1)
        layout.addLayout(row)
        layout.addWidget(self._total_label)
        layout.addWidget(note)
        layout.addWidget(buttons)

        if formulation is not None:
            self._load(formulation)
        self._refresh_total()

    # --- contents ----------------------------------------------------------

    def _load(self, formulation: FormulationModel) -> None:
        self._name_edit.setText(formulation.display_name)
        if formulation.loading_density is not None:
            self._density_spin.setValue(float(formulation.loading_density))
        for component in formulation.components:
            self._append_row(
                component.display_name,
                component.smiles,
                f"{component.mass_fraction:g}",
                f"{component.enthalpy_kcal_per_mol:g}",
            )

    def _append_row(self, name: str, smiles: str, fraction: str, enthalpy: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for column, text in (
            (_NAME_COLUMN, name),
            (_SMILES_COLUMN, smiles),
            (_FRACTION_COLUMN, fraction),
            (_ENTHALPY_COLUMN, enthalpy),
        ):
            self._table.setItem(row, column, QTableWidgetItem(text))

    def _add_blank_component(self) -> None:
        self._append_row("", "", "", "")
        self._refresh_total()

    def _remove_selected_component(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._refresh_total()

    def _on_molecule_picked(self, index: int) -> None:
        smiles = self._pick_combo.itemData(index)
        if not smiles:
            return
        self._append_row(self._pick_combo.itemText(index), str(smiles), "", "")
        # Back to the prompt, so the combo reads as an action rather than
        # as a setting that now claims a value.
        self._pick_combo.setCurrentIndex(0)
        self._refresh_total()

    def _on_item_changed(self, _item) -> None:
        self._refresh_total()

    # --- the running total -------------------------------------------------

    def _cell_text(self, row: int, column: int) -> str:
        item = self._table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _stated_fractions(self) -> list[float]:
        values: list[float] = []
        for row in range(self._table.rowCount()):
            try:
                values.append(float(self._cell_text(row, _FRACTION_COLUMN)))
            except ValueError:
                continue
        return values

    def _refresh_total(self) -> None:
        """Says where the recipe stands, while it is being typed.

        The SUM is shown rather than only its verdict, because "0.995"
        tells you a component is short and "not consistent" does not.
        """
        rows = self._table.rowCount()
        if rows == 0:
            self._total_label.setText("No components yet.")
            return
        values = self._stated_fractions()
        total = sum(values)
        if len(values) != rows:
            self._total_label.setText(
                f"Mass fractions total {total:.4g} over {len(values)} of {rows} "
                "rows - the rest are blank or not numbers."
            )
            return
        if abs(total - 1.0) <= FRACTION_TOLERANCE:
            self._total_label.setText(f"Mass fractions total {total:.4g}.")
            return
        self._total_label.setText(
            f"Mass fractions total {total:.4g}, which is not 1. They are checked "
            "rather than rescaled, so state them as mixed."
        )

    # --- the result --------------------------------------------------------

    def status_text(self) -> str:
        """What the running total currently says.

        Public so a guard can read it without reaching into a private --
        the string is part of what this dialog is FOR, since a recipe
        that does not sum to 1 is the error it exists to make visible.
        """
        return self._total_label.text()

    def loading_density(self) -> float | None:
        value = self._density_spin.value()
        return None if value == _DENSITY_NOT_STATED else value

    def formulation(self) -> FormulationModel:
        """The recipe as stated. A blank or unparseable cell becomes 0.0.

        Deliberately TOTAL: it returns what was typed, and the report
        says what is wrong with it. Refusing to build a model here would
        put a second, quieter copy of the refusal rules in the dialog,
        where they would drift from the ones in `chem/energetics.py` --
        and a dialog that will not close is a worse way to learn that a
        fraction is missing than a report that names it.
        """
        components: list[FormulationComponent] = []
        for row in range(self._table.rowCount()):
            smiles = self._cell_text(row, _SMILES_COLUMN)
            name = self._cell_text(row, _NAME_COLUMN)
            if not smiles and not name:
                continue
            components.append(
                FormulationComponent(
                    smiles=smiles,
                    mass_fraction=_as_float(self._cell_text(row, _FRACTION_COLUMN)),
                    enthalpy_kcal_per_mol=_as_float(
                        self._cell_text(row, _ENTHALPY_COLUMN)
                    ),
                    display_name=name,
                )
            )
        fields = {
            "display_name": self._name_edit.text().strip() or "Untitled formulation",
            "components": tuple(components),
            "loading_density": self.loading_density(),
            "notes": self._notes,
            "metadata": dict(self._metadata),
        }
        if self._uuid is not None:
            fields["uuid"] = self._uuid
        return FormulationModel(**fields)


def _as_float(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0
