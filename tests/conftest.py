from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Bundled first-party plugins (src/openchem/plugins/ is the *loader*;
# plugins/ at the repo root is content it loads) aren't part of the
# installable `openchem` package, but tests still need to import their
# modules directly. plugins/<name>/ has no __init__.py, so this relies on
# PEP 420 implicit namespace packages -- `import ai_assistant.providers`
# resolves fine once `plugins/` is on sys.path.
PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
if str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """A QApplication is required for QObject-derived types used throughout
    the app (EventBus signals, QThreadPool, QUndoStack) even in headless
    tests. Session-scoped and offscreen so the suite runs in CI with no
    display.
    """
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """`openchem.app.settings.Settings` wraps `QSettings(ORG_NAME, APP_NAME)`,
    which on Windows is backed by the real, persistent registry key this
    app's actual installs use — not a throwaway store. Without this, any
    test that writes a setting (e.g. `plugins/project_directory`, as the
    plugin-manager tests do) permanently pollutes the real app's settings
    on whatever machine runs the suite. Force IniFormat plus a per-test
    unique org/app name so every test is fully isolated and nothing ever
    touches the real "OpenChemStudio" store.
    """
    import openchem.app.settings as settings_module

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    unique_name = f"OpenChemStudio-pytest-{tmp_path.name}"
    monkeypatch.setattr(settings_module, "ORG_NAME", unique_name)
    monkeypatch.setattr(settings_module, "APP_NAME", unique_name)
