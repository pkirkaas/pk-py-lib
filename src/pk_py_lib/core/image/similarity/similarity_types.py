"""
src/pk_py_lib/core/image/similarity/types.py

Shared types, exceptions, and constants for the similarity detection module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any
import traceback

# Valid image file extensions for processing
VALID_IMAGE_EXTENSIONS: Set[str] = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}


class InvalidImageError(Exception):
    """
    Raised when an image file is invalid or cannot be processed.

    This exception is raised when attempting to process a file that is not a valid
    image, is corrupted, has an unsupported format, or cannot be opened for any reason.

    Args:
        path (str): The path to the invalid image file.
        details (str): Detailed description of the issue encountered.

    Attributes:
        path (str): The file path that caused the error.
        details (str): Specific details about why the image is invalid.

    Example:
        >>> raise InvalidImageError("/path/to/img.jpg", "Unsupported format")
        InvalidImageError: Invalid image at /path/to/img.jpg: Unsupported format
    """
    def __init__(self, path: str, details: str):
        self.path = path
        self.details = details
        super().__init__(f"Invalid image at {path}: {details}")


class SimilarityError(Exception):
    """
    Base exception for similarity computation errors.

    This exception is raised when there are errors in hash computation, similarity
    detection, clustering, or other similarity-related operations that are not
    specifically related to invalid image files.

    Args:
        message (str): Error message with details about the failure.

    Example:
        >>> raise SimilarityError("Hash computation failed due to invalid parameters")
        SimilarityError: Hash computation failed due to invalid parameters
    """
    def __init__(self, message: str):
        super().__init__(message)


@dataclass
class ErrorContext:
    """
    Enhanced error context that preserves detailed information about failures.

    This class captures comprehensive error information including the original
    exception, file path, operation details, and execution context to help with
    debugging and diagnosis of hash computation failures.

    Args:
        file_path (str): Path to the file being processed when error occurred
        operation (str): Operation being performed (e.g., 'load_image', 'compute_phash')
        original_exception (Exception): The original exception that was raised
        error_type (str): Type of error (e.g., 'PIL_UnidentifiedImageError', 'IOError')
        backend (str): Backend being used (e.g., 'PIL', 'OpenCV')
        additional_context (Dict[str, Any]): Additional context information

    Attributes:
        timestamp (str): When the error occurred
        traceback_str (str): Full traceback as string
        error_chain (List[str]): Chain of exceptions for nested errors

    Example:
        >>> try:
        ...     # Some operation that fails
        ...     pass
        ... except Exception as e:
        ...     context = ErrorContext(
        ...         file_path="/path/to/img.jpg",
        ...         operation="load_image",
        ...         original_exception=e,
        ...         error_type=type(e).__name__,
        ...         backend="PIL"
        ...     )
    """
    file_path: str
    operation: str
    original_exception: Exception
    error_type: str
    backend: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())
    traceback_str: str = field(init=False)
    error_chain: List[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        """Post-initialization processing to capture traceback and error chain."""
        # Capture full traceback
        self.traceback_str = traceback.format_exc()

        # Build error chain for nested exceptions
        current = self.original_exception
        self.error_chain = []
        while current:
            self.error_chain.append(f"{type(current).__name__}: {str(current)}")
            current = current.__cause__ if hasattr(current, '__cause__') and current.__cause__ else None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error context to dictionary for logging/serialization.

        Returns:
            Dictionary representation of the error context
        """
        return {
            'file_path': self.file_path,
            'operation': self.operation,
            'error_type': self.error_type,
            'backend': self.backend,
            'timestamp': self.timestamp,
            'original_message': str(self.original_exception),
            'traceback': self.traceback_str,
            'error_chain': self.error_chain,
            'additional_context': self.additional_context
        }

    def get_summary(self) -> str:
        """
        Get a concise summary of the error for logging.

        Returns:
            Concise error summary string
        """
        backend_info = f" (backend: {self.backend})" if self.backend else ""
        return f"{self.operation} failed for {self.file_path}{backend_info}: {self.error_type}: {str(self.original_exception)}"


class DetailedSimilarityError(SimilarityError):
    """
    Enhanced similarity error with detailed context information.

    This exception extends SimilarityError to include comprehensive error
    context, making debugging and diagnosis much easier.

    Args:
        message (str): Error message
        context (ErrorContext): Detailed error context information

    Attributes:
        context (ErrorContext): The detailed error context
    """
    def __init__(self, message: str, context: ErrorContext):
        self.context = context
        super().__init__(message)


@dataclass(frozen=True)
class ExactDuplicateSet:
    """
    Immutable representation of a set of exact duplicate files based on content hash equality.

    This dataclass groups files that are byte-for-byte identical, identified by matching
    XXH3 content hashes. It is used in the two-phase similarity detection process to
    deduplicate before perceptual hashing, improving efficiency by computing perceptual
    hashes only once per unique file content.

    The representative_path is selected as the lexicographically smallest path in the set
    for consistency and deterministic behavior across multiple runs.

    Args:
        id (int): Unique integer identifier for this exact duplicate set.
        paths (List[str]): Sorted list of absolute file paths in the set (minimum 2 paths).
        representative_path (str): The path used as representative for perceptual hashing
            computations. This is always the lexicographically smallest path in the set.

    Attributes:
        id (int): The unique set identifier.
        paths (List[str]): All file paths in this duplicate set.
        representative_path (str): The canonical representative path for this set.

    Example:
        >>> exact_set = ExactDuplicateSet(
        ...     id=1,
        ...     paths=["/path/to/dup1.jpg", "/path/to/dup2.jpg"],
        ...     representative_path="/path/to/dup1.jpg"
        ... )
        >>> len(exact_set.paths)
        2
        >>> exact_set.representative_path
        '/path/to/dup1.jpg'

    Note:
        This class is frozen (immutable) to ensure data integrity and thread safety
        during multi-phase processing.
    """
    id: int
    paths: List[str]
    representative_path: str
