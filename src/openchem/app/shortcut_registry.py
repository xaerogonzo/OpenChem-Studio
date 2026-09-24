"""Which key runs which menu command, and letting a person change it.

**EVERY MENU ACTION ALREADY CARRIES A STABLE NAME**: the key it is documented under (`MENU_HELP`),
which the help contracts and the command palette read. Shortcuts were set in code at each site
(`setShortcut("F7")` and nine like it) and could not be changed, so this keeps the name, the shortcut
the code gave (its DEFAULT) and the person's override, and applies the override to the real `QAction`.

**A NAME SHARED BY SEVERAL ACTIONS IS NOT AN ID.** Every panel's View entry is documented under
`panel_visibility`, so that key alone would bind one shortcut to twelve commands. `apply` gives a
unique key its own name and a shared one `key:label`, decided over ALL of them once the menus are
built -- never by arrival order, because a dock that moves in the menu must not inherit another's
stored shortcut.

What it does not touch, deliberately: the **canvas**. Ketcher owns the keys typed while it has focus
(element letters, digits for bond orders, Delete), and a window shortcut bound to a bare letter would
compete with them. So a shortcut must carry Ctrl, Alt or Meta, or be a function key (`refusal_for`
says so) rather than promising a remap of the canvas that the drawing spike found no safe way to keep
(`docs/KETCHER_SPIKE.md`).

Stored under `shortcuts/<id>` as portable text. An ABSENT key follows the default; an EMPTY string is a
deliberate "no shortcut", which is a different thing and has to survive a restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from openchem.app.settings import Settings

logger = logging.getLogger("openchem.app")

#: Where one command's shortcut is stored, under its id.
SHORTCUT_KEY_PREFIX = "shortcuts/"

#: The modifiers that make a sequence safe to bind at the window level: none of them types a
#: character, so none competes with the canvas's own keys.
_SAFE_MODIFIERS = (
    Qt.KeyboardModifier.ControlModifier,
    Qt.KeyboardModifier.AltModifier,
    Qt.KeyboardModifier.MetaModifier,
)

#: The text form a shortcut is stored and shown in ("Ctrl+Shift+P"), the same on every platform and
#: locale; the native form ("Ctrl+Shift+P" here, a symbol string on macOS) is display only.
PORTABLE = QKeySequence.SequenceFormat.PortableText


@dataclass(frozen=True)
class ShortcutEntry:
    """One command as the Keyboard page shows it."""

    command_id: str
    #: What the menu calls it, without its mnemonic ampersand or trailing ellipsis.
    label: str
    #: The shortcut the code gave the command ("" for none).
    default: str
    #: The shortcut in force now ("" for none).
    current: str

    @property
    def is_default(self) -> bool:
        return self.current == self.default


def portable(sequence: QKeySequence | str) -> str:
    """A sequence as portable text ("Ctrl+Shift+P"), or "" for none or unparseable."""
    if isinstance(sequence, str):
        sequence = QKeySequence.fromString(sequence, PORTABLE)
    return sequence.toString(PORTABLE)


def refusal_for(sequence: str) -> str | None:
    """Why `sequence` cannot be a window shortcut, or None when it can.

    Empty is allowed (it clears the shortcut). More than one chord ("Ctrl+K, Ctrl+C") is refused:
    Qt accepts it in a menu, but a person clearing a mistaken binding then has two keys to hunt for.
    """
    if not sequence:
        return None
    parsed = QKeySequence.fromString(sequence, PORTABLE)
    # Text Qt cannot read is NOT an empty sequence: "banana" parses to one "unknown" key whose portable
    # text is "", so the empty test alone lets it through and `set_shortcut` would then clear a
    # command's shortcut on a typo.
    if parsed.isEmpty() or not parsed.toString(PORTABLE):
        return f"{sequence!r} is not a key combination."
    if parsed.count() > 1:
        return "A shortcut is one key combination, not a sequence of them."
    combination = parsed[0]
    key = combination.key()
    is_function_key = Qt.Key.Key_F1 <= key <= Qt.Key.Key_F35
    if not is_function_key and not any(combination.keyboardModifiers() & flag for flag in _SAFE_MODIFIERS):
        return (
            "A shortcut needs Ctrl, Alt or Meta (or to be a function key): a bare letter, digit or "
            "Shift+letter would compete with the keys the drawing canvas uses."
        )
    return None


def _label_of(action: QAction) -> str:
    return action.text().replace("&", "").rstrip(".…").strip()


class ShortcutRegistry:
    """See the module docstring."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        #: (help key, action, label) in the order registered; ids are decided in `apply`.
        self._pending: list[tuple[str, QAction, str]] = []
        #: command id -> the action, in menu order.
        self._actions: dict[str, QAction] = {}
        self._labels: dict[str, str] = {}
        #: command id -> the shortcut the code gave it, captured by `apply`.
        self._defaults: dict[str, str] = {}
        self._sealed = False

    # --- registration ------------------------------------------------------------------

    def track(self, key: str, action: QAction, label: str | None = None) -> None:
        """Remember `action`, documented under `key`.

        `label` is what the Keyboard page calls it when the action's own text would not say what
        it is on a page of fifty commands (the panel rail's toggle is titled just "Panels").

        Ignored once `apply` has run: a menu rebuilt later (the installed-plugins list) would
        otherwise add commands whose defaults were never captured and whose ids depend on when
        they were built.
        """
        if not self._sealed:
            self._pending.append((key, action, label or _label_of(action)))

    def apply(self) -> None:
        """Name every tracked action, capture its default and put the person's overrides in force.

        Called once, after the menus are built, so every default the code gave is in place and a
        key's uniqueness can be judged over all of them.
        """
        if self._sealed:
            return
        self._sealed = True
        uses: dict[str, int] = {}
        for key, _action, _label in self._pending:
            uses[key] = uses.get(key, 0) + 1
        for key, action, label in self._pending:
            command_id = key if uses[key] == 1 else f"{key}:{label}"
            while command_id in self._actions:  # two identical labels under one shared key
                command_id += "#"
            self._actions[command_id] = action
            self._labels[command_id] = label
            self._defaults[command_id] = portable(action.shortcut())
        self._pending = []
        for command_id, sequence in self._intended().items():
            self._actions[command_id].setShortcut(QKeySequence.fromString(sequence, PORTABLE))

    def _intended(self) -> dict[str, str]:
        """What every command should hold at startup: its stored choice, else its default.

        **TWO COMMANDS ON ONE KEY MAKE BOTH DEAD.** Qt treats a shortcut two actions share as
        ambiguous and runs neither. A stored choice can collide because a later release gave
        another command that key by default, or the store was edited by hand. The colliding CHOICE
        is dropped (its command returns to its default, with a warning) and the shipped default
        keeps the key -- never the reverse, because a person's old choice must not disable a command
        the release added. Repeated until stable, since a returned default can collide in turn.
        Choices that merely swap two commands' keys collide with nothing and are kept whole.
        """
        chosen: dict[str, str] = {}
        for command_id in self._actions:
            stored = self._stored(command_id)
            if stored is not None:
                chosen[command_id] = stored
        while True:
            holders: dict[str, list[str]] = {}
            for command_id in self._actions:
                held = chosen.get(command_id, self._defaults[command_id])
                if held:
                    holders.setdefault(portable(held), []).append(command_id)
            dropped = [
                command_id
                for names in holders.values() if len(names) > 1
                for command_id in names if command_id in chosen
            ]
            if not dropped:
                break
            for command_id in dropped:
                logger.warning(
                    "Stored shortcut %r for %s collides with another command; using the default",
                    chosen.pop(command_id), command_id,
                )
        return {c: chosen.get(c, self._defaults[c]) for c in self._actions}

    # --- reading -------------------------------------------------------------------------

    def _stored(self, command_id: str) -> str | None:
        """The override, or None to follow the default. "" is a real override: no shortcut."""
        raw = self._settings.get(SHORTCUT_KEY_PREFIX + command_id, None)
        if raw is None:
            return None
        text = str(raw)
        if text and refusal_for(text) is not None:
            logger.warning("Stored shortcut for %s (%r) is not usable; using the default", command_id, text)
            return None
        return text

    def entries(self) -> list[ShortcutEntry]:
        return [
            ShortcutEntry(
                command_id=command_id,
                label=self._labels[command_id],
                default=self._defaults[command_id],
                current=portable(action.shortcut()),
            )
            for command_id, action in self._actions.items()
        ]

    def entry(self, command_id: str) -> ShortcutEntry | None:
        return next((e for e in self.entries() if e.command_id == command_id), None)

    def conflicts(self, sequence: str, exclude: str = "") -> list[ShortcutEntry]:
        """The OTHER commands already using `sequence`."""
        if not sequence:
            return []
        wanted = portable(sequence)
        return [e for e in self.entries() if e.command_id != exclude and e.current == wanted]

    # --- changing --------------------------------------------------------------------------

    def set_shortcut(self, command_id: str, sequence: str) -> str | None:
        """Give a command a shortcut; returns None on success, or the reason it was refused.

        Refused (and nothing changes) when the sequence is not assignable or another command
        already uses it. The caller says which one, and the person clears THAT first: a silent
        steal would leave a command with no way in and no sign of why.
        """
        action = self._actions.get(command_id)
        if action is None:
            return f"There is no command {command_id!r}."
        # The text as GIVEN is what is judged: normalising first would turn unreadable text
        # into "", which is a valid request to clear the shortcut.
        reason = refusal_for(sequence)
        if reason is not None:
            return reason
        sequence = portable(sequence) if sequence else ""
        taken = self.conflicts(sequence, exclude=command_id)
        if taken:
            return f"{sequence} is already used by {taken[0].label}."
        action.setShortcut(QKeySequence.fromString(sequence, PORTABLE))
        self._store(command_id, sequence)
        return None

    def reset(self, command_id: str) -> str | None:
        """Back to the default; refused, with the reason, if another command holds it now."""
        return self.set_shortcut(command_id, self._defaults.get(command_id, ""))

    def reset_all(self) -> None:
        """Every command back to its default, and every stored override forgotten.

        Cleared first and re-applied second, so a default is never refused for colliding with an
        override that is about to be replaced.
        """
        for action in self._actions.values():
            action.setShortcut(QKeySequence())
        for command_id, action in self._actions.items():
            action.setShortcut(QKeySequence.fromString(self._defaults[command_id], PORTABLE))
            self._settings.remove(SHORTCUT_KEY_PREFIX + command_id)

    def _store(self, command_id: str, sequence: str) -> None:
        """Following the default again means NO stored value rather than one equal to it, so a later
        change of the default in code still reaches a person who never chose anything."""
        key = SHORTCUT_KEY_PREFIX + command_id
        if sequence == self._defaults.get(command_id, ""):
            self._settings.remove(key)
        else:
            self._settings.set(key, sequence)
