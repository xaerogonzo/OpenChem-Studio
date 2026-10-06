"""The "Compare with..." drop-down, shared by every window that can offer it.

It was written inside the Calculator Inspector for per-atom results; the NMR view needs the same
button for a spectrum, and a second copy of a menu that decides what may honestly be compared is
two places for that decision to drift.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QMenu, QPushButton, QWidget


class CompareMenuButton(QPushButton):
    """A button whose menu lists what `result` can be compared with RIGHT NOW.

    `candidates(result)` returns `(anchor, others)` -- `Panel.comparable_with`. `on_compare` is
    handed the chosen list (anchor first). A drop-down rather than a dialog: `QPushButton.setMenu`
    shows its menu without `exec()`, which a test cannot patch, and the choice is one click either
    way.
    """

    def __init__(
        self,
        result: object,
        candidates: Callable[[object], tuple[object, list]],
        on_compare: Callable[[list], None],
        tooltip: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Compare with...", parent)
        self._result = result
        self._candidates = candidates
        self._on_compare = on_compare
        self.setObjectName("compareWith")
        self.setToolTip(tooltip)
        self._menu = QMenu(self)
        self._menu.aboutToShow.connect(self.rebuild)
        self.setMenu(self._menu)

    def rebuild(self) -> None:
        """Offer what can be compared NOW: another method may have been run since this opened.

        One entry per comparable result, and "all of them" when there are two or more. An empty
        menu says why instead of being empty.
        """
        menu = self._menu
        menu.clear()
        anchor, others = self._candidates(self._result)
        others = list(others)
        if not others:
            menu.addAction("Nothing to compare: run another method on this structure").setEnabled(False)
            return
        for candidate in others:
            action = menu.addAction(f"With {candidate.label}")
            action.setData([anchor, candidate])
            action.triggered.connect(self._on_action)
        if len(others) > 1:
            everyone = menu.addAction(f"With all {len(others)}")
            everyone.setData([anchor, *others])
            everyone.triggered.connect(self._on_action)

    def _on_action(self, _checked: bool = False) -> None:
        action = self.sender()
        chosen = action.data() if action is not None else None
        if chosen:
            self._on_compare(chosen)
