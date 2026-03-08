from __future__ import annotations

import time

from core.storage import Storage


def test_storage_init(in_memory_storage: Storage):
    """Test schema applies without errors."""
    stats = in_memory_storage.get_stats()
    assert stats["total_queries"] == 0


def test_file_summary(in_memory_storage: Storage, temp_dir):
    test_file = temp_dir / "test.py"
    test_file.write_text("print('hello')")
    
    # Save
    in_memory_storage.save_file_summary(str(test_file), "mock summary", 10)
    
    # Get
    res = in_memory_storage.get_file_summary(str(test_file))
    assert res == "mock summary"
    
    # Touch file (mtime changes)
    time.sleep(0.02)
    test_file.write_text("print('world')")
    
    # Should be invalidated
    res2 = in_memory_storage.get_file_summary(str(test_file))
    assert res2 is None


def test_query_cache(in_memory_storage: Storage):
    query = "What is this?"
    
    # Cache miss
    assert in_memory_storage.get_cached_response(query) is None
    
    # Set cache with short TTL
    in_memory_storage.cache_response(query, "It is a test", "baseline", 50, ttl=1)
    
    # Cache hit
    hit = in_memory_storage.get_cached_response(query)
    assert hit is not None
    assert hit["response"] == "It is a test"
    assert hit["method"] == "baseline"
    
    # Let expired
    time.sleep(1.1)
    assert in_memory_storage.get_cached_response(query) is None
    
    # Cleanup
    deleted = in_memory_storage.cleanup_expired_cache()
    assert deleted == 1


def test_session_stats(in_memory_storage: Storage):
    sid = "sess_123"
    
    in_memory_storage.log_query(sid, "Q1", "baseline", 100, cache_hit=False)
    in_memory_storage.log_query(sid, "Q2", "baseline", 0, cache_hit=True)
    in_memory_storage.log_query(sid, "Q3", "deep_research", 500, cache_hit=False)
    
    stats = in_memory_storage.get_stats(sid)
    assert stats["total_queries"] == 3
    assert stats["cache_hits"] == 1
    assert stats["total_tokens"] == 600
    assert stats["by_method"]["baseline"] == 2
    assert stats["by_method"]["deep_research"] == 1
