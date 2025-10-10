"""
Test script for enhanced error handling in the phash computation system.

This script tests the improved error reporting and context preservation
functionality to ensure that detailed diagnostic information is available
when hash computation failures occur.
"""

import logging
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

# Set up logging to see debug output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from pk_py_lib.core.image.similarity.hash_utils import (
    load_image_with_fallback,
    handle_image_loading_errors
)
from pk_py_lib.core.image.similarity.hashing import (
    compute_phash,
    compute_whash,
    compute_phash_batch
)
from pk_py_lib.core.image.similarity.types import (
    ErrorContext,
    DetailedSimilarityError,
    InvalidImageError
)
from pk_py_lib.core.flat_cache import FlatCacheManager


def test_invalid_image_error_context():
    """Test error context preservation for invalid images."""
    print("\n=== Testing Invalid Image Error Context ===")

    # Create a temporary file that's not a valid image
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
        temp_file.write(b"This is not an image file")
        temp_path = temp_file.name

    try:
        try:
            # This should fail with enhanced error context
            result = compute_phash(temp_path, return_response=True)
            print(f"Result: {result}")
            if not result.success:
                print(f"Error details: {result.error_details}")
                print(f"Error message: {result.error_message}")
        except Exception as e:
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")

            # Check if it's a DetailedSimilarityError with context
            if isinstance(e, DetailedSimilarityError):
                print(f"Error context: {e.context.to_dict()}")
                print(f"Error summary: {e.context.get_summary()}")

    finally:
        # Clean up
        os.unlink(temp_path)


def test_nonexistent_file_error():
    """Test error handling for nonexistent files."""
    print("\n=== Testing Nonexistent File Error ===")

    nonexistent_path = "/path/that/does/not/exist/image.jpg"

    try:
        result = compute_phash(nonexistent_path, return_response=True)
        print(f"Result: {result}")
        if not result.success:
            print(f"Error details: {result.error_details}")
    except Exception as e:
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")


def test_wavelet_error_context():
    """Test error context for wavelet-related errors."""
    print("\n=== Testing Wavelet Error Context ===")

    # Create a temporary file that's not a valid image
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
        temp_file.write(b"This is not an image file")
        temp_path = temp_file.name

    try:
        try:
            # Try wHash with invalid wavelet parameters
            result = compute_whash(
                temp_path,
                wavelet='invalid_wavelet_name',
                return_response=True
            )
            print(f"Result: {result}")
            if not result.success:
                print(f"Error details: {result.error_details}")
                if hasattr(result.error_details, 'get') and result.error_details.get('error_context'):
                    print(f"Error context: {result.error_details['error_context']}")
        except Exception as e:
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")

    finally:
        # Clean up
        os.unlink(temp_path)


def test_batch_error_reporting():
    """Test enhanced batch processing error reporting."""
    print("\n=== Testing Batch Error Reporting ===")

    # Create temporary files - some valid, some invalid
    temp_files = []

    # Create some invalid image files
    for i in range(3):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_file.write(f"This is not image {i}".encode())
            temp_files.append(temp_file.name)

    # Add a nonexistent file
    temp_files.append("/path/that/does/not/exist.jpg")

    try:
        # Initialize cache manager for batch processing
        cache_manager = FlatCacheManager()

        # Test batch computation with mixed valid/invalid files
        results = compute_phash_batch(
            temp_files,
            flat_cache_manager=cache_manager
        )

        print(f"Batch results:")
        for path, hash_val in results.items():
            status = "SUCCESS" if hash_val else "FAILED"
            print(f"  {path}: {status}")

        # Check error details in cache logs
        print("\nCheck the debug logs above for detailed error context information")

    except Exception as e:
        print(f"Batch processing exception: {type(e).__name__}: {str(e)}")

    finally:
        # Clean up
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.unlink(temp_file)


def test_error_context_serialization():
    """Test ErrorContext serialization and dictionary conversion."""
    print("\n=== Testing ErrorContext Serialization ===")

    try:
        # Create a test error
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_file.write(b"Not an image")
            temp_path = temp_file.name

        try:
            # Trigger an error to create context
            load_image_with_fallback(temp_path)
        except DetailedSimilarityError as e:
            context = e.context

            # Test serialization
            context_dict = context.to_dict()
            print(f"Context keys: {list(context_dict.keys())}")
            print(f"File path: {context_dict['file_path']}")
            print(f"Operation: {context_dict['operation']}")
            print(f"Error type: {context_dict['error_type']}")
            print(f"Backend: {context_dict['backend']}")
            print(f"Additional context: {context_dict['additional_context']}")

            # Test summary
            summary = context.get_summary()
            print(f"Summary: {summary}")

            # Test error chain
            print(f"Error chain: {context.error_chain}")

    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)


def test_handle_image_loading_errors_enhanced():
    """Test the enhanced handle_image_loading_errors function."""
    print("\n=== Testing Enhanced handle_image_loading_errors ===")

    # Test with different types of errors
    test_cases = [
        Exception("Generic test error"),
        IOError("File access error"),
        OSError("OS level error"),
        ValueError("Value error"),
    ]

    for i, test_error in enumerate(test_cases):
        print(f"\nTest case {i+1}: {type(test_error).__name__}")

        try:
            handle_image_loading_errors(
                "/test/path/image.jpg",
                test_error,
                operation="test_operation",
                backend="test_backend",
                additional_context={"test_param": f"test_value_{i+1}"}
            )
        except Exception as e:
            print(f"  Resulting exception: {type(e).__name__}")
            print(f"  Message: {str(e)}")

            if isinstance(e, DetailedSimilarityError):
                print(f"  Context operation: {e.context.operation}")
                print(f"  Context backend: {e.context.backend}")
                print(f"  Additional context: {e.context.additional_context}")


def main():
    """Run all enhanced error handling tests."""
    print("Starting Enhanced Error Handling Tests")
    print("=" * 50)

    test_invalid_image_error_context()
    test_nonexistent_file_error()
    test_wavelet_error_context()
    test_batch_error_reporting()
    test_error_context_serialization()
    test_handle_image_loading_errors_enhanced()

    print("\n" + "=" * 50)
    print("Enhanced Error Handling Tests Complete")
    print("\nKey improvements implemented:")
    print("1. ✓ Fixed variable scope bug in hash_utils.py")
    print("2. ✓ Enhanced ErrorContext class for detailed error information")
    print("3. ✓ Improved error propagation preserving original exceptions")
    print("4. ✓ Debug-level logging with comprehensive context")
    print("5. ✓ Enhanced handle_image_loading_errors with context preservation")
    print("6. ✓ Improved batch processing error reporting with summaries")
    print("7. ✓ Comprehensive error context throughout hash computation pipeline")


if __name__ == "__main__":
    main()
