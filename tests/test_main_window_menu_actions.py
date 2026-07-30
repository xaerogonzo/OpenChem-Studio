from __future__ import annotations

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container


def test_add_menu_action_callback_receives_no_arguments(qapp, tmp_path):
    """Regression test: QAction.triggered emits `triggered(checked: bool)`.
    Connecting it directly to a plugin-supplied callback would silently pass
    that bool through as a positional argument, clobbering a lambda default
    like `lambda aid=action_id: ...` instead of raising. `add_menu_action`
    must shield callers from this so `UIRegistry`'s zero-arg `callback`
    contract genuinely holds when a real QAction fires.
    """
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)

    received: list[object] = []

    # Shaped exactly like the real callback plugins get from
    # `_MenuRegistrar.register` (context.py): a callable with one
    # *optional* positional parameter carrying the real payload as its
    # default. Qt's signal/slot introspection calls a connected callable
    # with min(signal_arg_count, slot_arity) arguments -- for a genuinely
    # zero-arg callable it correctly passes nothing, but for a one-optional-
    # arg callable like this it fills that slot with the emitted
    # `triggered(bool)`, clobbering the default unless add_menu_action
    # shields it.
    def callback(action_id: str = "expected_action_id") -> None:
        received.append(action_id)

    window.add_menu_action("test_plugin", "Do Thing", callback)
    action = next(a for a in window._plugins_menu.actions() if a.text() == "Do Thing")
    action.trigger()

    assert received == ["expected_action_id"]

    window.remove_menu_actions("test_plugin")
    assert not any(a.text() == "Do Thing" for a in window._plugins_menu.actions())
