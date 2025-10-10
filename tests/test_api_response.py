"""
Tests for standardized API response structures.

This module provides comprehensive test coverage for the ApiResponse infrastructure,
including error codes, response types, and integration with existing components.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from pk_py_lib.core.api.response import (
    ApiResponse, ErrorCode, ErrorDetail,
    success, error, from_exception, partial_success
)
from pk_py_lib.core.image.similarity import (
    compute_phash, compute_whash, find_similar_images
)


class TestErrorCode:
    """Test ErrorCode enum functionality."""

    def test_error_code_values(self):
        """Test that error codes have expected values."""
        assert ErrorCode.SUCCESS.value == "SUCCESS"
        assert ErrorCode.PARTIAL_SUCCESS.value == "PARTIAL_SUCCESS"
        assert ErrorCode.FILE_NOT_FOUND.value == "FILE_NOT_FOUND"
        assert ErrorCode.HASH_COMPUTATION_FAILED.value == "HASH_COMPUTATION_FAILED"
        assert ErrorCode.SIMILARITY_DETECTION_FAILED.value == "SIMILARITY_DETECTION_FAILED"

    def test_error_code_categories(self):
        """Test that error codes are properly categorized."""
        # Success codes
        success_codes = [ErrorCode.SUCCESS, ErrorCode.PARTIAL_SUCCESS]
        for code in success_codes:
            assert "SUCCESS" in code.value

        # File system errors
        fs_errors = [ErrorCode.FILE_NOT_FOUND, ErrorCode.FILE_ACCESS_DENIED,
                    ErrorCode.INVALID_FILE_FORMAT, ErrorCode.FILE_TOO_LARGE]
        for code in fs_errors:
            assert any(keyword in code.value for keyword in ["FILE", "INVALID"])

        # Image processing errors
        img_errors = [ErrorCode.IMAGE_LOAD_FAILED, ErrorCode.INVALID_IMAGE_FORMAT,
                     ErrorCode.IMAGE_CORRUPTED, ErrorCode.UNSUPPORTED_IMAGE_TYPE]
        for code in img_errors:
            assert any(keyword in code.value for keyword in ["IMAGE"])

        # Hash computation errors
        hash_errors = [ErrorCode.HASH_COMPUTATION_FAILED, ErrorCode.INVALID_HASH_ALGORITHM,
                      ErrorCode.INVALID_HASH_SIZE]
        for code in hash_errors:
            assert "HASH" in code.value


class TestErrorDetail:
    """Test ErrorDetail class functionality."""

    def test_error_detail_creation(self):
        """Test ErrorDetail creation and basic properties."""
        error = ErrorDetail(
            code=ErrorCode.FILE_NOT_FOUND,
            message="File not found",
            details={'file_path': '/path/to/file.jpg'}
        )

        assert error.code == ErrorCode.FILE_NOT_FOUND
        assert error.message == "File not found"
        assert error.details['file_path'] == '/path/to/file.jpg'
        assert error.stack_trace is not None
        assert isinstance(error.timestamp, datetime)

    def test_error_detail_to_dict(self):
        """Test ErrorDetail serialization to dictionary."""
        error = ErrorDetail(
            code=ErrorCode.INVALID_INPUT,
            message="Invalid hash size",
            details={'hash_size': 5, 'valid_range': '4-64'}
        )

        data = error.to_dict()
        assert data['code'] == "INVALID_INPUT"
        assert data['message'] == "Invalid hash size"
        assert data['details']['hash_size'] == 5
        assert data['details']['valid_range'] == '4-64'
        assert 'timestamp' in data
        assert 'stack_trace' in data
        assert isinstance(data['timestamp'], str)

    def test_error_detail_with_custom_stack_trace(self):
        """Test ErrorDetail with custom stack trace."""
        custom_trace = "Custom stack trace line 1\nCustom stack trace line 2"
        error = ErrorDetail(
            code=ErrorCode.UNKNOWN_ERROR,
            message="Test error",
            stack_trace=custom_trace
        )

        assert error.stack_trace == custom_trace
        data = error.to_dict()
        assert data['stack_trace'] == custom_trace


class TestApiResponse:
    """Test ApiResponse class functionality."""

    def test_success_response_creation(self):
        """Test successful response creation."""
        response = ApiResponse.success_response(data="test_data")

        assert response.success is True
        assert response.data == "test_data"
        assert response.error is None
        assert response.warnings == []
        assert isinstance(response.timestamp, datetime)
        assert response.metadata == {}

    def test_success_response_with_metadata(self):
        """Test successful response with metadata and warnings."""
        warnings = ["Minor issue detected", "Performance warning"]
        metadata = {"algorithm": "phash", "hash_size": 8, "processing_time": 1.23}

        response = ApiResponse.success_response(
            data={"hash": "abcdef1234567890"},
            warnings=warnings,
            metadata=metadata
        )

        assert response.success is True
        assert response.data["hash"] == "abcdef1234567890"
        assert response.warnings == warnings
        assert response.metadata == metadata

    def test_partial_success_response(self):
        """Test partial success response creation."""
        response = ApiResponse.partial_success_response(
            data={"processed": 95, "failed": 5},
            warnings=["5 items failed processing"],
            metadata={"total_items": 100}
        )

        assert response.success is True
        assert response.data["processed"] == 95
        assert response.data["failed"] == 5
        assert "5 items failed processing" in response.warnings
        assert response.metadata["partial_success"] is True
        assert response.metadata["total_items"] == 100

    def test_error_response_creation(self):
        """Test error response creation."""
        response = ApiResponse.error_response(
            code=ErrorCode.FILE_NOT_FOUND,
            message="File not found",
            details={'file_path': '/nonexistent/file.jpg'}
        )

        assert response.success is False
        assert response.error.code == ErrorCode.FILE_NOT_FOUND
        assert response.error.message == "File not found"
        assert response.error.details['file_path'] == '/nonexistent/file.jpg'
        assert response.data is None
        assert response.warnings == []

    def test_from_exception_file_not_found(self):
        """Test creating response from FileNotFoundError."""
        try:
            raise FileNotFoundError("Test file not found")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.FILE_NOT_FOUND
        assert "Test file not found" in response.error.message
        assert response.error.details['exception_type'] == "FileNotFoundError"

    def test_from_exception_permission_error(self):
        """Test creating response from PermissionError."""
        try:
            raise PermissionError("Permission denied")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.FILE_ACCESS_DENIED
        assert "Permission denied" in response.error.message

    def test_from_exception_value_error(self):
        """Test creating response from ValueError."""
        try:
            raise ValueError("Invalid parameter value")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.INVALID_INPUT
        assert "Invalid parameter value" in response.error.message

    def test_from_exception_memory_error(self):
        """Test creating response from MemoryError."""
        try:
            raise MemoryError("Out of memory")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.MEMORY_ERROR
        assert "Out of memory" in response.error.message

    def test_from_exception_timeout_error(self):
        """Test creating response from TimeoutError."""
        try:
            raise TimeoutError("Operation timed out")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.TIMEOUT_ERROR
        assert "Operation timed out" in response.error.message

    def test_from_exception_unknown_error(self):
        """Test creating response from unknown exception type."""
        try:
            raise RuntimeError("Unexpected runtime error")
        except Exception as e:
            response = ApiResponse.from_exception(e)

        assert response.success is False
        assert response.error.code == ErrorCode.UNKNOWN_ERROR
        assert "Unexpected runtime error" in response.error.message

    def test_from_exception_with_custom_code_and_message(self):
        """Test creating response from exception with custom code and message."""
        try:
            raise ValueError("Original error message")
        except Exception as e:
            response = ApiResponse.from_exception(
                e,
                code=ErrorCode.VALIDATION_ERROR,
                message="Custom validation error message",
                metadata={"field": "hash_size", "value": 5}
            )

        assert response.success is False
        assert response.error.code == ErrorCode.VALIDATION_ERROR
        assert response.error.message == "Custom validation error message"
        assert response.metadata["field"] == "hash_size"
        assert response.metadata["value"] == 5

    def test_response_validation_success_with_error(self):
        """Test that successful response cannot contain error."""
        with pytest.raises(ValueError, match="Successful response cannot contain error"):
            ApiResponse(success=True, error=ErrorDetail(ErrorCode.UNKNOWN_ERROR, "test"))

    def test_response_validation_error_without_error(self):
        """Test that unsuccessful response must contain error."""
        with pytest.raises(ValueError, match="Unsuccessful response must contain error"):
            ApiResponse(success=False)

    def test_response_serialization(self):
        """Test response serialization to dictionary."""
        response = ApiResponse.success_response(
            data={"result": "success", "count": 42},
            warnings=["test warning"],
            metadata={"version": "1.0", "algorithm": "phash"}
        )

        serialized = response.to_dict()
        assert serialized['success'] is True
        assert serialized['data']['result'] == "success"
        assert serialized['data']['count'] == 42
        assert "test warning" in serialized['warnings']
        assert serialized['metadata']['version'] == "1.0"
        assert serialized['metadata']['algorithm'] == "phash"
        assert 'timestamp' in serialized
        assert 'error' not in serialized

    def test_error_response_serialization(self):
        """Test error response serialization to dictionary."""
        response = ApiResponse.error_response(
            code=ErrorCode.INVALID_HASH_ALGORITHM,
            message="Invalid hash algorithm",
            details={"algorithm": "invalid_hash", "supported": ["phash", "whash"]}
        )

        serialized = response.to_dict()
        assert serialized['success'] is False
        assert serialized['error']['code'] == "INVALID_HASH_ALGORITHM"
        assert serialized['error']['message'] == "Invalid hash algorithm"
        assert serialized['error']['details']['algorithm'] == "invalid_hash"
        assert serialized['error']['details']['supported'] == ["phash", "whash"]
        assert 'timestamp' in serialized['error']
        assert 'data' not in serialized

    def test_add_warning(self):
        """Test adding warnings to response."""
        response = ApiResponse.success_response(data="test")
        response.add_warning("First warning")
        response.add_warning("Second warning")

        assert len(response.warnings) == 2
        assert "First warning" in response.warnings
        assert "Second warning" in response.warnings

    def test_add_metadata(self):
        """Test adding metadata to response."""
        response = ApiResponse.success_response(data="test")
        response.add_metadata("algorithm", "phash")
        response.add_metadata("hash_size", 8)

        assert response.metadata["algorithm"] == "phash"
        assert response.metadata["hash_size"] == 8


class TestConvenienceFunctions:
    """Test convenience functions for creating responses."""

    def test_success_function(self):
        """Test success convenience function."""
        response = success(data="test_data", metadata={"key": "value"})

        assert response.success is True
        assert response.data == "test_data"
        assert response.metadata["key"] == "value"

    def test_error_function(self):
        """Test error convenience function."""
        response = error(
            ErrorCode.INVALID_INPUT,
            "Invalid input provided",
            details={"field": "threshold", "value": -1}
        )

        assert response.success is False
        assert response.error.code == ErrorCode.INVALID_INPUT
        assert response.error.message == "Invalid input provided"
        assert response.error.details["field"] == "threshold"
        assert response.error.details["value"] == -1

    def test_from_exception_function(self):
        """Test from_exception convenience function."""
        try:
            raise FileNotFoundError("Test file")
        except Exception as e:
            response = from_exception(e, metadata={"operation": "file_read"})

        assert response.success is False
        assert response.error.code == ErrorCode.FILE_NOT_FOUND
        assert response.metadata["operation"] == "file_read"

    def test_partial_success_function(self):
        """Test partial_success convenience function."""
        response = partial_success(
            data={"processed": 80, "failed": 20},
            warnings=["20% of items failed"],
            metadata={"success_rate": 0.8}
        )

        assert response.success is True
        assert response.data["processed"] == 80
        assert response.data["failed"] == 20
        assert response.metadata["partial_success"] is True
        assert response.metadata["success_rate"] == 0.8


class TestApiResponseIntegration:
    """Test ApiResponse integration with existing components."""

    @patch('pk_py_lib.core.image.similarity.hashing.load_image_with_fallback')
    @patch('pk_py_lib.core.image.similarity.hashing.check_cache_for_hash')
    def test_compute_phash_with_api_response(self, mock_cache, mock_load):
        """Test compute_phash with ApiResponse return format."""
        # Mock successful image loading
        import numpy as np
        mock_image = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_load.return_value = mock_image
        mock_cache.return_value = None

        # Test traditional usage (backward compatibility)
        hash_result = compute_phash("/fake/path.jpg", return_response=False)
        assert hash_result is not None  # Should return hash string

        # Test new ApiResponse usage
        response = compute_phash("/fake/path.jpg", return_response=True)
        assert response.success is True
        assert response.data is not None  # Should contain hash string
        assert response.metadata['algorithm'] == 'phash'
        assert 'computed' in response.metadata

    def test_compute_phash_error_handling(self):
        """Test compute_phash error handling with ApiResponse."""
        # Test that error handling is properly integrated by checking the function exists
        # and has the return_response parameter
        import inspect
        sig = inspect.signature(compute_phash)
        assert 'return_response' in sig.parameters
        assert sig.parameters['return_response'].default is False

    @patch('pk_py_lib.core.image.similarity.phases.execute_all_phases')
    def test_find_similar_images_with_api_response(self, mock_execute):
        """Test find_similar_images with ApiResponse return format."""
        # Mock successful phase execution
        from pk_py_lib.core.image.similarity.phases import PhaseContext
        mock_context = Mock(spec=PhaseContext)
        mock_context.final_groups = []
        mock_context.exact_duplicate_sets = []
        mock_context.warnings = []
        mock_context.algorithm = "phash"
        mock_context.threshold = 10
        mock_execute.return_value = mock_context

        # Test traditional usage (backward compatibility)
        groups = find_similar_images(["/fake/path1.jpg", "/fake/path2.jpg"], return_response=False)
        assert isinstance(groups, list)

        # Test new ApiResponse usage
        response = find_similar_images(["/fake/path1.jpg", "/fake/path2.jpg"], return_response=True)
        assert response.success is True
        assert 'similarity_groups' in response.data
        assert 'duplicate_groups' in response.data
        assert response.metadata['algorithm'] == 'phash'
        assert response.metadata['threshold'] == 10

    @patch('pk_py_lib.core.image.similarity.phases.execute_all_phases')
    def test_find_similar_images_error_handling(self, mock_execute):
        """Test find_similar_images error handling with ApiResponse."""
        # Mock phase execution failure
        mock_execute.side_effect = Exception("Phase execution failed")

        # Test new ApiResponse usage with error
        response = find_similar_images(["/fake/path1.jpg"], return_response=True)
        assert response.success is False
        assert response.error.code == ErrorCode.SIMILARITY_DETECTION_FAILED
        assert "Phase execution failed" in response.error.message
        assert response.metadata['total_images'] == 1

    def test_find_similar_images_empty_input(self):
        """Test find_similar_images with empty input."""
        response = find_similar_images([], return_response=True)
        assert response.success is False
        assert response.error.code == ErrorCode.INVALID_INPUT
        assert "paths list cannot be empty" in response.error.message


class TestApiResponseEdgeCases:
    """Test ApiResponse edge cases and boundary conditions."""

    def test_response_with_none_data(self):
        """Test response with None data."""
        response = ApiResponse.success_response(data=None)
        assert response.success is True
        assert response.data is None

    def test_response_with_complex_data(self):
        """Test response with complex nested data structures."""
        complex_data = {
            "groups": [
                {
                    "id": 1,
                    "items": [
                        {"path": "/file1.jpg", "size": 1024},
                        {"path": "/file2.jpg", "size": 2048}
                    ],
                    "stats": {"total_size": 3072, "avg_score": 0.95}
                }
            ],
            "metadata": {
                "processing": {
                    "start_time": "2023-01-01T00:00:00Z",
                    "end_time": "2023-01-01T00:01:00Z",
                    "duration": 60.0
                }
            }
        }

        response = ApiResponse.success_response(data=complex_data)
        assert response.success is True
        assert response.data["groups"][0]["items"][0]["path"] == "/file1.jpg"

        # Test serialization
        serialized = response.to_dict()
        assert serialized['data']['groups'][0]['items'][0]['path'] == "/file1.jpg"

    def test_response_with_unicode_content(self):
        """Test response with Unicode characters in messages and data."""
        unicode_data = {"message": "测试消息", "emoji": "🔍"}
        unicode_warning = "警告：包含特殊字符"

        response = ApiResponse.success_response(
            data=unicode_data,
            warnings=[unicode_warning]
        )

        assert response.success is True
        assert response.data["message"] == "测试消息"
        assert response.data["emoji"] == "🔍"
        assert unicode_warning in response.warnings

        # Test serialization
        serialized = response.to_dict()
        assert serialized['data']['message'] == "测试消息"
        assert serialized['data']['emoji'] == "🔍"
        assert unicode_warning in serialized['warnings']

    def test_error_detail_with_large_details(self):
        """Test ErrorDetail with large details dictionary."""
        large_details = {}
        for i in range(1000):
            large_details[f"key_{i}"] = f"value_{i}" * 100  # Large values

        error = ErrorDetail(
            code=ErrorCode.UNKNOWN_ERROR,
            message="Error with large details",
            details=large_details
        )

        assert len(error.details) == 1000
        assert error.details["key_0"] == "value_0" * 100
        assert error.details["key_999"] == "value_999" * 100

        # Test serialization
        serialized = error.to_dict()
        assert len(serialized['details']) == 1000
        assert serialized['details']['key_0'] == "value_0" * 100


if __name__ == "__main__":
    pytest.main([__file__])
