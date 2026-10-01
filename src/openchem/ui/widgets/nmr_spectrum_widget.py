from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from openchem.chem.nmr_signals import (
    DEFAULT_FREQUENCY_MHZ,
    RESIDUAL_SOLVENT_PEAKS,
    NMRSignal,
    lorentzian_envelope,
    multiplet_lines,
)
from openchem.ui.widgets import plot_zoom
from openchem.ui.widgets.plot_axis import nice_ticks

#: The axis line and its tick labels.
_AXIS_COLOR = QColor(120, 120, 120)
#: An ordinary, unselected signal -- sticks or the smooth curve alike.
_PEAK_COLOR = QColor(30, 100, 200)
#: The signal a table row, a 3D atom click, or a direct click selected.
_HIGHLIGHT_COLOR = QColor(214, 100, 20)
#: The deuterated solvent's own residual peak, drawn dashed so it is never
#: mistaken for one of the compound's own signals.
_SOLVENT_COLOR = QColor(150, 150, 150)
#: The cumulative "relative integral" trace -- a third colour, distinct
#: from both the solvent dash and the signal itself.
_INTEGRAL_COLOR = QColor(60, 150, 90)
#: Points sampled across the plot for the smooth curve and the integral
#: trace -- fine enough that a Lorentzian at the default HWHM (0.012 ppm)
#: over a typical 10 ppm span still has several samples under each line.
_CURVE_SAMPLE_COUNT = 400
#: Half-width of a peak's clickable region, in pixels. Peaks are drawn as
#: 1px vertical lines, which is far too thin to hit with a mouse -- and two
#: diastereotopic protons can share a shift exactly (the predictor splits the
#: signal without distinguishing the values), so the regions do sometimes
#: overlap; the first match wins, deterministically ordered by shift.
_HIT_HALF_WIDTH = 6.0
#: One wheel notch zooms by this factor (in); the inverse zooms out. Same
#: value and reasoning as `NmrCorrelationPlotWidget`'s own constant -- the
#: two plots should feel the same to scroll.
_ZOOM_STEP = 0.85
#: Cannot zoom in past this fraction of the full (padded) axis span.
_MIN_ZOOM_FRACTION = 0.02
#: A press/release pair closer together than this, in pixels, is a CLICK
#: (select the nearest signal) rather than a PAN (the view already moved).
_CLICK_MAX_DRIFT = 4.0


class NmrSpectrumWidget(QWidget):
    """A 1D NMR peak spectrum -- hand-rolled `QPainter`, no charting
    dependency, the same approach `NmrCorrelationPlotWidget` uses for the 2D
    correlation scatter plots.

    Peaks are stick lines on a descending-ppm axis (NMR convention: high
    shift on the left), with total height scaled by integration. A signal
    with a real coupling constant is drawn as its first-order MULTIPLET --
    lines J/frequency ppm apart with binomial intensities -- which is why
    the spectrometer frequency is a setting here: frequency does not move
    a chemical shift, but it does decide whether a multiplet resolves or
    collapses into one blur.

    Still NOT a simulated spectrum: no Lorentzian line shape, no
    second-order effects (the "roofing" that appears once two coupled
    shifts approach each other), no baseline noise. Those need a full
    spin-Hamiltonian treatment. Stick height means "this many nuclei",
    and line spacing means "this J at this field", and nothing more.

    Clicking anywhere in a signal's region emits `peak_clicked` with its
    `atom_indices`, which is what drives highlighting in the structure
    views.
    """

    peak_clicked = Signal(list)  # list[int] atom indices of the clicked signal

    _MARGIN = 50.0

    def __init__(
        self,
        signals: list[NMRSignal] | None = None,
        x_label: str = "δ (ppm)",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._signals: list[NMRSignal] = list(signals or [])
        self._x_label = x_label
        self._shielding = False
        self._highlighted_atoms: set[int] = set()
        self._frequency_mhz = DEFAULT_FREQUENCY_MHZ
        self._solvent: str | None = None
        self._element = "H"
        #: "sticks" (the original zero-width lines) or "smooth" (the same
        #: `multiplet_lines()` positions convolved with a Lorentzian -- see
        #: `lorentzian_envelope`). Neither is a simulated spectrum; smooth
        #: just reads more like one.
        self._render_mode = "sticks"
        self._show_integral = False
        # None means "fit to the data" -- `_axis_range()`'s own padded
        # extent. Set only by zooming/panning/`zoom_to_signal`, and
        # cleared by `set_signals` (a new spectrum resets navigation) but
        # never by anything else -- render mode, frequency, solvent and
        # integral visibility are viewer PREFERENCES, not navigation
        # state, and must survive a zoom untouched.
        self._view_range: tuple[float, float] | None = None
        self._panning = False
        self._pan_last_pos: QPointF | None = None
        self._press_pos: QPointF | None = None
        self.setMinimumSize(320, 200)

    def set_render_mode(self, mode: str) -> None:
        if mode not in ("sticks", "smooth"):
            raise ValueError(f"unknown NMR render mode: {mode!r}")
        self._render_mode = mode
        self.update()

    def render_mode(self) -> str:
        return self._render_mode

    def set_show_integral(self, show: bool) -> None:
        self._show_integral = bool(show)
        self.update()

    def set_signals(
        self, signals: list[NMRSignal], x_label: str = "δ (ppm)", shielding: bool = False
    ) -> None:
        """`shielding=True` means the values are isotropic shielding σ, not a
        chemical shift δ. The two run in OPPOSITE directions (δ = σ_ref − σ),
        so a raw σ drawn on the descending δ axis is a mirror image of the
        spectrum a chemist expects: the most shielded carbons (aliphatic,
        σ high) land on the DOWNFIELD side. σ is therefore drawn ascending
        left to right, which puts each nucleus where its δ will fall once
        it is referenced, and the axis says σ so it cannot be read as δ."""
        self._signals = list(signals)
        self._x_label = x_label
        self._shielding = shielding
        self._element = signals[0].element if signals else "H"
        self._highlighted_atoms.clear()
        self._view_range = None
        self.update()

    def set_frequency(self, frequency_mhz: float) -> None:
        self._frequency_mhz = frequency_mhz
        self.update()

    def set_solvent(self, solvent: str | None) -> None:
        """The residual peak of a deuterated solvent, or None for none.

        Drawn because it is always there in a real spectrum and a chemist
        reads around it -- and because, unlike everything else on this
        plot, it is a measured literature value rather than a prediction.
        """
        self._solvent = solvent
        self.update()

    def _solvent_shift(self) -> float | None:
        # A solvent peak is a chemical shift; it has no place on a σ axis.
        if not self._solvent or self._shielding:
            return None
        return RESIDUAL_SOLVENT_PEAKS.get(self._solvent, {}).get(self._element)

    def set_highlighted_atoms(self, atom_indices: list[int]) -> None:
        """Highlights every peak owning any of these atoms — the inbound half
        of the bidirectional link (a 3D atom click selects its signal)."""
        self._highlighted_atoms = set(atom_indices)
        self.update()

    def _axis_range(self) -> tuple[float, float]:
        if not self._signals:
            return 0.0, 1.0
        shifts = [signal.shift for signal in self._signals]
        solvent = self._solvent_shift()
        if solvent is not None:
            # Included so a solvent peak outside the sample's own range
            # (DMSO at 2.50 under an aromatics-only spectrum) is visible
            # rather than drawn off the edge of the plot.
            shifts.append(solvent)
        low, high = min(shifts), max(shifts)
        # A single peak (or several at one shift) would otherwise be a
        # zero-width axis; pad it into a real range.
        if low == high:
            low, high = low - 1.0, high + 1.0
        padding = (high - low) * 0.1
        return low - padding, high + padding

    def view_range(self) -> tuple[float, float]:
        """The range actually drawn -- the zoomed/panned window if one is
        set, otherwise the full padded data extent. Every consumer --
        stick/curve drawing, the integral sampling grid, labels, and
        `hit_regions()` -- reads THIS, never `_axis_range()` directly, so
        a zoomed plot's click regions track the viewport instead of
        staying anchored to the old range."""
        return self._view_range or self._axis_range()

    def is_zoomed(self) -> bool:
        return self._view_range is not None

    def reset_view(self) -> None:
        self._view_range = None
        self.update()

    def zoom_to_signal(self, signal: NMRSignal) -> None:
        """Centres and zooms the view on `signal`'s full multiplet extent
        -- not just its nominal shift, since a resolved triplet/quartet
        can extend visibly away from the centre. Uses the min/max of its
        own drawn lines (`multiplet_lines`, the same positions the plot
        itself renders), padded so the whole pattern reads clearly rather
        than filling the plot edge to edge."""
        lines = multiplet_lines(signal, self._frequency_mhz)
        shifts = [ppm for ppm, _intensity in lines]
        low, high = min(shifts), max(shifts)
        padding = max((high - low) * 0.75, 0.3)
        self._view_range = (low - padding, high + padding)
        self.update()

    def _data_x_at(self, x: float, plot_rect: QRectF) -> float:
        """The inverse of `_to_widget_x` against the CURRENT view."""
        low, high = self.view_range()
        if plot_rect.width() <= 0:
            return low
        fraction = (x - plot_rect.left()) / plot_rect.width()
        if self._shielding:
            return low + fraction * (high - low)
        return high - fraction * (high - low)

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._MARGIN,
            self._MARGIN / 2,
            max(self.width() - 1.5 * self._MARGIN, 1.0),
            max(self.height() - 1.5 * self._MARGIN, 1.0),
        )

    def _to_widget_x(self, shift: float, plot_rect: QRectF, x_range: tuple[float, float]) -> float:
        low, high = x_range
        # Descending ppm left-to-right, matching how every published NMR
        # spectrum is drawn (and NmrCorrelationPlotWidget's axes). Shielding
        # is the mirror image, see `set_signals`.
        if high == low:
            fraction = 0.5
        elif self._shielding:
            fraction = (shift - low) / (high - low)
        else:
            fraction = (high - shift) / (high - low)
        return plot_rect.left() + fraction * plot_rect.width()

    def hit_regions(self) -> list[tuple[QRectF, NMRSignal]]:
        """Clickable region per peak. Derived from geometry rather than
        recorded during `paintEvent`, so a click resolves correctly even
        before the first paint (and so it is testable without a repaint)."""
        if not self._signals:
            return []
        plot_rect = self._plot_rect()
        x_range = self.view_range()
        regions = []
        for signal in self._signals:
            x = self._to_widget_x(signal.shift, plot_rect, x_range)
            regions.append(
                (
                    QRectF(x - _HIT_HALF_WIDTH, plot_rect.top(), 2 * _HIT_HALF_WIDTH, plot_rect.height()),
                    signal,
                )
            )
        return regions

    def signal_at(self, x: float, y: float) -> NMRSignal | None:
        for region, signal in self.hit_regions():
            if region.contains(x, y):
                return signal
        return None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override naming
        """Horizontal-only scroll-to-zoom, around the cursor. No vertical
        zoom is added: `paintEvent`'s `max_integration` is deliberately
        the tallest peak across the WHOLE spectrum, not just the zoomed
        window, so a stick's height keeps meaning the same proton count
        at every zoom level -- rescaling it to whatever is visible would
        make relative integration lie as soon as you zoomed into a region
        without the tallest peak in it."""
        if not self._signals:
            return
        plot_rect = self._plot_rect()
        anchor = self._data_x_at(event.position().x(), plot_rect)
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        full_range = self._axis_range()
        new_range = plot_zoom.zoomed_window(self.view_range(), full_range, anchor, factor, _MIN_ZOOM_FRACTION)
        if plot_zoom.is_full_span(new_range, full_range):
            self.reset_view()
        else:
            self._view_range = new_range
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        self.reset_view()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        if event.button() == Qt.MouseButton.LeftButton and self._signals:
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
        delta = event.position() - self._pan_last_pos
        self._pan_last_pos = event.position()
        if plot_rect.width() > 0:
            self._view_range = plot_zoom.panned_window(
                self.view_range(), delta.x(), plot_rect.width(), descending=not self._shielding
            )
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            press_pos, self._press_pos = self._press_pos, None
            self._pan_last_pos = None
            if press_pos is not None:
                drift = plot_zoom.drift(event.position().x() - press_pos.x(), event.position().y() - press_pos.y())
                if drift <= _CLICK_MAX_DRIFT:
                    signal = self.signal_at(event.position().x(), event.position().y())
                    if signal is not None:
                        self._highlighted_atoms = set(signal.atom_indices)
                        self.update()
                        self.peak_clicked.emit(list(signal.atom_indices))
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _draw_ticks(self, painter: QPainter, plot_rect: QRectF, x_range: tuple[float, float]) -> None:
        """Intermediate numeric ticks across the current view, replacing
        the old two-endpoint-only labels -- spacing is view-range-
        dependent (`nice_ticks`), so a deep zoom still reads sane ticks
        instead of two numbers 0.02 ppm apart."""
        painter.setPen(QPen(_AXIS_COLOR))
        for value in nice_ticks(*x_range):
            x = self._to_widget_x(value, plot_rect, x_range)
            painter.drawLine(QPointF(x, plot_rect.bottom()), QPointF(x, plot_rect.bottom() + 4))
            painter.drawText(
                QRectF(x - 30, plot_rect.bottom() + 4, 60, self._MARGIN / 2 - 4),
                Qt.AlignmentFlag.AlignCenter,
                f"{value:.4g}",
            )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        plot_rect = self._plot_rect()
        painter.setPen(QPen(_AXIS_COLOR))
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.bottomRight())
        painter.drawText(
            QRectF(0, self.height() - self._MARGIN / 2, self.width(), self._MARGIN / 2),
            Qt.AlignmentFlag.AlignCenter,
            self._x_label,
        )

        if not self._signals:
            painter.end()
            return

        x_range = self.view_range()
        self._draw_ticks(painter, plot_rect, x_range)
        if self.is_zoomed():
            painter.setPen(QPen(_AXIS_COLOR))
            painter.drawText(
                QRectF(plot_rect.right() - 160, plot_rect.top() - self._MARGIN / 2, 160, self._MARGIN / 2),
                Qt.AlignmentFlag.AlignRight,
                "zoomed (double-click to reset)",
            )

        # Tallest peak fills the plot area; everything else is proportional
        # to its integration, so relative peak heights ARE relative proton
        # counts and nothing else.
        max_integration = max(signal.integration for signal in self._signals) or 1
        label_height = 14.0

        solvent_shift = self._solvent_shift()
        if solvent_shift is not None:
            # Dashed and grey: it belongs to the solvent, not the sample,
            # and must not be mistaken for one of the compound's signals.
            solvent_x = self._to_widget_x(solvent_shift, plot_rect, x_range)
            painter.setPen(QPen(_SOLVENT_COLOR, 1, Qt.PenStyle.DashLine))
            painter.drawLine(
                QRectF(solvent_x, plot_rect.top(), 0, plot_rect.height()).topLeft(),
                QRectF(solvent_x, plot_rect.top(), 0, plot_rect.height()).bottomLeft(),
            )
            painter.drawText(
                QRectF(solvent_x - 40, plot_rect.top(), 80, label_height),
                Qt.AlignmentFlag.AlignCenter,
                self._solvent or "",
            )

        if self._render_mode == "smooth":
            self._draw_smooth_curve(painter, plot_rect, x_range, label_height)
        else:
            for signal in self._signals:
                highlighted = bool(self._highlighted_atoms & set(signal.atom_indices))
                full_height = (plot_rect.height() - label_height) * (signal.integration / max_integration)
                painter.setPen(QPen(_HIGHLIGHT_COLOR if highlighted else _PEAK_COLOR, 3 if highlighted else 1))
                # Each line of the multiplet carries its share of the signal's
                # total intensity, so a quartet and a singlet of the same
                # integration still enclose the same area -- which is what
                # integration means.
                for line_shift, intensity in multiplet_lines(signal, self._frequency_mhz):
                    line_x = self._to_widget_x(line_shift, plot_rect, x_range)
                    height = full_height * intensity
                    painter.drawLine(
                        QRectF(line_x, plot_rect.bottom() - height, 0, height).topLeft(),
                        QRectF(line_x, plot_rect.bottom() - height, 0, height).bottomLeft(),
                    )
                centre_x = self._to_widget_x(signal.shift, plot_rect, x_range)
                painter.drawText(
                    QRectF(centre_x - 30, plot_rect.bottom() - full_height - label_height, 60, label_height),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{signal.shift:.2f}",
                )

        if self._show_integral:
            self._draw_integral(painter, plot_rect, x_range, label_height)

        painter.end()

    def _sample_grid(self, x_range: tuple[float, float], count: int = _CURVE_SAMPLE_COUNT) -> list[float]:
        """`count` ppm values, in LEFT-TO-RIGHT SCREEN order, spanning
        `x_range`. Ascending for shielding (drawn ascending left to right,
        `_to_widget_x`), descending otherwise -- so a caller that walks this
        list in order is walking the plot in order, which is what the
        cumulative integral trace needs to rise in the right direction."""
        low, high = x_range
        if count < 2 or high == low:
            return [low]
        step = (high - low) / (count - 1)
        if self._shielding:
            return [low + step * i for i in range(count)]
        return [high - step * i for i in range(count)]

    def _draw_smooth_curve(
        self, painter: QPainter, plot_rect: QRectF, x_range: tuple[float, float], label_height: float
    ) -> None:
        xs = self._sample_grid(x_range)
        ys = lorentzian_envelope(self._signals, xs, self._frequency_mhz)
        scale = (plot_rect.height() - label_height) / (max(ys) or 1.0)

        painter.setPen(QPen(_PEAK_COLOR, 1))
        painter.drawPath(self._curve_path(xs, ys, plot_rect, x_range, scale))

        highlighted_signals = [
            signal for signal in self._signals if self._highlighted_atoms & set(signal.atom_indices)
        ]
        if highlighted_signals:
            # Drawn on the SAME scale as the full curve (not renormalised to
            # its own peak), because the point is "how much of the total
            # curve is this signal", not "what does this signal look like
            # alone".
            highlighted_ys = lorentzian_envelope(highlighted_signals, xs, self._frequency_mhz)
            painter.setPen(QPen(_HIGHLIGHT_COLOR, 3))
            painter.drawPath(self._curve_path(xs, highlighted_ys, plot_rect, x_range, scale))

    def _draw_integral(
        self, painter: QPainter, plot_rect: QRectF, x_range: tuple[float, float], label_height: float
    ) -> None:
        """A cumulative trace of the same Lorentzian-convolved intensity
        smooth mode draws, rising left to right the way a real integral
        trace does -- available in EITHER render mode, since it needs a
        continuous curve to integrate regardless of how the peaks above it
        are drawn."""
        xs = self._sample_grid(x_range)
        ys = lorentzian_envelope(self._signals, xs, self._frequency_mhz)
        cumulative = [0.0] * len(xs)
        acc = 0.0
        for index in range(1, len(xs)):
            acc += (ys[index] + ys[index - 1]) / 2.0 * abs(xs[index] - xs[index - 1])
            cumulative[index] = acc
        total = cumulative[-1] or 1.0
        scale = (plot_rect.height() - label_height) / total

        painter.setPen(QPen(_INTEGRAL_COLOR, 1.5, Qt.PenStyle.DashLine))
        painter.drawPath(self._curve_path(xs, cumulative, plot_rect, x_range, scale))
        painter.drawText(
            QRectF(plot_rect.left(), plot_rect.top() - label_height, 120, label_height),
            Qt.AlignmentFlag.AlignLeft,
            "relative integral",
        )

    def _curve_path(
        self,
        xs: list[float],
        ys: list[float],
        plot_rect: QRectF,
        x_range: tuple[float, float],
        scale: float,
    ) -> QPainterPath:
        path = QPainterPath()
        for index, (x, y) in enumerate(zip(xs, ys)):
            point = QPointF(self._to_widget_x(x, plot_rect, x_range), plot_rect.bottom() - y * scale)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        return path
