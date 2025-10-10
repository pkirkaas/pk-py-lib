"""
src/pk_py_lib/core/image/similarity/phases.py

Processing phases for find_similar_images functionality.

This module extracts the individual processing phases from the monolithic
find_similar_images function to improve testability, maintainability,
and enable per-phase optimization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Set, Callable
import numpy as np

from pk_py_lib.core.filesystem.identity import compute_xxh3
from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.models import FileItem
from pk_py_lib.gui.dialog_models import Group

from .hashing import compute_similarity_hash_batch
from .metadata import compute_group_stats, format_timestamp, get_image_metadata, get_image_quality_score
from .similarity_types import ExactDuplicateSet, SimilarityError
from .validation import hamming_distance, validate_and_normalize_hash, validate_threshold

logger = get_logger(__name__)


class PhaseContext:
    """
    Context object passed between phases to maintain state and support progress reporting.

    This class carries all the data and configuration needed by the processing phases,
    avoiding parameter passing complexity. It also provides progress callback and
    cancellation support for long-running operations.

    Attributes:
        image_paths (List[str]): List of absolute file paths to process.
        algorithm (Optional[str]): 'exact', 'phash', or 'whash' algorithm selection.
        threshold (Optional[int]): Max Hamming distance for perceptual clustering.
        settings (Optional[Dict]): Algorithm selection and threshold overrides.
        flat_cache_manager (Optional[FlatCacheManager]): Cache manager for hash computations.
        search_type (str): 'similarity' or 'duplicate' search type.
        max_workers (int): Maximum number of worker threads for parallel processing.
        progress_callback (Optional[Callable[[int, int, str], None]]): Function to call for progress updates.
        cancellation_flag (Optional[List[bool]]): Mutable flag list for external cancellation control.
        total_files (int): Total number of files for progress calculation.
    """

    def __init__(
        self,
        image_paths: List[str],
        algorithm: Optional[str] = None,
        threshold: Optional[int] = None,
        settings: Optional[Dict] = None,
        flat_cache_manager: Optional[FlatCacheManager] = None,
        search_type: str = 'similarity',
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_flag: Optional[List[bool]] = None,
        total_files: Optional[int] = None
    ):
        """
        Initialize phase context with all processing parameters and progress support.

        Args:
            image_paths (List[str]): List of absolute file paths to process.
            algorithm (Optional[str]): 'exact', 'phash', or 'whash' (default from settings or 'phash').
            threshold (Optional[int]): Max Hamming distance for perceptual clustering (ignored for 'exact').
            settings (Optional[Dict]): For algorithm selection and threshold overrides.
            flat_cache_manager (Optional[FlatCacheManager]): For caching all hash computations and metadata.
            search_type (str): 'similarity' or 'duplicate' (affects computations).
            max_workers (int): Maximum number of worker threads for parallel processing.
            progress_callback (Optional[Callable[[int, int, str], None]]): Function called to report progress.
                Should accept (current: int, total: int, message: str) parameters.
            cancellation_flag (Optional[List[bool]]): Single-element list containing cancellation status.
                External code can set [True] to request cancellation. Defaults to new list if None.
            total_files (Optional[int]): Total files for progress calculation. Defaults to len(image_paths).

        Note:
            All new parameters are optional to maintain backward compatibility with existing code.
        """
        self.image_paths = image_paths
        self.algorithm = algorithm
        self.threshold = threshold
        self.settings = settings
        self.flat_cache_manager = flat_cache_manager
        self.search_type = search_type
        self.max_workers = max_workers

        # Progress and cancellation support
        self.progress_callback = progress_callback
        self.cancellation_flag = cancellation_flag if cancellation_flag is not None else [False]
        self.total_files = total_files if total_files is not None else len(image_paths)

        # Phase-specific data
        self.exact_sets: List[ExactDuplicateSet] = []
        self.path_to_set_id_map: Dict[str, Optional[int]] = {}
        self.representative_paths: List[str] = []
        self.perceptual_hashes: Dict[str, Optional[str]] = {}
        self.representative_groups: List[Group] = []
        self.final_groups: List[Group] = []
        self.stats: Dict[str, Any] = {}

    def report_progress(self, current: int, message: str = "") -> None:
        """
        Report progress to the callback function if available.

        Args:
            current (int): Current progress count (0 to total_files).
            message (str): Optional progress message.

        Note:
            This method handles None callback gracefully - no exception will be raised.
        """
        if self.progress_callback is not None:
            try:
                self.progress_callback(current, self.total_files, message)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def is_cancelled(self) -> bool:
        """
        Check if operation has been cancelled.

        Returns:
            bool: True if cancellation has been requested, False otherwise.
        """
        return self.cancellation_flag[0] if self.cancellation_flag else False

    def check_cancellation(self) -> None:
        """
        Check for cancellation and raise exception if cancelled.

        Raises:
            SimilarityError: If cancellation has been requested.
        """
        if self.is_cancelled():
            raise SimilarityError("Operation cancelled by user")


def phase_algorithm_resolution(context: PhaseContext) -> PhaseContext:
    """
    Phase 1: Resolve and validate algorithm parameters.

    This phase validates all input parameters, determines the effective
    algorithm and hash size, and prepares for processing.

    Args:
        context: Phase context with input parameters

    Returns:
        Updated context with resolved parameters

    Raises:
        SimilarityError: If parameters are invalid
    """
    logger.info(f"Starting Phase 1: Algorithm Resolution for {len(context.image_paths)} paths")
    context.report_progress(0, "Starting algorithm resolution...")

    if not context.image_paths:
        raise SimilarityError("paths list cannot be empty")

    # Check for cancellation after initial validation
    context.check_cancellation()

    # Determine algorithm
    if context.algorithm is None:
        if context.settings and 'criteria' in context.settings and 'similarity_hash_algorithm' in context.settings['criteria']:
            context.algorithm = context.settings['criteria']['similarity_hash_algorithm']
        else:
            context.algorithm = 'phash'

    if context.algorithm not in ['exact', 'phash', 'whash']:
        raise SimilarityError(f"Unsupported algorithm: {context.algorithm}. Supported: 'exact', 'phash', 'whash'")

    logger.info(f"Resolved algorithm: {context.algorithm}")

    # Store algorithm in stats for reporting
    context.stats['resolved_algorithm'] = context.algorithm
    context.stats['search_type'] = context.search_type

    # Report 25% progress when algorithm validation is complete
    context.report_progress(len(context.image_paths) // 4, "Algorithm validation complete (25%)")
    logger.info("Phase 1 complete: Algorithm Resolution")
    return context


def phase_exact_duplicate_detection(context: PhaseContext) -> PhaseContext:
    """
    Phase 2: Detect exact file duplicates.

    This phase identifies files that are exact duplicates based on
    file size and hash, removing them from further processing.

    Args:
        context: Phase context with validated parameters

    Returns:
        Updated context with exact duplicates identified

    Raises:
        SimilarityError: If duplicate detection fails
    """
    logger.info(f"Starting Phase 2: Exact Duplicate Detection for {len(context.image_paths)} paths")
    context.report_progress(len(context.image_paths) // 4, "Starting exact duplicate detection...")

    # Check for cancellation at start of phase
    context.check_cancellation()

    # Note: We still perform exact duplicate detection even in exact mode
    # because we need to identify the duplicate sets for grouping

    # Compute XXH3 hashes for all paths (use cache if available)
    path_to_hash: Dict[str, Optional[str]] = {}

    # File list building phase - start
    context.report_progress(len(context.image_paths) // 4, "File list building phase started...")
    logger.info("File list building phase: Preparing to process file list and check cache")

    if context.flat_cache_manager:
        try:
            # Cache checking phase - start
            context.report_progress(len(context.image_paths) // 4, "Cache checking phase started - checking existing hash cache...")
            logger.info(f"Cache checking phase: Querying cache for {len(context.image_paths)} files")

            hashes = context.flat_cache_manager.get_hashes(context.image_paths, ['xxh3'])
            path_to_hash = {p: h.get('xxh3') for p, h in hashes.items()}

            # Cache checking phase - completion with stats
            files_found_in_cache = sum(1 for h in path_to_hash.values() if h is not None)
            files_to_compute = sum(1 for h in path_to_hash.values() if h is None)
            context.report_progress(len(context.image_paths) // 4, f"Cache checking complete: {files_found_in_cache}/{len(context.image_paths)} files found in cache, {files_to_compute} files need computation")
            logger.info(f"Cache checking complete: {files_found_in_cache} files found in cache, {files_to_compute} files require computation")

        except Exception as e:
            logger.warning(f"Cache failure for XXH3; falling back to direct computation: {e}")
            path_to_hash = {}
            files_to_compute = len(context.image_paths)
            context.report_progress(len(context.image_paths) // 4, f"Cache checking failed: {e}, falling back to direct computation for all {files_to_compute} files")
    else:
        path_to_hash = {}
        files_to_compute = len(context.image_paths)
        context.report_progress(len(context.image_paths) // 4, f"No cache available: Direct computation required for all {files_to_compute} files")

    # Direct computation for misses or no cache
    files_to_process = len(context.image_paths)
    files_computed = 0
    files_with_errors = 0

    # Cache update phase - start
    if files_to_compute > 0:
        context.report_progress(len(context.image_paths) // 4, f"Cache update phase started - computing {files_to_compute} missing hashes...")
        logger.info(f"Cache update phase: Computing hashes for {files_to_compute} files not found in cache")

    for i, path in enumerate(context.image_paths):
        if path not in path_to_hash or path_to_hash[path] is None:
            try:
                hash_val = compute_xxh3(Path(path))
                path_to_hash[path] = hash_val
                files_computed += 1
                logger.debug(f"Computed XXH3 for {path}: {hash_val[:8]}...")
            except Exception as e:
                logger.warning(f"Failed to compute XXH3 for {path}: {e}")
                path_to_hash[path] = None
                files_with_errors += 1

        # Periodic progress updates during hash computation with granular cache update tracking
        if (i + 1) % max(1, files_to_process // 20) == 0:  # Update ~5% intervals or every file for small batches
            computed_so_far = files_computed
            errors_so_far = files_with_errors
            total_progress = files_to_compute

            # Calculate progress between 25% and 50% during hash computation
            phase2_progress_base = len(context.image_paths) // 4  # 25%
            phase2_progress_range = len(context.image_paths) // 4  # 25% range for phase 2
            current_phase2_progress = int(phase2_progress_base + (i + 1) / files_to_process * phase2_progress_range)

            if files_to_compute > 0:
                context.report_progress(current_phase2_progress, f"Cache update: {computed_so_far}/{total_progress} computed, {errors_so_far} errors ({i + 1}/{files_to_process} total)")
            else:
                context.report_progress(current_phase2_progress, f"Processing files... ({i + 1}/{files_to_process} files)")
            context.check_cancellation()

        # Additional cancellation check for every file (frequent but lightweight)
        if (i + 1) % max(1, files_to_process // 100) == 0:  # Check cancellation ~1% intervals
            context.check_cancellation()

    # Cache completion status
    if files_to_compute > 0:
        total_cached = files_found_in_cache if context.flat_cache_manager else 0
        context.report_progress(len(context.image_paths) // 4, f"Cache update complete: {files_computed}/{files_to_compute} computed, {files_with_errors} errors, {total_cached} from cache")
        logger.info(f"Cache update complete: {files_computed} hashes computed, {files_with_errors} errors, {total_cached} retrieved from cache")

    # File list building phase - completion
    context.report_progress(len(context.image_paths) // 4, f"File list building phase complete: Processed {files_to_process} files")
    logger.info(f"File list building phase complete: {files_to_process} files processed, {files_computed} hashes computed, {files_with_errors} errors")

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

    # Store results in context
    context.exact_sets = exact_sets
    context.path_to_set_id_map = path_to_set_id_map

    # Update stats
    context.stats['exact_sets_count'] = len(exact_sets)
    context.stats['exact_duplicates_count'] = sum(len(s.paths) for s in exact_sets)

    # Report 50% progress when exact duplicate detection is complete
    context.report_progress(len(context.image_paths) // 2, "Exact duplicate detection complete (50%)")
    logger.info(f"Phase 2 complete: Detected {len(exact_sets)} exact duplicate sets from {len(context.image_paths)} paths "
                f"({context.stats['exact_duplicates_count']} duplicates total)")
    return context


def phase_perceptual_hash_computation(context: PhaseContext) -> PhaseContext:
    """
    Phase 3: Compute perceptual hashes for remaining files.

    This phase computes similarity hashes for all files that were
    not identified as exact duplicates, using caching when available.

    Args:
        context: Phase context with exact duplicates removed

    Returns:
        Updated context with hash computation results

    Raises:
        SimilarityError: If hash computation fails
    """
    logger.info(f"Starting Phase 3: Perceptual Hash Computation")
    context.report_progress(len(context.image_paths) // 2, "Starting perceptual hash computation...")

    # Check for cancellation at start of phase
    context.check_cancellation()

    # Skip perceptual hash computation for exact mode
    if context.algorithm == 'exact':
        logger.info("Skipping perceptual hash computation in exact mode")
        context.stats['perceptual_hashes_count'] = 0
        context.report_progress(3 * len(context.image_paths) // 4, "Skipped perceptual hashing in exact mode")
        return context

    # Identify unique representatives
    rep_paths = set()
    for path in context.image_paths:
        set_id = context.path_to_set_id_map.get(path)
        if set_id is None:
            # Singleton: use itself
            rep_paths.add(path)
        else:
            # Duplicate: use rep from its set
            for s in context.exact_sets:
                if s.id == set_id:
                    rep_paths.add(s.representative_path)
                    break

    all_reps = list(rep_paths)
    context.representative_paths = all_reps

    logger.debug(f"Phase 3: {len(context.exact_sets)} exact sets, "
                f"{len([p for p in context.image_paths if context.path_to_set_id_map.get(p) is None])} singletons, "
                f"{len(all_reps)} unique reps")

    # Compute perceptual hashes only for representatives
    context.report_progress(3 * len(context.image_paths) // 4, f"Computing perceptual hashes for {len(all_reps)} representatives...")
    context.check_cancellation()

    # Add cancellation check before starting hash computation
    context.check_cancellation()

    perceptual_hashes = compute_similarity_hash_batch(
        all_reps,
        algorithm=context.algorithm,
        settings=context.settings,
        flat_cache_manager=context.flat_cache_manager,
        search_type=context.search_type
    )

    # Additional cancellation check after hash computation completes
    context.check_cancellation()

    # Log sample hashes to verify correct algorithm
    logger.info(f"Computed {len(perceptual_hashes)} {context.algorithm} hashes")
    for path, hash_val in list(perceptual_hashes.items())[:3]:
        logger.debug(f"  {Path(path).name}: {context.algorithm} = {hash_val[:16] if hash_val else None}...")

    # Store results in context
    context.perceptual_hashes = perceptual_hashes

    # Update stats
    valid_hashes = [h for h in perceptual_hashes.values() if h is not None]
    context.stats['perceptual_hashes_count'] = len(valid_hashes)
    context.stats['representative_paths_count'] = len(all_reps)

    # Report 75% progress when perceptual hash computation is complete
    context.report_progress(3 * len(context.image_paths) // 4, "Perceptual hash computation complete (75%)")
    logger.info(f"Phase 3 complete: Computed {len(valid_hashes)}/{len(all_reps)} valid perceptual hashes")
    return context


def phase_similarity_clustering(context: PhaseContext) -> PhaseContext:
    """
    Phase 4: Perform similarity clustering and group expansion.

    This phase groups files by similarity using the selected clustering
    algorithm and expands groups to include related files.

    Args:
        context: Phase context with hash computation complete

    Returns:
        Updated context with final similarity groups

    Raises:
        SimilarityError: If clustering fails
    """
    logger.info(f"Starting Phase 4: Similarity Clustering and Group Expansion")
    context.report_progress(len(context.image_paths), "Starting similarity clustering...")

    # Check for cancellation at start of phase
    context.check_cancellation()

    # Handle exact mode
    if context.algorithm == 'exact':
        logger.info("Processing exact mode clustering")
        groups = []
        group_id = 1
        quality_evaluator = get_active_image_quality_evaluator() if context.search_type != 'duplicate' else None

        for exact_set in context.exact_sets:
            images = []
            for path in exact_set.paths:
                try:
                    meta = get_image_metadata(path, search_type=context.search_type)
                    score = 1.0
                    quality_score, quality_algorithm = (
                        (1.0, None) if context.search_type == 'duplicate' else
                        get_image_quality_score(path, quality_evaluator, context.flat_cache_manager, search_type=context.search_type)
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
                # Create new stats with overridden scores for exact duplicates
                from pk_py_lib.gui.models import GroupStats
                stats = GroupStats(
                    total_size=stats.total_size,
                    savings=stats.savings,
                    min_score=1.0,
                    max_score=1.0,
                    avg_score=1.0,
                    file_count=stats.file_count
                )
                group = Group(
                    id=group_id,
                    items=images,
                    stats=stats,
                    ref_path=exact_set.representative_path
                )
                groups.append(group)
                group_id += 1

        context.final_groups = groups
        context.stats['final_groups_count'] = len(groups)
        logger.info(f"Phase 4 complete: Exact mode found {len(groups)} groups from {len(context.exact_sets)} sets")
        return context

    # Filter valid reps (skip if hash computation failed)
    valid_reps = [rep for rep in context.representative_paths if context.perceptual_hashes.get(rep) is not None]
    rep_hashes = [{'path': rep, 'hash': context.perceptual_hashes[rep]} for rep in valid_reps]

    if not rep_hashes:
        logger.warning("No valid perceptual hashes computed for representatives; returning empty groups")
        context.final_groups = []
        context.stats['final_groups_count'] = 0
        return context

    # Perform similarity clustering on representatives
    from .clustering import find_similar_phash, find_similar_whash

    # Comparison phase start
    context.report_progress(len(context.image_paths), f"Comparison phase started: Clustering {len(rep_hashes)} representatives using {context.algorithm}...")
    logger.info(f"Comparison phase started: Beginning similarity comparison for {len(rep_hashes)} representatives")
    context.check_cancellation()

    # Add cancellation check before starting clustering computation
    context.check_cancellation()

    if context.algorithm == 'phash':
        rep_groups = find_similar_phash(
            rep_hashes,
            context.threshold,
            context.settings,
            context.flat_cache_manager,
            search_type=context.search_type,
            algorithm=context.algorithm
        )
    elif context.algorithm == 'whash':
        rep_groups = find_similar_whash(
            rep_hashes,
            context.threshold,
            context.settings,
            context.flat_cache_manager,
            search_type=context.search_type,
            algorithm=context.algorithm
        )
    else:
        raise SimilarityError(f"Unexpected perceptual algorithm: {context.algorithm}")

    # Add cancellation check after clustering computation completes
    context.check_cancellation()

    context.representative_groups = rep_groups
    logger.debug(f"Phase 4: Clustered {len(valid_reps)} reps into {len(rep_groups)} perceptual groups")

    # Expand groups with exact duplicates
    final_groups = []
    perceptual_group_id = 1
    quality_evaluator = get_active_image_quality_evaluator() if context.search_type != 'duplicate' else None

    for i, rep_group in enumerate(rep_groups):
        # Periodic cancellation checks during group expansion (can be slow for many groups)
        if i > 0 and i % max(1, len(rep_groups) // 10) == 0:  # Check every 10% of groups
            context.check_cancellation()

        expanded_items = []
        ref_path = rep_group.ref_path  # Keep original ref (a rep)

        # For each rep in the perceptual group, create FileItem with exact_set_id from map
        for rep_item in rep_group.items:
            # Recreate rep_item with exact_set_id
            rep_set_id = context.path_to_set_id_map.get(rep_item.path)
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
                for exact_set in context.exact_sets:
                    if exact_set.id == rep_set_id:
                        # Add all other paths in the set (excluding the rep itself)
                        for dup_path in exact_set.paths:
                            if dup_path != rep_item.path:
                                try:
                                    meta = get_image_metadata(dup_path, search_type=context.search_type)
                                    # Score same as rep's score (exact dup, same perceptual)
                                    dup_score = rep_item.score
                                    quality_score, quality_algorithm = (
                                        (1.0, None) if context.search_type == 'duplicate' else
                                        get_image_quality_score(dup_path, quality_evaluator, context.flat_cache_manager, search_type=context.search_type)
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

    # Final cancellation check before completing phase
    context.check_cancellation()

    # Store results in context
    context.final_groups = final_groups
    context.stats['final_groups_count'] = len(final_groups)
    context.stats['representative_groups_count'] = len(rep_groups)

    # Report 100% progress when clustering is complete
    context.report_progress(len(context.image_paths), f"Clustering complete (100%): {len(final_groups)} groups found")
    logger.info(f"Phase 4 complete: Perceptual mode ({context.algorithm}) found {len(final_groups)} expanded groups from {len(rep_groups)} rep groups")
    return context


def execute_all_phases(context: PhaseContext) -> PhaseContext:
    """
    Execute all processing phases in order.

    This function orchestrates the complete similarity detection
    process by running each phase in sequence with error handling.

    Args:
        context: Initial phase context

    Returns:
        Final context with all processing complete

    Raises:
        SimilarityError: If any phase fails
    """
    phases = [
        ("Algorithm Resolution", phase_algorithm_resolution),
        ("Exact Duplicate Detection", phase_exact_duplicate_detection),
        ("Perceptual Hash Computation", phase_perceptual_hash_computation),
        ("Similarity Clustering", phase_similarity_clustering),
    ]

    for phase_name, phase_func in phases:
        logger.info(f"Starting phase: {phase_name}")
        try:
            context = phase_func(context)
            logger.info(f"Completed phase: {phase_name}")
        except Exception as e:
            logger.error(f"Phase {phase_name} failed: {e}")
            raise SimilarityError(f"Phase {phase_name} failed: {e}") from e

    logger.info(f"All phases completed successfully. Found {context.stats.get('final_groups_count', 0)} final groups.")

    # Final progress report
    if context.progress_callback is not None:
        final_message = f"All phases complete! Found {context.stats.get('final_groups_count', 0)} groups."
        context.report_progress(context.total_files, final_message)

    return context
