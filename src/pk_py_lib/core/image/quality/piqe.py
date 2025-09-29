"""
PIQE Image Quality Evaluator.

This module implements the PIQEImageQualityEvaluator class, which uses OpenCV's
QualityPIQE for blind/referenceless image quality assessment. PIQE is a no-reference
metric that does not require external model files.
Native scores are lower-better (0-100, closer to 0 means better quality); this implementation
normalizes to higher-better (0-100) for consistency with the ImageQualityEvaluator interface.

PIQE specifics:
- Blind metric based on local variance and distortion analysis.
- Does not require external model files.
- Score range is typically 0-100.

Usage Example:
    evaluator = PIQEImageQualityEvaluator()
    score = evaluator.evaluate('/path/to/image.jpg')  # e.g., 74.7 (higher = better quality)

Raises:
    ImageQualityFileError: If file not found, unreadable, or invalid image.
    ImageQualityComputationError: If computation fails.
"""

import os
import cv2
import numpy as np
from typing import Optional

from .base import ImageQualityEvaluator

# Check for PIQE availability in OpenCV
_PIQE_CLASS = getattr(cv2.quality, 'QualityPIQE', None)
_PIQE_AVAILABLE = _PIQE_CLASS is not None
from pk_py_lib.core.image.quality.exceptions import ImageQualityFileError, ImageQualityComputationError
from pk_py_lib.core.logging import get_logger


class PIQEImageQualityEvaluator(ImageQualityEvaluator):
    """
    PIQE-based image quality evaluator.

    Uses OpenCV's QualityPIQE, which is a no-reference metric that does not require
    external model files. PIQE scores are lower-better (0-100).
    Normalizes scores to higher-better scale (0-100).

    Args:
        None.

    Attributes:
        piqe: The OpenCV QualityPIQE instance.
        logger: Project logger.

    Example:
        evaluator = PIQEImageQualityEvaluator()
        score = evaluator.evaluate('/path/to/img.jpg')  # e.g., 74.7 (higher = better quality)
    """

    @property
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm."""
        return "PIQE"

    IS_AVAILABLE = _PIQE_AVAILABLE

    def __init__(self):
        """
        Initialize the PIQE evaluator.

        PIQE does not require external model files, so initialization is straightforward.
        Raises ImageQualityComputationError if QualityPIQE is not available in cv2.quality.
        """
        self.logger = get_logger(__name__)

        if not self.IS_AVAILABLE:
            error_msg = "PIQE evaluator is unavailable. cv2.quality.QualityPIQE not found."
            self.logger.error(error_msg)
            raise ImageQualityComputationError(
                error_msg, path="N/A", original_error=AttributeError(error_msg)
            )

        try:
            # Instantiate the PIQE object using the dynamically retrieved class
            self.piqe = _PIQE_CLASS()
            self.logger.info("PIQE evaluator initialized successfully.")
        except Exception as exc:
            error_msg = "Failed to initialize PIQE evaluator."
            self.logger.error(error_msg, exception=exc, exc_info=True)
            # Re-raise as a computation error if the OpenCV object cannot be created
            raise ImageQualityComputationError(
                error_msg, path="N/A", original_error=exc
            ) from exc

    def evaluate(self, path: str) -> float:
        """
        Evaluate the quality of the image at the given path using PIQE.

        PIQE scores are lower-better (0-100). Normalization: 100 - raw_score, clamped to 0-100.

        Args:
            path (str): Path to image file.

        Returns:
            float: Normalized quality score (0-100, higher = better).

        Raises:
            ImageQualityFileError: File/loading issues.
            ImageQualityComputationError: Computation failures.

        Example:
            score = evaluator.evaluate('/path/to/good_image.jpg')  # e.g., 95.1
        """
        # File validation
        if not os.path.exists(path):
            raise ImageQualityFileError(f"File not found: {path}", path=path)
        if not os.path.isfile(path):
            raise ImageQualityFileError(f"Not a file: {path}", path=path)

        # Load image
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ImageQualityFileError(f"Failed to load image: {path}", path=path)

        try:
            # OpenCV's QualityPIQE.compute() returns (score, features, ...).
            # Score can be a float or a 1-element sequence (tuple/list/ndarray).
            result = self.piqe.compute(image)
            
            # Extract the score component (first element of the result tuple)
            raw_score = result[0]
            
            # If the score component is a sequence (e.g., (score,)), extract the scalar value
            if isinstance(raw_score, (list, tuple, np.ndarray)):
                raw_score = raw_score[0]
            
            # Ensure final score is a float
            raw_score = float(raw_score)
            
            # PIQE is lower-better (0-100). Normalize to higher-better (0-100).
            # Clamp the result to ensure it stays within 0-100 range.
            normalized = max(0.0, min(100.0, 100.0 - raw_score))
            
            self.logger.debug(f"PIQE raw: {raw_score:.2f}, normalized: {normalized:.2f} for {path}")
            return normalized
        except Exception as e:
            raise ImageQualityComputationError(
                f"PIQE computation failed for {path}: {str(e)}", path=path, original_error=e
            ) from e


__all__ = ["PIQEImageQualityEvaluator"]