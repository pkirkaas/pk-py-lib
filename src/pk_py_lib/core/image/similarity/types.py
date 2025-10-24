"""
Type definitions for image similarity detection.

This module contains the core type definitions, enums, and data structures
used throughout the image similarity detection system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


class HashAlgorithm(Enum):
    """Supported hash algorithms for similarity detection."""
    PHASH = "phash"      # Perceptual hash (DCT-based)
    WHASH = "whash"      # Wavelet hash (DWT-based)
    XXH3 = "xxh3"        # XXH3 content hash for exact duplicates
    BLAKE3 = "blake3"    # BLAKE3 content hash for exact duplicates


class SimilarityMode(Enum):
    """Similarity detection modes."""
    EXACT_DUPLICATES = "exact_duplicates"
    PERCEPTUAL_SIMILARITY = "perceptual_similarity"


class ProcessingPhase(Enum):
    """Processing phases for similarity detection."""
    ALGORITHM_RESOLUTION = "algorithm_resolution"
    EXACT_DUPLICATE_DETECTION = "exact_duplicate_detection"
    PERCEPTUAL_HASH_COMPUTATION = "perceptual_hash_computation"
    SIMILARITY_CLUSTERING = "similarity_clustering"
    GROUP_EXPANSION = "group_expansion"


@dataclass(frozen=True)
class HashResult:
    """
    Result of hash computation.

    Contains the computed hash value, metadata about the computation,
    and any additional information.
    """
    algorithm: HashAlgorithm
    hash_value: str
    computation_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate hash result."""
        if not self.hash_value:
            raise ValueError("Hash value cannot be empty")
        if self.computation_time < 0:
            raise ValueError("Computation time cannot be negative")


@dataclass(frozen=True)
class ImageMetadata:
    """
    Metadata for an image file.

    Contains file system information and computed properties
    needed for similarity detection.
    """
    path: str
    size: int
    width: int
    height: int
    format: str
    mod_time: float

    # Optional metadata
    quality_score: Optional[float] = None
    quality_algorithm: Optional[str] = None

    # Computed properties
    aspect_ratio: float = field(init=False)
    megapixels: float = field(init=False)

    def __post_init__(self) -> None:
        """Calculate computed properties."""
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Image dimensions must be positive")

        self.aspect_ratio = self.width / self.height
        self.megapixels = (self.width * self.height) / 1_000_000

    @property
    def dimensions(self) -> str:
        """Get dimensions as string."""
        return f"{self.width}x{self.height}"

    @property
    def size_readable(self) -> str:
        """Get human-readable file size."""
        size_bytes = float(self.size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"


@dataclass
class SimilarityGroup:
    """
    Group of similar images.

    Represents a collection of images that are similar to each other
    based on the specified similarity criteria.
    """
    id: int
    reference_image: ImageMetadata
    similar_images: List[ImageMetadata]
    similarity_scores: Dict[str, float]  # path -> similarity score
    algorithm_used: HashAlgorithm
    threshold_used: float
    exact_duplicate_sets: List[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_images(self) -> int:
        """Get total number of images in group."""
        return len(self.similar_images) + 1  # +1 for reference

    @property
    def avg_similarity(self) -> float:
        """Get average similarity score."""
        if not self.similarity_scores:
            return 0.0
        return sum(self.similarity_scores.values()) / len(self.similarity_scores)

    @property
    def min_similarity(self) -> float:
        """Get minimum similarity score."""
        if not self.similarity_scores:
            return 0.0
        return min(self.similarity_scores.values())

    @property
    def max_similarity(self) -> float:
        """Get maximum similarity score."""
        if not self.similarity_scores:
            return 0.0
        return max(self.similarity_scores.values())


@dataclass
class ExactDuplicateSet:
    """
    Set of exact duplicate files.

    Represents files that have identical content hashes and are
    considered byte-for-byte duplicates.
    """
    id: int
    files: List[str]  # List of file paths
    content_hash: str
    total_size: int
    representative_path: str = field(init=False)

    def __post_init__(self) -> None:
        """Set representative path."""
        self.representative_path = min(self.files)  # Lexicographically first

    @property
    def file_count(self) -> int:
        """Get number of files in set."""
        return len(self.files)

    @property
    def potential_savings(self) -> int:
        """Get potential size savings if duplicates are removed."""
        return self.total_size - min(self.file_sizes) if self.file_sizes else 0

    @property
    def file_sizes(self) -> List[int]:
        """Get sizes of all files (would need to be populated)."""
        # This would be populated during processing
        return []


@dataclass
class ProcessingContext:
    """
    Context for similarity processing operations.

    Contains all the information needed to perform similarity detection
    including configuration, state, and metadata.
    """
    # Configuration
    algorithm: HashAlgorithm
    threshold: float
    search_type: str = "similarity"

    # State
    total_files: int = 0
    processed_files: int = 0
    exact_duplicate_sets: List[ExactDuplicateSet] = field(default_factory=list)
    current_phase: ProcessingPhase = ProcessingPhase.ALGORITHM_RESOLUTION

    # Metadata
    start_time: datetime = field(default_factory=datetime.now)
    settings: Dict[str, Any] = field(default_factory=dict)
    cache_manager: Any = None  # Will be FlatCacheManager

    @property
    def progress(self) -> float:
        """Get current progress as percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100.0

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    def update_progress(self, processed: int) -> None:
        """Update progress counter."""
        self.processed_files = processed

    def set_phase(self, phase: ProcessingPhase) -> None:
        """Set current processing phase."""
        self.current_phase = phase


@dataclass
class SimilarityError(Exception):
    """Base exception for similarity detection errors."""
    message: str
    algorithm: Optional[HashAlgorithm] = None
    file_path: Optional[str] = None

    def __init__(
        self,
        message: str,
        algorithm: Optional[HashAlgorithm] = None,
        file_path: Optional[str] = None
    ):
        self.message = message
        self.algorithm = algorithm
        self.file_path = file_path
        super().__init__(message)


@dataclass
class InvalidImageError(SimilarityError):
    """Exception raised when an image file is invalid or corrupted."""
    pass


@dataclass
class HashComputationError(SimilarityError):
    """Exception raised when hash computation fails."""
    pass
