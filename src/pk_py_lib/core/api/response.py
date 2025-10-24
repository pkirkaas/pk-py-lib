"""
API response patterns for pk-py-lib.

This module provides consistent API response patterns and error codes
used throughout the library's API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Generic, Optional, TypeVar
import traceback


T = TypeVar('T')


class ErrorCodes(Enum):
    """Canonical machine-readable error codes for API responses."""

    # Database errors
    LOCKED_DB = "LOCKED_DB"               # Database locked / concurrent access
    CORRUPTED_DB = "CORRUPTED_DB"         # Database corrupted or integrity check failed

    # File system errors
    FILE_MISSING = "FILE_MISSING"         # File not found on disk
    PERMISSION_DENIED = "PERMISSION_DENIED"  # Read/write permission denied
    PATH_INVALID = "PATH_INVALID"         # Invalid path format or structure

    # Image processing errors
    CORRUPTED_IMAGE = "CORRUPTED_IMAGE"   # Image file corrupted or unreadable
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"  # Image format not supported
    INVALID_DIMENSIONS = "INVALID_DIMENSIONS"  # Image dimensions out of range

    # Configuration errors
    INVALID_CONFIG = "INVALID_CONFIG"     # Configuration validation failed
    SCHEMA_VALIDATION_ERROR = "SCHEMA_VALIDATION_ERROR"  # JSON schema validation failed
    DUPLICATE_NAME = "DUPLICATE_NAME"     # Profile name already exists

    # Processing errors
    ALGORITHM_ERROR = "ALGORITHM_ERROR"   # Algorithm computation failed
    OUT_OF_MEMORY = "OUT_OF_MEMORY"       # Memory allocation failure
    TIMEOUT = "TIMEOUT"                   # Operation timed out

    # Network and external errors
    NETWORK_ERROR = "NETWORK_ERROR"       # Network or mount error for remote paths

    # Generic errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"       # Fallback/unspecified error
    VALIDATION_ERROR = "VALIDATION_ERROR" # Data validation failed


@dataclass
class ApiResponse(Generic[T]):
    """
    Standard API response wrapper.

    Fields:
        success: Indicates operation success (True/False).
        data: Optional payload of type T when success is True.
        error: Human-readable error message when success is False.
        code: Machine-readable error code (see ErrorCodes enum).
        metadata: Optional dictionary with extra contextual data.
    """
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate response consistency."""
        if self.success and self.error is not None:
            raise ValueError("Success response cannot have error message")
        if not self.success and self.data is not None:
            raise ValueError("Error response cannot have data")
        if not self.success and self.code is None:
            raise ValueError("Error response must have error code")


class ApiError(Exception):
    """Base API error class."""

    def __init__(
        self,
        message: str,
        code: ErrorCodes,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        self.cause = cause
        super().__init__(message)


def create_success_response(data: T, metadata: Optional[Dict[str, Any]] = None) -> ApiResponse[T]:
    """
    Create a successful API response.

    Args:
        data: Response data
        metadata: Optional metadata

    Returns:
        Success ApiResponse
    """
    return ApiResponse(
        success=True,
        data=data,
        metadata=metadata or {}
    )


def create_error_response(
    error: Union[str, Exception],
    code: ErrorCodes,
    details: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> ApiResponse:
    """
    Create an error API response.

    Args:
        error: Error message or exception
        code: Error code
        details: Optional error details
        metadata: Optional metadata

    Returns:
        Error ApiResponse
    """
    if isinstance(error, Exception):
        message = str(error)
        # Include traceback in metadata for debugging
        if metadata is None:
            metadata = {}
        metadata["traceback"] = traceback.format_exc()
    else:
        message = error

    return ApiResponse(
        success=False,
        error=message,
        code=code.value,
        metadata=metadata or {}
    )


def map_exception_to_error_code(exception: Exception) -> ErrorCodes:
    """
    Map Python exceptions to canonical error codes.

    Args:
        exception: Exception to map

    Returns:
        Corresponding error code
    """
    import sqlite3

    # Map by exception type and message content
    if isinstance(exception, FileNotFoundError):
        return ErrorCodes.FILE_MISSING
    elif isinstance(exception, PermissionError):
        return ErrorCodes.PERMISSION_DENIED
    elif isinstance(exception, MemoryError):
        return ErrorCodes.OUT_OF_MEMORY
    elif isinstance(exception, ValueError):
        return ErrorCodes.INVALID_CONFIG
    elif isinstance(exception, sqlite3.OperationalError):
        if "locked" in str(exception).lower():
            return ErrorCodes.LOCKED_DB
        else:
            return ErrorCodes.CORRUPTED_DB
    elif isinstance(exception, TimeoutError):
        return ErrorCodes.TIMEOUT
    elif isinstance(exception, OSError):
        if "network" in str(exception).lower() or "mount" in str(exception).lower():
            return ErrorCodes.NETWORK_ERROR
        else:
            return ErrorCodes.FILE_MISSING
    else:
        return ErrorCodes.UNKNOWN_ERROR
