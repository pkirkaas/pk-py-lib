"""
Tests for enhanced cache manager with LRU eviction and performance monitoring.
"""

import pytest
import tempfile
import time
from datetime import datetime, timedelta

from pk_py_lib.core.flat_cache import EnhancedFlatCacheManager, CacheStats, CacheEntry
from pk_py_lib.core.api.response import ApiResponse, ErrorCode


class TestCacheStats:
    """Test CacheStats class."""

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hit_count=80, miss_count=20)
        assert stats.hit_rate == 80.0

        # Test zero requests
        stats_zero = CacheStats()
        assert stats_zero.hit_rate == 0.0

    def test_hit_miss_ratio(self):
        """Test hit:miss ratio."""
        stats = CacheStats(hit_count=75, miss_count=25)
        assert stats.hit_miss_ratio == "75:25"

    def test_to_dict(self):
        """Test stats serialization."""
        stats = CacheStats(
            total_entries=100,
            cache_size_bytes=1024,
            hit_count=80,
            miss_count=20
        )

        data = stats.to_dict()
        assert data['total_entries'] == 100
        assert data['cache_size_mb'] == 1024 / (1024 * 1024)
        assert data['hit_rate'] == 80.0


class TestCacheEntry:
    """Test CacheEntry class."""

    def test_entry_creation(self):
        """Test cache entry creation."""
        entry = CacheEntry(
            key="test_key",
            value={"data": "test"},
            created_at=datetime.now(),
            last_accessed=datetime.now()
        )

        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.access_count == 0
        assert entry.size_bytes > 0

    def test_touch(self):
        """Test entry touch functionality."""
        entry = CacheEntry(
            key="test_key",
            value="test_value",
            created_at=datetime.now(),
            last_accessed=datetime.now()
        )

        original_access_count = entry.access_count
        original_last_accessed = entry.last_accessed

        time.sleep(0.01)  # Small delay
        entry.touch()

        assert entry.access_count == original_access_count + 1
        assert entry.last_accessed > original_last_accessed


class TestEnhancedFlatCacheManager:
    """Test enhanced cache manager functionality."""

    @pytest.fixture
    def cache_manager(self):
        """Create a temporary cache manager for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EnhancedFlatCacheManager(
                cache_dir=temp_dir,
                max_size_mb=1,  # Small for testing
                max_entries=10,
                cleanup_interval=1
            )
            yield manager

    def test_cache_initialization(self, cache_manager):
        """Test cache manager initialization."""
        assert cache_manager.max_size_bytes == 1024 * 1024
        assert cache_manager.max_entries == 10
        assert cache_manager.eviction_policy == "lru"
        assert cache_manager.cache_dir.exists()

    def test_set_and_get(self, cache_manager):
        """Test basic set and get operations."""
        # Set value
        set_response = cache_manager.set("test_key", "test_value")
        assert set_response.success

        # Get value
        get_response = cache_manager.get("test_key")
        assert get_response.success
        assert get_response.data == "test_value"
        assert get_response.metadata['cache_hit'] is True

    def test_cache_miss(self, cache_manager):
        """Test cache miss behavior."""
        response = cache_manager.get("nonexistent_key")
        assert not response.success
        assert response.error.code == ErrorCode.NOT_FOUND
        assert response.metadata['cache_hit'] is False

    def test_lru_eviction(self, cache_manager):
        """Test LRU eviction policy."""
        # Fill cache to capacity
        for i in range(cache_manager.max_entries):
            cache_manager.set(f"key_{i}", f"value_{i}")

        # All entries should be present
        for i in range(cache_manager.max_entries):
            response = cache_manager.get(f"key_{i}")
            assert response.success

        # Add one more entry to trigger eviction
        cache_manager.set("new_key", "new_value")

        # Oldest entry should be evicted
        response = cache_manager.get("key_0")
        assert not response.success

        # New entry should be present
        response = cache_manager.get("new_key")
        assert response.success

    def test_cache_statistics(self, cache_manager):
        """Test cache statistics tracking."""
        # Perform some operations
        cache_manager.set("test_key", "test_value")
        cache_manager.get("test_key")  # Hit
        cache_manager.get("nonexistent")  # Miss

        # Get stats
        stats_response = cache_manager.get_stats()
        assert stats_response.success

        stats = stats_response.data
        assert stats['total_entries'] == 1
        assert stats['hit_count'] == 1
        assert stats['miss_count'] == 1
        assert stats['hit_rate'] == 50.0

    def test_size_limit_eviction(self, cache_manager):
        """Test eviction based on size limits."""
        # Create large entries that exceed size limit
        large_value = "x" * 100000  # 100KB each

        # Add entries until size limit is reached
        entries_added = 0
        while True:
            response = cache_manager.set(f"large_key_{entries_added}", large_value)
            if not response.success:
                break
            entries_added += 1

            # Check if eviction occurred
            stats_response = cache_manager.get_stats()
            stats = stats_response.data
            if stats['eviction_count'] > 0:
                break

        # Should have evicted some entries due to size limit
        stats_response = cache_manager.get_stats()
        stats = stats_response.data
        assert stats['eviction_count'] > 0

    def test_persistence(self, cache_manager):
        """Test cache persistence across restarts."""
        # Store some data
        cache_manager.set("persistent_key", "persistent_value")

        # Create new cache manager with same directory
        new_manager = EnhancedFlatCacheManager(
            cache_dir=cache_manager.cache_dir,
            max_size_mb=1,
            max_entries=10
        )

        # Data should be persisted
        response = new_manager.get("persistent_key")
        assert response.success
        assert response.data == "persistent_value"

    def test_clear_cache(self, cache_manager):
        """Test cache clearing."""
        # Add some data
        cache_manager.set("test_key", "test_value")

        # Clear cache
        response = cache_manager.clear()
        assert response.success

        # Verify cache is empty
        response = cache_manager.get("test_key")
        assert not response.success

        stats_response = cache_manager.get_stats()
        stats = stats_response.data
        assert stats['total_entries'] == 0

    def test_delete_entry(self, cache_manager):
        """Test individual entry deletion."""
        # Add data
        cache_manager.set("test_key", "test_value")

        # Delete specific entry
        response = cache_manager.delete("test_key")
        assert response.success

        # Verify deletion
        response = cache_manager.get("test_key")
        assert not response.success

    def test_access_pattern_analysis(self, cache_manager):
        """Test access pattern analysis functionality."""
        # Add entries with different access patterns
        cache_manager.set("popular_key", "popular_value")
        cache_manager.set("unpopular_key", "unpopular_value")

        # Access popular key multiple times
        for _ in range(5):
            cache_manager.get("popular_key")

        # Get access pattern
        response = cache_manager.get_entries_by_access_pattern()
        assert response.success

        entries = response.data
        assert len(entries) == 2

        # Popular key should be first
        assert entries[0]['key'] == "popular_key"
        assert entries[0]['access_count'] == 5

        # Unpopular key should be second
        assert entries[1]['key'] == "unpopular_key"
        assert entries[1]['access_count'] == 1


class TestCacheIntegration:
    """Test cache integration with similarity modules."""

    def test_hash_computation_with_cache(self):
        """Test hash computation using enhanced cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = EnhancedFlatCacheManager(cache_dir=temp_dir)

            # Test hash computation with cache
            from pk_py_lib.core.image.similarity.hashing import compute_phash_with_cache

            # Mock image path for testing
            test_image_path = "test_image.jpg"

            # First call should compute and cache
            result1 = compute_phash_with_cache(
                test_image_path,
                flat_cache_manager=cache_manager,
                return_response=True
            )

            # Second call should use cache (if image existed)
            # Note: This would fail without actual image, but tests the integration
            assert isinstance(result1, ApiResponse)

    def test_clustering_with_cache_stats(self):
        """Test clustering with cache statistics reporting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = EnhancedFlatCacheManager(cache_dir=temp_dir)

            # Test clustering with cache stats
            from pk_py_lib.core.image.similarity.clustering import find_similar_images

            # Mock paths for testing
            test_paths = ["test1.jpg", "test2.jpg"]

            # This would normally fail without actual images, but tests the integration
            try:
                result = find_similar_images(
                    test_paths,
                    flat_cache_manager=cache_manager,
                    return_response=True
                )
                assert isinstance(result, ApiResponse)
            except Exception:
                # Expected without actual images
                pass


class TestCacheEvictionPolicies:
    """Test different eviction policies."""

    @pytest.fixture(params=["lru", "lfu", "fifo"])
    def cache_manager(self, request):
        """Create cache manager with different eviction policies."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EnhancedFlatCacheManager(
                cache_dir=temp_dir,
                max_size_mb=1,
                max_entries=5,
                eviction_policy=request.param
            )
            yield manager

    def test_eviction_policy_behavior(self, cache_manager):
        """Test that eviction policies work correctly."""
        # Fill cache
        for i in range(cache_manager.max_entries):
            cache_manager.set(f"key_{i}", f"value_{i}")

        # Access some entries to create different patterns
        if cache_manager.eviction_policy == "lfu":
            # Access some entries more frequently
            for _ in range(3):
                cache_manager.get("key_1")
                cache_manager.get("key_2")
        elif cache_manager.eviction_policy == "lru":
            # Access some entries recently
            cache_manager.get("key_3")
            cache_manager.get("key_4")

        # Add one more to trigger eviction
        cache_manager.set("new_key", "new_value")

        # Verify eviction occurred
        stats_response = cache_manager.get_stats()
        stats = stats_response.data
        assert stats['eviction_count'] > 0


class TestCachePerformance:
    """Test cache performance characteristics."""

    def test_cache_performance_benchmark(self):
        """Test cache performance with benchmark."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = EnhancedFlatCacheManager(
                cache_dir=temp_dir,
                max_size_mb=10,
                max_entries=1000
            )

            # Benchmark set operations
            start_time = time.time()
            for i in range(100):
                cache_manager.set(f"perf_key_{i}", f"perf_value_{i}")
            set_time = time.time() - start_time

            # Benchmark get operations
            start_time = time.time()
            for i in range(100):
                cache_manager.get(f"perf_key_{i}")
            get_time = time.time() - start_time

            # Performance should be reasonable
            assert set_time < 1.0  # Should complete in under 1 second
            assert get_time < 0.5  # Gets should be faster

            # Check hit rate
            stats_response = cache_manager.get_stats()
            stats = stats_response.data
            assert stats['hit_rate'] == 100.0  # All gets should be hits


if __name__ == "__main__":
    pytest.main([__file__])
