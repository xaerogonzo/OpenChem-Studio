"""The interface size: the stored step, the font it makes, and the pixel sizes that must follow it."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from openchem.app.interface_size_service import InterfaceSizeService
from openchem.app.settings import INTERFACE_SIZE, Settings
from openchem.domain.interface_size import (
    SCALE,
    InterfaceSize,
    interface_size_from_stored,
    scaled_points,
)
from openchem.events.base import EventBus
from openchem.ui import theme


@pytest.fixture
def service(qapp):
    """A service on a fresh bus, with the application font and the theme scale put back afterwards."""
    base = qapp.font()
    bus = EventBus()
    settings = Settings(bus)
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.DEFAULT))
    svc = InterfaceSizeService(qapp, settings, bus)
    yield svc, settings
    qapp.setFont(base)
    theme.set_scale(1.0)
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.DEFAULT))


def test_every_step_has_a_factor_and_they_grow():
    assert set(SCALE) == set(InterfaceSize)
    factors = [SCALE[size] for size in sorted(InterfaceSize)]
    assert factors[0] == 1.0 and factors == sorted(factors) and len(set(factors)) == len(factors)


@pytest.mark.parametrize("raw", [None, "", "x", "-1", "3", 99, 1.5e300])
def test_an_unreadable_stored_value_is_the_default(raw):
    assert interface_size_from_stored(raw) is InterfaceSize.DEFAULT


def test_a_stored_integer_round_trips_as_its_step():
    for size in InterfaceSize:
        assert interface_size_from_stored(str(int(size))) is size


def test_the_default_step_returns_a_point_size_exactly():
    assert scaled_points(9.0, InterfaceSize.DEFAULT) == 9.0
    assert scaled_points(10.0, InterfaceSize.LARGE) == pytest.approx(13.0)


def test_the_preference_is_bounded_by_the_steps():
    assert INTERFACE_SIZE.default == int(InterfaceSize.DEFAULT)
    assert INTERFACE_SIZE.minimum == 0 and INTERFACE_SIZE.maximum == int(max(InterfaceSize))


def test_choosing_a_step_scales_the_application_font_from_the_platform_size(qapp, service):
    svc, settings = service
    base = qapp.font().pointSizeF()
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.LARGE))
    assert qapp.font().pointSizeF() == pytest.approx(base * SCALE[InterfaceSize.LARGE])


def test_going_back_to_the_default_restores_the_platform_size_with_no_drift(qapp, service):
    svc, settings = service
    base = qapp.font().pointSizeF()
    for size in (InterfaceSize.LARGE, InterfaceSize.LARGER, InterfaceSize.LARGE, InterfaceSize.DEFAULT):
        settings.set_preference(INTERFACE_SIZE, int(size))
    assert qapp.font().pointSizeF() == pytest.approx(base)


def test_a_widget_that_is_already_open_follows_the_change(qapp, service):
    svc, settings = service
    label = QLabel("already open")
    label.show()
    before = label.font().pointSizeF()
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.LARGER))
    qapp.processEvents()  # Qt hands the new font to open widgets from the event loop
    assert label.font().pointSizeF() == pytest.approx(before * SCALE[InterfaceSize.LARGER])
    label.close()


def test_a_change_asks_for_the_stylesheets_to_be_set_again(qapp, service, monkeypatch):
    """Measured on the REAL window (offscreen does not reproduce it): a section header with `QToolButton { font-weight:
    bold; }` stayed at the old size after a live change until its sheet was set again, the same trap the palette has.
    Here only the request is checked; `benchmarks/visual/interface_size.json` shows the effect."""
    calls = []
    monkeypatch.setattr(theme, "repolish_styled_widgets", lambda: calls.append(1))
    svc, settings = service
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.LARGE))
    qapp.processEvents()
    assert calls == [1]
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.LARGE))  # no change, no second pass
    qapp.processEvents()
    assert calls == [1]


def test_start_applies_the_stored_step(qapp, service):
    svc, settings = service
    base = qapp.font().pointSizeF()
    settings.set_preference(INTERFACE_SIZE, int(InterfaceSize.LARGER))
    qapp.setFont(svc._base)
    theme.set_scale(1.0)
    svc._applied = None
    svc.start()
    assert qapp.font().pointSizeF() == pytest.approx(base * SCALE[InterfaceSize.LARGER])


# --- the pixel sizes in stylesheets, which the application font does not reach ----------------------


def test_the_default_scale_leaves_a_stylesheet_byte_for_byte(service):
    sheet = "color: #666666; font-size: 9px; font-weight: bold;"
    assert theme.resolve(sheet) == sheet


def test_a_pixel_font_size_is_scaled_and_nothing_else_is(service):
    theme.set_scale(1.5)
    assert theme.resolve("font-size: 10px; padding: 10px; border: 2px solid red;") == (
        "font-size: 15px; padding: 10px; border: 2px solid red;"
    )


def test_a_themed_widget_is_rewritten_when_the_scale_changes(qapp, service):
    label = QLabel("x")
    theme.style(label, "font-size: 10px;")
    assert "10px" in label.styleSheet()
    theme.set_scale(1.3)
    assert "13px" in label.styleSheet()
    theme.set_scale(1.0)
    assert label.styleSheet() == "font-size: 10px;"
