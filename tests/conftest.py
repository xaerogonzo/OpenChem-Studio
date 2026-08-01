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


def synthetic_nmr_spectrum(mol, molecule_uuid: str = "mol-1"):
    """A deterministic NMRSpectrumResult for a molecule, for tests that need
    *some* shift values to exercise signal grouping, plotting or selection.

    Replaces the empirical SMARTS estimator these tests used to borrow.
    That estimator was removed for collapsing distinct signals onto
    identical values (11 of propranolol's 16), but the deeper point is that
    a test of grouping or rendering should never have depended on a
    predictor's accuracy in the first place -- it only needs values that
    are distinct and reproducible.

    Shifts are spread by atom index within each element's usual window, so
    every atom gets a different value and grouping/overlap behaviour is
    observable rather than accidental.
    """
    from openchem.domain.scientific_result import NMRSpectrumResult

    values: dict[int, float] = {}
    elements: dict[int, str] = {}
    protons = carbons = 0
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        if symbol == "H":
            values[atom.GetIdx()] = round(0.9 + 0.37 * protons, 3)
            protons += 1
        elif symbol == "C":
            values[atom.GetIdx()] = round(18.0 + 7.3 * carbons, 3)
            carbons += 1
        else:
            continue
        elements[atom.GetIdx()] = symbol

    return NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="Synthetic test spectrum",
        units="ppm",
        method="test",
        molecule_uuid=molecule_uuid,
        values=values,
        elements=elements,
    )


@pytest.fixture(autouse=True)
def _stout_weights_assumed_reachable(monkeypatch):
    """Two jobs, and the second is the important one.

    STOUT's setup now probes whether upstream still publishes its model
    weights. Left unstubbed, EVERY test that touches STOUT prerequisites
    would make a real network request -- so the suite would be slower
    offline and would give different answers depending on a third party.

    Defaulting to True keeps every pre-existing test asserting what it
    was written to assert (they are about the Java and uv preconditions,
    which sit behind this one). Tests that are specifically about the
    weights being gone override it explicitly.
    """
    from openchem.services import stout_setup

    stout_setup.weights_available.cache_clear()
    monkeypatch.setattr(stout_setup, "weights_available", lambda: True)
