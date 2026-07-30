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


def test_build_default_providers_has_four_backends():
    provider_map = providers_mod.build_default_providers()
    assert set(provider_map) == {"anthropic", "openai", "ollama", "claude_cli"}


def test_claude_cli_provider_does_not_require_an_api_key():
    assert providers_mod.ClaudeCLIProvider().requires_api_key is False
    assert providers_mod.AnthropicProvider().requires_api_key is True


def test_claude_cli_provider_raises_clear_error_when_executable_not_found():
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")

    with patch("shutil.which", return_value=None):
        with pytest.raises(providers_mod.AIProviderError, match="not found on PATH"):
            provider.complete(request)


def test_claude_cli_provider_invokes_cli_headless_with_tools_disabled():
    """Regression coverage for the exact invocation shape confirmed live
    against a real `claude` install: prompt fed over stdin (not as a CLI
    argument, to sidestep shell-length/quoting limits), tools fully
    disabled (`--tools ""`) since this is a plain text-completion call, not
    a second agent loop that should be able to touch files."""
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(
        system_context="You are a chemistry assistant.",
        messages=[
            providers_mod.AIMessage(role="user", content="What is benzene?"),
        ],
        model="sonnet",
        api_key="",
    )

    fake_result = MagicMock(returncode=0, stdout="Benzene is C6H6.\n", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/claude"),
        patch("subprocess.run", return_value=fake_result) as mock_run,
    ):
        response = provider.complete(request)

    assert response.text == "Benzene is C6H6."
    args, kwargs = mock_run.call_args
    invoked_args = args[0]
    assert invoked_args[0] == "/usr/bin/claude"
    assert "-p" in invoked_args
    assert "--tools" in invoked_args
    assert invoked_args[invoked_args.index("--tools") + 1] == ""
    assert "--system-prompt" in invoked_args
    assert invoked_args[invoked_args.index("--system-prompt") + 1] == "You are a chemistry assistant."
    assert "--model" in invoked_args
    assert invoked_args[invoked_args.index("--model") + 1] == "sonnet"
    assert "What is benzene?" in kwargs["input"]


def test_claude_cli_provider_prefers_configured_path_over_path_lookup(tmp_path):
    configured = tmp_path / "claude.exe"
    configured.write_text("fake")
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: str(configured))
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")

    fake_result = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("subprocess.run", return_value=fake_result) as mock_run:
        provider.complete(request)

    assert mock_run.call_args[0][0][0] == str(configured)


def test_claude_cli_provider_wraps_nonzero_exit_as_error():
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")

    fake_result = MagicMock(returncode=1, stdout="", stderr="not logged in")
    with (
        patch("shutil.which", return_value="/usr/bin/claude"),
        patch("subprocess.run", return_value=fake_result),
    ):
        with pytest.raises(providers_mod.AIProviderError, match="not logged in"):
            provider.complete(request)
