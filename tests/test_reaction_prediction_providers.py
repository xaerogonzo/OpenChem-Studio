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
