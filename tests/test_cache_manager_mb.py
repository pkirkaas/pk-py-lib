"""
tests/test_cache_manager_mb.py

Tests to validate CacheManager respects MB-based size limits and triggers eviction.
"""
from __future__ import annotations

from pathlib import Path
from src.pk_py_lib.core.cache import CacheManager


def test_cache_eviction_by_mb(tmp_path: Path):
    # Prepare a cache directory inside the pytest tmp_path
    cache_dir = Path(tmp_path) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Prepare thumbnail files to exceed a 1 MB limit
    size_dir = cache_dir / "thumbnails" / "256"
    size_dir.mkdir(parents=True, exist_ok=True)

    # Create two files of ~700 KB each (total ~1.4 MB)
    sizes = [700 * 1024, 700 * 1024]
    for i, s in enumerate(sizes):
        p = size_dir / f"test_{i}.jpg"
        p.write_bytes(b"0" * s)

    # Instantiate CacheManager with 1 MB limit to force cleanup
    cm = CacheManager(cache_dir, max_size_mb=1)

    # Verify initial total exceeds cleanup threshold (CLEANUP_ON_SIZE_PERCENT)
    initial_total = cm._get_total_cache_size()
    assert initial_total > cm.CLEANUP_ON_SIZE_PERCENT * cm.max_size_bytes

    # Trigger cleanup and assert that total size is reduced to target (80% of max) or below
    cm._cleanup_if_needed()
    final_total = cm._get_total_cache_size()
    assert final_total <= int(cm.max_size_bytes * 0.80)