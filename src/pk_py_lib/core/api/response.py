"""
Standardized API response structures for the pk-py-lib project.

This module provides consistent response formats and error handling
across all components, ensuring a unified API experience.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Union
from enum import Enum
import traceback
from datetime import datetime


class ErrorCode(Enum):
    """
    Standardized error codes for consistent error handling.

    These codes provide machine-readable error identification
    while maintaining human-readable error messages.
    """

    # Success codes
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"

    # General error codes
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"

    # File system errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_ACCESS_DENIED = "FILE_ACCESS_DENIED"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"

    # Image processing errors
    IMAGE_LOAD_FAILED = "IMAGE_LOAD_FAILED"
    INVALID_IMAGE_FORMAT = "INVALID_IMAGE_FORMAT"
    IMAGE_CORRUPTED = "IMAGE_CORRUPTED"
    UNSUPPORTED_IMAGE_TYPE = "UNSUPPORTED_IMAGE_TYPE"

    # Hash computation errors
    HASH_COMPUTATION_FAILED = "HASH_COMPUTATION_FAILED"
    INVALID_HASH_ALGORITHM = "INVALID_HASH_ALGORITHM"
    INVALID_HASH_SIZE = "INVALID_HASH_SIZE"

    # Similarity detection errors
    SIMILARITY_DETECTION_FAILED = "SIMILARITY_DETECTION_FAILED"
    INSUFFICIENT_IMAGES = "INSUFFICIENT_IMAGES"
    CLUSTERING_FAILED = "CLUSTERING_FAILED"

    # Cache errors
    CACHE_ERROR = "CACHE_ERROR"
    CACHE_FULL = "CACHE_FULL"
    CACHE_CORRUPTED = "CACHE_CORRUPTED"

    # Database errors
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    DATABASE_CORRUPTED = "DATABASE_CORRUPTED"

    # Settings errors
    SETTINGS_ERROR = "SETTINGS_ERROR"
    INVALID_SETTINGS = "INVALID_SETTINGS"
    SETTINGS_NOT_FOUND = "SETTINGS_NOT_FOUND"

    # Performance errors
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"


@dataclass
class ErrorDetail:
    """
    Detailed error information for debugging and logging.

    Provides comprehensive error context including stack traces
    and additional debugging information.
    """

    code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize error details with stack trace if available."""
        if self.stack_trace is None:
            self.stack_trace = traceback.format_exc()

    def to_dict(self) -> Dict[str, Any]:
        """Convert error detail to dictionary for serialization."""
        return {
            'code': self.code.value,
            'message': self.message,
            'details': self.details,
            'stack_trace': self.stack_trace,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class ApiResponse:
    """
    Standardized API response structure.

    Provides consistent response format across all API endpoints
    and internal function calls, with support for success,
    partial success, and error states.
    """

    success: bool
    data: Optional[Any] = None
    error: Optional[ErrorDetail] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate response consistency."""
        if self.success and self.error:
            raise ValueError("Successful response cannot contain error")
        if not self.success and not self.error:
            raise ValueError("Unsuccessful response must contain error")

    @classmethod
    def success_response(
        cls,
        data: Any = None,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'ApiResponse':
        """Create a successful response."""
        return cls(
            success=True,
            data=data,
            warnings=warnings or [],
            metadata=metadata or {}
        )

    @classmethod
    def partial_success_response(
        cls,
        data: Any = None,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'ApiResponse':
        """Create a partial success response."""
        return cls(
            success=True,
            data=data,
            warnings=warnings or [],
            metadata={**(metadata or {}), 'partial_success': True}
        )

    @classmethod
    def error_response(
        cls,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'ApiResponse':
        """Create an error response."""
        error = ErrorDetail(
            code=code,
            message=message,
            details=details
        )
        return cls(
            success=False,
            error=error,
            metadata=metadata or {}
        )

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        code: Optional[ErrorCode] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'ApiResponse':
        """Create an error response from an exception."""
        if code is None:
            # Map common exceptions to error codes
            if isinstance(exception, FileNotFoundError):
                code = ErrorCode.FILE_NOT_FOUND
            elif isinstance(exception, PermissionError):
                code = ErrorCode.FILE_ACCESS_DENIED
            elif isinstance(exception, ValueError):
                code = ErrorCode.INVALID_INPUT
            elif isinstance(exception, MemoryError):
                code = ErrorCode.MEMORY_ERROR
            elif isinstance(exception, TimeoutError):
                code = ErrorCode.TIMEOUT_ERROR
            else:
                code = ErrorCode.UNKNOWN_ERROR

        error_message = message or str(exception)

        return cls.error_response(
            code=code,
            message=error_message,
            details={'exception_type': type(exception).__name__},
            metadata=metadata
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for serialization."""
        result = {
            'success': self.success,
            'timestamp': self.timestamp.isoformat(),
            'warnings': self.warnings,
            'metadata': self.metadata
        }

        if self.success:
            result['data'] = self.data
        else:
            result['error'] = self.error.to_dict() if self.error else None

        return result

    def add_warning(self, warning: str) -> None:
        """Add a warning to the response."""
        self.warnings.append(warning)

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the response."""
        self.metadata[key] = value


# Convenience functions for common response types
def success(data: Any = None, **kwargs) -> ApiResponse:
    """Create a success response."""
    return ApiResponse.success_response(data, **kwargs)


def error(code: ErrorCode, message: str, **kwargs) -> ApiResponse:
    """Create an error response."""
    return ApiResponse.error_response(code, message, **kwargs)


def from_exception(exception: Exception, **kwargs) -> ApiResponse:
    """Create an error response from an exception."""
    return ApiResponse.from_exception(exception, **kwargs)


def partial_success(data: Any = None, **kwargs) -> ApiResponse:
    """Create a partial success response."""
    return ApiResponse.partial_success_response(data, **kwargs)
