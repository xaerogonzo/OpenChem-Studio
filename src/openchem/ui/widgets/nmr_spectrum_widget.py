from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.chem.nmr_signals import (
    DEFAULT_FREQUENCY_MHZ,
    RESIDUAL_SOLVENT_PEAKS,
    NMRSignal,
    multiplet_lines,
)

_AXIS_COLOR = QColor(120, 120, 120)
_PEAK_COLOR = QColor(30, 100, 200)
_HIGHLIGHT_COLOR = QColor(214, 100, 20)
_SOLVENT_COLOR = QColor(150, 150, 150)
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
        self._highlighted_atoms: set[int] = set()
        self._frequency_mhz = DEFAULT_FREQUENCY_MHZ
        self._solvent: str | None = None
        self._element = "H"
        self.setMinimumSize(320, 200)

    def set_signals(self, signals: list[NMRSignal], x_label: str = "δ (ppm)") -> None:
        self._signals = list(signals)
        self._x_label = x_label
        self._element = signals[0].element if signals else "H"
        self._highlighted_atoms.clear()
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
        if not self._solvent:
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
        painter.end()
