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
from pk_py_lib.core.cache import CacheManager
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.models import ImageData, Group, Stats


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


def get_resolution(path: str) -> str:
    """
    Get image resolution (width x height) using PIL.

    Args:
        path (str): Path to the image file.

    Returns:
        str: Resolution string (e.g., "1920x1080") or "Unknown" on failure.

    Raises:
        InvalidImageError: If image cannot be loaded.

    Example:
        >>> res = get_resolution("/path/to/img.jpg")
        >>> print(res)
        1920x1080
    """
    try:
        with Image.open(path) as img:
            w, h = img.size
            return f"{w}x{h}"
    except Exception as e:
        logger.warning(f"Failed to get resolution for {path}: {e}")
        return "Unknown"


def get_image_metadata(path: str) -> Dict[str, any]:
    """
    Fetch basic metadata for an image: size, resolution, modification date.

    Args:
        path (str): Path to the image file.

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
    try:
        stat = os.stat(path)
        size = stat.st_size
        mod_ts = stat.st_mtime
        mod_date = format_timestamp(mod_ts)
        resolution = get_resolution(path)
        return {'size': size, 'resolution': resolution, 'mod_date': mod_date}
    except IOError as e:
        raise IOError(f"Failed to access file {path}: {e}")
    except Exception as e:
        raise InvalidImageError(path, f"Metadata extraction failed: {e}")


def compute_group_stats(images: List[ImageData]) -> Stats:
    """
    Compute aggregate statistics for a group of images.

    Args:
        images (List[ImageData]): List of ImageData objects.

    Returns:
        Stats: Aggregated min/max/avg score and total size.

    Example:
        >>> stats = compute_group_stats([img1, img2])
        >>> print(stats.avg_score)
        0.9
    """
    if not images:
        return Stats()

    scores = [img.score for img in images]
    sizes = [img.size for img in images]

    min_score = min(scores)
    max_score = max(scores)
    avg_score = sum(scores) / len(scores)
    total_size = sum(sizes)

    return Stats(min_score=min_score, max_score=max_score, avg_score=avg_score, total_size=total_size)


def compute_phash(
    image_path: str,
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None
) -> str:
    """
    Compute perceptual hash (pHash) for an image using Discrete Cosine Transform (DCT).

    Loads the image with Pillow, computes the hash using imagehash.phash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching to avoid recomputation.
    The settings dict is primarily for future use (e.g., threshold), but hash_size can
    be overridden via settings['criteria']['phash']['hash_size'] if provided.

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Higher values
            increase precision but computation time. Must be >=4 and <=64.
        settings (Optional[Dict]): Optional settings dictionary from core.settings_schema.
            If provided and contains 'criteria']['phash']['hash_size', overrides hash_size.
            Also used for logging context.
        cache_manager (Optional[CacheManager]): Optional CacheManager instance for caching.
            If provided, checks cache key f"{image_path}:phash" before computing and stores result.

    Returns:
        str: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890').

    Raises:
        InvalidImageError: If the image file does not exist, is not a valid image, or has an
            unsupported format (e.g., PIL.UnidentifiedImageError). Includes path and details.
        SimilarityError: For general computation failures (e.g., invalid hash_size, memory issues).
        IOError: For file access errors (e.g., permissions).
        ValueError: If hash_size is invalid or resulting hash is not 16 characters.

    Example:
        >>> from pk_py_lib.core.cache import CacheManager
        >>> cache = CacheManager(Path.home() / ".cache")
        >>> settings = {"criteria": {"phash": {"hash_size": 16}}}
        >>> hash_val = compute_phash('/path/to/img.jpg', settings=settings, cache_manager=cache)
        >>> print(hash_val)  # e.g., 'a1b2c3d4e5f67890'
        'a1b2c3d4e5f67890'

    Note:
        - pHash is robust to minor edits like compression, resizing, or brightness changes.
        - For batch processing, use compute_phash_batch.
        - Logs computation and cache hits via logger.info/debug.
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

    key = f"{image_path}:phash"

    # Check cache
    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Cache hit for pHash: {key}")
            return cached_hash

    try:
        with Image.open(path) as img:
            # imagehash.phash handles grayscale conversion and resizing internally
            # (resizes to hash_size*8 x hash_size*8, applies DCT, thresholds)
            phash_obj = imagehash.phash(img, hash_size=effective_hash_size)
            hash_str = str(phash_obj)

        if len(hash_str) != 16:
            raise SimilarityError(f"Computed hash has invalid length {len(hash_str)}, expected 16")

        # Cache the result
        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)  # 1 day TTL
            logger.debug(f"Cached pHash for {key}")

        # Changed to DEBUG to reduce terminal clutter in normal runs;
        # enable DEBUG logging (e.g., via --log-level=DEBUG) to see per-file pHash computations during scans
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
    cache_manager: Optional[CacheManager] = None
) -> str:
    """
    Compute a color-aware perceptual hash by averaging pHashes of RGB channels.

    Splits the image into R, G, B channels, computes pHash for each, converts to integers,
    averages them, and returns a 64-bit hex string. This provides some color sensitivity
    compared to standard grayscale pHash. Cache key: f"{image_path}:color_phash".

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        cache_manager (Optional[CacheManager]): Optional cache manager.

    Returns:
        str: 16-character hexadecimal hash string.

    Raises:
        InvalidImageError: For invalid images.
        SimilarityError: For computation errors.
        ValueError: For invalid parameters.

    Example:
        >>> color_hash = compute_color_phash('/path/to/color_img.jpg')
        >>> print(color_hash)
        'fedcba9876543210'

    Note:
        - Converts non-RGB images to RGB.
        - Averaging may lose some precision; suitable for PoC color similarity.
        - Logs via logger.info.
    """
    if hash_size < 4 or hash_size > 64:
        raise SimilarityError(f"hash_size must be between 4 and 64, got {hash_size}")

    effective_hash_size = hash_size
    if settings and "criteria" in settings and "phash" in settings["criteria"]:
        effective_hash_size = settings["criteria"]["phash"].get("hash_size", hash_size)

    path = Path(image_path)
    if not path.is_file():
        raise InvalidImageError(image_path, "File does not exist or is not a file")

    key = f"{image_path}:color_phash"

    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Cache hit for color pHash: {key}")
            return cached_hash

    try:
        with Image.open(path) as img:
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

        if len(hash_str) != 16:
            raise SimilarityError(f"Color hash has invalid length {len(hash_str)}")

        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)
            logger.debug(f"Cached color pHash for {key}")

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
    settings: Optional[Dict] = None
) -> List[Group]:
    """
    Find groups of visually similar images using pHash Hamming distances.

    Performs brute-force clustering: computes pairwise distances and uses union-find
    to group images where any chain of distances <= threshold (transitive similarity).
    Input dicts should have 'path' (str) and 'hash' (str) keys. Outputs groups of 2+ paths.
    Threshold defaults to settings['similarity']['phash_threshold'] or 10.

    Args:
        hashes (List[Dict[str, str]]): List of image records, e.g.,
            [{'path': '/img1.jpg', 'hash': 'a1b2c3d4e5f67890'}, ...].
            Typically from DB query (image_hashes table joined with images).
        threshold (Optional[int]): Maximum Hamming distance for similarity (0-64).
            Lower values = stricter matching (e.g., 5 for near-identical).
        settings (Optional[Dict]): Settings dict to override threshold via
            settings['similarity']['phash_threshold'] (default 10).

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - images (List[ImageData]): ImageData objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (Stats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].images[0].score → 0.95 (95% similarity)

    Raises:
        ValueError: If hashes list is empty, invalid dict structure, or invalid hashes.
        SimilarityError: If grouping fails (e.g., too many items for brute-force; warn for >1000).

    Example:
        >>> sample_hashes = [
        ...     {'path': '/img1.jpg', 'hash': '0000000000000000'},
        ...     {'path': '/img2.jpg', 'hash': '0000000000000001'},
        ...     {'path': '/img3.jpg', 'hash': '1111111111111111'}
        ... ]
        >>> groups = find_similar_phash(sample_hashes, threshold=1)
        >>> print(groups)  # [['/img1.jpg', '/img2.jpg']]
        [['/img1.jpg', '/img2.jpg']]

    Note:
        - Brute-force O(n^2); suitable for PoC (<1000 images). For larger, use LSH/ANN.
        - Logs number of groups via logger.info.
        - Threshold tuning: Test empirically (0=exact, 10~similar, 20~loose).
    """
    if not hashes:
        raise ValueError("hashes list cannot be empty")

    n = len(hashes)
    if n > 1000:
        logger.warning(f"Large input ({n} images) for brute-force grouping; consider indexing for scale")

    # Validate input
    for i, h in enumerate(hashes):
        if not isinstance(h, dict) or 'path' not in h or 'hash' not in h:
            raise ValueError(f"Invalid dict at index {i}: missing 'path' or 'hash'")
        if not isinstance(h['path'], str) or not h['path']:
            raise ValueError(f"Empty path at index {i}")
        if len(h['hash']) != 16:
            raise ValueError(f"Invalid hash length at index {i}: {len(h['hash'])}")

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('phash_threshold', 10)
        else:
            threshold = 10
    if threshold < 0 or threshold > 64:
        raise ValueError(f"Threshold must be 0-64, got {threshold}")

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

    # Compute pairwise distances
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
        images: List[ImageData] = []
        valid_count = 0
        for h_dict in group_hashes:
            try:
                dist = hamming_distance(ref_hash, h_dict['hash'])
                score = 1.0 - (dist / 64.0)
                meta = get_image_metadata(h_dict['path'])
                img_data = ImageData(
                    path=h_dict['path'],
                    size=meta['size'],
                    resolution=meta['resolution'],
                    mod_date=meta['mod_date'],
                    score=score
                )
                images.append(img_data)
                valid_count += 1
            except Exception as e:
                logger.warning(f"Failed to create ImageData for {h_dict['path']}: {e}")
                continue
        if valid_count < 2:
            continue
        stats = compute_group_stats(images)
        group_obj = Group(
            id=group_id,
            images=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group_obj)
        group_id += 1

    logger.info(f"Found {len(groups)} similar pHash groups (threshold={threshold}, n={n})")
    return groups


def compute_phash_batch(
    paths: List[str],
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None,
    update_cache: bool = True
) -> Dict[str, Optional[str]]:
    """
    Batch compute pHashes for a list of image paths, with progress logging.

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. Cache is used/updated if provided and update_cache=True.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        settings (Optional[Dict]): Settings for overrides.
        cache_manager (Optional[CacheManager]): Cache instance.
        update_cache (bool): If True and cache_manager provided, update cache on misses.

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

    effective_cache = cache_manager if update_cache else None
    results: Dict[str, Optional[str]] = {}
    total = len(paths)

    logger.info(f"Starting batch pHash computation for {total} images (size={hash_size})")

    for i, path in enumerate(paths, 1):
        try:
            hash_val = compute_phash(path, hash_size, settings, effective_cache)
            results[path] = hash_val
        except Exception as e:
            logger.warning(f"Batch failed for {path} ({i}/{total}): {e}")
            results[path] = None

        # Log progress every 50 files or at completion to reduce verbosity
        if i % 50 == 0 or i == total:
            progress_pct = (i / total) * 100
            logger.info(f"Batch progress: {i}/{total} ({progress_pct:.1f}%)")

    success_count = sum(1 for v in results.values() if v is not None)
    logger.info(f"Batch complete: {success_count}/{total} successful")

    return results


def compute_whash(
    image_path: str,
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None
) -> str:
    """
    Compute wavelet hash (wHash) for an image using Discrete Wavelet Transform (DWT).

    Loads the image with Pillow, computes the hash using imagehash.whash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching to avoid recomputation.
    The settings dict is primarily for future use (e.g., threshold), but hash_size can
    be overridden via settings['criteria']['whash']['hash_size'] if provided.

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Higher values
            increase precision but computation time. Must be >=4 and <=64.
        mode (str): DWT mode for edge handling (default 'constant'; options: 'constant', 'symmetric', 'periodic', 'reflect', 'smooth').
        wavelet (str): Wavelet family name (default 'db1'; e.g., 'db1', 'haar', 'db4' via PyWavelets).
        settings (Optional[Dict]): Optional settings dictionary from core.settings_schema.
            If provided and contains 'criteria']['whash']['hash_size', overrides hash_size.
            Also used for logging context.
        cache_manager (Optional[CacheManager]): Optional CacheManager instance for caching.
            If provided, checks cache key f"{image_path}:whash" before computing and stores result.

    Returns:
        str: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890').

    Raises:
        InvalidImageError: If the image file does not exist, is not a valid image, or has an
            unsupported format (e.g., PIL.UnidentifiedImageError). Includes path and details.
        SimilarityError: For general computation failures (e.g., invalid hash_size, wavelet errors, memory issues).
        IOError: For file access errors (e.g., permissions).
        ValueError: If hash_size is invalid or resulting hash is not 16 characters.

    Example:
        >>> from pk_py_lib.core.cache import CacheManager
        >>> cache = CacheManager(Path.home() / ".cache")
        >>> settings = {"criteria": {"whash": {"hash_size": 16}}}
        >>> hash_val = compute_whash('/path/to/img.jpg', mode='symmetric', wavelet='haar', settings=settings, cache_manager=cache)
        >>> print(hash_val)  # e.g., 'a1b2c3d4e5f67890'
        'a1b2c3d4e5f67890'

    Note:
        - wHash is robust to scale, rotation, and translation changes.
        - Requires PyWavelets for DWT computation.
        - For batch processing, use compute_whash_batch.
        - Logs computation and cache hits via logger.info/debug.
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

    key = f"{image_path}:whash"

    # Check cache
    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Cache hit for wHash: {key}")
            return cached_hash

    try:
        with Image.open(path) as img:
            # imagehash.whash handles grayscale, resizing, DWT, thresholding
            whash_obj = imagehash.whash(img, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
            hash_str = str(whash_obj)

        if len(hash_str) != 16:
            raise SimilarityError(f"Computed hash has invalid length {len(hash_str)}, expected 16")

        # Cache the result
        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)  # 1 day TTL
            logger.debug(f"Cached wHash for {key}")

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
    cache_manager: Optional[CacheManager] = None
) -> str:
    """
    Compute a color-aware wavelet hash by averaging wHashes of RGB channels.

    Splits the image into R, G, B channels, computes wHash for each, converts to integers,
    averages them, and returns a 64-bit hex string. This provides some color sensitivity
    compared to standard grayscale wHash. Cache key: f"{image_path}:color_whash".

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        cache_manager (Optional[CacheManager]): Optional cache manager.

    Returns:
        str: 16-character hexadecimal hash string.

    Raises:
        InvalidImageError: For invalid images.
        SimilarityError: For computation errors.
        ValueError: For invalid parameters.

    Example:
        >>> color_hash = compute_color_whash('/path/to/color_img.jpg', wavelet='haar')
        >>> print(color_hash)
        'fedcba9876543210'

    Note:
        - Converts non-RGB images to RGB.
        - Averaging may lose some precision; suitable for PoC color similarity.
        - Logs via logger.info.
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

    key = f"{image_path}:color_whash"

    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Cache hit for color wHash: {key}")
            return cached_hash

    try:
        with Image.open(path) as img:
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

        if len(hash_str) != 16:
            raise SimilarityError(f"Color wHash has invalid length {len(hash_str)}")

        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)
            logger.debug(f"Cached color wHash for {key}")

        logger.info(f"Computed color wHash for {image_path} (size={effective_hash_size}, mode={mode}, wavelet={wavelet}): {hash_str}")
        return hash_str

    except Exception as e:
        logger.error(f"Color wHash failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"Color wHash computation failed: {e}") from e


def find_similar_whash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None
) -> List[Group]:
    """
    Find groups of visually similar images using wHash Hamming distances.

    Performs brute-force clustering: computes pairwise distances and uses union-find
    to group images where any chain of distances <= threshold (transitive similarity).
    Input dicts should have 'path' (str) and 'hash' (str) keys. Outputs groups of 2+ paths.
    Threshold defaults to settings['similarity']['whash_threshold'] or 12.

    Args:
        hashes (List[Dict[str, str]]): List of image records, e.g.,
            [{'path': '/img1.jpg', 'hash': 'a1b2c3d4e5f67890'}, ...].
            Typically from DB query (image_hashes table joined with images, algorithm='whash').
        threshold (Optional[int]): Maximum Hamming distance for similarity (0-64).
            Lower values = stricter matching (e.g., 8 for near-identical).
        settings (Optional[Dict]): Settings dict to override threshold via
            settings['similarity']['whash_threshold'] (default 12).

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - images (List[ImageData]): ImageData objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (Stats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].images[0].score → 0.95 (95% similarity)

    Raises:
        ValueError: If hashes list is empty, invalid dict structure, or invalid hashes.
        SimilarityError: If grouping fails (e.g., too many items for brute-force; warn for >1000).

    Example:
        >>> sample_hashes = [
        ...     {'path': '/img1.jpg', 'hash': '0000000000000000'},
        ...     {'path': '/img2.jpg', 'hash': '0000000000000001'},
        ...     {'path': '/img3.jpg', 'hash': '1111111111111111'}
        ... ]
        >>> groups = find_similar_whash(sample_hashes, threshold=1)
        >>> print(groups)  # [['/img1.jpg', '/img2.jpg']]
        [['/img1.jpg', '/img2.jpg']]

    Note:
        - Brute-force O(n^2); suitable for PoC (<1000 images). For larger, use LSH/ANN.
        - Logs number of groups via logger.info.
        - Threshold tuning: Test empirically (0=exact, 12~similar, 20~loose for wHash).
    """
    if not hashes:
        raise ValueError("hashes list cannot be empty")

    n = len(hashes)
    if n > 1000:
        logger.warning(f"Large input ({n} images) for brute-force grouping; consider indexing for scale")

    # Validate input
    for i, h in enumerate(hashes):
        if not isinstance(h, dict) or 'path' not in h or 'hash' not in h:
            raise ValueError(f"Invalid dict at index {i}: missing 'path' or 'hash'")
        if not isinstance(h['path'], str) or not h['path']:
            raise ValueError(f"Empty path at index {i}")
        if len(h['hash']) != 16:
            raise ValueError(f"Invalid hash length at index {i}: {len(h['hash'])}")

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('whash_threshold', 12)
        else:
            threshold = 12
    if threshold < 0 or threshold > 64:
        raise ValueError(f"Threshold must be 0-64, got {threshold}")

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

    # Compute pairwise distances
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
        images: List[ImageData] = []
        valid_count = 0
        for h_dict in group_hashes:
            try:
                dist = hamming_distance(ref_hash, h_dict['hash'])
                score = 1.0 - (dist / 64.0)
                meta = get_image_metadata(h_dict['path'])
                img_data = ImageData(
                    path=h_dict['path'],
                    size=meta['size'],
                    resolution=meta['resolution'],
                    mod_date=meta['mod_date'],
                    score=score
                )
                images.append(img_data)
                valid_count += 1
            except Exception as e:
                logger.warning(f"Failed to create ImageData for {h_dict['path']}: {e}")
                continue
        if valid_count < 2:
            continue
        stats = compute_group_stats(images)
        group_obj = Group(
            id=group_id,
            images=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group_obj)
        group_id += 1

    logger.info(f"Found {len(groups)} similar wHash groups (threshold={threshold}, n={n})")
    return groups


def compute_whash_batch(
    paths: List[str],
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None,
    update_cache: bool = True
) -> Dict[str, Optional[str]]:
    """
    Batch compute wHashes for a list of image paths, with progress logging.

    Processes paths sequentially (PoC; no parallelism). Skips failures but logs warnings.
    Results include None for failed paths. Cache is used/updated if provided and update_cache=True.

    Args:
        paths (List[str]): List of image paths to process.
        hash_size (int): Default hash size (overridable via settings).
        mode (str): DWT mode (default 'constant').
        wavelet (str): Wavelet family (default 'db1').
        settings (Optional[Dict]): Settings for overrides.
        cache_manager (Optional[CacheManager]): Cache instance.
        update_cache (bool): If True and cache_manager provided, update cache on misses.

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
    """
    if not paths:
        raise ValueError("paths list cannot be empty")

    effective_cache = cache_manager if update_cache else None
    results: Dict[str, Optional[str]] = {}
    total = len(paths)

    logger.info(f"Starting batch wHash computation for {total} images (size={hash_size}, mode={mode}, wavelet={wavelet})")

    for i, path in enumerate(paths, 1):
        try:
            hash_val = compute_whash(path, hash_size, mode, wavelet, settings, effective_cache)
            results[path] = hash_val
        except Exception as e:
            logger.warning(f"Batch failed for {path} ({i}/{total}): {e}")
            results[path] = None

        # Log progress every 50 files or at completion to reduce verbosity
        if i % 50 == 0 or i == total:
            progress_pct = (i / total) * 100
            logger.info(f"Batch progress: {i}/{total} ({progress_pct:.1f}%)")

    success_count = sum(1 for v in results.values() if v is not None)
    logger.info(f"Batch complete: {success_count}/{total} successful")

    return results


def find_exact_duplicates(
    hashes: List[Dict[str, str]]
) -> List[Group]:
    """
    Find groups of exact duplicate images based on content hash equality.

    Groups paths with identical hash values. Fetches metadata for each, sets score=1.0
    for all, and computes stats. Suitable for BLAKE3 or SHA-256 hashes.

    Args:
        hashes (List[Dict[str, str]]): List of {'path': str, 'hash': str} where 'hash' is
            content hash (e.g., BLAKE3 hex). From DB or computed.

    Returns:
        List[Group]: List of duplicate groups with ImageData (score=1.0), stats.

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

        images: List[ImageData] = []
        for path in paths:
            try:
                meta = get_image_metadata(path)
                score = 1.0
                img_data = ImageData(
                    path=path,
                    size=meta['size'],
                    resolution=meta['resolution'],
                    mod_date=meta['mod_date'],
                    score=score
                )
                images.append(img_data)
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
            images=images,
            stats=stats,
            ref_path=ref_path
        )
        groups.append(group)
        group_id += 1

    logger.info(f"Found {len(groups)} exact duplicate groups (n={len(hashes)})")
    return groups


def find_similar_images(
    hashes: List[Dict[str, str]],
    algorithm: str = "phash",
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None
) -> List[Group]:
    """
    Dispatcher for finding similar or exact duplicate image groups.

    Routes to exact, pHash, or wHash. For 'exact', ignores threshold/settings.
    Returns enriched Group objects with metadata and normalized scores.

    Args:
        hashes (List[Dict[str, str]]): List of {'path': str, 'hash': str} records.
            For 'exact': content hash (BLAKE3/SHA-256). For perceptual: phash/whash.
        algorithm (str): 'exact', 'phash', or 'whash' (default 'phash').
        threshold (Optional[int]): Max distance for perceptual (ignored for 'exact').
        settings (Optional[Dict]): For perceptual threshold override.

    Returns:
        List[Group]: List of groups.

    Raises:
        ValueError: Unsupported algorithm or invalid input.

    Example:
        >>> groups = find_similar_images(hashes=sample_hashes, algorithm='exact')
        >>> print(len(groups))
        1
    """
    if algorithm == "exact":
        return find_exact_duplicates(hashes)
    elif algorithm == "phash":
        return find_similar_phash(hashes, threshold, settings)
    elif algorithm == "whash":
        return find_similar_whash(hashes, threshold, settings)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


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
        sample = [{'path': 'a.jpg', 'hash': '0000'}, {'path': 'b.jpg', 'hash': '0000'}]
        groups = find_exact_duplicates(sample)
        print(f"Exact duplicates: {len(groups)} groups")
    except Exception as e:
        print(f"Exact test error: {e}")
    
    print("Verification complete.")