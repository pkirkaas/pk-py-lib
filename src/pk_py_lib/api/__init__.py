"""
src/pk_py_lib/api/__init__.py
API contract utilities: ApiResponse dataclass and ErrorCodes enum.
"""

from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional, Dict, Any
from enum import Enum

T = TypeVar("T")


@dataclass
class ApiResponse(Generic[T]):
    """
    Standard API response wrapper used across pk_py_lib APIs.

    Attributes
    ----------
    success : bool
        True when the operation completed successfully; False otherwise.
    data : Optional[T]
        The payload returned on success. Type is generic.
    error : Optional[str]
        Human-readable error message when success is False.
    code : Optional[str]
        Machine-readable error code (see :class:`ErrorCodes`).
    metadata : Dict[str, Any]
        Optional dictionary with additional contextual information.

    Usage example
    -------------
    >>> resp = ApiResponse(success=True, data={'id': 1})
    >>> resp.to_dict()
    {'success': True, 'data': {'id': 1}, 'error': None, 'code': None, 'metadata': {}}
    """
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the ApiResponse into a plain dictionary suitable for JSON encoding.

        Returns
        -------
        Dict[str, Any]
            Serialized representation of the response.
        """
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "code": self.code,
            "metadata": self.metadata,
        }

    @classmethod
    def ok(cls, data: Optional[T] = None, metadata: Optional[Dict[str, Any]] = None) -> "ApiResponse[T]":
        """
        Helper to construct a successful ApiResponse.

        Parameters
        ----------
        data : Optional[T]
            Payload to return.
        metadata : Optional[Dict[str, Any]]
            Additional contextual metadata.

        Returns
        -------
        ApiResponse[T]
            A success ApiResponse.
        """
        return cls(success=True, data=data, metadata=metadata or {})

    @classmethod
    def fail(cls, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> "ApiResponse[None]":
        """
        Helper to construct a failed ApiResponse.

        Parameters
        ----------
        message : str
            Human-readable error message.
        code : Optional[str]
            Machine-readable error code.
        details : Optional[Dict[str, Any]]
            Additional error details included in metadata.

        Returns
        -------
        ApiResponse[None]
            A failure ApiResponse.
        """
        return cls(success=False, data=None, error=message, code=code, metadata={"details": details} if details else {})


class ApiError(Exception):
    """
    Base class for API errors used by pk_py_lib.

    Parameters
    ----------
    message : str
        Human-readable error message.
    code : Optional[str]
        Machine-readable error code (see :class:`ErrorCodes`).
    details : Optional[Dict[str, Any]]
        Optional structured details about the failure.

    Example
    -------
    >>> raise ApiError("File not found", code=ErrorCodes.FILE_MISSING.value)
    """

    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        # Default to UNKNOWN_ERROR if code not provided; resolved at runtime
        self.message = message
        self.code = code or ErrorCodes.UNKNOWN_ERROR.value
        self.details = details or {}

    def to_response(self) -> ApiResponse[None]:
        """
        Convert the exception into an ApiResponse suitable for returning to callers.

        Returns
        -------
        ApiResponse[None]
            Failure response populated with error information.
        """
        return ApiResponse.fail(self.message, code=self.code, details=self.details)

    def __repr__(self) -> str:
        return f"ApiError(message={self.message!r}, code={self.code!r}, details={self.details!r})"


class ErrorCodes(Enum):
    """
    Canonical machine-readable error codes for API responses.

    These codes are intended for programmatic handling of errors by callers.
    """
    LOCKED_DB = "LOCKED_DB"               # Database locked / concurrent access
    FILE_MISSING = "FILE_MISSING"         # File not found on disk
    OUT_OF_MEMORY = "OUT_OF_MEMORY"       # Memory allocation failure
    PERMISSION_DENIED = "PERMISSION_DENIED"  # Read/write permission denied
    CORRUPTED_IMAGE = "CORRUPTED_IMAGE"   # Image file corrupted or unreadable
    INVALID_CONFIG = "INVALID_CONFIG"     # Configuration validation failed
    NETWORK_ERROR = "NETWORK_ERROR"       # Network or mount error for remote paths
    TIMEOUT = "TIMEOUT"                   # Operation timed out
    UNKNOWN_ERROR = "UNKNOWN_ERROR"       # Fallback/unspecified error


__all__ = ["ApiResponse", "ApiError", "ErrorCodes"]

# End of file