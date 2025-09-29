"""
NIQE Image Quality Evaluator.

This module implements the NIQEImageQualityEvaluator class, which uses OpenCV's
QualityNIQE for blind/referenceless image quality assessment. NIQE extracts features
from the image and compares them to a pre-trained model derived from natural images.
Native scores are lower-better (closer to 0 means better quality); this implementation
normalizes to higher-better (0-100) for consistency with the ImageQualityEvaluator interface.

NIQE specifics:
- Blind metric based on natural scene statistics (NSS).
- Loads bundled model from niqe_model.xml in 'models/'.
- If model missing or load fails, it will raise an error, as NIQE requires a model.
  Unlike BRISQUE, there is no simple, universally accepted fallback like Laplacian variance
  that provides a similar quality assessment.

Usage Example:
    evaluator = NIQEImageQualityEvaluator()
    score = evaluator.evaluate('/path/to/image.jpg')  # e.g., 74.7 (higher = better quality)

Raises:
    ImageQualityFileError: If file not found, unreadable, or invalid image.
    ImageQualityComputationError: If model load or computation fails.
"""

import os
import cv2
import numpy as np
import textwrap
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from .base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.exceptions import ImageQualityFileError, ImageQualityComputationError
from pk_py_lib.core.logging import get_logger


_NIQE_MODEL_FILENAME = "niqe_model.xml"
_NIQE_RANGE_FILENAME = "niqe_range.xml"
_NIQE_MODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/cv/quality/niqe_model.xml"
_NIQE_RANGE_URL = "https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/cv/quality/niqe_range.xml"
_SIGNATURE_PREVIEW_BYTES = 96
_MIN_VALID_BYTES = 512


def _read_signature_preview(path: str, preview_bytes: int = _SIGNATURE_PREVIEW_BYTES) -> str:
    """
    Read a short ASCII preview of the file contents for diagnostic logging.

    Parameters
    ----------
    path : str
        Path to the file whose signature should be read.
    preview_bytes : int
        Number of bytes to read from the file head.

    Returns
    -------
    str
        ASCII-safe preview string with whitespace condensed for logs.
    """
    try:
        with open(path, "rb") as handle:
            snippet = handle.read(preview_bytes)
        sanitized = snippet.decode("ascii", errors="replace")
        sanitized = sanitized.replace("\r", "\\r").replace("\n", "\\n")
        return textwrap.shorten(sanitized, width=preview_bytes, placeholder="…")
    except Exception as exc:  # pragma: no cover - purely diagnostic
        return f"<error reading signature: {exc}>"


def _is_suspect_asset(path: str, signature: str, min_bytes: int = _MIN_VALID_BYTES) -> bool:
    """
    Determine whether the on-disk asset appears invalid or corrupted.

    Parameters
    ----------
    path : str
        Absolute path to the asset.
    signature : str
        Preview signature obtained from `_read_signature_preview`.
    min_bytes : int
        Minimum acceptable file size in bytes.

    Returns
    -------
    bool
        True if the asset looks invalid and should be repaired.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return True

    if size < min_bytes:
        return True

    lowered = signature.lower()
    if "404" in lowered or "not found" in lowered or "<html" in lowered:
        return True

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline().strip()
    except OSError:
        return True

    # NIQE models are XML files, check for XML declaration
    return not first_line.startswith("<?xml")


def _download_asset(destination: str, url: str) -> None:
    """
    Download the NIQE asset from the official OpenCV repository.

    Parameters
    ----------
    destination : str
        Destination path for the downloaded file.
    url : str
        Remote URL for the asset.

    Raises
    ------
    RuntimeError
        If the download fails or returns empty content.
    """
    try:
        with urlopen(url) as response:
            content = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} while downloading {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to reach {url}: {exc.reason}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Unexpected error while downloading {url}: {exc}") from exc

    if not content:
        raise RuntimeError(f"Downloaded zero bytes from {url}")

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with open(destination, "wb") as handle:
        handle.write(content)


def _ensure_asset(directory: str, filename: str, url: str, logger) -> str:
    """
    Ensure that a NIQE asset exists and is valid, repairing it if necessary.

    Parameters
    ----------
    directory : str
        Target directory containing the model assets.
    filename : str
        Name of the asset file.
    url : str
        Remote source URL for automatic repair.
    logger :
        Project logger instance for diagnostics.

    Returns
    -------
    str
        Absolute path to the validated asset.

    Raises
    ------
    RuntimeError
        If the asset cannot be downloaded or repaired.
    """
    os.makedirs(directory, exist_ok=True)
    asset_path = os.path.join(directory, filename)
    needs_repair = False

    if os.path.exists(asset_path):
        signature = _read_signature_preview(asset_path)
        size = os.path.getsize(asset_path)
        logger.debug(
            f"NIQE asset diagnostics: path={asset_path} size={size} signature='{signature}'"
        )
        if _is_suspect_asset(asset_path, signature):
            logger.warning(
                f"Detected invalid NIQE asset at {asset_path} (size={size}, signature='{signature}'); "
                f"attempting repair via {url}"
            )
            needs_repair = True
    else:
        logger.warning(
            f"NIQE asset missing: {asset_path}. Attempting to download from {url}"
        )
        needs_repair = True

    if needs_repair:
        _download_asset(asset_path, url)
        signature = _read_signature_preview(asset_path)
        size = os.path.getsize(asset_path)
        if _is_suspect_asset(asset_path, signature):
            raise RuntimeError(
                f"Asset {asset_path} remains invalid after download (size={size}, signature='{signature}')"
            )
        logger.info(
            f"Repaired NIQE asset at {asset_path} (size={size}, signature='{signature}')"
        )

    return asset_path


class NIQEImageQualityEvaluator(ImageQualityEvaluator):
    """
    NIQE-based image quality evaluator.

    Loads bundled XML model for QualityNIQE. NIQE scores are lower-better (closer to 0).
    Normalizes scores to higher-better scale (0-100).

    Args:
        None (uses bundled model).

    Attributes:
        niqe: The OpenCV QualityNIQE instance.
        logger: Project logger.

    Example:
        evaluator = NIQEImageQualityEvaluator()
        score = evaluator.evaluate('/path/to/img.jpg')  # e.g., 74.7 (higher = better quality)
    """

    @property
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm."""
        return "NIQE"

    def __init__(self):
        """
        Initialize the NIQE evaluator with validated bundled model assets.

        Ensures both niqe_model.xml and niqe_range.xml are present and valid.
        Automatically repairs corrupted assets by downloading the official OpenCV copies
        from the opencv_extra repository if they are missing or appear corrupted.

        Creates the NIQE evaluator using the file-path overload. If initialization fails,
        it raises a ImageQualityComputationError, as NIQE cannot function without its model.
        """
        self.logger = get_logger(__name__)
        self.niqe = None
        model_dir = os.path.join(os.path.dirname(__file__), "models")

        try:
            model_path = _ensure_asset(
                model_dir,
                _NIQE_MODEL_FILENAME,
                _NIQE_MODEL_URL,
                self.logger,
            )
            range_path = _ensure_asset(
                model_dir,
                _NIQE_RANGE_FILENAME,
                _NIQE_RANGE_URL,
                self.logger,
            )
            self.logger.debug(
                f"Initializing QualityNIQE with model='{model_path}' range='{range_path}'"
            )
            # QualityNIQE_create requires model and range paths
            self.niqe = cv2.quality.QualityNIQE_create(model_path, range_path)
            self.logger.info(
                "NIQE evaluator initialized successfully with bundled assets."
            )
        except Exception as exc:
            # Log the failure with full traceback for detailed diagnostics
            error_msg = "Failed to initialize NIQE evaluator. NIQE requires its model and cannot fall back."
            self.logger.error(error_msg, exception=exc, exc_info=True)
            # Re-raise as a computation error since the evaluator cannot be created
            raise ImageQualityComputationError(
                error_msg, path=model_dir, original_error=exc
            ) from exc

    def evaluate(self, path: str) -> float:
        """
        Evaluate the quality of the image at the given path using NIQE.

        NIQE scores are lower-better. Normalization: 100 - raw_score, clamped to 0-100.

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
            # OpenCV's QualityNIQE.compute() returns (score, features, ...).
            # Score can be a float or a 1-element sequence (tuple/list/ndarray).
            result = self.niqe.compute(image)
            
            # Extract the score component (first element of the result tuple)
            raw_score = result[0]
            
            # If the score component is a sequence (e.g., (score,)), extract the scalar value
            if isinstance(raw_score, (list, tuple, np.ndarray)):
                raw_score = raw_score[0]
            
            # Ensure final score is a float
            raw_score = float(raw_score)
            
            # NIQE is lower-better (0-100+). Normalize to higher-better (0-100).
            # We assume 0 is perfect quality (100 normalized).
            # Clamp the result to ensure it stays within 0-100 range.
            normalized = max(0.0, min(100.0, 100.0 - raw_score))
            
            self.logger.debug(f"NIQE raw: {raw_score:.2f}, normalized: {normalized:.2f} for {path}")
            return normalized
        except Exception as e:
            raise ImageQualityComputationError(
                f"NIQE computation failed for {path}: {str(e)}", path=path, original_error=e
            ) from e


__all__ = ["NIQEImageQualityEvaluator"]