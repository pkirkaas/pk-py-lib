"""
src/pk_py_lib/core/image/similarity/metadata.py

Metadata extraction utilities for image similarity detection.
Handles image properties, quality scoring, and group statistics computation.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

from PIL import Image

from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.image.quality.base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.models import FileItem, GroupStats

from .similarity_types import InvalidImageError
from .validation import is_image_extension

logger = get_logger(__name__)


def format_timestamp(ts: float) -> str:
    """
    Format Unix timestamp to human-readable date string.

    Converts a Unix epoch timestamp (seconds since 1970-01-01) to a formatted
    date string in the format "dd-MMM-yy" (e.g., "15-Sep-25"). Returns "Unknown"
    if the timestamp is invalid or cannot be converted.

    Args:
        ts (float): Unix timestamp (seconds since epoch).

    Returns:
        str: Formatted date as "dd-MMM-yy" (e.g., "15-Sep-25"), or "Unknown" on error.

    Example:
        >>> format_timestamp(1726400000.0)
        '15-Sep-24'
        >>> format_timestamp(-1)  # Invalid timestamp
        'Unknown'
        >>> format_timestamp(0)  # Epoch start
        '01-Jan-70'
    """
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d-%b-%y")
    except (ValueError, OSError):
        return "Unknown"


def get_resolution(path: str, search_type: str = 'similarity') -> str:
    """
    Get image resolution (width x height) using PIL.

    Loads the image and extracts its dimensions. For efficiency in duplicate
    detection mode, returns "Unknown" without loading the image. Also returns
    "Unknown" for non-image files or if loading fails.

    Args:
        path (str): Path to the image file.
        search_type (str): 'duplicate' to skip image loading and return "Unknown",
            'similarity' for full processing.

    Returns:
        str: Resolution string (e.g., "1920x1080") or "Unknown" on failure/skip.

    Raises:
        InvalidImageError: If image cannot be loaded in similarity mode and
            the file is expected to be an image.

    Example:
        >>> get_resolution("/path/to/img.jpg")
        '1920x1080'
        >>> get_resolution("/path/to/img.jpg", search_type='duplicate')
        'Unknown'
        >>> get_resolution("/path/to/not_an_image.txt")
        'Unknown'

    Note:
        In duplicate mode, resolution extraction is skipped because it requires
        loading the full image, which is expensive for exact duplicate detection
        that only needs content hashes.
    """
    # Skip image loading in duplicate mode for efficiency
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

    Retrieves file statistics (size, modification time) and optionally image
    dimensions. The resolution extraction is skipped in duplicate mode or for
    non-image files to improve performance.

    Args:
        path (str): Path to the image file.
        search_type (str): 'duplicate' to skip image loading (returns "Unknown"
            for resolution), 'similarity' for full metadata extraction.

    Returns:
        Dict[str, any]: Dictionary with keys:
            - 'size' (int): File size in bytes
            - 'resolution' (str): Image resolution "WxH" or "Unknown"
            - 'mod_date' (str): Formatted modification date "dd-MMM-yy"

    Raises:
        IOError: For file access errors (permissions, file not found).
        InvalidImageError: For image loading issues in similarity mode.

    Example:
        >>> meta = get_image_metadata("/path/to/img.jpg")
        >>> print(f"Size: {meta['size']}, Resolution: {meta['resolution']}")
        Size: 524288, Resolution: 1920x1080
        >>> meta_dup = get_image_metadata("/path/to/img.jpg", search_type='duplicate')
        >>> print(meta_dup['resolution'])
        Unknown

    Note:
        File size and modification date are always retrieved regardless of search_type.
        Only resolution extraction is conditional.
    """
    try:
        stat = os.stat(path)
        size = stat.st_size
        mod_ts = stat.st_mtime
        mod_date = format_timestamp(mod_ts)

        # Skip image operations for non-images regardless of search_type
        if not is_image_extension(path):
            return {'size': size, 'resolution': 'Unknown', 'mod_date': mod_date}

        # Skip image loading in duplicate mode for efficiency
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
    Compute the image quality score using the provided evaluator, preferring cached value.

    If the evaluator is None (quality evaluation disabled), returns (None, None).
    If flat_cache_manager is provided, checks for cached brisque score first.
    If evaluation fails, logs an error and returns (None, evaluator.name).

    Quality scores are normalized (higher is better) and represent perceptual quality.
    Common algorithms include BRISQUE (Blind/Referenceless Image Spatial Quality Evaluator).

    Args:
        path (str): Path to the image file.
        evaluator (Optional[ImageQualityEvaluator]): Instantiated quality evaluator or None
            to disable quality scoring.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to check for cached score and store new computation.
        search_type (str): 'duplicate' to skip computation and return (None, None);
            'similarity' to perform evaluation.

    Returns:
        tuple[Optional[float], Optional[str]]: (quality_score, algorithm_name) where:
            - quality_score: Normalized score (higher is better) or None if disabled/failed
            - algorithm_name: Name of the evaluator (e.g., 'brisque') or None

    Example:
        >>> from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
        >>> from pk_py_lib.core.flat_cache import FlatCacheManager
        >>> evaluator = get_active_image_quality_evaluator()
        >>> flat_cache = FlatCacheManager()
        >>> score, name = get_image_quality_score("/path/to/img.jpg", evaluator, flat_cache)
        >>> print(f"Score: {score}, Algorithm: {name}")
        Score: 75.5, Algorithm: brisque

    Note:
        - In duplicate mode, quality evaluation is skipped for efficiency
        - Cache is automatically updated after successful computation
        - Failures are logged but don't raise exceptions (returns None score)
    """
    # Skip in duplicate mode for efficiency
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

    # Compute quality score
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

    Calculates various statistics across all files in a group, including:
    - Total size (sum of all file sizes)
    - Potential savings (total size minus smallest file size)
    - Quality score range (min, max, average)
    - File count

    For exact duplicate groups where all scores are None, sets scores to 1.0
    to indicate perfect similarity.

    Args:
        images (List[FileItem]): List of FileItem objects with metadata and scores.

    Returns:
        GroupStats: Aggregated statistics with attributes:
            - total_size (int): Total bytes across all files
            - savings (int): Bytes that could be saved by removing duplicates
            - min_score (float): Lowest similarity/quality score in group
            - max_score (float): Highest similarity/quality score in group
            - avg_score (float): Average similarity/quality score
            - file_count (int): Number of files in the group

    Example:
        >>> from pk_py_lib.gui.dialog_models import FileItem
        >>> item1 = FileItem(path='a', size=100, resolution='1920x1080',
        ...                  mod_date='01-Jan-25', score=0.8)
        >>> item2 = FileItem(path='b', size=200, resolution='1920x1080',
        ...                  mod_date='01-Jan-25', score=1.0)
        >>> stats = compute_group_stats([item1, item2])
        >>> print(f"Avg score: {stats.avg_score}, Savings: {stats.savings}")
        Avg score: 0.9, Savings: 200

    Note:
        If the images list is empty, returns a GroupStats object with all values set to 0.
    """
    if not images:
        # Return a default GroupStats object with zero/default values
        return GroupStats(
            total_size=0,
            savings=0,
            min_score=0.0,
            max_score=0.0,
            avg_score=0.0,
            file_count=0
        )

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
