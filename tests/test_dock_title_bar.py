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

from openchem.app.main_window import HELP_TOPIC_BY_DOCK, HELP_TOPIC_BY_PLUGIN_DOCK
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


def _named(bar: DockTitleBar, name: str) -> QToolButton:
    """A control by its stable objectName: the children's order changes whenever a panel adds a button."""
    found = bar.findChild(QToolButton, name)
    assert found is not None, name
    return found


def test_the_help_button_is_there_and_emits(dock, qapp):
    _dock, bar = dock
    fired = []
    bar.help_requested.connect(lambda: fired.append(True))
    help_buttons = [b for b in _buttons(bar) if b.text() == "?"]
    assert len(help_buttons) == 1
    help_buttons[0].click()
    assert fired == [True]


def test_the_layout_and_close_buttons_are_put_back(dock):
    """setTitleBarWidget removes the native buttons; a panel that cannot be closed or floated any more is a
    straight regression against the native bar. Float now lives in the layout menu, so the bar still has three
    fixed buttons: the layout menu, help, close."""
    _dock, bar = dock
    assert sorted(b.objectName() for b in _buttons(bar)) == ["dockCloseButton", "dockHelpButton", "dockLayoutButton"]


def test_the_layout_menu_floats_and_redocks_a_panel_on_its_own(dock, qapp):
    """With no window listening, the menu still offers the one thing a dock on its own can do."""
    widget, bar = dock
    assert not widget.isFloating()
    bar._fill_menu()
    [float_action] = [a for a in bar.layout_menu().actions() if a.objectName() == "dockMenu_float"]
    assert float_action.text() == "Float panel"
    float_action.trigger()
    qapp.processEvents()
    assert widget.isFloating()
    bar._fill_menu()
    [back] = [a for a in bar.layout_menu().actions() if a.objectName() == "dockMenu_float"]
    assert back.text() == "Dock panel back"
    back.trigger()
    qapp.processEvents()
    assert not widget.isFloating()


def test_the_close_button_closes(dock, qapp):
    widget, bar = dock
    _named(bar, "dockCloseButton").click()
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
    visible = sorted(b.objectName() for b in _buttons(bar) if b.isVisibleTo(bar))
    assert visible == ["dockHelpButton", "dockLayoutButton"]  # not closable


def test_the_title_bar_shows_the_dock_title(dock):
    _dock, bar = dock
    assert bar.findChild(QLabel, "dockTitleLabel").fullText() == "Docking"


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

    def test_panels_without_a_topic_have_the_bar_but_no_question_mark(self, qapp, tmp_path, widgets):
        """A "?" that opened the wrong section would be worse than none, so Console and Jobs -- which nothing is
        written about -- get the layout menu and close but are not pointed at a vaguely related topic."""
        window = self._window(qapp, tmp_path, widgets)
        docks = [d for d in window.findChildren(QDockWidget) if d.parent() is window]
        assert all(isinstance(d.titleBarWidget(), DockTitleBar) for d in docks)
        wrongly_helped = [
            d.objectName()
            for d in docks
            if d.objectName() not in HELP_TOPIC_BY_DOCK and d.titleBarWidget().help_button() is not None
        ]
        assert not wrongly_helped

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


def test_a_long_title_is_shortened_on_purpose_and_kept_whole(dock, qapp):
    """A QLabel clips; the bar elides, and the whole title stays for a hover and a screen reader."""
    widget, bar = dock
    widget.setWindowTitle("A panel with a very long and descriptive title indeed")
    bar.setWindowTitle(widget.windowTitle())
    bar.resize(120, bar.height())
    qapp.processEvents()
    label = bar.findChild(QLabel, "dockTitleLabel")
    assert label.text().endswith("…") and len(label.text()) < len(label.fullText())
    assert label.fullText() == "A panel with a very long and descriptive title indeed"
    assert bar.toolTip() == label.fullText() and bar.accessibleName() == label.fullText()
    assert label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_the_layout_button_is_text_not_a_platform_icon(dock):
    """`SP_TitleBarMenuButton` is the WINDOW's icon on Windows and drew the Qt logo in the real window; offscreen
    draws something else, so only the absence of an icon can be asserted here."""
    _dock, bar = dock
    button = _named(bar, "dockLayoutButton")
    assert button.icon().isNull() and button.text() == "…"


def test_every_control_has_a_stable_name_and_an_accessible_name(dock):
    _dock, bar = dock
    for button in _buttons(bar):
        assert button.objectName().startswith("dock")
        assert button.accessibleName(), button.objectName()


def test_a_panel_control_sits_after_the_title_and_before_the_docks_own_buttons(dock):
    """A panel's action on its whole view -- the Results reader's pop-out --
    joins the bar without separating help from float and close, and takes
    no focus, like them."""
    _dock, bar = dock
    extra = QToolButton()
    extra.setText("extra")
    bar.add_control(extra)

    layout = bar.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order[0] is bar._label
    assert order[1] is extra
    assert extra.parent() is bar
    assert extra.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert len(_buttons(bar)) == 4


class TestAPluginPanelsHelp:
    """The Synthesis panel is a PLUGIN's dock, so a window built with no plugins never has it and the map the other tests read (`HELP_TOPIC_BY_DOCK`) cannot name it.

    Its `?` and F1 are therefore tested in a window built with the real plugins, which is the only place the dock exists. A topic that only the map knew would give the panel a button that opened
    the wrong section, or none.
    """

    @staticmethod
    def _window(qapp, tmp_path, widgets):
        from pathlib import Path

        from openchem.app.main_window import MainWindow
        from openchem.app.session import SessionManager
        from openchem.app.settings import Settings
        from openchem.bootstrap import build_service_container

        services = build_service_container()
        settings = Settings(services.event_bus)
        settings.set("plugins/project_directory", str(Path(__file__).resolve().parent.parent / "plugins"))
        settings.set("plugins/user_directory", str(tmp_path / "no_user"))
        window = MainWindow(services, settings, SessionManager())
        widgets.append(window)
        window.show()
        qapp.processEvents()
        return window

    @staticmethod
    def _dock(window, name="Synthesis"):
        return next(d for d in window.findChildren(QDockWidget) if d.objectName() == name)

    @pytest.mark.parametrize("name", sorted(HELP_TOPIC_BY_PLUGIN_DOCK))
    def test_a_plugin_dock_has_a_help_button_that_opens_its_section(self, qapp, tmp_path, widgets, name):
        window = self._window(qapp, tmp_path, widgets)
        dock = self._dock(window, name)
        bar = dock.titleBarWidget()
        assert isinstance(bar, DockTitleBar)
        buttons = [b for b in bar.findChildren(QToolButton) if b.text() == "?"]
        assert len(buttons) == 1
        buttons[0].click()
        qapp.processEvents()
        dialog = window._help_dialog
        assert dialog is not None and dialog._current_key == HELP_TOPIC_BY_PLUGIN_DOCK[name]
        dialog.close()

    @pytest.mark.parametrize("name", sorted(HELP_TOPIC_BY_PLUGIN_DOCK))
    def test_f1_in_a_plugin_panel_selects_its_topic(self, qapp, tmp_path, widgets, name):
        window = self._window(qapp, tmp_path, widgets)
        expected = HELP_TOPIC_BY_PLUGIN_DOCK[name]
        window.reveal_panel(name.replace("_", " "))
        qapp.processEvents()
        dock = self._dock(window, name)
        dock.widget().setFocus()
        qapp.processEvents()
        assert window._help_topic_for_visible_panel() == expected, "focus inside the panel"
        front, window._right_docks = window._right_docks, []  # so the front-panel fallback cannot be what answers: only the focus path can
        assert window._help_topic_for_visible_panel() == expected, "the focus path alone"
        window._right_docks = front
        window._center_tabs.setFocus()  # focus in the editor beats a visible side panel, as `TestHelpRouting` pins; the panel's own topic needs focus in it
        qapp.processEvents()
        assert window._help_topic_for_visible_panel() == "centre-tabs"

    @pytest.mark.parametrize("name", sorted(HELP_TOPIC_BY_PLUGIN_DOCK))
    def test_with_no_focus_the_front_panel_is_the_one_whose_topic_is_opened(self, qapp, tmp_path, widgets, monkeypatch, name):
        from PySide6.QtWidgets import QApplication

        window = self._window(qapp, tmp_path, widgets)
        window.reveal_panel(name.replace("_", " "))
        qapp.processEvents()
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: None))
        assert window._help_topic_for_visible_panel() == HELP_TOPIC_BY_PLUGIN_DOCK[name]

    def test_a_plugin_dock_without_a_topic_has_the_bar_and_no_question_mark(self, qapp, tmp_path, widgets):
        window = self._window(qapp, tmp_path, widgets)
        from openchem.app.main_window import help_topic_of_dock

        docks = [d for d in window.findChildren(QDockWidget) if d.parent() is window]
        assert docks
        no_bar = [d.objectName() for d in docks if not isinstance(d.titleBarWidget(), DockTitleBar)]
        assert not no_bar, f"panels with no layout menu: {no_bar}"
        wrongly_helped = [
            d.objectName()
            for d in docks
            if help_topic_of_dock(d.objectName()) is None and d.titleBarWidget().help_button() is not None
        ]
        assert not wrongly_helped, f"a '?' on a panel nothing is written about: {wrongly_helped}"

    def test_every_topic_a_dock_opens_exists_and_is_named_for_it(self):
        from openchem.app.main_window import HELP_TOPIC_BY_PLUGIN_DOCK
        from openchem.help import topics

        titles = {t.key: t.title for t in topics()}
        for dock, key in HELP_TOPIC_BY_PLUGIN_DOCK.items():
            assert key in titles, f"{dock} opens {key!r}, which is not a topic"
            assert dock.replace("_", " ").lower() in titles[key].lower(), f"{dock} opens {titles[key]!r}"
        assert not set(HELP_TOPIC_BY_PLUGIN_DOCK) & set(HELP_TOPIC_BY_DOCK), "a dock is in one map or the other"
