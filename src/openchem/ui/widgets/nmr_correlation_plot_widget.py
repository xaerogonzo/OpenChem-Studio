from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from openchem.ui.picture_export import show_picture_menu

from openchem.ui import contours
from openchem.ui.widgets import plot_zoom
from openchem.ui.widgets.plot_axis import nice_ticks

#: One wheel notch zooms by this factor (in); the inverse zooms out. Chosen
#: so a handful of notches comfortably separates two cross peaks a couple
#: of tenths of a ppm apart without the first notch feeling like nothing
#: happened.
_ZOOM_STEP = 0.85
#: Cannot zoom in past this fraction of the full (padded) data span --
#: below it the axes stop meaning anything, and contour tracing over a
#: near-zero range is wasted work.
_MIN_ZOOM_FRACTION = 0.02
#: A press/release pair closer together than this, in pixels, is a CLICK
#: (resolve the nearest peak) rather than a PAN (the view already moved).
_CLICK_MAX_DRIFT = 4.0
#: How close a click has to land to a peak's drawn centre, in pixels, to
#: select it -- independent of `_CONTOUR_COLOUR`'s drawn dot radius, which
#: is deliberately tiny so it reads as the exact datum, not a hit target.
_CLICK_HIT_RADIUS = 10.0
#: The selected peak -- a clicked peak, or the one a table row selected.
_HIGHLIGHT_COLOUR = QColor(214, 100, 20)


@dataclass(frozen=True)
class Peak:
    """A single point on a 2D correlation plot.

    `atom_a`/`atom_b` are the cross peak's STABLE identity -- the same
    pair the table row beside this plot was built from (see
    `QuantumChemistryPanel._populate_correlation_tab`). A click resolves
    to a peak, and a peak resolves to a table row and a pair of atoms,
    through this pair rather than by "whichever row has nearby
    coordinates": two cross peaks can legitimately share a shift pair
    (a symmetric molecule, or two diastereotopic protons), where
    coordinates alone would not tell them apart.
    """

    x: float
    y: float
    label: str | None = None
    atom_a: int | None = None
    atom_b: int | None = None


class NmrCorrelationPlotWidget(QWidget):
    """2D NMR cross peaks (HSQC/HMBC/COSY), drawn as contours or dots.

    Hand-rolled `QPainter`, no charting library. Axes in NMR convention:
    higher ppm toward the top-left corner.

    CONTOURS ARE THE DEFAULT because that is how a 2D spectrum is read --
    a chemist compares a predicted HSQC against a real one by shape and
    position, and a scatter of dots does not look like the thing it is
    being compared to. The dot view stays available, and is genuinely
    better when peaks are few and far apart.

    WHAT THE RINGS MEAN, exactly: nothing beyond position. Every peak is
    drawn with the same amplitude and width, because the cross peaks come
    from the molecular graph (`chem/nmr_correlation.py`) and carry no
    intensity. Real contour heights encode peak volume; ours cannot, and
    the module docstring in `ui/contours.py` says so at the place the
    grid is built. Overlapping peaks DO sum, so a crowded region reads as
    one taller feature -- which is true of the drawing and true of a real
    spectrum, and is the one place the shape carries information.
    """

    #: Emits (atom_a, atom_b) of the clicked peak -- the outbound half of
    #: the bidirectional link to the table beside this plot.
    peak_selected = Signal(int, int)
    #: The view was zoomed, panned or reset, so a host can enable its Reset Zoom.
    view_changed = Signal()

    _MARGIN = 50.0
    _CONTOUR_COLOUR = QColor(30, 100, 200)

    def __init__(
        self,
        peaks: list[Peak] | None = None,
        x_label: str = "",
        y_label: str = "",
        parent: QWidget | None = None,
        show_contours: bool = True,
    ) -> None:
        super().__init__(parent)
        self._peaks: list[Peak] = list(peaks or [])
        self._x_label = x_label
        self._y_label = y_label
        self._show_contours = show_contours
        # The grid is in DATA coordinates, so it survives a resize -- only
        # the peak list invalidates it. Rebuilding a 200x200 grid on every
        # repaint would be work that changes nothing.
        self._grid: contours.DensityGrid | None = None
        #: Shown in the plot area while there are no peaks. Settable so the
        #: panel can name the experiment ("No HSQC cross peaks yet.")
        #: rather than this widget guessing which one it is drawing.
        self._empty_message = "No cross peaks yet."
        # None means "fit to the data" -- `_axis_ranges()`'s own padded
        # extent. Set only by zooming/panning, and never by `set_peaks`,
        # which deliberately leaves a user's zoom alone across a live
        # re-render (a job finishing while zoomed in must not snap back
        # out). A brand-new set of peaks from a DIFFERENT run is reset by
        # the panel calling `reset_view()` itself -- see
        # `quantum_chemistry_panel._render_run`.
        self._view_x_range: tuple[float, float] | None = None
        self._view_y_range: tuple[float, float] | None = None
        self._panning = False
        self._pan_last_pos: QPointF | None = None
        self._press_pos: QPointF | None = None
        #: The selected (atom_a, atom_b) pair, or None -- the inbound half
        #: of the link, set by `set_highlighted_pair` when a table row is
        #: selected instead of a peak clicked directly.
        self._highlighted_pair: tuple[int, int] | None = None
        self.setMinimumSize(280, 280)
        self.setMouseTracking(False)

    def set_highlighted_pair(self, atom_a: int | None, atom_b: int | None) -> None:
        self._highlighted_pair = (atom_a, atom_b) if atom_a is not None and atom_b is not None else None
        self.update()

    def view_ranges(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The ranges actually drawn -- the zoomed/panned window if one is
        set, otherwise the full padded data extent."""
        x_min, x_max, y_min, y_max = self._axis_ranges()
        x_range = self._view_x_range or (x_min, x_max)
        y_range = self._view_y_range or (y_min, y_max)
        return x_range, y_range

    def is_zoomed(self) -> bool:
        return self._view_x_range is not None or self._view_y_range is not None

    def reset_view(self) -> None:
        self._view_x_range = None
        self._view_y_range = None
        self.view_changed.emit()
        self.update()

    def set_empty_message(self, message: str) -> None:
        self._empty_message = message
        self.update()

    def empty_message(self) -> str:
        """What is painted here while there are no peaks.

        Readable so the panel's own `empty_message_for_tab` can derive a
        tab's explanation from the widgets rather than from a list kept
        beside them.
        """
        return self._empty_message

    def set_peaks(self, peaks: list[Peak], x_label: str = "", y_label: str = "") -> None:
        self._peaks = list(peaks)
        self._x_label = x_label
        self._y_label = y_label
        self._grid = None
        self.update()

    def set_show_contours(self, show: bool) -> None:
        self._show_contours = bool(show)
        self.update()

    def _density(self) -> contours.DensityGrid:
        if self._grid is None:
            x_min, x_max, y_min, y_max = self._axis_ranges()
            self._grid = contours.density_grid(
                [(p.x, p.y) for p in self._peaks], (x_min, x_max), (y_min, y_max)
            )
        return self._grid

    def _axis_ranges(self) -> tuple[float, float, float, float]:
        if not self._peaks:
            return 0.0, 1.0, 0.0, 1.0
        xs = [p.x for p in self._peaks]
        ys = [p.y for p in self._peaks]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        # Pad a flat/single-point range so it isn't a zero-width plot area.
        if x_min == x_max:
            x_min, x_max = x_min - 1.0, x_max + 1.0
        if y_min == y_max:
            y_min, y_max = y_min - 1.0, y_max + 1.0
        pad_x = (x_max - x_min) * 0.1
        pad_y = (y_max - y_min) * 0.1
        return x_min - pad_x, x_max + pad_x, y_min - pad_y, y_max + pad_y

    def _to_widget_coords(
        self, x: float, y: float, plot_rect: QRectF, x_range: tuple[float, float], y_range: tuple[float, float]
    ) -> tuple[float, float]:
        x_min, x_max = x_range
        y_min, y_max = y_range
        # NMR convention: higher ppm toward the origin (top-left) -- both
        # axes are drawn descending left-to-right / top-to-bottom.
        fx = (x_max - x) / (x_max - x_min) if x_max != x_min else 0.5
        fy = (y_max - y) / (y_max - y_min) if y_max != y_min else 0.5
        px = plot_rect.left() + fx * plot_rect.width()
        py = plot_rect.top() + fy * plot_rect.height()
        return px, py

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._MARGIN,
            self._MARGIN / 2,
            max(self.width() - 1.5 * self._MARGIN, 1.0),
            max(self.height() - 1.5 * self._MARGIN, 1.0),
        )

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        # A reader chart has its own menu installed (CustomContextMenu), which
        # takes over; this is for the same plot anywhere else it is shown.
        show_picture_menu(self, event, "nmr-correlation")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        plot_rect = self._plot_rect()

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(plot_rect)

        # In the plot's OWN header, not just a caption or a hover tooltip
        # -- these cross peaks come from the molecular graph
        # (chem/nmr_correlation.py), not a simulated 2D experiment, and a
        # zoomable contour map that looks like spectrometer software is
        # exactly the presentation where that distinction most needs
        # saying where it is being read, not somewhere it has to be
        # sought out.
        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawText(
            QRectF(plot_rect.left(), plot_rect.top() - self._MARGIN / 2, plot_rect.width() - 100, self._MARGIN / 2),
            Qt.AlignmentFlag.AlignLeft,
            "connectivity-derived cross peaks, not simulated intensities",
        )

        # The empty state, PAINTED rather than added as a placeholder
        # widget. An empty plot is axes around nothing, which reads as
        # broken; saying so costs one drawText.
        #
        # It is drawn instead of using a placeholder widget for a measured
        # reason, not a stylistic one: adding a placeholder QLabel to a tab
        # page that already holds content widgets corrupted the heap during
        # the teardown collect. See `ui/widgets/empty_state.py`, which has
        # the numbers. Painting into a widget that already exists sidesteps
        # it entirely, and is the better drawing anyway -- the message
        # lands where the peaks would be.
        if not self._peaks:
            painter.setPen(QPen(QColor(120, 120, 120)))
            painter.drawText(
                plot_rect,
                Qt.AlignmentFlag.AlignCenter,
                self._empty_message,
            )

        painter.drawText(
            QRectF(0, self.height() - self._MARGIN / 2, self.width(), self._MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            self._x_label,
        )
        painter.save()
        painter.translate(self._MARGIN / 4, self.height() / 2)
        painter.rotate(-90)
        painter.drawText(
            QRectF(-self.height() / 2, -self._MARGIN / 4, self.height(), self._MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            self._y_label,
        )
        painter.restore()

        if not self._peaks:
            painter.end()
            return

        # The VIEW window (zoomed/panned, or the full padded extent) is
        # what maps data to pixels; the density grid underneath it keeps
        # covering the full data extent regardless -- see `_density()`.
        # Zooming re-maps the same field onto more pixels, it never
        # recomputes it.
        x_range, y_range = self.view_ranges()
        self._draw_axis_ticks(painter, plot_rect, x_range, y_range)

        if self._show_contours:
            self._draw_contours(painter, plot_rect, x_range, y_range)

        painter.save()
        painter.setClipRect(plot_rect)
        for peak in self._peaks:
            highlighted = (
                self._highlighted_pair is not None
                and peak.atom_a is not None
                and (peak.atom_a, peak.atom_b) == self._highlighted_pair
            )
            colour = _HIGHLIGHT_COLOUR if highlighted else self._CONTOUR_COLOUR
            painter.setPen(QPen(colour))
            painter.setBrush(colour)
            px, py = self._to_widget_coords(peak.x, peak.y, plot_rect, x_range, y_range)
            # A small centre mark stays even under contours: it is the
            # actual datum, and at a low zoom two merged blobs would
            # otherwise hide how many peaks are really there. A selected
            # peak is drawn larger rather than just recoloured, the same
            # "bigger AND a different colour" NmrSpectrumWidget uses for a
            # highlighted stick.
            radius = (3.0 if highlighted else 1.5) if self._show_contours else (5.0 if highlighted else 3.0)
            painter.drawEllipse(QRectF(px - radius, py - radius, radius * 2, radius * 2))
            if peak.label:
                painter.drawText(QRectF(px + 5, py - 8, 60, 16), Qt.AlignmentFlag.AlignLeft, peak.label)
        painter.restore()

        if self.is_zoomed():
            painter.setPen(QPen(QColor(120, 120, 120)))
            painter.drawText(
                QRectF(plot_rect.right() - 90, plot_rect.top() - self._MARGIN / 2, 90, self._MARGIN / 2),
                Qt.AlignmentFlag.AlignRight,
                "zoomed (double-click to reset)",
            )
        painter.end()

    def _data_point_at(self, pos: QPointF, plot_rect: QRectF) -> tuple[float, float]:
        """The inverse of `_to_widget_coords` against the current view."""
        x_range, y_range = self.view_ranges()
        x_min, x_max = x_range
        y_min, y_max = y_range
        fx = (pos.x() - plot_rect.left()) / plot_rect.width() if plot_rect.width() else 0.5
        fy = (pos.y() - plot_rect.top()) / plot_rect.height() if plot_rect.height() else 0.5
        # Inverse of `_to_widget_coords`'s descending-axis mapping.
        x = x_max - fx * (x_max - x_min)
        y = y_max - fy * (y_max - y_min)
        return x, y

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override naming
        if not self._peaks:
            return
        plot_rect = self._plot_rect()
        anchor_x, anchor_y = self._data_point_at(event.position(), plot_rect)

        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        full_x_min, full_x_max, full_y_min, full_y_max = self._axis_ranges()
        full_x_range = (full_x_min, full_x_max)
        full_y_range = (full_y_min, full_y_max)

        x_range, y_range = self.view_ranges()
        new_x_range = plot_zoom.zoomed_window(x_range, full_x_range, anchor_x, factor, _MIN_ZOOM_FRACTION)
        new_y_range = plot_zoom.zoomed_window(y_range, full_y_range, anchor_y, factor, _MIN_ZOOM_FRACTION)

        # A span that reaches the full data span is the same thing as "not
        # zoomed" -- drop back to None so `is_zoomed()` and the cached
        # `_grid` usage both read it as the fit-to-data state again.
        if plot_zoom.is_full_span(new_x_range, full_x_range) and plot_zoom.is_full_span(new_y_range, full_y_range):
            self.reset_view()
        else:
            self._view_x_range = new_x_range
            self._view_y_range = new_y_range
            self.view_changed.emit()
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        self.reset_view()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        if event.button() == Qt.MouseButton.LeftButton and self._peaks:
            self._panning = True
            self._pan_last_pos = event.position()
            self._press_pos = event.position()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        if not self._panning or self._pan_last_pos is None:
            super().mouseMoveEvent(event)
            return
        plot_rect = self._plot_rect()
        x_range, y_range = self.view_ranges()
        delta = event.position() - self._pan_last_pos
        self._pan_last_pos = event.position()
        if plot_rect.width() and plot_rect.height():
            # The data point under the OLD cursor position must end up
            # under the NEW one -- a drag grabs the plot, not the axes.
            self._view_x_range = plot_zoom.panned_window(x_range, delta.x(), plot_rect.width())
            self._view_y_range = plot_zoom.panned_window(y_range, delta.y(), plot_rect.height())
            self.view_changed.emit()
            self.update()
        event.accept()

    def _peak_near(self, pos: QPointF, plot_rect: QRectF) -> Peak | None:
        """The nearest peak to `pos`, within `_CLICK_HIT_RADIUS` pixels, or
        None. Ties (two peaks equidistant, or overlapping) go to whichever
        was drawn LAST -- the one on top, matching what the eye sees."""
        x_range, y_range = self.view_ranges()
        best: tuple[float, Peak] | None = None
        for peak in self._peaks:
            px, py = self._to_widget_coords(peak.x, peak.y, plot_rect, x_range, y_range)
            distance = ((px - pos.x()) ** 2 + (py - pos.y()) ** 2) ** 0.5
            if distance <= _CLICK_HIT_RADIUS and (best is None or distance <= best[0]):
                best = (distance, peak)
        return best[1] if best else None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            press_pos, self._press_pos = self._press_pos, None
            self._pan_last_pos = None
            if press_pos is not None:
                drift = plot_zoom.drift(event.position().x() - press_pos.x(), event.position().y() - press_pos.y())
                if drift <= _CLICK_MAX_DRIFT:
                    peak = self._peak_near(event.position(), self._plot_rect())
                    if peak is not None and peak.atom_a is not None and peak.atom_b is not None:
                        self.set_highlighted_pair(peak.atom_a, peak.atom_b)
                        self.peak_selected.emit(peak.atom_a, peak.atom_b)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _draw_axis_ticks(
        self, painter: QPainter, plot_rect: QRectF, x_range: tuple[float, float], y_range: tuple[float, float]
    ) -> None:
        """Intermediate numeric ticks on both axes -- this plot drew none
        before (only the axis captions), unlike `NmrSpectrumWidget`,
        which at least labelled its two endpoints. Reads the current
        VIEW range so a zoomed-in plot's ticks are the zoomed numbers,
        not the full data's."""
        painter.setPen(QPen(QColor(120, 120, 120)))
        for value in nice_ticks(*x_range):
            px, _ = self._to_widget_coords(value, y_range[0], plot_rect, x_range, y_range)
            painter.drawLine(QPointF(px, plot_rect.bottom()), QPointF(px, plot_rect.bottom() + 4))
            painter.drawText(
                QRectF(px - 30, plot_rect.bottom() + 4, 60, self._MARGIN / 4),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.4g}",
            )
        for value in nice_ticks(*y_range):
            _, py = self._to_widget_coords(x_range[0], value, plot_rect, x_range, y_range)
            painter.drawLine(QPointF(plot_rect.left() - 4, py), QPointF(plot_rect.left(), py))
            painter.drawText(
                QRectF(plot_rect.left() - self._MARGIN, py - 7, self._MARGIN - 6, 14),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.4g}",
            )

    def _draw_contours(self, painter, plot_rect, x_range, y_range) -> None:
        """Rings from lowest level to highest, darkening as they climb.

        Drawn faintest first so the innermost ring reads as the peak
        centre, matching how spectrometer software shades levels.
        """
        grid = self._density()
        levels = contours.contour_levels(peak=grid.peak_value)
        if not levels:
            return
        painter.save()
        painter.setClipRect(plot_rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, level in enumerate(levels):
            fade = 90 + int(165 * index / max(len(levels) - 1, 1))
            colour = QColor(self._CONTOUR_COLOUR)
            colour.setAlpha(fade)
            painter.setPen(QPen(colour, 1.0))
            for x0, y0, x1, y1 in contours.trace(grid, level):
                ax, ay = self._to_widget_coords(x0, y0, plot_rect, x_range, y_range)
                bx, by = self._to_widget_coords(x1, y1, plot_rect, x_range, y_range)
                painter.drawLine(QLineF(ax, ay, bx, by))
        painter.restore()
