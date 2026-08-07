from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.ui import contours


@dataclass(frozen=True)
class Peak:
    """A single point on a 2D correlation plot.

    Kept to (x, y, optional label) so that the contour renderer added
    later consumes exactly this, with no data-model change -- which is
    what Phase 22 predicted when it deferred contours, and it held.
    """

    x: float
    y: float
    label: str | None = None


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
        self.setMinimumSize(280, 280)

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

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        plot_rect = QRectF(
            self._MARGIN,
            self._MARGIN / 2,
            max(self.width() - 1.5 * self._MARGIN, 1.0),
            max(self.height() - 1.5 * self._MARGIN, 1.0),
        )

        painter.setPen(QPen(QColor(120, 120, 120)))
        painter.drawRect(plot_rect)

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

        x_min, x_max, y_min, y_max = self._axis_ranges()
        x_range, y_range = (x_min, x_max), (y_min, y_max)

        if self._show_contours:
            self._draw_contours(painter, plot_rect, x_range, y_range)

        painter.setPen(QPen(self._CONTOUR_COLOUR))
        painter.setBrush(self._CONTOUR_COLOUR)
        for peak in self._peaks:
            px, py = self._to_widget_coords(peak.x, peak.y, plot_rect, x_range, y_range)
            # A small centre mark stays even under contours: it is the
            # actual datum, and at a low zoom two merged blobs would
            # otherwise hide how many peaks are really there.
            radius = 1.5 if self._show_contours else 3.0
            painter.drawEllipse(QRectF(px - radius, py - radius, radius * 2, radius * 2))
            if peak.label:
                painter.drawText(QRectF(px + 5, py - 8, 60, 16), Qt.AlignmentFlag.AlignLeft, peak.label)
        painter.end()

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
