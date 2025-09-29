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
import textwrap
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from .base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.exceptions import ImageQualityFileError, ImageQualityComputationError
from pk_py_lib.core.logging import get_logger
from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheEntry, FlatCacheDBError
from pathlib import Path


_BRISQUE_MODEL_FILENAME = "brisque_model_live.yml"
_BRISQUE_RANGE_FILENAME = "brisque_range_live.yml"
_BRISQUE_MODEL_URL = "https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/cv/quality/brisque_model_live.yml"
_BRISQUE_RANGE_URL = "https://raw.githubusercontent.com/opencv/opencv_extra/4.x/testdata/cv/quality/brisque_range_live.yml"
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

    return not first_line.startswith("%YAML")


def _download_asset(destination: str, url: str) -> None:
    """
    Download the BRISQUE asset from the official OpenCV repository.

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
    Ensure that a BRISQUE asset exists and is valid, repairing it if necessary.

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
            f"BRISQUE asset diagnostics: path={asset_path} size={size} signature='{signature}'"
        )
        if _is_suspect_asset(asset_path, signature):
            logger.warning(
                f"Detected invalid BRISQUE asset at {asset_path} (size={size}, signature='{signature}'); "
                f"attempting repair via {url}"
            )
            needs_repair = True
    else:
        logger.warning(
            f"BRISQUE asset missing: {asset_path}. Attempting to download from {url}"
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
            f"Repaired BRISQUE asset at {asset_path} (size={size}, signature='{signature}')"
        )

    return asset_path


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

    @property
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm."""
        return "BRISQUE"

    def __init__(self):
        """
        Initialize the BRISQUE evaluator with validated bundled model assets.

        Ensures both brisque_model_live.yml and brisque_range_live.yml are present and valid.
        Automatically repairs corrupted assets by downloading the official OpenCV copies
        from the opencv_extra repository if they are missing or appear corrupted (e.g., HTML content).
        
        Creates the BRISQUE evaluator using the file-path overload to leverage OpenCV's
        native parsing of the SVM and range data. Falls back to Laplacian variance if any
        step fails despite repair attempts, with detailed error logging including traceback.
        """
        self.logger = get_logger(__name__)
        self.brisque = None
        model_dir = os.path.join(os.path.dirname(__file__), "models")

        try:
            model_path = _ensure_asset(
                model_dir,
                _BRISQUE_MODEL_FILENAME,
                _BRISQUE_MODEL_URL,
                self.logger,
            )
            range_path = _ensure_asset(
                model_dir,
                _BRISQUE_RANGE_FILENAME,
                _BRISQUE_RANGE_URL,
                self.logger,
            )
            self.logger.debug(
                f"Initializing QualityBRISQUE with model='{model_path}' range='{range_path}'"
            )
            self.brisque = cv2.quality.QualityBRISQUE_create(model_path, range_path)
            self.logger.info(
                "BRISQUE evaluator initialized successfully with bundled assets."
            )
        except Exception as exc:
            # Log the failure with full traceback for detailed diagnostics
            self.logger.error(
                "Failed to initialize BRISQUE evaluator. Falling back to Laplacian variance.",
                exception=exc,
                exc_info=True
            )
            self.brisque = None

    def evaluate(self, path: str, flat_cache_manager: Optional[FlatCacheManager] = None) -> float:
        """
        Evaluate the quality of the image at the given path using BRISQUE or fallback.

        Supports caching via FlatCacheManager, checking for a valid 'brisque_score'
        before computation.

        If BRISQUE loaded:
            - Loads image, computes raw score (lower = better).
            - Normalizes: 100 - raw, clamped to 0-100.

        Fallback (Laplacian):
            - Grayscale, Laplacian variance (higher = sharper/better).
            - Normalizes: min(100, var / 100) (empirical for 0-10000 var range).

        Args:
            path (str): Path to image file.
            flat_cache_manager (Optional[FlatCacheManager]): Optional FlatCacheManager instance
                to check and store the quality score.

        Returns:
            float: Normalized quality score (0-100, higher = better).

        Raises:
            ImageQualityFileError: File/loading issues.
            ImageQualityComputationError: Computation failures.

        Example:
            score = evaluator.evaluate('/path/to/blurry.jpg')  # e.g., 45.2 (low sharpness)
        """
        # --- 1. Check Flat Cache (Priority) ---
        if flat_cache_manager:
            try:
                entry = flat_cache_manager.get_entry(path)
                if entry and entry.brisque_score is not None and entry.quality_algorithm == self.name:
                    self.logger.debug(f"Flat cache hit for {self.name} on {path}")
                    return entry.brisque_score
            except FlatCacheDBError as e:
                self.logger.warning(f"Flat cache DB error during {self.name} lookup for {path}. Error: {e}")
            except Exception as e:
                self.logger.warning(f"Unexpected error during flat cache {self.name} lookup for {path}. Error: {e}")

        # File validation
        if not os.path.exists(path):
            raise ImageQualityFileError(f"File not found: {path}", path=path)
        if not os.path.isfile(path):
            raise ImageQualityFileError(f"Not a file: {path}", path=path)

        # Load image
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ImageQualityFileError(f"Failed to load image: {path}", path=path)

        normalized_score = None

        if self.brisque is not None:
            try:
                # OpenCV's QualityBRISQUE.compute() returns (score, features, ...).
                # Score can be a float or a 1-element sequence (tuple/list/ndarray).
                result = self.brisque.compute(image)
                
                # Extract the score component (first element of the result tuple)
                raw_score = result[0]
                
                # If the score component is a sequence (e.g., (score,)), extract the scalar value
                if isinstance(raw_score, (list, tuple, np.ndarray)):
                    raw_score = raw_score[0]
                
                # Ensure final score is a float
                raw_score = float(raw_score)
                normalized_score = max(0.0, min(100.0, 100.0 - raw_score))
                self.logger.debug(f"BRISQUE raw: {raw_score:.2f}, normalized: {normalized_score:.2f} for {path}")
            except Exception as e:
                self.logger.warning(f"BRISQUE compute failed for {path}: {str(e)}. Falling back to Laplacian.")
        
        # Fallback: Laplacian variance
        if normalized_score is None:
            try:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                normalized_score = min(100.0, lap_var / 100.0)  # Scale typical var to 0-100
                self.logger.debug(f"Laplacian fallback: var={lap_var:.2f}, normalized={normalized_score:.2f} for {path}")
            except Exception as e:
                raise ImageQualityComputationError(
                    f"Laplacian fallback failed for {path}: {str(e)}", path=path, original_error=e
                ) from e

        # --- 2. Update Flat Cache ---
        if flat_cache_manager and normalized_score is not None:
            try:
                # Get current entry or create a new one with file stats
                current_entry = flat_cache_manager.get_entry(path)
                if current_entry is None:
                    # If get_entry failed validation or was missing, create a new base entry
                    # Note: We rely on FlatCacheManager's internal _get_file_stats, but we need to handle the case
                    # where get_entry returns None due to validation failure, but the file still exists.
                    # Since we already validated file existence above, we can safely call _get_file_stats.
                    size, mtime, inode, device = flat_cache_manager._get_file_stats(path)
                    current_entry = FlatCacheEntry(
                        file=path, size=size, mod_date=mtime, file_inode=inode, file_device=device
                    )
                
                current_entry.brisque_score = normalized_score
                current_entry.quality_algorithm = self.name
                flat_cache_manager.set_entry(current_entry)
                self.logger.debug(f"Flat cache updated for {self.name} on {path}")
            except Exception as e:
                self.logger.warning(f"Failed to update flat cache for {self.name} on {path}: {e}")

        return normalized_score