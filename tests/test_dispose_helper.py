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
