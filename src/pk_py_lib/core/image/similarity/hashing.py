"""
src/pk_py_lib/core/image/similarity/hashing.py

Hash computation functions for image similarity detection.
Supports perceptual hashing (pHash), wavelet hashing (wHash), and content hashing (XXH3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

import imagehash
from PIL import Image
import numpy as np

from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheEntry, FlatCacheDBError
from pk_py_lib.core.logging.logger import get_logger

from ...api.response import ApiResponse, ErrorCode
from .similarity_types import InvalidImageError, SimilarityError, ErrorContext, DetailedSimilarityError
from .validation import is_image_extension, validate_hash_size, validate_image_path
from .hash_utils import (
    load_image_with_fallback,
    validate_hash_parameters,
    normalize_hash_length,
    compute_color_channels,
    combine_color_hashes,
    compute_generic_color_hash,
    check_cache_for_hash,
    handle_image_loading_errors,
    get_effective_hash_size
)
from .algorithm_utils import (
    resolve_hash_algorithm,
    get_algorithm_info,
    get_default_hash_size,
    supports_color_hashing,
    list_supported_algorithms,
    initialize_algorithm_functions
)

logger = get_logger(__name__)

# Initialize algorithm functions to avoid circular dependencies
initialize_algorithm_functions()


def compute_phash_with_cache(
    image_path: str,
    hash_size: int = 8,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    return_response: bool = False
) -> Union[str, ApiResponse]:
    """
    Compute perceptual hash with enhanced caching.

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash matrix
        flat_cache_manager: Enhanced FlatCacheManager instance
        return_response: Whether to return ApiResponse

    Returns:
        Hash string or ApiResponse with cache statistics
    """
    if flat_cache_manager is None:
        # Use basic hash computation
        return _compute_phash_internal(image_path, hash_size)

    # Generate cache key
    cache_key = _generate_cache_key(image_path, "phash", hash_size)

    # Try to get from cache
    cache_response = flat_cache_manager.get(cache_key)
    if cache_response.success:
        if return_response:
            return ApiResponse.success_response(
                data=cache_response.data,
                metadata={**cache_response.metadata, 'cache_source': 'flat_cache'}
            )
        return cache_response.data

    # Compute hash if not in cache
    try:
        hash_result = _compute_phash_internal(image_path, hash_size)

        # Store in cache
        flat_cache_manager.set(cache_key, hash_result)

        if return_response:
            return ApiResponse.success_response(
                data=hash_result,
                metadata={'cache_source': 'computed', 'cache_stored': True}
            )
        return hash_result

    except Exception as e:
        if return_response:
            return ApiResponse.from_exception(e)
        raise


def compute_phash(
    image_path: str,
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    return_response: bool = False
) -> Union[Optional[str], ApiResponse]:
    """
    Compute perceptual hash (pHash) for an image using Discrete Cosine Transform (DCT).

    Loads the image with Pillow, computes the hash using imagehash.phash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching via FlatCacheManager
    (file-stat validated). Can return either the hash string directly (backward compatibility)
    or an ApiResponse object.

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Must be >=4 and <=64.
        settings (Optional[Dict]): Optional settings dictionary. Used to override hash_size.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'phash' field before computing and stores result.
        return_response (bool): If True, returns ApiResponse object instead of hash string.

    Returns:
        Union[Optional[str], ApiResponse]: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890'),
            None for non-image files, or ApiResponse object if return_response=True.

    Raises:
        InvalidImageError: If the image file does not exist, is not a valid image, or has an
            unsupported format (e.g., PIL.UnidentifiedImageError).
        SimilarityError: For general computation failures (e.g., invalid hash_size, memory issues).
        IOError: For file access errors (e.g., permissions).
        ValueError: If hash_size is invalid or resulting hash is not 16 characters.

    Example:
        >>> from pk_py_lib.core.flat_cache import FlatCacheManager
        >>> flat_cache = FlatCacheManager()
        >>> settings = {"criteria": {"phash": {"hash_size": 16}}}
        >>> # Traditional usage (backward compatible)
        >>> hash_val = compute_phash('/path/to/img.jpg', settings=settings, flat_cache_manager=flat_cache)
        >>> print(hash_val)
        'a1b2c3d4e5f67890'
        >>> # New ApiResponse usage
        >>> response = compute_phash('/path/to/img.jpg', return_response=True)
        >>> if response.success:
        ...     print(response.data)
        'a1b2c3d4e5f67890'

    Note:
        - Logs computation and cache hits via logger.debug.
        - Use return_response=True for new standardized error handling.
    """
    try:
        # Validate parameters using utility function
        effective_hash_size, algorithm, color_mode = validate_hash_parameters(hash_size, 'phash')

        # Get effective hash size from settings
        effective_hash_size = get_effective_hash_size(effective_hash_size, 'phash', settings)

        # Check if file is an image
        if not is_image_extension(image_path):
            if return_response:
                return ApiResponse.success_response(
                    data=None,
                    metadata={'algorithm': 'phash', 'hash_size': effective_hash_size, 'skipped': True}
                )
            return None

        # Check cache first
        cached_hash = check_cache_for_hash(image_path, 'phash', flat_cache_manager)
        if cached_hash is not None:
            if return_response:
                return ApiResponse.success_response(
                    data=cached_hash,
                    metadata={'algorithm': 'phash', 'hash_size': effective_hash_size, 'cached': True}
                )
            return cached_hash

        # --- Compute Hash ---
        # Load image with fallback utility
        image = load_image_with_fallback(image_path)

        # Convert BGR to RGB for PIL compatibility
        image_rgb = image[:, :, ::-1]  # BGR to RGB
        pil_img = Image.fromarray(image_rgb)

        # Compute hash using imagehash
        phash_obj = imagehash.phash(pil_img, hash_size=effective_hash_size)
        hash_str = str(phash_obj)

        # Normalize hash length
        hash_str = normalize_hash_length(hash_str)

        logger.debug(f"Computed pHash for {image_path} (size={effective_hash_size}): {hash_str}")

        # CRITICAL FIX: Store computed hash in cache if cache manager is provided
        if flat_cache_manager and hash_str is not None:
            try:
                # Get or create cache entry for this file
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    # Create new entry with file stats if it doesn't exist
                    try:
                        size, mtime = flat_cache_manager._get_file_stats(image_path)
                        current_entry = FlatCacheEntry(
                            path=image_path,
                            size=size,
                            mtime=mtime,
                            is_valid=True
                        )
                    except OSError:
                        # If we can't get file stats, still try to update with just the hash
                        current_entry = FlatCacheEntry(
                            path=image_path,
                            size=0,
                            mtime=0,
                            is_valid=True
                        )

                # Update the phash field
                current_entry.phash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Stored pHash in cache for {image_path}: {hash_str}")
            except Exception as e:
                logger.warning(f"Failed to store pHash in cache for {image_path}: {e}")

        if return_response:
            return ApiResponse.success_response(
                data=hash_str,
                metadata={'algorithm': 'phash', 'hash_size': effective_hash_size, 'computed': True}
            )

        return hash_str

    except Exception as e:
        # Enhanced error handling with context
        try:
            handle_image_loading_errors(
                image_path,
                e,
                operation="compute_phash",
                backend="PIL/OpenCV",
                additional_context={
                    "hash_size": effective_hash_size,
                    "algorithm": "phash",
                    "return_response": return_response
                }
            )
        except (InvalidImageError, IOError, DetailedSimilarityError):
            # Re-raise these enhanced errors
            if return_response:
                return ApiResponse.from_exception(e, ErrorCode.HASH_COMPUTATION_FAILED)
            raise
        except Exception as handling_error:
            # Fallback for any unexpected error in handling
            logger.error(f"Unexpected error in error handling for {image_path}: {handling_error}")
            if return_response:
                return ApiResponse.from_exception(
                    e,
                    ErrorCode.HASH_COMPUTATION_FAILED,
                    f"pHash computation failed for {image_path}: {e}"
                )
            raise SimilarityError(f"pHash computation failed: {e}") from e

        # This should not be reached due to the exception handling in the utility function
        if return_response:
            return ApiResponse.from_exception(
                e,
                ErrorCode.HASH_COMPUTATION_FAILED,
                f"pHash computation failed for {image_path}: {e}"
            )
        raise SimilarityError(f"pHash computation failed: {e}") from e


def compute_whash(
    image_path: str,
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    return_response: bool = False
) -> Union[Optional[str], ApiResponse]:
    """
    Compute wavelet hash (wHash) for an image using Discrete Wavelet Transform (DWT).

    Loads the image with Pillow, computes the hash using imagehash.whash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching via FlatCacheManager
    (file-stat validated). Can return either the hash string directly (backward compatibility)
    or an ApiResponse object.

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Must be >=4 and <=64.
        mode (str): DWT mode for edge handling (default 'constant').
        wavelet (str): Wavelet family name (default 'db1').
        settings (Optional[Dict]): Optional settings dictionary. Used to override hash_size.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'whash' field before computing and stores result.
        return_response (bool): If True, returns ApiResponse object instead of hash string.

    Returns:
        Union[Optional[str], ApiResponse]: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890'),
            None for non-image files, or ApiResponse object if return_response=True.

    Raises:
        InvalidImageError: If the image file does not exist, is not a valid image, or has an
            unsupported format (e.g., PIL.UnidentifiedImageError).
        SimilarityError: For general computation failures (e.g., invalid hash_size, wavelet errors, memory issues).
        IOError: For file access errors (e.g., permissions).
        ValueError: If hash_size is invalid or resulting hash is not 16 characters.

    Example:
        >>> from pk_py_lib.core.flat_cache import FlatCacheManager
        >>> flat_cache = FlatCacheManager()
        >>> settings = {"criteria": {"whash": {"hash_size": 16}}}
        >>> # Traditional usage (backward compatible)
        >>> hash_val = compute_whash('/path/to/img.jpg', settings=settings, flat_cache_manager=flat_cache)
        >>> print(hash_val)
        'a1b2c3d4e5f67890'
        >>> # New ApiResponse usage
        >>> response = compute_whash('/path/to/img.jpg', return_response=True)
        >>> if response.success:
        ...     print(response.data)
        'a1b2c3d4e5f67890'

    Note:
        - Logs computation and cache hits via logger.debug/info.
        - Use return_response=True for new standardized error handling.
    """
    try:
        # Validate parameters using utility function
        effective_hash_size, algorithm, color_mode = validate_hash_parameters(hash_size, 'whash')

        # Get effective hash size from settings
        effective_hash_size = get_effective_hash_size(effective_hash_size, 'whash', settings)

        # Check if file is an image
        if not is_image_extension(image_path):
            if return_response:
                return ApiResponse.success_response(
                    data=None,
                    metadata={'algorithm': 'whash', 'hash_size': effective_hash_size, 'skipped': True}
                )
            return None

        # Check cache first
        cached_hash = check_cache_for_hash(image_path, 'whash', flat_cache_manager)
        if cached_hash is not None:
            if return_response:
                return ApiResponse.success_response(
                    data=cached_hash,
                    metadata={'algorithm': 'whash', 'hash_size': effective_hash_size, 'cached': True}
                )
            return cached_hash

        # --- Compute Hash ---
        # Load image with fallback utility
        image = load_image_with_fallback(image_path)

        # Convert BGR to RGB for PIL compatibility
        image_rgb = image[:, :, ::-1]  # BGR to RGB
        pil_img = Image.fromarray(image_rgb)

        # Compute hash using imagehash
        try:
            whash_obj = imagehash.whash(pil_img, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
        except TypeError:
            # Fallback for older versions of imagehash that don't support wavelet parameter
            whash_obj = imagehash.whash(pil_img, hash_size=effective_hash_size, mode=mode)
        hash_str = str(whash_obj)

        # Normalize hash length
        hash_str = normalize_hash_length(hash_str)

        logger.info(f"Computed wHash for {image_path} (size={effective_hash_size}, mode={mode}, wavelet={wavelet}): {hash_str}")

        # CRITICAL FIX: Store computed hash in cache if cache manager is provided
        if flat_cache_manager and hash_str is not None:
            try:
                # Get or create cache entry for this file
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    # Create new entry with file stats if it doesn't exist
                    try:
                        size, mtime = flat_cache_manager._get_file_stats(image_path)
                        current_entry = FlatCacheEntry(
                            path=image_path,
                            size=size,
                            mtime=mtime,
                            is_valid=True
                        )
                    except OSError:
                        # If we can't get file stats, still try to update with just the hash
                        current_entry = FlatCacheEntry(
                            path=image_path,
                            size=0,
                            mtime=0,
                            is_valid=True
                        )

                # Update the whash field
                current_entry.whash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Stored wHash in cache for {image_path}: {hash_str}")
            except Exception as e:
                logger.warning(f"Failed to store wHash in cache for {image_path}: {e}")

        if return_response:
            return ApiResponse.success_response(
                data=hash_str,
                metadata={'algorithm': 'whash', 'hash_size': effective_hash_size, 'computed': True}
            )

        return hash_str

    except Exception as e:
        # Handle wavelet-specific errors with enhanced context
        error_details = str(e).lower()
        if "wavelet" in error_details or "dwt" in error_details or "pywt" in error_details:
            wavelet_context = ErrorContext(
                file_path=image_path,
                operation="compute_whash",
                original_exception=e,
                error_type="WaveletError",
                backend="PyWavelets",
                additional_context={
                    "wavelet": wavelet,
                    "mode": mode,
                    "hash_size": effective_hash_size,
                    "algorithm": "whash",
                    "return_response": return_response
                }
            )
            logger.debug(f"Wavelet error context: {wavelet_context.to_dict()}")

            if return_response:
                return ApiResponse.error_response(
                    ErrorCode.INVALID_HASH_ALGORITHM,
                    f"wHash computation failed due to invalid wavelet '{wavelet}' or mode '{mode}': {e}",
                    details={'wavelet': wavelet, 'mode': mode, 'error_context': wavelet_context.to_dict()}
                )
            raise SimilarityError(f"wHash computation failed due to invalid wavelet '{wavelet}' or mode '{mode}': {e}") from e

        # Enhanced error handling with context
        try:
            handle_image_loading_errors(
                image_path,
                e,
                operation="compute_whash",
                backend="PIL/OpenCV",
                additional_context={
                    "hash_size": effective_hash_size,
                    "algorithm": "whash",
                    "mode": mode,
                    "wavelet": wavelet,
                    "return_response": return_response
                }
            )
        except (InvalidImageError, IOError, DetailedSimilarityError):
            # Re-raise these enhanced errors
            if return_response:
                return ApiResponse.from_exception(e, ErrorCode.HASH_COMPUTATION_FAILED)
            raise
        except Exception as handling_error:
            # Fallback for any unexpected error in handling
            logger.error(f"Unexpected error in error handling for {image_path}: {handling_error}")
            if return_response:
                return ApiResponse.from_exception(
                    e,
                    ErrorCode.HASH_COMPUTATION_FAILED,
                    f"wHash computation failed for {image_path}: {e}"
                )
            raise SimilarityError(f"wHash computation failed: {e}") from e

        # This should not be reached due to the exception handling in the utility function
        if return_response:
            return ApiResponse.from_exception(
                e,
                ErrorCode.HASH_COMPUTATION_FAILED,
                f"wHash computation failed for {image_path}: {e}"
            )
        raise SimilarityError(f"wHash computation failed: {e}") from e


def compute_color_hash(
    image_path: str,
    algorithm: str = 'phash',
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute a color-aware hash by averaging hashes of RGB channels.

    This unified function replaces compute_color_phash and compute_color_whash,
    providing a generic interface for color hashing across algorithms.

    Args:
        image_path (str): Path to the image file.
        algorithm (str): Hash algorithm to use ('phash' or 'whash').
        hash_size (int): Size of the hash matrix (default 8).
        mode (str): DWT mode for whash (default 'constant').
        wavelet (str): Wavelet family for whash (default 'db1').
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance (not used for color hashes).

    Returns:
        Optional[str]: 16-character hexadecimal hash string, or None for non-image files.

    Raises:
        InvalidImageError: For invalid images.
        SimilarityError: For computation errors.
        ValueError: For invalid parameters.

    Example:
        >>> color_hash = compute_color_hash('/path/to/color_img.jpg', algorithm='phash')
        >>> print(color_hash)
        'fedcba9876543210'

    Note:
        - Logs via logger.info/debug.
        - Color hashes are not cached in the flat_cache schema.
    """
    # Validate parameters using utility function
    effective_hash_size, normalized_algorithm, color_mode = validate_hash_parameters(hash_size, algorithm, color_mode=True)

    # Get effective hash size from settings
    effective_hash_size = get_effective_hash_size(effective_hash_size, normalized_algorithm, settings)

    # Check if file is an image
    if not is_image_extension(image_path):
        return None

    # Note: Custom color hashes are not cached in the simplified flat_cache schema
    # They will be computed on demand each time

    # --- Compute Hash ---
    try:
        # Load image with fallback utility
        image = load_image_with_fallback(image_path)

        # Get the appropriate hash function
        if normalized_algorithm == 'phash':
            hash_function = lambda img, hash_size: imagehash.phash(img, hash_size=hash_size)
        elif normalized_algorithm == 'whash':
            hash_function = lambda img, hash_size: imagehash.whash(img, hash_size=hash_size, mode=mode, wavelet=wavelet)
        else:
            raise ValueError(f"Color hashing not supported for algorithm: {normalized_algorithm}")

        # Compute generic color hash
        hash_str = compute_generic_color_hash(image, effective_hash_size, hash_function)

        # Normalize hash length
        hash_str = normalize_hash_length(hash_str)

        logger.info(f"Computed color {normalized_algorithm} for {image_path} (size={effective_hash_size}): {hash_str}")
        return hash_str

    except Exception as e:
        # Enhanced error handling with context for color hashing
        try:
            handle_image_loading_errors(
                image_path,
                e,
                operation=f"compute_color_{normalized_algorithm}",
                backend="PIL/OpenCV",
                additional_context={
                    "hash_size": effective_hash_size,
                    "algorithm": normalized_algorithm,
                    "color_mode": True,
                    "mode": mode if normalized_algorithm == 'whash' else None,
                    "wavelet": wavelet if normalized_algorithm == 'whash' else None
                }
            )
        except (InvalidImageError, IOError, DetailedSimilarityError):
            # Re-raise these enhanced errors
            raise
        except Exception as handling_error:
            # Fallback for any unexpected error in handling
            logger.error(f"Unexpected error in color hash error handling for {image_path}: {handling_error}")
            raise SimilarityError(f"Color {normalized_algorithm} computation failed: {e}") from e

        # This should not be reached due to exception handling in the utility function
        raise SimilarityError(f"Color {normalized_algorithm} computation failed: {e}") from e


def compute_color_phash(
    image_path: str,
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute a color-aware perceptual hash by averaging pHashes of RGB channels.

    This function is deprecated. Use compute_color_hash(algorithm='phash') instead.

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance (not used for color hashes).

    Returns:
        Optional[str]: 16-character hexadecimal hash string, or None for non-image files.

    Raises:
        InvalidImageError: For invalid images.
        SimilarityError: For computation errors.
        ValueError: For invalid parameters.

    Example:
        >>> color_hash = compute_color_phash('/path/to/color_img.jpg')
        >>> print(color_hash)
        'fedcba9876543210'

    Note:
        - This function is deprecated. Use compute_color_hash(algorithm='phash') instead.
        - Logs via logger.info/debug.
    """
    logger.warning("compute_color_phash is deprecated. Use compute_color_hash(algorithm='phash') instead.")
    return compute_color_hash(image_path, algorithm='phash', hash_size=hash_size, settings=settings, flat_cache_manager=flat_cache_manager)


def compute_color_whash(
    image_path: str,
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute a color-aware wavelet hash by averaging wHashes of RGB channels.

    This function is deprecated. Use compute_color_hash(algorithm='whash') instead.

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance (not used for color hashes).

    Returns:
        Optional[str]: 16-character hexadecimal hash string, or None for non-image files.

    Raises:
        InvalidImageError: For invalid images.
        SimilarityError: For computation errors.
        ValueError: For invalid parameters.

    Example:
        >>> color_hash = compute_color_whash('/path/to/color_img.jpg', wavelet='haar')
        >>> print(color_hash)
        'fedcba9876543210'

    Note:
        - This function is deprecated. Use compute_color_hash(algorithm='whash') instead.
        - Logs via logger.info/debug.
        - Requires PyWavelets.
    """
    logger.warning("compute_color_whash is deprecated. Use compute_color_hash(algorithm='whash') instead.")
    return compute_color_hash(image_path, algorithm='whash', hash_size=hash_size, mode=mode, wavelet=wavelet, settings=settings, flat_cache_manager=flat_cache_manager)


def compute_phash_batch(
    paths: List[str],
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    algorithm: str = 'phash'
) -> Dict[str, Optional[str]]:
    """
    Batch compute pHashes for a list of image paths, with progress logging.

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. Cache is used/updated if provided.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        settings (Optional[Dict]): Settings for overrides.
        flat_cache_manager (Optional[FlatCacheManager]): FlatCache instance.
        algorithm (str): Algorithm name for logging (default 'phash').

    Returns:
        Dict[str, Optional[str]]: {path: hash_str or None if failed}.

    Raises:
        ValueError: If paths is empty or flat_cache_manager not provided.
        SimilarityError: If batch setup fails.

    Example:
        >>> paths = ['/img1.jpg', '/img2.jpg']
        >>> results = compute_phash_batch(paths)
        >>> print(results)
        {'/img1.jpg': 'a1b2c3d4e5f67890', '/img2.jpg': 'b2c3d4e5f6789012'}

    Note:
        - Logs progress via logger.info.
        - For large batches, consider future parallelization with ThreadPoolExecutor.
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    if not flat_cache_manager:
        raise ValueError("flat_cache_manager is required for batch computation")

    results: Dict[str, Optional[str]] = {}
    total = len(paths)
    error_details: Dict[str, Dict[str, Any]] = {}

    logger.info(f"Starting batch {algorithm} computation for {total} images (size={hash_size}) [cache-enabled]")

    # Step 1: Check cache first for existing hashes (keep current optimization)
    batch_results = flat_cache_manager.get_hashes(paths, [algorithm])

    # Step 2: Identify missing entries that need computation
    missing_paths = []
    for path in paths:
        hash_val = batch_results.get(path, {}).get(algorithm)
        if hash_val is not None:
            # Cache hit - use existing hash
            results[path] = hash_val
        else:
            # Cache miss - needs computation
            missing_paths.append(path)

    cache_hits = total - len(missing_paths)
    logger.info(f"Cache check complete: {cache_hits}/{total} hits, {len(missing_paths)} need computation")

    # Step 3: Fall back to individual computation for uncached images
    if missing_paths:
        logger.info(f"Computing {algorithm} for {len(missing_paths)} uncached images...")

        for path in missing_paths:
            try:
                # Use the enhanced compute_phash function with error handling
                hash_result = compute_phash(
                    path,
                    hash_size=hash_size,
                    settings=settings,
                    flat_cache_manager=flat_cache_manager,
                    return_response=False
                )

                if hash_result is not None:
                    # Successfully computed hash
                    results[path] = hash_result
                    logger.debug(f"Computed {algorithm} for {path}: {hash_result}")
                else:
                    # Hash computation returned None (likely non-image file)
                    results[path] = None
                    logger.debug(f"Skipped {algorithm} computation for {path} (non-image or unsupported format)")

            except Exception as e:
                # Handle computation errors with enhanced context
                results[path] = None
                error_context = {
                    "algorithm": algorithm,
                    "hash_size": hash_size,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                }

                # Try to extract more detailed error information
                if hasattr(e, 'file_path'):
                    error_context["file_path"] = e.file_path
                if hasattr(e, 'error_type'):
                    error_context["detailed_error_type"] = e.error_type

                error_details[path] = error_context

                # Enhanced error logging with context
                logger.warning(f"Failed to compute {algorithm} for {path}: {e}")
                logger.debug(f"Error context for {path}: {error_context}")

    # Step 4: Calculate and report final statistics
    success_count = sum(1 for v in results.values() if v is not None)
    failure_count = total - success_count
    computed_count = len(missing_paths) - failure_count

    # Enhanced logging with comprehensive statistics
    if failure_count > 0:
        logger.warning(
            f"Batch {algorithm} completed: {success_count}/{total} successful "
            f"({cache_hits} cache hits, {computed_count} computed, {failure_count} failed)"
        )

        # Log detailed error information at debug level
        if error_details:
            logger.debug(f"Batch {algorithm} error details: {error_details}")

            # Categorize errors for better understanding
            error_types = {}
            for path, details in error_details.items():
                error_type = details.get("error_type", "Unknown")
                error_types[error_type] = error_types.get(error_type, 0) + 1

            logger.debug(f"Batch {algorithm} error breakdown: {error_types}")
    else:
        logger.info(
            f"Batch {algorithm} complete: {success_count}/{total} successful "
            f"({cache_hits} cache hits, {computed_count} computed)"
        )

    return results


def compute_whash_batch(
    paths: List[str],
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity',
    algorithm: str = 'whash'
) -> Dict[str, Optional[str]]:
    """
    Batch compute wHashes for a list of image paths, with progress logging.

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. In duplicate mode, skips computation entirely.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Settings for overrides.
        flat_cache_manager (Optional[FlatCacheManager]): FlatCache instance.
        search_type (str): 'duplicate' to skip computation, return empty dict.
        algorithm (str): Algorithm name for logging (default 'whash').

    Returns:
        Dict[str, Optional[str]]: {path: hash_str or None if failed}.

    Raises:
        ValueError: If paths is empty or flat_cache_manager not provided.
        SimilarityError: If batch setup fails.

    Example:
        >>> paths = ['/img1.jpg', '/img2.jpg']
        >>> results = compute_whash_batch(paths, wavelet='haar')
        >>> print(results)
        {'/img1.jpg': 'a1b2c3d4e5f67890', '/img2.jpg': 'b2c3d4e5f6789012'}

    Note:
        - Logs progress via logger.info.
        - In 'duplicate' mode, skips perceptual hash computation to avoid image loading.
    """
    if search_type == 'duplicate':
        logger.warning(f"Skipping batch wHash computation in duplicate mode for {len(paths)} paths - no image loading")
        return {p: None for p in paths}

    if not paths:
        raise ValueError("paths list cannot be empty")

    if not flat_cache_manager:
        raise ValueError("flat_cache_manager is required for batch computation")

    results: Dict[str, Optional[str]] = {}
    total = len(paths)
    error_details: Dict[str, Dict[str, Any]] = {}

    logger.info(f"Starting batch {algorithm} computation for {total} images (size={hash_size}, mode={mode}, wavelet={wavelet}) [cache-enabled]")

    # Step 1: Check cache first for existing hashes (keep current optimization)
    batch_results = flat_cache_manager.get_hashes(paths, [algorithm], search_type=search_type)

    # Step 2: Identify missing entries that need computation
    missing_paths = []
    for path in paths:
        hash_val = batch_results.get(path, {}).get(algorithm)
        if hash_val is not None:
            # Cache hit - use existing hash
            results[path] = hash_val
        else:
            # Cache miss - needs computation
            missing_paths.append(path)

    cache_hits = total - len(missing_paths)
    logger.info(f"Cache check complete: {cache_hits}/{total} hits, {len(missing_paths)} need computation")

    # Step 3: Fall back to individual computation for uncached images
    if missing_paths:
        logger.info(f"Computing {algorithm} for {len(missing_paths)} uncached images...")

        for path in missing_paths:
            try:
                # Use the enhanced compute_whash function with error handling
                hash_result = compute_whash(
                    path,
                    hash_size=hash_size,
                    mode=mode,
                    wavelet=wavelet,
                    settings=settings,
                    flat_cache_manager=flat_cache_manager,
                    return_response=False
                )

                if hash_result is not None:
                    # Successfully computed hash
                    results[path] = hash_result
                    logger.debug(f"Computed {algorithm} for {path}: {hash_result}")
                else:
                    # Hash computation returned None (likely non-image file)
                    results[path] = None
                    logger.debug(f"Skipped {algorithm} computation for {path} (non-image or unsupported format)")

            except Exception as e:
                # Handle computation errors with enhanced context
                results[path] = None
                error_context = {
                    "algorithm": algorithm,
                    "hash_size": hash_size,
                    "mode": mode,
                    "wavelet": wavelet,
                    "search_type": search_type,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                }

                # Try to extract more detailed error information
                if hasattr(e, 'file_path'):
                    error_context["file_path"] = e.file_path
                if hasattr(e, 'error_type'):
                    error_context["detailed_error_type"] = e.error_type

                error_details[path] = error_context

                # Enhanced error logging with context
                logger.warning(f"Failed to compute {algorithm} for {path}: {e}")
                logger.debug(f"Error context for {path}: {error_context}")

    # Step 4: Calculate and report final statistics
    success_count = sum(1 for v in results.values() if v is not None)
    failure_count = total - success_count
    computed_count = len(missing_paths) - failure_count

    # Enhanced logging with comprehensive statistics
    if failure_count > 0:
        logger.warning(
            f"Batch {algorithm} completed: {success_count}/{total} successful "
            f"({cache_hits} cache hits, {computed_count} computed, {failure_count} failed)"
        )

        # Log detailed error information at debug level
        if error_details:
            logger.debug(f"Batch {algorithm} error details: {error_details}")

            # Categorize errors for better understanding
            error_types = {}
            for path, details in error_details.items():
                error_type = details.get("error_type", "Unknown")
                error_types[error_type] = error_types.get(error_type, 0) + 1

            logger.debug(f"Batch {algorithm} error breakdown: {error_types}")
    else:
        logger.info(
            f"Batch {algorithm} complete: {success_count}/{total} successful "
            f"({cache_hits} cache hits, {computed_count} computed)"
        )

    return results


def get_similarity_hash(
    image_path: str,
    algorithm: Optional[str] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute similarity hash (pHash or wHash) for an image based on the selected algorithm.

    Dynamically selects the algorithm from settings if not provided. Dispatches to
    the appropriate compute function. Supports caching via FlatCacheManager.

    Args:
        image_path (str): Path to the image file.
        algorithm (Optional[str]): 'phash' or 'whash'. If None, retrieves from
            settings['criteria']['similarity_hash_algorithm'] or defaults to 'phash'.
        settings (Optional[Dict]): Settings dictionary for overrides and algorithm selection.
        flat_cache_manager (Optional[FlatCacheManager]): Cache manager for storing/retrieving hashes.

    Returns:
        Optional[str]: Computed hash string or None for non-image files or errors.

    Raises:
        ValueError: For unsupported algorithm.
        SimilarityError: For computation failures.
        InvalidImageError: For invalid images.

    Example:
        >>> hash_val = get_similarity_hash('/path/to/img.jpg', settings=my_settings)
        >>> print(hash_val)
        'a1b2c3d4e5f67890'
    """
    # Resolve algorithm from settings if not provided
    if algorithm is None:
        if settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            algorithm = settings['criteria']['similarity_hash_algorithm']
        else:
            algorithm = 'phash'

    # Use algorithm utility to resolve and validate
    normalized_algorithm = resolve_hash_algorithm(algorithm)

    if algorithm == 'phash':
        return compute_phash(image_path, settings=settings, flat_cache_manager=flat_cache_manager)
    elif algorithm == 'whash':
        return compute_whash(image_path, settings=settings, flat_cache_manager=flat_cache_manager)
    else:
        raise ValueError(f"Unsupported similarity hash algorithm: {algorithm}. Supported: 'phash', 'whash'")


def compute_similarity_hash_batch(
    paths: List[str],
    algorithm: Optional[str] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity'
) -> Dict[str, Optional[str]]:
    """
    Batch compute similarity hashes (pHash or wHash) for a list of image paths.

    Dynamically selects the algorithm from settings if not provided. Dispatches to
    the appropriate batch compute function. Supports caching.

    Args:
        paths (List[str]): List of image paths.
        algorithm (Optional[str]): 'phash' or 'whash'. If None, retrieves from settings or defaults to 'phash'.
        settings (Optional[Dict]): Settings for overrides and algorithm selection.
        flat_cache_manager (Optional[FlatCacheManager]): Cache manager.
        search_type (str): 'similarity' or 'duplicate' (skips for 'duplicate' in wHash).

    Returns:
        Dict[str, Optional[str]]: {path: hash or None}.

    Raises:
        ValueError: For unsupported algorithm or empty paths.

    Example:
        >>> results = compute_similarity_hash_batch(['/img1.jpg', '/img2.jpg'], settings=my_settings)
        >>> print(results)
        {'/img1.jpg': 'a1b2c3d4e5f67890', '/img2.jpg': None}
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    # Resolve algorithm from settings if not provided
    if algorithm is None:
        if settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            algorithm = settings['criteria']['similarity_hash_algorithm']
        else:
            algorithm = 'phash'

    # Use algorithm utility to resolve and validate
    normalized_algorithm = resolve_hash_algorithm(algorithm)

    if normalized_algorithm == 'phash':
        return compute_phash_batch(paths, settings=settings, flat_cache_manager=flat_cache_manager, algorithm=normalized_algorithm)
    elif normalized_algorithm == 'whash':
        return compute_whash_batch(paths, settings=settings, flat_cache_manager=flat_cache_manager, search_type=search_type, algorithm=normalized_algorithm)
    else:
        supported_algorithms = list_supported_algorithms()
        raise ValueError(f"Unsupported similarity hash algorithm: {algorithm}. Supported: {', '.join(supported_algorithms.keys())}")


def _generate_cache_key(image_path: str, hash_type: str, hash_size: int) -> str:
    """
    Generate a cache key for hash computations.

    Args:
        image_path: Path to image file
        hash_type: Type of hash (phash, whash, etc.)
        hash_size: Hash size parameter

    Returns:
        Unique cache key string
    """
    import hashlib
    # Create a unique key based on path, hash type, and size
    key_data = f"{image_path}:{hash_type}:{hash_size}"
    return hashlib.md5(key_data.encode()).hexdigest()


def _compute_phash_internal(image_path: str, hash_size: int) -> str:
    """
    Internal pHash computation without caching.

    Args:
        image_path: Path to image file
        hash_size: Size of hash matrix

    Returns:
        Computed hash string
    """
    # Load image with fallback utility
    image = load_image_with_fallback(image_path)

    # Convert BGR to RGB for PIL compatibility
    image_rgb = image[:, :, ::-1]  # BGR to RGB
    pil_img = Image.fromarray(image_rgb)

    # Compute hash using imagehash
    phash_obj = imagehash.phash(pil_img, hash_size=hash_size)
    hash_str = str(phash_obj)

    # Normalize hash length
    hash_str = normalize_hash_length(hash_str)

    return hash_str
