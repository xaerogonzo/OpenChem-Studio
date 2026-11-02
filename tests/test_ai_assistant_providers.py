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


def test_every_provider_takes_the_applications_tools():
    assert providers_mod.ClaudeCLIProvider().supports_tools is True
    assert providers_mod.AnthropicProvider().supports_tools is True
    assert providers_mod.OpenAICompatibleProvider("openai", default_model="gpt-test").supports_tools is True


# --- a local model is called cooler than the server's default, and nothing else changes ------------------------------------------------------------------------


def test_a_temperature_is_sent_only_where_a_provider_sets_one():
    request = providers_mod.AIRequest(system_context="ctx", messages=[], model="", api_key="k")
    assert "temperature" not in providers_mod._openai_create_kwargs(request, "m", None)
    assert providers_mod._openai_create_kwargs(request, "m", None, 0.2)["temperature"] == 0.2
    assert providers_mod._openai_create_kwargs(request, "m", None, 0.0)["temperature"] == 0.0, "zero is a temperature, not 'unset'"


def test_only_the_local_server_provider_asks_for_a_lower_temperature():
    """A live qwen2.5:14b run at the server's default (0.8 on Ollama) invented about seventy settings for one calculator and answered in Thai; the real OpenAI provider is left as it was."""
    built = providers_mod.build_default_providers()
    assert built["ollama"]._temperature == 0.2 and built["openai"]._temperature is None


def test_the_request_the_local_provider_streams_carries_its_temperature():
    provider = providers_mod.build_default_providers()["ollama"]
    request = providers_mod.AIRequest(system_context="ctx", messages=[], model="qwen2.5:14b", api_key="")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([])
    with patch("openai.OpenAI", return_value=fake_client):
        provider.stream(request, lambda _text: None)
    assert fake_client.chat.completions.create.call_args.kwargs["temperature"] == 0.2


def test_the_non_streaming_request_carries_the_temperature_too():
    provider = providers_mod.build_default_providers()["ollama"]
    request = providers_mod.AIRequest(system_context="ctx", messages=[], model="qwen2.5:14b", api_key="")
    fake_choice = MagicMock()
    fake_choice.message.content = "ok"
    fake_choice.message.tool_calls = None
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response
    with patch("openai.OpenAI", return_value=fake_client):
        provider.complete(request)
    assert fake_client.chat.completions.create.call_args.kwargs["temperature"] == 0.2


# --- the Claude CLI takes this application's tools through a written protocol ---------------------------------------------------------------------------------


import json as _json  # noqa: E402
from pathlib import Path  # noqa: E402

from ai_assistant.tools import ToolDefinition  # noqa: E402

_CLI_TOOLS = [
    ToolDefinition("run_calculator", "Ask for a calculator to be run.", {"type": "object", "properties": {"calculator_id": {"type": "string"}}, "required": ["calculator_id"]}),
    ToolDefinition("read_results", "Read what is computed.", {"type": "object", "properties": {}}),
]


def _block(calls) -> str:
    return "```tool_calls\n" + _json.dumps(calls) + "\n```"


def test_the_system_prompt_gives_the_protocol_first_then_the_panels_prompt_then_each_tool_with_its_schema():
    request = providers_mod.AIRequest(system_context="PANEL PROMPT", messages=[], model="", api_key="")
    text = providers_mod._cli_system_prompt(request, _CLI_TOOLS)
    assert text.startswith("HOW TO USE THE TOOLS IN THIS CHAT") and "```tool_calls" in text and "Never write a tool result yourself" in text
    assert "never write anything after the block" in text
    assert text.index("HOW TO USE THE TOOLS") < text.index("PANEL PROMPT") < text.index("The tools you may call")
    for tool in _CLI_TOOLS:
        assert f"- {tool.name}: {tool.description}" in text and _json.dumps(tool.input_schema) in text


def test_the_transcript_shows_what_the_assistant_asked_for_in_the_form_it_is_asked_to_write_it_and_what_it_was_told():
    call = providers_mod.ToolCall(id="cli-1", name="run_calculator", input={"calculator_id": "orca.sp"})
    request = providers_mod.AIRequest(
        system_context="",
        messages=[
            providers_mod.AIMessage("user", "Run it."),
            providers_mod.AIMessage("assistant", "Asking.", tool_calls=[call]),
            providers_mod.AIMessage("tool", '{"ok": false}', tool_call_id="cli-1"),
        ],
        model="",
        api_key="",
    )
    text = providers_mod._render_transcript_prompt(request)
    assert "User: Run it." in text and "Assistant: Asking." in text
    assert _block([{"name": "run_calculator", "input": {"calculator_id": "orca.sp"}}]) in text
    assert 'Tool result (run_calculator): {"ok": false}' in text and text.endswith("\n\nAssistant:")


def test_the_first_block_becomes_the_tool_calls_and_the_text_before_it_the_reply():
    reply = "Looking that up.\n" + _block([{"name": "run_calculator", "input": {"calculator_id": "orca.sp"}}, {"name": "read_results", "input": {}}])
    response = providers_mod._parse_cli_reply(reply, _CLI_TOOLS)
    assert response.text == "Looking that up." and response.stop_reason == "tool_use"
    assert [(c.name, c.input) for c in response.tool_calls] == [("run_calculator", {"calculator_id": "orca.sp"}), ("read_results", {})]
    assert len({c.id for c in response.tool_calls}) == 2 and all(c.id.startswith("cli-") for c in response.tool_calls)


def test_nothing_after_the_block_counts_not_even_a_result_the_model_invented():
    reply = _block([{"name": "read_results", "input": {}}]) + '\n\nTool result (read_results): {"ok": true, "value": 42}\n' + _block([{"name": "run_calculator", "input": {"calculator_id": "orca.sp"}}])
    response = providers_mod._parse_cli_reply(reply, _CLI_TOOLS)
    assert [c.name for c in response.tool_calls] == ["read_results"] and "42" not in response.text and response.text == ""


def test_a_reply_with_no_block_is_a_final_answer():
    response = providers_mod._parse_cli_reply("  Water is H2O.\n", _CLI_TOOLS)
    assert (response.text, response.tool_calls, response.stop_reason) == ("Water is H2O.", [], "end_turn")


def test_a_call_to_a_tool_that_is_not_offered_is_not_run_and_the_others_are():
    reply = _block([{"name": "delete_everything", "input": {}}, {"name": "read_results", "input": "not an object"}, "junk"])
    response = providers_mod._parse_cli_reply(reply, _CLI_TOOLS)
    assert [(c.name, c.input) for c in response.tool_calls] == [("read_results", {})]


def test_a_block_that_does_not_hold_to_the_protocol_is_shown_to_the_user_and_never_lost():
    for reply in (
        "Sure.\n```tool_calls\nnot json\n```",
        "Sure.\n" + _block({"name": "read_results"}),  # an object, not a list
        "Sure.\n" + _block([{"name": "delete_everything", "input": {}}]),  # only tools that are not offered
    ):
        response = providers_mod._parse_cli_reply(reply, _CLI_TOOLS)
        assert response.tool_calls == [] and response.text == reply.strip() and response.stop_reason == "end_turn", reply


def test_the_tag_is_read_whatever_its_case_and_line_endings():
    reply = "Go.\r\n```Tool_Calls  \r\n[{\"name\": \"read_results\", \"input\": {}}]\r\n```\r\n"
    response = providers_mod._parse_cli_reply(reply, _CLI_TOOLS)
    assert [c.name for c in response.tool_calls] == ["read_results"] and response.text == "Go."


def _run_cli(provider, request, tools, stdout):
    """Call `complete` with `subprocess.run` replaced, returning what was run and what the system-prompt file held while it ran."""
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        if "--system-prompt-file" in args:
            seen["prompt_file_text"] = Path(args[args.index("--system-prompt-file") + 1]).read_text(encoding="utf-8")
        return MagicMock(returncode=0, stdout=stdout, stderr="")

    with patch.object(providers_mod.ClaudeCLIProvider, "_resolve_executable", return_value="claude"), patch("subprocess.run", side_effect=fake_run):
        response = provider.complete(request, tools)
    return response, seen


def test_a_tool_call_runs_the_cli_with_its_own_tools_off_a_prompt_file_and_a_scratch_directory():
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(system_context="PANEL PROMPT", messages=[providers_mod.AIMessage("user", "hi")], model="sonnet", api_key="")
    response, seen = _run_cli(provider, request, _CLI_TOOLS, "Ok.\n" + _block([{"name": "read_results", "input": {}}]))
    args = seen["args"]
    assert args[:2] == ["claude", "-p"] and args[args.index("--tools") + 1] == "" and args[args.index("--output-format") + 1] == "text"
    assert args[args.index("--model") + 1] == "sonnet" and "--json-schema" not in args
    for flag in ("--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config", "--no-chrome"):
        assert flag in args, flag
    assert args[args.index("--setting-sources") + 1] == ""
    assert "--system-prompt" not in args, "the prompt is in a file: a Windows command line holds 32,768 characters"
    assert "PANEL PROMPT" in seen["prompt_file_text"] and "run_calculator" in seen["prompt_file_text"]
    assert seen["kwargs"]["input"].endswith("\n\nAssistant:")
    assert Path(seen["kwargs"]["cwd"]).name.startswith("openchem-claude-cli-") and not Path(seen["kwargs"]["cwd"]).exists(), "a scratch directory, removed afterwards"
    assert response.text == "Ok." and [c.name for c in response.tool_calls] == ["read_results"]


def test_with_no_tools_the_cli_is_still_a_plain_text_completion_with_the_same_isolation():
    provider = providers_mod.ClaudeCLIProvider(cli_path_resolver=lambda: "")
    request = providers_mod.AIRequest(system_context="PANEL PROMPT", messages=[providers_mod.AIMessage("user", "hi")], model="", api_key="")
    response, seen = _run_cli(provider, request, None, "plain reply\n")
    args = seen["args"]
    assert args[args.index("--output-format") + 1] == "text" and args[args.index("--system-prompt") + 1] == "PANEL PROMPT"
    assert "--system-prompt-file" not in args and "--disable-slash-commands" in args and args[args.index("--tools") + 1] == ""
    assert response.text == "plain reply" and response.tool_calls == [] and seen["kwargs"]["input"].endswith("\n\nAssistant:")
