"""
src/pk_py_lib/core/image/similarity/validation.py

Validation utilities for hash computation and similarity detection.
Includes parameter validation, hash validation, and normalization functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pk_py_lib.core.logging.logger import get_logger

from .types import VALID_IMAGE_EXTENSIONS, InvalidImageError, SimilarityError

logger = get_logger(__name__)


def is_image_extension(path: str) -> bool:
    """
    Check if the file has a valid image extension.

    Validates that the file extension is one of the supported image formats
    defined in VALID_IMAGE_EXTENSIONS. The check is case-insensitive.

    Args:
        path (str): File path to check (can be relative or absolute).

    Returns:
        bool: True if the extension is a known image format, False otherwise.

    Example:
        >>> is_image_extension("/path/to/image.jpg")
        True
        >>> is_image_extension("/path/to/document.pdf")
        False
        >>> is_image_extension("/path/to/IMAGE.PNG")
        True
    """
    return Path(path).suffix.lower() in VALID_IMAGE_EXTENSIONS


def validate_hash_size(hash_size: int) -> None:
    """
    Validate that hash_size is within acceptable range.

    Hash size must be between 4 and 64 (inclusive). This range ensures the hash
    has sufficient bits for meaningful similarity detection (minimum 16 bits with
    hash_size=4) while avoiding excessive computational cost (maximum 4096 bits
    with hash_size=64).

    Args:
        hash_size (int): The hash matrix size to validate.

    Raises:
        SimilarityError: If hash_size is outside the valid range [4, 64].

    Example:
        >>> validate_hash_size(8)  # Valid
        >>> validate_hash_size(16)  # Valid
        >>> validate_hash_size(2)  # Raises SimilarityError
        Traceback (most recent call last):
        ...
        SimilarityError: hash_size must be between 4 and 64, got 2
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")


def validate_image_path(image_path: str) -> Path:
    """
    Validate that the image path exists and is a file.

    Converts the path string to a Path object and verifies it points to an
    existing file. This is a preliminary check before attempting to open or
    process the image.

    Args:
        image_path (str): Path to the image file (relative or absolute).

    Returns:
        Path: The validated Path object.

    Raises:
        InvalidImageError: If the path doesn't exist or is not a file.

    Example:
        >>> path = validate_image_path("/path/to/existing/image.jpg")
        >>> path.is_file()
        True
        >>> validate_image_path("/path/to/nonexistent.jpg")
        Traceback (most recent call last):
        ...
        InvalidImageError: Invalid image at /path/to/nonexistent.jpg: File does not exist or is not a file
    """
    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")
    return path


def validate_and_normalize_hash(
    hash_str: str,
    expected_length: int = 16,
    index: Optional[int] = None
) -> str:
    """
    Validate and normalize a hash string to the expected length.

    Handles various hash string formats and lengths gracefully:
    - Standard 16-character (64-bit) hashes: passed through unchanged
    - 21-character hashes: extracts only hex digits and truncates to 16
    - Short hashes (8-15 chars): zero-padded to 16 characters
    - Long hashes (17-32 chars): truncated to 16 characters
    - Invalid lengths (<8 or >32): raises ValueError

    All hash characters must be valid hexadecimal digits (0-9, a-f, A-F).

    Args:
        hash_str (str): The hash string to validate and normalize.
        expected_length (int): Expected final length (default 16 for 64-bit hashes).
        index (Optional[int]): Optional index for error messages (e.g., position in a list).

    Returns:
        str: Normalized hash string of exactly expected_length characters, lowercase hex.

    Raises:
        ValueError: If hash is empty, too short (<8), too long (>32), or contains
            non-hexadecimal characters.

    Example:
        >>> validate_and_normalize_hash("a1b2c3d4e5f67890")
        'a1b2c3d4e5f67890'
        >>> validate_and_normalize_hash("abc123")  # Short, padded
        '0000000000abc123'
        >>> validate_and_normalize_hash("a" * 21)  # 21 chars, extract hex and truncate
        'aaaaaaaaaaaaaaaa'
        >>> validate_and_normalize_hash("xyz")  # Invalid
        Traceback (most recent call last):
        ...
        ValueError: Hash too short at index None: 3 (minimum 8 characters)
    """
    index_str = f" at index {index}" if index is not None else ""

    if not isinstance(hash_str, str) or not hash_str:
        raise ValueError(f"Empty or invalid hash{index_str}")

    # Handle variable hash lengths gracefully
    if len(hash_str) == expected_length:
        # Standard length - validate hex characters
        if not all(c in '0123456789abcdefABCDEF' for c in hash_str):
            raise ValueError(f"Invalid hex characters in hash{index_str}: {hash_str}")
        return hash_str.lower()

    elif len(hash_str) == 21:
        # Handle 21-character hashes - extract only hex digits
        logger.warning(f"Hash length 21{index_str}, extracting hex digits for compatibility")
        hex_digits = ''.join(c for c in hash_str if c in '0123456789abcdefABCDEF')
        if len(hex_digits) >= expected_length:
            return hex_digits[:expected_length].lower()
        else:
            # Pad if we don't have enough hex digits
            return hex_digits.zfill(expected_length).lower()

    elif len(hash_str) < 8:
        raise ValueError(f"Hash too short{index_str}: {len(hash_str)} (minimum 8 characters)")

    elif len(hash_str) > 32:
        raise ValueError(f"Hash too long{index_str}: {len(hash_str)} (maximum 32 characters)")

    else:
        # For lengths between 8-32, pad or truncate to expected_length
        if len(hash_str) < expected_length:
            logger.warning(f"Hash length {len(hash_str)}{index_str}, padding to {expected_length} characters")
            normalized = hash_str.zfill(expected_length)
        else:
            logger.warning(f"Hash length {len(hash_str)}{index_str}, truncating to {expected_length} characters")
            normalized = hash_str[:expected_length]

        # Validate hex characters after normalization
        if not all(c in '0123456789abcdefABCDEF' for c in normalized):
            raise ValueError(f"Invalid hex characters in hash{index_str}: {hash_str}")

        return normalized.lower()


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Compute the Hamming distance (bit differences) between two 64-bit hex hashes.

    Converts hexadecimal strings to integers, XORs them, and counts the '1' bits
    in the binary result. This measures perceptual similarity: lower distance
    indicates more similar images (0 = identical, 64 = completely different).

    The hash strings are automatically normalized before comparison, so they can
    be of varying lengths (8-32 characters) as long as they contain valid hex digits.

    Args:
        hash1 (str): First 16-character hex hash (will be normalized if different length).
        hash2 (str): Second 16-character hex hash (will be normalized if different length).

    Returns:
        int: Hamming distance (0 for identical, up to 64 for completely different).

    Raises:
        ValueError: If either hash cannot be normalized or contains invalid characters.

    Example:
        >>> hamming_distance('a1b2c3d4e5f67890', 'a1b2c3d4e5f67891')
        1
        >>> hamming_distance('0000000000000000', 'ffffffffffffffff')
        64
        >>> hamming_distance('abc', 'def')  # Short hashes, will be padded
        48

    Note:
        For perceptual image hashing, typical similarity thresholds are:
        - 0-5: Nearly identical images (minor differences)
        - 6-10: Very similar images (same content, different quality/size)
        - 11-15: Similar images (recognizable as related)
        - 16+: Different images
    """
    try:
        # Normalize both hashes to 16 characters
        norm_hash1 = validate_and_normalize_hash(hash1, expected_length=16)
        norm_hash2 = validate_and_normalize_hash(hash2, expected_length=16)

        # Convert to integers and XOR
        i1 = int(norm_hash1, 16)
        i2 = int(norm_hash2, 16)
        xor_result = i1 ^ i2

        # Count '1' bits in the XOR result
        distance = bin(xor_result).count('1')

        logger.debug(f"Hamming distance between {norm_hash1[:8]}... and {norm_hash2[:8]}...: {distance}")
        return distance

    except ValueError as e:
        raise ValueError(f"Hamming distance computation failed: {e}") from e


def validate_threshold(threshold: int, algorithm: str = "hash") -> None:
    """
    Validate that a similarity threshold is within acceptable range.

    For perceptual hashing algorithms (pHash, wHash), the threshold represents
    the maximum Hamming distance (0-64) for images to be considered similar.

    Args:
        threshold (int): The similarity threshold to validate.
        algorithm (str): Name of the algorithm (for error messages).

    Raises:
        ValueError: If threshold is outside the valid range [0, 64].

    Example:
        >>> validate_threshold(10)  # Valid
        >>> validate_threshold(10, "phash")  # Valid with algorithm name
        >>> validate_threshold(100)  # Raises ValueError
        Traceback (most recent call last):
        ...
        ValueError: Threshold must be 0-64, got 100
    """
    if threshold < 0 or threshold > 64:
        raise ValueError(f"Threshold must be 0-64, got {threshold}")
