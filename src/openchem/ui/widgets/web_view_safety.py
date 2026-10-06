"""Destroy the web views under a widget in the order Chromium survives.

A `QWebEngineView` that is still loading must not be deleted as a CHILD, inside its parent's
destructor. The order that works is the one `tests/conftest.dispose` found on Windows CI (#197): stop
the view, delete it, flush its deferred delete, each view on its own and BEFORE the widget that holds
it goes. This module is that order, in one place, so the application and the test suite cannot drift.

**WHERE A PYTHON WRAPPER'S DEATH FITS IN.** A top-level widget with no Qt parent is owned by its Python
wrapper: when the last reference goes (a discarded return value, a test's locals at return, a garbage
collection) Python deletes the C++ object right there, web view and all, with no chance for any caller
to dispose of it properly first. `destroy_web_views_first` is what a widget's `__del__` calls, which
runs BEFORE that delete, while the C++ object is still alive.

A no-op until something has imported the web-engine module (until then no view can exist, and
importing it here would drag Chromium into code that never touches one).
"""

from __future__ import annotations

import os
import sys

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent

#: Switch for the crash-rate experiment (`benchmarks/windows_crash/`): "1" runs the safe order from a
#: widget's `__del__`. One commit and one env var, so the two arms of an A/B are the same tree.
SAFE_DEL_ENV = "OPENCHEM_SAFE_WEBVIEW_DEL"


def destroy_web_views_first(widget) -> None:
    """Stop, delete and flush every `QWebEngineView` that is `widget` or inside it, each on its own,
    before `widget` itself is destroyed."""
    module = sys.modules.get("PySide6.QtWebEngineWidgets")
    if module is None or not shiboken6.isValid(widget):
        return
    view_type = module.QWebEngineView
    views = [widget] if isinstance(widget, view_type) else []
    views += widget.findChildren(view_type)
    for view in views:
        if not shiboken6.isValid(view):
            continue
        view.stop()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def safe_teardown_on_delete(widget) -> None:
    """The body of a web-view owner's `__del__`. A finaliser must never raise (an exception in `__del__` is
    only printed, but a half-run teardown is worse than none), and it must do nothing at interpreter
    shutdown, when the modules it uses may already be gone."""
    try:
        if os.environ.get(SAFE_DEL_ENV) != "1" or sys.is_finalizing():
            return
        if shiboken6.isValid(widget):
            destroy_web_views_first(widget)
    except Exception:  # noqa: BLE001 - see the docstring
        pass
