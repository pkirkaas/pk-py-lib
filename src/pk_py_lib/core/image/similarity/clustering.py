"""
src/pk_py_lib/core/image/similarity/clustering.py

Clustering and similarity comparison algorithms for grouping similar/duplicate images.
Includes exact duplicate detection, perceptual similarity grouping, and multi-phase integration.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from pk_py_lib.core.filesystem.identity import compute_xxh3
from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.models import FileItem
from pk_py_lib.gui.dialog_models import Group  # Group still defined in dialog_models (List-based)

from ...api.response import ApiResponse, ErrorCode
from .hashing import compute_similarity_hash_batch
from .metadata import compute_group_stats, format_timestamp, get_image_metadata, get_image_quality_score
from .types import ExactDuplicateSet, SimilarityError
from .validation import hamming_distance, validate_and_normalize_hash, validate_threshold

logger = get_logger(__name__)


def find_similar_phash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity',
    algorithm: str = 'phash'
) -> List[Group]:
    """
    Find groups of visually similar images using pHash Hamming distances.

    Performs clustering using brute-force pairwise distances and union-find
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
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.
        search_type (str): 'similarity' to ensure full computations.
        algorithm (str): Algorithm name for logging (default 'phash').

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - items (List[FileItem]): FileItem objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (GroupStats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].items[0].score → 0.95 (95% similarity)

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

    Note:
        - Brute-force O(n^2) for all sizes; for large n (>1000), logs warning.
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

        # Validate and normalize hash
        hash_str = h['hash']
        if not isinstance(hash_str, str) or not hash_str:
            raise ValueError(f"Empty or invalid hash at index {i}")

        # Normalize hash using validation utility
        h['hash'] = validate_and_normalize_hash(hash_str, expected_length=16, index=i)

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('phash_threshold', 10)
        else:
            threshold = 10
    validate_threshold(threshold, algorithm)

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
                meta = get_image_metadata(h_dict['path'], search_type=search_type)
                quality_score, quality_algorithm = get_image_quality_score(
                    h_dict['path'], quality_evaluator, flat_cache_manager, search_type=search_type
                )

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


def find_similar_whash(
    hashes: List[Dict[str, str]],
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity',
    algorithm: str = 'whash'
) -> List[Group]:
    """
    Find groups of visually similar images using wHash Hamming distances.

    Performs clustering using brute-force pairwise distances and union-find
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
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.
        search_type (str): 'similarity' to ensure full computations.
        algorithm (str): Algorithm name for logging (default 'whash').

    Returns:
        List[Group]: List of groups, each a Group with:
        - id (int): Unique group identifier
        - items (List[FileItem]): FileItem objects with path, metadata, and normalized score (1 - hamming_dist / 64)
        - stats (GroupStats): Aggregated min/max/avg score and total_size
        - ref_path (str): Path to reference image
        Singletons omitted; images sorted by path.
        Example: groups[0].items[0].score → 0.95 (95% similarity)

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

    Note:
        - Brute-force O(n^2) for all sizes; for large n (>1000), logs warning.
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

        # Validate and normalize hash
        hash_str = h['hash']
        if not isinstance(hash_str, str) or not hash_str:
            raise ValueError(f"Empty or invalid hash at index {i}")

        # Normalize hash using validation utility
        h['hash'] = validate_and_normalize_hash(hash_str, expected_length=16, index=i)

    # Get threshold
    if threshold is None:
        if settings and 'similarity' in settings:
            threshold = settings['similarity'].get('whash_threshold', 12)
        else:
            threshold = 12
    validate_threshold(threshold, algorithm)

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
                # For exact duplicates, fetch only file stats without image loading
                stat = os.stat(h_dict['path'])
                size = stat.st_size
                mod_ts = stat.st_mtime
                mod_date = format_timestamp(mod_ts)
                resolution = "Unknown"  # No image loading for duplicates
                quality_score, quality_algorithm = get_image_quality_score(
                    h_dict['path'], quality_evaluator, flat_cache_manager, search_type=search_type
                )

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
        paths (List[str]): List of absolute file paths to process.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager for caching
            XXH3 computations. If provided, uses get_hashes to compute/retrieve 'xxh3' for all paths.

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
    """
    Find groups of exact duplicate images based on content hash equality.

    Groups paths with identical hash values. Fetches metadata for each, sets score=1.0
    for all, and computes stats. Suitable for BLAKE3 or SHA-256 hashes.

    Args:
        hashes (List[Dict[str, str]]): List of {'path': str, 'hash': str} where 'hash' is
            content hash (e.g., BLAKE3 hex). From DB or computed.
        flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
            to pass to quality evaluators for caching.
        search_type (str): 'similarity' or 'duplicate' (affects quality scoring).

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
                meta = get_image_metadata(path, search_type=search_type)
                score = 1.0
                if search_type == 'duplicate':
                    quality_score = 1.0
                    quality_algorithm = None
                else:
                    quality_score, quality_algorithm = get_image_quality_score(
                        path, quality_evaluator, flat_cache_manager, search_type=search_type
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
    search_type: str = 'similarity',
    return_response: bool = False
) -> Union[List[Group], ApiResponse]:
    """
    Dispatcher for finding similar or exact duplicate image groups using paths.

    This simplified function uses the new phase-based architecture to process
    images through 4 distinct phases: algorithm resolution, exact duplicate
    detection, perceptual hash computation, and similarity clustering.
    Can return either the groups directly (backward compatibility) or an ApiResponse object.

    Args:
        paths (List[str]): List of absolute file paths to process.
        algorithm (Optional[str]): 'exact', 'phash', or 'whash' (default from settings or 'phash').
        threshold (Optional[int]): Max Hamming distance for perceptual clustering (ignored for 'exact').
        settings (Optional[Dict]): For algorithm selection and threshold overrides.
        flat_cache_manager (Optional[FlatCacheManager]): For caching all hash computations and metadata.
        search_type (str): 'similarity' or 'duplicate' (affects computations, e.g., skips perceptual in duplicate mode).
        return_response (bool): If True, returns ApiResponse object instead of groups list.

    Returns:
        Union[List[Group], ApiResponse]: Enriched groups with FileItem (scores normalized, exact_set_id set),
            or ApiResponse object if return_response=True.

    Raises:
        ValueError: Invalid algorithm, empty paths, or computation failures.
        SimilarityError: For hash or clustering errors.

    Example:
        >>> paths = ["/img1.jpg", "/img2.jpg", "/unique.jpg"]
        >>> # Traditional usage (backward compatible)
        >>> groups = find_similar_images(paths, algorithm='phash', threshold=10)
        >>> print(len(groups))
        1
        >>> # New ApiResponse usage
        >>> response = find_similar_images(paths, return_response=True)
        >>> if response.success:
        ...     print(f"Found {len(response.data['similarity_groups'])} groups")
        Found 1 groups
    """
    try:
        from .phases import PhaseContext, execute_all_phases

        # Validate input
        if not paths:
            if return_response:
                return ApiResponse.error_response(
                    ErrorCode.INVALID_INPUT,
                    "paths list cannot be empty"
                )
            raise ValueError("paths list cannot be empty")

        # Get initial cache stats if available
        initial_stats = None
        if flat_cache_manager and hasattr(flat_cache_manager, '_enhanced_cache'):
            stats_response = flat_cache_manager._enhanced_cache.get_stats()
            if stats_response.success:
                initial_stats = stats_response.data

        start_time = time.time()

        # Create phase context with all input parameters
        context = PhaseContext(
            image_paths=paths,
            algorithm=algorithm,
            threshold=threshold,
            settings=settings,
            flat_cache_manager=flat_cache_manager,
            search_type=search_type
        )

        # Execute all phases through the orchestrator
        final_context = execute_all_phases(context)

        # Prepare response data
        similarity_groups = final_context.final_groups
        duplicate_groups = final_context.exact_sets

        # Get final cache stats and calculate improvements
        cache_metadata = {}
        if flat_cache_manager and hasattr(flat_cache_manager, '_enhanced_cache'):
            stats_response = flat_cache_manager._enhanced_cache.get_stats()
            if stats_response.success:
                final_stats = stats_response.data
                cache_metadata = {
                    'cache_stats': final_stats,
                    'cache_improvement': {
                        'hits': final_stats.get('hit_count', 0) - (initial_stats.get('hit_count', 0) if initial_stats else 0),
                        'misses': final_stats.get('miss_count', 0) - (initial_stats.get('miss_count', 0) if initial_stats else 0),
                        'hit_rate': final_stats.get('hit_rate', 0.0)
                    }
                }

        processing_time = time.time() - start_time

        response_data = {
            'similarity_groups': similarity_groups,
            'duplicate_groups': duplicate_groups,
            'total_images': len(paths),
            'similarity_groups_found': len(similarity_groups),
            'duplicate_groups_found': len(duplicate_groups)
        }

        if return_response:
            # Determine if we have partial success
            has_warnings = len(final_context.warnings) > 0
            base_metadata = {
                'algorithm': final_context.algorithm,
                'threshold': final_context.threshold,
                'search_type': search_type,
                'processing_time': processing_time,
                **cache_metadata
            }

            if has_warnings:
                response = ApiResponse.partial_success_response(
                    data=response_data,
                    warnings=final_context.warnings,
                    metadata=base_metadata
                )
            else:
                response = ApiResponse.success_response(
                    data=response_data,
                    metadata=base_metadata
                )
            return response

        # Return the final groups from the completed context (backward compatibility)
        return final_context.final_groups

    except Exception as e:
        if return_response:
            return ApiResponse.from_exception(
                e,
                ErrorCode.SIMILARITY_DETECTION_FAILED,
                f"Similarity detection failed: {e}",
                metadata={
                    'algorithm': algorithm,
                    'search_type': search_type,
                    'total_images': len(paths) if paths else 0
                }
            )

        # Re-raise for backward compatibility
        raise
