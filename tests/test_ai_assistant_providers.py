from __future__ import annotations

import types
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


def test_anthropic_provider_returns_tool_calls_when_model_requests_one():
    provider = providers_mod.AnthropicProvider()
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="validate [C]")],
        model="claude-test",
        api_key="sk-test",
    )
    tool = providers_mod.ToolDefinition(name="validate_smarts", description="d", input_schema={"type": "object"})

    tool_block = types.SimpleNamespace(type="tool_use", id="tool_1", name="validate_smarts", input={"pattern": "[C]"})
    fake_message = types.SimpleNamespace(content=[tool_block], stop_reason="tool_use")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message

    with patch("anthropic.Anthropic", return_value=fake_client):
        response = provider.complete(request, tools=[tool])

    assert response.text == ""
    assert response.stop_reason == "tool_use"
    assert response.tool_calls == [
        providers_mod.ToolCall(id="tool_1", name="validate_smarts", input={"pattern": "[C]"})
    ]
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["tools"] == [{"name": "validate_smarts", "description": "d", "input_schema": {"type": "object"}}]


def test_anthropic_provider_serializes_tool_call_and_result_messages():
    provider = providers_mod.AnthropicProvider()
    tool_call = providers_mod.ToolCall(id="tool_1", name="validate_smarts", input={"pattern": "[C]"})
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[
            providers_mod.AIMessage(role="user", content="validate [C]"),
            providers_mod.AIMessage(role="assistant", content="Checking.", tool_calls=[tool_call]),
            providers_mod.AIMessage(role="tool", content="Valid SMARTS pattern.", tool_call_id="tool_1"),
        ],
        model="claude-test",
        api_key="sk-test",
    )
    fake_block = MagicMock()
    fake_block.text = "It's valid."
    fake_message = types.SimpleNamespace(content=[fake_block], stop_reason="end_turn")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_message

    with patch("anthropic.Anthropic", return_value=fake_client):
        provider.complete(request)

    _, kwargs = fake_client.messages.create.call_args
    messages = kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "validate [C]"}
    assert messages[1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "tool_1", "name": "validate_smarts", "input": {"pattern": "[C]"}},
        ],
    }
    assert messages[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "tool_1", "content": "Valid SMARTS pattern."}],
    }


def test_anthropic_provider_streams_text_chunks_incrementally():
    provider = providers_mod.AnthropicProvider()
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="hello")],
        model="claude-test",
        api_key="sk-test",
    )

    text_block = types.SimpleNamespace(type="text", text="hi there")
    final_message = types.SimpleNamespace(content=[text_block], stop_reason="end_turn")

    fake_stream_ctx = MagicMock()
    fake_stream_ctx.__enter__.return_value = fake_stream_ctx
    fake_stream_ctx.__exit__.return_value = False
    fake_stream_ctx.text_stream = iter(["hi ", "there"])
    fake_stream_ctx.get_final_message.return_value = final_message

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = fake_stream_ctx

    received = []
    with patch("anthropic.Anthropic", return_value=fake_client):
        response = provider.stream(request, on_chunk=received.append)

    assert received == ["hi ", "there"]
    assert response.text == "hi there"
    assert response.stop_reason == "end_turn"


def test_openai_compatible_provider_returns_tool_calls_when_model_requests_one():
    provider = providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test")
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="validate [C]")],
        model="",
        api_key="sk-test",
    )
    tool = providers_mod.ToolDefinition(name="validate_smarts", description="d", input_schema={"type": "object"})

    fake_tool_call = types.SimpleNamespace(
        id="call_1", function=types.SimpleNamespace(name="validate_smarts", arguments='{"pattern": "[C]"}')
    )
    fake_message = types.SimpleNamespace(content=None, tool_calls=[fake_tool_call])
    fake_choice = types.SimpleNamespace(message=fake_message, finish_reason="tool_calls")
    fake_response = types.SimpleNamespace(choices=[fake_choice])
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    with patch("openai.OpenAI", return_value=fake_client):
        response = provider.complete(request, tools=[tool])

    assert response.text == ""
    assert response.stop_reason == "tool_calls"
    assert response.tool_calls == [
        providers_mod.ToolCall(id="call_1", name="validate_smarts", input={"pattern": "[C]"})
    ]
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {"name": "validate_smarts", "description": "d", "parameters": {"type": "object"}},
        }
    ]


def test_openai_compatible_provider_streams_text_and_accumulates_tool_calls():
    provider = providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test")
    request = providers_mod.AIRequest(
        system_context="ctx",
        messages=[providers_mod.AIMessage(role="user", content="hi")],
        model="",
        api_key="sk-test",
    )

    def _chunk(content=None, tool_call_deltas=None, finish_reason=None):
        delta = types.SimpleNamespace(content=content, tool_calls=tool_call_deltas)
        choice = types.SimpleNamespace(delta=delta, finish_reason=finish_reason)
        return types.SimpleNamespace(choices=[choice])

    # Tool-call arguments arrive fragmented across multiple chunks, all at
    # the same `index` -- matches OpenAI's own streaming-tool-calls shape.
    tc_delta_1 = types.SimpleNamespace(
        index=0, id="call_1", function=types.SimpleNamespace(name="validate_sm", arguments="")
    )
    tc_delta_2 = types.SimpleNamespace(
        index=0, id=None, function=types.SimpleNamespace(name="arts", arguments='{"pattern"')
    )
    tc_delta_3 = types.SimpleNamespace(
        index=0, id=None, function=types.SimpleNamespace(name=None, arguments=': "[C]"}')
    )

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter(
        [
            _chunk(content="Checking"),
            _chunk(content="..."),
            _chunk(tool_call_deltas=[tc_delta_1]),
            _chunk(tool_call_deltas=[tc_delta_2]),
            _chunk(tool_call_deltas=[tc_delta_3], finish_reason="tool_calls"),
        ]
    )

    received = []
    with patch("openai.OpenAI", return_value=fake_client):
        response = provider.stream(request, on_chunk=received.append)

    assert received == ["Checking", "..."]
    assert response.text == "Checking..."
    assert response.stop_reason == "tool_calls"
    assert response.tool_calls == [
        providers_mod.ToolCall(id="call_1", name="validate_smarts", input={"pattern": "[C]"})
    ]


def test_claude_cli_provider_stream_falls_back_to_a_single_chunk():
    """ClaudeCLIProvider never overrides stream() -- the base class default
    (complete() once, then one on_chunk call with the whole reply) is the
    behavior, confirmed here rather than assumed."""
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(system_context="", messages=[], model="", api_key="")
    fake_result = MagicMock(returncode=0, stdout="Benzene is C6H6.", stderr="")

    received = []
    with (
        patch("shutil.which", return_value="/usr/bin/claude"),
        patch("subprocess.run", return_value=fake_result),
    ):
        response = provider.stream(request, on_chunk=received.append)

    assert received == ["Benzene is C6H6."]
    assert response.text == "Benzene is C6H6."


def test_claude_cli_provider_does_not_support_tools():
    assert providers_mod.ClaudeCLIProvider().supports_tools is False
    assert providers_mod.AnthropicProvider().supports_tools is True
    assert providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test").supports_tools is True
