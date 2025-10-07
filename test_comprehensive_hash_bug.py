#!/usr/bin/env python3
"""
Comprehensive test to reproduce the hash algorithm selection bug.
This test covers multiple scenarios where the bug might manifest.
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.pk_py_lib.core.image.similarity import (
    compute_phash,
    compute_whash,
    get_similarity_hash,
    compute_similarity_hash_batch,
    find_similar_images
)
from src.pk_py_lib.core.flat_cache import FlatCacheManager

def create_test_image(width=100, height=100, color=(255, 0, 0)):
    """Create a simple test image"""
    from PIL import Image
    img = Image.new('RGB', (width, height), color)
    return img

def test_scenario_1_different_algorithms():
    """Test 1: Direct computation with different algorithms"""
    print("🧪 SCENARIO 1: Direct hash computation with different algorithms")

    # Create a test image
    test_img = create_test_image(100, 100, (255, 0, 0))

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        test_img.save(tmp.name)
        temp_path = tmp.name

    try:
        cache_manager = FlatCacheManager()

        # Test phash
        phash_result = compute_phash(temp_path, flat_cache_manager=cache_manager)
        print(f"  phash: {phash_result}")

        # Test whash
        whash_result = compute_whash(temp_path, flat_cache_manager=cache_manager)
        print(f"  whash: {whash_result}")

        if phash_result == whash_result:
            print("  ❌ BUG CONFIRMED: Identical results!")
            return False
        else:
            print("  ✅ Different results - working correctly")
            return True
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_scenario_2_algorithm_selection_api():
    """Test 2: Algorithm selection through high-level API"""
    print("\n🧪 SCENARIO 2: Algorithm selection through API")

    # Create a test image
    test_img = create_test_image(100, 100, (0, 255, 0))

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        test_img.save(tmp.name)
        temp_path = tmp.name

    try:
        cache_manager = FlatCacheManager()

        # Test with phash settings
        phash_settings = {
            'criteria': {
                'similarity_hash_algorithm': 'phash'
            }
        }

        # Test with whash settings
        whash_settings = {
            'criteria': {
                'similarity_hash_algorithm': 'whash'
            }
        }

        phash_result = get_similarity_hash(
            temp_path,
            settings=phash_settings,
            flat_cache_manager=cache_manager
        )

        whash_result = get_similarity_hash(
            temp_path,
            settings=whash_settings,
            flat_cache_manager=cache_manager
        )

        print(f"  phash via API: {phash_result}")
        print(f"  whash via API: {whash_result}")

        if phash_result == whash_result:
            print("  ❌ BUG CONFIRMED: Identical results!")
            return False
        else:
            print("  ✅ Different results - working correctly")
            return True
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_scenario_3_caching_issue():
    """Test 3: Check for caching issues that might cause same results"""
    print("\n🧪 SCENARIO 3: Testing for caching issues")

    # Create two different images
    img1 = create_test_image(100, 100, (255, 0, 0))  # Red
    img2 = create_test_image(100, 100, (0, 255, 0))  # Green

    temp_dir = tempfile.mkdtemp()
    try:
        path1 = os.path.join(temp_dir, 'test1.png')
        path2 = os.path.join(temp_dir, 'test2.png')

        img1.save(path1)
        img2.save(path2)

        cache_manager = FlatCacheManager()

        # Compute hashes for both images with both algorithms
        phash1 = compute_phash(path1, flat_cache_manager=cache_manager)
        whash1 = compute_whash(path1, flat_cache_manager=cache_manager)

        phash2 = compute_phash(path2, flat_cache_manager=cache_manager)
        whash2 = compute_whash(path2, flat_cache_manager=cache_manager)

        print(f"  Image 1 - phash: {phash1}, whash: {whash1}")
        print(f"  Image 2 - phash: {phash2}, whash: {whash2}")

        # Check if different images get different hashes
        if phash1 == phash2:
            print("  ⚠️  WARNING: Different images have same phash")
        if whash1 == whash2:
            print("  ⚠️  WARNING: Different images have same whash")

        # Check if same image gets different algorithm results
        if phash1 == whash1:
            print("  ❌ BUG CONFIRMED: Same image, different algorithms give same result!")
            return False
        if phash2 == whash2:
            print("  ❌ BUG CONFIRMED: Same image, different algorithms give same result!")
            return False

        print("  ✅ Different algorithms produce different results for same image")
        return True
    finally:
        shutil.rmtree(temp_dir)

def test_scenario_4_batch_computation():
    """Test 4: Batch computation with different algorithms"""
    print("\n🧪 SCENARIO 4: Batch computation")

    # Create test images
    images = [
        create_test_image(100, 100, (255, 0, 0)),
        create_test_image(100, 100, (0, 255, 0)),
        create_test_image(100, 100, (0, 0, 255))
    ]

    temp_dir = tempfile.mkdtemp()
    try:
        paths = []
        for i, img in enumerate(images):
            path = os.path.join(temp_dir, f'test{i}.png')
            img.save(path)
            paths.append(path)

        cache_manager = FlatCacheManager()

        # Test batch phash
        phash_results = compute_similarity_hash_batch(
            paths,
            algorithm='phash',
            flat_cache_manager=cache_manager
        )

        # Test batch whash
        whash_results = compute_similarity_hash_batch(
            paths,
            algorithm='whash',
            flat_cache_manager=cache_manager
        )

        print("  phash results:", {k: v for k, v in phash_results.items()})
        print("  whash results:", {k: v for k, v in whash_results.items()})

        # Check if any image gets same result for different algorithms
        for path in paths:
            phash = phash_results.get(path)
            whash = whash_results.get(path)
            if phash == whash:
                print(f"  ❌ BUG CONFIRMED: {path} has identical phash and whash!")
                return False

        print("  ✅ All images have different phash and whash results")
        return True
    finally:
        shutil.rmtree(temp_dir)

def main():
    print("COMPREHENSIVE HASH ALGORITHM BUG TEST")
    print("=" * 60)

    tests = [
        test_scenario_1_different_algorithms,
        test_scenario_2_algorithm_selection_api,
        test_scenario_3_caching_issue,
        test_scenario_4_batch_computation
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print(f"Tests passed: {sum(results)}/{len(results)}")

    if all(results):
        print("🎉 All tests passed - no bug detected")
        print("The hash algorithm selection appears to be working correctly.")
        return True
    else:
        print("🔍 Bug detected in one or more scenarios")
        print("Need to investigate the failing scenarios.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
