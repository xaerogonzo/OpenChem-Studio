"""The reaction-template example plugin, exercised the way a user would.

ARCHITECTURE.md carried this as an OPEN item: `context.reactions` was
covered by tests including an end-to-end one, but no shipped or example
plugin actually CALLED it, so the third-party story rested entirely on
tests of the namespace rather than on anything a reader could copy.

**REGISTRATION -> DISCOVERY -> APPLICATION -> ROLLBACK, and the third step
is the one worth insisting on.** Asserting that three templates arrive in
`all_templates()` proves the plumbing and says nothing about whether the
example demonstrates anything: a SMARTS that parses cleanly and matches
NOTHING would pass that check while being a worked example of failure.
Every template is therefore applied to a declared substrate through the
same `RDKitTemplateProvider` the shipped reaction plugin uses, and the
expected product is asserted.

Loaded through the real `PluginManager` rather than by importing
`plugin.py`, for the reason `tests/test_calculator_registry.py` already
records: a direct-import test once passed while the registration itself
bound to a shadowed function.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.plugins.manager import PluginManager

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "plugins"
BUNDLED_TEMPLATES = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "reaction_prediction"
    / "reaction_templates.json"
)
PLUGIN_ID = "reaction_templates_plugin"

#: One substrate set per template, small enough to check by eye, and the
#: product it must produce. These are the assertions that make the example
#: an example rather than three strings that happen to compile.
EXPECTED = {
    "Primary alcohol oxidation": (["CCO"], "CC=O"),
    "Nitro reduction": (["[O-][N+](=O)c1ccccc1"], "Nc1ccccc1"),
    "Williamson ether synthesis": (["CCl", "CO"], "COC"),
}


class _FakeUIRegistry:
    """The panel/menu surface `PluginManager` expects.

    It RECORDS rather than asserting, because `load_all()` loads every
    example in the directory and `hello_plugin` legitimately registers a
    panel and a menu action. The widget factory is deliberately not called:
    constructing a real `QWidget` would drag a `qapp` into a test that is
    about reaction data.
    """

    def __init__(self) -> None:
        self.panels: dict[str, object] = {}
        self.menu_actions: dict[str, list[str]] = {}

    def add_panel(self, panel_id, widget_factory):
        self.panels[panel_id] = widget_factory

    def remove_panel(self, panel_id):
        self.panels.pop(panel_id, None)

    def add_menu_action(self, plugin_id, label, callback):
        self.menu_actions.setdefault(plugin_id, []).append(label)

    def remove_menu_actions(self, plugin_id):
        self.menu_actions.pop(plugin_id, None)


@pytest.fixture
def loaded(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(EXAMPLES_DIR))
    settings.set("plugins/user_directory", str(tmp_path / "unused_user_plugins"))

    ui = _FakeUIRegistry()
    manager = PluginManager(services, ui, settings)
    manager.load_all()
    return manager, services, ui


def test_the_example_plugin_registers_its_templates(loaded):
    manager, services, ui = loaded

    assert PLUGIN_ID in manager.loaded_plugin_ids
    # A plugin contributing only DATA needs no widget, which is part of what
    # this example is showing.
    assert PLUGIN_ID not in ui.menu_actions

    registered = {
        t.name: t
        for t in services.reaction_template_service.all_templates()
        if t.source_id == PLUGIN_ID
    }
    assert set(registered) == set(EXPECTED), (
        f"expected {sorted(EXPECTED)} from {PLUGIN_ID}, got {sorted(registered)}"
    )


def test_every_registered_template_actually_produces_its_product(loaded):
    """The assertion that makes this an example of something.

    Applied through `RDKitTemplateProvider`, which is what the shipped
    reaction plugin runs -- so this also covers the claim in the example's
    docstring that a registered template reaches the bundled provider
    without either side knowing about the other.
    """
    _, services, _ui = loaded

    from plugins.reaction_prediction.providers import RDKitTemplateProvider

    provider = RDKitTemplateProvider(
        bundled_templates_path=BUNDLED_TEMPLATES,
        template_service=services.reaction_template_service,
    )

    for name, (reactants, expected_smiles) in EXPECTED.items():
        predictions = provider.predict(reactants)
        products = {p.product_smiles for p in predictions}
        want = Chem.CanonSmiles(expected_smiles)
        assert want in products, (
            f"{name}: applying it to {reactants} did not produce {want}. "
            f"Got {sorted(products)}. A template that matches nothing would "
            "pass a registration-only test while demonstrating nothing."
        )
        assert any(
            p.product_smiles == want and PLUGIN_ID in (p.source_label or "")
            for p in predictions
        ), f"{name}: the product is not attributed to {PLUGIN_ID}"


def test_unloading_the_plugin_removes_its_templates(loaded):
    """The rollback half, which a hand-written example never exercises.

    `deactivate` in the example is empty on purpose: the registrar recorded
    the rollback when `register` was called. If that ever stops being true
    this fails, and the example's docstring becomes wrong with it.
    """
    manager, services, _ui = loaded
    service = services.reaction_template_service

    assert [t for t in service.all_templates() if t.source_id == PLUGIN_ID]

    manager.unload(PLUGIN_ID)

    assert not [t for t in service.all_templates() if t.source_id == PLUGIN_ID], (
        "templates survived the plugin that registered them"
    )
