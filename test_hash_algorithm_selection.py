#!/usr/bin/env python3
"""
Test script to debug hash algorithm selection logic in similarity.py

This script tests the algorithm selection mechanism with different settings
configurations to identify where the selection might be failing.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.pk_py_lib.core.image.similarity import (
    get_similarity_hash,
    compute_similarity_hash_batch,
    find_similar_images
)

def test_similarity_mode_settings():
    """Test algorithm selection with similarity mode settings"""
    print("=" * 60)
    print("TESTING SIMILARITY MODE SETTINGS")
    print("=" * 60)

    # Test settings in similarity mode with phash
    similarity_settings_phash = {
        'mode': 'similarity',
        'criteria': {
            'similarity_hash_algorithm': 'phash',
            'degree_ui': 90
        },
        'similarity': {
            'phash_threshold': 10,
            'whash_threshold': 12,
            'enabled_algorithms': ['phash']
        }
    }

    print("Settings (similarity mode, phash):")
    print(f"  mode: {similarity_settings_phash['mode']}")
    print(f"  similarity_hash_algorithm: {similarity_settings_phash['criteria']['similarity_hash_algorithm']}")

    # Test single hash computation
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            settings=similarity_settings_phash
        )
        print(f"✓ get_similarity_hash succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash failed: {e}")

    # Test batch hash computation
    try:
        result = compute_similarity_hash_batch(
            paths=["dummy1.jpg", "dummy2.jpg"],
            settings=similarity_settings_phash
        )
        print(f"✓ compute_similarity_hash_batch succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ compute_similarity_hash_batch failed: {e}")

    # Test find_similar_images
    try:
        result = find_similar_images(
            paths=["dummy1.jpg", "dummy2.jpg"],
            settings=similarity_settings_phash
        )
        print(f"✓ find_similar_images succeeded (returned: {len(result)} groups)")
    except Exception as e:
        print(f"✗ find_similar_images failed: {e}")


def test_similarity_mode_settings_whash():
    """Test algorithm selection with similarity mode settings using whash"""
    print("\n" + "=" * 60)
    print("TESTING SIMILARITY MODE SETTINGS (WHASH)")
    print("=" * 60)

    # Test settings in similarity mode with whash
    similarity_settings_whash = {
        'mode': 'similarity',
        'criteria': {
            'similarity_hash_algorithm': 'whash',
            'degree_ui': 90
        },
        'similarity': {
            'phash_threshold': 10,
            'whash_threshold': 12,
            'enabled_algorithms': ['whash']
        }
    }

    print("Settings (similarity mode, whash):")
    print(f"  mode: {similarity_settings_whash['mode']}")
    print(f"  similarity_hash_algorithm: {similarity_settings_whash['criteria']['similarity_hash_algorithm']}")

    # Test single hash computation
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            settings=similarity_settings_whash
        )
        print(f"✓ get_similarity_hash succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash failed: {e}")

    # Test batch hash computation
    try:
        result = compute_similarity_hash_batch(
            paths=["dummy1.jpg", "dummy2.jpg"],
            settings=similarity_settings_whash
        )
        print(f"✓ compute_similarity_hash_batch succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ compute_similarity_hash_batch failed: {e}")


def test_duplicates_mode_settings():
    """Test algorithm selection with duplicates mode settings"""
    print("\n" + "=" * 60)
    print("TESTING DUPLICATES MODE SETTINGS")
    print("=" * 60)

    # Test settings in duplicates mode (should NOT have similarity_hash_algorithm)
    duplicates_settings = {
        'mode': 'duplicates',
        'criteria': {
            'algorithm': 'xxh3'
        },
        'similarity': {
            'phash_threshold': 10,
            'whash_threshold': 12,
            'enabled_algorithms': ['phash']
        }
    }

    print("Settings (duplicates mode):")
    print(f"  mode: {duplicates_settings['mode']}")
    print(f"  criteria keys: {list(duplicates_settings['criteria'].keys())}")
    print(f"  similarity_hash_algorithm in criteria: {'similarity_hash_algorithm' in duplicates_settings['criteria']}")

    # Test single hash computation
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            settings=duplicates_settings
        )
        print(f"✓ get_similarity_hash succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash failed: {e}")

    # Test batch hash computation
    try:
        result = compute_similarity_hash_batch(
            paths=["dummy1.jpg", "dummy2.jpg"],
            settings=duplicates_settings
        )
        print(f"✓ compute_similarity_hash_batch succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ compute_similarity_hash_batch failed: {e}")


def test_missing_criteria_settings():
    """Test algorithm selection with missing criteria"""
    print("\n" + "=" * 60)
    print("TESTING MISSING CRITERIA SETTINGS")
    print("=" * 60)

    # Test settings missing criteria entirely
    incomplete_settings = {
        'mode': 'similarity',
        'similarity': {
            'phash_threshold': 10,
            'whash_threshold': 12,
            'enabled_algorithms': ['phash']
        }
    }

    print("Settings (missing criteria):")
    print(f"  mode: {incomplete_settings['mode']}")
    print(f"  criteria in settings: {'criteria' in incomplete_settings}")

    # Test single hash computation
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            settings=incomplete_settings
        )
        print(f"✓ get_similarity_hash succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash failed: {e}")


def test_no_settings():
    """Test algorithm selection with no settings provided"""
    print("\n" + "=" * 60)
    print("TESTING NO SETTINGS PROVIDED")
    print("=" * 60)

    print("Settings: None")

    # Test single hash computation
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            settings=None
        )
        print(f"✓ get_similarity_hash succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash failed: {e}")

    # Test batch hash computation
    try:
        result = compute_similarity_hash_batch(
            paths=["dummy1.jpg", "dummy2.jpg"],
            settings=None
        )
        print(f"✓ compute_similarity_hash_batch succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ compute_similarity_hash_batch failed: {e}")


def test_explicit_algorithm_override():
    """Test that explicit algorithm parameter overrides settings"""
    print("\n" + "=" * 60)
    print("TESTING EXPLICIT ALGORITHM OVERRIDE")
    print("=" * 60)

    # Settings that specify whash, but we explicitly pass phash
    settings_with_whash = {
        'mode': 'similarity',
        'criteria': {
            'similarity_hash_algorithm': 'whash',
            'degree_ui': 90
        }
    }

    print("Settings specify whash, but we pass algorithm='phash'")

    # Test single hash computation with explicit phash (should override settings)
    try:
        result = get_similarity_hash(
            image_path="dummy.jpg",
            algorithm='phash',  # Explicit override
            settings=settings_with_whash
        )
        print(f"✓ get_similarity_hash with explicit override succeeded (returned: {result})")
    except Exception as e:
        print(f"✗ get_similarity_hash with explicit override failed: {e}")


if __name__ == "__main__":
    print("HASH ALGORITHM SELECTION DEBUG TEST")
    print("=" * 60)

    try:
        test_similarity_mode_settings()
        test_similarity_mode_settings_whash()
        test_duplicates_mode_settings()
        test_missing_criteria_settings()
        test_no_settings()
        test_explicit_algorithm_override()

        print("\n" + "=" * 60)
        print("DEBUG TEST COMPLETED")
        print("=" * 60)
        print("\nCheck the debug logs above for detailed information about:")
        print("- Settings structure analysis")
        print("- Algorithm selection logic")
        print("- Potential failure points")
        print("- Mode vs algorithm compatibility issues")

    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
