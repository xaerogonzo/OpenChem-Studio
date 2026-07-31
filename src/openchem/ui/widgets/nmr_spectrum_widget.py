from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.chem.nmr_signals import NMRSignal

_AXIS_COLOR = QColor(120, 120, 120)
_PEAK_COLOR = QColor(30, 100, 200)
_HIGHLIGHT_COLOR = QColor(214, 100, 20)
# Half-width of a peak's clickable region, in pixels. Peaks are drawn as
# 1px vertical lines, which is far too thin to hit with a mouse -- and two
# diastereotopic protons can share a shift exactly (the predictor splits the
# signal without distinguishing the values), so the regions do sometimes
# overlap; the first match wins, deterministically ordered by shift.
_HIT_HALF_WIDTH = 6.0


class NmrSpectrumWidget(QWidget):
    """A 1D NMR peak spectrum -- hand-rolled `QPainter`, no charting
    dependency, the same approach `NmrCorrelationPlotWidget` uses for the 2D
    correlation scatter plots.

    Peaks are vertical lines at each signal's shift, scaled by integration,
    on a descending-ppm axis (NMR convention: high shift on the left).
    Explicitly NOT a simulated spectrum: no Lorentzian line shape, no
    line-splitting from coupling constants, no baseline noise. The stick
    height means "this many nuclei" and nothing more.

    Clicking a peak emits `peak_clicked` with that signal's `atom_indices`,
    which is what drives highlighting in the structure views.
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
        self._highlighted_atoms: set[int] = set()
        self.setMinimumSize(320, 200)

    def set_signals(self, signals: list[NMRSignal], x_label: str = "δ (ppm)") -> None:
        self._signals = list(signals)
        self._x_label = x_label
        self._highlighted_atoms.clear()
        self.update()

    def set_highlighted_atoms(self, atom_indices: list[int]) -> None:
        """Highlights every peak owning any of these atoms — the inbound half
        of the bidirectional link (a 3D atom click selects its signal)."""
        self._highlighted_atoms = set(atom_indices)
        self.update()

    def _axis_range(self) -> tuple[float, float]:
        if not self._signals:
            return 0.0, 1.0
        shifts = [signal.shift for signal in self._signals]
        low, high = min(shifts), max(shifts)
        # A single peak (or several at one shift) would otherwise be a
        # zero-width axis; pad it into a real range.
        if low == high:
            low, high = low - 1.0, high + 1.0
        padding = (high - low) * 0.1
        return low - padding, high + padding

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
        # spectrum is drawn (and NmrCorrelationPlotWidget's axes).
        fraction = (high - shift) / (high - low) if high != low else 0.5
        return plot_rect.left() + fraction * plot_rect.width()

    def hit_regions(self) -> list[tuple[QRectF, NMRSignal]]:
        """Clickable region per peak. Derived from geometry rather than
        recorded during `paintEvent`, so a click resolves correctly even
        before the first paint (and so it is testable without a repaint)."""
        if not self._signals:
            return []
        plot_rect = self._plot_rect()
        x_range = self._axis_range()
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

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        position = event.position()
        signal = self.signal_at(position.x(), position.y())
        if signal is not None:
            self._highlighted_atoms = set(signal.atom_indices)
            self.update()
            self.peak_clicked.emit(list(signal.atom_indices))
        super().mousePressEvent(event)

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

        x_range = self._axis_range()
        painter.drawText(
            QRectF(plot_rect.left(), plot_rect.bottom(), 60, self._MARGIN / 2),
            Qt.AlignmentFlag.AlignLeft,
            f"{x_range[1]:.1f}",
        )
        painter.drawText(
            QRectF(plot_rect.right() - 60, plot_rect.bottom(), 60, self._MARGIN / 2),
            Qt.AlignmentFlag.AlignRight,
            f"{x_range[0]:.1f}",
        )

        # Tallest peak fills the plot area; everything else is proportional
        # to its integration, so relative peak heights ARE relative proton
        # counts and nothing else.
        max_integration = max(signal.integration for signal in self._signals) or 1
        label_height = 14.0
        for signal in self._signals:
            highlighted = bool(self._highlighted_atoms & set(signal.atom_indices))
            x = self._to_widget_x(signal.shift, plot_rect, x_range)
            height = (plot_rect.height() - label_height) * (signal.integration / max_integration)
            top = plot_rect.bottom() - height
            painter.setPen(QPen(_HIGHLIGHT_COLOR if highlighted else _PEAK_COLOR, 3 if highlighted else 1))
            painter.drawLine(QRectF(x, top, 0, height).topLeft(), QRectF(x, top, 0, height).bottomLeft())
            painter.drawText(
                QRectF(x - 30, top - label_height, 60, label_height),
                Qt.AlignmentFlag.AlignCenter,
                f"{signal.shift:.2f}",
            )
        painter.end()
