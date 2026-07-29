from __future__ import annotations

from typing import Callable, Protocol

from PySide6.QtWidgets import QWidget

from openchem.domain.molecule import MoleculeModel


class UIRegistry(Protocol):
    """What `PluginManager` needs from a host window — nothing more.

    A `Protocol` rather than a base class `MainWindow` inherits from:
    `Protocol` matching is structural, so `MainWindow` satisfies this by
    having matching methods without ever subclassing it at runtime. That
    keeps `PluginManager` decoupled from any concrete window class — a
    headless mode, a second window, or a different frontend later just
    needs its own `UIRegistry` implementation, no `PluginManager` changes.
    (It also sidesteps the QObject/ABCMeta metaclass conflict documented in
    `ui/editor_backend.py`, since no runtime inheritance is involved.)
    """

    def add_panel(self, panel_id: str, widget_factory: Callable[[], QWidget]) -> None:
        """Add a new dock panel hosting the widget `widget_factory()` returns."""
        ...

    def remove_panel(self, panel_id: str) -> None:
        """Remove a previously added panel."""
        ...

    def add_menu_action(self, plugin_id: str, label: str, callback: Callable[[], None]) -> None:
        """Add an entry under the Plugins menu that calls `callback()` when triggered."""
        ...

    def remove_menu_actions(self, plugin_id: str) -> None:
        """Remove every menu action previously added for this plugin."""
        ...

    def add_molecule(self, molecule: MoleculeModel) -> None:
        """Add `molecule` to the current project as an undoable action and
        select it — the same path `MainWindow._new_molecule()` uses. A
        no-op (should log, not raise) if no project is currently open."""
        ...
