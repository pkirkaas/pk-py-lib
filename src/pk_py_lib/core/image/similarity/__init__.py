"""
Image similarity detection module for pk-py-lib.

This module provides comprehensive image similarity detection capabilities
including perceptual hashing, clustering, and duplicate detection.
"""

from __future__ import annotations

# Core types and exceptions
from .types import (
    HashAlgorithm,
    SimilarityMode,
    ProcessingPhase,
    HashResult,
    ImageMetadata,
    SimilarityGroup,
    ExactDuplicateSet,
    ProcessingContext,
    SimilarityError,
    InvalidImageError,
    HashComputationError,
)

# Hash computation functions
from .hashing import (
    compute_phash,
    compute_whash,
    compute_xxh3,
    compute_phash_batch,
    compute_whash_batch,
    compute_xxh3_batch,
    hamming_distance,
    normalize_similarity_score,
    get_image_metadata,
    get_image_metadata_batch,
)

# Clustering and similarity detection
from .clustering import (
    find_similar_images,
    find_similar_phash,
    find_similar_whash,
    find_exact_duplicates,
    detect_exact_duplicates,
)

__all__ = [
    # Types and enums
    "HashAlgorithm",
    "SimilarityMode",
    "ProcessingPhase",
    "HashResult",
    "ImageMetadata",
    "SimilarityGroup",
    "ExactDuplicateSet",
    "ProcessingContext",
    "SimilarityError",
    "InvalidImageError",
    "HashComputationError",

    # Hash computation
    "compute_phash",
    "compute_whash",
    "compute_xxh3",
    "compute_phash_batch",
    "compute_whash_batch",
    "compute_xxh3_batch",
    "hamming_distance",
    "normalize_similarity_score",
    "get_image_metadata",
    "get_image_metadata_batch",

    # Similarity detection
    "find_similar_images",
    "find_similar_phash",
    "find_similar_whash",
    "find_exact_duplicates",
    "detect_exact_duplicates",
]
