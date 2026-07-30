from __future__ import annotations

import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(slots=True)
class AIMessage:
    role: str  # "user" or "assistant"
    content: str


@dataclass(slots=True)
class AIRequest:
    system_context: str
    messages: list[AIMessage]
    model: str
    api_key: str


@dataclass(slots=True)
class AIResponse:
    text: str


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
    not a core feature (see PLUGIN_SDK.md / ARCHITECTURE.md for why).
    """

    provider_id: str
    default_model: str
    # Most providers need an Anthropic/OpenAI-style API key; ClaudeCLIProvider
    # below authenticates via a locally-logged-in `claude` CLI session
    # instead, so _ProviderSettingsDialog (panel.py) uses this to decide
    # whether to even show an API key field.
    requires_api_key: bool = True

    @abstractmethod
    def complete(self, request: AIRequest) -> AIResponse:
        """Send `request` and return the full reply. Synchronous — callers
        (panel.py) are responsible for running this off the GUI thread."""


class AnthropicProvider(AIProvider):
    provider_id = "anthropic"
    default_model = "claude-sonnet-4-5"

    def complete(self, request: AIRequest) -> AIResponse:
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
            message = client.messages.create(
                model=request.model or self.default_model,
                max_tokens=1024,
                system=request.system_context,
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            )
        except Exception as exc:  # noqa: BLE001 - surface any SDK/network error uniformly
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        return AIResponse(text=text)


class OpenAICompatibleProvider(AIProvider):
    """Covers two of the three requested backends with one implementation:
    real OpenAI (default base_url) and local Ollama (its `/v1` endpoint
    speaks the same chat-completions shape) — configured, not subclassed.
    """

    def __init__(self, provider_id: str, default_model: str, base_url: str | None = None) -> None:
        self.provider_id = provider_id
        self.default_model = default_model
        self._base_url = base_url

    def complete(self, request: AIRequest) -> AIResponse:
        try:
            import openai
        except ImportError as exc:
            raise AIProviderError(
                "The 'openai' package is not installed. Run: uv sync --extra ai"
            ) from exc

        # Ollama's OpenAI-compatible endpoint doesn't check the key, but the
        # SDK still requires a non-empty string to construct a client.
        api_key = request.api_key or ("ollama" if self._base_url else "")
        if not api_key:
            raise AIProviderError(f"No API key configured for {self.provider_id}.")

        messages = [{"role": "system", "content": request.system_context}]
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        try:
            client = openai.OpenAI(api_key=api_key, base_url=self._base_url)
            response = client.chat.completions.create(
                model=request.model or self.default_model,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"{self.provider_id} request failed: {exc}") from exc

        return AIResponse(text=response.choices[0].message.content or "")


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

    def complete(self, request: AIRequest) -> AIResponse:
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
