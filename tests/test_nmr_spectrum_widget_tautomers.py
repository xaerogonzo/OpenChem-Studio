"""Tautomer traces drawn over the 1D NMR spectrum (P5, step 4).

Data checks on what the widget says it draws, and PIXEL checks on what it actually paints: a trace can be right in
the data and absent from the screen.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

import conftest
from openchem.chem.tautomer_nmr import TautomerTrace, TracePeak
from openchem.ui.widgets.nmr_spectrum_widget import (
    TAUTOMER_AVERAGE_COLOUR,
    TAUTOMER_TRACE_COLOURS,
    NmrSpectrumWidget,
)


def _trace(key, label, c_peaks=(), h_peaks=(), *, population=None, average=False, failure=""):
    peaks = {}
    if c_peaks or h_peaks:
        peaks = {
            "C": tuple(TracePeak(s, 1.0, i) for i, s in enumerate(c_peaks)),
            "H": tuple(TracePeak(s, w, 100 + i, labile=lab) for i, (s, w, lab) in enumerate(h_peaks)),
        }
    return TautomerTrace(key, label, average, population, None, peaks, failure)


@pytest.fixture
def widget(qapp):
    w = NmrSpectrumWidget()
    w.resize(640, 320)
    yield w
    conftest.dispose(w)


def _image(widget):
    return widget.grab().toImage()


def _near(image, x, colour, *, y0=None, y1=None):
    """How many pixels in column `x` (and its neighbours) are within a small distance of `colour`."""
    target = QColor(colour)
    count = 0
    for xx in (x - 1, x, x + 1):
        for y in range(y0 or 0, y1 or image.height()):
            c = image.pixelColor(int(xx), y)
            if abs(c.red() - target.red()) + abs(c.green() - target.green()) + abs(c.blue() - target.blue()) < 130:
                count += 1
    return count


def test_traces_draw_even_when_the_molecule_has_no_spectrum_of_its_own(widget):
    widget.set_tautomer_traces([_trace("a", "keto", c_peaks=(30.0, 200.0))], "C")
    assert [t.key for t in widget.drawn_tautomer_traces()] == ["a"]
    low, high = widget.view_range()
    assert low < 30.0 and high > 200.0  # the axis covers the traces
    plot = widget._plot_rect()
    image = _image(widget)
    for shift in (30.0, 200.0):
        x = widget._to_widget_x(shift, plot, widget.view_range())
        assert _near(image, int(x), TAUTOMER_TRACE_COLOURS[0]) > 40, shift


def test_each_tautomer_has_its_own_colour_by_position_and_the_average_is_near_black(widget):
    traces = [
        _trace("a", "A", c_peaks=(10.0,)),
        _trace("avg", "Fast-exchange average", c_peaks=(11.0,), average=True),
        _trace("b", "B", c_peaks=(12.0,)),
    ]
    widget.set_tautomer_traces(traces, "C")
    assert widget.tautomer_trace_colour(traces[0]) == TAUTOMER_TRACE_COLOURS[0]
    assert widget.tautomer_trace_colour(traces[2]) == TAUTOMER_TRACE_COLOURS[1]  # the average does not take a slot
    assert widget.tautomer_trace_colour(traces[1]) == TAUTOMER_AVERAGE_COLOUR
    plot, view = widget._plot_rect(), widget.view_range()
    image = _image(widget)
    for trace, colour in zip(traces, (TAUTOMER_TRACE_COLOURS[0], TAUTOMER_AVERAGE_COLOUR, TAUTOMER_TRACE_COLOURS[1])):
        x = widget._to_widget_x(trace.peaks["C"][0].shift_ppm, plot, view)
        assert _near(image, int(x), colour) > 40, trace.label


def test_a_hidden_trace_is_not_drawn_and_not_in_the_legend(widget):
    widget.set_tautomer_traces([_trace("a", "A", c_peaks=(10.0,)), _trace("b", "B", c_peaks=(50.0,))], "C")
    widget.set_show_legend(True)
    widget.set_tautomer_trace_visible("b", False)
    assert [t.key for t in widget.drawn_tautomer_traces()] == ["a"]
    assert [text for _k, text, _c in widget.legend_entries() if _c.startswith("#")] == ["A"]
    plot, view = widget._plot_rect(), widget.view_range()
    assert _near(_image(widget), int(widget._to_widget_x(50.0, plot, view)), TAUTOMER_TRACE_COLOURS[1]) == 0
    widget.set_tautomer_trace_visible("b", True)
    assert [t.key for t in widget.drawn_tautomer_traces()] == ["a", "b"]


def test_the_nucleus_chooses_which_peaks_are_drawn(widget):
    trace = _trace("a", "A", c_peaks=(120.0,), h_peaks=((7.2, 2.0, False),))
    widget.set_tautomer_traces([trace], "H")
    assert widget.view_range()[1] < 20  # the proton axis
    widget.set_tautomer_trace_element("C")
    assert widget.view_range()[1] > 100  # the carbon axis
    with pytest.raises(ValueError):
        widget.set_tautomer_trace_element("N")


def test_a_failed_tautomer_draws_nothing_and_never_raises(widget):
    widget.set_tautomer_traces([_trace("a", "A", failure="ORCA produced no shielding data")], "C")
    assert widget.drawn_tautomer_traces() == []
    _image(widget)  # paints with nothing to draw


def test_traces_are_not_drawn_on_a_shielding_axis(widget):
    widget.set_tautomer_traces([_trace("a", "A", c_peaks=(10.0,))], "C")
    widget._shielding = True  # the same state `set_signals(shielding=True)` leaves
    assert widget.drawn_tautomer_traces() == []


def test_the_legend_names_populations_only_when_a_trace_has_one(widget):
    widget.set_tautomer_traces([
        _trace("a", "keto", c_peaks=(10.0,), population=0.8123),
        _trace("b", "enol", c_peaks=(20.0,)),
        _trace("avg", "Fast-exchange average", c_peaks=(15.0,), average=True),
    ], "C")
    texts = [text for _k, text, c in widget.legend_entries() if c.startswith("#")]
    assert texts == ["keto (81.2%)", "enol", "Fast-exchange average"]


def test_a_labile_hydrogen_is_dashed_and_a_carbon_hydrogen_is_solid(widget):
    widget.set_tautomer_traces([_trace("a", "A", h_peaks=((2.0, 3.0, False), (9.0, 3.0, True)))], "H")
    plot, view = widget._plot_rect(), widget.view_range()
    image = _image(widget)
    colour = TAUTOMER_TRACE_COLOURS[0]
    solid = _near(image, int(widget._to_widget_x(2.0, plot, view)), colour)
    dashed = _near(image, int(widget._to_widget_x(9.0, plot, view)), colour)
    assert solid > 0 and dashed > 0 and dashed < solid * 0.8  # same height, dashed has gaps


def test_stick_height_is_the_hydrogen_count_on_one_scale(widget):
    widget.set_tautomer_traces([_trace("a", "A", h_peaks=((2.0, 3.0, False), (6.0, 1.0, False)))], "H")
    plot, view = widget._plot_rect(), widget.view_range()
    image = _image(widget)
    tall = _near(image, int(widget._to_widget_x(2.0, plot, view)), TAUTOMER_TRACE_COLOURS[0])
    short = _near(image, int(widget._to_widget_x(6.0, plot, view)), TAUTOMER_TRACE_COLOURS[0])
    assert tall == pytest.approx(3 * short, rel=0.15)


def test_clearing_removes_the_traces_and_their_legend_entries(widget):
    widget.set_tautomer_traces([_trace("a", "A", c_peaks=(10.0,))], "C")
    widget.clear_tautomer_traces()
    assert widget.tautomer_traces() == [] and widget.drawn_tautomer_traces() == []
    assert not any(c.startswith("#") for _k, _t, c in widget.legend_entries())
