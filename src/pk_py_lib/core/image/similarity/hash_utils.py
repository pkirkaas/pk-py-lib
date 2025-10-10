"""
Hash computation utilities for image similarity detection.

This module provides common utilities to reduce code duplication
across hash computation functions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, Optional, Union, Dict, Callable
import cv2
import numpy as np
from PIL import Image

from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheDBError
from pk_py_lib.core.logging.logger import get_logger

from .types import InvalidImageError, SimilarityError
from .validation import is_image_extension, validate_hash_size, validate_image_path

logger = get_logger(__name__)


def load_image_with_fallback(image_path: Union[str, Path]) -> np.ndarray:
    """
    Load image using PIL with OpenCV fallback.

    This function provides robust image loading with multiple backend support
    to handle various image formats and edge cases.

    Args:
        image_path: Path to the image file

    Returns:
        numpy.ndarray: Loaded image as numpy array in BGR format

    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If image cannot be loaded by any backend
    """
    path = validate_image_path(image_path)

    # Try PIL first for better compatibility with various formats
    try:
        with Image.open(path) as img:
            # Handle GIF animations by taking first frame
            if hasattr(img, 'is_animated') and img.is_animated:
                img.seek(0)  # Ensure we're on the first frame

            # Convert to RGB if necessary for consistent hashing
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Convert PIL Image to numpy array in BGR format for OpenCV compatibility
            img_array = np.array(img)
            if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                # RGB to BGR conversion for OpenCV compatibility
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            return img_array

    except Exception as pil_exc:
        logger.warning(f"PIL loading failed for {path}: {pil_exc}, trying OpenCV fallback")

        # Fallback to OpenCV if PIL fails
        try:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV")
            return image
        except Exception as cv_exc:
            logger.error(f"OpenCV fallback also failed for {path}: {cv_exc}")
            raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV: {pil_exc}")


def validate_hash_parameters(
    hash_size: int,
    algorithm: str,
    color_mode: bool = False
) -> Tuple[int, str, bool]:
    """
    Validate and normalize hash computation parameters.

    Args:
        hash_size: Desired hash size (will be normalized to valid values)
        algorithm: Hash algorithm name
        color_mode: Whether to use color hashing

    Returns:
        Tuple of (normalized_hash_size, normalized_algorithm, color_mode)

    Raises:
        ValueError: If parameters are invalid
    """
    # Validate hash size
    validate_hash_size(hash_size)

    # Normalize algorithm name to lowercase
    normalized_algorithm = algorithm.lower().strip()

    # Validate algorithm
    supported_algorithms = ['phash', 'whash', 'ahash', 'dhash']
    if normalized_algorithm not in supported_algorithms:
        raise ValueError(f"Unsupported algorithm: {algorithm}. Supported: {', '.join(supported_algorithms)}")

    # Ensure color_mode is boolean
    color_mode = bool(color_mode)

    return hash_size, normalized_algorithm, color_mode


def normalize_hash_length(hash_value: str, target_size: int = 16) -> str:
    """
    Normalize hash string to target size.

    Args:
        hash_value: Input hash string
        target_size: Target hash size in characters (default 16 for 64-bit)

    Returns:
        Normalized hash string

    Raises:
        SimilarityError: If hash is too short or too long
    """
    if len(hash_value) < 8:
        raise SimilarityError(f"Computed hash too short: {len(hash_value)} characters")
    elif len(hash_value) > 32:
        raise SimilarityError(f"Computed hash too long: {len(hash_value)} characters")
    elif len(hash_value) != target_size:
        logger.warning(f"Computed hash length {len(hash_value)}, expected {target_size}, normalizing")
        if len(hash_value) < target_size:
            hash_value = hash_value.zfill(target_size)
        else:
            hash_value = hash_value[:target_size]

    return hash_value


def compute_color_channels(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract and process color channels for color hashing.

    Args:
        image: Input image in BGR format

    Returns:
        Tuple of (blue_channel, green_channel, red_channel) as numpy arrays
    """
    if len(image.shape) != 3 or image.shape[2] != 3:
        raise ValueError("Input image must be 3-channel BGR format")

    # Split BGR channels
    blue_channel, green_channel, red_channel = cv2.split(image)

    return blue_channel, green_channel, red_channel


def combine_color_hashes(
    blue_hash: str,
    green_hash: str,
    red_hash: str
) -> str:
    """
    Combine individual color channel hashes into single hash.

    Args:
        blue_hash: Hash from blue channel
        green_hash: Hash from green channel
        red_hash: Hash from red channel

    Returns:
        Combined color hash
    """
    # Convert hex strings to integers
    int_b = int(blue_hash, 16)
    int_g = int(green_hash, 16)
    int_r = int(red_hash, 16)

    # Average the integer representations
    avg_int = (int_b + int_g + int_r) // 3

    # Format as 64-bit hex (16 chars), truncate/pad if needed
    combined_hash = f"{avg_int:064x}"[:16].zfill(16)

    return combined_hash


def compute_generic_color_hash(
    image: np.ndarray,
    hash_size: int,
    hash_function: Callable
) -> str:
    """
    Generic color hash computation for any hash algorithm.

    This function eliminates duplication between color_phash and color_whash
    by providing a generic interface for color hashing.

    Args:
        image: Input image in BGR format
        hash_size: Hash size for each channel
        hash_function: Function to compute hash for single channel

    Returns:
        Combined color hash
    """
    # Extract color channels
    blue_channel, green_channel, red_channel = compute_color_channels(image)

    # Convert channels to PIL Images for hashing
    blue_pil = Image.fromarray(blue_channel)
    green_pil = Image.fromarray(green_channel)
    red_pil = Image.fromarray(red_channel)

    # Compute hash for each channel
    h_b = hash_function(blue_pil, hash_size=hash_size)
    h_g = hash_function(green_pil, hash_size=hash_size)
    h_r = hash_function(red_pil, hash_size=hash_size)

    # Convert to strings and combine
    blue_hash = str(h_b)
    green_hash = str(h_g)
    red_hash = str(h_r)

    # Normalize each hash to consistent length
    blue_hash = normalize_hash_length(blue_hash)
    green_hash = normalize_hash_length(green_hash)
    red_hash = normalize_hash_length(red_hash)

    # Combine the hashes
    return combine_color_hashes(blue_hash, green_hash, red_hash)


def check_cache_for_hash(
    image_path: str,
    hash_type: str,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Check cache for existing hash value.

    Args:
        image_path: Path to the image file
        hash_type: Type of hash to check (e.g., 'phash', 'whash')
        flat_cache_manager: Optional FlatCacheManager instance

    Returns:
        Cached hash value or None if not found
    """
    if not flat_cache_manager:
        return None

    try:
        hashes = flat_cache_manager.get_hashes([image_path], [hash_type])
        cached_hash = hashes.get(image_path, {}).get(hash_type)
        if cached_hash is not None:
            logger.debug(f"Flat cache hit for {hash_type} on {image_path}")
            return cached_hash
    except FlatCacheDBError as e:
        logger.warning(f"Flat cache DB error during {hash_type} lookup for {image_path}. "
                      f"Falling back to computation. Error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error during flat cache {hash_type} lookup for {image_path}. "
                      f"Falling back to computation. Error: {e}")

    return None


def handle_image_loading_errors(
    image_path: str,
    error: Exception
) -> None:
    """
    Handle and categorize image loading errors.

    Args:
        image_path: Path to the image file
        error: The exception that occurred

    Raises:
        InvalidImageError: If image format is unsupported or corrupted
        SimilarityError: For other computation errors
        IOError: For file access errors
    """
    error_details = str(error).lower()

    if "cannot identify" in error_details or "unidentified image" in error_details:
        raise InvalidImageError(image_path, "Unsupported or corrupted image format")
    elif isinstance(error, (IOError, OSError)):
        logger.error(f"IO error loading image {image_path}: {error}", exception=error)
        raise error
    else:
        logger.error(f"Image loading failed for {image_path}: {error}", exception=error)
        raise SimilarityError(f"Image loading failed: {error}") from error


def get_effective_hash_size(
    default_size: int,
    algorithm: str,
    settings: Optional[Dict] = None
) -> int:
    """
    Get effective hash size considering settings overrides.

    Args:
        default_size: Default hash size
        algorithm: Hash algorithm name
        settings: Optional settings dictionary

    Returns:
        Effective hash size
    """
    effective_size = default_size

    if settings and "criteria" in settings and algorithm in settings["criteria"]:
        effective_size = settings["criteria"][algorithm].get("hash_size", default_size)

    return effective_size
