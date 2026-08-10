"""The trajectory player: frames in order, and the energy underneath.

`molecular_dynamics` computed 101 frames and had NO VIEW -- the inspector
would have fallen back to the single-molecule 2D+3D view and depicted the
input, so the panel opened nothing at all. Recorded as the one gap in
`docs/NAVIGATION_AUDIT.md` that was a real build.

**The backend is injected**, so none of this starts Chromium. The real
one is a `QWebEngineView` and CLAUDE.md documents at length what those
cost when a suite accumulates them; the widget takes a `ViewerBackend`
for the same reason `ir_view_widget` and `nmr_view_widget` do.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QWidget

from openchem.domain.common import Provenance
from openchem.domain.scientific_result import TrajectoryResult
from openchem.ui.widgets.trajectory_player import EnergyTrace, TrajectoryPlayerWidget

from conftest import ink, painted


class _RecordingBackend:
    """Records what it was asked to show. No web engine involved."""

    def __init__(self) -> None:
        self.loaded: list[str] = []
        self._widget = QWidget()

    def load_conformer(self, molblock: str) -> None:
        self.loaded.append(molblock)

    def set_style(self, style: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def widget(self) -> QWidget:
        return self._widget


def _trajectory(frames: int = 5, *, energies: bool = True) -> TrajectoryResult:
    return TrajectoryResult(
        trajectory_id="molecular_dynamics",
        name="Vacuum MD (MMFF94)",
        method="rdkit-mmff",
        molecule_uuid="mol-1",
        # Distinguishable frames, so "which one is on screen" is a
        # question the test can actually answer.
        frames=[f"FRAME-{n}" for n in range(frames)],
        times=[float(n * 10) for n in range(frames)],
        energies=[float(n) for n in range(frames)] if energies else [],
        provenance=Provenance(created_by="core", method="test"),
    )


@pytest.fixture
def player(qapp):
    built: list[TrajectoryPlayerWidget] = []

    def make(result: TrajectoryResult, backend=None) -> TrajectoryPlayerWidget:
        widget = TrajectoryPlayerWidget(result, backend=backend or _RecordingBackend())
        built.append(widget)
        return widget

    yield make
    for widget in built:
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


# --- the frames ---------------------------------------------------------


def test_the_first_frame_is_shown_without_being_asked(player):
    backend = _RecordingBackend()
    player(_trajectory(), backend)

    assert backend.loaded == ["FRAME-0"]


def test_scrubbing_loads_that_frame(player):
    backend = _RecordingBackend()
    widget = player(_trajectory(), backend)

    widget.show_frame(3)

    assert widget.current_frame() == 3
    assert backend.loaded[-1] == "FRAME-3"


def test_playing_advances_through_the_frames(player):
    """The frames are DISTINCT, so this cannot pass by reloading frame 0
    five times -- which is what a wrong index would do."""
    backend = _RecordingBackend()
    widget = player(_trajectory(), backend)

    for _ in range(4):
        widget._advance()

    assert backend.loaded == ["FRAME-0", "FRAME-1", "FRAME-2", "FRAME-3", "FRAME-4"]


def test_playing_wraps_at_the_end_rather_than_stopping(player):
    widget = player(_trajectory(frames=3))

    for _ in range(3):
        widget._advance()

    assert widget.current_frame() == 0


def test_play_toggles_and_says_which_it_will_do(player):
    widget = player(_trajectory())
    assert not widget.is_playing()

    widget.toggle_play()
    assert widget.is_playing()
    assert widget._play_button.text() == "Pause"

    widget.toggle_play()
    assert not widget.is_playing()
    assert widget._play_button.text() == "Play"


def test_the_slider_and_the_frame_stay_in_step(player):
    """`setValue` re-emits `valueChanged`, so the guard against the
    slider and `show_frame` calling each other is load-bearing. Without
    it this recurses."""
    widget = player(_trajectory())

    widget._slider.setValue(4)
    assert widget.current_frame() == 4

    widget.show_frame(1)
    assert widget._slider.value() == 1


def test_an_out_of_range_frame_is_clamped_not_crashed(player):
    widget = player(_trajectory(frames=3))

    widget.show_frame(99)
    assert widget.current_frame() == 2

    widget.show_frame(-5)
    assert widget.current_frame() == 0


# --- the readout --------------------------------------------------------


def test_the_readout_names_the_frame_time_and_energy(player):
    widget = player(_trajectory())

    widget.show_frame(2)

    text = widget._readout.text()
    assert "Frame 3 of 5" in text
    assert "20 fs" in text
    assert "2.00 kcal/mol" in text


def test_the_readout_stays_inside_cp1252(player):
    """These strings reach Windows console streams elsewhere in the app,
    where a codepoint outside cp1252 RAISES -- recorded three times in
    one session in regulatory/calculator.py. U+00B7 is inside it; an em
    dash and a proper minus sign are not."""
    widget = player(_trajectory())
    widget.show_frame(1)

    widget._readout.text().encode("cp1252")


def test_a_trajectory_without_energies_still_plays(player):
    """`energies` is optional on the result. The trace hides rather than
    dividing by an empty range, and the readout simply says less."""
    backend = _RecordingBackend()
    widget = player(_trajectory(energies=False), backend)

    widget.show_frame(2)

    assert backend.loaded[-1] == "FRAME-2"
    assert widget._trace.isHidden()
    assert "kcal/mol" not in widget._readout.text()


# --- the empty state ----------------------------------------------------


def test_a_run_with_no_frames_says_so_and_offers_the_next_step(player):
    """"An empty state is two sentences, and the second one is the
    point." A row of dead controls would be the alternative."""
    widget = player(_trajectory(frames=0))
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in widget.findChildren(QLabel))

    assert "no frames" in text.lower()
    assert "again" in text.lower()
    assert widget.frame_count() == 0


def test_an_empty_trajectory_does_not_build_dead_controls(player):
    widget = player(_trajectory(frames=0))

    assert widget._slider is None
    assert widget._play_button is None
    assert widget._timer is None


# --- the energy trace ---------------------------------------------------


def test_the_trace_draws_the_energies(qapp):
    """AXES HELD FIXED, CONTENT VARIED -- the technique CLAUDE.md records
    after two plausible ink checks were killed by mutation testing.

    Both traces share their extreme values, so the frame, the box and the
    range are pixel-identical and the only thing that can differ is the
    line itself.
    """
    flat = EnergyTrace()
    flat.set_energies([0.0, 5.0, 0.0, 5.0, 0.0])
    spiky = EnergyTrace()
    spiky.set_energies([0.0, 5.0, 2.5, 5.0, 0.0])

    assert ink(flat) != ink(spiky)


def test_an_empty_trace_still_draws_its_frame_but_no_line(qapp):
    """The control for the test above: a trace with nothing in it must
    ink LESS than one with data, or "it drew something" is measuring the
    box rather than the trace."""
    empty = EnergyTrace()
    empty.set_energies([])
    filled = EnergyTrace()
    filled.set_energies([0.0, 5.0, 1.0, 4.0, 0.0])

    assert ink(empty) < ink(filled)


def test_the_trace_marks_the_frame_being_shown(qapp):
    """The marker is the only difference between these two, so if it were
    not drawn the counts would match."""
    left = EnergyTrace()
    left.set_energies([0.0, 5.0, 1.0, 4.0, 0.0])
    left.set_frame(0)
    middle = EnergyTrace()
    middle.set_energies([0.0, 5.0, 1.0, 4.0, 0.0])
    middle.set_frame(2)

    assert painted(left) != painted(middle)


def test_clicking_the_trace_picks_that_frame(qapp):
    """The trace navigates as well as reads -- an energy spike is the
    thing somebody wants to look at, and making them find it again on the
    slider is busywork."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    trace = EnergyTrace()
    trace.set_energies([float(n) for n in range(11)])
    trace.resize(200, 64)
    picked: list[int] = []
    trace.frame_picked.connect(picked.append)

    # Right-hand edge of the plot area -> the last frame.
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(196, 30),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    trace.mousePressEvent(event)

    assert picked == [10]
