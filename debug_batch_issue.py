#!/usr/bin/env python3
"""
Debug script to confirm the batch processing issue.
"""

import sys
import os
sys.path.insert(0, 'src')

from pk_py_lib.core.image.similarity.hashing import compute_phash_batch
from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.logging.logger import configure_logging, LogLevel

# Configure debug logging
configure_logging(
    console=True,
    file_path="debug_batch_issue.log",
    level=LogLevel.DEBUG,
    rich_console=True
)

# Test the same images that work individually but fail in batch
test_images = [
    "V:\\D4\\38739506010c2583044c_crop.jpg",
    "V:\\D4\\0_427 (1)_crop.jpg",
    "V:\\Cache\\0_219_crop0.jpg",
    "V:\\D4\\0_959_crop0.jpg",
    "V:\\D4\\0_175_crop1.jpg"
]

print("Testing batch processing issue...")
print("=" * 60)

# Initialize cache manager
cache_manager = FlatCacheManager()

print("\n1. Testing batch processing (should fail):")
print("-" * 40)

try:
    batch_results = compute_phash_batch(
        test_images,
        flat_cache_manager=cache_manager,
        algorithm="phash"
    )

    print(f"Batch results:")
    for path, hash_val in batch_results.items():
        status = "SUCCESS" if hash_val else "FAILED"
        print(f"  {path}: {status} ({hash_val})")

except Exception as e:
    print(f"Batch processing exception: {type(e).__name__}: {str(e)}")

print("\n2. Testing individual computation (should work):")
print("-" * 40)

from pk_py_lib.core.image.similarity.hashing import compute_phash

for path in test_images:
    try:
        result = compute_phash(path, flat_cache_manager=cache_manager, return_response=True)
        if result.success:
            print(f"  {path}: SUCCESS ({result.data})")
        else:
            print(f"  {path}: FAILED ({result.error_message})")
    except Exception as e:
        print(f"  {path}: EXCEPTION ({type(e).__name__}: {str(e)})")

print("\n3. Testing batch processing after individual computation (should now work):")
print("-" * 40)

try:
    batch_results_after = compute_phash_batch(
        test_images,
        flat_cache_manager=cache_manager,
        algorithm="phash"
    )

    print(f"Batch results after individual computation:")
    for path, hash_val in batch_results_after.items():
        status = "SUCCESS" if hash_val else "FAILED"
        print(f"  {path}: {status} ({hash_val})")

except Exception as e:
    print(f"Batch processing exception: {type(e).__name__}: {str(e)}")

print("\n" + "=" * 60)
print("Analysis complete. The issue is that batch processing only checks cache")
print("and never computes hashes for missing entries.")
