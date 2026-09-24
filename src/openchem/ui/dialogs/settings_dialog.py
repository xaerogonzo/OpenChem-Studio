"""The Settings window: every preference, with External Tools as one section.

**ONE WINDOW, BECAUSE A SETTING WITH NO DISCOVERABLE HOME IS WORSE THAN NONE.**
That is why these preferences waited (ROADMAP, "A Settings page"). Each was a
fixed choice, written down until there was somewhere to put it. External
Tools was already a settings window in all but name, so its tabs moved in as
a section. Every route that opened them opens this window there: the Tools
menu, and the Docking and Quantum Chemistry panels' Configure buttons.

**EVERYTHING APPLIES AS IT CHANGES.** The External Tools tabs always saved a
path the moment it was committed. In a window where some controls waited for
OK and others did not, Close would silently lose one kind of change. The one
change that asks first is lowering the revisions kept, because the result
store drops results the moment the setting is stored
(`ResultStoreService._on_settings_changed`).

**CONTROLS READ AND WRITE ONLY THROUGH `Preference`** (`app/settings.py`), so
the default a control shows and the default its consumer falls back to are
the same number.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import (
    MAX_REVISIONS_KEPT,
    RAIL_HIDES_PANELS,
    RECALC_MODE,
    RECALC_QUIET_MS,
    RECOVERY_DELAY_SECONDS,
    RECOVERY_ENABLED,
    Preference,
    Settings,
)
from openchem.domain.recalc_policy import RecalcMode
from openchem.ui.dialogs.calculator_visibility_page import CalculatorVisibilityPage
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages
from openchem.ui.dialogs.keyboard_shortcuts_page import KeyboardShortcutsPage
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: Section id of how the rail treats panels. Callers open the window at a
#: section by id, never by its label, which is display text.
PANELS = "panels"

#: Section id of recovery copies.
RECOVERY = "recovery"

#: Section id of when drawing recomputes results.
RECALCULATION = "recalculation"

#: Section id of the results kept in memory.
RESULTS = "results"

#: Section id of which calculators the launcher offers, and why some are not.
CALCULATORS = "calculators"

#: Section id of the menu commands' shortcuts.
KEYBOARD = "keyboard"

#: Section id of the remembered file-dialog folders.
FILE_DIALOGS = "file_dialogs"

#: Section id of the External Tools tabs, Storage included.
EXTERNAL_TOOLS = "external_tools"

#: Every section, in the order the list shows them, with its label.
SECTIONS = (
    (PANELS, "Panels"),
    (RECOVERY, "Recovery"),
    (RECALCULATION, "Recalculation"),
    (RESULTS, "Results"),
    (CALCULATORS, "Calculators"),
    (KEYBOARD, "Keyboard"),
    (FILE_DIALOGS, "File dialogs"),
    (EXTERNAL_TOOLS, "External tools"),
)

#: What each remembered folder is FOR, named by the dialogs that use it. The
#: keys must be exactly `DIRECTORY_KINDS`; a test holds them to that set, so a
#: new kind cannot arrive without a row here to forget it from.
DIRECTORY_LABELS = {
    "project": "Projects: Open Project and Save Project",
    "molecule": "Molecules: Import Molecule and Export Molecule",
    "macromolecule": "Macromolecules: Import Macromolecule and Import Crystal Structure",
}

#: Qt property naming which folder a Forget button forgets. It travels on the
#: button and comes back through `sender()`, because a lambda capturing
#: `self` in `connect()` roots the dialog for the life of the process.
_DIRECTORY_KIND_PROPERTY = "openchem_directory_kind"

#: The contracts, one per concept. The three Forget buttons share one: which
#: folder they forget is what `instance_path` already says.
_HELP = {
    "rail": HelpTooltip(
        text=(
            "On (the default): choosing a panel from the rail shows it and hides the "
            "other right-hand panels in its area, so the one you chose gets the whole "
            "column. A panel you have dragged elsewhere, or floated, is never hidden.\n\n"
            "Off: choosing a panel only shows it. Panels already open stay open beside "
            "it, and each one closes from its own title bar."
        ),
        tier=2,
        help_id="settings.rail_hides_panels",
        topic="settings",
        help_anchor="settings",
    ),
    "recovery": HelpTooltip(
        text=(
            "On (the default): shortly after each change, a copy of the unsaved project "
            "and its results is written, and offered back at the next launch if the app "
            "closed without saving. Saving removes the copy.\n\n"
            "Turning this off stops new copies being written. A copy already written is "
            "still offered at the next launch."
        ),
        tier=2,
        help_id="settings.recovery_copies",
        topic="settings",
        help_anchor="settings",
    ),
    "recovery_delay": HelpTooltip(
        text=(
            "How long after the last change a recovery copy is written: 1 to 600 "
            "seconds, default 5. Every change restarts the wait, so a burst of edits "
            "is one write. A longer wait writes less often and can lose more work."
        ),
        tier=2,
        help_id="settings.recovery_delay",
        topic="settings",
        help_anchor="settings",
    ),
    "revisions": HelpTooltip(
        text=(
            "How many versions of each molecule keep their results in memory: 1 to 64, "
            "default 8, counted separately for the 2D drawing and for its 3D "
            "conformers. Undoing back to a version still kept shows its results "
            "without recomputing.\n\n"
            "Lowering it removes the older results at once, after asking. The "
            "molecules and undo are not affected, and a saved project holds only each "
            "molecule's current results whatever this is set to."
        ),
        tier=2,
        help_id="settings.revisions_kept",
        topic="settings",
        help_anchor="settings",
    ),
    "recalc_mode": HelpTooltip(
        text=(
            "When results are recomputed after you draw.\n\n"
            "After I pause (the default): once no edit has arrived for the delay below. "
            "While I draw: as soon as the application is free, at most once per "
            "moment. Only when I ask: never by itself -- results read Stale until you "
            "use Tools > Recalculate Now (F5).\n\n"
            "Results are marked Stale the instant you edit in every mode; this only "
            "decides when they are refreshed. Undo, redo and importing always "
            "recompute at once."
        ),
        tier=2,
        help_id="settings.recalc_mode",
        topic="settings",
        help_anchor="settings",
    ),
    "recalc_delay": HelpTooltip(
        text=(
            "How long a pause counts as stopping: 0 to 5000 milliseconds, default 800. "
            "Every edit restarts the wait, so a burst of edits is one recomputation. "
            "Used only by After I pause."
        ),
        tier=2,
        help_id="settings.recalc_delay",
        topic="settings",
        help_anchor="settings",
    ),
    "forget_directory": HelpTooltip(
        text=(
            "Forgets the folder these file dialogs last opened in, so the next one "
            "starts in Documents again. Nothing on disk is touched."
        ),
        tier=1,
        help_id="settings.forget_directory",
        topic="settings",
        help_anchor="settings",
    ),
}


def _note(text: str, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    # The External Tools tabs' own note colour, so the sections match.
    label.setStyleSheet("color: #666666;")
    return label


def _heading(text: str, parent: QWidget) -> QLabel:
    return QLabel(f"<b>{text}</b>", parent)


class SettingsDialog(QDialog):
    """Every preference in one window. See the module docstring."""

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        *,
        section: str = PANELS,
        tool: str = "vina",
        result_store_service=None,
        calculator_definitions=None,
        shortcut_registry=None,
    ) -> None:
        """`section` is the section to open at, and `tool` is the External
        Tools tab in front there.

        `result_store_service` is optional. With it, lowering the revisions
        kept says exactly what would go, and asks nothing when nothing
        would. The panels' Configure buttons open this window without it,
        so there the question is asked every time, in general terms.

        `calculator_definitions` is every registered calculator, for the
        Calculators page; only those with a declared support level are
        listed, and none given means an empty list rather than a guess.

        `shortcut_registry` is the main window's, which holds every menu command
        and its shortcut; without one the Keyboard page says there is nothing to
        show rather than listing commands this window cannot change.
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(780, 520)
        self._settings = settings
        self._result_store_service = result_store_service
        self._calculator_definitions = list(calculator_definitions or [])
        self._shortcut_registry = shortcut_registry
        self._section_ids: list[str] = []
        # See `_commit_revisions`: its own question moves the focus, which
        # finishes the edit a second time.
        self._committing_revisions = False

        self._sections = QListWidget(self)
        self._sections.setObjectName("settingsSections")
        self._pages = QStackedWidget(self)

        builders = {
            PANELS: self._build_panels_page,
            RECOVERY: self._build_recovery_page,
            RECALCULATION: self._build_recalculation_page,
            RESULTS: self._build_results_page,
            CALCULATORS: self._build_calculators_page,
            KEYBOARD: self._build_keyboard_page,
            FILE_DIALOGS: self._build_file_dialogs_page,
        }
        for section_id, label in SECTIONS:
            if section_id == EXTERNAL_TOOLS:
                #: The seven tabs, moved in whole. Public so a caller or a
                #: test can ask which tool is in front.
                self.external_tools = ExternalToolsPages(settings, self, focus=tool)
                page = self.external_tools
            else:
                page = builders[section_id]()
            self._section_ids.append(section_id)
            self._sections.addItem(label)
            self._pages.addWidget(page)
        self._sections.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._sections.setFixedWidth(self._sections.sizeHintForColumn(0) + 32)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        # NO BUTTON IS THE DEFAULT. A dialog shown without one makes the first
        # auto-default push button in its focus chain the default, and Enter
        # that the focused control passes on presses it. Measured 2026-09-14,
        # after the magnified shot drew the first Forget button as the
        # default: choosing File dialogs in the list and pressing Enter forgot
        # the projects folder. Everything here applies as it changes, so Enter
        # has nothing to confirm.
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

        body = QHBoxLayout()
        body.addWidget(self._sections)
        body.addWidget(self._pages, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

        self.show_section(section)

    # --- navigation ----------------------------------------------------------

    def show_section(self, section: str) -> None:
        """Bring one section to the front, by id.

        An unknown id RAISES. Every caller names its section in code, so a
        typo is a bug to see, not a window that quietly opens on the wrong
        page -- the same fail-closed rule as `DIRECTORY_KINDS`.
        """
        if section not in self._section_ids:
            raise ValueError(
                f"unknown settings section {section!r}; expected one of {self._section_ids}"
            )
        self._sections.setCurrentRow(self._section_ids.index(section))

    def current_section(self) -> str:
        return self._section_ids[self._sections.currentRow()]

    def done(self, result: int) -> None:
        """Close, committing a revisions value that was never committed.

        A number typed into the box, with Escape pressed before the focus
        left it, has not been through `_commit_revisions` yet. Without this,
        closing would drop it silently.
        """
        self._commit_revisions()
        super().done(result)

    # --- Panels ----------------------------------------------------------------

    def _build_panels_page(self) -> QWidget:
        page = QWidget(self)
        self._rail_hides_panels = QCheckBox(
            "Choosing a panel hides the other panels in its area", page
        )
        self._rail_hides_panels.setObjectName("railHidesPanels")
        self._rail_hides_panels.setChecked(bool(self._settings.preference(RAIL_HIDES_PANELS)))
        apply_help_tooltip(self._rail_hides_panels, _HELP["rail"])
        self._rail_hides_panels.toggled.connect(self._on_rail_hides_panels_toggled)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Panels", page))
        layout.addWidget(self._rail_hides_panels)
        layout.addWidget(_note(
            "A panel you have dragged somewhere else, or floated, is never hidden. "
            "With this off, close a panel from its own title bar.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_rail_hides_panels_toggled(self, checked: bool) -> None:
        self._store(RAIL_HIDES_PANELS, checked)

    # --- Recovery ----------------------------------------------------------------

    def _build_recovery_page(self) -> QWidget:
        page = QWidget(self)
        enabled = bool(self._settings.preference(RECOVERY_ENABLED))
        self._recovery_enabled = QCheckBox("Keep recovery copies of unsaved work", page)
        self._recovery_enabled.setObjectName("recoveryEnabled")
        self._recovery_enabled.setChecked(enabled)
        apply_help_tooltip(self._recovery_enabled, _HELP["recovery"])
        self._recovery_enabled.toggled.connect(self._on_recovery_enabled_toggled)

        self._recovery_delay = _spin_box(RECOVERY_DELAY_SECONDS, " s", page)
        self._recovery_delay.setObjectName("recoveryDelaySeconds")
        self._recovery_delay.setValue(int(self._settings.preference(RECOVERY_DELAY_SECONDS)))
        self._recovery_delay.setEnabled(enabled)
        apply_help_tooltip(self._recovery_delay, _HELP["recovery_delay"])
        self._recovery_delay.valueChanged.connect(self._on_recovery_delay_changed)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("Write a copy", page))
        delay_row.addWidget(self._recovery_delay)
        delay_row.addWidget(QLabel("after the last change", page))
        delay_row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Recovery", page))
        layout.addWidget(self._recovery_enabled)
        layout.addLayout(delay_row)
        layout.addWidget(_note(
            "Copies are kept in the recovery folder under the data folder, and saving "
            "removes them. A copy already written is still offered at the next launch "
            "if you turn this off.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_recovery_enabled_toggled(self, checked: bool) -> None:
        self._recovery_delay.setEnabled(checked)
        self._store(RECOVERY_ENABLED, checked)

    def _on_recovery_delay_changed(self, seconds: int) -> None:
        self._store(RECOVERY_DELAY_SECONDS, seconds)

    # --- Recalculation -----------------------------------------------------------

    #: The mode combo's entries, in the order shown: the stored integer and its words.
    _RECALC_CHOICES = (
        (RecalcMode.WHILE_DRAWING, "While I draw"),
        (RecalcMode.AFTER_PAUSE, "After I pause"),
        (RecalcMode.ON_REQUEST, "Only when I ask"),
    )

    def _build_recalculation_page(self) -> QWidget:
        page = QWidget(self)
        self._recalc_mode = QComboBox(page)
        self._recalc_mode.setObjectName("recalcMode")
        for mode, words in self._RECALC_CHOICES:
            # The integer is what is stored; the words are what is read.
            self._recalc_mode.addItem(words, int(mode))
        current = int(self._settings.preference(RECALC_MODE))
        self._recalc_mode.setCurrentIndex(max(0, self._recalc_mode.findData(current)))
        apply_help_tooltip(self._recalc_mode, _HELP["recalc_mode"])

        self._recalc_delay = _spin_box(RECALC_QUIET_MS, " ms", page)
        self._recalc_delay.setObjectName("recalcQuietMs")
        self._recalc_delay.setSingleStep(100)
        self._recalc_delay.setValue(int(self._settings.preference(RECALC_QUIET_MS)))
        self._recalc_delay.setEnabled(current == int(RecalcMode.AFTER_PAUSE))
        apply_help_tooltip(self._recalc_delay, _HELP["recalc_delay"])
        self._recalc_mode.currentIndexChanged.connect(self._on_recalc_mode_changed)
        self._recalc_delay.valueChanged.connect(self._on_recalc_delay_changed)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Recalculate results", page))
        mode_row.addWidget(self._recalc_mode)
        mode_row.addStretch(1)
        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("A pause is", page))
        delay_row.addWidget(self._recalc_delay)
        delay_row.addWidget(QLabel("with no edit", page))
        delay_row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Recalculation", page))
        layout.addLayout(mode_row)
        layout.addLayout(delay_row)
        layout.addWidget(_note(
            "Results are marked Stale the moment you edit, whichever you choose; this decides "
            "when they are refreshed. Recomputing fifty results for every bond you draw made "
            "drawing lag. Undo, redo and importing always recompute at once, and Tools > "
            "Recalculate Now (F5) does it whenever you ask.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_recalc_mode_changed(self, _index: int) -> None:
        mode = int(self._recalc_mode.currentData())
        self._recalc_delay.setEnabled(mode == int(RecalcMode.AFTER_PAUSE))
        self._store(RECALC_MODE, mode)

    def _on_recalc_delay_changed(self, milliseconds: int) -> None:
        self._store(RECALC_QUIET_MS, milliseconds)

    # --- Calculators ---------------------------------------------------------------

    def _build_calculators_page(self) -> QWidget:
        #: Public so a caller or a test can ask what the page offers.
        self.calculators_page = CalculatorVisibilityPage(
            self._settings, self._calculator_definitions, self
        )
        return self.calculators_page

    # --- Keyboard ------------------------------------------------------------------

    def _build_keyboard_page(self) -> QWidget:
        #: Public so a caller or a test can drive a rebinding.
        self.keyboard_page = KeyboardShortcutsPage(self._shortcut_registry, self)
        return self.keyboard_page

    # --- Results -----------------------------------------------------------------

    def _build_results_page(self) -> QWidget:
        page = QWidget(self)
        self._max_revisions = _spin_box(MAX_REVISIONS_KEPT, "", page)
        self._max_revisions.setObjectName("maxRevisionsKept")
        self._max_revisions.setValue(int(self._settings.preference(MAX_REVISIONS_KEPT)))
        apply_help_tooltip(self._max_revisions, _HELP["revisions"])
        # ON COMMIT, NEVER PER STEP. Lowering this drops results at once and
        # asks first, so eight arrow clicks down from 8 must be one question,
        # not seven. `editingFinished` is Enter or the focus leaving the box.
        # Keyboard tracking is off so typing "16" is not also a stop at 1.
        # `done` commits whatever is still pending when the window closes.
        self._max_revisions.setKeyboardTracking(False)
        self._max_revisions.editingFinished.connect(self._commit_revisions)

        row = QHBoxLayout()
        row.addWidget(QLabel("Keep results for the last", page))
        row.addWidget(self._max_revisions)
        row.addWidget(QLabel("versions of each molecule", page))
        row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Results", page))
        layout.addLayout(row)
        layout.addWidget(_note(
            "Counted separately for the 2D drawing and for its 3D conformers. Undoing "
            "back to a version still kept shows its results without recomputing. "
            "Lowering this removes older results at once, after asking.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _commit_revisions(self) -> None:
        """Store the revisions limit, asking first when it goes down.

        **NOT RE-ENTERED.** Enter finishes the edit, and the question that
        follows takes the focus out of the box, which Qt reports as the edit
        finishing AGAIN -- while the first question is still open. Without
        the guard that is a second question stacked on the first.
        """
        if self._committing_revisions:
            return
        self._committing_revisions = True
        try:
            limit = self._max_revisions.value()
            current = int(self._settings.preference(MAX_REVISIONS_KEPT))
            if limit == current:
                return
            if limit < current and not self._confirm_fewer_revisions(limit):
                self._max_revisions.blockSignals(True)
                self._max_revisions.setValue(current)
                self._max_revisions.blockSignals(False)
                return
            self._store(MAX_REVISIONS_KEPT, limit)
        finally:
            self._committing_revisions = False

    def _confirm_fewer_revisions(self, limit: int) -> bool:
        """Say what lowering the limit removes, and ask.

        Counted from the store BEFORE anything changes, because storing the
        setting is what trims. With nothing to remove, nothing is asked.
        """
        kept = f"Keep {limit} version{'' if limit == 1 else 's'}"
        service = self._result_store_service
        if service is not None:
            result_sets, molecules = service.store.revisions_beyond(limit)
            if not result_sets:
                return True
            removed = (
                f"{result_sets} older result set{'' if result_sets == 1 else 's'} for "
                f"{molecules} molecule{'' if molecules == 1 else 's'} will be removed "
                "from memory."
            )
        else:
            removed = "results held for older versions will be removed from memory."
        answer = QMessageBox.question(
            self,
            "Keep fewer versions",
            f"{kept} -- {removed}\n\n"
            "The molecules and undo are not affected. Undoing back to a removed version "
            "computes its automatic results again; a calculation you ran by hand would "
            "need running again.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    # --- File dialogs --------------------------------------------------------------

    def _build_file_dialogs_page(self) -> QWidget:
        page = QWidget(self)
        grid = QGridLayout()
        #: kind -> (where it opens, its Forget button)
        self._directory_rows: dict[str, tuple[QLabel, QPushButton]] = {}
        for row, kind in enumerate(DIRECTORY_LABELS):
            where = QLabel(page)
            where.setWordWrap(True)
            forget = QPushButton("Forget", page)
            forget.setObjectName(f"forget_{kind}_directory")
            forget.setProperty(_DIRECTORY_KIND_PROPERTY, kind)
            apply_help_tooltip(forget, _HELP["forget_directory"])
            forget.clicked.connect(self._on_forget_directory_clicked)
            grid.addWidget(QLabel(DIRECTORY_LABELS[kind], page), row * 2, 0, 1, 2)
            grid.addWidget(where, row * 2 + 1, 0)
            grid.addWidget(forget, row * 2 + 1, 1)
            self._directory_rows[kind] = (where, forget)
            self._refresh_directory(kind)
        grid.setColumnStretch(0, 1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("File dialogs", page))
        layout.addWidget(_note(
            "Each kind of file dialog opens where it was last used. A folder that no "
            "longer exists is ignored, and the dialog opens in Documents.",
            page,
        ))
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _refresh_directory(self, kind: str) -> None:
        where, forget = self._directory_rows[kind]
        remembered = self._settings.last_directory(kind)
        where.setText(remembered or "Nothing remembered; opens in Documents")
        forget.setEnabled(bool(remembered))

    def _on_forget_directory_clicked(self, _checked: bool = False) -> None:
        button = self.sender()
        if button is None:
            return
        kind = button.property(_DIRECTORY_KIND_PROPERTY)
        self._settings.forget_last_directory(kind)
        self._refresh_directory(kind)

    # --- shared ----------------------------------------------------------------------

    def _store(self, preference: Preference, value: bool | int) -> None:
        self._settings.set_preference(preference, value)


def _spin_box(preference: Preference, suffix: str, parent: QWidget) -> QSpinBox:
    """A spin box bounded by the preference's own range, never a second copy."""
    box = QSpinBox(parent)
    box.setRange(int(preference.minimum), int(preference.maximum))
    box.setSuffix(suffix)
    return box
