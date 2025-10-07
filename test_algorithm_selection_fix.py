#!/usr/bin/env python3
"""Test script to verify hash algorithm selection works correctly.

This script compares two JSON export files from similarity comparison runs
to verify that different algorithms produce different results.

Usage:
    1. Run similarity comparison with "phash" selected
    2. Export results to JSON (e.g., logs/test-phash-export.json)
    3. Run similarity comparison with "whash" selected on same files
    4. Export results to JSON (e.g., logs/test-whash-export.json)
    5. Run this script to verify the exports use different algorithms

Expected outcome:
    - Different algorithm field in metadata
    - Different similarity groups (different results)
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def compare_json_exports(phash_file: str, whash_file: str) -> bool:
    """Compare two JSON export files to verify they use different algorithms.

    Args:
        phash_file: Path to JSON export from phash comparison
        whash_file: Path to JSON export from whash comparison

    Returns:
        True if tests pass, False otherwise
    """
    print("=" * 70)
    print("HASH ALGORITHM SELECTION TEST")
    print("=" * 70)

    # Check if files exist
    phash_path = Path(phash_file)
    whash_path = Path(whash_file)

    if not phash_path.exists():
        print(f"❌ FAIL: PHash export file not found: {phash_file}")
        print(f"\nPlease run similarity comparison with 'phash' selected")
        print(f"and export results to this path.")
        return False

    if not whash_path.exists():
        print(f"❌ FAIL: WHash export file not found: {whash_file}")
        print(f"\nPlease run similarity comparison with 'whash' selected")
        print(f"and export results to this path.")
        return False

    # Load JSON files
    try:
        with open(phash_file, 'r', encoding='utf-8') as f:
            phash_data = json.load(f)
        print(f"✓ Loaded PHash export: {phash_file}")
    except Exception as e:
        print(f"❌ FAIL: Error loading PHash file: {e}")
        return False

    try:
        with open(whash_file, 'r', encoding='utf-8') as f:
            whash_data = json.load(f)
        print(f"✓ Loaded WHash export: {whash_file}")
    except Exception as e:
        print(f"❌ FAIL: Error loading WHash file: {e}")
        return False

    print()

    # Test 1: Check algorithm field in metadata
    print("TEST 1: Algorithm Metadata")
    print("-" * 70)

    phash_algo = phash_data.get('export_info', {}).get('algorithm', 'unknown')
    whash_algo = whash_data.get('export_info', {}).get('algorithm', 'unknown')

    print(f"PHash export algorithm: '{phash_algo}'")
    print(f"WHash export algorithm: '{whash_algo}'")

    test1_pass = True
    if phash_algo.lower() != 'phash':
        print(f"⚠️  WARNING: PHash export reports algorithm as '{phash_algo}' (expected 'phash')")
        test1_pass = False

    if whash_algo.lower() != 'whash':
        print(f"⚠️  WARNING: WHash export reports algorithm as '{whash_algo}' (expected 'whash')")
        test1_pass = False

    if phash_algo == whash_algo:
        print("❌ FAIL: Both exports report same algorithm!")
        test1_pass = False
    else:
        print("✅ PASS: Exports report different algorithms")

    print()

    # Test 2: Compare results
    print("TEST 2: Results Comparison")
    print("-" * 70)

    phash_groups = phash_data.get('groups', [])
    whash_groups = whash_data.get('groups', [])

    print(f"PHash groups: {len(phash_groups)}")
    print(f"WHash groups: {len(whash_groups)}")

    # Count total files
    phash_files = sum(len(g.get('files', [])) for g in phash_groups)
    whash_files = sum(len(g.get('files', [])) for g in whash_groups)

    print(f"PHash total files in groups: {phash_files}")
    print(f"WHash total files in groups: {whash_files}")

    test2_pass = True

    # Extract group compositions for comparison
    phash_group_sets = [
        frozenset(f['path'] for f in g.get('files', []))
        for g in phash_groups
    ]
    whash_group_sets = [
        frozenset(f['path'] for f in g.get('files', []))
        for g in whash_groups
    ]

    # Check if results are identical
    if phash_group_sets == whash_group_sets:
        print("❌ FAIL: Results are identical! Groups contain same files.")
        print("This indicates the bug is still present - algorithm selection not working.")
        test2_pass = False
    else:
        print("✅ PASS: Results are different! Algorithm selection is working.")

        # Show some differences
        unique_to_phash = len([g for g in phash_group_sets if g not in whash_group_sets])
        unique_to_whash = len([g for g in whash_group_sets if g not in phash_group_sets])
        print(f"   Groups unique to PHash: {unique_to_phash}")
        print(f"   Groups unique to WHash: {unique_to_whash}")

    print()

    # Final summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_pass = test1_pass and test2_pass

    if all_pass:
        print("✅ ALL TESTS PASSED")
        print("\nThe hash algorithm selection bug appears to be FIXED!")
        print("Different algorithms now produce different results.")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nThe hash algorithm selection bug may still be present.")
        print("Check the test output above for details.")

    print("=" * 70)
    return all_pass


if __name__ == '__main__':
    # Default paths - update these to your actual export files
    phash_file = "logs/test-phash-export.json"
    whash_file = "logs/test-whash-export.json"

    # You can also pass paths as command line arguments
    import sys
    if len(sys.argv) >= 3:
        phash_file = sys.argv[1]
        whash_file = sys.argv[2]

    success = compare_json_exports(phash_file, whash_file)

    # Exit with appropriate code
    sys.exit(0 if success else 1)
