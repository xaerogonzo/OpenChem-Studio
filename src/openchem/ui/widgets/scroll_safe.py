"""Keeps a wheel scroll from being eaten by a control it merely passes over.

`QComboBox` and `QAbstractSpinBox` (so `QSpinBox`/`QDoubleSpinBox`) both
change their own value on a wheel event UNCONDITIONALLY -- confirmed live
with `OPENCHEM_DRIVE`'s `wheel_trace`/`wheel` steps against this panel's real
controls: a `QComboBox` accepts the event directly; a `QSpinBox` delivers it
first to its internal `QLineEdit` (which correctly ignores it), and Qt's own
native propagation then hands it to the `QSpinBox` itself, which does not.
Neither checks focus. So scrolling PAST one of these controls on the way
down a form silently changes it instead of scrolling the page -- the same
class of surprise Phase 6 fixed for a `QWebEngineView`, with a materially
simpler cause: an ordinary Qt widget, not Chromium's own canvas, so native
propagation-to-parent-on-ignore (the mechanism `NmrCorrelationPlotWidget`'s
own zoom already relies on) is trusted to carry an ignored event the rest of
the way to an enclosing `QScrollArea`, rather than manually redirected to one
the way `Mol3DViewerBackend._ScrollThroughFilter` has to.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject


class ScrollSafeFilter(QObject):
    """Install on a `QComboBox`/`QAbstractSpinBox` with `installEventFilter`.

    Unfocused: the wheel event is `ignore()`d and consumed here (the
    control's own `wheelEvent` never runs), leaving it for Qt's native
    propagation to carry to whatever ancestor DOES want to scroll. Focused
    (the control was clicked into first): the event is let through
    unchanged, so the normal "wheel changes the value" gesture still works
    -- the same click-first contract Phase 6 already established for the 3D
    views.
    """

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override naming
        if event.type() != QEvent.Type.Wheel or watched.hasFocus():
            return False
        event.ignore()
        return True


def make_scroll_safe(widget) -> ScrollSafeFilter:
    """Installs a `ScrollSafeFilter` on `widget` and returns it.

    Constructed WITH `widget` as its Qt parent (not `installEventFilter`,
    which does not take ownership), so the filter's lifetime is tied to the
    control's the same way `Mol3DViewerBackend._scroll_through_filter` is
    tied to its view -- Qt's own parent/child tracking keeps it alive, not
    a Python reference. The caller is still expected to keep the returned
    value (a plain instance attribute is enough), because a filter
    findable only through `widget.children()` is a filter a test cannot
    assert on directly.
    """
    guard = ScrollSafeFilter(widget)
    widget.installEventFilter(guard)
    return guard
