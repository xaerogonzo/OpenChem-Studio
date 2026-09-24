"""Several calculator inspectors stand side by side, and asking again raises the one already open.

The panel used to `exec()` an inspector: one modal window, so comparing two results
meant closing the first and remembering it. A person asked to compare charge methods
could not put two of them on screen. Now each RESULT opens its own window -- modeless,
deleted on close, owned by the panel, under the cap the Batch panel already uses --
and the same result is one window.

The dialogs are doubles here (a real inspector is a Chromium process); the real ones
are covered by `benchmarks/visual/modeless_inspectors.json`, driven in the application.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

import openchem.ui.panels.property_panel as property_panel_module
from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import (
    PropertyPanel,
    cascade_position,
    inspector_window_title,
)
from tests.test_property_panel import _FakeDescriptorService, _FakeModelessDialog


class _Dialogs:
    """Every dialog the panel constructed, so a test can count and inspect them."""

    def __init__(self) -> None:
        self.made: list = []


@pytest.fixture
def rig(qapp, monkeypatch):
    dialogs = _Dialogs()

    class _Inspector(_FakeModelessDialog):
        def __init__(self, engine, molecule, result, conformer_molblock, parent=None, **kwargs):
            self.result = result
            self.open = True
            dialogs.made.append(self)

        def isVisible(self):  # noqa: N802
            return self.open

    monkeypatch.setattr(property_panel_module, "CalculatorInspectorDialog", _Inspector)
    bus = EventBus()
    panel = PropertyPanel(bus, CalculatorRegistry(), _FakeDescriptorService(), ChemistryEngine())
    molecule = MoleculeModel(display_name="Ethanol")
    panel.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    return panel, molecule, dialogs


def _result(molecule, name="Partial Charge (3D)", method="eem_bultinck2002_part1") -> PerAtomDataset:
    return PerAtomDataset(
        property_id="geometry_partial_charge", name=name, units="e", method=method,
        molecule_uuid=molecule.uuid, values={0: -0.4},
    )


def test_two_results_are_two_windows_side_by_side(rig):
    panel, molecule, dialogs = rig
    panel._open_inspector(_result(molecule, method="eem_bultinck2002_part1"))
    panel._open_inspector(_result(molecule, method="qeq_rg1991"))
    assert len(dialogs.made) == 2
    assert all(d.shown == 1 for d in dialogs.made), "both are shown, neither replaced the other"


def test_the_same_result_is_one_window_and_asking_again_raises_it(rig):
    panel, molecule, dialogs = rig
    result = _result(molecule)
    panel._open_inspector(result)
    panel._open_inspector(result)
    assert len(dialogs.made) == 1, "a duplicate window for one result"
    assert dialogs.made[0].shown == 2, "the second ask brought the first forward"


def test_a_closed_window_is_opened_again_not_raised(rig):
    panel, molecule, dialogs = rig
    result = _result(molecule)
    panel._open_inspector(result)
    dialogs.made[0].open = False  # the person closed it

    panel._open_inspector(result)

    assert len(dialogs.made) == 2


def test_the_title_names_the_result_the_molecule_and_a_method_the_name_does_not_carry(rig):
    """Two windows of one calculator with different methods must be tellable apart."""
    panel, molecule, dialogs = rig
    panel._open_inspector(_result(molecule, name="Partial Charge (3D)", method="qeq_rg1991"))
    assert dialogs.made[0].title == "Partial Charge (3D) [qeq_rg1991] — Ethanol"
    panel._open_inspector(_result(molecule, name="Dipole Moment", method=""))
    assert dialogs.made[1].title == "Dipole Moment — Ethanol", "no method, no empty brackets"


def test_a_name_that_already_says_the_method_is_not_followed_by_its_raw_id():
    """Measured in the running app: 'Partial Charge (EEM, Bultinck 2002, 3D)
    (eem_bultinck2002_part1)'. The label is already in the name."""
    result = PerAtomDataset(
        property_id="geometry_partial_charge", name="Partial Charge (EEM, Bultinck 2002, 3D)",
        units="e", method="eem_bultinck2002_part1", molecule_uuid="m", values={0: 0.0},
    )
    assert inspector_window_title(result, "Methanol") == "Partial Charge (EEM, Bultinck 2002, 3D) — Methanol"


def test_the_second_window_does_not_sit_exactly_on_the_first(rig):
    """Driven in the app, both opened at (360, 128): one window's worth of pixels."""
    panel, molecule, dialogs = rig
    panel._open_inspector(_result(molecule, method="a_method"))
    panel._open_inspector(_result(molecule, method="b_method"))
    first, second = (d.position for d in dialogs.made)
    assert second != first, "two inspectors at one position read as one"
    assert second[0] > first[0] and second[1] > first[1], "offset down and to the right"


def test_cascade_steps_down_and_right():
    assert cascade_position((100, 100), (800, 600), (0, 0, 1919, 1079), step=36) == (136, 136)


def test_cascade_is_clamped_to_the_screen():
    """Near the corner the window is held on screen instead of walking off it."""
    x, y = cascade_position((1100, 500), (800, 600), (0, 0, 1919, 1079), step=36)
    assert x + 800 <= 1920 and y + 600 <= 1080


def test_a_window_bigger_than_the_screen_sits_at_the_corner_not_at_a_negative_offset():
    assert cascade_position((0, 0), (3000, 2000), (0, 0, 1919, 1079)) == (0, 0)


def test_past_the_cap_it_refuses_and_says_how_many(rig, monkeypatch):
    """The same refusal the Batch panel gives: an unbounded number of these is a
    Chromium process each, and once hung a machine."""
    panel, molecule, dialogs = rig
    told: list[str] = []
    monkeypatch.setattr(property_panel_module, "inspector_budget_message", lambda: "8 inspectors are open")
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: told.append(text))

    panel._open_inspector(_result(molecule))

    assert dialogs.made == []
    assert told == ["8 inspectors are open"]


def test_it_never_blocks_the_caller(rig):
    """`exec()` did; `show()` returns, so the reveal cannot starve later subscribers
    and a script can keep going."""
    panel, molecule, dialogs = rig
    panel._open_inspector(_result(molecule))
    assert dialogs.made[0].shown == 1
    assert not hasattr(dialogs.made[0], "exec"), "the double has no exec: it must not be called"
