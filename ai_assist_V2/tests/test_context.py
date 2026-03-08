from __future__ import annotations

import pytest

from core.context_manager import ContextManager
from core.exceptions import TokenBudgetExceeded


def test_load_full_content(in_memory_storage, token_counter, temp_dir):
    ctx = ContextManager(in_memory_storage, token_counter, 1000)
    
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello World!")
    
    data = ctx.load_file(str(test_file), full_content=True)
    assert not data["is_summary"]
    assert data["content"] == "Hello World!"
    
    # Unload
    assert ctx.unload_file(str(test_file))
    assert not ctx.loaded_files


def test_budget_exceeded(in_memory_storage, token_counter, temp_dir):
    ctx = ContextManager(in_memory_storage, token_counter, max_tokens=2)
    
    test_file = temp_dir / "large.txt"
    test_file.write_text("This is much longer than two tokens")
    
    with pytest.raises(TokenBudgetExceeded):
        ctx.load_file(str(test_file), full_content=True)


def test_clear_all(in_memory_storage, token_counter, temp_dir):
    ctx = ContextManager(in_memory_storage, token_counter, 1000)
    
    f1 = temp_dir / "1.txt"
    f2 = temp_dir / "2.txt"
    f1.write_text("A")
    f2.write_text("B")
    
    ctx.load_file(str(f1), full_content=True)
    ctx.load_file(str(f2), full_content=True)
    
    assert len(ctx.loaded_files) == 2
    count = ctx.clear_all()
    assert count == 2
    assert len(ctx.loaded_files) == 0
