"""`context.calculations`: the plugin's handle on the calculator bridge, and what it must not carry."""

from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.domain.calculation_bridge import ProblemCode
from openchem.domain.molecule import MoleculeModel
from openchem.domain.run_lifecycle import PrepareResult, RunOutcome, RunState
from openchem.domain.turn_snapshot import build_turn_context
from openchem.plugins.calculation_access import PluginCalculations
from openchem.plugins.manager import PluginManager
from test_plugin_manager import FakeUIRegistry

import pytest


def _turn():
    return build_turn_context(
        project_uuid="p", molecule_uuid="m", display_name="Aspirin", canonical_smiles="", heavy_atoms=13,
        has_structure=True, conformer_count=0, fingerprints={"drawing": "fp"}, records=[], fresh=[],
    )


class _FakeHost:
    def __init__(self):
        self.calls = []

    def begin_turn(self):
        self.calls.append(("begin_turn",))
        return _turn()

    def catalog(self, query="", limit=20):
        self.calls.append(("catalog", query, limit))
        return ()

    def describe(self, calculator_id):
        self.calls.append(("describe", calculator_id))
        return None

    def prepare(self, turn, calculator_id, parameters=None):
        self.calls.append(("prepare", calculator_id, parameters))
        return PrepareResult()

    def run(self, turn, run_id, *, timeout=None):
        self.calls.append(("run", run_id, timeout))
        return RunOutcome(run_id, "c", RunState.COMPLETED)


# --- the handle ---------------------------------------------------------------------------------


def test_the_handle_offers_exactly_these_calls_and_none_that_approve():
    public = {name for name in dir(PluginCalculations) if not name.startswith("_")}
    assert public == {"available", "begin_turn", "catalog", "describe", "read_results", "prepare", "run"}


def test_the_handle_does_not_hand_out_the_host():
    handle = PluginCalculations(_FakeHost())
    for name in dir(handle):
        if name.startswith("_"):
            continue
        assert not isinstance(getattr(handle, name, None), _FakeHost), name


def test_with_no_host_every_call_answers_unavailable_rather_than_raising():
    handle = PluginCalculations(None)
    assert handle.available is False
    assert handle.begin_turn() is None and handle.catalog("x") == () and handle.describe("x") is None
    prepared = handle.prepare(_turn(), "polar_surface_area", {})
    assert not prepared.ok and prepared.problems[0].code is ProblemCode.UNAVAILABLE
    outcome = handle.run(_turn(), "r1")
    assert outcome.state is RunState.REJECTED and outcome.problems[0].code is ProblemCode.UNAVAILABLE


def test_reading_results_needs_no_host_because_it_reads_only_the_frozen_turn():
    view = PluginCalculations(None).read_results(_turn(), ["pka"])
    assert view.not_run == ("pka",) and view.entries == ()


def test_the_handle_passes_every_call_to_the_host_unchanged():
    host = _FakeHost()
    handle = PluginCalculations(host)
    turn = handle.begin_turn()
    handle.catalog("lewis", 3)
    handle.describe("pka")
    handle.prepare(turn, "polar_surface_area", {"pH": 7})
    handle.run(turn, "r1", timeout=2.5)
    assert host.calls == [
        ("begin_turn",), ("catalog", "lewis", 3), ("describe", "pka"),
        ("prepare", "polar_surface_area", {"pH": 7}), ("run", "r1", 2.5),
    ]


# --- the context and the manager ----------------------------------------------------------------------


_CAPTURE = """
from openchem.plugins.interfaces import Plugin

class Capture(Plugin):
    def activate(self, context):
        pass
    def deactivate(self):
        pass

def create_plugin():
    return Capture()
"""


def _load_capture_plugin(tmp_path: Path, host):
    plugins = tmp_path / "plugins" / "capture"
    plugins.mkdir(parents=True)
    (plugins / "plugin.py").write_text(_CAPTURE, encoding="utf-8")
    (plugins / "manifest.toml").write_text(
        'plugin_id = "capture"\nversion = "0.1.0"\napi_version = 1\ndisplay_name = "Capture"\n'
        'author = "t"\ndescription = "d"\nhomepage = ""\nlicense = "GPL-3.0-or-later"\ndependencies = []\n',
        encoding="utf-8",
    )
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    manager = PluginManager(services, FakeUIRegistry(), settings, host)
    manager.load_all()
    assert "capture" in manager.loaded_plugin_ids
    return manager._loaded["capture"].context.calculations


def test_a_plugin_loaded_with_a_host_gets_a_working_handle(tmp_path, qapp):
    host = _FakeHost()
    handle = _load_capture_plugin(tmp_path, host)
    assert handle.available is True
    handle.catalog("pka")
    assert ("catalog", "pka", 20) in host.calls


def test_a_plugin_loaded_without_a_host_gets_an_unavailable_handle(tmp_path, qapp):
    assert _load_capture_plugin(tmp_path, None).available is False


# --- the small additions this slice made -----------------------------------------------------------------


def test_the_registry_lists_every_calculator_as_a_copy():
    registry = build_service_container().calculator_registry
    listed = registry.definitions()
    assert len(listed) == 72 and listed[0].calculator_id == next(iter(registry._definitions))
    listed.clear()
    assert len(registry.definitions()) == 72


def test_the_engine_counts_the_heavy_atoms_of_a_drawing():
    engine = ChemistryEngine()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CC(=O)Oc1ccccc1C(=O)O")
    assert engine.heavy_atom_count(model) == 13
    with pytest.raises(InvalidStructureError):
        engine.heavy_atom_count(MoleculeModel())
