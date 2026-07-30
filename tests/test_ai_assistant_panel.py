from __future__ import annotations

from ai_assistant.panel import MAX_TOOL_ITERATIONS
from ai_assistant.providers import AIMessage, AIProvider, AIRequest, AIResponse, ToolCall

from test_ai_assistant_plugin import _make_manager


class _StubToolProvider(AIProvider):
    """A minimal AIProvider whose stream() returns a scripted sequence of
    AIResponse objects -- exercises AIAssistantPanel._run_completion's
    tool-calling loop without needing real Anthropic/OpenAI wire-format
    mocking (that's covered separately in test_ai_assistant_providers.py).
    """

    provider_id = "stub"
    default_model = "stub-model"
    supports_tools = True

    def __init__(self, responses: list[AIResponse]) -> None:
        self._responses = list(responses)
        self.stream_calls: list[AIRequest] = []

    def complete(self, request: AIRequest, tools=None) -> AIResponse:
        raise AssertionError("panel orchestration must call stream(), not complete()")

    def stream(self, request: AIRequest, on_chunk, tools=None) -> AIResponse:
        self.stream_calls.append(request)
        response = self._responses.pop(0)
        if response.text:
            on_chunk(response.text)
        return response


def test_run_completion_executes_tool_call_and_returns_final_response(tmp_path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["AI Assistant"]

    tool_call = ToolCall(id="t1", name="validate_smarts", input={"pattern": "[C]"})
    provider = _StubToolProvider(
        responses=[
            AIResponse(text="Let me check.", tool_calls=[tool_call], stop_reason="tool_use"),
            AIResponse(text="It's a valid SMARTS pattern.", stop_reason="end_turn"),
        ]
    )
    chunks: list[str] = []

    result = panel._run_completion(
        provider, "system context", [AIMessage(role="user", content="Is [C] valid?")], "model", "key", chunks.append
    )

    assert result.text == "It's a valid SMARTS pattern."
    assert result.tool_calls == []
    assert len(provider.stream_calls) == 2
    # The tool's real result made it back into the second call's messages.
    second_request_messages = provider.stream_calls[1].messages
    tool_result_message = next(m for m in second_request_messages if m.role == "tool")
    assert tool_result_message.tool_call_id == "t1"
    assert "Valid SMARTS pattern" in tool_result_message.content
    assert chunks == ["Let me check.", "It's a valid SMARTS pattern."]


def test_run_completion_stops_at_max_tool_iterations(tmp_path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["AI Assistant"]

    # A provider that ALWAYS wants another tool call -- must not loop forever.
    tool_call = ToolCall(id="t1", name="validate_smarts", input={"pattern": "[C]"})

    class _AlwaysToolProvider(AIProvider):
        provider_id = "stub"
        default_model = "stub-model"
        supports_tools = True
        stream_call_count = 0

        def complete(self, request, tools=None):
            raise AssertionError("must call stream(), not complete()")

        def stream(self, request, on_chunk, tools=None):
            self.stream_call_count += 1
            return AIResponse(text="", tool_calls=[tool_call], stop_reason="tool_use")

    provider = _AlwaysToolProvider()
    panel._run_completion(provider, "sys", [AIMessage(role="user", content="hi")], "model", "key", lambda c: None)

    assert provider.stream_call_count == MAX_TOOL_ITERATIONS


def test_run_completion_skips_tool_loop_for_provider_without_tool_support(tmp_path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["AI Assistant"]

    class _NoToolsProvider(AIProvider):
        provider_id = "stub"
        default_model = "stub-model"
        supports_tools = False
        received_tools = "unset"

        def complete(self, request, tools=None):
            raise AssertionError("must call stream(), not complete()")

        def stream(self, request, on_chunk, tools=None):
            self.received_tools = tools
            on_chunk("plain reply")
            return AIResponse(text="plain reply")

    provider = _NoToolsProvider()
    result = panel._run_completion(
        provider, "sys", [AIMessage(role="user", content="hi")], "model", "key", lambda c: None
    )

    assert provider.received_tools is None
    assert result.text == "plain reply"
