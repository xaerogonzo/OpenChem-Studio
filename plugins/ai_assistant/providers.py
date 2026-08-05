from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .tools import ToolDefinition


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(slots=True)
class AIMessage:
    role: str  # "user", "assistant", or "tool" (a tool's result, fed back)
    content: str
    # Only set on an "assistant" message that requested tool calls (the
    # model's own tool-use turn) -- carried so a later provider.complete()
    # call in the same tool loop can re-serialize it in that provider's
    # own wire format.
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Only set on a "tool" role message: which tool_calls[i].id this is
    # the result for.
    tool_call_id: str | None = None


@dataclass(slots=True)
class AIRequest:
    system_context: str
    messages: list[AIMessage]
    model: str
    api_key: str


@dataclass(slots=True)
class AIResponse:
    text: str
    # Non-empty means the model wants these tools run before it can finish
    # replying -- the caller (AIAssistantPanel) executes each locally and
    # calls complete() again with the results appended, never handing tool
    # execution to the provider itself.
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class AIProviderError(Exception):
    """Raised when a provider can't produce a response — missing SDK,
    missing/bad API key, or a network/API failure. Always caught by the
    panel and shown as an inline chat message, never allowed to propagate
    into a crash.
    """


class AIProvider(ABC):
    """Plugin-local provider abstraction.

    Deliberately not part of `openchem.plugins.interfaces` — core never
    needs to know this exists, since the AI assistant is a bundled plugin,
    not a core feature (see docs/PLUGIN_SDK.md / docs/ARCHITECTURE.md for why).
    """

    provider_id: str
    default_model: str
    # Most providers need an Anthropic/OpenAI-style API key; ClaudeCLIProvider
    # below authenticates via a locally-logged-in `claude` CLI session
    # instead, so _ProviderSettingsDialog (panel.py) uses this to decide
    # whether to even show an API key field.
    requires_api_key: bool = True
    # Anthropic and OpenAI-compatible SDKs support tool-calling natively;
    # ClaudeCLIProvider's single-shot `--tools ""` text-completion mode
    # does not (and must not gain arbitrary tool access here -- that flag
    # disables Claude Code's OWN tools, unrelated to this app-level
    # tool-calling loop). AIAssistantPanel checks this before ever passing
    # `tools=` into complete().
    supports_tools: bool = False

    @abstractmethod
    def complete(self, request: AIRequest, tools: list[ToolDefinition] | None = None) -> AIResponse:
        """Send `request` and return the full reply. Synchronous — callers
        (panel.py) are responsible for running this off the GUI thread.
        `tools`, when the provider's `supports_tools` is True, are offered
        to the model — a returned `AIResponse.tool_calls` means the model
        wants them run before it can finish; providers that don't support
        tools ignore this parameter."""

    def stream(
        self,
        request: AIRequest,
        on_chunk: Callable[[str], None],
        tools: list[ToolDefinition] | None = None,
    ) -> AIResponse:
        """Like `complete()`, but calls `on_chunk(text_fragment)` as text
        arrives instead of only returning it all at the end. Default
        implementation here is exactly today's non-streaming behavior — a
        single `on_chunk` call with the whole reply — so a provider that
        doesn't override this (`ClaudeCLIProvider`, whose CLI invocation
        has no incremental-output mode this app uses) behaves identically
        to before streaming existed, via inheritance rather than a special
        case in the caller."""
        response = self.complete(request, tools)
        on_chunk(response.text)
        return response


def _anthropic_messages(messages: list[AIMessage]) -> list[dict]:
    """Serializes the generic `AIMessage` list into Anthropic's own wire
    shape. A plain user/assistant text message stays a simple
    `{"role": ..., "content": <str>}` (unchanged from before tool-calling
    existed) -- only a message that's part of a tool-call/result exchange
    gets Anthropic's structured content-block form.
    """
    serialized = []
    for message in messages:
        if message.role == "tool":
            serialized.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
                    ],
                }
            )
        elif message.tool_calls:
            content = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            content.extend(
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input} for tc in message.tool_calls
            )
            serialized.append({"role": "assistant", "content": content})
        else:
            serialized.append({"role": message.role, "content": message.content})
    return serialized


def _anthropic_response(message) -> AIResponse:
    """Shared parsing for both `AnthropicProvider.complete()` (a plain
    `Message`) and `.stream()` (a `Message` from `stream.get_final_message()`
    -- same shape, so one parser covers both)."""
    text = "".join(block.text for block in message.content if hasattr(block, "text"))
    tool_calls = [
        ToolCall(id=block.id, name=block.name, input=block.input)
        for block in message.content
        if getattr(block, "type", None) == "tool_use"
    ]
    stop_reason = message.stop_reason if isinstance(message.stop_reason, str) else "end_turn"
    return AIResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)


def _anthropic_create_kwargs(request: AIRequest, default_model: str, tools: list[ToolDefinition] | None) -> dict:
    kwargs = dict(
        model=request.model or default_model,
        max_tokens=1024,
        system=request.system_context,
        messages=_anthropic_messages(request.messages),
    )
    if tools:
        kwargs["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools
        ]
    return kwargs


class AnthropicProvider(AIProvider):
    provider_id = "anthropic"
    default_model = "claude-sonnet-4-5"
    supports_tools = True

    def complete(self, request: AIRequest, tools: list[ToolDefinition] | None = None) -> AIResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise AIProviderError(
                "The 'anthropic' package is not installed. Run: uv sync --extra ai"
            ) from exc
        if not request.api_key:
            raise AIProviderError("No Anthropic API key configured.")

        try:
            client = anthropic.Anthropic(api_key=request.api_key)
            message = client.messages.create(**_anthropic_create_kwargs(request, self.default_model, tools))
        except Exception as exc:  # noqa: BLE001 - surface any SDK/network error uniformly
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        return _anthropic_response(message)

    def stream(
        self,
        request: AIRequest,
        on_chunk: Callable[[str], None],
        tools: list[ToolDefinition] | None = None,
    ) -> AIResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise AIProviderError(
                "The 'anthropic' package is not installed. Run: uv sync --extra ai"
            ) from exc
        if not request.api_key:
            raise AIProviderError("No Anthropic API key configured.")

        try:
            client = anthropic.Anthropic(api_key=request.api_key)
            # `.text_stream` only ever yields text deltas -- tool_use
            # blocks (and their incrementally-streamed input JSON) arrive
            # through separate stream events this app doesn't need to
            # observe live, since `get_final_message()` returns the
            # complete assembled Message (text AND any tool_use blocks)
            # once the stream ends.
            with client.messages.stream(
                **_anthropic_create_kwargs(request, self.default_model, tools)
            ) as message_stream:
                for text in message_stream.text_stream:
                    on_chunk(text)
                message = message_stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 - surface any SDK/network error uniformly
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        return _anthropic_response(message)


def _openai_messages(messages: list[AIMessage]) -> list[dict]:
    """Serializes the generic `AIMessage` list into the OpenAI Chat
    Completions wire shape. A plain user/assistant text message stays
    `{"role": ..., "content": <str>}` (unchanged from before tool-calling
    existed) -- only a message that's part of a tool-call/result exchange
    gets the structured `tool_calls`/`tool` form.
    """
    serialized = []
    for message in messages:
        if message.role == "tool":
            serialized.append(
                {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
            )
        elif message.tool_calls:
            serialized.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )
        else:
            serialized.append({"role": message.role, "content": message.content})
    return serialized


def _openai_create_kwargs(
    request: AIRequest, default_model: str, tools: list[ToolDefinition] | None
) -> dict:
    messages = [{"role": "system", "content": request.system_context}]
    messages.extend(_openai_messages(request.messages))
    kwargs = dict(model=request.model or default_model, messages=messages)
    if tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in tools
        ]
    return kwargs


def _openai_response(response) -> AIResponse:
    """Shared parsing for `OpenAICompatibleProvider.complete()`'s single
    non-streamed response object."""
    message = response.choices[0].message
    raw_tool_calls = getattr(message, "tool_calls", None)
    tool_calls = []
    if isinstance(raw_tool_calls, list):
        for tc in raw_tool_calls:
            try:
                tool_input = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, AttributeError):
                tool_input = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=tool_input))
    finish_reason = response.choices[0].finish_reason
    stop_reason = finish_reason if isinstance(finish_reason, str) else "stop"
    return AIResponse(text=message.content or "", tool_calls=tool_calls, stop_reason=stop_reason)


class OpenAICompatibleProvider(AIProvider):
    """Covers two of the three requested backends with one implementation:
    real OpenAI (default base_url) and local Ollama (its `/v1` endpoint
    speaks the same chat-completions shape) — configured, not subclassed.
    """

    supports_tools = True

    def __init__(self, provider_id: str, default_model: str, base_url: str | None = None) -> None:
        self.provider_id = provider_id
        self.default_model = default_model
        self._base_url = base_url

    def _resolve_api_key(self, request: AIRequest) -> str:
        # Ollama's OpenAI-compatible endpoint doesn't check the key, but the
        # SDK still requires a non-empty string to construct a client.
        api_key = request.api_key or ("ollama" if self._base_url else "")
        if not api_key:
            raise AIProviderError(f"No API key configured for {self.provider_id}.")
        return api_key

    def complete(self, request: AIRequest, tools: list[ToolDefinition] | None = None) -> AIResponse:
        try:
            import openai
        except ImportError as exc:
            raise AIProviderError(
                "The 'openai' package is not installed. Run: uv sync --extra ai"
            ) from exc

        api_key = self._resolve_api_key(request)
        try:
            client = openai.OpenAI(api_key=api_key, base_url=self._base_url)
            response = client.chat.completions.create(
                **_openai_create_kwargs(request, self.default_model, tools)
            )
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"{self.provider_id} request failed: {exc}") from exc

        return _openai_response(response)

    def stream(
        self,
        request: AIRequest,
        on_chunk: Callable[[str], None],
        tools: list[ToolDefinition] | None = None,
    ) -> AIResponse:
        try:
            import openai
        except ImportError as exc:
            raise AIProviderError(
                "The 'openai' package is not installed. Run: uv sync --extra ai"
            ) from exc

        api_key = self._resolve_api_key(request)
        create_kwargs = _openai_create_kwargs(request, self.default_model, tools)
        create_kwargs["stream"] = True

        text_parts: list[str] = []
        # Streamed tool calls arrive as partial fragments across multiple
        # chunks, matched by `index` (OpenAI's own streaming-tool-calls
        # convention) -- `function.name`/`.arguments` each accumulate as a
        # running string until the stream ends, not one full value per
        # chunk.
        tool_call_fragments: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        try:
            client = openai.OpenAI(api_key=api_key, base_url=self._base_url)
            for chunk in client.chat.completions.create(**create_kwargs):
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    on_chunk(delta.content)
                for tc_delta in delta.tool_calls or []:
                    fragment = tool_call_fragments.setdefault(
                        tc_delta.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc_delta.id:
                        fragment["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        fragment["name"] += tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        fragment["arguments"] += tc_delta.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"{self.provider_id} request failed: {exc}") from exc

        tool_calls = []
        for fragment in tool_call_fragments.values():
            try:
                tool_input = json.loads(fragment["arguments"]) if fragment["arguments"] else {}
            except json.JSONDecodeError:
                tool_input = {}
            tool_calls.append(ToolCall(id=fragment["id"], name=fragment["name"], input=tool_input))

        stop_reason = finish_reason if isinstance(finish_reason, str) else "stop"
        return AIResponse(text="".join(text_parts), tool_calls=tool_calls, stop_reason=stop_reason)


def _render_transcript_prompt(request: AIRequest) -> str:
    """The Claude Code CLI's `--print` mode is single-shot (one prompt in,
    one reply out) with no separate "conversation history" argument like
    the Anthropic/OpenAI SDKs -- render the whole exchange as a plain-text
    transcript fed over stdin instead."""
    lines = [f"User: {m.content}" if m.role == "user" else f"Assistant: {m.content}" for m in request.messages]
    lines.append("Assistant:")
    return "\n\n".join(lines)


class ClaudeCLIProvider(AIProvider):
    """Runs prompts through a locally-installed Claude Code CLI (`claude`)
    instead of the Anthropic API -- for users with a claude.ai subscription
    (Pro/Max) who don't have (or don't want to use) a separate, separately
    billed Anthropic API key. Confirmed live against the real CLI: `claude
    -p --tools "" --no-session-persistence --system-prompt "..."` fed a
    prompt over stdin returns a clean plain-text reply on stdout with
    nothing else attached, authenticated via whatever `claude` is already
    logged into (`claude auth status` shows authMethod "claude.ai" for a
    subscription login, vs. an API key) -- no separate configuration needed
    beyond having logged in once.

    `--tools ""` disables all of Claude Code's normal file/bash/etc. tool
    access for this call -- this provider is a plain text-completion
    backend, not a second agent loop, and must not be able to read or
    write the user's files just because a chat reply was requested.
    """

    provider_id = "claude_cli"
    default_model = ""  # blank = whatever `claude` itself is configured to default to
    requires_api_key = False

    def __init__(self, cli_path_resolver: Callable[[], str] | None = None) -> None:
        self._cli_path_resolver = cli_path_resolver

    def _resolve_executable(self) -> str | None:
        configured = self._cli_path_resolver() if self._cli_path_resolver else ""
        if configured and Path(configured).is_file():
            return configured
        return shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.exe")

    def complete(self, request: AIRequest, tools: list[ToolDefinition] | None = None) -> AIResponse:
        # `tools` is accepted for interface consistency but always ignored
        # -- `supports_tools = False` (inherited from AIProvider) means
        # AIAssistantPanel never actually passes any, and this single-shot
        # `--tools ""` text-completion mode has no tool-use protocol to
        # honor them with anyway.
        executable = self._resolve_executable()
        if executable is None:
            raise AIProviderError(
                "Claude Code CLI ('claude') was not found on PATH. Install it from "
                "https://claude.com/claude-code, run 'claude' once to log in with your "
                "Claude subscription, then set its path in Configure... if it's still "
                "not found automatically."
            )

        args = [executable, "-p", "--output-format", "text", "--tools", "", "--no-session-persistence"]
        if request.system_context:
            args += ["--system-prompt", request.system_context]
        if request.model:
            args += ["--model", request.model]

        try:
            result = subprocess.run(
                args,
                input=_render_transcript_prompt(request),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                # Run from a throwaway directory, not the user's project --
                # tools are disabled above anyway, but this is a second,
                # independent guard against this "chat completion" call
                # touching real files if that ever changed.
                cwd=tempfile.gettempdir(),
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AIProviderError(f"Failed to run Claude Code CLI: {exc}") from exc

        if result.returncode != 0:
            raise AIProviderError(
                "Claude Code CLI exited with an error: "
                f"{result.stderr.strip() or result.stdout.strip() or f'exit code {result.returncode}'}"
            )

        return AIResponse(text=result.stdout.strip())


def build_default_providers(cli_path_resolver: Callable[[], str] | None = None) -> dict[str, AIProvider]:
    """The four backends confirmed for V1. `cli_path_resolver` lets the
    caller (plugin.py) supply a live Settings-backed lookup for a
    manually-configured `claude` executable path, same pattern as
    VinaDockingProvider's `executable_path_resolver` in core -- optional
    since ClaudeCLIProvider falls back to PATH lookup on its own.
    """
    return {
        "anthropic": AnthropicProvider(),
        "openai": OpenAICompatibleProvider("openai", default_model="gpt-4o-mini"),
        "ollama": OpenAICompatibleProvider(
            "ollama", default_model="llama3.1", base_url="http://localhost:11434/v1"
        ),
        "claude_cli": ClaudeCLIProvider(cli_path_resolver=cli_path_resolver),
    }
