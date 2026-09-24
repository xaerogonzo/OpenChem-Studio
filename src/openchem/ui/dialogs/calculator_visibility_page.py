"""The Settings page that says which calculators the launcher offers, and why some are not.

**A CALCULATOR THAT IS HIDDEN MUST BE EXPLAINED WHERE YOU WOULD LOOK FOR IT.**
Thermophysical Properties (Joback) and Detonation used to sit in the launcher
saying "Not applicable" for nearly everything drawn (`domain/calculator_support`).
They are hidden by default now, which is only an improvement if a person who
wonders where they went finds a page that names them, says WHY each is not
offered, links to the section that explains it, and lets them turn it on.

**EVERY ROW IS THE EFFECTIVE STATE, NOT THE STORED ONE.** The tick beside a
calculator says whether the launcher offers it now -- the default, the master
toggle and this person's own choice combined by `domain.calculator_support.
is_visible`, the same function the Properties panel reads, so the page and the
launcher cannot disagree. Ticking it stores a choice only when that differs from
what the defaults would give; ticking it back to the default forgets the choice
rather than storing a redundant one, so a later change of default still reaches
this person.

**IT CHANGES DISCOVERY ONLY.** Nothing here runs a calculator, removes a result,
or hides Help for one; a hidden calculator stays documented and its stored
results stay readable.

Only calculators with a DECLARED support level are listed. A calculator nobody has
classified has nothing to explain, and listing sixty-six rows saying nothing would
bury the two that do.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import SHOW_HIDDEN_CALCULATORS, Settings
from openchem.domain.calculator_support import (
    Visibility,
    help_anchor_for,
    is_classified,
    is_visible,
    support_of,
)
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: Qt property naming which calculator a row's control belongs to. It travels on
#: the control and comes back through `sender()`, because a lambda capturing
#: `self` in `connect()` roots the dialog for the life of the process.
_CALCULATOR_PROPERTY = "openchem_calculator_id"

#: The stage as a person reads it. `SupportStage` values are ids, not display text.
_STAGE_WORDS = {"experimental": "Experimental", "limited": "Limited", "stable": "Stable"}

#: The contracts, one per concept. Every row's tick shares one and every row's
#: Learn more shares another: which calculator is what `instance_path` says.
_HELP = {
    "master": HelpTooltip(
        text=(
            "Off (the default): calculators that are limited, experimental or specialist "
            "are not offered in the Properties panel, and \"Run selected\" never includes "
            "them. On: they are offered, each with its support level in this list.\n\n"
            "A choice made for one calculator below always wins. This changes what is "
            "offered, never what exists: hidden calculators stay in the Help, and results "
            "already computed stay readable."
        ),
        tier=2,
        help_id="settings.show_hidden_calculators",
        topic="settings",
        help_anchor="settings",
    ),
    "row": HelpTooltip(
        text=(
            "Whether the Properties panel offers this calculator. The tick shows what is "
            "happening now -- the default, the setting above and your own choice "
            "combined -- and changing it stores a choice for this calculator only.\n\n"
            "It changes what is offered, never what exists: nothing is run or removed, and "
            "the Help section for it stays available."
        ),
        tier=2,
        help_id="settings.calculator_offered",
        topic="settings",
        help_anchor="settings",
    ),
    "learn_more": HelpTooltip(
        text=(
            "Opens the Help section for this calculator: what it computes, what it needs, "
            "what it refuses and why, and how far its numbers can be trusted."
        ),
        tier=1,
        help_id="settings.calculator_learn_more",
        topic="settings",
        help_anchor="settings",
    ),
    "reset": HelpTooltip(
        text=(
            "Puts every calculator back to its default: the setting above turned off and "
            "every choice of your own forgotten. Nothing is run or removed."
        ),
        tier=1,
        help_id="settings.reset_calculator_visibility",
        topic="settings",
        help_anchor="settings",
    ),
}


class CalculatorVisibilityPage(QWidget):
    """See the module docstring."""

    def __init__(
        self,
        settings: Settings,
        definitions: list,
        parent: QWidget | None = None,
        *,
        open_help: Callable[[str], None] | None = None,
    ) -> None:
        """`definitions` is every registered calculator; only the classified ones are listed.

        `open_help` is given a help anchor and opens it. Left None, the page
        opens a non-modal `HelpDialog` CHILD of itself: a modal Settings window
        blocks input to every window except its own children, so a help window
        parented to the main window would open unclickable.
        """
        super().__init__(parent)
        self._settings = settings
        self._definitions = sorted(
            (d for d in definitions if is_classified(d)), key=lambda d: d.display_name
        )
        self._all_ids = [d.calculator_id for d in definitions]
        self._open_help = open_help
        self._help_window = None
        self._row_ticks: dict[str, QCheckBox] = {}

        self._master = QCheckBox("Offer calculators that are hidden by default", self)
        self._master.setObjectName("showHiddenCalculators")
        self._master.setChecked(bool(settings.preference(SHOW_HIDDEN_CALCULATORS)))
        apply_help_tooltip(self._master, _HELP["master"])
        self._master.toggled.connect(self._on_master_toggled)

        self._reset = QPushButton("Reset to defaults", self)
        self._reset.setObjectName("resetCalculatorVisibility")
        self._reset.setAutoDefault(False)
        apply_help_tooltip(self._reset, _HELP["reset"])
        self._reset.clicked.connect(self._on_reset_clicked)

        rows = QWidget(self)
        rows_layout = QVBoxLayout(rows)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        for definition in self._definitions:
            rows_layout.addWidget(self._build_row(definition, rows))
        rows_layout.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(rows)

        heading = QLabel("<b>Calculators</b>", self)
        note = QLabel(
            "Some calculators refuse most of what people draw, or need inputs no structure "
            "can supply. They are not offered by default so they do not read as everyday "
            "equipment. Each is listed here with the reason, and can be turned on.",
            self,
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666666;")
        empty = QLabel("No calculator has a declared support level yet.", self)
        empty.setVisible(not self._definitions)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addWidget(self._master)
        layout.addWidget(empty)
        layout.addWidget(scroll, 1)
        controls = QHBoxLayout()
        controls.addWidget(self._reset)
        controls.addStretch(1)
        layout.addLayout(controls)

    # --- rows ----------------------------------------------------------------

    def _build_row(self, definition, parent: QWidget) -> QWidget:
        support = support_of(definition)
        row = QFrame(parent)
        row.setObjectName(f"calculatorRow:{definition.calculator_id}")
        row.setFrameShape(QFrame.Shape.StyledPanel)

        tick = QCheckBox(definition.display_name, row)
        tick.setObjectName(f"calculatorOffered:{definition.calculator_id}")
        tick.setProperty(_CALCULATOR_PROPERTY, definition.calculator_id)
        tick.setChecked(self._settings.calculator_is_visible(definition))
        apply_help_tooltip(tick, _HELP["row"])
        tick.toggled.connect(self._on_row_toggled)
        self._row_ticks[definition.calculator_id] = tick

        level = _STAGE_WORDS[support.stage.value]
        hidden = " -- hidden by default" if support.default_visibility is Visibility.HIDDEN else ""
        badge = QLabel(f"<b>{level}</b>{hidden}", row)
        badge.setObjectName(f"calculatorLevel:{definition.calculator_id}")

        learn_more = QPushButton("Learn more", row)
        learn_more.setObjectName(f"calculatorLearnMore:{definition.calculator_id}")
        learn_more.setProperty(_CALCULATOR_PROPERTY, definition.calculator_id)
        learn_more.setAutoDefault(False)
        apply_help_tooltip(learn_more, _HELP["learn_more"])
        learn_more.clicked.connect(self._on_learn_more_clicked)

        header = QHBoxLayout()
        header.addWidget(tick, 1)
        header.addWidget(badge)
        header.addWidget(learn_more)

        layout = QVBoxLayout(row)
        layout.addLayout(header)
        if support.support_reason:
            why = QLabel(f"<b>Why:</b> {support.support_reason}", row)
            why.setObjectName(f"calculatorWhy:{definition.calculator_id}")
            why.setWordWrap(True)
            layout.addWidget(why)
        if support.scope_note:
            covers = QLabel(f"<b>Covers:</b> {support.scope_note}", row)
            covers.setObjectName(f"calculatorCovers:{definition.calculator_id}")
            covers.setWordWrap(True)
            layout.addWidget(covers)
        return row

    def offered(self, calculator_id: str) -> bool:
        """What the row's tick says, for a test or a caller."""
        return self._row_ticks[calculator_id].isChecked()

    def _definition(self, calculator_id: str):
        return next(d for d in self._definitions if d.calculator_id == calculator_id)

    # --- changes -------------------------------------------------------------

    def _on_master_toggled(self, checked: bool) -> None:
        self._settings.set_preference(SHOW_HIDDEN_CALCULATORS, checked)
        self._refresh_rows()

    def _on_row_toggled(self, checked: bool) -> None:
        calculator_id = str(self.sender().property(_CALCULATOR_PROPERTY))
        definition = self._definition(calculator_id)
        # What the defaults alone would give, ignoring this person's own choice.
        baseline = is_visible(
            definition, show_hidden=bool(self._settings.preference(SHOW_HIDDEN_CALCULATORS)),
            override=None,
        )
        if checked == baseline:
            self._settings.set_calculator_override(calculator_id, None)
        else:
            self._settings.set_calculator_override(
                calculator_id, Visibility.SHOWN if checked else Visibility.HIDDEN
            )

    def _on_reset_clicked(self) -> None:
        self._settings.reset_calculator_visibility(self._all_ids)
        self._master.blockSignals(True)
        self._master.setChecked(False)
        self._master.blockSignals(False)
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        """Put every tick in step with the effective state, without storing anything."""
        for calculator_id, tick in self._row_ticks.items():
            tick.blockSignals(True)
            tick.setChecked(self._settings.calculator_is_visible(self._definition(calculator_id)))
            tick.blockSignals(False)

    # --- help ----------------------------------------------------------------

    def _on_learn_more_clicked(self) -> None:
        calculator_id = str(self.sender().property(_CALCULATOR_PROPERTY))
        self.show_help_for(calculator_id)

    def show_help_for(self, calculator_id: str) -> None:
        anchor = help_anchor_for(calculator_id)
        if self._open_help is not None:
            self._open_help(anchor)
            return
        from openchem.ui.dialogs.help_dialog import HelpDialog

        if self._help_window is None:
            self._help_window = HelpDialog(self, anchor)
        self._help_window.show_topic(anchor)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()
