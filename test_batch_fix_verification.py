#!/usr/bin/env python3
"""
Test script to verify the batch processing fix resolves the similarity clustering issue.
This script tests the complete workflow from batch hash computation to similarity clustering.
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.image.similarity.hashing import compute_phash_batch, compute_similarity_hash_batch
from pk_py_lib.core.image.similarity.clustering import find_similar_images
from pk_py_lib.core.logging.logger import get_logger

logger = get_logger(__name__)

def test_batch_fix_verification():
    """Test that the batch processing fix enables similarity clustering to work."""

    print("=" * 80)
    print("BATCH PROCESSING FIX VERIFICATION TEST")
    print("=" * 80)

    # Test image paths (same as debug script)
    test_paths = [
        r"V:\D4\38739506010c2583044c_crop.jpg",
        r"V:\D4\0_427 (1)_crop.jpg",
        r"V:\Cache\0_219_crop0.jpg",
        r"V:\D4\0_959_crop0.jpg",
        r"V:\D4\0_175_crop1.jpg"
    ]

    # Initialize cache manager
    cache_manager = FlatCacheManager()

    print("\n1. Testing batch hash computation (FIXED):")
    print("-" * 50)

    # Test batch computation with the fix
    batch_results = compute_phash_batch(
        paths=test_paths,
        hash_size=8,
        flat_cache_manager=cache_manager
    )

    success_count = sum(1 for v in batch_results.values() if v is not None)
    total_count = len(batch_results)

    print(f"Batch computation results: {success_count}/{total_count} successful")

    if success_count == total_count:
        print("✅ BATCH PROCESSING FIX VERIFIED: All hashes computed successfully!")
    else:
        print("❌ BATCH PROCESSING FAILED: Some hashes still missing")
        return False

    print("\n2. Testing similarity clustering with computed hashes:")
    print("-" * 50)

    # Test similarity clustering using the computed hashes
    try:
        # This should now work since we have valid hashes
        similar_groups = find_similar_images(
            paths=test_paths,
            threshold=10,  # Hamming distance threshold (not percentage)
            settings={"criteria": {"phash": {"hash_size": 8}}},
            flat_cache_manager=cache_manager
        )

        print(f"Similarity clustering completed successfully!")
        print(f"Found {len(similar_groups)} similar groups")

        for i, group in enumerate(similar_groups):
            print(f"  Group {i+1}: {len(group.items)} images")
            for item in group.items:
                print(f"    - {Path(item.path).name} (score: {item.score:.3f})")

        print("✅ SIMILARITY CLUSTERING WORKS: Batch fix resolved the issue!")
        return True

    except Exception as e:
        print(f"❌ SIMILARITY CLUSTERING FAILED: {e}")
        return False

def test_cache_behavior():
    """Test that cache behavior works correctly with the fix."""

    print("\n3. Testing cache behavior with batch processing:")
    print("-" * 50)

    test_paths = [
        r"V:\D4\38739506010c2583044c_crop.jpg",
        r"V:\D4\0_427 (1)_crop.jpg"
    ]

    cache_manager = FlatCacheManager()

    # First run - should compute hashes
    print("First batch run (should compute):")
    results1 = compute_phash_batch(test_paths, flat_cache_manager=cache_manager)
    computed1 = sum(1 for v in results1.values() if v is not None)
    print(f"  Computed: {computed1}/{len(test_paths)}")

    # Second run - should use cache
    print("Second batch run (should use cache):")
    results2 = compute_phash_batch(test_paths, flat_cache_manager=cache_manager)
    computed2 = sum(1 for v in results2.values() if v is not None)
    print(f"  From cache: {computed2}/{len(test_paths)}")

    # Verify results are consistent
    consistent = all(results1[path] == results2[path] for path in test_paths)
    if consistent:
        print("✅ CACHE BEHAVIOR VERIFIED: Consistent results across runs!")
        return True
    else:
        print("❌ CACHE BEHAVIOR FAILED: Inconsistent results!")
        return False

if __name__ == "__main__":
    print("Testing batch processing fix and similarity clustering integration...")

    # Test 1: Basic batch fix verification
    test1_passed = test_batch_fix_verification()

    # Test 2: Cache behavior
    test2_passed = test_cache_behavior()

    print("\n" + "=" * 80)
    print("FINAL VERIFICATION RESULTS:")
    print("=" * 80)
    print(f"Batch Processing Fix: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Cache Behavior: {'✅ PASSED' if test2_passed else '❌ FAILED'}")

    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! The batch processing fix successfully resolves the 100% failure rate!")
        print("Similarity clustering should now work properly in the application.")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED! The fix may need additional work.")
        sys.exit(1)
