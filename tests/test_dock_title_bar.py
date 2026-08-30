"""A custom dock title bar must not cost the native one's behaviour.

`QDockWidget.setTitleBarWidget` REPLACES the built-in title bar. Every
test here covers something that stops working the moment you do that, and
that nothing else would notice: the buttons vanish, double-click stops
floating the panel, and -- the quiet one -- the dock stops being draggable
if the replacement accepts mouse events across its width.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QToolButton

from openchem.app.main_window import HELP_TOPIC_BY_DOCK
from openchem.ui.widgets.dock_title_bar import DockTitleBar

import conftest


@pytest.fixture
def widgets():
    """Destroys each widget deterministically; see tests/test_batch_panel.py."""
    built = []
    yield built
    for widget in built:
        conftest.dispose(widget)


@pytest.fixture
def dock(qapp, widgets):
    window = QMainWindow()
    widgets.append(window)
    dock = QDockWidget("Docking", window)
    dock.setObjectName("Docking")
    dock.setWidget(QLabel("panel", dock))
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    bar = DockTitleBar(dock)
    dock.setTitleBarWidget(bar)
    window.show()
    qapp.processEvents()
    return dock, bar


def _buttons(bar: DockTitleBar) -> list[QToolButton]:
    return bar.findChildren(QToolButton)


def test_the_help_button_is_there_and_emits(dock, qapp):
    _dock, bar = dock
    fired = []
    bar.help_requested.connect(lambda: fired.append(True))
    help_buttons = [b for b in _buttons(bar) if b.text() == "?"]
    assert len(help_buttons) == 1
    help_buttons[0].click()
    assert fired == [True]


def test_the_float_and_close_buttons_are_put_back(dock):
    """setTitleBarWidget removes them; a panel that cannot be closed or
    floated any more is a straight regression against the native bar."""
    _dock, bar = dock
    assert len(_buttons(bar)) == 3  # help, float, close


def test_the_float_button_floats_and_redocks(dock, qapp):
    widget, bar = dock
    float_button = _buttons(bar)[1]
    assert not widget.isFloating()
    float_button.click()
    qapp.processEvents()
    assert widget.isFloating()
    float_button.click()
    qapp.processEvents()
    assert not widget.isFloating()


def test_the_close_button_closes(dock, qapp):
    widget, bar = dock
    _buttons(bar)[2].click()
    qapp.processEvents()
    assert not widget.isVisible()


def test_double_click_floats_the_panel(dock, qapp):
    """A title-bar behaviour, so it goes with the title bar."""
    widget, bar = dock
    assert not widget.isFloating()
    bar.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPoint(10, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qapp.processEvents()
    assert widget.isFloating()


def test_the_title_text_does_not_swallow_mouse_presses(dock):
    """THE QUIET ONE. Dragging a dock works because a press on the title
    reaches the QDockWidget. A label that accepts mouse events leaves the
    dock looking perfectly normal and silently undraggable, and nothing
    else in the suite would catch it."""
    _dock, bar = dock
    labels = bar.findChildren(QLabel)
    assert labels
    assert all(
        label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) for label in labels
    )


def test_buttons_do_not_steal_focus(dock):
    """F1 resolves the topic from the focused widget, so a title-bar
    button taking focus would break the routing for the panel it belongs
    to."""
    _dock, bar = dock
    assert all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in _buttons(bar))


def test_buttons_follow_the_docks_features(dock, qapp):
    widget, bar = dock
    widget.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
    qapp.processEvents()
    visible = [b for b in _buttons(bar) if b.isVisibleTo(bar)]
    assert len(visible) == 1  # help only; not floatable, not closable


def test_the_title_bar_shows_the_dock_title(dock):
    _dock, bar = dock
    assert any(label.text() == "Docking" for label in bar.findChildren(QLabel))


class TestInTheRealWindow:
    @staticmethod
    def _window(qapp, tmp_path, widgets):
        from openchem.app.main_window import MainWindow
        from openchem.app.session import SessionManager
        from openchem.app.settings import Settings
        from openchem.bootstrap import build_service_container

        services = build_service_container()
        settings = Settings(services.event_bus)
        settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
        settings.set("plugins/user_directory", str(tmp_path / "no_user"))
        window = MainWindow(services, settings, SessionManager())
        widgets.append(window)
        qapp.processEvents()
        return window

    def test_every_panel_with_a_topic_gets_a_help_button(self, qapp, tmp_path, widgets):
        window = self._window(qapp, tmp_path, widgets)
        without = []
        for dock in window.findChildren(QDockWidget):
            if dock.objectName() not in HELP_TOPIC_BY_DOCK:
                continue
            bar = dock.titleBarWidget()
            if not isinstance(bar, DockTitleBar) or not [
                b for b in bar.findChildren(QToolButton) if b.text() == "?"
            ]:
                without.append(dock.objectName())
        assert not without, f"Panels with a help topic but no help button: {without}"

    def test_panels_without_a_topic_keep_the_native_title_bar(self, qapp, tmp_path, widgets):
        """A "?" that opened the wrong section would be worse than none,
        so Console and Jobs -- which nothing is written about -- are left
        alone rather than pointed at a vaguely related topic."""
        window = self._window(qapp, tmp_path, widgets)
        wrongly_customised = [
            dock.objectName()
            for dock in window.findChildren(QDockWidget)
            if dock.objectName() not in HELP_TOPIC_BY_DOCK
            and isinstance(dock.titleBarWidget(), DockTitleBar)
        ]
        assert not wrongly_customised

    def test_the_help_button_opens_that_panels_topic(self, qapp, tmp_path, widgets):
        window = self._window(qapp, tmp_path, widgets)
        target = next(
            dock
            for dock in window.findChildren(QDockWidget)
            if dock.objectName() == "Quantum_Chemistry"
        )
        button = next(b for b in target.titleBarWidget().findChildren(QToolButton) if b.text() == "?")
        button.click()
        qapp.processEvents()
        dialog = window._help_dialog
        assert dialog is not None
        assert dialog._current_key == "quantum-chemistry"
        dialog.close()
        # NOT added to `widgets`: the dialog is parented to the window,
        # which is already tracked, so Qt destroys it along with the
        # window. Tracking it too means the fixture reaches a C++ object
        # its parent already freed -- a double-free dressed up as a
        # teardown error.
