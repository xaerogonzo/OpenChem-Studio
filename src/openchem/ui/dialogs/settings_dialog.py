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

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from openchem.app.settings import (
    APPEARANCE,
    CONFORMER_EARLY_STOP,
    CONFORMER_KEEP_OPTIMIZED,
    CONFORMER_OPTIMIZE_LOWEST,
    CONFORMER_MAX_EMBEDDINGS,
    DRAWING_BOND_CLICK,
    DRAWING_BOND_KEYS,
    FUKUI_ANION_F_PLUS,
    FUKUI_CATION_SEARCH,
    MAX_REVISIONS_KEPT,
    PSI4_MEMORY_GB,
    PSI4_THREADS,
    RAIL_HIDES_PANELS,
    RECALC_MODE,
    RECALC_QUIET_MS,
    RECOVERY_DELAY_SECONDS,
    RECOVERY_ENABLED,
    STRUCTURE_COVERAGE,
    Preference,
    Settings,
)
from openchem.domain.appearance import Appearance, appearance_from_stored
from openchem.domain.recalc_policy import RecalcMode
from openchem.events.events import SettingsChanged
from openchem.ui import theme
from openchem.ui.dialogs.calculator_visibility_page import CalculatorVisibilityPage
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages
from openchem.ui.dialogs.keyboard_shortcuts_page import KeyboardShortcutsPage
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip

#: Section id of the colour scheme: light, dark, or follow the system.
APPEARANCE_SECTION = "appearance"

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

#: Section id of how drawing behaves.
DRAWING = "drawing"

#: Section id of the 3D conformer search.
CONFORMERS = "conformers"

#: Section id of the quantum chemistry calculations' own choices (today: whether an anion's Fukui functions include its f+).
QUANTUM_CHEMISTRY = "quantum_chemistry"

#: Section id of the remembered file-dialog folders.
FILE_DIALOGS = "file_dialogs"

#: Section id of the External Tools tabs, Storage included.
EXTERNAL_TOOLS = "external_tools"

#: Every section, in the order the list shows them, with its label.
#:
#: Two runs, each A-Z: how the WINDOW looks and behaves (Appearance first, a test holds it there), then
#: how CALCULATIONS run. It used to be the order the pages were written in, which put Keyboard between
#: Calculators and Drawing.
SECTIONS = (
    (APPEARANCE_SECTION, "Appearance"),
    (DRAWING, "Drawing"),
    (FILE_DIALOGS, "File dialogs"),
    (KEYBOARD, "Keyboard"),
    (PANELS, "Panels"),
    (RECOVERY, "Recovery"),
    (CALCULATORS, "Calculators"),
    (CONFORMERS, "Conformers"),
    (EXTERNAL_TOOLS, "External tools"),
    (QUANTUM_CHEMISTRY, "Quantum chemistry"),
    (RECALCULATION, "Recalculation"),
    (RESULTS, "Results"),
)

#: How the list is PRESENTED: a heading over each run of sections. `SECTIONS` stays the one list of pages and
#: ids; this only says which heading each id sits under, and `tests/test_settings_section_headings.py` holds
#: the two together (every id once, none invented, none left out).
SECTION_GROUPS = (
    ("Window", (APPEARANCE_SECTION, DRAWING, FILE_DIALOGS, KEYBOARD, PANELS, RECOVERY)),
    ("Calculations", (CALCULATORS, CONFORMERS, EXTERNAL_TOOLS, QUANTUM_CHEMISTRY, RECALCULATION, RESULTS)),
)

class _SectionList(QListWidget):
    """The section list, with Home going to the first SECTION: row 0 is a heading, which cannot be current."""

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() == Qt.Key.Key_Home and not event.modifiers():
            for row in range(self.count()):
                if self.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                    self.setCurrentRow(row)
                    return
        super().keyPressEvent(event)


#: The item data that makes a list row a SECTION. A heading carries none, and nothing resolves a page from a
#: row number: with headings in the list the row of a section is no longer its place in `SECTIONS`.
SECTION_ID_ROLE = Qt.ItemDataRole.UserRole

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
    "appearance": HelpTooltip(
        text=(
            "The colour scheme of the window.\n\n"
            "Follow the system (the default): light or dark as Windows is, and it changes when "
            "Windows does. Light and Dark keep that scheme whatever Windows is set to.\n\n"
            "The same choice is in the View menu, under Theme. It changes how the window looks "
            "and nothing about your structures or results. In dark, the 2D editor's drawing area "
            "is dark with white bonds; atom colours and selection feedback are never altered."
        ),
        tier=2,
        help_id="settings.appearance",
        topic="settings",
        help_anchor="settings",
    ),
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
    "structure_coverage": HelpTooltip(
        text=(
            "On (the default): before you run anything, each calculator in Properties says whether the structure "
            "on screen is one it takes -- Can run, With limits (it runs, and the tooltip says what the limit is), "
            "or Not applicable (it will refuse, and the tooltip says why). Rows that open another panel show a "
            "check, a triangle or a circle before their name. Rows with no check say nothing.\n\n"
            "The check is the calculator's own refusal test, run once each time the structure settles (never while "
            "you drag), about 5 ms for all calculators together. Off: nothing is checked and every row says Not run "
            "until you run it."
        ),
        tier=2,
        help_id="settings.structure_coverage",
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
    "bond_keys": HelpTooltip(
        text=(
            "On (the default): pointing at a bond in the drawing and pressing 1, 2 or 3 makes "
            "it single, double or triple. It is one undoable edit.\n\n"
            "A bond that is aromatic, a query bond, a wedge or hash bond, or one whose change "
            "would break a valence is left as it was, and the status bar says why. Pointing at "
            "an atom is not affected: those keys still start a bond from it.\n\n"
            "Off hands the keys back to the editor, which does nothing with them over a bond."
        ),
        tier=2,
        help_id="settings.bond_order_keys",
        topic="settings",
        help_anchor="settings",
    ),
    "conformer_embeddings": HelpTooltip(
        text=(
            "The most starting structures Generate Conformers > Automatic will try before it stops "
            "(10 to 5000, default 1000).\n\n"
            "The search tries them in batches of 50 and can stop sooner, but on a flexible molecule it "
            "usually does not: new shapes keep turning up. Measured on a flexible drug-like molecule, the "
            "conformers within 3 kcal/mol of the lowest that it found were 71% of the 1000-embedding "
            "set at 300, 93% at 500 and all of them at 750, and 1000 took about a minute and a half. "
            "A lower number is faster and finds fewer of the higher-energy shapes.\n\n"
            "Not used when Automatic is unticked in the dialog: the number typed there is."
        ),
        tier=2,
        help_id="settings.conformer_embeddings",
        topic="settings",
        help_anchor="settings",
    ),
    "conformer_early_stop": HelpTooltip(
        text=(
            "EXPERIMENTAL, off by default. Stop the conformer search when no new shape would rank among the "
            "lowest conformers this run keeps, instead of when no new shape of ANY energy turns up.\n\n"
            "The default rule rarely fires on a flexible molecule, because higher-energy shapes keep arriving "
            "that the run will never show. This one ignores them. Measured by replaying 1000-embedding "
            "searches of three flexible drug-like molecules on three seeds against the same search run to "
            "1000: it never stopped later than the default, used about a quarter fewer embeddings, and "
            "recovered about 18 of the 20 lowest shapes against about 19 for the default (worst run 16 of "
            "20, with the kept energies about 1 kcal/mol higher on average for that molecule). The single "
            "lowest-energy shape was the same in every run. Three molecules and three seeds is a small "
            "sample, which is why it is opt-in.\n\n"
            "A run ended this way says so in Details. Finish now, next to Generate Conformers, is the manual "
            "way to stop and keep what has been found."
        ),
        tier=2,
        help_id="settings.conformer_early_stop",
        topic="settings",
        help_anchor="settings",
    ),
    "conformer_keep_optimized": HelpTooltip(
        text=(
            "On (the default): generating conformers again keeps the geometries an ORCA optimization produced. "
            "The new conformers come first and the kept ORCA ones follow them, in the order they had, with "
            "their level of theory and origin intact.\n\n"
            "Off: generating replaces everything, ORCA geometries included, which is what it did before this "
            "choice existed. Undo restores the previous set either way.\n\n"
            "Why on: an ORCA geometry takes minutes to hours and is the one every later calculation uses, so "
            "losing it as a side effect of pressing Generate was the surprise.\n\n"
            "Editing the structure still clears every conformer, ORCA ones included: the geometry no longer "
            "fits the molecule."
        ),
        tier=2,
        help_id="settings.conformer_keep_optimized",
        topic="settings",
        help_anchor="settings",
    ),
    "conformer_optimize_lowest": HelpTooltip(
        text=(
            "Off (the default): Generate Conformers only generates.\n\n"
            "On: the Generate Conformers window starts with \"Also ORCA-optimize the lowest-energy conformer\" "
            "ticked. When the set is installed, ORCA optimizes the conformer with the lowest force-field energy "
            "in it, with the method, basis, charge and multiplicity the Quantum Chemistry panel shows at that "
            "moment, exactly as if you had pressed Run there. The result replaces that conformer in its slot.\n\n"
            "This is only where the window's checkbox starts: each generation can still tick or untick it. "
            "Nothing starts when ORCA is not set up, and the window says so.\n\n"
            "Why off: an optimization takes minutes to hours, and pressing Generate did not ask for one."
        ),
        tier=2,
        help_id="settings.conformer_optimize_lowest",
        topic="settings",
        help_anchor="settings",
    ),
    "fukui_anion_f_plus": HelpTooltip(
        text=(
            "On (the default): the Fukui functions of a species that is itself an anion include f+, f0 and the dual "
            "descriptor, from its dianion. No basis set binds a dianion, so these are the least trustworthy numbers the "
            "calculator gives, and the result says by how many eV the dianion lies above the anion.\n\n"
            "The dianion is run last, so f- (where an electron comes from, the function that describes an anion) is the "
            "same either way, and a dianion that does not converge costs only f+ and what is made from it: you get f- "
            "and a sentence saying why.\n\n"
            "Off: only the anion and its neutral radical are run, which is what the second preregistered check tested, "
            "and the result says the dianion was left out. Neutral molecules and cations are not affected.\n\n"
            "Applies to the next Fukui run; results already computed are not changed."
        ),
        tier=2,
        help_id="settings.fukui_anion_f_plus",
        topic="settings",
        help_anchor="settings",
    ),
    "fukui_cation_search": HelpTooltip(
        text=(
            "On (the default): a Fukui run also looks for other states of the cation. It starts three more cation jobs from the "
            "neutral's orbitals, with the electron taken from the HOMO-1, HOMO-2 and HOMO-3, and f- is read from the LOWEST state "
            "found (the average of the states if the lowest level is degenerate). When another state lies within 0.5 eV of it, the "
            "result says so and how far that state's f- is from the one used.\n\n"
            "Why: a cation can have several states a few tenths of an eV apart, and one cation job reaches only the one ORCA's SCF "
            "falls into. For benzaldehyde that was not a function of the structure: 6 of 14 runs of the same molecule reached one "
            "state and 8 the other, depending on a rotation, a displacement of 0.001 A or the embedding.\n\n"
            "Off: one cation job, as before, and the result says no search was run. A search that finds nothing else costs the three "
            "jobs (about 2.5 times the time of a run without it, measured) and changes no number. Species of any charge are searched; molecules with an element heavier than krypton are not.\n\n"
            "Applies to the next Fukui run; results already computed are not changed."
        ),
        tier=2,
        help_id="settings.fukui_cation_search",
        topic="settings",
        help_anchor="settings",
    ),
    "psi4_memory": HelpTooltip(
        text=(
            "How much memory a Psi4 job is told to use, in GB (the `memory` line of its input). The default, 2 GB, is what the engine always wrote; "
            "Psi4's own default of 500 MB is too small for a def2-TZVP job on a drug-sized molecule, and a failed allocation reads like a broken input.\n\n"
            "Raise it for a large molecule or basis; keep it below what the machine has free, because Psi4 takes it at once. It is one job's total, shared "
            "by the job's threads. ORCA's memory is a separate setting and is not changed by this one.\n\n"
            "Applies to the next Psi4 job."
        ),
        tier=2,
        help_id="settings.psi4_memory",
        topic="settings",
        help_anchor="settings",
    ),
    "psi4_threads": HelpTooltip(
        text=(
            "How many threads a Psi4 job runs on. Automatic (the default) uses the core count set for ORCA on the Quantum Chemistry panel when there "
            "is one, and otherwise the machine's automatic choice: what Psi4 used before it had a setting of its own.\n\n"
            "A number from 1 up is used as it stands, whatever ORCA's is. Asking for more threads than the machine has cores does not make a job faster.\n\n"
            "Applies to the next Psi4 job."
        ),
        tier=2,
        help_id="settings.psi4_threads",
        topic="settings",
        help_anchor="settings",
    ),
    "bond_click": HelpTooltip(
        text=(
            "Off (the default): a click on a bond selects it, as it always has.\n\n"
            "On: a click on a bond with the Select tool or ANY atom tool (C, N, O, ...) armed cycles its order, "
            "single, double, triple, single, so you can keep an element armed and fix bonds without going "
            "back to the toolbar. "
            "It is one undoable edit, made the way the number keys make it, and a bond that is aromatic, a "
            "query bond, a wedge or hash bond, or one whose change would break a valence is left as it was.\n\n"
            "The cost is that, in the Select tool, a click no longer selects a bond (a drag across it still "
            "does); an atom tool did nothing on a bond, so it loses nothing. With the bond tool (which already "
            "cycles by itself), the chain tool or the eraser a click means what it did."
        ),
        tier=2,
        help_id="settings.bond_click_cycle",
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
    theme.style(label, "color: #666666;")
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
        tool: str = "guide",
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

        self._sections = _SectionList(self)
        self._sections.setObjectName("settingsSections")
        self._pages = QStackedWidget(self)

        builders = {
            APPEARANCE_SECTION: self._build_appearance_page,
            PANELS: self._build_panels_page,
            RECOVERY: self._build_recovery_page,
            RECALCULATION: self._build_recalculation_page,
            RESULTS: self._build_results_page,
            CALCULATORS: self._build_calculators_page,
            KEYBOARD: self._build_keyboard_page,
            DRAWING: self._build_drawing_page,
            CONFORMERS: self._build_conformers_page,
            QUANTUM_CHEMISTRY: self._build_quantum_chemistry_page,
            FILE_DIALOGS: self._build_file_dialogs_page,
        }
        for section_id, _label in SECTIONS:
            if section_id == EXTERNAL_TOOLS:
                #: The seven tabs, moved in whole. Public so a caller or a
                #: test can ask which tool is in front.
                self.external_tools = ExternalToolsPages(settings, self, focus=tool)
                page = self.external_tools
            else:
                page = builders[section_id]()
            self._section_ids.append(section_id)
            self._pages.addWidget(page)
        self._fill_section_list()
        self._sections.currentItemChanged.connect(self._on_section_item_changed)
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

        # A change made elsewhere (the View menu) shows here too, without writing it back.
        settings.on_change(self._on_setting_changed)

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
        self._sections.setCurrentItem(self._item_of[section])

    def current_section(self) -> str:
        section = self._section_of(self._sections.currentItem())
        assert section is not None, "a heading can never be the current section"
        return section

    def _fill_section_list(self) -> None:
        """One non-selectable heading per group, then its sections; each section row remembers its id."""
        labels = dict(SECTIONS)
        self._item_of: dict[str, QListWidgetItem] = {}
        heading_font = self._sections.font()
        heading_font.setBold(True)
        for heading, ids in SECTION_GROUPS:
            header = QListWidgetItem(heading)
            header.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable, not enabled: the arrow keys step over it
            header.setFont(heading_font)
            self._sections.addItem(header)
            for section_id in ids:
                item = QListWidgetItem(labels[section_id])
                item.setData(SECTION_ID_ROLE, section_id)
                self._sections.addItem(item)
                self._item_of[section_id] = item

    @staticmethod
    def _section_of(item: QListWidgetItem | None) -> str | None:
        """The section id a row stands for, or None for a heading (or nothing): the one place a row becomes a page."""
        return None if item is None else item.data(SECTION_ID_ROLE)

    def _on_section_item_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        section = self._section_of(current)
        if section is None:
            # A heading was made current by code; the list stays on the section it was on.
            if self._section_of(previous) is not None:
                self._sections.setCurrentItem(previous)
            return
        self._pages.setCurrentIndex(self._section_ids.index(section))

    def done(self, result: int) -> None:
        """Close, committing a revisions value that was never committed.

        A number typed into the box, with Escape pressed before the focus
        left it, has not been through `_commit_revisions` yet. Without this,
        closing would drop it silently.
        """
        self._commit_revisions()
        super().done(result)

    # --- Appearance --------------------------------------------------------------

    #: The combo's entries, in the order shown: the stored integer and its words.
    _APPEARANCE_CHOICES = (
        (Appearance.SYSTEM, "Follow the system"),
        (Appearance.LIGHT, "Light"),
        (Appearance.DARK, "Dark"),
    )

    def _build_appearance_page(self) -> QWidget:
        page = QWidget(self)
        self._appearance = QComboBox(page)
        self._appearance.setObjectName("appearanceChoice")
        for mode, words in self._APPEARANCE_CHOICES:
            # The integer is what is stored and read back; the row number and the words are neither.
            self._appearance.addItem(words, int(mode))
        self._show_appearance()
        apply_help_tooltip(self._appearance, _HELP["appearance"])
        self._appearance.currentIndexChanged.connect(self._on_appearance_changed)

        row = QHBoxLayout()
        row.addWidget(QLabel("Colour scheme", page))
        row.addWidget(self._appearance)
        row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Appearance", page))
        layout.addLayout(row)
        layout.addWidget(_note(
            "Follow the system changes when Windows does. The same choice is in the View menu, "
            "under Theme. In dark, the 2D editor's drawing area is dark with white bonds; atom "
            "colours and selection feedback are never altered. The 2D editor's dialogs and the "
            "macromolecule viewer's side panels follow the look too; its 3D canvas does not.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _show_appearance(self) -> None:
        """Put the combo on the stored choice, without writing it back."""
        mode = appearance_from_stored(self._settings.preference(APPEARANCE))
        blocked = self._appearance.blockSignals(True)
        try:
            self._appearance.setCurrentIndex(max(0, self._appearance.findData(int(mode))))
        finally:
            self._appearance.blockSignals(blocked)

    def _on_appearance_changed(self, _index: int) -> None:
        self._store(APPEARANCE, int(self._appearance.currentData()))

    def _on_setting_changed(self, event: SettingsChanged) -> None:
        # The bus holds this window weakly but can outlive its widgets; a closed window has nothing to update.
        if event.key == APPEARANCE.key and shiboken6.isValid(self._appearance):
            self._show_appearance()

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

    def _on_structure_coverage_toggled(self, checked: bool) -> None:
        self._store(STRUCTURE_COVERAGE, checked)

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
        self._structure_coverage = QCheckBox("Say whether each calculator takes the structure, before I run it", page)
        self._structure_coverage.setObjectName("structureCoverage")
        self._structure_coverage.setChecked(bool(self._settings.preference(STRUCTURE_COVERAGE)))
        apply_help_tooltip(self._structure_coverage, _HELP["structure_coverage"])
        self._structure_coverage.toggled.connect(self._on_structure_coverage_toggled)
        layout.addWidget(_note(
            "Results are marked Stale the moment you edit, whichever you choose; this decides "
            "when they are refreshed. Recomputing fifty results for every bond you draw made "
            "drawing lag. Undo, redo and importing always recompute at once, and Tools > "
            "Recalculate Now (F5) does it whenever you ask.",
            page,
        ))
        layout.addSpacing(8)
        layout.addWidget(self._structure_coverage)
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
        self.keyboard_page = KeyboardShortcutsPage(self._shortcut_registry, self, settings=self._settings)
        return self.keyboard_page

    # --- Drawing -------------------------------------------------------------------

    def _build_drawing_page(self) -> QWidget:
        page = QWidget(self)
        self._bond_keys = QCheckBox("A number key over a bond sets its order (1, 2, 3)", page)
        self._bond_keys.setObjectName("drawingBondKeys")
        self._bond_keys.setChecked(bool(self._settings.preference(DRAWING_BOND_KEYS)))
        apply_help_tooltip(self._bond_keys, _HELP["bond_keys"])
        self._bond_keys.toggled.connect(self._on_bond_keys_toggled)

        self._bond_click = QCheckBox(
            "A click on a bond cycles its order (single, double, triple) with the Select tool or an atom tool", page
        )
        self._bond_click.setObjectName("drawingBondClick")
        self._bond_click.setChecked(bool(self._settings.preference(DRAWING_BOND_CLICK)))
        apply_help_tooltip(self._bond_click, _HELP["bond_click"])
        self._bond_click.toggled.connect(self._on_bond_click_toggled)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Drawing", page))
        layout.addWidget(self._bond_keys)
        layout.addWidget(self._bond_click)
        layout.addWidget(_note(
            "Point at a bond and press 1, 2 or 3 to make it single, double or triple; Ctrl+Z "
            "undoes it. Aromatic, query and wedge bonds are left as drawn.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_bond_keys_toggled(self, checked: bool) -> None:
        self._store(DRAWING_BOND_KEYS, checked)

    def _on_bond_click_toggled(self, checked: bool) -> None:
        self._store(DRAWING_BOND_CLICK, checked)

    # --- Conformers ----------------------------------------------------------------

    def _build_conformers_page(self) -> QWidget:
        page = QWidget(self)
        self._conformer_embeddings = _spin_box(CONFORMER_MAX_EMBEDDINGS, "", page)
        self._conformer_embeddings.setObjectName("conformerMaxEmbeddings")
        self._conformer_embeddings.setSingleStep(50)
        self._conformer_embeddings.setValue(int(self._settings.preference(CONFORMER_MAX_EMBEDDINGS)))
        apply_help_tooltip(self._conformer_embeddings, _HELP["conformer_embeddings"])
        self._conformer_embeddings.valueChanged.connect(self._on_conformer_embeddings_changed)

        self._conformer_early_stop = QCheckBox(
            "Stop early when the lowest conformers stop changing (experimental)", page
        )
        self._conformer_early_stop.setObjectName("conformerEarlyStop")
        self._conformer_early_stop.setChecked(bool(self._settings.preference(CONFORMER_EARLY_STOP)))
        apply_help_tooltip(self._conformer_early_stop, _HELP["conformer_early_stop"])
        self._conformer_early_stop.toggled.connect(self._on_conformer_early_stop_toggled)

        self._conformer_keep_optimized = QCheckBox(
            "Keep ORCA-optimized conformers when generating conformers again", page
        )
        self._conformer_keep_optimized.setObjectName("conformerKeepOptimized")
        self._conformer_keep_optimized.setChecked(bool(self._settings.preference(CONFORMER_KEEP_OPTIMIZED)))
        apply_help_tooltip(self._conformer_keep_optimized, _HELP["conformer_keep_optimized"])
        self._conformer_keep_optimized.toggled.connect(self._on_conformer_keep_optimized_toggled)

        self._conformer_optimize_lowest = QCheckBox(
            "Start the Generate Conformers window with \"Also ORCA-optimize the lowest-energy conformer\" ticked", page
        )
        self._conformer_optimize_lowest.setObjectName("conformerOptimizeLowest")
        self._conformer_optimize_lowest.setChecked(bool(self._settings.preference(CONFORMER_OPTIMIZE_LOWEST)))
        apply_help_tooltip(self._conformer_optimize_lowest, _HELP["conformer_optimize_lowest"])
        self._conformer_optimize_lowest.toggled.connect(self._on_conformer_optimize_lowest_toggled)

        row = QHBoxLayout()
        row.addWidget(QLabel("Automatic search tries up to", page))
        row.addWidget(self._conformer_embeddings)
        row.addWidget(QLabel("starting structures", page))
        row.addStretch(1)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Conformers", page))
        layout.addLayout(row)
        layout.addWidget(_note(
            "This is a ceiling, not a count: the search stops earlier when nothing new turns up, and "
            "what it hands back is the lowest-energy conformers, up to the number you ask to keep. "
            "Lower is faster and finds fewer of the higher-energy shapes.",
            page,
        ))
        layout.addWidget(self._conformer_early_stop)
        layout.addWidget(_note(
            "Experimental. Ends a search that keeps finding only higher-energy shapes than the ones it "
            "will hand back. Faster, at the cost of sometimes missing a shape a full search would find.",
            page,
        ))
        layout.addWidget(self._conformer_keep_optimized)
        layout.addWidget(_note(
            "An ORCA optimization is expensive and every later calculation prefers it, so generating again "
            "keeps it by default. Untick to have Generate replace everything.",
            page,
        ))
        layout.addWidget(self._conformer_optimize_lowest)
        layout.addWidget(_note(
            "Off by default, because an ORCA optimization takes minutes to hours. Each generation can still "
            "tick it in its own window; this is only where that checkbox starts.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_conformer_embeddings_changed(self, value: int) -> None:
        self._store(CONFORMER_MAX_EMBEDDINGS, value)

    def _on_conformer_early_stop_toggled(self, checked: bool) -> None:
        self._store(CONFORMER_EARLY_STOP, checked)

    def _on_conformer_keep_optimized_toggled(self, checked: bool) -> None:
        self._store(CONFORMER_KEEP_OPTIMIZED, checked)

    def _on_conformer_optimize_lowest_toggled(self, checked: bool) -> None:
        self._store(CONFORMER_OPTIMIZE_LOWEST, checked)

    # --- Quantum chemistry ---------------------------------------------------------

    def _build_quantum_chemistry_page(self) -> QWidget:
        page = QWidget(self)
        self._fukui_anion_f_plus = QCheckBox(
            "Include f+, f0 and the dual descriptor for an anion (from its dianion, which no basis set binds)", page
        )
        self._fukui_anion_f_plus.setObjectName("fukuiAnionFPlus")
        self._fukui_anion_f_plus.setChecked(bool(self._settings.preference(FUKUI_ANION_F_PLUS)))
        apply_help_tooltip(self._fukui_anion_f_plus, _HELP["fukui_anion_f_plus"])
        self._fukui_anion_f_plus.toggled.connect(self._on_fukui_anion_f_plus_toggled)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Quantum chemistry", page))
        layout.addWidget(_heading("Fukui functions", page))
        layout.addWidget(self._fukui_anion_f_plus)
        layout.addWidget(_note(
            "An anion's f+ describes a state no basis set binds, so it is the least trustworthy number the calculator gives, "
            "and the result says how far above the anion the dianion lies. f- does not depend on it: the dianion is run "
            "last, and if it does not converge you get f- and a sentence saying why. Untick to run only the anion and its "
            "neutral radical. Neutral molecules and cations always get all four. Applies to the next run.",
            page,
        ))

        self._fukui_cation_search = QCheckBox(
            "Look for other states of the cation (three more ORCA jobs) and read f- from the lowest", page
        )
        self._fukui_cation_search.setObjectName("fukuiCationSearch")
        self._fukui_cation_search.setChecked(bool(self._settings.preference(FUKUI_CATION_SEARCH)))
        apply_help_tooltip(self._fukui_cation_search, _HELP["fukui_cation_search"])
        self._fukui_cation_search.toggled.connect(self._on_fukui_cation_search_toggled)
        layout.addWidget(self._fukui_cation_search)
        layout.addWidget(_note(
            "f- is a difference between the neutral and its cation, and a cation can have several states a few tenths of an eV "
            "apart. With one cation job, f- was taken from whichever state ORCA's SCF happened to reach, which for benzaldehyde "
            "was not a function of the structure: 6 of 14 runs reached one state and 8 the other. The search also starts the "
            "cation from the neutral's orbitals with the electron taken from the HOMO-1, HOMO-2 and HOMO-3, reads f- from the "
            "lowest state it finds, and says when another lies within 0.5 eV and how far its f- is. It takes about 2.5 times as long as the one job, which is what unticking runs. "
            "Applies to the next run.",
            page,
        ))

        # Psi4, the second engine (`chem.psi4_engine`): its memory and threads. Spin boxes bounded by the preferences' own ranges, as the conformer one is.
        self._psi4_memory = _spin_box(PSI4_MEMORY_GB, " GB", page)
        self._psi4_memory.setObjectName("psi4MemoryGb")
        self._psi4_memory.setValue(int(self._settings.preference(PSI4_MEMORY_GB)))
        apply_help_tooltip(self._psi4_memory, _HELP["psi4_memory"])
        self._psi4_memory.valueChanged.connect(self._on_psi4_memory_changed)
        self._psi4_threads = _spin_box(PSI4_THREADS, "", page)
        self._psi4_threads.setObjectName("psi4Threads")
        self._psi4_threads.setSpecialValueText("Automatic")  # the minimum, 0
        self._psi4_threads.setValue(int(self._settings.preference(PSI4_THREADS)))
        apply_help_tooltip(self._psi4_threads, _HELP["psi4_threads"])
        self._psi4_threads.valueChanged.connect(self._on_psi4_threads_changed)
        layout.addWidget(_heading("Psi4", page))
        for caption, box in (("Memory per job", self._psi4_memory), ("Threads", self._psi4_threads)):
            row = QHBoxLayout()
            row.addWidget(QLabel(caption, page))
            row.addWidget(box)
            row.addStretch(1)
            layout.addLayout(row)
        layout.addWidget(_note(
            "These apply to Psi4 jobs only (ORCA keeps its own core count on the Quantum Chemistry panel). Memory is the one total the job asks for, "
            "2 GB unless changed; Automatic threads follow ORCA's core count when it is set, otherwise the machine's. Applies to the next Psi4 job.",
            page,
        ))
        layout.addStretch(1)
        return page

    def _on_psi4_memory_changed(self, value: int) -> None:
        self._store(PSI4_MEMORY_GB, value)

    def _on_psi4_threads_changed(self, value: int) -> None:
        self._store(PSI4_THREADS, value)

    def _on_fukui_anion_f_plus_toggled(self, checked: bool) -> None:
        self._store(FUKUI_ANION_F_PLUS, checked)

    def _on_fukui_cation_search_toggled(self, checked: bool) -> None:
        self._store(FUKUI_CATION_SEARCH, checked)

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
