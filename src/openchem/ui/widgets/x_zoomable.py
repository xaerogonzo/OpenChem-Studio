"""Ctrl+wheel zoom, Shift+wheel pan and double-click reset along x, for a plot that draws a window of its data.

**THE LINE CHART'S GESTURES, WRITTEN ONCE.** The histogram and the
stick chart drew their whole data span however many points it held, so a powder pattern's crowded
low-angle lines or a distribution's thin tail could not be opened up. `LineChartWidget` already had
the answer and the same constraint: these charts sit in a scrolling reader, so a PLAIN wheel must
keep scrolling the page and zoom is Ctrl+wheel, pan Shift+wheel, a double-click puts it back.

It is a mixin, not a shared widget, because what differs is the drawing; the window arithmetic is
`plot_zoom`'s, shared with the NMR plots and the line chart. The host supplies four small facts:
`_zoom_has_data`, `_full_x_range`, `_plot_rect` and `_zoom_descending`, and declares the
`view_changed` signal (a mixin cannot, not being a QObject). The line chart, the histogram and the
stick chart all use it; the line chart's own copy was moved here unchanged, with its 20-odd zoom tests
as the net.

Put it BEFORE `QWidget` in the bases so its `wheelEvent` is the one that runs.
"""

from __future__ import annotations

from openchem.ui.widgets.plot_zoom import is_full_span, zoomed_window


class XZoomable:
    #: Zooming in stops at this fraction of the full span.
    _MIN_WINDOW_FRACTION = 0.02
    #: One wheel notch zooms by this factor, and pans by this fraction of the window.
    _ZOOM_STEP = 0.8
    _PAN_STEP = 0.1

    #: A zoomed x window `(low, high)` in DATA units, or None for the whole span. View state only:
    #: the data is never touched.
    _x_window: tuple[float, float] | None = None

    # -- what the host supplies ----------------------------------------------------

    def _zoom_has_data(self) -> bool:
        raise NotImplementedError

    def _full_x_range(self) -> tuple[float, float]:
        raise NotImplementedError

    def _zoom_descending(self) -> bool:
        return False

    def _window_changed(self) -> None:
        """Called after the window changed, before the repaint: drop anything that was keyed to it."""

    # -- the window ----------------------------------------------------------------

    def _x_range(self) -> tuple[float, float]:
        """The range DRAWN: the zoom window, or the whole span."""
        return self._x_window if self._x_window is not None else self._full_x_range()

    def is_zoomed(self) -> bool:
        return self._x_window is not None

    def view_range(self) -> tuple[float, float]:
        return self._x_range()

    def reset_view(self) -> None:
        self._set_x_window(None)

    def in_view(self, x: float) -> bool:
        """Whether `x` falls inside what is drawn (always, when not zoomed)."""
        if self._x_window is None:
            return True
        return self._x_window[0] <= x <= self._x_window[1]

    def _set_x_window(self, window: tuple[float, float] | None) -> None:
        if window == self._x_window:
            return
        self._x_window = window
        self._window_changed()
        self.view_changed.emit()
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        """**CTRL zooms and SHIFT pans; a plain wheel is NOT taken**, so the reader keeps scrolling."""
        from PySide6.QtCore import Qt

        modifiers = event.modifiers()
        delta = event.angleDelta().y() or event.angleDelta().x()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if not self._zoom_has_data() or delta == 0 or not (ctrl or shift):
            event.ignore()
            return
        full = self._full_x_range()
        window = self._x_range()
        if ctrl:
            rect = self._plot_rect()
            fraction = (event.position().x() - rect.left()) / rect.width() if rect.width() else 0.5
            fraction = max(0.0, min(1.0, fraction))
            if self._zoom_descending():
                fraction = 1.0 - fraction
            anchor = window[0] + fraction * (window[1] - window[0])
            factor = self._ZOOM_STEP if delta > 0 else 1.0 / self._ZOOM_STEP
            new = zoomed_window(window, full, anchor, factor, self._MIN_WINDOW_FRACTION)
            self._set_x_window(None if is_full_span(new, full) else new)
        elif self._x_window is not None:
            span = window[1] - window[0]
            shift_by = span * self._PAN_STEP * (-1 if delta > 0 else 1)
            low = min(max(window[0] + shift_by, full[0]), full[1] - span)
            self._set_x_window((low, low + span))
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.reset_view()
        super().mouseDoubleClickEvent(event)
