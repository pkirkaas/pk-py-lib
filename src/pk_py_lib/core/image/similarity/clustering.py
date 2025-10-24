"""
Similarity clustering for image similarity detection.

This module provides clustering algorithms for grouping similar images
based on hash comparisons and similarity thresholds.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from ...logging.logger import get_logger
from .types import HashAlgorithm, SimilarityGroup, ImageMetadata, ExactDuplicateSet


logger = get_logger(__name__)


def find_similar_images(
    image_paths: List[str],
    algorithm: str = "phash",
    threshold: int = 10,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[Any] = None,
    search_type: str = "similarity"
) -> List[SimilarityGroup]:
    """
    Find similar images using the specified algorithm and threshold.

    This is the main entry point for similarity detection. It handles
    both exact duplicate detection and perceptual similarity detection
    based on the algorithm parameter.

    Args:
        image_paths: List of image paths to analyze
        algorithm: Algorithm to use ('phash', 'whash', 'exact')
        threshold: Similarity threshold (0-64 for hash algorithms)
        settings: Optional settings dictionary
        flat_cache_manager: Optional cache manager
        search_type: Search type ('similarity' or 'duplicate')

    Returns:
        List of similarity groups
    """
    start_time = time.time()

    try:
        logger.info(f"Starting similarity detection with {algorithm} algorithm")

        # Handle exact duplicate detection
        if algorithm == "exact":
            return _find_exact_duplicates(image_paths, flat_cache_manager, search_type)

        # Handle perceptual similarity detection
        if algorithm in ["phash", "whash"]:
            return _find_perceptual_similarities(
                image_paths, algorithm, threshold, settings, flat_cache_manager, search_type
            )

        # Unknown algorithm
        raise ValueError(f"Unknown algorithm: {algorithm}")

    except Exception as e:
        logger.error(f"Similarity detection failed: {e}")
        raise
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Similarity detection completed in {elapsed:.2f}s")


def _find_exact_duplicates(
    image_paths: List[str],
    cache_manager: Optional[Any] = None,
    search_type: str = "similarity"
) -> List[SimilarityGroup]:
    """
    Find exact duplicate images using content hashing.

    Args:
        image_paths: List of image paths
        cache_manager: Optional cache manager
        search_type: Search type

    Returns:
        List of similarity groups containing exact duplicates
    """
    logger.info("Finding exact duplicates")

    # Get content hashes for all images
    if cache_manager:
        # Use cache manager to get hashes
        hashes = cache_manager.get_xxh3_batch(image_paths)
    else:
        # Compute hashes directly
        from .hashing import compute_xxh3_batch
        hashes = compute_xxh3_batch(image_paths)

    # Group by hash
    hash_groups = defaultdict(list)
    for path, hash_value in hashes.items():
        if hash_value:  # Only include successfully hashed images
            hash_groups[hash_value].append(path)

    # Create similarity groups for duplicates (groups with 2+ images)
    groups = []
    for hash_value, paths in hash_groups.items():
        if len(paths) > 1:
            # Create metadata for each image
            images_metadata = []
            for path in paths:
                try:
                    metadata = _get_image_metadata_safe(path)
                    images_metadata.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to get metadata for {path}: {e}")

            if images_metadata:
                group = SimilarityGroup(
                    id=len(groups) + 1,
                    reference_image=images_metadata[0],
                    similar_images=images_metadata[1:],
                    similarity_scores={img: 1.0 for img in images_metadata},  # All exact duplicates
                    algorithm_used=HashAlgorithm.XXH3,
                    threshold_used=0  # Exact duplicates have no threshold
                )
                groups.append(group)

    logger.info(f"Found {len(groups)} exact duplicate groups")
    return groups


def _find_perceptual_similarities(
    image_paths: List[str],
    algorithm: str,
    threshold: int,
    settings: Optional[Dict] = None,
    cache_manager: Optional[Any] = None,
    search_type: str = "similarity"
) -> List[SimilarityGroup]:
    """
    Find perceptually similar images using hash comparison.

    Args:
        image_paths: List of image paths
        algorithm: Algorithm to use ('phash' or 'whash')
        threshold: Similarity threshold (0-64)
        settings: Optional settings
        cache_manager: Optional cache manager
        search_type: Search type

    Returns:
        List of similarity groups
    """
    logger.info(f"Finding perceptual similarities with {algorithm} algorithm")

    # Get hashes for all images
    if algorithm == "phash":
        from .hashing import compute_phash_batch
        hash_function = compute_phash_batch
    elif algorithm == "whash":
        from .hashing import compute_whash_batch
        hash_function = compute_whash_batch
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    # Compute hashes
    hashes = hash_function(image_paths, settings=settings, cache_manager=cache_manager)

    # Filter out failed hashes
    valid_hashes = {path: hash_value for path, hash_value in hashes.items() if hash_value}

    if len(valid_hashes) < 2:
        logger.info("Not enough valid hashes for similarity detection")
        return []

    # Find similar pairs
    similar_pairs = _find_similar_pairs(valid_hashes, threshold)

    # Group similar images using union-find
    groups = _cluster_similar_images(similar_pairs, valid_hashes, algorithm, threshold)

    logger.info(f"Found {len(groups)} similarity groups")
    return groups


def _find_similar_pairs(
    hashes: Dict[str, str],
    threshold: int
) -> List[Tuple[str, str]]:
    """
    Find pairs of images that are similar based on hash comparison.

    Args:
        hashes: Dictionary mapping paths to hash values
        threshold: Maximum Hamming distance for similarity

    Returns:
        List of similar image pairs (path1, path2)
    """
    from .hashing import hamming_distance

    similar_pairs = []
    paths = list(hashes.keys())

    # Compare all pairs
    for i, path1 in enumerate(paths):
        for path2 in paths[i + 1:]:
            try:
                distance = hamming_distance(hashes[path1], hashes[path2])
                if distance <= threshold:
                    similar_pairs.append((path1, path2))
            except Exception as e:
                logger.warning(f"Failed to compare {path1} and {path2}: {e}")

    logger.debug(f"Found {len(similar_pairs)} similar pairs")
    return similar_pairs


def _cluster_similar_images(
    similar_pairs: List[Tuple[str, str]],
    hashes: Dict[str, str],
    algorithm: str,
    threshold: int
) -> List[SimilarityGroup]:
    """
    Cluster similar images using union-find algorithm.

    Args:
        similar_pairs: List of similar image pairs
        hashes: Dictionary mapping paths to hash values
        algorithm: Algorithm used
        threshold: Threshold used

    Returns:
        List of similarity groups
    """
    # Union-find data structure
    parent = {path: path for path in hashes.keys()}
    rank = {path: 0 for path in hashes.keys()}

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            if rank[px] < rank[py]:
                parent[px] = py
            elif rank[px] > rank[py]:
                parent[py] = px
            else:
                parent[py] = px
                rank[px] += 1

    # Union similar pairs
    for path1, path2 in similar_pairs:
        union(path1, path2)

    # Group by root parent
    clusters = defaultdict(list)
    for path in hashes.keys():
        root = find(path)
        clusters[root].append(path)

    # Create similarity groups
    groups = []
    for cluster_id, (root_path, cluster_paths) in enumerate(clusters.items()):
        if len(cluster_paths) > 1:  # Only groups with 2+ images
            # Create metadata for each image
            images_metadata = []
            similarity_scores = {}

            for path in cluster_paths:
                try:
                    metadata = _get_image_metadata_safe(path)
                    images_metadata.append(metadata)

                    # Calculate similarity score relative to reference
                    if path != root_path:
                        distance = _hamming_distance_safe(hashes[root_path], hashes[path])
                        similarity = 1.0 - (distance / 64.0) if distance is not None else 0.0
                        similarity_scores[path] = similarity

                except Exception as e:
                    logger.warning(f"Failed to get metadata for {path}: {e}")

            if images_metadata:
                group = SimilarityGroup(
                    id=cluster_id + 1,
                    reference_image=images_metadata[0],
                    similar_images=images_metadata[1:],
                    similarity_scores=similarity_scores,
                    algorithm_used=HashAlgorithm(algorithm.upper()),
                    threshold_used=float(threshold)
                )
                groups.append(group)

    return groups


def _get_image_metadata_safe(image_path: str) -> ImageMetadata:
    """
    Safely get image metadata, with fallback on error.

    Args:
        image_path: Path to the image

    Returns:
        ImageMetadata object
    """
    try:
        from .hashing import get_image_metadata
        return get_image_metadata(image_path)
    except Exception as e:
        logger.warning(f"Failed to get metadata for {image_path}: {e}")
        # Return minimal metadata
        from pathlib import Path
        path_obj = Path(image_path)
        return ImageMetadata(
            path=str(path_obj),
            size=path_obj.stat().st_size,
            width=0,  # Unknown
            height=0,  # Unknown
            format="Unknown",
            mod_time=path_obj.stat().st_mtime
        )


def _hamming_distance_safe(hash1: str, hash2: str) -> Optional[int]:
    """
    Safely calculate Hamming distance.

    Args:
        hash1: First hash
        hash2: Second hash

    Returns:
        Hamming distance or None if calculation fails
    """
    try:
        from .hashing import hamming_distance
        return hamming_distance(hash1, hash2)
    except Exception:
        return None


def detect_exact_duplicates(
    content_hashes: Dict[str, str]
) -> List[ExactDuplicateSet]:
    """
    Detect exact duplicates from content hashes.

    Args:
        content_hashes: Dictionary mapping paths to content hashes

    Returns:
        List of exact duplicate sets
    """
    # Group by hash
    hash_groups = defaultdict(list)
    for path, hash_value in content_hashes.items():
        if hash_value:
            hash_groups[hash_value].append(path)

    # Create duplicate sets for groups with 2+ files
    duplicate_sets = []
    for set_id, (hash_value, paths) in enumerate(hash_groups.items()):
        if len(paths) > 1:
            set_obj = ExactDuplicateSet(
                id=set_id + 1,
                files=paths,
                content_hash=hash_value,
                total_size=sum(Path(p).stat().st_size for p in paths)
            )
            duplicate_sets.append(set_obj)

    return duplicate_sets


def find_similar_phash(
    image_paths: List[str],
    threshold: int = 10,
    settings: Optional[Dict] = None,
    cache_manager: Optional[Any] = None
) -> List[SimilarityGroup]:
    """
    Find similar images using pHash algorithm.

    Args:
        image_paths: List of image paths
        threshold: Similarity threshold (0-64)
        settings: Optional settings
        cache_manager: Optional cache manager

    Returns:
        List of similarity groups
    """
    return find_similar_images(
        image_paths,
        algorithm="phash",
        threshold=threshold,
        settings=settings,
        flat_cache_manager=cache_manager
    )


def find_similar_whash(
    image_paths: List[str],
    threshold: int = 12,
    settings: Optional[Dict] = None,
    cache_manager: Optional[Any] = None
) -> List[SimilarityGroup]:
    """
    Find similar images using wHash algorithm.

    Args:
        image_paths: List of image paths
        threshold: Similarity threshold (0-64)
        settings: Optional settings
        cache_manager: Optional cache manager

    Returns:
        List of similarity groups
    """
    return find_similar_images(
        image_paths,
        algorithm="whash",
        threshold=threshold,
        settings=settings,
        flat_cache_manager=cache_manager
    )


def find_exact_duplicates(
    image_paths: List[str],
    cache_manager: Optional[Any] = None
) -> List[SimilarityGroup]:
    """
    Find exact duplicate images.

    Args:
        image_paths: List of image paths
        cache_manager: Optional cache manager

    Returns:
        List of similarity groups containing exact duplicates
    """
    return find_similar_images(
        image_paths,
        algorithm="exact",
        flat_cache_manager=cache_manager
    )
