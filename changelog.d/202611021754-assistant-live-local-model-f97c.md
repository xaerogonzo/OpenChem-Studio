### The assistant answers in the language you write in, and a local Ollama model is asked at a lower temperature
- The system prompt now says to reply in the language the user writes in (English if they write English). A live `qwen2.5:14b` run answered an English question in Thai when nothing said which language to use.
- The Ollama provider asks for a temperature of 0.2 instead of the server's default (0.8 on Ollama), which was loose for tool calling: the same run invented about seventy settings for one calculator. The OpenAI and Anthropic providers are unchanged.
- The drive harness's `ai_send` step takes `"live": {"provider": ..., "model": ...}` to send through a real provider and record what it did (`benchmarks/visual/ai_live_ollama.json`).
