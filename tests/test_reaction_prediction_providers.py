from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import reaction_prediction.providers as providers_mod

BUNDLED_TEMPLATES = Path(__file__).resolve().parent.parent / "plugins" / "reaction_prediction" / "reaction_templates.json"


def test_rdkit_template_provider_esterification():
    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    results = provider.predict(["CC(=O)O", "CCO"])

    assert len(results) == 1
    assert results[0].product_smiles == "CCOC(C)=O"
    assert results[0].confidence is None
    assert results[0].source_label == "Fischer esterification"


def test_rdkit_template_provider_works_regardless_of_reactant_order():
    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    forward = provider.predict(["CC(=O)O", "CCO"])
    reversed_order = provider.predict(["CCO", "CC(=O)O"])
    assert {r.product_smiles for r in forward} == {r.product_smiles for r in reversed_order}


def test_rdkit_template_provider_amide_coupling():
    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    results = provider.predict(["CC(=O)O", "CCN"])
    assert any(r.product_smiles == "CCNC(C)=O" for r in results)


def test_rdkit_template_provider_bad_smiles_raises():
    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    with pytest.raises(providers_mod.ReactionPredictionError):
        provider.predict(["not a smiles", "CCO"])


def test_rdkit_template_provider_no_matching_template_returns_empty():
    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    # A single reactant matches no 2-reactant template.
    assert provider.predict(["CCO"]) == []


def test_rdkit_template_provider_loads_user_override_file(tmp_path, monkeypatch):
    user_templates = tmp_path / "reaction_templates.json"
    user_templates.write_text(
        json.dumps([{"name": "Trivial identity", "smarts": "[C:1]>>[C:1]"}]), encoding="utf-8"
    )
    monkeypatch.setattr(providers_mod, "USER_TEMPLATES_PATH", user_templates)

    provider = providers_mod.RDKitTemplateProvider(BUNDLED_TEMPLATES)
    names = {t.name for t in provider._templates}
    assert "Trivial identity" in names
    assert "Fischer esterification" in names


def test_rdkit_template_provider_missing_bundled_file_is_empty():
    provider = providers_mod.RDKitTemplateProvider(Path("does_not_exist.json"))
    assert provider._templates == []


def _fake_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


def test_remote_api_provider_requires_base_url_and_key():
    provider = providers_mod.RemoteReactionAPIProvider()
    with pytest.raises(providers_mod.ReactionPredictionError, match="base_url"):
        provider.predict(["CCO"])

    provider.base_url = "https://example.test/predict"
    with pytest.raises(providers_mod.ReactionPredictionError, match="key"):
        provider.predict(["CCO"])


def test_remote_api_provider_parses_response():
    provider = providers_mod.RemoteReactionAPIProvider(
        base_url="https://example.test/predict", api_key="sk-test"
    )
    payload = {"products": [{"smiles": "CCOC(C)=O", "confidence": 0.9}]}
    with patch("requests.post", return_value=_fake_response(payload)) as mock_post:
        results = provider.predict(["CC(=O)O", "CCO"])

    assert len(results) == 1
    assert results[0].product_smiles == "CCOC(C)=O"
    assert results[0].confidence == 0.9
    assert results[0].source_label == "remote_api"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.test/predict"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"


def test_remote_api_provider_wraps_request_exceptions():
    import requests

    provider = providers_mod.RemoteReactionAPIProvider(base_url="https://example.test", api_key="k")
    with patch("requests.post", side_effect=requests.exceptions.Timeout("slow")):
        with pytest.raises(providers_mod.ReactionPredictionError, match="timed out"):
            provider.predict(["CCO"])


def test_build_default_providers_has_two_methods():
    provider_map = providers_mod.build_default_providers(BUNDLED_TEMPLATES)
    assert set(provider_map) == {"Templates", "Remote API"}


# --- templates contributed by a plugin --------------------------------------
#
# `ARCHITECTURE.md` recorded this as "an extensibility point with nothing
# built on them yet ... a real gap, not silently dropped". These cover the
# third source: bundled file, user file, and now another plugin.

_ESTERIFICATION = "[C:1](=O)[OH:2].[OH:3][C:4]>>[C:1](=O)[O:3][C:4]"


def _service():
    from openchem.services.reaction_template_service import ReactionTemplateService

    return ReactionTemplateService()


def _template(name="Esterification", smarts=_ESTERIFICATION):
    from openchem.services.reaction_template_service import ReactionTemplate

    return ReactionTemplate(name=name, smarts=smarts)


def test_a_registered_template_carries_the_plugin_that_supplied_it():
    """A prediction has to be able to say which rule produced it, and
    "Esterification" alone does not distinguish two plugins shipping a
    template of that name."""
    service = _service()
    service.register("acme_reactions", [_template()])

    stored = service.all_templates()[0]

    assert stored.source_id == "acme_reactions"
    assert stored.source_label == "Esterification (acme_reactions)"
    stored.source_label.encode("cp1252")  # it reaches a result line


def test_registering_again_replaces_that_plugins_set_and_no_others():
    """Re-registering is how a plugin updates its library. It must not
    disturb anybody else's."""
    service = _service()
    service.register("first", [_template("A")])
    service.register("second", [_template("B")])

    service.register("first", [_template("A2"), _template("A3")])

    names = sorted(t.name for t in service.all_templates())
    assert names == ["A2", "A3", "B"]


def test_two_plugins_may_ship_the_same_NAME_without_one_disappearing():
    """Different SMARTS under one name is a real case, and collapsing
    them would silently lose a rule somebody installed. De-duplication
    belongs at the PRODUCT level, which the provider already does."""
    service = _service()
    service.register("one", [_template("Esterification", _ESTERIFICATION)])
    service.register("two", [_template("Esterification", "[C:1]=[O:2]>>[C:1][O:2]")])

    assert len(service.all_templates()) == 2
    assert len({t.source_label for t in service.all_templates()}) == 2


def test_unloading_a_plugin_removes_exactly_its_templates():
    """The transactional unwind every other registrar gets."""
    service = _service()
    service.register("stays", [_template("Kept")])
    service.register("goes", [_template("Removed")])

    service.unregister_source("goes")

    assert [t.name for t in service.all_templates()] == ["Kept"]


def test_the_provider_applies_a_template_a_plugin_registered(tmp_path):
    """End to end: the namespace is decorative unless the provider
    actually reacts with what was registered."""
    bundled = tmp_path / "empty.json"
    bundled.write_text("[]", encoding="utf-8")
    service = _service()
    service.register("acme", [_template()])
    provider = providers_mod.RDKitTemplateProvider(bundled, service)

    predictions = provider.predict(["CC(=O)O", "CCO"])

    assert predictions
    assert any("acme" in p.source_label for p in predictions)
    # Deterministic, so no invented confidence -- unchanged by this work.
    assert all(p.confidence is None for p in predictions)


def test_a_template_registered_AFTER_the_provider_is_built_still_applies(tmp_path):
    """**Why the templates are read live rather than snapshotted.**
    Plugin load order is not something a template author should have to
    reason about, and a provider built before the contributing plugin
    activates would silently ignore it."""
    bundled = tmp_path / "empty.json"
    bundled.write_text("[]", encoding="utf-8")
    service = _service()
    provider = providers_mod.RDKitTemplateProvider(bundled, service)
    assert provider.predict(["CC(=O)O", "CCO"]) == []

    service.register("late_plugin", [_template()])

    assert provider.predict(["CC(=O)O", "CCO"])


def test_a_provider_with_no_registry_still_works(tmp_path):
    """The service is optional so the providers stay constructible
    without a whole ServiceContainer -- the same reason `kapustinskii`
    takes ions rather than a molecule."""
    bundled = tmp_path / "one.json"
    bundled.write_text(
        json.dumps([{"name": "Esterification", "smarts": _ESTERIFICATION}]), encoding="utf-8"
    )

    provider = providers_mod.RDKitTemplateProvider(bundled)

    assert provider.predict(["CC(=O)O", "CCO"])


def test_the_registrar_records_a_rollback_so_unload_removes_the_templates():
    """**The claim that matters for a plugin namespace**: everything
    registered through the context is unwound exactly on unload, or a
    disabled plugin keeps reacting. Tested on the registrar directly --
    building a whole `PluginContext` needs a ServiceContainer, a
    UIRegistry and Settings, and the rollback is the part under test."""
    from openchem.plugins.context import _ReactionTemplateRegistrar

    service = _service()
    rollbacks: list = []
    registrar = _ReactionTemplateRegistrar(service, "acme", rollbacks)

    registrar.register([_template()])
    assert len(rollbacks) == 1
    assert registrar.all_templates()  # readable, so the reaction plugin can apply them

    for rollback in rollbacks:
        rollback()

    assert service.all_templates() == []
