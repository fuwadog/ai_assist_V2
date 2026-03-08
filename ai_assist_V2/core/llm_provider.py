"""NVIDIA / OpenAI-compatible LLM provider."""

from __future__ import annotations

import time
from typing import Any

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from config import Config
from core.exceptions import LLMAuthError, LLMRateLimitError
from utils.logger import logger
from utils.token_counter import TokenCounter


class LLMResponse:
    """Wraps a raw OpenAI chat completion response."""

    def __init__(self, content: str, total_tokens: int) -> None:
        self.content = content
        self.total_tokens = total_tokens

    # Back-compat alias used in research_worker
    @property
    def usage(self) -> "_FakeUsage":
        return _FakeUsage(self.total_tokens)


class _FakeUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


class LLMProvider:
    """
    Thin wrapper around the OpenAI client pointing at NVIDIA's free API.

    Features:
    - Exponential back-off on RateLimitError (max 3 retries)
    - Converts auth errors to friendly LLMAuthError
    - Provides token estimation via tiktoken
    """

    def __init__(self, config: Config, token_counter: TokenCounter) -> None:
        self.config = config
        self.token_counter = token_counter
        self.model_name = config.default_model
        self.api_key = config.nvidia_api_key

        self._client = OpenAI(
            api_key=config.nvidia_api_key,
            base_url=config.base_url,
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.3,
        retries: int = 3,
    ) -> LLMResponse:
        """
        Send *messages* to the LLM and return the response.

        Args:
            messages:    OpenAI-style message list [{role, content}, ...]
            max_tokens:  Maximum tokens in the response
            temperature: Sampling temperature (lower = more deterministic)
            retries:     Number of retry attempts on transient errors

        Raises:
            LLMAuthError:       API key is invalid
            LLMRateLimitError:  Rate limits hit after all retries
            LLMError:           Other API failures
        """
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                content = response.choices[0].message.content or ""
                tokens = (
                    response.usage.total_tokens
                    if response.usage
                    else self.token_counter.count(content)
                )
                return LLMResponse(content=content, total_tokens=tokens)

            except AuthenticationError as e:
                raise LLMAuthError(
                    "Invalid NVIDIA API key. Check your .env.local file."
                ) from e

            except RateLimitError as e:
                last_error = e
                if attempt < retries - 1:
                    wait = 2**attempt
                    logger.warning("Rate limited. Retrying in %ds (attempt %d)...", wait, attempt + 1)
                    time.sleep(wait)

            except APIError as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning("API error: %s. Retrying...", e)
                    time.sleep(1)
                else:
                    raise

        raise LLMRateLimitError(
            f"Rate limit hit after {retries} retries. Try again later."
        ) from last_error

    def chat_simple(self, prompt: str, system: str | None = None, **kwargs: Any) -> LLMResponse:
        """Convenience wrapper for single-turn prompts."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    def count_tokens(self, text: str) -> int:
        """Estimate token count for *text*."""
        return self.token_counter.count(text)
