"""
Hash computation for image similarity detection.

This module provides hash computation functionality for perceptual
similarity detection using pHash and wHash algorithms.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import imagehash
    from PIL import Image
    import numpy as np
except ImportError as e:
    raise ImportError("Required dependencies not available. Install with: pip install imagehash pillow numpy") from e

from ...logging.logger import get_logger
from .types import HashAlgorithm, HashResult, ImageMetadata, InvalidImageError, HashComputationError


logger = get_logger(__name__)


def compute_phash(
    image_path: Union[str, Path],
    hash_size: int = 8,
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Optional[str]:
    """
    Compute perceptual hash (pHash) for an image.

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash (default: 8 for 64-bit hash)
        settings: Optional settings dictionary
        cache_manager: Optional cache manager for caching results

    Returns:
        Hexadecimal hash string or None if computation fails
    """
    start_time = time.time()

    try:
        # Validate parameters
        if hash_size < 4 or hash_size > 64:
            raise ValueError(f"hash_size must be between 4 and 64, got {hash_size}")

        image_path = Path(image_path)

        # Check cache if available
        if cache_manager:
            cached_hash = cache_manager.get_phash(image_path)
            if cached_hash:
                logger.debug(f"Cache hit for pHash: {image_path}")
                return cached_hash

        # Load and process image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Compute pHash
            hash_obj = imagehash.phash(img, hash_size=hash_size)
            hash_str = str(hash_obj)

        # Cache result if manager available
        if cache_manager:
            cache_manager.set_phash(image_path, hash_str)

        computation_time = time.time() - start_time
        logger.debug(f"Computed pHash for {image_path}: {hash_str} ({computation_time:.3f}s)")

        return hash_str

    except Exception as e:
        logger.warning(f"Failed to compute pHash for {image_path}: {e}")
        return None


def compute_whash(
    image_path: Union[str, Path],
    hash_size: int = 8,
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Optional[str]:
    """
    Compute wavelet hash (wHash) for an image.

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash (default: 8 for 64-bit hash)
        settings: Optional settings dictionary
        cache_manager: Optional cache manager for caching results

    Returns:
        Hexadecimal hash string or None if computation fails
    """
    start_time = time.time()

    try:
        # Validate parameters
        if hash_size < 4 or hash_size > 64:
            raise ValueError(f"hash_size must be between 4 and 64, got {hash_size}")

        image_path = Path(image_path)

        # Check cache if available
        if cache_manager:
            cached_hash = cache_manager.get_whash(image_path)
            if cached_hash:
                logger.debug(f"Cache hit for wHash: {image_path}")
                return cached_hash

        # Load and process image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Compute wHash
            hash_obj = imagehash.whash(img, hash_size=hash_size)
            hash_str = str(hash_obj)

        # Cache result if manager available
        if cache_manager:
            cache_manager.set_whash(image_path, hash_str)

        computation_time = time.time() - start_time
        logger.debug(f"Computed wHash for {image_path}: {hash_str} ({computation_time:.3f}s)")

        return hash_str

    except Exception as e:
        logger.warning(f"Failed to compute wHash for {image_path}: {e}")
        return None


def compute_xxh3(
    file_path: Union[str, Path],
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Optional[str]:
    """
    Compute XXH3 hash for a file.

    Args:
        file_path: Path to the file
        settings: Optional settings dictionary
        cache_manager: Optional cache manager for caching results

    Returns:
        Hexadecimal hash string or None if computation fails
    """
    start_time = time.time()

    try:
        import xxhash

        file_path = Path(file_path)

        # Check cache if available
        if cache_manager:
            cached_hash = cache_manager.get_xxh3(file_path)
            if cached_hash:
                logger.debug(f"Cache hit for XXH3: {file_path}")
                return cached_hash

        # Compute XXH3 hash
        with open(file_path, 'rb') as f:
            hasher = xxhash.xxh3_64()
            while True:
                data = f.read(8192)  # Read in chunks
                if not data:
                    break
                hasher.update(data)

        hash_str = hasher.hexdigest()

        # Cache result if manager available
        if cache_manager:
            cache_manager.set_xxh3(file_path, hash_str)

        computation_time = time.time() - start_time
        logger.debug(f"Computed XXH3 for {file_path}: {hash_str} ({computation_time:.3f}s)")

        return hash_str

    except Exception as e:
        logger.warning(f"Failed to compute XXH3 for {file_path}: {e}")
        return None


def compute_phash_batch(
    image_paths: List[Union[str, Path]],
    hash_size: int = 8,
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Dict[str, Optional[str]]:
    """
    Compute pHash for multiple images.

    Args:
        image_paths: List of image paths
        hash_size: Size of the hash
        settings: Optional settings dictionary
        cache_manager: Optional cache manager

    Returns:
        Dictionary mapping paths to hash strings or None
    """
    results = {}
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        try:
            hash_str = compute_phash(path, hash_size, settings, cache_manager)
            results[str(path)] = hash_str

            if (i + 1) % 10 == 0:
                logger.debug(f"Processed {i + 1}/{total} images for pHash")

        except Exception as e:
            logger.warning(f"Batch pHash failed for {path}: {e}")
            results[str(path)] = None

    return results


def compute_whash_batch(
    image_paths: List[Union[str, Path]],
    hash_size: int = 8,
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Dict[str, Optional[str]]:
    """
    Compute wHash for multiple images.

    Args:
        image_paths: List of image paths
        hash_size: Size of the hash
        settings: Optional settings dictionary
        cache_manager: Optional cache manager

    Returns:
        Dictionary mapping paths to hash strings or None
    """
    results = {}
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        try:
            hash_str = compute_whash(path, hash_size, settings, cache_manager)
            results[str(path)] = hash_str

            if (i + 1) % 10 == 0:
                logger.debug(f"Processed {i + 1}/{total} images for wHash")

        except Exception as e:
            logger.warning(f"Batch wHash failed for {path}: {e}")
            results[str(path)] = None

    return results


def compute_xxh3_batch(
    file_paths: List[Union[str, Path]],
    settings: Optional[Dict[str, Any]] = None,
    cache_manager: Optional[Any] = None
) -> Dict[str, Optional[str]]:
    """
    Compute XXH3 hash for multiple files.

    Args:
        file_paths: List of file paths
        settings: Optional settings dictionary
        cache_manager: Optional cache manager

    Returns:
        Dictionary mapping paths to hash strings or None
    """
    results = {}
    total = len(file_paths)

    for i, path in enumerate(file_paths):
        try:
            hash_str = compute_xxh3(path, settings, cache_manager)
            results[str(path)] = hash_str

            if (i + 1) % 10 == 0:
                logger.debug(f"Processed {i + 1}/{total} files for XXH3")

        except Exception as e:
            logger.warning(f"Batch XXH3 failed for {path}: {e}")
            results[str(path)] = None

    return results


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two hash strings.

    Args:
        hash1: First hash string
        hash2: Second hash string

    Returns:
        Hamming distance (number of differing bits)
    """
    # Convert hex strings to integers
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)

        # Calculate XOR and count differing bits
        xor_result = int1 ^ int2
        return bin(xor_result).count('1')

    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid hash strings: {hash1}, {hash2}") from e


def normalize_similarity_score(distance: int, max_distance: int = 64) -> float:
    """
    Normalize Hamming distance to similarity score (0.0-1.0).

    Args:
        distance: Hamming distance
        max_distance: Maximum possible distance

    Returns:
        Similarity score (1.0 = identical, 0.0 = maximum difference)
    """
    if max_distance <= 0:
        raise ValueError("max_distance must be positive")

    if distance < 0:
        raise ValueError("distance cannot be negative")

    if distance > max_distance:
        raise ValueError(f"distance {distance} exceeds max_distance {max_distance}")

    return 1.0 - (distance / max_distance)


def get_image_metadata(image_path: Union[str, Path]) -> ImageMetadata:
    """
    Get metadata for an image file.

    Args:
        image_path: Path to the image file

    Returns:
        ImageMetadata object

    Raises:
        InvalidImageError: If image cannot be loaded or is invalid
    """
    try:
        image_path = Path(image_path)

        # Get file stats
        stat = image_path.stat()
        size = stat.st_size
        mod_time = stat.st_mtime

        # Load image to get dimensions and format
        with Image.open(image_path) as img:
            width, height = img.size
            format_name = img.format or "Unknown"

        # Calculate computed properties
        aspect_ratio = width / height if height > 0 else 0
        megapixels = (width * height) / 1_000_000

        return ImageMetadata(
            path=str(image_path),
            size=size,
            width=width,
            height=height,
            format=format_name,
            mod_time=mod_time,
            aspect_ratio=aspect_ratio,
            megapixels=megapixels
        )

    except Exception as e:
        raise InvalidImageError(f"Failed to get metadata for {image_path}: {e}", file_path=str(image_path))


def get_image_metadata_batch(
    image_paths: List[Union[str, Path]]
) -> Dict[str, Optional[ImageMetadata]]:
    """
    Get metadata for multiple images.

    Args:
        image_paths: List of image paths

    Returns:
        Dictionary mapping paths to ImageMetadata or None
    """
    results = {}
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        try:
            metadata = get_image_metadata(path)
            results[str(path)] = metadata

            if (i + 1) % 10 == 0:
                logger.debug(f"Processed metadata for {i + 1}/{total} images")

        except Exception as e:
            logger.warning(f"Failed to get metadata for {path}: {e}")
            results[str(path)] = None

    return results
