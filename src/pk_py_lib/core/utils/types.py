"""
Core type definitions and data structures for pk-py-lib.

This module defines the fundamental types, enums, and data structures
that are used throughout the library for consistency and type safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import uuid


class ProcessingMode(Enum):
    """Processing modes for image operations."""
    SIMILARITY = "similarity"
    DUPLICATES = "duplicates"


class HashAlgorithm(Enum):
    """Supported hash algorithms."""
    PHASH = "phash"
    WHASH = "whash"
    XXH3 = "xxh3"
    BLAKE3 = "blake3"


class ImageFormat(Enum):
    """Supported image formats."""
    JPEG = "jpeg"
    PNG = "png"
    GIF = "gif"
    BMP = "bmp"
    TIFF = "tiff"
    WEBP = "webp"
    HEIC = "heic"
    HEIF = "heif"


class CacheInvalidationKey(Enum):
    """Keys used for cache invalidation."""
    PATH = "path"
    SIZE = "size"
    MTIME_NS = "mtime_ns"
    INODE = "inode"
    DEVICE = "device"


@dataclass(frozen=True)
class FileIdentity:
    """
    Immutable file identity information for robust move/rename detection.

    This class captures the essential file attributes needed to determine
    if a file has changed or been moved/renamed.
    """
    path: str
    size: int
    mtime_ns: int
    inode: Optional[int] = None
    device: Optional[int] = None
    hash_xxh3: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate identity information."""
        if self.size < 0:
            raise ValueError("File size cannot be negative")
        if self.mtime_ns < 0:
            raise ValueError("Modification time cannot be negative")

    @property
    def is_complete(self) -> bool:
        """Check if identity information is complete."""
        return (
            self.inode is not None and
            self.device is not None and
            self.hash_xxh3 is not None
        )

    def matches(self, other: FileIdentity) -> bool:
        """Check if this identity matches another."""
        return (
            self.size == other.size and
            self.mtime_ns == other.mtime_ns and
            self.inode == other.inode and
            self.device == other.device and
            self.hash_xxh3 == other.hash_xxh3
        )


@dataclass
class ImageMetadata:
    """
    Metadata information for an image file.

    This class stores all the metadata extracted from an image file,
    including file system information and computed properties.
    """
    # File information
    path: Path
    size: int
    created_time: datetime
    modified_time: datetime

    # Image properties
    width: int
    height: int
    format: str
    mode: str  # PIL mode (RGB, RGBA, etc.)

    # Computed properties
    aspect_ratio: float = field(init=False)
    megapixels: float = field(init=False)

    # Optional metadata
    exif_data: Optional[Dict[str, Any]] = None
    quality_score: Optional[float] = None
    quality_algorithm: Optional[str] = None

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
class HashResult:
    """
    Result of hash computation with metadata.
    """
    algorithm: HashAlgorithm
    hash_value: str
    computation_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SimilarityGroup:
    """
    Group of similar images.
    """
    id: int
    reference_image: ImageMetadata
    member_images: List[ImageMetadata]
    similarity_scores: Dict[ImageMetadata, float]
    algorithm_used: HashAlgorithm
    threshold_used: float
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_images(self) -> int:
        """Get total number of images in group."""
        return len(self.member_images) + 1  # +1 for reference

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
class ProcessingResult:
    """
    Result of image processing operation.
    """
    success: bool
    groups: List[SimilarityGroup] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    processing_time: float = 0.0
    images_processed: int = 0
    images_skipped: int = 0


@dataclass
class ValidationResult:
    """
    Result of validation operation.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Type aliases for convenience
PathLike = Union[str, Path]
ImagePath = Union[str, Path]
HashValue = str
SimilarityScore = float
Timestamp = Union[datetime, str]
