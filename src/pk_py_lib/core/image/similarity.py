"""
src/pk_py_lib/core/image/similarity.py

Perceptual hash (pHash) implementation for image similarity detection in pk-py-lib.
Focuses on reusability: functions are standalone, configurable, with caching and error handling.
No database integration; caller provides hashes for grouping.
Uses imagehash for computation, Pillow for loading.

Note: Syntax validation performed per project rules using Python ast.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from PIL import Image
import imagehash
from ..filesystem.identity import compute_xxh3
from collections import defaultdict
from dataclasses import dataclass

@dataclass(frozen=True)
class ExactDuplicateSet:
    """
    Immutable representation of a set of exact duplicate files based on content hash equality.

    This dataclass groups files that are byte-for-byte identical, identified by matching XXH3 hashes.
    Used in the two-phase similarity detection process to deduplicate before perceptual hashing.
    The representative_path is selected as the lexicographically smallest path in the set for consistency.

    Args:
        id: Unique integer identifier for the exact duplicate set.
        paths: Sorted list of absolute file paths in the set.
        representative_path: The path used as representative for perceptual hashing (smallest path).

    Example:
        >>> exact_set = ExactDuplicateSet(
        ...     id=1,
        ...     paths=["/path/to/dup1.jpg", "/path/to/dup2.jpg"],
        ...     representative_path="/path/to/dup1.jpg"
        ... )
        >>> len(exact_set.paths)
        2
    """
    id: int
    paths: List[str]
    representative_path: str
from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheDBError
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
from pk_py_lib.core.image.quality.base import ImageQualityEvaluator
from pathlib import Path
from pathlib import Path

VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}

# LSH removed; always use brute-force


class InvalidImageError(Exception):
    """
    Raised when an image file is invalid or cannot be processed.

    Args:
        path (str): The path to the invalid image.
        details (str): Detailed description of the issue.

    Example:
        >>> raise InvalidImageError("/path/to/img.jpg", "Unsupported format")
    """
    def __init__(self, path: str, details: str):
        self.path = path
        self.details = details
        super().__init__(f"Invalid image at {path}: {details}")


class SimilarityError(Exception):
    """
    Base exception for similarity computation errors.

    Args:
        message (str): Error message with details.

    Example:
        >>> raise SimilarityError("Hash computation failed due to invalid parameters")
    """
    def __init__(self, message: str):
        super().__init__(message)


logger = get_logger(__name__)


def format_timestamp(ts: float) -> str:
    """
    Format Unix timestamp to human-readable date string.

    Args:
        ts (float): Unix timestamp (seconds since epoch).

    Returns:
        str: Formatted date as "dd-MMM-yy" (e.g., "15-Sep-25").

    Example:
        >>> print(format_timestamp(1726400000.0))
        15-Sep-25
    """
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d-%b-%y")
    except (ValueError, OSError):
        return "Unknown"


def is_image_extension(path: str) -> bool:
    """
    Check if the file has an image extension.

    Args:
        path (str): File path to check.

    Returns:
        bool: True if the extension is a known image format.
    """
    return Path(path).suffix.lower() in VALID_IMAGE_EXTENSIONS


def get_resolution(path: str, search_type: str = 'similarity') -> str:
    """
    Get image resolution (width x height) using PIL.

    Args:
        path (str): Path to the image file.
        search_type (str): 'duplicate' to skip image loading and return "Unknown".

    Returns:
        str: Resolution string (e.g., "1920x1080") or "Unknown" on failure or skip.

    Raises:
        InvalidImageError: If image cannot be loaded (non-duplicate mode).

    Example:
        >>> res = get_resolution("/path/to/img.jpg")
        >>> print(res)
        1920x1080
    """
    # Fixed duplicate mode skips
    if search_type == 'duplicate':
        return "Unknown"
    # Skip for non-images
    if not is_image_extension(path):
        return "Unknown"
    try:
        with Image.open(path) as img:
            w, h = img.size
            return f"{w}x{h}"
    except Exception as e:
        logger.warning(f"Failed to get resolution for {path}: {e}")
        return "Unknown"


def get_image_metadata(path: str, search_type: str = 'similarity') -> Dict[str, any]:
    """
    Fetch basic metadata for an image: size, resolution, modification date.

    Args:
        path (str): Path to the image file.
        search_type (str): 'duplicate' to skip image loading, return "Unknown" for resolution.

    Returns:
        Dict[str, any]: {'size': int, 'resolution': str, 'mod_date': str}

    Raises:
        IOError: For file access errors.
        InvalidImageError: For image loading issues.

    Example:
        >>> meta = get_image_metadata("/path/to/img.jpg")
        >>> print(meta['size'])
        524288
    """
    # Fixed duplicate mode skips
    try:
        stat = os.stat(path)
        size = stat.st_size
        mod_ts = stat.st_mtime
        mod_date = format_timestamp(mod_ts)

        # Skip image operations for non-images regardless of search_type
        if not is_image_extension(path):
            return {'size': size, 'resolution': 'Unknown', 'mod_date': mod_date}

        if search_type == 'duplicate':
            return {'size': size, 'resolution': "Unknown", 'mod_date': mod_date}
        resolution = get_resolution(path, search_type)
        return {'size': size, 'resolution': resolution, 'mod_date': mod_date}
    except IOError as e:
        raise IOError(f"Failed to access file {path}: {e}")
    except Exception as e:
        raise InvalidImageError(path, f"Metadata extraction failed: {e}")

def get_image_quality_score(
    path: str,
    evaluator: Optional[ImageQualityEvaluator],
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity'
) -> tuple[Optional[float], Optional[str]]:
    """
    Compute the image quality score using the provided evaluator, preferring cached value if available.

    If the evaluator is None (quality evaluation disabled), returns (None, None).
    If flat_cache_manager is provided, checks for cached brisque score first.
    If evaluation fails, logs an error and returns (None, evaluator.name).

    Args:
        path (str): Path to the image file.
        evaluator (Optional[ImageQualityEvaluator]): Instantiated quality evaluator or None.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to check for cached score and store new computation.
        search_type (str): 'duplicate' to skip computation, return (None, None); else pass to evaluator.

    Returns:
        tuple[Optional[float], Optional[str]]: (quality_score, algorithm_name)
            quality_score is normalized (higher is better).
            algorithm_name is the evaluator's name (e.g., 'brisque').

    Example:
        >>> evaluator = get_active_image_quality_evaluator()
        >>> flat_cache = FlatCacheManager()
        >>> score, name = get_image_quality_score("/path/to/img.jpg", evaluator, flat_cache)
        >>> print(f"Score: {score}, Algorithm: {name}")
        Score: 75.5, Algorithm: brisque
    """
    # Fixed duplicate mode skips
    if search_type == 'duplicate':
        return None, None
    if evaluator is None:
        return None, None

    if not is_image_extension(path):
        return None, None

    # Prefer cached value if available
    if flat_cache_manager:
        try:
            entry = flat_cache_manager.get_entry(path)
            if entry and entry.brisque is not None:
                logger.debug(f"Cached brisque score found for {path}: {entry.brisque}")
                return entry.brisque, evaluator.name
        except Exception as e:
            logger.warning(f"Failed to retrieve cached brisque for {path}: {e}")

    try:
        score = evaluator.evaluate(path, flat_cache_manager=flat_cache_manager)
        # Store in cache if manager provided and computation succeeded
        if flat_cache_manager and score is not None:
            try:
                entry = flat_cache_manager.get_entry(path)
                if entry:
                    entry.brisque = score
                    flat_cache_manager.set_entry(entry)
            except Exception as cache_e:
                logger.warning(f"Failed to cache brisque score for {path}: {cache_e}")
        return score, evaluator.name
    except Exception as e:
        logger.error(f"Image quality evaluation failed for {path} using {evaluator.name}: {e}", exception=e)
        # Return None score but keep the algorithm name for reporting the failure context
        return None, evaluator.name



def compute_group_stats(images: List[FileItem]) -> GroupStats:
    """
    Compute aggregate statistics for a group of files.

    Args:
        images (List[FileItem]): List of FileItem objects.

    Returns:
        GroupStats: Aggregated min/max/avg score and total size.

    Example:
        >>> from pk_py_lib.gui.dialog_models import FileItem
        >>> item1 = FileItem(path='a', size=100, resolution='1', mod_date='1', score=0.8)
        >>> item2 = FileItem(path='b', size=200, resolution='1', mod_date='1', score=1.0)
        >>> stats = compute_group_stats([item1, item2])
        >>> print(stats.avg_score)
        0.9
    """
    if not images:
        # Return a default GroupStats object with zero/default values
        return GroupStats(total_size=0, savings=0, min_score=0.0, max_score=0.0, avg_score=0.0, file_count=0)

    scores = [img.score for img in images if img.score is not None]
    sizes = [img.size for img in images]

    if not scores:
        # Handle case where scores are None for all items (e.g., exact duplicates)
        min_score = 1.0
        max_score = 1.0
        avg_score = 1.0
    else:
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

    total_size = sum(sizes)
    min_size = min(sizes) if sizes else 0
    savings = total_size - min_size

    return GroupStats(
        total_size=total_size,
        savings=savings,
        min_score=min_score,
        max_score=max_score,
        avg_score=avg_score,
        file_count=len(images)
    )


def compute_phash(
    image_path: str,
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute perceptual hash (pHash) for an image using Discrete Cosine Transform (DCT).

    Loads the image with Pillow, computes the hash using imagehash.phash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching via FlatCacheManager
    (file-stat validated).

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Must be >=4 and <=64.
        settings (Optional[Dict]): Optional settings dictionary. Used to override hash_size.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'phash' field before computing and stores result.

    Returns:
        Optional[str]: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890'), or None for non-image files.

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
        >>> hash_val = compute_phash('/path/to/img.jpg', settings=settings, flat_cache_manager=flat_cache)
        >>> print(hash_val)
        'a1b2c3d4e5f67890'

    Note:
        - Flat cache takes precedence if both cache managers are provided.
        - Logs computation and cache hits via logger.debug.
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")

    # Override hash_size from settings if provided
    effective_hash_size = hash_size
    if settings and "criteria" in settings and "phash" in settings["criteria"]:
        effective_hash_size = settings["criteria"]["phash"].get("hash_size", hash_size)

    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")

    if not is_image_extension(image_path):
        return None

    # Use flat_cache.get_hashes for integrated caching and computation
    if flat_cache_manager:
        try:
            hashes = flat_cache_manager.get_hashes([image_path], ['phash'])
            cached_hash = hashes.get(image_path, {}).get('phash')
            if cached_hash is not None:
                logger.debug(f"Flat cache hit for pHash on {image_path}")
                return cached_hash
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during pHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache pHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- Compute Hash ---
    hash_str = None
    try:
        # Try PIL first for better compatibility with various formats
        try:
            with Image.open(path) as img:
                # Handle GIF animations by taking first frame
                if hasattr(img, 'is_animated') and img.is_animated:
                    img.seek(0)  # Ensure we're on the first frame

                # Convert to RGB if necessary for consistent hashing
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                phash_obj = imagehash.phash(img, hash_size=effective_hash_size)
                hash_str = str(phash_obj)
        except Exception as pil_exc:
            logger.warning(f"PIL loading failed for {path}: {pil_exc}, trying fallback")
            # Fallback to OpenCV if PIL fails
            import cv2
            import numpy as np
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV")

            # Convert BGR to RGB for PIL compatibility
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(image_rgb)
            phash_obj = imagehash.phash(pil_img, hash_size=effective_hash_size)
            hash_str = str(phash_obj)

        # Validate hash length and normalize if needed
        if len(hash_str) < 8:
            raise SimilarityError(f"Computed hash too short: {len(hash_str)} characters")
        elif len(hash_str) > 32:
            raise SimilarityError(f"Computed hash too long: {len(hash_str)} characters")
        elif len(hash_str) != 16:
            logger.warning(f"Computed hash length {len(hash_str)}, expected 16, normalizing")
            if len(hash_str) < 16:
                hash_str = hash_str.zfill(16)
            else:
                hash_str = hash_str[:16]

        # --- Update cache if available ---
        if flat_cache_manager:
            try:
                hashes = flat_cache_manager.get_hashes([image_path], ['phash'])
                # Since get_hashes would have computed if missing, but if we reached here, update directly if needed
                # But since get_hashes already handles, this is fallback
                pass  # get_hashes already updated
            except Exception as e:
                logger.warning(f"Failed to update flat cache for pHash on {image_path}: {e}")

        logger.debug(f"Computed pHash for {image_path} (size={effective_hash_size}): {hash_str}")
        return hash_str

    except IOError as e:
        logger.error(f"IO error loading image {image_path}: {e}", exception=e)
        raise
    except Exception as e:
        details = str(e).lower()
        if "cannot identify" in details or "unidentified image" in details:
            raise InvalidImageError(image_path, "Unsupported or corrupted image format")
        logger.error(f"pHash computation failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"pHash computation failed: {e}") from e


def compute_color_phash(
    image_path: str,
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute a color-aware perceptual hash by averaging pHashes of RGB channels.
    Note: Custom hash not directly supported by flat_cache.get_hashes; compute directly.

    Splits the image into R, G, B channels, computes pHash for each, converts to integers,
    averages them, and returns a 64-bit hex string. Supports caching via FlatCacheManager
    (file-stat validated). Cache key: f"{image_path}:color_phash".

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'color_phash' field before computing and stores result.

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
        - Flat cache takes precedence if both cache managers are provided.
        - Logs via logger.info/debug.
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")

    effective_hash_size = hash_size
    if settings and "criteria" in settings and "phash" in settings["criteria"]:
        effective_hash_size = settings["criteria"]["phash"].get("hash_size", hash_size)

    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")

    if not is_image_extension(image_path):
        return None

    # Note: Custom color_phash is not cached in the simplified flat_cache schema
    # It will be computed on demand each time

    # --- Compute Hash ---
    hash_str = None
    try:
        # Try PIL first for better compatibility with various formats
        try:
            with Image.open(path) as img:
                # Handle GIF animations by taking first frame
                if hasattr(img, 'is_animated') and img.is_animated:
                    img.seek(0)  # Ensure we're on the first frame

                if img.mode != 'RGB':
                    img = img.convert('RGB')
                r, g, b = img.split()

                h_r = imagehash.phash(r, hash_size=effective_hash_size)
                h_g = imagehash.phash(g, hash_size=effective_hash_size)
                h_b = imagehash.phash(b, hash_size=effective_hash_size)

                # Average the integer representations
                int_r = int(str(h_r), 16)
                int_g = int(str(h_g), 16)
                int_b = int(str(h_b), 16)
                avg_int = (int_r + int_g + int_b) // 3

                # Format as 64-bit hex (16 chars), truncate/pad if needed
                hash_str = f"{avg_int:064x}"[:16].zfill(16)
        except Exception as pil_exc:
            logger.warning(f"PIL loading failed for {path}: {pil_exc}, trying OpenCV fallback")
            # Fallback to OpenCV if PIL fails
            import cv2
            import numpy as np
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV")

            # Convert BGR to RGB for PIL compatibility
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(image_rgb)
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            r, g, b = pil_img.split()

            h_r = imagehash.phash(r, hash_size=effective_hash_size)
            h_g = imagehash.phash(g, hash_size=effective_hash_size)
            h_b = imagehash.phash(b, hash_size=effective_hash_size)

            # Average the integer representations
            int_r = int(str(h_r), 16)
            int_g = int(str(h_g), 16)
            int_b = int(str(h_b), 16)
            avg_int = (int_r + int_g + int_b) // 3

            # Format as 64-bit hex (16 chars), truncate/pad if needed
            hash_str = f"{avg_int:064x}"[:16].zfill(16)

        # Validate hash length and normalize if needed
        if len(hash_str) < 8:
            raise SimilarityError(f"Color hash too short: {len(hash_str)} characters")
        elif len(hash_str) > 32:
            raise SimilarityError(f"Color hash too long: {len(hash_str)} characters")
        elif len(hash_str) != 16:
            logger.warning(f"Color hash length {len(hash_str)}, expected 16, normalizing")
            if len(hash_str) < 16:
                hash_str = hash_str.zfill(16)
            else:
                hash_str = hash_str[:16]

        logger.info(f"Computed color pHash for {image_path} (size={effective_hash_size}): {hash_str}")
        return hash_str

    except Exception as e:
        logger.error(f"Color pHash failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"Color pHash computation failed: {e}") from e


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Compute the Hamming distance (bit differences) between two 64-bit hex hashes.

    Converts hex to integers, XORs them, and counts the '1' bits in the binary result.
    Used to measure perceptual similarity (lower distance = more similar).

    Args:
        hash1 (str): First 16-character hex hash.
        hash2 (str): Second 16-character hex hash.

    Returns:
        int: Hamming distance (0 for identical, up to 64 for completely different).

    Raises:
        ValueError: If either hash is not a valid 16-character hex string.

    Example:
        >>> dist = hamming_distance('a1b2c3d4e5f67890', 'a1b2c3d4e5f67891')
        >>> print(dist)  # 1 (very similar)
        1
    """
    if len(hash1) != 16 or not all(c in '0123456789abcdefABCDEF' for c in hash1):
        raise ValueError(f"Invalid hex hash1: {hash1}")
    if len(hash2) != 16 or not all(c in '0123456789abcdefABCDEF' for c in hash2):
        raise ValueError(f"Invalid hex hash2: {hash2}")

    try:
        i1 = int(hash1, 16)
        i2 = int(hash2, 16)
        xor_result = i1 ^ i2
        distance = bin(xor_result).count('1')
        logger.debug(f"Hamming distance between {hash1[:8]}... and {hash2[:8]}...: {distance}")
        return distance
    except ValueError as e:
        raise ValueError("Hex conversion failed") from e


def find_similar_phash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity',
    algorithm: str = 'phash'
) -> List[Group]:
    # Fixed duplicate mode skips
    """
    Find groups of visually similar images using pHash Hamming distances.

    Performs clustering: For n <= 1000 or if LSH unavailable, uses brute-force pairwise distances and union-find
    to group images where any chain of distances <= threshold (transitive similarity).
    For n > 1000 and datasketch available, uses MinHashLSH for candidate retrieval (approximating bit sets as MinHash signatures)
    + exact Hamming verification on candidates, then union-find.
    Input dicts should have 'path' (str) and 'hash' (str) keys. Outputs groups of 2+ paths.
    Threshold defaults to settings['similarity']['phash_threshold'] or 10.
    LSH uses num_perm=128, threshold=1 - (hamming_threshold / 64.0) for Jaccard approximation.

    Args:
        hashes (List[Dict[str, str]]): List of image records, e.g.,
            [{'path': '/img1.jpg', 'hash': 'a1b2c3d4e5f67890'}, ...].
            Typically from DB query (image_hashes table joined with images).
        threshold (Optional[int]): Maximum Hamming distance for similarity (0-64).
            Lower values = stricter matching (e.g., 5 for near-identical).
        settings (Optional[Dict]): Settings dict to override threshold via
            settings['similarity']['phash_threshold'] (default 10).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.
        search_type (str): 'similarity' to ensure full computations.

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - images (List[FileItem]): FileItem objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (GroupStats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].images[0].score → 0.95 (95% similarity)

    Raises:
        ValueError: If hashes list is empty, invalid dict structure, or invalid hashes.
        SimilarityError: If grouping fails (e.g., fallback errors).

    Example:
        >>> sample_hashes = [
        ...     {'path': '/img1.jpg', 'hash': '0000000000000000'},
        ...     {'path': '/img2.jpg', 'hash': '0000000000000001'},
        ...     {'path': '/img3.jpg', 'hash': '1111111111111111'}
        ... ]
        >>> groups = find_similar_phash(sample_hashes, threshold=1)
        >>> print(groups)  # [['/img1.jpg', '/img2.jpg']]
        [['/img1.jpg', '/img2.jpg']]

        # For large n (e.g., 2000 images), LSH reduces candidates from O(n^2) to ~O(n * k), where k << n
        >>> large_hashes = [{'path': f'/img{i}.jpg', 'hash': 'a' * 16} for i in range(2000)]  # Simulate
        >>> groups_large = find_similar_phash(large_hashes, threshold=5)
        >>> print(f"Groups: {len(groups_large)}")

    Note:
        - Brute-force O(n^2) for all sizes; for large n (>1000), consider external indexing in future.
        - Logs warning for large inputs.
        - Threshold tuning: Test empirically (0=exact, 10~similar, 20~loose).
    """
    if not hashes:
        raise ValueError("hashes list cannot be empty")

    n = len(hashes)

    # Retrieve the active quality evaluator once for the entire batch
    quality_evaluator = get_active_image_quality_evaluator()

    # Validate input
    for i, h in enumerate(hashes):
        if not isinstance(h, dict) or 'path' not in h or 'hash' not in h:
            raise ValueError(f"Invalid dict at index {i}: missing 'path' or 'hash'")
        if not isinstance(h['path'], str) or not h['path']:
            raise ValueError(f"Empty path at index {i}")

        # Validate and normalize hash length
        hash_str = h['hash']
        if not isinstance(hash_str, str) or not hash_str:
            raise ValueError(f"Empty or invalid hash at index {i}")

        # Handle variable hash lengths gracefully
        if len(hash_str) == 16:
            # Standard 64-bit hash
            pass
        elif len(hash_str) == 21:
            # Handle 21-character hashes - extract only hex digits from the end
            logger.warning(f"Hash length 21 at index {i}, extracting hex digits for compatibility")
            # Extract only the hex digits from the hash string
            hex_digits = ''.join(c for c in hash_str if c in '0123456789abcdefABCDEF')
            if len(hex_digits) >= 16:
                hash_str = hex_digits[:16]
            else:
                # Pad if we don't have enough hex digits
                hash_str = hex_digits.zfill(16)
            h['hash'] = hash_str
        elif len(hash_str) < 8:
            raise ValueError(f"Hash too short at index {i}: {len(hash_str)} (minimum 8 characters)")
        elif len(hash_str) > 32:
            raise ValueError(f"Hash too long at index {i}: {len(hash_str)} (maximum 32 characters)")
        else:
            # For lengths between 8-32, pad or truncate to 16 characters
            if len(hash_str) < 16:
                logger.warning(f"Hash length {len(hash_str)} at index {i}, padding to 16 characters")
                hash_str = hash_str.zfill(16)
            else:
                logger.warning(f"Hash length {len(hash_str)} at index {i}, truncating to 16 characters")
                hash_str = hash_str[:16]
            h['hash'] = hash_str

        # Validate hex characters
        if not all(c in '0123456789abcdefABCDEF' for c in hash_str):
            raise ValueError(f"Invalid hex characters in hash at index {i}: {hash_str}")

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('phash_threshold', 10)
        else:
            threshold = 10
    if threshold < 0 or threshold > 64:
        raise ValueError(f"Threshold must be 0-64, got {threshold}")

    # Path to index mapping for LSH
    path_to_index = {h['path']: i for i, h in enumerate(hashes)}

    # Union-find for clustering
    parent = list(range(n))

    def find(p: int) -> int:
        if parent[p] != p:
            parent[p] = find(parent[p])
        return parent[p]

    def union(p1: int, p2: int) -> None:
        pp1 = find(p1)
        pp2 = find(p2)
        if pp1 != pp2:
            parent[pp1] = pp2

    if n > 1000:
        logger.warning(f"Large input ({n} images) for brute-force grouping; consider external indexing for scale in production")

    # Always use brute-force pairwise comparison
    # Compute pairwise distances (brute-force)
    for i in range(n):
        for j in range(i + 1, n):
            try:
                dist = hamming_distance(hashes[i]['hash'], hashes[j]['hash'])
                if dist <= threshold:
                    union(i, j)
            except ValueError as e:
                logger.warning(f"Skipping invalid pair ({i}, {j}): {e}")
                continue

    # Build groups using indices to preserve hashes
    from collections import defaultdict
    group_dict: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        root = find(i)
        group_dict[root].append(i)

    groups: List[Group] = []
    group_id = 1
    for root, indices in group_dict.items():
        if len(indices) < 2:
            continue
        group_hashes = [hashes[i] for i in indices]
        group_hashes.sort(key=lambda d: d['path'])
        ref_hash_dict = group_hashes[0]
        ref_path = ref_hash_dict['path']
        ref_hash = ref_hash_dict['hash']
        images: List[FileItem] = []
        valid_count = 0
        for h_dict in group_hashes:
            try:
                dist = hamming_distance(ref_hash, h_dict['hash'])
                score = 1.0 - (dist / 64.0)
                # Fixed duplicate mode skips
                meta = get_image_metadata(h_dict['path'], search_type=search_type)
                quality_score, quality_algorithm = get_image_quality_score(h_dict['path'], quality_evaluator, flat_cache_manager, search_type=search_type)

                file_item = FileItem(
                    path=h_dict['path'],
                    size=meta['size'],
                    resolution=meta['resolution'],
                    mod_date=meta['mod_date'],
                    score=score,
                    file_type="",
                    savings=0,
                    quality_score=quality_score,
                    quality_algorithm=quality_algorithm,
                )
                images.append(file_item)
                valid_count += 1
            except Exception as e:
                logger.warning(f"Failed to create FileItem for {h_dict['path']}: {e}")
                continue
        if valid_count < 2:
            continue
        stats = compute_group_stats(images)
        group_obj = Group(
            id=group_id,
            items=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group_obj)
        group_id += 1

    logger.info(f"Found {len(groups)} similar {algorithm} groups (threshold={threshold}, n={n}, search_type={search_type})")
    return groups


def compute_phash_batch(
    paths: List[str],
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    algorithm: str = 'phash'
) -> Dict[str, Optional[str]]:
    """
    Batch compute pHashes for a list of image paths, with progress logging.
    Uses flat_cache.get_hashes for efficiency.

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. Cache is used/updated if provided and update_cache=True.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        settings (Optional[Dict]): Settings for overrides.
        cache_manager (Optional[CacheManager]): Legacy Cache instance.
        flat_cache_manager (Optional[FlatCacheManager]): FlatCache instance.
        update_cache (bool): If True, update cache on misses (applies to legacy cache only; flat cache handles its own updates internally).

    Returns:
        Dict[str, Optional[str]]: {path: hash_str or None if failed}.

    Raises:
        ValueError: If paths is empty.
        SimilarityError: If batch setup fails.

    Example:
        >>> paths = ['/img1.jpg', '/img2.jpg']
        >>> results = compute_phash_batch(paths)
        >>> print(results)
        {'/img1.jpg': 'a1b2c3d4e5f67890', '/img2.jpg': 'b2c3d4e5f6789012'}

    Note:
        - Logs progress via logger.info (e.g., "Batch progress: 1/10 - /path/to/img.jpg").
        - For large batches, consider future parallelization with ThreadPoolExecutor.
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    if not flat_cache_manager:
        raise ValueError("flat_cache_manager is required for batch computation")

    results: Dict[str, Optional[str]] = {}
    total = len(paths)

    logger.info(f"Starting batch {algorithm} computation for {total} images (size={hash_size}) [cache-enabled]")

    # Use get_hashes for batch efficiency
    batch_results = flat_cache_manager.get_hashes(paths, [algorithm])

    for path in paths:
        hash_val = batch_results.get(path, {}).get(algorithm)
        results[path] = hash_val
        if hash_val is None:
            logger.warning(f"Failed to compute {algorithm} for {path}")

    success_count = sum(1 for v in results.values() if v is not None)

    # Calculate cache hit information
    if flat_cache_manager:
        counters = flat_cache_manager.get_counters()
        cache_hits = len([p for p in paths if p in batch_results and batch_results[p].get(algorithm) is not None])
        cache_info = f" (cache hits: {cache_hits})"
    else:
        cache_info = ""

    logger.info(f"Batch complete: {success_count}/{total} successful{cache_info}")

    return results


def compute_whash(
    image_path: str,
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Optional[str]:
    """
    Compute wavelet hash (wHash) for an image using Discrete Wavelet Transform (DWT).
    Uses flat_cache.get_hashes for integrated caching.

    Loads the image with Pillow, computes the hash using imagehash.whash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching via CacheManager (legacy)
    or FlatCacheManager (new, file-stat validated).

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Must be >=4 and <=64.
        mode (str): DWT mode for edge handling (default 'constant').
        wavelet (str): Wavelet family name (default 'db1').
        settings (Optional[Dict]): Optional settings dictionary. Used to override hash_size.
        cache_manager (Optional[CacheManager]): Optional legacy CacheManager instance.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'whash' field before computing and stores result.

    Returns:
        Optional[str]: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890'), or None for non-image files.

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
        >>> hash_val = compute_whash('/path/to/img.jpg', settings=settings, flat_cache_manager=flat_cache)
        >>> print(hash_val)
        'a1b2c3d4e5f67890'

    Note:
        - Flat cache takes precedence if both cache managers are provided.
        - Logs computation and cache hits via logger.debug/info.
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")

    # Override hash_size from settings if provided
    effective_hash_size = hash_size
    if settings and "criteria" in settings and "whash" in settings["criteria"]:
        effective_hash_size = settings["criteria"]["whash"].get("hash_size", hash_size)

    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")

    if not is_image_extension(image_path):
        return None

    # Use flat_cache.get_hashes for integrated caching and computation
    if flat_cache_manager:
        try:
            hashes = flat_cache_manager.get_hashes([image_path], ['whash'])
            cached_hash = hashes.get(image_path, {}).get('whash')
            if cached_hash is not None:
                logger.debug(f"Flat cache hit for wHash on {image_path}")
                return cached_hash
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during wHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache wHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- Compute Hash ---
    hash_str = None
    try:
        # Try PIL first for better compatibility with various formats
        try:
            with Image.open(path) as img:
                # Handle GIF animations by taking first frame
                if hasattr(img, 'is_animated') and img.is_animated:
                    img.seek(0)  # Ensure we're on the first frame

                # Convert to RGB if necessary for consistent hashing
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                # imagehash.whash handles grayscale, resizing, DWT, thresholding
                whash_obj = imagehash.whash(img, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
                hash_str = str(whash_obj)
        except Exception as pil_exc:
            logger.warning(f"PIL loading failed for {path}: {pil_exc}, trying OpenCV fallback")
            # Fallback to OpenCV if PIL fails
            import cv2
            import numpy as np
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV")

            # Convert BGR to RGB for PIL compatibility
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(image_rgb)
            whash_obj = imagehash.whash(pil_img, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
            hash_str = str(whash_obj)

        # Validate hash length and normalize if needed
        if len(hash_str) < 8:
            raise SimilarityError(f"Computed hash too short: {len(hash_str)} characters")
        elif len(hash_str) > 32:
            raise SimilarityError(f"Computed hash too long: {len(hash_str)} characters")
        elif len(hash_str) != 16:
            logger.warning(f"Computed hash length {len(hash_str)}, expected 16, normalizing")
            if len(hash_str) < 16:
                hash_str = hash_str.zfill(16)
            else:
                hash_str = hash_str[:16]

        # --- Update cache if available ---
        if flat_cache_manager:
            try:
                flat_cache_manager.get_hashes([image_path], ['whash'])  # Triggers update
            except Exception as e:
                logger.warning(f"Failed to update flat cache for wHash on {image_path}: {e}")

        logger.info(f"Computed wHash for {image_path} (size={effective_hash_size}, mode={mode}, wavelet={wavelet}): {hash_str}")
        return hash_str

    except IOError as e:
        logger.error(f"IO error loading image {image_path}: {e}", exception=e)
        raise
    except Exception as e:
        details = str(e).lower()
        if "cannot identify" in details or "unidentified image" in details:
            raise InvalidImageError(image_path, "Unsupported or corrupted image format")
        if "wavelet" in details or "dwt" in details or "pywt" in details:
            raise SimilarityError(f"wHash computation failed due to invalid wavelet '{wavelet}' or mode '{mode}': {e}")
        logger.error(f"wHash computation failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"wHash computation failed: {e}") from e


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
    Note: Custom hash; compute directly and update cache if possible.

    Splits the image into R, G, B channels, computes wHash for each, converts to integers,
    averages them, and returns a 64-bit hex string. Supports caching via CacheManager (legacy)
    or FlatCacheManager (new, file-stat validated). Cache key: f"{image_path}:color_whash".

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        cache_manager (Optional[CacheManager]): Optional legacy cache manager.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'color_whash' field before computing and stores result.

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
        - Flat cache takes precedence if both cache managers are provided.
        - Logs via logger.info/debug.
        - Requires PyWavelets.
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")

    effective_hash_size = hash_size
    if settings and "criteria" in settings and "whash" in settings["criteria"]:
        effective_hash_size = settings["criteria"]["whash"].get("hash_size", hash_size)

    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")

    if not is_image_extension(image_path):
        return None

    # Note: Custom color_whash is not cached in the simplified flat_cache schema
    # It will be computed on demand each time

    # --- Compute Hash ---
    hash_str = None
    try:
        # Try PIL first for better compatibility with various formats
        try:
            with Image.open(path) as img:
                # Handle GIF animations by taking first frame
                if hasattr(img, 'is_animated') and img.is_animated:
                    img.seek(0)  # Ensure we're on the first frame

                if img.mode != 'RGB':
                    img = img.convert('RGB')
                r, g, b = img.split()

                h_r = imagehash.whash(r, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
                h_g = imagehash.whash(g, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
                h_b = imagehash.whash(b, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)

                # Average the integer representations
                int_r = int(str(h_r), 16)
                int_g = int(str(h_g), 16)
                int_b = int(str(h_b), 16)
                avg_int = (int_r + int_g + int_b) // 3

                # Format as 64-bit hex (16 chars), truncate/pad if needed
                hash_str = f"{avg_int:064x}"[:16].zfill(16)
        except Exception as pil_exc:
            logger.warning(f"PIL loading failed for {path}: {pil_exc}, trying OpenCV fallback")
            # Fallback to OpenCV if PIL fails
            import cv2
            import numpy as np
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                raise SimilarityError(f"Failed to load image {path} with both PIL and OpenCV")

            # Convert BGR to RGB for PIL compatibility
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(image_rgb)
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            r, g, b = pil_img.split()

            h_r = imagehash.whash(r, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
            h_g = imagehash.whash(g, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
            h_b = imagehash.whash(b, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)

            # Average the integer representations
            int_r = int(str(h_r), 16)
            int_g = int(str(h_g), 16)
            int_b = int(str(h_b), 16)
            avg_int = (int_r + int_g + int_b) // 3

            # Format as 64-bit hex (16 chars), truncate/pad if needed
            hash_str = f"{avg_int:064x}"[:16].zfill(16)

        # Validate hash length and normalize if needed
        if len(hash_str) < 8:
            raise SimilarityError(f"Color wHash too short: {len(hash_str)} characters")
        elif len(hash_str) > 32:
            raise SimilarityError(f"Color wHash too long: {len(hash_str)} characters")
        elif len(hash_str) != 16:
            logger.warning(f"Color wHash length {len(hash_str)}, expected 16, normalizing")
            if len(hash_str) < 16:
                hash_str = hash_str.zfill(16)
            else:
                hash_str = hash_str[:16]

        logger.info(f"Computed color wHash for {image_path} (size={effective_hash_size}, mode={mode}, wavelet={wavelet}): {hash_str}")
        return hash_str

    except Exception as e:
        logger.error(f"Color wHash failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"Color wHash computation failed: {e}") from e


def find_similar_whash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity',
    algorithm: str = 'whash'
) -> List[Group]:
    # Fixed duplicate mode skips
    """
    Find groups of visually similar images using wHash Hamming distances.

    Performs clustering: For n <= 1000 or if LSH unavailable, uses brute-force pairwise distances and union-find
    to group images where any chain of distances <= threshold (transitive similarity).
    For n > 1000 and datasketch available, uses MinHashLSH for candidate retrieval (approximating bit sets as MinHash signatures)
    + exact Hamming verification on candidates, then union-find.
    Input dicts should have 'path' (str) and 'hash' (str) keys. Outputs groups of 2+ paths.
    Threshold defaults to settings['similarity']['whash_threshold'] or 12.
    LSH uses num_perm=128, threshold=1 - (hamming_threshold / 64.0) for Jaccard approximation.

    Args:
        hashes (List[Dict[str, str]]): List of image records, e.g.,
            [{'path': '/img1.jpg', 'hash': 'a1b2c3d4e5f67890'}, ...].
            Typically from DB query (image_hashes table joined with images, algorithm='whash').
        threshold (Optional[int]): Maximum Hamming distance for similarity (0-64).
            Lower values = stricter matching (e.g., 8 for near-identical).
        settings (Optional[Dict]): Settings dict to override threshold via
            settings['similarity']['whash_threshold'] (default 12).
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.
        search_type (str): 'similarity' to ensure full computations.

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - images (List[FileItem]): FileItem objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (GroupStats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].images[0].score → 0.95 (95% similarity)

    Raises:
        ValueError: If hashes list is empty, invalid dict structure, or invalid hashes.
        SimilarityError: If grouping fails (e.g., fallback errors).

    Example:
        >>> sample_hashes = [
        ...     {'path': '/img1.jpg', 'hash': '0000000000000000'},
        ...     {'path': '/img2.jpg', 'hash': '0000000000000001'},
        ...     {'path': '/img3.jpg', 'hash': '1111111111111111'}
        ... ]
        >>> groups = find_similar_whash(sample_hashes, threshold=1)
        >>> print(groups)  # [['/img1.jpg', '/img2.jpg']]
        [['/img1.jpg', '/img2.jpg']]

        # For large n (e.g., 2000 images), LSH reduces candidates from O(n^2) to ~O(n * k), where k << n
        >>> large_hashes = [{'path': f'/img{i}.jpg', 'hash': 'a' * 16} for i in range(2000)]  # Simulate
        >>> groups_large = find_similar_whash(large_hashes, threshold=5)
        >>> print(f"Groups: {len(groups_large)}")

    Note:
        - Brute-force O(n^2) for all sizes; for large n (>1000), consider external indexing in future.
        - Logs warning for large inputs.
        - Threshold tuning: Test empirically (0=exact, 12~similar, 20~loose for wHash).
    """
    if not hashes:
        raise ValueError("hashes list cannot be empty")

    n = len(hashes)

    # Retrieve the active quality evaluator once for the entire batch
    quality_evaluator = get_active_image_quality_evaluator()

    # Validate input
    for i, h in enumerate(hashes):
        if not isinstance(h, dict) or 'path' not in h or 'hash' not in h:
            raise ValueError(f"Invalid dict at index {i}: missing 'path' or 'hash'")
        if not isinstance(h['path'], str) or not h['path']:
            raise ValueError(f"Empty path at index {i}")

        # Validate and normalize hash length
        hash_str = h['hash']
        if not isinstance(hash_str, str) or not hash_str:
            raise ValueError(f"Empty or invalid hash at index {i}")

        # Handle variable hash lengths gracefully
        if len(hash_str) == 16:
            # Standard 64-bit hash
            pass
        elif len(hash_str) == 21:
            # Handle 21-character hashes - extract only hex digits from the end
            logger.warning(f"Hash length 21 at index {i}, extracting hex digits for compatibility")
            # Extract only the hex digits from the hash string
            hex_digits = ''.join(c for c in hash_str if c in '0123456789abcdefABCDEF')
            if len(hex_digits) >= 16:
                hash_str = hex_digits[:16]
            else:
                # Pad if we don't have enough hex digits
                hash_str = hex_digits.zfill(16)
            h['hash'] = hash_str
        elif len(hash_str) < 8:
            raise ValueError(f"Hash too short at index {i}: {len(hash_str)} (minimum 8 characters)")
        elif len(hash_str) > 32:
            raise ValueError(f"Hash too long at index {i}: {len(hash_str)} (maximum 32 characters)")
        else:
            # For lengths between 8-32, pad or truncate to 16 characters
            if len(hash_str) < 16:
                logger.warning(f"Hash length {len(hash_str)} at index {i}, padding to 16 characters")
                hash_str = hash_str.zfill(16)
            else:
                logger.warning(f"Hash length {len(hash_str)} at index {i}, truncating to 16 characters")
                hash_str = hash_str[:16]
            h['hash'] = hash_str

        # Validate hex characters
        if not all(c in '0123456789abcdefABCDEF' for c in hash_str):
            raise ValueError(f"Invalid hex characters in hash at index {i}: {hash_str}")

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('whash_threshold', 12)
        else:
            threshold = 12
    if threshold < 0 or threshold > 64:
        raise ValueError(f"Threshold must be 0-64, got {threshold}")

    # Path to index mapping for LSH
    path_to_index = {h['path']: i for i, h in enumerate(hashes)}

    # Union-find for clustering
    parent = list(range(n))

    def find(p: int) -> int:
        if parent[p] != p:
            parent[p] = find(parent[p])
        return parent[p]

    def union(p1: int, p2: int) -> None:
        pp1 = find(p1)
        pp2 = find(p2)
        if pp1 != pp2:
            parent[pp1] = pp2

    if n > 1000:
        logger.warning(f"Large input ({n} images) for brute-force grouping; consider external indexing for scale in production")

    # Always use brute-force pairwise comparison
    # Compute pairwise distances (brute-force)
    for i in range(n):
        for j in range(i + 1, n):
            try:
                dist = hamming_distance(hashes[i]['hash'], hashes[j]['hash'])
                if dist <= threshold:
                    union(i, j)
            except ValueError as e:
                logger.warning(f"Skipping invalid pair ({i}, {j}): {e}")
                continue

    # Build groups using indices to preserve hashes
    from collections import defaultdict
    group_dict: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        root = find(i)
        group_dict[root].append(i)

    groups: List[Group] = []
    group_id = 1
    for root, indices in group_dict.items():
        if len(indices) < 2:
            continue
        group_hashes = [hashes[i] for i in indices]
        group_hashes.sort(key=lambda d: d['path'])
        ref_hash_dict = group_hashes[0]
        ref_path = ref_hash_dict['path']
        ref_hash = ref_hash_dict['hash']
        images: List[FileItem] = []
        valid_count = 0
        for h_dict in group_hashes:
            try:
                dist = hamming_distance(ref_hash, h_dict['hash'])
                score = 1.0 - (dist / 64.0)
                # Fixed duplicate mode skips
                # For exact duplicates, fetch only file stats without image loading
                stat = os.stat(h_dict['path'])
                size = stat.st_size
                mod_ts = stat.st_mtime
                mod_date = format_timestamp(mod_ts)
                resolution = "Unknown"  # No image loading for duplicates
                quality_score, quality_algorithm = get_image_quality_score(h_dict['path'], quality_evaluator, flat_cache_manager, search_type=search_type)

                file_item = FileItem(
                    path=h_dict['path'],
                    size=size,
                    resolution=resolution,
                    mod_date=mod_date,
                    score=score,
                    file_type="",
                    savings=0,
                    quality_score=quality_score,
                    quality_algorithm=quality_algorithm,
                )
                images.append(file_item)
                valid_count += 1
            except Exception as e:
                logger.warning(f"Failed to create FileItem for {h_dict['path']}: {e}")
                continue
        if valid_count < 2:
            continue
        stats = compute_group_stats(images)
        group_obj = Group(
            id=group_id,
            items=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group_obj)
        group_id += 1

    logger.info(f"Found {len(groups)} similar wHash groups (threshold={threshold}, n={n}, search_type={search_type})")
    return groups


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
    Uses flat_cache.get_hashes for efficiency.
    # Fixed duplicate mode skips

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. Cache is used/updated if provided and update_cache=True.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Settings for overrides.
        cache_manager (Optional[CacheManager]): Legacy Cache instance.
        flat_cache_manager (Optional[FlatCacheManager]): FlatCache instance.
        update_cache (bool): If True, update cache on misses (applies to legacy cache only; flat cache handles its own updates internally).
        search_type (str): 'duplicate' to skip computation, return {} without image loading.

    Returns:
        Dict[str, Optional[str]]: {path: hash_str or None if failed}.

    Raises:
        ValueError: If paths is empty.
        SimilarityError: If batch setup fails.

    Example:
        >>> paths = ['/img1.jpg', '/img2.jpg']
        >>> results = compute_whash_batch(paths, wavelet='haar')
        >>> print(results)
        {'/img1.jpg': 'a1b2c3d4e5f67890', '/img2.jpg': 'b2c3d4e5f6789012'}

    Note:
        - Logs progress via logger.info (e.g., "Batch progress: 1/10 - /path/to/img.jpg").
        - For large batches, consider future parallelization with ThreadPoolExecutor.
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

    logger.info(f"Starting batch {algorithm} computation for {total} images (size={hash_size}, mode={mode}, wavelet={wavelet}) [cache-enabled]")

    # Use get_hashes for batch efficiency (note: get_hashes doesn't support mode/wavelet params yet; assume default or extend if needed)
    # For now, since _compute_hash in flat_cache uses default for whash, call batch
    batch_results = flat_cache_manager.get_hashes(paths, [algorithm], search_type=search_type)

    for path in paths:
        hash_val = batch_results.get(path, {}).get(algorithm)
        results[path] = hash_val
        if hash_val is None:
            logger.warning(f"Failed to compute {algorithm} for {path}")

    success_count = sum(1 for v in results.values() if v is not None)

    # Calculate cache hit information
    if flat_cache_manager:
        cache_hits = len([p for p in paths if p in batch_results and batch_results[p].get(algorithm) is not None])
        cache_info = f" (cache hits: {cache_hits})"
    else:
        cache_info = ""

    logger.info(f"Batch complete: {success_count}/{total} successful{cache_info}")

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
        algorithm (Optional[str]): 'phash' or 'whash'. If None, retrieves from settings['criteria']['similarity_hash_algorithm'] or defaults to 'phash'.
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
        >>> print(hash_val)  # 'a1b2c3d4e5f67890'
    """
    # DEBUG: Log settings structure and algorithm selection process
    logger.debug(f"get_similarity_hash called for {image_path}")
    logger.debug(f"  algorithm parameter: {algorithm}")
    logger.debug(f"  settings provided: {settings is not None}")

    if settings:
        logger.debug(f"  settings keys: {list(settings.keys())}")
        if 'criteria' in settings:
            logger.debug(f"  criteria keys: {list(settings['criteria'].keys())}")
            logger.debug(f"  similarity_hash_algorithm in criteria: {'similarity_hash_algorithm' in settings['criteria']}")
        if 'mode' in settings:
            logger.debug(f"  settings mode: {settings['mode']}")

    if algorithm is None:
        logger.debug("  algorithm not provided, attempting to resolve from settings...")

        if settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            algorithm = settings['criteria']['similarity_hash_algorithm']
            logger.debug(f"  resolved algorithm from settings: {algorithm}")
        else:
            algorithm = 'phash'
            logger.debug(f"  using default algorithm: {algorithm}")

            # Additional debugging for why settings didn't work
            if settings:
                if 'criteria' not in settings:
                    logger.warning("  settings missing 'criteria' key")
                elif 'similarity_hash_algorithm' not in settings['criteria']:
                    logger.warning("  settings['criteria'] missing 'similarity_hash_algorithm' key")
                    if 'mode' in settings:
                        logger.warning(f"  settings mode is '{settings['mode']}' - this might be expected if mode is 'duplicates'")
            else:
                logger.warning("  no settings provided")

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

    # DEBUG: Log batch algorithm selection
    logger.debug(f"compute_similarity_hash_batch called for {len(paths)} paths, search_type={search_type}")
    logger.debug(f"  algorithm parameter: {algorithm}")
    logger.debug(f"  settings provided: {settings is not None}")

    if settings:
        logger.debug(f"  settings keys: {list(settings.keys())}")
        if 'criteria' in settings:
            logger.debug(f"  criteria keys: {list(settings['criteria'].keys())}")
            logger.debug(f"  similarity_hash_algorithm in criteria: {'similarity_hash_algorithm' in settings['criteria']}")
        if 'mode' in settings:
            logger.debug(f"  settings mode: {settings['mode']}")

    if algorithm is None:
        logger.debug("  algorithm not provided, attempting to resolve from settings...")

        if settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            algorithm = settings['criteria']['similarity_hash_algorithm']
            logger.debug(f"  resolved algorithm from settings: {algorithm}")
        else:
            algorithm = 'phash'
            logger.debug(f"  using default algorithm: {algorithm}")

            # Additional debugging for why settings didn't work
            if settings:
                if 'criteria' not in settings:
                    logger.warning("  settings missing 'criteria' key")
                elif 'similarity_hash_algorithm' not in settings['criteria']:
                    logger.warning("  settings['criteria'] missing 'similarity_hash_algorithm' key")
                    if 'mode' in settings:
                        logger.warning(f"  settings mode is '{settings['mode']}' - this might be expected if mode is 'duplicates'")
            else:
                logger.warning("  no settings provided")

    if algorithm == 'phash':
        return compute_phash_batch(paths, settings=settings, flat_cache_manager=flat_cache_manager, algorithm=algorithm)
    elif algorithm == 'whash':
        return compute_whash_batch(paths, settings=settings, flat_cache_manager=flat_cache_manager, search_type=search_type, algorithm=algorithm)
    else:
        raise ValueError(f"Unsupported similarity hash algorithm: {algorithm}. Supported: 'phash', 'whash'")


def detect_exact_duplicates(
    paths: List[str],
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> Tuple[List[ExactDuplicateSet], Dict[str, Optional[int]]]:
    """
    Detect exact duplicate sets using XXH3 content hashes, with caching support.

    Computes XXH3 hashes for all provided paths (using FlatCacheManager if available,
    falling back to direct computation). Groups paths by identical hashes into sets
    of size >=2. Singletons (unique hashes or uncomputable) are mapped to None.

    Args:
        paths: List of absolute file paths to process.
        flat_cache_manager: Optional FlatCacheManager for caching XXH3 computations.
            If provided, uses get_hashes to compute/retrieve 'xxh3' for all paths.

    Returns:
        Tuple[List[ExactDuplicateSet], Dict[str, Optional[int]]]:
            - exact_sets: List of ExactDuplicateSet objects (only groups with >=2 files).
            - path_to_set_id_map: Mapping of each path to its set ID (int for duplicates, None for uniques/uncomputable).

    Raises:
        ValueError: If paths is empty.
        SimilarityError: If XXH3 computation fails for all paths (partial failures logged, paths mapped to None).

    Example:
        >>> paths = ["/img1.jpg", "/img2.jpg", "/unique.jpg"]
        >>> sets, mapping = detect_exact_duplicates(paths)
        >>> # If img1 and img2 match: sets = [ExactDuplicateSet(id=1, paths=["/img1.jpg", "/img2.jpg"], rep="/img1.jpg")]
        >>> # mapping = {"/img1.jpg": 1, "/img2.jpg": 1, "/unique.jpg": None}
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    logger.info(f"Detecting exact duplicates for {len(paths)} paths using XXH3 (cache: {flat_cache_manager is not None})")

    # Compute XXH3 hashes for all paths (use cache if available)
    path_to_hash: Dict[str, Optional[str]] = {}
    if flat_cache_manager:
        try:
            hashes = flat_cache_manager.get_hashes(paths, ['xxh3'])
            path_to_hash = {p: h.get('xxh3') for p, h in hashes.items()}
            logger.debug(f"Retrieved {sum(1 for h in path_to_hash.values() if h is not None)}/{len(paths)} XXH3 hashes from cache")
        except Exception as e:
            logger.warning(f"Cache failure for XXH3; falling back to direct computation: {e}")
            path_to_hash = {}
    else:
        path_to_hash = {}

    # Direct computation for misses or no cache
    for path in paths:
        if path not in path_to_hash or path_to_hash[path] is None:
            try:
                hash_val = compute_xxh3(Path(path))
                path_to_hash[path] = hash_val
                logger.debug(f"Computed XXH3 for {path}: {hash_val[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to compute XXH3 for {path}: {e}")
                path_to_hash[path] = None

    # Group by hash
    from collections import defaultdict
    hash_to_paths_map: Dict[str, List[str]] = defaultdict(list)
    for path, h in path_to_hash.items():
        if h is not None:
            hash_to_paths_map[h].append(path)
        else:
            # Uncomputable: treat as unique
            hash_to_paths_map[path].append(path)  # Use path as "hash" for singletons

    # Build exact sets (only groups >=2) and mapping
    exact_sets: List[ExactDuplicateSet] = []
    path_to_set_id_map: Dict[str, Optional[int]] = {}
    set_id = 1

    for h, group_paths in hash_to_paths_map.items():
        if len(group_paths) < 2:
            # Singleton: map to None
            for p in group_paths:
                path_to_set_id_map[p] = None
        else:
            # Exact duplicate set
            sorted_paths = sorted(group_paths)
            rep_path = sorted_paths[0]  # Lex smallest as representative
            exact_set = ExactDuplicateSet(id=set_id, paths=sorted_paths, representative_path=rep_path)
            exact_sets.append(exact_set)
            # Map all paths in set to set_id
            for p in sorted_paths:
                path_to_set_id_map[p] = set_id
            set_id += 1
            logger.debug(f"Exact duplicate set {set_id-1}: {len(sorted_paths)} files, rep: {rep_path}")

    logger.info(f"Detected {len(exact_sets)} exact duplicate sets from {len(paths)} paths "
                f"({sum(len(s.paths) for s in exact_sets)} duplicates total)")
    return exact_sets, path_to_set_id_map


def find_exact_duplicates(
    hashes: List[Dict[str, str]],
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity'
) -> List[Group]:
    # Fixed duplicate mode skips
    """
    Find groups of exact duplicate images based on content hash equality.

    Groups paths with identical hash values. Fetches metadata for each, sets score=1.0
    for all, and computes stats. Suitable for BLAKE3 or SHA-256 hashes.

    Args:
        hashes (List[Dict[str, str]]): List of {'path': str, 'hash': str} where 'hash' is
            content hash (e.g., BLAKE3 hex). From DB or computed.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.

    Returns:
        List[Group]: List of duplicate groups with FileItem (score=1.0), stats.

    Raises:
        ValueError: If hashes empty or invalid.
        InvalidImageError: For metadata fetch failures.

    Example:
        >>> sample_hashes = [
        ...     {'path': '/img1.jpg', 'hash': 'abc123'},
        ...     {'path': '/img2.jpg', 'hash': 'abc123'},
        ...     {'path': '/img3.jpg', 'hash': 'def456'}
        ... ]
        >>> groups = find_exact_duplicates(sample_hashes)
        >>> print(len(groups))  # 1 group
        1
    """
    if not hashes:
        raise ValueError("hashes list cannot be empty")

    from collections import defaultdict

    # Retrieve the active quality evaluator once for the entire batch
    if search_type != 'duplicate':
        quality_evaluator = get_active_image_quality_evaluator()
    else:
        quality_evaluator = None

    hash_to_paths = defaultdict(list)
    for h in hashes:
        if 'path' not in h or 'hash' not in h or not isinstance(h['path'], str):
            raise ValueError("Invalid hash dict: missing 'path' or 'hash'")
        hash_to_paths[h['hash']].append(h['path'])

    groups: List[Group] = []
    group_id = 1
    for hash_val, paths in hash_to_paths.items():
        if len(paths) < 2:
            continue
        paths.sort()
        ref_path = paths[0]

        images: List[FileItem] = []
        for path in paths:
            try:
                # Fixed duplicate mode skips
                meta = get_image_metadata(path, search_type=search_type)
                score = 1.0
                if search_type == 'duplicate':
                    quality_score = 1.0
                    quality_algorithm = None
                else:
                    quality_score, quality_algorithm = get_image_quality_score(path, quality_evaluator, flat_cache_manager, search_type=search_type)

                file_item = FileItem(
                    path=path,
                    size=meta['size'],
                    resolution=meta['resolution'],
                    mod_date=meta['mod_date'],
                    score=score,
                    file_type="",
                    savings=0,
                    quality_score=quality_score,
                    quality_algorithm=quality_algorithm,
                )
                images.append(file_item)
            except Exception as e:
                logger.error(f"Failed to process duplicate {path}: {e}")
                continue

        if len(images) < 2:
            continue

        stats = compute_group_stats(images)
        # Override scores for exact
        stats.min_score = 1.0
        stats.max_score = 1.0
        stats.avg_score = 1.0

        group = Group(
            id=group_id,
            items=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group)
        group_id += 1

    logger.info(f"Found {len(groups)} exact duplicate groups (n={len(hashes)})")
    return groups


def find_similar_images(
    paths: List[str],
    algorithm: Optional[str] = None,
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity'
) -> List[Group]:
    """
    Dispatcher for finding similar or exact duplicate image groups using paths.

    For 'exact': Computes content hashes (XXH3), groups identical files.
    For perceptual ('phash', 'whash'): Two-phase process:
    1. Detect exact duplicates via XXH3 to identify sets and representatives.
    2. Compute perceptual hashes only on unique representatives.
    3. Cluster representatives by perceptual similarity.
    4. Expand each cluster by including all exact duplicates of its representatives.
    5. Create FileItem objects with exact_set_id set accordingly.

    Args:
        paths: List of absolute file paths to process.
        algorithm: 'exact', 'phash', or 'whash' (default from settings or 'phash').
        threshold: Max Hamming distance for perceptual clustering (ignored for 'exact').
        settings: For algorithm selection and threshold overrides.
        flat_cache_manager: For caching all hash computations and metadata.
        search_type: 'similarity' or 'duplicate' (affects computations, e.g., skips perceptual in duplicate mode).

    Returns:
        List[Group]: Enriched groups with FileItem (scores normalized, exact_set_id set).

    Raises:
        ValueError: Invalid algorithm, empty paths, or computation failures.
        SimilarityError: For hash or clustering errors.

    Example:
        >>> paths = ["/img1.jpg", "/img2.jpg", "/unique.jpg"]
        >>> groups = find_similar_images(paths, algorithm='phash', threshold=10)
        >>> # Groups expanded with exact dups, exact_set_id set
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    # Determine algorithm
    logger.debug(f"find_similar_images determining algorithm for {len(paths)} paths")
    logger.debug(f"  algorithm parameter: {algorithm}")
    logger.debug(f"  settings provided: {settings is not None}")

    if settings:
        logger.debug(f"  settings keys: {list(settings.keys())}")
        if 'criteria' in settings:
            logger.debug(f"  criteria keys: {list(settings['criteria'].keys())}")
            logger.debug(f"  similarity_hash_algorithm in criteria: {'similarity_hash_algorithm' in settings['criteria']}")
        if 'mode' in settings:
            logger.debug(f"  settings mode: {settings['mode']}")

    if algorithm is None:
        logger.debug("  algorithm not provided, attempting to resolve from settings...")

        if settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            algorithm = settings['criteria']['similarity_hash_algorithm']
            logger.debug(f"  resolved algorithm from settings: {algorithm}")
        else:
            algorithm = 'phash'
            logger.debug(f"  using default algorithm: {algorithm}")

            # Additional debugging for why settings didn't work
            if settings:
                if 'criteria' not in settings:
                    logger.warning("  settings missing 'criteria' key")
                elif 'similarity_hash_algorithm' not in settings['criteria']:
                    logger.warning("  settings['criteria'] missing 'similarity_hash_algorithm' key")
                    if 'mode' in settings:
                        logger.warning(f"  settings mode is '{settings['mode']}' - this might be expected if mode is 'duplicates'")
            else:
                logger.warning("  no settings provided")

    if algorithm not in ['exact', 'phash', 'whash']:
        raise ValueError(f"Unsupported algorithm: {algorithm}. Supported: 'exact', 'phash', 'whash'")

    logger.info(f"Finding {algorithm} groups for {len(paths)} paths (search_type={search_type})")

    if algorithm == 'exact':
        # For exact: use detect_exact_duplicates, then create Groups from sets
        exact_sets, _ = detect_exact_duplicates(paths, flat_cache_manager)
        groups = []
        group_id = 1
        quality_evaluator = get_active_image_quality_evaluator() if search_type != 'duplicate' else None
        for exact_set in exact_sets:
            images = []
            for path in exact_set.paths:
                try:
                    meta = get_image_metadata(path, search_type=search_type)
                    score = 1.0
                    quality_score, quality_algorithm = (
                        (1.0, None) if search_type == 'duplicate' else
                        get_image_quality_score(path, quality_evaluator, flat_cache_manager, search_type=search_type)
                    )
                    file_item = FileItem(
                        path=path,
                        size=meta['size'],
                        resolution=meta['resolution'],
                        mod_date=meta['mod_date'],
                        score=score,
                        file_type="",
                        savings=0,
                        quality_score=quality_score,
                        quality_algorithm=quality_algorithm,
                        exact_set_id=exact_set.id  # Set to set ID for exact groups
                    )
                    images.append(file_item)
                except Exception as e:
                    logger.error(f"Failed to create FileItem for exact dup {path}: {e}")
                    continue
            if len(images) >= 2:
                stats = compute_group_stats(images)
                stats.min_score = 1.0
                stats.max_score = 1.0
                stats.avg_score = 1.0
                group = Group(
                    id=group_id,
                    items=images,
                    stats=stats,
                    ref_path=exact_set.representative_path
                )
                groups.append(group)
                group_id += 1
        logger.info(f"Exact mode: Found {len(groups)} groups from {len(exact_sets)} sets")
        return groups

    # Perceptual similarity: Two-phase integration
    # Phase 1: Detect exact duplicates
    exact_sets, path_to_set_id_map = detect_exact_duplicates(paths, flat_cache_manager)

    # Identify unique representatives
    rep_paths = set()
    for path in paths:
        set_id = path_to_set_id_map.get(path)
        if set_id is None:
            # Singleton: use itself
            rep_paths.add(path)
        else:
            # Duplicate: use rep from its set
            for s in exact_sets:
                if s.id == set_id:
                    rep_paths.add(s.representative_path)
                    break

    all_reps = list(rep_paths)
    logger.debug(f"Phase 1 complete: {len(exact_sets)} exact sets, {len([p for p in paths if path_to_set_id_map.get(p) is None])} singletons, {len(all_reps)} unique reps")

    # Phase 2: Compute perceptual hashes only for representatives
    perceptual_hashes = compute_similarity_hash_batch(
        all_reps, algorithm=algorithm, settings=settings, flat_cache_manager=flat_cache_manager, search_type=search_type
    )

    # Filter valid reps (skip if hash computation failed)
    valid_reps = [rep for rep in all_reps if perceptual_hashes.get(rep) is not None]
    rep_hashes = [{'path': rep, 'hash': perceptual_hashes[rep]} for rep in valid_reps]

    if not rep_hashes:
        logger.warning("No valid perceptual hashes computed for representatives; returning empty groups")
        return []

    # Phase 3: Perform similarity clustering on representatives
    if algorithm == 'phash':
        rep_groups = find_similar_phash(rep_hashes, threshold, settings, flat_cache_manager, search_type=search_type, algorithm=algorithm)
    elif algorithm == 'whash':
        rep_groups = find_similar_whash(rep_hashes, threshold, settings, flat_cache_manager, search_type=search_type, algorithm=algorithm)
    else:
        raise ValueError(f"Unexpected perceptual algorithm: {algorithm}")

    logger.debug(f"Phase 3: Clustered {len(valid_reps)} reps into {len(rep_groups)} perceptual groups")

    # Phase 4: Expand groups with exact duplicates
    final_groups = []
    perceptual_group_id = 1
    quality_evaluator = get_active_image_quality_evaluator() if search_type != 'duplicate' else None

    for rep_group in rep_groups:
        expanded_items = []
        ref_path = rep_group.ref_path  # Keep original ref (a rep)

        # For each rep in the perceptual group, create FileItem with exact_set_id from map
        for rep_item in rep_group.items:
            # Recreate rep_item with exact_set_id
            rep_set_id = path_to_set_id_map.get(rep_item.path)
            rep_item_with_id = FileItem(
                path=rep_item.path,
                size=rep_item.size,
                resolution=rep_item.resolution,
                mod_date=rep_item.mod_date,
                score=rep_item.score,
                file_type=rep_item.file_type,
                savings=rep_item.savings,
                quality_score=rep_item.quality_score,
                quality_algorithm=rep_item.quality_algorithm,
                exact_set_id=rep_set_id  # None for singletons, id for reps from sets
            )
            expanded_items.append(rep_item_with_id)

            # Expand with exact dups of this rep if any (other members of its set)
            if rep_set_id is not None:
                for exact_set in exact_sets:
                    if exact_set.id == rep_set_id:
                        # Add all other paths in the set (excluding the rep itself)
                        for dup_path in exact_set.paths:
                            if dup_path != rep_item.path:
                                try:
                                    meta = get_image_metadata(dup_path, search_type=search_type)
                                    # Score same as rep's score (exact dup, same perceptual)
                                    dup_score = rep_item.score
                                    quality_score, quality_algorithm = (
                                        (1.0, None) if search_type == 'duplicate' else
                                        get_image_quality_score(dup_path, quality_evaluator, flat_cache_manager, search_type=search_type)
                                    )
                                    dup_item = FileItem(
                                        path=dup_path,
                                        size=meta['size'],
                                        resolution=meta['resolution'],
                                        mod_date=meta['mod_date'],
                                        score=dup_score,
                                        file_type="",
                                        savings=0,
                                        quality_score=quality_score,
                                        quality_algorithm=quality_algorithm,
                                        exact_set_id=rep_set_id  # Same set as rep
                                    )
                                    expanded_items.append(dup_item)
                                except Exception as e:
                                    logger.error(f"Failed to create FileItem for dup {dup_path}: {e}")
                                    continue
                        break  # Only one set per rep

        # Sort expanded items by path
        expanded_items.sort(key=lambda item: item.path)

        if len(expanded_items) >= 2:  # Only groups with >=2 after expansion
            # Recalculate stats for expanded group
            stats = compute_group_stats(expanded_items)
            final_group = Group(
                id=perceptual_group_id,
                items=expanded_items,
                stats=stats,
                ref_path=ref_path
            )
            final_groups.append(final_group)
            perceptual_group_id += 1

    logger.info(f"Perceptual mode ({algorithm}): Found {len(final_groups)} expanded groups from {len(rep_groups)} rep groups")
    return final_groups


if __name__ == "__main__":
    """
    Simple module test: Verify imports and basic calls.
    Uses dummy paths (raises InvalidImageError, expected).
    """
    print("Image similarity module loaded successfully.")
    try:
        _ = compute_phash("dummy.jpg")
        print("pHash call OK (dummy fails gracefully).")
    except InvalidImageError:
        print("Expected pHash error.")
    except Exception as e:
        print(f"pHash error: {e}")

    try:
        _ = compute_whash("dummy.jpg")
        print("wHash call OK (dummy fails gracefully).")
    except InvalidImageError:
        print("Expected wHash error.")
    except Exception as e:
        print(f"wHash error: {e}")

    try:
        sample_paths = ['a.jpg', 'b.jpg']
        groups = find_similar_images(sample_paths, algorithm='exact')
        print(f"Exact duplicates: {len(groups)} groups")
    except Exception as e:
        print(f"Exact test error: {e}")

    print("Verification complete.")
