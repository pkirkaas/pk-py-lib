#!/usr/bin/env python3
"""
Debug script to test specific failing images and capture enhanced error context.
"""

import sys
import os
sys.path.insert(0, 'src')

from pk_py_lib.core.image.similarity.hashing import compute_phash
from pk_py_lib.core.logging.logger import configure_logging, LogLevel
from pathlib import Path

# Configure debug logging to capture all details
configure_logging(
    console=True,
    file_path="debug_phash_failures.log",
    level=LogLevel.DEBUG,
    rich_console=True
)

# Test a few of the failing images from the log output
failing_images = [
    "V:\\D4\\38739506010c2583044c_crop.jpg",
    "V:\\D4\\0_427 (1)_crop.jpg",
    "V:\\Cache\\0_219_crop0.jpg",
    "V:\\D4\\0_959_crop0.jpg",
    "V:\\D4\\0_175_crop1.jpg"
]

print("Testing specific failing images with enhanced error handling...")
print("=" * 60)

for i, image_path in enumerate(failing_images, 1):
    print(f"\n{i}. Testing: {image_path}")
    print("-" * 40)

    try:
        # Test with return_response=True to get detailed error information
        result = compute_phash(image_path, return_response=True)

        if result.success:
            print(f"✓ SUCCESS: Hash = {result.data}")
            if hasattr(result, 'metadata') and result.metadata:
                print(f"  Metadata: {result.metadata}")
        else:
            print(f"✗ FAILED: {result.error_message}")
            if hasattr(result, 'error_details') and result.error_details:
                print(f"  Error Details: {result.error_details}")
            if hasattr(result, 'stack_trace') and result.stack_trace:
                print(f"  Stack Trace: {result.stack_trace}")

    except Exception as e:
        print(f"✗ EXCEPTION: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("Debug testing complete. Check debug_phash_failures.log for detailed information.")
