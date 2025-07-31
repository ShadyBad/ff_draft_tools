"""Tests for optimized caching system"""
import pytest
import tempfile
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

from src.utils.cache import OptimizedCache, CacheStats


class TestOptimizedCache:
    """Test optimized cache functionality"""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def cache(self, temp_cache_dir, monkeypatch):
        """Create a cache instance with temporary directory"""
        # Monkeypatch CACHE_DIR to use temp directory
        monkeypatch.setattr('config.CACHE_DIR', temp_cache_dir)
        return OptimizedCache('test_cache', cache_hours=1)
    
    def test_cache_set_and_get(self, cache):
        """Test basic cache set and get operations"""
        test_data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        
        # Set data in cache
        success = cache.set("test_key", test_data)
        assert success is True
        
        # Get data from cache
        retrieved = cache.get("test_key")
        assert retrieved == test_data
    
    def test_cache_compression(self, cache):
        """Test that compression is working"""
        # Create large data that compresses well
        large_data = {"data": "x" * 10000}
        
        success = cache.set("large_key", large_data)
        assert success is True
        
        # Check that compression happened
        assert cache.stats.compression_ratio > 0.5  # Should compress >50%
    
    def test_cache_expiry(self, cache):
        """Test cache expiration"""
        # Set cache with very short expiry (1 second)
        cache.set("expiring_key", "data", cache_hours=1/3600)  # 1 second
        
        # Should still be available immediately
        assert cache.get("expiring_key") == "data"
        
        # Wait for expiry
        time.sleep(1.1)  # Wait slightly longer than expiry
        
        # Should be expired now
        assert cache.get("expiring_key") is None
    
    def test_cache_invalidate(self, cache):
        """Test cache invalidation"""
        cache.set("key_to_invalidate", "data")
        
        # Verify it's there
        assert cache.get("key_to_invalidate") == "data"
        
        # Invalidate
        success = cache.invalidate("key_to_invalidate")
        assert success is True
        
        # Should be gone
        assert cache.get("key_to_invalidate") is None
    
    def test_cache_clear_namespace(self, cache):
        """Test clearing entire namespace"""
        # Set multiple keys
        for i in range(5):
            cache.set(f"key_{i}", f"value_{i}")
        
        # Clear namespace
        count = cache.clear_namespace()
        assert count >= 5  # At least our 5 files
        
        # All should be gone
        for i in range(5):
            assert cache.get(f"key_{i}") is None
    
    def test_cache_stats(self, cache):
        """Test cache statistics tracking"""
        # Reset stats for clean test
        cache.stats = CacheStats()
        
        # Miss
        cache.get("nonexistent")
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0
        
        # Write and hit
        cache.set("stats_key", "data")
        cache.get("stats_key")
        assert cache.stats.hits == 1
        assert cache.stats.writes == 1
        
        # Check stats summary
        stats = cache.stats.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0.5
    
    def test_cache_thread_safety(self, cache):
        """Test thread safety of cache operations"""
        import threading
        
        results = []
        
        def write_thread(i):
            success = cache.set(f"thread_key_{i}", f"data_{i}")
            results.append(success)
        
        # Create multiple threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=write_thread, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # All should succeed
        assert all(results)
        assert len(results) == 10
        
        # Verify all data is correct
        for i in range(10):
            assert cache.get(f"thread_key_{i}") == f"data_{i}"
    
    def test_cache_with_special_characters(self, cache):
        """Test cache with special characters in keys"""
        special_keys = [
            "key with spaces",
            "key/with/slashes",
            "key:with:colons",
            "key|with|pipes",
            "very_long_key_" + "x" * 100
        ]
        
        for key in special_keys:
            cache.set(key, f"data_for_{key}")
            assert cache.get(key) == f"data_for_{key}"
    
    def test_cache_info(self, cache):
        """Test cache info reporting"""
        # Add some data
        for i in range(3):
            cache.set(f"info_key_{i}", {"data": i})
        
        info = cache.get_cache_info()
        
        assert info['namespace'] == 'test_cache'
        assert info['file_count'] >= 3
        assert info['total_size_mb'] > 0
        assert 'stats' in info
    
    def test_cache_cleanup_old_files(self, cache, monkeypatch):
        """Test cleanup of old cache files"""
        # Create an old file
        old_file = cache.cache_dir / "old_file.pkl.gz"
        old_file.touch()
        
        # Modify its timestamp to be old
        old_time = time.time() - (8 * 24 * 60 * 60)  # 8 days ago
        import os
        os.utime(old_file, (old_time, old_time))
        
        # Create new cache instance (triggers cleanup)
        new_cache = OptimizedCache('test_cache', cache_hours=1)
        
        # Old file should be gone
        assert not old_file.exists()
    
    def test_cache_error_handling(self, cache, monkeypatch):
        """Test cache error handling"""
        # Test get with corrupted file
        cache_path = cache._get_cache_path("corrupt_key")
        meta_path = cache._get_metadata_path(cache_path)
        
        # Create corrupted cache file and valid metadata
        cache_path.write_text("corrupted data")
        meta_data = {
            'key': 'corrupt_key',
            'created': datetime.now().isoformat(),
            'expires': (datetime.now() + timedelta(hours=1)).isoformat()
        }
        with open(meta_path, 'w') as f:
            json.dump(meta_data, f)
        
        # Should return None instead of crashing
        result = cache.get("corrupt_key")
        assert result is None
        assert cache.stats.errors > 0
    
    def test_cache_without_compression(self, temp_cache_dir, monkeypatch):
        """Test cache without compression"""
        monkeypatch.setattr('config.CACHE_DIR', temp_cache_dir)
        uncompressed_cache = OptimizedCache('test_uncompressed', use_compression=False)
        
        test_data = {"data": "test"}
        uncompressed_cache.set("key", test_data)
        
        # File should not have .gz extension
        cache_path = uncompressed_cache._get_cache_path("key")
        assert not str(cache_path).endswith('.gz')
        
        # Should still work
        assert uncompressed_cache.get("key") == test_data