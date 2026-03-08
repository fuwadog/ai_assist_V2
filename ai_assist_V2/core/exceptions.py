"""Custom exception hierarchy for AI Assistant CLI V2."""

from __future__ import annotations


# ── File / Context Errors ────────────────────────────────────────────────────

class AIAssistError(Exception):
    """Base class for all project-specific errors."""


class FileOperationError(AIAssistError):
    """Base class for file-related errors."""


class TokenBudgetExceeded(FileOperationError):
    """Adding a file would exceed the token budget."""

    def __init__(self, current: int, adding: int, max_tokens: int) -> None:
        self.current = current
        self.adding = adding
        self.max_tokens = max_tokens
        super().__init__(
            f"Token budget exceeded. "
            f"Current: {current:,}, Adding: {adding:,}, Max: {max_tokens:,}. "
            f"Unload some files first with /unload <file>."
        )


# ── LLM Errors ───────────────────────────────────────────────────────────────

class LLMError(AIAssistError):
    """Base class for LLM-related errors."""


class LLMAuthError(LLMError):
    """API key missing or invalid."""


class LLMRateLimitError(LLMError):
    """Rate limit hit; retries exhausted."""


# ── REPL / RLM Errors (Phase 3 — defined now for forward compat) ─────────────

class REPLError(AIAssistError):
    """Base class for REPL errors."""


class REPLInitializationError(REPLError):
    """Failed to start the RLM REPL."""


class REPLTimeoutError(REPLError):
    """REPL execution exceeded the time limit."""

    def __init__(self, partial_result: str | None, elapsed: float) -> None:
        self.partial_result = partial_result
        self.elapsed = elapsed
        super().__init__(f"REPL timed out after {elapsed:.1f}s.")


class REPLMaxIterationsError(REPLError):
    """REPL reached the maximum iteration limit."""

    def __init__(
        self,
        partial_result: str | None,
        iterations: int,
        files_accessed: list[str],
        tokens_used: int = 0,
    ) -> None:
        self.partial_result = partial_result
        self.iterations = iterations
        self.files_accessed = files_accessed
        self.tokens_used = tokens_used
        super().__init__(f"REPL hit max iterations ({iterations}).")


class REPLCriticalError(REPLError):
    """Unrecoverable REPL error."""
