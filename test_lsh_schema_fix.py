#!/usr/bin/env python3
"""
Test script to verify that LSH parameters are properly handled in the settings schema.

This script tests that:
1. LSH parameters (lsh_num_perm, lsh_threshold) are now allowed in the similarity section
2. Settings validation passes with LSH parameters included
3. Default values are properly set
"""

import sys
import os

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pk_py_lib.core.settings_schema import (
    validate_settings_schema,
    normalize_settings,
    create_default_profile
)

def test_lsh_parameters_in_schema():
    """Test that LSH parameters are properly validated in the schema."""
    print("Testing LSH parameters in settings schema...")

    # Test 1: Create a profile with LSH parameters
    profile_with_lsh = {
        "id": "test-profile-id",
        "name": "Test Profile",
        "description": "Test profile with LSH parameters",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "pools": {
            "A": {
                "paths": ["."]
            }
        },
        "mode": "similarity",
        "criteria": {
            "algorithm": "phash",
            "similarity_hash_algorithm": "phash",
            "degree_ui": 90
        },
        "scope": {
            "kind": "single_pool"
        },
        "output": {
            "mode": "report_only"
        },
        "similarity": {
            "phash_threshold": 10,
            "whash_threshold": 12,
            "enabled_algorithms": ["phash"],
            "max_distance": 15,
            "lsh_num_perm": 256,
            "lsh_threshold": 0.85
        },
        "image_quality_evaluator": "brisque",
        "use_flat_cache": True
    }

    # Test validation
    is_valid, errors = validate_settings_schema(profile_with_lsh)
    if is_valid:
        print("✓ Profile with LSH parameters validates successfully")
    else:
        print(f"✗ Profile with LSH parameters failed validation: {errors}")
        return False

    # Test 2: Test normalization
    normalized = normalize_settings(profile_with_lsh)
    similarity = normalized.get("similarity", {})

    if "lsh_num_perm" in similarity and "lsh_threshold" in similarity:
        print(f"✓ LSH parameters present in normalized settings: lsh_num_perm={similarity['lsh_num_perm']}, lsh_threshold={similarity['lsh_threshold']}")
    else:
        print("✗ LSH parameters missing from normalized settings")
        return False

    # Test 3: Test default profile creation
    default_profile = create_default_profile("Default Test")
    default_similarity = default_profile.get("similarity", {})

    if "lsh_num_perm" in default_similarity and "lsh_threshold" in default_similarity:
        print(f"✓ Default profile includes LSH parameters: lsh_num_perm={default_similarity['lsh_num_perm']}, lsh_threshold={default_similarity['lsh_threshold']}")
    else:
        print("✗ Default profile missing LSH parameters")
        return False

    # Test 4: Test invalid LSH parameters
    invalid_profile = profile_with_lsh.copy()
    invalid_profile["similarity"]["lsh_num_perm"] = 32  # Below minimum of 64
    invalid_profile["similarity"]["lsh_threshold"] = 1.5  # Above maximum of 1.0

    is_valid, errors = validate_settings_schema(invalid_profile)
    if not is_valid:
        print("✓ Invalid LSH parameters correctly rejected by validation")
    else:
        print("✗ Invalid LSH parameters were incorrectly accepted")
        return False

    return True

def test_image_quality_evaluator_settings():
    """Test that image quality evaluator settings work without LSH interference."""
    print("\nTesting image quality evaluator settings...")

    # Test profile with BRISQUE evaluator
    profile = {
        "id": "test-brisque",
        "name": "BRISQUE Test",
        "description": "Test profile with BRISQUE evaluator",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "pools": {
            "A": {
                "paths": ["."]
            }
        },
        "mode": "duplicates",
        "criteria": {
            "algorithm": "xxh3"
        },
        "scope": {
            "kind": "single_pool"
        },
        "output": {
            "mode": "report_only"
        },
        "image_quality_evaluator": "brisque",
        "use_flat_cache": True
    }

    # This should validate successfully (LSH params should be added by normalization)
    is_valid, errors = validate_settings_schema(profile)
    if is_valid:
        print("✓ BRISQUE evaluator profile validates successfully")
    else:
        print(f"✗ BRISQUE evaluator profile failed validation: {errors}")
        return False

    # Test normalization adds LSH defaults
    normalized = normalize_settings(profile)
    similarity = normalized.get("similarity", {})

    if "lsh_num_perm" in similarity and "lsh_threshold" in similarity:
        print(f"✓ Normalization adds LSH defaults: lsh_num_perm={similarity['lsh_num_perm']}, lsh_threshold={similarity['lsh_threshold']}")
    else:
        print("✗ Normalization failed to add LSH defaults")
        return False

    return True

if __name__ == "__main__":
    print("Testing LSH schema fix...")
    print("=" * 50)

    success = True
    success &= test_lsh_parameters_in_schema()
    success &= test_image_quality_evaluator_settings()

    print("\n" + "=" * 50)
    if success:
        print("✓ All tests passed! LSH schema fix is working correctly.")
        sys.exit(0)
    else:
        print("✗ Some tests failed. LSH schema fix needs more work.")
        sys.exit(1)
