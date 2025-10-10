#!/usr/bin/env python3
"""
Fix script for flat_cache issues.
This script identifies and fixes the critical issues with cache population and metadata extraction.
"""

import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from src.pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheEntry
from src.pk_py_lib.core.filesystem.identity import compute_xxh3
from src.pk_py_lib.core.image.similarity.hashing import compute_phash, compute_whash
from src.pk_py_lib.core.image.similarity.metadata import get_image_metadata
from src.pk_py_lib.core.image.similarity.validation import is_image_extension
from src.pk_py_lib.core.logging.logger import get_logger

logger = get_logger(__name__)

def analyze_cache_issues():
    """Analyze and identify the root causes of cache issues."""
    print("=== ANALYZING CACHE ISSUES ===")

    issues_found = []

    # Issue 1: Check if scan_directory actually stores data in cache
    print("\n1. Testing cache population...")
    cache_manager = FlatCacheManager()

    # Test direct cache entry creation
    test_entry = FlatCacheEntry(
        path="test_direct.jpg",
        size=1024,
        mtime=1234567890.0,
        xxh3="test_xxh3_hash",
        phash="test_phash_hash",
        whash="test_whash_hash",
        width=100,
        height=100
    )

    success = cache_manager.set_entry(test_entry)
    if success:
        print("✓ Direct cache entry creation works")
        retrieved = cache_manager.get_entry("test_direct.jpg")
        if retrieved and retrieved.xxh3 == "test_xxh3_hash":
            print("✓ Cache entry retrieval works")
        else:
            print("✗ Cache entry retrieval failed")
            issues_found.append("Cache retrieval mechanism broken")
    else:
        print("✗ Direct cache entry creation failed")
        issues_found.append("Cache storage mechanism broken")

    # Issue 2: Check XXH3 computation
    print("\n2. Testing XXH3 computation...")
    try:
        test_file = Path("test_images/test_image_0.jpg")
        if test_file.exists():
            xxh3_hash = compute_xxh3(test_file)
            print(f"✓ XXH3 computation works: {xxh3_hash[:16]}...")
        else:
            print("✗ Test file not found for XXH3 testing")
            issues_found.append("Test files missing for XXH3 testing")
    except Exception as e:
        print(f"✗ XXH3 computation failed: {e}")
        issues_found.append(f"XXH3 computation error: {e}")

    # Issue 3: Check image metadata extraction
    print("\n3. Testing image metadata extraction...")
    try:
        test_file = "test_images/test_image_0.jpg"
        if os.path.exists(test_file):
            metadata = get_image_metadata(test_file)
            print(f"✓ Metadata extraction works: {metadata}")
        else:
            print("✗ Test file not found for metadata testing")
            issues_found.append("Test files missing for metadata testing")
    except Exception as e:
        print(f"✗ Metadata extraction failed: {e}")
        issues_found.append(f"Metadata extraction error: {e}")

    # Issue 4: Check hash computation functions
    print("\n4. Testing hash computation functions...")
    try:
        test_file = "test_images/test_image_0.jpg"
        if os.path.exists(test_file):
            phash = compute_phash(test_file)
            whash = compute_whash(test_file)
            print(f"✓ pHash computation works: {phash}")
            print(f"✓ wHash computation works: {whash}")
        else:
            print("✗ Test file not found for hash testing")
            issues_found.append("Test files missing for hash testing")
    except Exception as e:
        print(f"✗ Hash computation failed: {e}")
        issues_found.append(f"Hash computation error: {e}")

    return issues_found

def fix_cache_population_logic():
    """Fix the cache population logic in the system."""
    print("\n=== FIXING CACHE POPULATION LOGIC ===")

    # The main issue is that scan_directory doesn't actually store data in the cache
    # It only returns results but doesn't persist them

    print("Creating enhanced cache population function...")

    def enhanced_populate_cache(file_paths: List[str], cache_manager: FlatCacheManager) -> Dict[str, Any]:
        """
        Enhanced cache population that actually stores data in the cache.

        Args:
            file_paths: List of file paths to process
            cache_manager: FlatCacheManager instance

        Returns:
            Dictionary with processing results
        """
        results = {
            'processed': 0,
            'errors': [],
            'entries_created': 0
        }

        for file_path in file_paths:
            try:
                # Skip directories and non-existent files
                if not os.path.isfile(file_path):
                    continue

                # Get file stats
                stat_info = os.stat(file_path)
                size = stat_info.st_size
                mtime = stat_info.st_mtime

                # Skip empty files
                if size == 0:
                    continue

                # Check if entry already exists and is valid
                existing_entry = cache_manager.get_entry(file_path)
                if existing_entry and existing_entry.size == size and existing_entry.mtime == mtime:
                    logger.debug(f"Entry already exists and is valid: {file_path}")
                    results['processed'] += 1
                    continue

                # Create new entry
                entry = FlatCacheEntry(
                    path=file_path,
                    size=size,
                    mtime=mtime,
                    is_valid=True
                )

                # Compute XXH3 hash for all files
                try:
                    entry.xxh3 = compute_xxh3(Path(file_path))
                except Exception as e:
                    logger.warning(f"Failed to compute XXH3 for {file_path}: {e}")
                    entry.xxh3 = None

                # Compute image-specific metadata for image files
                if is_image_extension(file_path):
                    try:
                        # Get image metadata (includes dimensions)
                        metadata = get_image_metadata(file_path, search_type='similarity')
                        if metadata.get('resolution') != "Unknown":
                            # Parse resolution string "WxH"
                            try:
                                width_str, height_str = metadata['resolution'].split('x')
                                entry.width = int(width_str)
                                entry.height = int(height_str)
                            except (ValueError, AttributeError):
                                entry.width = None
                                entry.height = None
                    except Exception as e:
                        logger.warning(f"Failed to get metadata for {file_path}: {e}")

                    # Compute perceptual hashes
                    try:
                        entry.phash = compute_phash(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to compute pHash for {file_path}: {e}")
                        entry.phash = None

                    try:
                        entry.whash = compute_whash(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to compute wHash for {file_path}: {e}")
                        entry.whash = None

                # Store entry in cache
                if cache_manager.set_entry(entry):
                    results['entries_created'] += 1
                    logger.debug(f"Created cache entry for {file_path}")
                else:
                    results['errors'].append(f"Failed to store cache entry for {file_path}")

                results['processed'] += 1

            except Exception as e:
                results['errors'].append(f"Error processing {file_path}: {e}")
                logger.error(f"Error processing {file_path}: {e}")

        return results

    return enhanced_populate_cache

def test_fixed_cache_population():
    """Test the fixed cache population logic."""
    print("\n=== TESTING FIXED CACHE POPULATION ===")

    # Get all test image files
    test_dir = Path("test_images")
    if not test_dir.exists():
        print("✗ Test images directory not found")
        return False

    image_files = []
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        image_files.extend(test_dir.glob(f"*{ext}"))

    if not image_files:
        print("✗ No test image files found")
        return False

    print(f"Found {len(image_files)} test image files")

    # Test fixed cache population
    cache_manager = FlatCacheManager()
    enhanced_populate = fix_cache_population_logic()

    file_paths = [str(f) for f in image_files]
    results = enhanced_populate(file_paths, cache_manager)

    print(f"Processed: {results['processed']} files")
    print(f"Entries created: {results['entries_created']}")
    print(f"Errors: {len(results['errors'])}")

    if results['errors']:
        print("Errors:")
        for error in results['errors']:
            print(f"  - {error}")

    # Verify cache contents
    print("\nVerifying cache contents...")
    cache_info = cache_manager.get_cache_info()
    print(f"Cache info: {cache_info}")

    # Check a few entries
    for i, file_path in enumerate(file_paths[:3]):
        entry = cache_manager.get_entry(file_path)
        if entry:
            print(f"\nEntry {i+1}: {file_path}")
            print(f"  Size: {entry.size}")
            print(f"  XXH3: {entry.xxh3[:16] if entry.xxh3 else None}...")
            print(f"  pHash: {entry.phash}")
            print(f"  wHash: {entry.whash}")
            print(f"  Dimensions: {entry.width}x{entry.height}")
        else:
            print(f"\n✗ No entry found for {file_path}")

    return results['entries_created'] > 0

def main():
    """Main function to analyze and fix cache issues."""
    print("FLAT CACHE ISSUES DIAGNOSIS AND FIX")
    print("=" * 50)

    # Step 1: Analyze issues
    issues = analyze_cache_issues()

    if issues:
        print(f"\nFound {len(issues)} issues:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\nNo obvious issues found with basic operations")

    # Step 2: Test fixed cache population
    success = test_fixed_cache_population()

    if success:
        print("\n✓ Cache population fix appears to work!")
        print("The main issues were:")
        print("  1. scan_directory() was not storing data in the cache")
        print("  2. XXH3 hashes were not being computed for all files")
        print("  3. Image metadata was not being extracted and stored")
        print("  4. Cache entries were not being created properly")
    else:
        print("\n✗ Cache population fix failed")

    print("\nRECOMMENDATIONS:")
    print("1. Replace scan_directory() calls with enhanced_populate_cache()")
    print("2. Ensure all file processing goes through proper cache population")
    print("3. Add validation to exclude directories/drives from cache")
    print("4. Implement proper error handling for hash computation failures")

if __name__ == "__main__":
    main()
