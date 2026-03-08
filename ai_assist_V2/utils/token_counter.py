"""Token counting utilities using tiktoken."""

from __future__ import annotations

import tiktoken

# cl100k_base is used by GPT-4 / modern models. Close enough for estimation.
_ENCODING_NAME = "cl100k_base"


class TokenCounter:
    """Estimates token counts for text strings."""

    def __init__(self) -> None:
        self._enc = tiktoken.get_encoding(_ENCODING_NAME)

    def count(self, text: str) -> int:
        """Return the number of tokens in *text*."""
        if not text:
            return 0
        return len(self._enc.encode(text))

    def count_messages(self, messages: list[dict]) -> int:
        """Estimate tokens for an OpenAI-style message list."""
        total = 0
        for msg in messages:
            # 4 tokens per message overhead (role, separators, etc.)
            total += 4 + self.count(msg.get("content", ""))
        total += 2  # reply prime
        return total


# Module-level singleton
_counter: TokenCounter | None = None


def get_counter() -> TokenCounter:
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter
