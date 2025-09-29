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
from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheEntry, FlatCacheDBError
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
from pk_py_lib.core.image.quality.base import ImageQualityEvaluator

try:
    from datasketch import MinHash, MinHashLSH
    LSH_AVAILABLE = True
except ImportError:
    LSH_AVAILABLE = False


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

def get_image_quality_score(
    path: str,
    evaluator: Optional[ImageQualityEvaluator],
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> tuple[Optional[float], Optional[str]]:
    """
    Compute the image quality score using the provided evaluator.

    If the evaluator is None (quality evaluation disabled), returns (None, None).
    If evaluation fails, logs an error and returns (None, evaluator.name).

    Args:
        path (str): Path to the image file.
        evaluator (Optional[ImageQualityEvaluator]): Instantiated quality evaluator or None.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to the evaluator for cache lookup/storage.

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
    if evaluator is None:
        return None, None

    try:
        score = evaluator.evaluate(path, flat_cache_manager=flat_cache_manager)
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
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> str:
    """
    Compute perceptual hash (pHash) for an image using Discrete Cosine Transform (DCT).

    Loads the image with Pillow, computes the hash using imagehash.phash, and returns
    a 64-bit hexadecimal string (16 characters). Supports caching via CacheManager (legacy)
    or FlatCacheManager (new, file-stat validated).

    Args:
        image_path (str): Absolute or relative path to the image file (e.g., '/path/to/img.jpg').
        hash_size (int): Size of the hash matrix (default 8, yielding 64 bits). Must be >=4 and <=64.
        settings (Optional[Dict]): Optional settings dictionary. Used to override hash_size.
        cache_manager (Optional[CacheManager]): Optional legacy CacheManager instance.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'phash' field before computing and stores result.

    Returns:
        str: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890').

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

    # --- 1. Check Flat Cache (Priority) ---
    if flat_cache_manager:
        try:
            entry = flat_cache_manager.get_entry(image_path)
            if entry and entry.phash:
                logger.debug(f"Flat cache hit for pHash on {image_path}")
                return entry.phash
            # If entry exists but hash is missing, we proceed to compute and update the entry later.
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during pHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache pHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- 2. Check Legacy Cache ---
    if cache_manager:
        key = f"{image_path}:phash"
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Legacy cache hit for pHash: {key}")
            return cached_hash

    # --- 3. Compute Hash ---
    hash_str = None
    try:
        with Image.open(path) as img:
            phash_obj = imagehash.phash(img, hash_size=effective_hash_size)
            hash_str = str(phash_obj)

        if len(hash_str) != 16:
            raise SimilarityError(f"Computed hash has invalid length {len(hash_str)}, expected 16")

        # --- 4. Cache the result ---
        if flat_cache_manager:
            try:
                # Get current entry or create a new one with file stats
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    # If get_entry failed validation or was missing, create a new base entry
                    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
                    current_entry = FlatCacheEntry(
                        file=image_path, size=size, mod_date=mtime, file_inode=inode, file_device=device
                    )
                
                current_entry.phash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Flat cache updated for pHash on {image_path}")
            except Exception as e:
                logger.warning(f"Failed to update flat cache for pHash on {image_path}: {e}")

        if cache_manager:
            key = f"{image_path}:phash"
            cache_manager.set_hash(key, hash_str, ttl=86400)  # 1 day TTL
            logger.debug(f"Legacy cache updated for pHash: {key}")

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
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> str:
    """
    Compute a color-aware perceptual hash by averaging pHashes of RGB channels.

    Splits the image into R, G, B channels, computes pHash for each, converts to integers,
    averages them, and returns a 64-bit hex string. Supports caching via CacheManager (legacy)
    or FlatCacheManager (new, file-stat validated). Cache key: f"{image_path}:color_phash".

    Args:
        image_path (str): Path to the image file.
        hash_size (int): Size of the hash matrix (default 8).
        settings (Optional[Dict]): Optional settings (overrides hash_size if provided).
        cache_manager (Optional[CacheManager]): Optional legacy cache manager.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance.
            If provided, checks cache entry's 'color_phash' field before computing and stores result.

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

    # --- 1. Check Flat Cache (Priority) ---
    if flat_cache_manager:
        try:
            entry = flat_cache_manager.get_entry(image_path)
            if entry and entry.color_phash:
                logger.debug(f"Flat cache hit for color pHash on {image_path}")
                return entry.color_phash
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during color pHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache color pHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- 2. Check Legacy Cache ---
    key = f"{image_path}:color_phash"
    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Legacy cache hit for color pHash: {key}")
            return cached_hash

    # --- 3. Compute Hash ---
    hash_str = None
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

        # --- 4. Cache the result ---
        if flat_cache_manager:
            try:
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
                    current_entry = FlatCacheEntry(
                        file=image_path, size=size, mod_date=mtime, file_inode=inode, file_device=device
                    )
                
                current_entry.color_phash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Flat cache updated for color pHash on {image_path}")
            except Exception as e:
                logger.warning(f"Failed to update flat cache for color pHash on {image_path}: {e}")

        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)
            logger.debug(f"Legacy cache updated for color pHash: {key}")

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
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> List[Group]:
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
        - Brute-force O(n^2); LSH approximates for scale (PoC; tune num_perm later via settings).
        - Logs LSH usage, candidate counts, fallbacks via logger.info/warning.
        - Threshold tuning: Test empirically (0=exact, 10~similar, 20~loose).
        - Requires datasketch for LSH; falls back gracefully.
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

    use_lsh = n > 1000 and LSH_AVAILABLE
    if use_lsh:
        try:
            logger.info(f"Using LSH for n={n}")
            similarity_settings = settings.get('similarity', {}) if settings else {}
            num_perm = similarity_settings.get('lsh_num_perm', 128)
            lsh_threshold = similarity_settings.get('lsh_threshold')
            if lsh_threshold is None:
                lsh_threshold = 1 - threshold / 64.0
            logger.debug(f"LSH params: num_perm={num_perm}, threshold={lsh_threshold}")
            lsh = MinHashLSH(threshold=lsh_threshold, num_perm=num_perm)
            minhases = {}
            for h in hashes:
                hash_int = int(h['hash'], 16)
                m = MinHash(num_perm=num_perm)
                for i in range(64):
                    if hash_int & (1 << i):
                        m.update(str(i).encode('utf-8'))  # Fixed datasketch MinHash.update (bytes) and insert order.
                minhases[h['path']] = m
                lsh.insert(h['path'], m)  # Fixed datasketch MinHash.update (bytes) and insert order.

            from collections import defaultdict
            candidates = defaultdict(set)
            for path, m in minhases.items():
                neighbors = lsh.query(m)
                for neigh in neighbors:
                    if neigh != path:
                        candidates[path].add(neigh)
                        candidates[neigh].add(path)  # Symmetric

            pairs = set()
            for p1 in candidates:
                for p2 in candidates[p1]:
                    if p1 < p2:
                        pairs.add((p1, p2))

            logger.info(f"Found {len(pairs)} candidate pairs")

            # Union on exact distances for candidates
            for p1, p2 in pairs:
                i = path_to_index[p1]
                j = path_to_index[p2]
                try:
                    dist = hamming_distance(hashes[i]['hash'], hashes[j]['hash'])
                    if dist <= threshold:
                        union(i, j)
                except ValueError as e:
                    logger.warning(f"Skipping invalid candidate pair ({p1}, {p2}): {e}")
                    continue

        except Exception as e:
            logger.warning(f"LSH failed: {e}, using brute-force")
            use_lsh = False

    if not use_lsh:
        if n > 1000:
            logger.warning(f"Large input ({n} images) for brute-force grouping; consider indexing for scale")
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
                meta = get_image_metadata(h_dict['path'])
                quality_score, quality_algorithm = get_image_quality_score(h_dict['path'], quality_evaluator, flat_cache_manager)
                
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

    logger.info(f"Found {len(groups)} similar pHash groups (threshold={threshold}, n={n})")
    return groups


def compute_phash_batch(
    paths: List[str],
    hash_size: int = 8,
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
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

    effective_cache = cache_manager if update_cache else None
    results: Dict[str, Optional[str]] = {}
    total = len(paths)

    logger.info(f"Starting batch pHash computation for {total} images (size={hash_size})")

    for i, path in enumerate(paths, 1):
        try:
            hash_val = compute_phash(path, hash_size, settings, effective_cache, flat_cache_manager)
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
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> str:
    """
    Compute wavelet hash (wHash) for an image using Discrete Wavelet Transform (DWT).

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
        str: 16-character hexadecimal hash string (e.g., 'a1b2c3d4e5f67890').

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

    # --- 1. Check Flat Cache (Priority) ---
    if flat_cache_manager:
        try:
            entry = flat_cache_manager.get_entry(image_path)
            if entry and entry.whash:
                logger.debug(f"Flat cache hit for wHash on {image_path}")
                return entry.whash
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during wHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache wHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- 2. Check Legacy Cache ---
    key = f"{image_path}:whash"
    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Legacy cache hit for wHash: {key}")
            return cached_hash

    # --- 3. Compute Hash ---
    hash_str = None
    try:
        with Image.open(path) as img:
            # imagehash.whash handles grayscale, resizing, DWT, thresholding
            whash_obj = imagehash.whash(img, hash_size=effective_hash_size, mode=mode, wavelet=wavelet)
            hash_str = str(whash_obj)

        if len(hash_str) != 16:
            raise SimilarityError(f"Computed hash has invalid length {len(hash_str)}, expected 16")

        # --- 4. Cache the result ---
        if flat_cache_manager:
            try:
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
                    current_entry = FlatCacheEntry(
                        file=image_path, size=size, mod_date=mtime, file_inode=inode, file_device=device
                    )
                
                current_entry.whash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Flat cache updated for wHash on {image_path}")
            except Exception as e:
                logger.warning(f"Failed to update flat cache for wHash on {image_path}: {e}")

        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)  # 1 day TTL
            logger.debug(f"Legacy cache updated for wHash: {key}")

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
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> str:
    """
    Compute a color-aware wavelet hash by averaging wHashes of RGB channels.

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

    # --- 1. Check Flat Cache (Priority) ---
    if flat_cache_manager:
        try:
            entry = flat_cache_manager.get_entry(image_path)
            if entry and entry.color_whash:
                logger.debug(f"Flat cache hit for color wHash on {image_path}")
                return entry.color_whash
        except FlatCacheDBError as e:
            logger.warning(f"Flat cache DB error during color wHash lookup for {image_path}. Falling back to computation. Error: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during flat cache color wHash lookup for {image_path}. Falling back to computation. Error: {e}")

    # --- 2. Check Legacy Cache ---
    key = f"{image_path}:color_whash"
    if cache_manager:
        cached_hash = cache_manager.get_hash(key)
        if cached_hash:
            logger.debug(f"Legacy cache hit for color wHash: {key}")
            return cached_hash

    # --- 3. Compute Hash ---
    hash_str = None
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

        # --- 4. Cache the result ---
        if flat_cache_manager:
            try:
                current_entry = flat_cache_manager.get_entry(image_path)
                if current_entry is None:
                    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
                    current_entry = FlatCacheEntry(
                        file=image_path, size=size, mod_date=mtime, file_inode=inode, file_device=device
                    )
                
                current_entry.color_whash = hash_str
                flat_cache_manager.set_entry(current_entry)
                logger.debug(f"Flat cache updated for color wHash on {image_path}")
            except Exception as e:
                logger.warning(f"Failed to update flat cache for color wHash on {image_path}: {e}")

        if cache_manager:
            cache_manager.set_hash(key, hash_str, ttl=86400)
            logger.debug(f"Legacy cache updated for color wHash: {key}")

        logger.info(f"Computed color wHash for {image_path} (size={effective_hash_size}, mode={mode}, wavelet={wavelet}): {hash_str}")
        return hash_str

    except Exception as e:
        logger.error(f"Color wHash failed for {image_path}: {e}", exception=e)
        raise SimilarityError(f"Color wHash computation failed: {e}") from e


def find_similar_whash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> List[Group]:
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
        - Brute-force O(n^2); LSH approximates for scale (PoC; tune num_perm later via settings).
        - Logs LSH usage, candidate counts, fallbacks via logger.info/warning.
        - Threshold tuning: Test empirically (0=exact, 12~similar, 20~loose for wHash).
        - Requires datasketch for LSH; falls back gracefully.
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

    use_lsh = n > 1000 and LSH_AVAILABLE
    if use_lsh:
        try:
            logger.info(f"Using LSH for n={n}")
            similarity_settings = settings.get('similarity', {}) if settings else {}
            num_perm = similarity_settings.get('lsh_num_perm', 128)
            lsh_threshold = similarity_settings.get('lsh_threshold')
            if lsh_threshold is None:
                lsh_threshold = 1 - threshold / 64.0
            logger.debug(f"LSH params: num_perm={num_perm}, threshold={lsh_threshold}")
            lsh = MinHashLSH(threshold=lsh_threshold, num_perm=num_perm)
            minhases = {}
            for h in hashes:
                hash_int = int(h['hash'], 16)
                m = MinHash(num_perm=num_perm)
                for i in range(64):
                    if hash_int & (1 << i):
                        m.update(str(i).encode('utf-8'))  # Fixed datasketch MinHash.update (bytes) and insert order.
                minhases[h['path']] = m
                lsh.insert(h['path'], m)  # Fixed datasketch MinHash.update (bytes) and insert order.

            from collections import defaultdict
            candidates = defaultdict(set)
            for path, m in minhases.items():
                neighbors = lsh.query(m)
                for neigh in neighbors:
                    if neigh != path:
                        candidates[path].add(neigh)
                        candidates[neigh].add(path)  # Symmetric

            pairs = set()
            for p1 in candidates:
                for p2 in candidates[p1]:
                    if p1 < p2:
                        pairs.add((p1, p2))

            logger.info(f"Found {len(pairs)} candidate pairs")

            # Union on exact distances for candidates
            for p1, p2 in pairs:
                i = path_to_index[p1]
                j = path_to_index[p2]
                try:
                    dist = hamming_distance(hashes[i]['hash'], hashes[j]['hash'])
                    if dist <= threshold:
                        union(i, j)
                except ValueError as e:
                    logger.warning(f"Skipping invalid candidate pair ({p1}, {p2}): {e}")
                    continue

        except Exception as e:
            logger.warning(f"LSH failed: {e}, using brute-force")
            use_lsh = False

    if not use_lsh:
        if n > 1000:
            logger.warning(f"Large input ({n} images) for brute-force grouping; consider indexing for scale")
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
                meta = get_image_metadata(h_dict['path'])
                quality_score, quality_algorithm = get_image_quality_score(h_dict['path'], quality_evaluator, flat_cache_manager)
                
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

    logger.info(f"Found {len(groups)} similar wHash groups (threshold={threshold}, n={n})")
    return groups


def compute_whash_batch(
    paths: List[str],
    hash_size: int = 8,
    mode: str = 'constant',
    wavelet: str = 'db1',
    settings: Optional[Dict] = None,
    cache_manager: Optional[CacheManager] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
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
            hash_val = compute_whash(path, hash_size, mode, wavelet, settings, effective_cache, flat_cache_manager)
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
    hashes: List[Dict[str, str]],
    flat_cache_manager: Optional[FlatCacheManager] = None
) -> List[Group]:
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
    quality_evaluator = get_active_image_quality_evaluator()

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
                meta = get_image_metadata(path)
                score = 1.0
                quality_score, quality_algorithm = get_image_quality_score(path, quality_evaluator, flat_cache_manager)
                
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
    hashes: List[Dict[str, str]],
    algorithm: str = "phash",
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None
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
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to underlying grouping functions for quality caching.

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
        return find_exact_duplicates(hashes, flat_cache_manager)
    elif algorithm == "phash":
        return find_similar_phash(hashes, threshold, settings, flat_cache_manager)
    elif algorithm == "whash":
        return find_similar_whash(hashes, threshold, settings, flat_cache_manager)
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