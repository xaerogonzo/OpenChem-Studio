from __future__ import annotations

from unittest.mock import MagicMock, patch

import ai_assistant.providers as providers_mod
import pytest


def test_anthropic_provider_builds_request_and_parses_response():
    provider = providers_mod.AnthropicProvider()
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="hello")],
        model="claude-test",
        api_key="sk-test",
    )

    fake_block = MagicMock()
    fake_block.text = "hi there"
    fake_message = MagicMock()
    fake_message.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message

    with patch("anthropic.Anthropic", return_value=fake_client) as mock_ctor:
        response = provider.complete(request)

    assert response.text == "hi there"
    mock_ctor.assert_called_once_with(api_key="sk-test")
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["model"] == "claude-test"
    assert kwargs["system"] == "ctx"
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]


def test_anthropic_provider_requires_api_key():
    provider = providers_mod.AnthropicProvider()
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")
    with pytest.raises(providers_mod.AIProviderError):
        provider.complete(request)


def test_anthropic_provider_wraps_sdk_errors():
    provider = providers_mod.AnthropicProvider()
    request = providers_mod.AIRequest(system_context="", messages=[], model="m", api_key="key")
    with patch("anthropic.Anthropic", side_effect=RuntimeError("boom")):
        with pytest.raises(providers_mod.AIProviderError):
            provider.complete(request)


def test_openai_compatible_provider_builds_request_and_parses_response():
    provider = providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test")
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="hello")],
        model="",
        api_key="sk-test",
    )

    fake_choice = MagicMock()
    fake_choice.message.content = "hi from openai"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch("openai.OpenAI", return_value=fake_client) as mock_ctor:
        response = provider.complete(request)

    assert response.text == "hi from openai"
    mock_ctor.assert_called_once_with(api_key="sk-test", base_url=None)
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-test"  # falls back to default_model since request.model == ""
    assert kwargs["messages"][0] == {"role": "system", "content": "ctx"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hello"}


def test_ollama_provider_uses_dummy_key_when_none_configured():
    provider = providers_mod.OpenAICompatibleProvider(
        "ollama", default_model="llama3.1", base_url="http://localhost:11434/v1"
    )
    request = providers_mod.AIRequest(system_context="ctx", messages=[], model="", api_key="")

    fake_choice = MagicMock()
    fake_choice.message.content = "ok"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch("openai.OpenAI", return_value=fake_client) as mock_ctor:
        response = provider.complete(request)

    assert response.text == "ok"
    mock_ctor.assert_called_once_with(api_key="ollama", base_url="http://localhost:11434/v1")


def test_openai_provider_with_no_key_and_no_base_url_raises():
    provider = providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test")
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")
    with pytest.raises(providers_mod.AIProviderError):
        provider.complete(request)


def test_build_default_providers_has_three_backends():
    provider_map = providers_mod.build_default_providers()
    assert set(provider_map) == {"anthropic", "openai", "ollama"}
