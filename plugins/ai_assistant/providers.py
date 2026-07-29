from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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


def build_default_providers() -> dict[str, AIProvider]:
    """The three backends confirmed for V1 — two classes, three configs."""
    return {
        "anthropic": AnthropicProvider(),
        "openai": OpenAICompatibleProvider("openai", default_model="gpt-4o-mini"),
        "ollama": OpenAICompatibleProvider(
            "ollama", default_model="llama3.1", base_url="http://localhost:11434/v1"
        ),
    }
