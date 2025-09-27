"""
BRISQUE Image Quality Evaluator.

This module implements the BRISQUEImageQualityEvaluator class, which uses OpenCV's
QualityBRISQUE for blind/referenceless image quality assessment. BRISQUE extracts natural
scene statistics from the image and uses a pre-trained SVR model to predict quality without
a reference image. Native scores are lower-better (0-100); this implementation normalizes
to higher-better for consistency with the ImageQualityEvaluator interface.

BRISQUE specifics:
- Blind metric based on natural scene statistics (NSS).
- Trained on LIVE dataset for common distortions (JPEG, blur, noise, etc.).
- Loads bundled SVM model from brisque_model_live.yml in 'models/'. Range hardcoded to 100.0 (LIVE).
  If model missing or load fails, falls back to Laplacian variance (sharpness measure, higher = better).

Usage Example:
    evaluator = BRISQUEImageQualityEvaluator()
    score = evaluator.evaluate('/path/to/image.jpg')  # e.g., 74.7 (higher = better quality)

Raises:
    ImageQualityFileError: If file not found, unreadable, or invalid image.
    ImageQualityComputationError: If model load or computation fails.
"""

import os
import cv2
import numpy as np
from typing import Optional

from pk_py_lib.core.image.quality.base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.exceptions import ImageQualityFileError, ImageQualityComputationError
from pk_py_lib.core.logging import get_logger


class BRISQUEImageQualityEvaluator(ImageQualityEvaluator):
    """
    BRISQUE-based image quality evaluator.

    Loads bundled SVM model for QualityBRISQUE. If model missing/load fails,
    falls back to Laplacian variance (sharpness; higher variance = better quality).

    Normalizes scores to higher-better scale (0-100).

    Args:
        None (uses bundled model or fallback).

    Attributes:
        brisque: The OpenCV QualityBRISQUE instance (or None if fallback).
        logger: Project logger.

    Example:
        evaluator = BRISQUEImageQualityEvaluator()
        score = evaluator.evaluate('/path/to/img.jpg')  # e.g., 74.7 (BRISQUE) or 65.2 (Laplacian)
    """

    def __init__(self):
        """
        Initialize the BRISQUE evaluator with bundled SVM model.

        Loads brisque_model_live.yml from models/ using cv2.ml.SVM_load, then creates
        QualityBRISQUE_create(svm, 100.0) (LIVE range).
        If file missing or load fails, sets fallback to Laplacian.
        Logs the mode used.
        """
        self.logger = get_logger(__name__)
        self.brisque = None
        model_dir = os.path.join(os.path.dirname(__file__), 'models')
        model_path = os.path.join(model_dir, 'brisque_model_live.yml')

        if os.path.exists(model_path):
            try:
                # Load SVM model from YML file
                svm = cv2.ml.SVM_load(model_path)
                if svm is None:
                    raise ValueError(f"Failed to load SVM from {model_path}.")

                # Create QualityBRISQUE with loaded SVM and LIVE range (100.0)
                self.brisque = cv2.quality.QualityBRISQUE_create(svm, 100.0)
                self.logger.debug("BRISQUE evaluator initialized with bundled SVM model.")
            except Exception as e:
                self.logger.warning(f"Failed to load bundled BRISQUE SVM model {model_path}: {str(e)}. Falling back to Laplacian.")
                self.brisque = None
        else:
            self.logger.warning(
                f"BRISQUE model file missing: {model_path}. "
                "Download from https://github.com/opencv/opencv_contrib/blob/master/modules/quality/src/brisque_model_live.yml. "
                "Falling back to Laplacian variance."
            )
            self.brisque = None

    def evaluate(self, path: str) -> float:
        """
        Evaluate the quality of the image at the given path using BRISQUE or fallback.

        If BRISQUE loaded:
            - Loads image, computes raw score (lower = better).
            - Normalizes: 100 - raw, clamped to 0-100.

        Fallback (Laplacian):
            - Grayscale, Laplacian variance (higher = sharper/better).
            - Normalizes: min(100, var / 100) (empirical for 0-10000 var range).

        Args:
            path (str): Path to image file.

        Returns:
            float: Normalized quality score (0-100, higher = better).

        Raises:
            ImageQualityFileError: File/loading issues.
            ImageQualityComputationError: Computation failures.

        Example:
            score = evaluator.evaluate('/path/to/blurry.jpg')  # e.g., 45.2 (low sharpness)
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

        if self.brisque is not None:
            try:
                raw_score = self.brisque.compute(image)
                raw_score = float(raw_score)
                normalized = max(0.0, min(100.0, 100.0 - raw_score))
                self.logger.debug(f"BRISQUE raw: {raw_score:.2f}, normalized: {normalized:.2f} for {path}")
                return normalized
            except Exception as e:
                self.logger.warning(f"BRISQUE compute failed for {path}: {str(e)}. Falling back to Laplacian.")
        # Fallback: Laplacian variance
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            normalized = min(100.0, lap_var / 100.0)  # Scale typical var to 0-100
            self.logger.debug(f"Laplacian fallback: var={lap_var:.2f}, normalized={normalized:.2f} for {path}")
            return normalized
        except Exception as e:
            raise ImageQualityComputationError(
                f"Laplacian fallback failed for {path}: {str(e)}", path=path, original_error=e
            ) from e