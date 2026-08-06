"""The status-bar structure-check light.

Marvin puts one in the corner and it is the right idea: checking is only
useful if you find out it happened. A panel you have to open first tells
you nothing about the structure you are drawing right now.

Four states, following Marvin's own: disabled (no structure to check),
clean, warning, error. Colour is never the only signal -- each state also
carries a symbol and a word, because roughly one man in twelve cannot
distinguish the red from the green.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel

from openchem.domain.structure_issue import CheckerResult, Severity

#: state -> (symbol, colour, tooltip stem). Okabe-Ito vermillion and blue
#: rather than pure red/green, which is this project's existing palette
#: choice for the same colour-vision reason.
_STATES = {
    "disabled": ("--", "#888888", "No structure to check"),
    "clean": ("OK", "#009e73", "No issues found"),
    "warning": ("!", "#e69f00", "Check the structure"),
    "error": ("X", "#d55e00", "This structure has a problem"),
}


class CheckerStatusIndicator(QLabel):
    """A one-word summary of the last check, clickable to open the panel."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CheckerStatusIndicator")
        self._state = "disabled"
        self.set_disabled()

    # --- state --------------------------------------------------------------

    def state(self) -> str:
        return self._state

    def set_disabled(self, reason: str = "") -> None:
        self._apply("disabled", reason or _STATES["disabled"][2])

    def show_result(self, result: CheckerResult) -> None:
        errors = len(result.errors)
        warnings = len(result.warnings)
        if errors:
            state = "error"
            text = f"{errors} error" + ("s" if errors != 1 else "")
            if warnings:
                text += f", {warnings} warning" + ("s" if warnings != 1 else "")
        elif warnings:
            state = "warning"
            text = f"{warnings} warning" + ("s" if warnings != 1 else "")
        elif result.issues:
            # INFO only. Not a warning: an isotope label or an explained
            # hypervalent centre is a note, and colouring it amber would
            # train people to ignore amber.
            state = "clean"
            text = f"{len(result.issues)} note" + ("s" if len(result.issues) != 1 else "")
        else:
            state = "clean"
            text = "No issues"
        self._apply(state, text)

    def _apply(self, state: str, detail: str) -> None:
        symbol, colour, _ = _STATES[state]
        self._state = state
        self.setText(f"{symbol}  Structure: {detail}")
        self.setStyleSheet(f"color: {colour}; padding: 0 8px;")
        self.setToolTip(f"{detail}. Click to open the Structure Checker.")

    # --- interaction --------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.clicked.emit()
        super().mousePressEvent(event)
