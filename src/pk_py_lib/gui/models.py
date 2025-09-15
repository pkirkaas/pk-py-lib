from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
from pathlib import Path
import os
from PIL import Image
from PySide6.QtGui import QPixmap
from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Stats:
    """
    Statistical data for a group of similar images.

    Computes aggregate metrics such as score ranges and total size for the group.
    Used in Group for summary information.

    Args:
        min_score (float): Minimum similarity score in the group (0.0-1.0 normalized).
        max_score (float): Maximum similarity score in the group.
        avg_score (float): Average similarity score across all images.
        total_size (int): Total file size of all images in bytes.

    Example:
        >>> stats = Stats(min_score=0.85, max_score=0.95, avg_score=0.90, total_size=1024000)
        >>> print(stats.avg_score)
        0.9
    """
    min_score: float = 0.0
    max_score: float = 0.0
    avg_score: float = 0.0
    total_size: int = 0


@dataclass
class ImageData:
    """
    Data structure for an individual image in a similarity group.

    Holds metadata and similarity score for display in the GUI tree.
    Thumb is a pre-scaled QPixmap for efficient rendering; generated on-demand in the dialog
    but stored here for reusability. Path is used as thumb source if pixmap is None.

    Args:
        path (str): Full file path to the image.
        size (int): File size in bytes.
        resolution (str): Image dimensions as "widthxheight" (e.g., "1920x1080").
        mod_date (str): Formatted modification date (e.g., "15-Sep-25").
        score (float): Individual similarity score to group reference (0.0-1.0).
        thumb (QPixmap, optional): Pre-rendered thumbnail pixmap (64x64). Defaults to None;
            generated from path in ThumbDelegate.

    Example:
        >>> img_data = ImageData(
        ...     path="/path/to/image.jpg",
        ...     size=524288,
        ...     resolution="1920x1080",
        ...     mod_date="15-Sep-25",
        ...     score=0.92
        ... )
        >>> print(img_data.resolution)
        1920x1080
    """
    path: str
    size: int
    resolution: str
    mod_date: str
    score: float = 0.0
    thumb: QPixmap | None = field(default=None, repr=False)


@dataclass
class Group:
    """
    A group of similar images for hierarchical display in the GUI.

    Represents a cluster of images with similarity scores <= threshold.
    Includes stats for group summary and reference path for primary thumbnail.

    Args:
        id (int): Unique group identifier (sequential).
        images (List[ImageData]): List of ImageData objects for images in the group.
        stats (Stats): Aggregate statistics for the group.
        ref_path (str): Path to the reference image (first in group) for primary thumbnail.

    Example:
        >>> group = Group(
        ...     id=1,
        ...     images=[img_data1, img_data2],
        ...     stats=Stats(avg_score=0.90, total_size=1048576),
        ...     ref_path="/path/to/ref.jpg"
        ... )
        >>> print(len(group.images))
        2
    """
    id: int
    images: List[ImageData]
    stats: Stats
    ref_path: str