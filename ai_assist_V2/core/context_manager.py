"""Context Manager — file loading, token budgeting, and AST summarization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.exceptions import TokenBudgetExceeded
from core.storage import Storage
from tools.ast_summarizer import ASTSummarizer
from utils.logger import logger
from utils.token_counter import TokenCounter
from utils.validators import validate_path

# Warn when budget is 80% consumed
_WARN_THRESHOLD = 0.80


class ContextManager:
    """
    Manages the set of files currently in context.

    Responsibilities:
    - Load files (as AST summaries or full content)
    - Enforce token budget
    - Cache summaries in SQLite
    - Track loaded-file state for the current session
    """

    def __init__(
        self,
        storage: Storage,
        token_counter: TokenCounter,
        max_tokens: int = 7000,
    ) -> None:
        self.storage = storage
        self.token_counter = token_counter
        self.max_tokens = max_tokens
        self.loaded_files: dict[str, dict[str, Any]] = {}
        self._summarizer = ASTSummarizer()

    # ── Public API ───────────────────────────────────────────────────────────

    def load_file(self, filepath: str, full_content: bool = False) -> dict[str, Any]:
        """
        Load a file into context.

        Args:
            filepath:     Absolute or relative path to the file.
            full_content: If True, load the raw file content.
                          If False (default), load an AST summary.

        Returns:
            {
                'filepath':    str,
                'content':     str,
                'token_count': int,
                'is_summary':  bool,
            }

        Raises:
            FileNotFoundError:   If the file doesn't exist.
            TokenBudgetExceeded: If loading would exceed the token budget.
        """
        path = validate_path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        key = str(path)

        # Already loaded — return cached result
        if key in self.loaded_files:
            return self.loaded_files[key]

        # Retrieve or generate content
        if full_content:
            content = path.read_text(encoding="utf-8", errors="replace")
            is_summary = False
        else:
            content, is_summary = self._get_or_generate_summary(path)

        token_count = self.token_counter.count(content)
        self._check_budget(token_count)

        file_data: dict[str, Any] = {
            "filepath": key,
            "content": content,
            "token_count": token_count,
            "is_summary": is_summary,
        }
        self.loaded_files[key] = file_data
        logger.info("Loaded %s (%d tokens, summary=%s)", path.name, token_count, is_summary)
        return file_data

    def unload_file(self, filepath: str) -> bool:
        """
        Remove a file from context.

        Returns:
            True if the file was loaded and removed; False if not found.
        """
        try:
            path = validate_path(filepath)
            key = str(path)
        except ValueError:
            key = filepath

        if key in self.loaded_files:
            del self.loaded_files[key]
            logger.info("Unloaded %s", Path(key).name)
            return True
        return False

    def clear_all(self) -> int:
        """Remove all files from context. Returns number removed."""
        count = len(self.loaded_files)
        self.loaded_files.clear()
        return count

    def get_context(self) -> dict[str, Any]:
        """
        Return a summary of the current context state.

        Returns:
            {
                'loaded_files':  list[str],
                'total_tokens':  int,
                'max_tokens':    int,
                'utilization':   float,  # 0.0–1.0
            }
        """
        total = self._current_token_count()
        return {
            "loaded_files": list(self.loaded_files.keys()),
            "total_tokens": total,
            "max_tokens": self.max_tokens,
            "utilization": total / self.max_tokens if self.max_tokens else 0.0,
        }

    def build_context_string(self) -> str:
        """Make a single string from all loaded file contents, for LLM prompts."""
        if not self.loaded_files:
            return "(No files loaded)"
        parts = []
        for filepath, data in self.loaded_files.items():
            marker = "[SUMMARY]" if data["is_summary"] else "[FULL]"
            parts.append(f"--- {Path(filepath).name} {marker} ---\n{data['content']}")
        return "\n\n".join(parts)

    # ── Search helpers (used by Phase 3 Deep Research Tools) ────────────────

    def search_files(self, pattern: str) -> list[str]:
        """Find files in the project matching *pattern* (fnmatch-style)."""
        import fnmatch

        project_root = Path.cwd()
        matches = [
            str(p.relative_to(project_root))
            for p in project_root.rglob("*")
            if p.is_file() and fnmatch.fnmatch(p.name, pattern)
        ]
        return matches[:20]

    def get_file_content(self, filepath: str) -> str:
        """Read file content (used as a REPL tool in Phase 3)."""
        # Check if already loaded
        try:
            path = validate_path(filepath)
        except ValueError:
            return f"Error: invalid path '{filepath}'"

        key = str(path)
        if key in self.loaded_files:
            return self.loaded_files[key]["content"]

        # Try storage summary
        cached = self.storage.get_file_summary(key)
        if cached:
            return f"[SUMMARY]\n{cached}"

        # Read raw
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return f"Error: file not found '{filepath}'"

    def list_directory(self, dirpath: str) -> list[str]:
        """List directory contents (used as a REPL tool in Phase 3)."""
        try:
            path = validate_path(dirpath)
        except ValueError:
            return [f"Error: invalid path '{dirpath}'"]

        if not path.is_dir():
            return [f"Error: not a directory '{dirpath}'"]
        return [p.name for p in sorted(path.iterdir())]

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_or_generate_summary(self, path: Path) -> tuple[str, bool]:
        """Return (content, is_summary=True) from cache or generate fresh."""
        key = str(path)
        cached = self.storage.get_file_summary(key)
        if cached:
            logger.debug("Cache hit for summary: %s", path.name)
            return cached, True

        summary = self._summarizer.summarize(path)
        token_count = self.token_counter.count(summary)
        self.storage.save_file_summary(key, summary, token_count)
        return summary, True

    def _current_token_count(self) -> int:
        return sum(f["token_count"] for f in self.loaded_files.values())

    def _check_budget(self, adding: int) -> None:
        current = self._current_token_count()
        if current + adding > self.max_tokens:
            raise TokenBudgetExceeded(current, adding, self.max_tokens)
        if current + adding > self.max_tokens * _WARN_THRESHOLD:
            pct = (current + adding) / self.max_tokens * 100
            logger.warning("⚠️  Token budget at %.0f%%", pct)
