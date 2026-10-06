"""`conftest.dispose` destroys a web view BEFORE the widget that holds it.

The reason is in `dispose`'s docstring: deleting a container deletes a still-loading `QWebEngineView` as a
child inside the parent's destructor, which is where the Windows suite's most frequent crash happened.
"""

from __future__ import annotations

import pytest

import conftest

pytest.importorskip("PySide6.QtWebEngineWidgets")
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QVBoxLayout, QWidget  # noqa: E402


def _watch(obj, name, order):
    obj.destroyed.connect(lambda *_: order.append(name))


def test_a_view_inside_the_widget_goes_before_it(qapp):
    parent = QWidget()
    view = QWebEngineView(parent)
    order: list[str] = []
    _watch(view, "view", order)
    _watch(parent, "parent", order)
    conftest.dispose(parent)
    assert order == ["view", "parent"]


def test_a_view_deep_in_the_tree_goes_before_the_top_widget(qapp):
    top = QWidget()
    inner = QWidget(top)
    QVBoxLayout(inner)
    view = QWebEngineView(inner)
    order: list[str] = []
    _watch(view, "view", order)
    _watch(top, "top", order)
    conftest.dispose(top)
    assert order == ["view", "top"]


def test_disposing_the_view_itself_is_fine(qapp):
    view = QWebEngineView()
    destroyed: list[str] = []
    _watch(view, "view", destroyed)
    conftest.dispose(view)
    assert destroyed == ["view"]


def test_a_widget_with_no_view_is_disposed_as_before(qapp):
    widget = QWidget()
    destroyed: list[str] = []
    _watch(widget, "widget", destroyed)
    conftest.dispose(widget)
    assert destroyed == ["widget"]


# --- a PARENTLESS widget dying by refcount: its __del__ runs the safe order first -------------------------


class _Owner(QWidget):
    """A parentless widget holding a web view, with the `__del__` the application's owners use."""

    def __del__(self) -> None:
        from openchem.ui.widgets.web_view_safety import safe_teardown_on_delete

        safe_teardown_on_delete(self)


def test_python_deleting_a_parentless_owner_destroys_its_view_first_when_enabled(qapp, monkeypatch):
    """The crash site was `_inspect(...)` with its return value discarded: the dialog's last reference
    died on that line and Python deleted the C++ dialog, web view inside it, with no caller able to
    dispose of it properly. `__del__` runs BEFORE that delete."""
    from openchem.ui.widgets import web_view_safety

    monkeypatch.setenv(web_view_safety.SAFE_DEL_ENV, "1")
    order: list[str] = []
    owner = _Owner()
    view = QWebEngineView(owner)
    _watch(view, "view", order)
    _watch(owner, "owner", order)
    del owner, view
    assert order == ["view", "owner"]


def test_it_is_off_unless_the_switch_is_on(qapp, monkeypatch):
    from openchem.ui.widgets import web_view_safety

    monkeypatch.delenv(web_view_safety.SAFE_DEL_ENV, raising=False)
    calls: list[object] = []
    monkeypatch.setattr(web_view_safety, "destroy_web_views_first", calls.append)
    owner = _Owner()
    del owner
    assert calls == []


def test_a_finaliser_never_raises(qapp, monkeypatch):
    from openchem.ui.widgets import web_view_safety

    monkeypatch.setenv(web_view_safety.SAFE_DEL_ENV, "1")

    def boom(_widget):
        raise RuntimeError("teardown failed")

    monkeypatch.setattr(web_view_safety, "destroy_web_views_first", boom)
    owner = _Owner()
    del owner  # an exception here would surface as an unraisable one, which pytest turns into a warning


def test_the_calculator_inspector_dialog_is_wired_to_it():
    """The dialog the crash was in. Not constructed here (it builds a real web view, which is slow): the
    contract is that its finaliser is the shared one."""
    import inspect

    from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog

    assert "safe_teardown_on_delete(self)" in inspect.getsource(CalculatorInspectorDialog.__del__)
