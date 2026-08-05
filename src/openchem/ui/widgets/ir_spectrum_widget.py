from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openchem.domain.scientific_result import VibrationalMode

_AXIS_COLOR = QColor(120, 120, 120)
_PEAK_COLOR = QColor(30, 100, 200)
_HIGHLIGHT_COLOR = QColor(214, 100, 20)
#: IR-silent modes are drawn in this, at a fixed stub height -- see
#: `_SILENT_STUB_HEIGHT` for why they are drawn at all.
_SILENT_COLOR = QColor(150, 150, 150)
#: The imaginary-frequency banner. Red because the statement it makes is
#: "the thermochemistry from this job is meaningless", not "heads up".
_WARNING_COLOR = QColor(200, 40, 40)

#: Half-width of a peak's clickable region, in pixels -- same reasoning as
#: `NmrSpectrumWidget`: a 1px stick is not hittable with a mouse, and two
#: modes of a degenerate pair can share a wavenumber to the printed digit
#: (methane's two n2 bends come back at 1530.8 and 1530.9). First match
#: wins, deterministically ordered by wavenumber.
_HIT_HALF_WIDTH = 6.0

#: Pixels of stick drawn for a mode whose IR intensity is exactly zero.
#: A real IR spectrum shows nothing there, but this plot doubles as the
#: mode list, and "no mode at this wavenumber" and "a mode that symmetry
#: forbids from absorbing" are different facts. The benchmark turns on
#: exactly that distinction -- CO2's symmetric stretch, methane's v1 and
#: v2, and 20 of benzene's 30 modes all come back at exactly 0.00, and
#: that agreement with group theory is the evidence the intensity column
#: is being read correctly. Drawing them flush with the axis would hide
#: the thing that was verified.
_SILENT_STUB_HEIGHT = 4.0


class IrSpectrumWidget(QWidget):
    """A harmonic IR stick spectrum -- hand-rolled `QPainter`, the same
    approach `NmrSpectrumWidget` takes, and deliberately its sibling: the
    axis/peak/hit-region structure below is that widget's, with the two
    conventions that differ for IR changed and commented.

    WAVENUMBER DESCENDING LEFT-TO-RIGHT. Every published IR spectrum is
    drawn with 4000 cm-1 at the left and the fingerprint region at the
    right, and a chemist reads band positions by eye against that habit.
    `NmrSpectrumWidget` descends too (high ppm left), so this is the same
    `_to_widget_x` in both -- the shared convention, not a coincidence.

    ABSORBANCE, NOT TRANSMITTANCE, AND THAT IS A MEASURED CHOICE RATHER
    THAN A STYLISTIC ONE. Experimental IR is conventionally published as
    transmittance -- peaks pointing DOWN from a 100% baseline -- and that
    is the more familiar picture. It is not available here. ORCA computes
    an integrated absorption intensity in km/mol; converting that to
    transmittance requires Beer-Lambert, T = 10^(-epsilon*c*l), and the
    path length `l` and concentration `c` are properties of a sample that
    was never prepared. Choosing them would put a y-axis on the plot that
    looks calibrated and is invented, which is the specific failure this
    project refuses elsewhere (the NMR view has no "prediction quality"
    column for the same reason). So the y-axis is the quantity actually
    computed, labelled with its real units, and peaks point up.

    IMAGINARY MODES ARE NEVER DRAWN AS PEAKS. A negative wavenumber is not
    a band at a negative position; it is the finding that the geometry is
    a saddle point rather than a minimum, which invalidates every
    thermochemistry number from the same job. Plotting one would place a
    fictitious band on the axis and, worse, imply the spectrum is
    trustworthy. They are excluded from the peak loop and reported in the
    banner instead -- which is also why the banner is drawn before the
    early return for an empty spectrum, since a structure whose only modes
    are imaginary must still say so.
    """

    #: Emits the index into `modes` of the clicked mode.
    mode_clicked = Signal(int)

    _MARGIN = 50.0

    def __init__(
        self,
        modes: list[VibrationalMode] | tuple[VibrationalMode, ...] | None = None,
        imaginary_warning: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._modes: list[VibrationalMode] = list(modes or [])
        self._imaginary_warning = imaginary_warning
        self._highlighted: set[int] = set()
        self._x_label = "Wavenumber (cm⁻¹)"
        self.setMinimumSize(320, 200)

    def set_modes(
        self,
        modes: list[VibrationalMode] | tuple[VibrationalMode, ...],
        imaginary_warning: str = "",
    ) -> None:
        self._modes = list(modes)
        self._imaginary_warning = imaginary_warning
        self._highlighted.clear()
        self.update()

    def set_highlighted_modes(self, indices: list[int]) -> None:
        """Highlights modes by index -- the inbound half of the link, so
        selecting a row in a mode table marks its band here."""
        self._highlighted = set(indices)
        self.update()

    def _real_modes(self) -> list[tuple[int, VibrationalMode]]:
        """Plottable modes, carrying their index into `self._modes`.

        The index is carried rather than recomputed so `mode_clicked`
        reports a position in the FULL mode list. Filtering first and
        emitting the filtered index would silently renumber every mode
        after an imaginary one, which is exactly the case where a caller
        most needs the right index.
        """
        return [
            (index, mode)
            for index, mode in enumerate(self._modes)
            if not mode.is_imaginary
        ]

    @staticmethod
    def _intensity(mode: VibrationalMode) -> float:
        """Intensity as a number, treating "not reported" as zero.

        `ir_intensity_km_mol` is None when ORCA's IR SPECTRUM table had no
        row for the mode. That is not the same as a measured zero, but for
        a bar height there is nothing else to draw; the distinction is
        preserved in the mode list and tooltips, not here.
        """
        return float(mode.ir_intensity_km_mol or 0.0)

    def _axis_range(self) -> tuple[float, float]:
        real = self._real_modes()
        if not real:
            return 0.0, 1.0
        numbers = [mode.wavenumber_cm1 for _, mode in real]
        low, high = min(numbers), max(numbers)
        if low == high:
            low, high = low - 50.0, high + 50.0
        padding = (high - low) * 0.1
        return low - padding, high + padding

    def _plot_rect(self) -> QRectF:
        # Top margin is a full _MARGIN rather than the NMR widget's half,
        # to leave room for the imaginary-frequency banner above the plot.
        return QRectF(
            self._MARGIN,
            self._MARGIN,
            max(self.width() - 1.5 * self._MARGIN, 1.0),
            max(self.height() - 2.0 * self._MARGIN, 1.0),
        )

    def _to_widget_x(
        self, wavenumber: float, plot_rect: QRectF, x_range: tuple[float, float]
    ) -> float:
        low, high = x_range
        # Descending: the HIGH wavenumber maps to the LEFT edge.
        fraction = (high - wavenumber) / (high - low) if high != low else 0.5
        return plot_rect.left() + fraction * plot_rect.width()

    def hit_regions(self) -> list[tuple[QRectF, int]]:
        """Clickable region per plotted mode, paired with its index into
        `modes`. Derived from geometry rather than recorded during
        `paintEvent`, so a click resolves before the first paint and is
        testable without one -- `NmrSpectrumWidget.hit_regions` for the
        same reason."""
        real = self._real_modes()
        if not real:
            return []
        plot_rect = self._plot_rect()
        x_range = self._axis_range()
        regions = []
        for index, mode in real:
            x = self._to_widget_x(mode.wavenumber_cm1, plot_rect, x_range)
            regions.append(
                (
                    QRectF(
                        x - _HIT_HALF_WIDTH,
                        plot_rect.top(),
                        2 * _HIT_HALF_WIDTH,
                        plot_rect.height(),
                    ),
                    index,
                )
            )
        return regions

    def mode_at(self, x: float, y: float) -> int | None:
        for region, index in self.hit_regions():
            if region.contains(x, y):
                return index
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        position = event.position()
        index = self.mode_at(position.x(), position.y())
        if index is not None:
            self._highlighted = {index}
            self.update()
            self.mode_clicked.emit(index)
        super().mousePressEvent(event)

    def _draw_imaginary_banner(self, painter: QPainter) -> None:
        if not self._imaginary_warning:
            return
        painter.setPen(QPen(_WARNING_COLOR))
        painter.drawText(
            QRectF(0, 0, self.width(), self._MARGIN),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self._imaginary_warning,
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

        # Before the empty-spectrum return: a geometry whose only modes are
        # imaginary has nothing to plot and the most to say.
        self._draw_imaginary_banner(painter)

        real = self._real_modes()
        if not real:
            painter.end()
            return

        x_range = self._axis_range()
        painter.setPen(QPen(_AXIS_COLOR))
        # Left label is the HIGH wavenumber, right the low -- the axis runs
        # backwards, and printing them the other way round would silently
        # mirror the reader's interpretation of every band.
        painter.drawText(
            QRectF(plot_rect.left(), plot_rect.bottom(), 70, self._MARGIN / 2),
            Qt.AlignmentFlag.AlignLeft,
            f"{x_range[1]:.0f}",
        )
        painter.drawText(
            QRectF(plot_rect.right() - 70, plot_rect.bottom(), 70, self._MARGIN / 2),
            Qt.AlignmentFlag.AlignRight,
            f"{x_range[0]:.0f}",
        )

        intensities = [self._intensity(mode) for _, mode in real]
        strongest = max(intensities) if intensities else 0.0
        label_height = 14.0
        # A spectrum in which every band is symmetry-forbidden (or in which
        # no intensities were reported at all) would divide by zero here.
        # Every stick then draws at the silent stub height, which is the
        # honest picture: modes exist, none of them absorb.
        scale = strongest if strongest > 0.0 else 0.0

        painter.setPen(QPen(_AXIS_COLOR))
        painter.drawText(
            QRectF(plot_rect.left(), plot_rect.top() - label_height, 200, label_height),
            Qt.AlignmentFlag.AlignLeft,
            f"max {strongest:.1f} km/mol" if strongest > 0 else "all bands IR-silent",
        )

        for index, mode in real:
            intensity = self._intensity(mode)
            highlighted = index in self._highlighted
            silent = intensity <= 0.0
            if scale > 0.0 and not silent:
                height = (plot_rect.height() - label_height) * (intensity / scale)
            else:
                height = _SILENT_STUB_HEIGHT
            if highlighted:
                colour, width = _HIGHLIGHT_COLOR, 3
            elif silent:
                colour, width = _SILENT_COLOR, 1
            else:
                colour, width = _PEAK_COLOR, 1
            painter.setPen(QPen(colour, width))
            x = self._to_widget_x(mode.wavenumber_cm1, plot_rect, x_range)
            painter.drawLine(
                QRectF(x, plot_rect.bottom() - height, 0, height).topLeft(),
                QRectF(x, plot_rect.bottom() - height, 0, height).bottomLeft(),
            )
            # Only bands with some real height are labelled. Labelling
            # every mode turns benzene's 30 into unreadable overlap, and
            # the ones worth reading off a spectrum are the ones that
            # absorb. The character goes on the label because "1746 cm-1"
            # and "1746 cm-1 stretch" are different amounts of help.
            if not silent and height > label_height * 1.5:
                caption = f"{mode.wavenumber_cm1:.0f}"
                if mode.character:
                    caption += f" {mode.character}"
                painter.drawText(
                    QRectF(x - 45, plot_rect.bottom() - height - label_height, 90, label_height),
                    Qt.AlignmentFlag.AlignCenter,
                    caption,
                )
        painter.end()
