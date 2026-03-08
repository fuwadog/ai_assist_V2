"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from config import Config
from core.llm_provider import LLMResponse
from core.storage import Storage
from utils.token_counter import TokenCounter


@pytest.fixture
def temp_dir():
    with TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_config(temp_dir):
    config = Config()
    config.nvidia_api_key = "test_key"
    config.db_path = temp_dir / "test.db"
    config.max_context_tokens = 1000
    config.cache_enabled = True
    config.cache_ttl = 3600
    return config


@pytest.fixture
def in_memory_storage():
    storage = Storage(Path(":memory:"))
    yield storage
    storage.close()


@pytest.fixture
def token_counter():
    return TokenCounter()


class MockLLMProvider:
    def __init__(self, *args, **kwargs):
        self.call_count = 0

    def chat_simple(self, prompt: str, **kwargs) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(content="Mocked answer", total_tokens=42)

    def count_tokens(self, text: str) -> int:
        return len(text) // 4


@pytest.fixture
def mock_llm():
    return MockLLMProvider()
