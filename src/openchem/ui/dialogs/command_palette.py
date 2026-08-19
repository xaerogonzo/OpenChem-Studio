"""Type what you want instead of remembering where it lives.

**IT INTRODUCES NO COMMAND REGISTRY, and that is the whole design.** Three
indexes already exist and already know their own names:

    panels          the rail's own list
    calculators     `CalculatorRegistry`, with display names and categories
    menu actions    walked off the live `QMenuBar`

A palette that required each feature to register itself would be a fourth
list to keep in step with the other three, and the thing that falls out of
step is always the one nobody remembers to update. Reading what the app
already knows about itself means a new calculator or a new menu item is in
the palette the moment it exists, with no extra step and no way to forget.

It also pays off the one real cost of grouping panels behind a rail: you
never have to remember which group something is filed under.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip


@dataclass(frozen=True)
class Command:
    """One thing the palette can do.

    `run` is a plain callable rather than a QAction, because the three
    sources are genuinely different objects and forcing them into one Qt
    type would mean wrapping two of them for no gain.
    """

    label: str
    #: Where it came from -- "Panel", "Calculator", "File", "Edit"...
    #: Shown beside the label, because "Geometry" alone is ambiguous
    #: between a panel, a calculator and a menu item.
    source: str
    run: Callable[[], None]
    #: Other words that should find this, none of them shown.
    #:
    #: **THE PALETTE USED TO SEARCH DISPLAY NAMES ONLY**, which made it
    #: useless for the vocabulary people actually arrive with. Measured
    #: against the real ranker before this existed:
    #:
    #:     cif        -> "Scientific Limitations", "Open Plugins Folder"
    #:     toxicity   -> "Toggle Explicit Hydrogens"
    #:     pdb        -> "Periodic Table..."
    #:     sdf, xyz, mmcif, protein, lattice, spectrum, energy -> NOTHING
    #:
    #: The first three are the subsequence tier answering with confident
    #: noise, which is worse than an empty list: it looks like the app
    #: considered the question. Keywords are what let a real match outrank
    #: that, and 45 of the 58 calculators already carry `tags` that were
    #: being ignored entirely.
    keywords: tuple[str, ...] = ()


def score(query: str, text: str) -> int:
    """How well `text` matches `query`. Higher is better; 0 is no match.

    A pure function, so the ranking is testable without constructing a
    dialog -- which matters more than usual here, because ranking is the
    only part of a palette that can be subtly wrong rather than broken.

    Four tiers, in the order people expect:

        exact                       "batch" -> "Batch"
        prefix                      "prop"  -> "Properties"
        word start                  "str"   -> "Structure Check"
        subsequence                 "sck"   -> "Structure Check"

    Subsequence last and lowest because it matches almost everything: it
    is what makes "qc" find "Quantum Chemistry", and also what would drown
    the list if it outranked a real prefix.
    """
    needle, hay = query.strip().lower(), text.lower()
    if not needle:
        return 1
    if needle == hay:
        return 1000
    if hay.startswith(needle):
        return 500 - len(hay)
    if any(word.startswith(needle) for word in hay.split()):
        return 300 - len(hay)
    # Subsequence: every character of the query in order, not adjacent.
    position = 0
    for character in needle:
        position = hay.find(character, position)
        if position < 0:
            return 0
        position += 1
    return 100 - len(hay)


#: A keyword match scores below every LABEL tier, so a command named for
#: what you typed always wins. "Batch" the panel must beat a calculator
#: that merely lists "batch" among its tags, whatever the tiers would say
#: about the two strings on their own.
#:
#: Above the label's SUBSEQUENCE tier (100 - len) on purpose, though: a
#: real keyword hit is a better answer than "toxicity" reaching "Toggle
#: Explicit Hydrogens" one letter at a time.
_KEYWORD_CEILING = 250


def _command_score(query: str, command: Command) -> int:
    """The best of the label and the keywords, keywords capped."""
    best = score(query, command.label)
    for keyword in command.keywords:
        matched = score(query, keyword)
        if matched > 0:
            best = max(best, min(matched, _KEYWORD_CEILING))
    return best


def rank(query: str, commands: list[Command]) -> list[Command]:
    """The matching commands, best first.

    Ties break on the ORIGINAL order rather than alphabetically, so the
    caller's ordering -- panels before calculators before menu items --
    survives into the list. Python's sort is stable, which is what makes
    that free.
    """
    scored = [(_command_score(query, c), c) for c in commands]
    matching = [(s, c) for s, c in scored if s > 0]
    matching.sort(key=lambda pair: -pair[0])
    return [c for _s, c in matching]


#: ONE control, and it is the whole dialog: the list below it is a result,
#: not something to operate.
#:
#: SEPARATE FROM `tools.command_palette`, which is the menu entry that
#: OPENS this window. "How do I get here" and "what does typing here do"
#: are two concepts, and one id may only mean one thing.
#:
#: The ranking is the part worth writing down, because it is the only
#: place a palette can be subtly wrong rather than broken -- a reader who
#: does not know the loose tier exists reads a poor last-place match as
#: the application misunderstanding the question.
_HELP: dict[str, HelpTooltip] = {
    "query": HelpTooltip(
        text=(
            "Searches panels, calculators and menu commands at once, best "
            "match first.\n\n"
            "Four tiers, in this order: the exact name, a name starting "
            "with what you typed, a word inside the name starting with it, "
            "and finally the letters in order but not adjacent -- which is "
            "what makes 'qc' find Quantum Chemistry, and what puts a weak "
            "match at the bottom rather than leaving it out. A calculator's "
            "own keywords are searched too; they outrank that loose tier "
            "and lose to a command genuinely named for what you typed.\n\n"
            "Up and Down move the selection without leaving the box, and "
            "Enter runs it."
        ),
        tier=1,
        help_id="command_palette.query",
        topic="navigation",
    ),
}


class CommandPalette(QDialog):
    """A search box over everything the app can already do."""

    def __init__(self, commands: list[Command], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Commands")
        self.resize(520, 420)
        self._commands = commands
        self._chosen: Command | None = None

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Type a panel, calculator or menu command...")
        self._search.textChanged.connect(self._render)
        # Enter runs the highlighted row without needing the mouse, which
        # is the only reason to use a palette rather than the menus.
        self._search.returnPressed.connect(self._run_current)
        apply_help_tooltip(self._search, _HELP["query"])

        self._list = QListWidget(self)
        self._list.itemActivated.connect(self._on_item_activated)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)

        self._render()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        """Up/Down move the selection while the cursor stays in the box.

        Without this, choosing the second result means leaving the search
        field, which defeats the point -- you type, you arrow, you press
        Enter, and your hands never move.
        """
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            row = self._list.currentRow()
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            self._list.setCurrentRow(max(0, min(self._list.count() - 1, row + step)))
            return
        super().keyPressEvent(event)

    def visible_labels(self) -> list[str]:
        """What the list is showing, read off the rows.

        Derived rather than recomputed, so a test cannot pass against a
        ranking that never reached the display.
        """
        return [self._list.item(row).text() for row in range(self._list.count())]

    def chosen(self) -> Command | None:
        return self._chosen

    def _render(self) -> None:
        self._list.clear()
        for command in rank(self._search.text(), self._commands):
            item = QListWidgetItem(f"{command.label}    ({command.source})", self._list)
            item.setData(Qt.ItemDataRole.UserRole, command)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _run_current(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self._on_item_activated(item)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        command = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(command, Command):
            return
        self._chosen = command
        # Closed BEFORE running, so a command that opens a dialog does not
        # open it behind this one.
        self.accept()
        command.run()
