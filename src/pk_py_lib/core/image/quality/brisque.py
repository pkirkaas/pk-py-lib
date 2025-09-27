"""
src/pk_py_lib/core/image/quality/brisque.py

BRISQUE (Blind/Referenceless Image Spatial Quality Evaluator) implementation for image quality assessment.

This module provides a concrete ImageQualityEvaluator using OpenCV's BRISQUE algorithm. BRISQUE is a no-reference
perceptual image quality metric based on natural scene statistics (NSS). It predicts quality without a reference
image, scoring on a scale of 0-100 where lower scores indicate better quality (0: pristine, 100: highly distorted).

Key features:
- Uses default OpenCV BRISQUE model (trained on LIVE database).
- Handles color images (BGR format from cv2.imread).
- Validates file existence and image loadability.
- Logs computation results and errors using project logger.
- Raises specific ImageQualityError subclasses for failures.

BRISQUE specifics:
- Blind metric: No need for original/distortion-free reference.
- Computation: Extracts NSS features (e.g., MSCN coefficients) and uses a SVM regressor for score.
- Edge cases: Fails gracefully on non-images, empty files, or corrupt data; supports common formats (JPG, PNG, etc.).
- Limitations: Best for distortion types in training data (JPEG, JPEG2000, etc.); may underperform on novel distortions.

Usage
-----
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator

evaluator = get_active_image_quality_evaluator()  # Defaults to BRISQUE
score = evaluator.evaluate("/path/to/image.jpg")  # Returns e.g., 25.3 (lower better)
"""

import os
import cv2
from typing import Optional

from .base import ImageQualityEvaluator
from .exceptions import ImageQualityError, ImageQualityFileError, ImageQualityComputationError
from pk_py_lib.core.logging import get_logger


class BRISQUEImageQualityEvaluator(ImageQualityEvaluator):
    """BRISQUE-based image quality evaluator using OpenCV.
    
    Implements the abstract ImageQualityEvaluator interface with BRISQUE (Blind/Referenceless Image Spatial
    Quality Evaluator). This is a no-reference metric that assesses perceived quality based on statistical
    deviations from natural images. Native BRISQUE scores range from 0 (excellent quality) to 100 (poor quality),
    but this implementation normalizes to higher-better scale for consistency: normalized_score = 100.0 - raw_score,
    clamped to [0.0, 100.0].
    
    Initialization:
    - Uses OpenCV's default BRISQUE model (no custom training data needed).
    - Lazy initialization of the BRISQUE object in evaluate() for efficiency.
    
    Extensibility:
    - Can be registered in the evaluator registry for pluggable use.
    - Subclass for custom models by overriding _create_brisque() (e.g., load custom SVM weights).
    - Normalizes BRISQUE scores (native lower-better) to higher-better scale for consistency.
    
    Parameters
    ----------
    None (uses default OpenCV model).
    
    Attributes
    ----------
    _brisque : cv2.quality.QualityBRISQUE or None
        Internal BRISQUE instance; created on first evaluate call.
    
    Raises
    ------
    ImageQualityError
        Base for all errors in this evaluator.
    
    Examples
    --------
    # Basic usage
    evaluator = BRISQUEImageQualityEvaluator()
    score = evaluator.evaluate("/path/to/pristine.jpg")  # e.g., 94.8 (higher is better)
    
    # In a loop for batch evaluation
    for img_path in image_paths:
        try:
            score = evaluator.evaluate(img_path)
            logger.info(f"Normalized BRISQUE score for {img_path}: {score}")
        except ImageQualityError as e:
            logger.error(f"Failed to evaluate {img_path}: {e}")
    """

    def __init__(self) -> None:
        # Initialize without creating BRISQUE yet (lazy load for potential reuse)
        # Inline comment: This allows multiple instances without redundant model loads
        self._brisque: Optional[cv2.quality.QualityBRISQUE] = None
        # Get logger for this module
        self._logger = get_logger(__name__)

    def evaluate(self, path: str) -> float:
        """Evaluate the quality of the image at the given path using BRISQUE.
        
        Steps:
        1. Validate path: exists, is file, readable.
        2. Load image with cv2.imread (color mode).
        3. Check loaded image validity (not None, non-empty).
        4. Initialize BRISQUE if needed.
        5. Compute raw score.
        6. Normalize to higher-better scale: 100.0 - raw_score, clamped to [0.0, 100.0].
        7. Log raw and normalized scores.
        8. Return normalized score.
        
        Handles edge cases:
        - Non-existent or non-file paths.
        - Non-image files (cv2.imread returns None).
        - Empty or zero-sized images.
        - BRISQUE creation/compute failures (e.g., OpenCV not built with contrib).
        - Extreme raw scores (>100 or <0) clamped during normalization.
        
        Parameters
        ----------
        path : str
            The absolute or relative path to the image file (e.g., '/home/user/photo.jpg').
            Supports formats readable by OpenCV (JPG, PNG, TIFF, etc.).
        
        Returns
        -------
        float
            Normalized BRISQUE quality score (0-100; higher is better). E.g., 100 for pristine, 50- for distorted.
            Native BRISQUE (lower-better) is inverted: normalized = 100.0 - raw, clamped to [0,100].
        
        Raises
        ------
        ImageQualityFileError
            If path invalid (not exists, not file) or image load fails (None or empty).
        ImageQualityComputationError
            If BRISQUE initialization or compute fails (e.g., model load error, invalid image data).
        ImageQualityError
            Base for unexpected errors.
        
        Examples
        --------
        # Successful evaluation (raw 25.3 -> normalized 74.7)
        score = evaluator.evaluate("/path/to/img.jpg")  # Returns 74.7
        
        # Good quality example (raw 10.0 -> 90.0)
        score = evaluator.evaluate("/pristine.jpg")  # Returns 90.0
        
        # Poor quality example (raw 80.5 -> 19.5)
        score = evaluator.evaluate("/distorted.jpg")  # Returns 19.5
        
        # File not found
        try:
            score = evaluator.evaluate("/nonexistent.jpg")
        except ImageQualityFileError as e:
            # e.message: "Image file not found", e.path: "/nonexistent.jpg"
            pass
        
        # Corrupted image
        try:
            score = evaluator.evaluate("/corrupt.dat")
        except ImageQualityFileError as e:
            # cv2.imread returns None for non-image
            pass
        except ImageQualityComputationError as e:
            # If load succeeds but compute fails
            pass
        
        Notes
        -----
        - BRISQUE works on color images; grayscale input may yield suboptimal results.
        - For batch use, reuse the evaluator instance to avoid repeated model initialization.
        - Logs: INFO for successful normalized scores, DEBUG for raw/normalized details, ERROR for failures.
        - Normalization inverts native lower-better scale for consistency with base interface.
        """
        # Step 1: Validate path existence and file type
        if not os.path.exists(path):
            # Raise file error with details
            raise ImageQualityFileError(
                message="Image file not found",
                path=path
            )
        if not os.path.isfile(path):
            # Raise for directories or special files
            raise ImageQualityFileError(
                message="Path is not a regular file",
                path=path
            )
        # Inline comment: Basic readability check; full I/O errors caught in imread
        
        # Step 2: Load image with OpenCV
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            # cv2.imread fails for non-images or corrupt headers
            raise ImageQualityFileError(
                message="Failed to load image (invalid format or corrupted)",
                path=path
            )
        if image.size == 0:
            # Empty image (e.g., zero dimensions)
            raise ImageQualityFileError(
                message="Loaded image is empty",
                path=path
            )
        # Inline comment: BRISQUE expects uint8 BGR; no need for conversion here
        
        # Step 3: Initialize BRISQUE if not already done
        if self._brisque is None:
            try:
                # Create BRISQUE with default model (LIVE database trained)
                # Inline comment: Uses OpenCV's built-in default weights; no custom path needed
                self._brisque = cv2.quality.QualityBRISQUE_create()
            except Exception as e:
                # Handle if OpenCV contrib not available or model load fails
                raise ImageQualityComputationError(
                    message="Failed to initialize BRISQUE model",
                    path=path,
                    original_error=e
                )
        
        # Step 4: Compute raw BRISQUE score
        try:
            # Compute score; returns float directly for single image
            # Inline comment: Per OpenCV docs, compute() returns the score (0-100)
            raw_score = self._brisque.compute(image)
            # Ensure it's a float; handle if tuple (though typically scalar)
            if isinstance(raw_score, (list, tuple)):
                raw_score = float(raw_score[0])
            else:
                raw_score = float(raw_score)
        except Exception as e:
            # Catch OpenCV errors (e.g., invalid image data post-load)
            self._logger.error(
                f"BRISQUE computation failed for {path}: {e}",
                exc_info=True  # Include stack trace for debugging
            )
            raise ImageQualityComputationError(
                message="Failed to compute BRISQUE score (possible image corruption)",
                path=path,
                original_error=e
            )
        
        # Step 5: Normalize to higher-better scale
        normalized_score = 100.0 - raw_score
        normalized_score = max(0.0, min(100.0, normalized_score))
        # Inline comment: Clamps for edge cases where raw_score <0 or >100 (rare, but robust)
        
        # Step 6: Log raw and normalized scores
        self._logger.debug(f"Raw BRISQUE: {raw_score}, Normalized: {normalized_score} for {path}")
        self._logger.info(f"Computed normalized BRISQUE score {normalized_score:.2f} for {path}")
        
        # Inline comment: Return normalized score; higher values indicate higher quality
        return normalized_score


__all__ = ["BRISQUEImageQualityEvaluator"]