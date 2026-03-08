from __future__ import annotations

from workers.research_worker import ResearchWorker


def test_research_worker_baseline_and_cache(
    mock_config, in_memory_storage, token_counter, mock_llm
):
    from core.context_manager import ContextManager
    
    ctx = ContextManager(in_memory_storage, token_counter, 1000)
    worker = ResearchWorker(ctx, mock_llm, in_memory_storage, mock_config)
    
    query = "Test query please ignore"
    
    # 1. First run, no cache
    res1 = worker.answer(query)
    assert res1["method"] == "baseline"
    assert not res1["cache_hit"]
    assert mock_llm.call_count == 1
    
    # 2. Second run, hit cache
    res2 = worker.answer(query)
    assert res2["method"] == "baseline (cached)"
    assert res2["cache_hit"]
    assert mock_llm.call_count == 1  # Not incremented
    
    # Query stats
    stats = worker.get_session_stats()
    assert stats["total_queries"] == 2
    assert stats["cache_hits"] == 1
