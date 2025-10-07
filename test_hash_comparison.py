#!/usr/bin/env python3
"""
Test script to verify that phash and whash algorithms produce different results.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.pk_py_lib.core.image.similarity import compute_phash, compute_whash
from src.pk_py_lib.core.flat_cache import FlatCacheManager

def test_hash_algorithms():
    """Test that phash and whash produce different results for the same image"""

    # Use the real image file that exists in the project
    image_path = "example-guis/clone-spy.jpg"

    if not Path(image_path).exists():
        print(f"❌ Image file not found: {image_path}")
        return False

    print(f"✅ Using image file: {image_path}")

    # Create a flat cache manager
    cache_manager = FlatCacheManager()

    try:
        # Test phash
        print("\n🧪 Computing phash...")
        phash_result = compute_phash(
            image_path,
            flat_cache_manager=cache_manager
        )
        print(f"✅ phash result: {phash_result}")

        # Test whash
        print("\n🧪 Computing whash...")
        whash_result = compute_whash(
            image_path,
            flat_cache_manager=cache_manager
        )
        print(f"✅ whash result: {whash_result}")

        # Compare results
        if phash_result == whash_result:
            print("\n❌ CRITICAL BUG CONFIRMED: phash and whash produced identical results!")
            print(f"Both algorithms returned: {phash_result}")
            return False
        else:
            print("\n✅ SUCCESS: phash and whash produced different results!")
            print(f"phash:  {phash_result}")
            print(f"whash:  {whash_result}")
            return True

    except Exception as e:
        print(f"❌ Error during hash computation: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_algorithm_selection():
    """Test algorithm selection through the high-level API"""

    image_path = "example-guis/clone-spy.jpg"

    if not Path(image_path).exists():
        print(f"❌ Image file not found: {image_path}")
        return False

    print("\n🧪 Testing algorithm selection API...")
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

    cache_manager = FlatCacheManager()

    try:
        from src.pk_py_lib.core.image.similarity import get_similarity_hash

        print("Computing hash with phash settings...")
        phash_result = get_similarity_hash(
            image_path,
            settings=phash_settings,
            flat_cache_manager=cache_manager
        )
        print(f"✅ phash via API: {phash_result}")

        print("Computing hash with whash settings...")
        whash_result = get_similarity_hash(
            image_path,
            settings=whash_settings,
            flat_cache_manager=cache_manager
        )
        print(f"✅ whash via API: {whash_result}")

        if phash_result == whash_result:
            print("\n❌ CRITICAL BUG CONFIRMED: API algorithm selection not working!")
            return False
        else:
            print("\n✅ SUCCESS: API algorithm selection working correctly!")
            return True

    except Exception as e:
        print(f"❌ Error in algorithm selection test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("HASH ALGORITHM COMPARISON TEST")
    print("=" * 50)

    # Test direct hash computation
    direct_test_passed = test_hash_algorithms()

    # Test high-level API
    api_test_passed = test_algorithm_selection()

    print("\n" + "=" * 50)
    print("FINAL RESULTS:")
    print(f"Direct hash computation: {'✅ PASS' if direct_test_passed else '❌ FAIL'}")
    print(f"API algorithm selection: {'✅ PASS' if api_test_passed else '❌ FAIL'}")

    if not direct_test_passed or not api_test_passed:
        print("\n🔍 Bug confirmed - need to investigate hash computation logic")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed - algorithms working correctly")
        sys.exit(0)
