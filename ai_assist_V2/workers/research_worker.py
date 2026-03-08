"""Research Worker — Answers queries using available context."""

from __future__ import annotations

import uuid
from typing import Any

from config import Config
from core.context_manager import ContextManager
from core.llm_provider import LLMProvider
from core.storage import Storage
from utils.logger import logger


class ResearchWorker:
    """
    Handles query answering with intelligent method selection.
    
    In Phase 1, it always uses the '_baseline' method, but tracks
    session stats and manages the query cache.
    """

    def __init__(
        self,
        context_manager: ContextManager,
        llm_provider: LLMProvider,
        storage: Storage,
        config: Config,
    ) -> None:
        self.context = context_manager
        self.llm = llm_provider
        self.storage = storage
        self.config = config
        
        # A single session ID for tracking analytics during this run
        self.session_id = str(uuid.uuid4())

    def answer(self, query: str) -> dict[str, Any]:
        """
        Answer a query using the appropriate method (baseline in Phase 1).

        Returns:
            {
                'answer': str,
                'method': str,
                'tokens_used': int,
                'cache_hit': bool
            }
        """
        # Check cache if enabled
        if self.config.cache_enabled:
            cached = self.storage.get_cached_response(query)
            if cached:
                logger.info("Cache hit for query: %r", query)
                self.storage.log_query(
                    session_id=self.session_id,
                    query=query,
                    method=cached["method"],
                    tokens_used=0,
                    cache_hit=True,
                )
                return {
                    "answer": cached["response"],
                    "method": cached["method"] + " (cached)",
                    "tokens_used": 0,
                    "cache_hit": True,
                }

        # Decide method (Phase 1: always baseline)
        logger.info("Executing baseline query...")
        result = self._baseline(query)
        method = "baseline"

        # Cache result
        if self.config.cache_enabled:
            self.storage.cache_response(
                query=query,
                response=result["answer"],
                method=method,
                token_count=result["tokens_used"],
                ttl=self.config.cache_ttl,
            )

        # Log stats
        self.storage.log_query(
            session_id=self.session_id,
            query=query,
            method=method,
            tokens_used=result["tokens_used"],
            cache_hit=False,
            files_searched=len(self.context.loaded_files),
        )

        return {
            "answer": result["answer"],
            "method": method,
            "tokens_used": result["tokens_used"],
            "cache_hit": False,
        }

    def _baseline(self, query: str) -> dict[str, Any]:
        """Answer using standard LLM with loaded context."""
        context_str = self.context.build_context_string()

        # Build prompt
        system_prompt = (
            "You are a helpful, expert AI programming assistant.\n"
            "Use the provided context (which may contain full file text or AST summaries) "
            "to answer the user's question accurately and concisely.\n"
            "If the answer cannot be found in the context, state that clearly."
        )

        prompt = f"Context (loaded files):\n{context_str}\n\nUser Question: {query}"

        response = self.llm.chat_simple(prompt, system=system_prompt)

        return {
            "answer": response.content,
            "tokens_used": response.total_tokens,
        }

    def get_session_stats(self) -> dict[str, Any]:
        """Get stats for the current session."""
        return self.storage.get_stats(self.session_id)
