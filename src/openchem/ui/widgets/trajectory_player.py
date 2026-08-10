"""Watch a trajectory: the frames, in order, with the energy underneath.

**A TRAJECTORY HAD NO VIEW AT ALL.** `molecular_dynamics` computed 101
frames and `_RESULT_VIEW_FACTORIES` had no entry for a
`TrajectoryResult`, so the inspector fell back to the single-molecule
2D+3D view -- which would have depicted the INPUT and none of the
result. The Properties panel therefore opened nothing on purpose, and
`docs/NAVIGATION_AUDIT.md` recorded it as the one gap in that sweep that
was a real build rather than a rearrangement. This is that build.

**A 2D depiction would have been the cheap answer and a wrong one.**
Molecular dynamics moves atoms; it does not change what is bonded to
what. Every frame of a vacuum MD run has identical connectivity, so a
grid of 2D structures shows 101 copies of the same picture and reads as
"the calculator produced nothing" -- the exact failure this whole line of
work has been unwinding. The motion is only visible in 3D.

The backend is INJECTABLE for the reason `ir_view_widget` and
`nmr_view_widget` make theirs injectable: the real one is a
`QWebEngineView`, and a test that does not need Chromium should not start
Chromium. See CLAUDE.md on what those processes cost when they
accumulate.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from openchem.domain.scientific_result import TrajectoryResult
from openchem.ui.viewer_backend import ViewerBackend

#: Milliseconds between frames while playing. 80 ms is ~12 fps, which is
#: fast enough to read as motion and slow enough that a 101-frame run
#: takes eight seconds rather than flashing past.
_FRAME_INTERVAL_MS = 80

_TRACE_COLOUR = QColor("#3aa0e0")
_MARKER_COLOUR = QColor("#e8546b")
_AXIS_COLOUR = QColor("#999999")
_MUTED = "color: #666666;"


class EnergyTrace(QWidget):
    """Energy against frame, with a marker on the frame being shown.

    Purpose-built rather than reusing `PhCurveWidget`, which is typed to
    a `PhCurveResult` and emits `ph_hovered`. Feeding femtoseconds
    through a field called `ph_values` would be correct arithmetic on the
    wrong object -- the shape of bug this codebase has already paid for
    in the crystal click and the Ketcher pool ids -- and the widget would
    tell every future reader that time is pH.
    """

    #: A frame the user clicked, so the trace is a way to NAVIGATE rather
    #: than only to read. An energy spike is the thing somebody wants to
    #: look at, and making them find it again on the slider is busywork.
    frame_picked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._energies: list[float] = []
        self._frame = 0
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_energies(self, energies: Sequence[float]) -> None:
        self._energies = list(energies)
        self.update()

    def set_frame(self, frame: int) -> None:
        self._frame = frame
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(4, 4, -4, -4)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())

        rect = self._plot_rect()
        painter.setPen(QPen(_AXIS_COLOUR, 1))
        painter.drawRect(rect)

        if len(self._energies) < 2:
            painter.end()
            return

        low = min(self._energies)
        high = max(self._energies)
        # A FLAT trace is a real result -- a well-equilibrated run barely
        # moves -- so it is drawn as a flat line down the middle rather
        # than divided by a zero span.
        span = (high - low) or 1.0
        count = len(self._energies)

        def point(index: int, value: float) -> tuple[float, float]:
            x = rect.left() + rect.width() * index / (count - 1)
            y = rect.bottom() - rect.height() * (value - low) / span
            return x, y

        painter.setPen(QPen(_TRACE_COLOUR, 1.5))
        previous = point(0, self._energies[0])
        for index in range(1, count):
            current = point(index, self._energies[index])
            painter.drawLine(previous[0], previous[1], current[0], current[1])
            previous = current

        if 0 <= self._frame < count:
            x, _y = point(self._frame, self._energies[self._frame])
            painter.setPen(QPen(_MARKER_COLOUR, 1.5))
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override naming
        if len(self._energies) < 2:
            return
        rect = self._plot_rect()
        if rect.width() <= 0:
            return
        fraction = (event.position().x() - rect.left()) / rect.width()
        frame = round(fraction * (len(self._energies) - 1))
        self.frame_picked.emit(max(0, min(len(self._energies) - 1, frame)))


class TrajectoryPlayerWidget(QWidget):
    """One trajectory: a 3D frame, a scrubber, and the energy trace."""

    def __init__(
        self,
        result: TrajectoryResult,
        backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._frames = list(result.frames)
        self._frame = 0

        if backend is None:
            from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

            backend = Mol3DViewerBackend(self)
        self._backend = backend

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(result.name, self))
        layout.addWidget(self._backend.widget(), 1)

        # EMPTY STATE FIRST, because a player with no frames is a real
        # outcome (a run that produced nothing) and the controls below
        # would otherwise be a row of dead buttons. Two sentences, the
        # second one naming what would fill the space.
        if not self._frames:
            message = QLabel(
                "This run produced no frames.\n"
                "Run Molecular Dynamics again with more steps to fill this in.",
                self,
            )
            message.setStyleSheet(_MUTED)
            message.setWordWrap(True)
            layout.addWidget(message)
            self._slider = None
            self._play_button = None
            self._timer = None
            self._readout = None
            self._trace = None
            return

        self._trace = EnergyTrace(self)
        self._trace.set_energies(result.energies)
        self._trace.frame_picked.connect(self.show_frame)
        # Hidden rather than absent when there are no energies: the row of
        # controls below keeps its position, so a trajectory with energies
        # and one without do not lay out differently.
        self._trace.setVisible(bool(result.energies))
        layout.addWidget(self._trace)

        controls = QHBoxLayout()
        self._play_button = QPushButton("Play", self)
        self._play_button.setToolTip("Step through the frames in order.")
        self._play_button.clicked.connect(self._on_play_clicked)
        controls.addWidget(self._play_button)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setMinimum(0)
        self._slider.setMaximum(len(self._frames) - 1)
        self._slider.valueChanged.connect(self.show_frame)
        controls.addWidget(self._slider, 1)
        layout.addLayout(controls)

        self._readout = QLabel(self)
        self._readout.setStyleSheet(_MUTED)
        layout.addWidget(self._readout)

        # PARENTED TO self, so Qt stops it when this widget is destroyed.
        # A timer outliving its widget fires a bound method on a dead
        # object, which is the access-violation shape CLAUDE.md documents
        # at length. A BOUND METHOD, never a lambda capturing self.
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

        self.show_frame(0)

    # --- state ----------------------------------------------------------

    def frame_count(self) -> int:
        return len(self._frames)

    def current_frame(self) -> int:
        return self._frame

    def is_playing(self) -> bool:
        return self._timer is not None and self._timer.isActive()

    # --- playback -------------------------------------------------------

    def show_frame(self, index: int) -> None:
        """Put frame `index` in the viewer, and say which one it is."""
        if not self._frames:
            return
        index = max(0, min(len(self._frames) - 1, int(index)))
        self._frame = index
        self._backend.load_conformer(self._frames[index])
        if self._slider is not None and self._slider.value() != index:
            # SIGNALS BLOCKED, not merely value-guarded. `setValue`
            # emits `valueChanged`, which re-enters this method; the
            # value guard stops it recursing but the nested call still
            # reaches `load_conformer`, so EVERY frame was loaded twice
            # -- doubling the JavaScript calls at twelve frames a second.
            # Caught because the test's frames are distinguishable; a
            # fixture of identical frames would have shown nothing.
            blocked = self._slider.blockSignals(True)
            self._slider.setValue(index)
            self._slider.blockSignals(blocked)
        if self._trace is not None:
            self._trace.set_frame(index)
        if self._readout is not None:
            self._readout.setText(self._describe(index))

    def _describe(self, index: int) -> str:
        parts = [f"Frame {index + 1} of {len(self._frames)}"]
        times = self._result.times
        if index < len(times):
            parts.append(f"{times[index]:.0f} fs")
        energies = self._result.energies
        if index < len(energies):
            parts.append(f"{energies[index]:.2f} kcal/mol")
        # MIDDLE DOT, not an em dash: these strings are read back through
        # Windows console streams elsewhere in this app and a codepoint
        # outside cp1252 raises there. U+00B7 is inside it.
        return " · ".join(parts)

    def _on_play_clicked(self, _checked: bool = False) -> None:
        self.toggle_play()

    def toggle_play(self) -> None:
        if self._timer is None or self._play_button is None:
            return
        if self._timer.isActive():
            self._timer.stop()
            self._play_button.setText("Play")
        else:
            self._timer.start()
            self._play_button.setText("Pause")

    def _advance(self) -> None:
        """Next frame, wrapping at the end.

        LOOPS rather than stopping. A trajectory is a cycle of motion and
        the interesting thing is usually the repeat; stopping at the last
        frame means re-pressing Play to see it again, and the Pause button
        is right there.
        """
        if not self._frames:
            return
        self.show_frame((self._frame + 1) % len(self._frames))
