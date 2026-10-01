"""Pure zoom/pan arithmetic, tested on constructed numbers.

No QApplication and no widget: these are pure functions over `(low, high)`
windows, which is the whole reason they were worth extracting out of
`NmrCorrelationPlotWidget`. The widgets that use them (that one, and
`NmrSpectrumWidget`) are tested separately, where a paint and a real event
can actually happen.
"""

from __future__ import annotations

import pytest

from openchem.ui.widgets.plot_zoom import drift, is_full_span, panned_window, zoomed_window


# --- zoomed_window -----------------------------------------------------


def test_zooming_in_narrows_the_span():
    low, high = zoomed_window((0.0, 10.0), (0.0, 10.0), anchor=5.0, factor=0.5, min_fraction=0.02)
    assert (high - low) == pytest.approx(5.0)
    assert (low, high) == pytest.approx((2.5, 7.5))


def test_the_anchor_keeps_its_fractional_position_off_centre():
    """A non-centred anchor is the real test of "stays under the cursor"
    -- a centred one would pass even with the fraction formula backwards."""
    old_fraction = (10.0 - 8.0) / 10.0  # distance from the high end
    low, high = zoomed_window((0.0, 10.0), (0.0, 10.0), anchor=8.0, factor=0.5, min_fraction=0.02)
    new_fraction = (high - 8.0) / (high - low)
    assert new_fraction == pytest.approx(old_fraction)


def test_zoom_is_direction_symmetric():
    """The whole reason `zoomed_window` has no `descending` parameter --
    see its docstring. Computed two ways (from the high end and from the
    low end) must land on the same window."""
    full = (0.0, 10.0)
    anchor = 3.0
    from_high = zoomed_window((0.0, 10.0), full, anchor, factor=0.4, min_fraction=0.02)

    # Re-derive the same result via the "distance from the low end"
    # fraction directly, independent of the function under test.
    old_span = 10.0
    new_span = old_span * 0.4
    fraction_from_low = (anchor - 0.0) / old_span
    expected_low = anchor - fraction_from_low * new_span
    expected_high = expected_low + new_span

    assert from_high == pytest.approx((expected_low, expected_high))


def test_zoom_clamps_to_the_minimum_fraction_of_the_full_span():
    low, high = zoomed_window((0.0, 10.0), (0.0, 10.0), anchor=5.0, factor=0.0001, min_fraction=0.1)
    assert (high - low) == pytest.approx(1.0)  # 10% of the full 10-wide span


def test_zoom_clamps_to_the_full_span_when_zooming_out_past_it():
    low, high = zoomed_window((4.0, 6.0), (0.0, 10.0), anchor=5.0, factor=100.0, min_fraction=0.02)
    assert (low, high) == pytest.approx((0.0, 10.0))


def test_a_zero_width_window_is_returned_unchanged():
    assert zoomed_window((5.0, 5.0), (0.0, 10.0), anchor=5.0, factor=0.5, min_fraction=0.02) == (5.0, 5.0)


def test_a_zero_width_full_range_is_returned_unchanged():
    window = (2.0, 8.0)
    assert zoomed_window(window, (5.0, 5.0), anchor=5.0, factor=0.5, min_fraction=0.02) == window


# --- is_full_span --------------------------------------------------------


def test_is_full_span_true_for_an_exact_match():
    assert is_full_span((0.0, 10.0), (0.0, 10.0)) is True


def test_is_full_span_false_for_a_narrower_window():
    assert is_full_span((1.0, 9.0), (0.0, 10.0)) is False


def test_is_full_span_true_for_a_wider_window_too():
    """A caller that zoomed out past the data (before clamping) must
    still read as "full", not as some unrepresentable fourth state."""
    assert is_full_span((-1.0, 11.0), (0.0, 10.0)) is True


# --- panned_window ---------------------------------------------------------


def test_panning_a_descending_axis_shifts_the_same_way_the_cursor_moved():
    low, high = panned_window((0.0, 10.0), pixel_delta=50.0, pixel_span=200.0, descending=True)
    assert (low, high) == pytest.approx((2.5, 12.5))


def test_panning_an_ascending_axis_shifts_the_opposite_way():
    """The load-bearing case: unlike zoom, pan is NOT direction-symmetric
    -- the same pixel drag must shift an ascending (shielding) axis's
    window the opposite way from a descending one, or the point under
    the cursor would slide instead of staying put."""
    low, high = panned_window((0.0, 10.0), pixel_delta=50.0, pixel_span=200.0, descending=False)
    assert (low, high) == pytest.approx((-2.5, 7.5))


def test_panning_preserves_the_span():
    low, high = panned_window((1.0, 9.0), pixel_delta=37.0, pixel_span=150.0, descending=True)
    assert (high - low) == pytest.approx(8.0)


def test_a_zero_pixel_span_returns_the_window_unchanged():
    window = (1.0, 9.0)
    assert panned_window(window, pixel_delta=50.0, pixel_span=0.0, descending=True) == window


def test_a_zero_pixel_delta_does_not_move_the_window():
    window = (1.0, 9.0)
    assert panned_window(window, pixel_delta=0.0, pixel_span=200.0, descending=True) == pytest.approx(window)


# --- drift -------------------------------------------------------------


def test_drift_is_euclidean_distance():
    assert drift(3.0, 4.0) == pytest.approx(5.0)


def test_zero_drift_for_no_movement():
    assert drift(0.0, 0.0) == 0.0
