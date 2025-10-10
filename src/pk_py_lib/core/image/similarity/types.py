"""
src/pk_py_lib/core/image/similarity/types.py

Shared types, exceptions, and constants for the similarity detection module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

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
