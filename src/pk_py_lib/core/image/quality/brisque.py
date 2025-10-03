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
from PIL import Image
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

        This evaluator uses OpenCV's QualityBRISQUE for blind image quality assessment based on natural
        scene statistics (NSS). It loads a pre-trained SVM model from bundled assets in 'models/'.
        Native BRISQUE scores are in [0, 100] with lower values indicating better quality; this
        implementation normalizes them to [0, 1] where higher values indicate better perceived quality
        for consistency with the ImageQualityEvaluator interface: normalized_score = max(0, min(1, (100 - raw) / 100)).

        Robustness Improvements:
        - Robust image loading: Attempts cv2.imread first; falls back to PIL.Image.open() for problematic
          formats like palette PNGs with transparency (e.g., 1x400 narrow PNGs that fail OpenCV loading).
        - Pre-computation checks: Skips BRISQUE computation for images with extreme dimensions (width/height < 2)
          or aspect ratios > 100 (e.g., narrow 1x400 PNGs), logging a warning and using Laplacian variance fallback.
        - Padding for small images: If min(width, height) < 8 pixels, pads with BORDER_REFLECT_101 to ensure
          filter kernels (e.g., for NSS extraction) do not trigger OpenCV assertion failures during resize.
        - Fallback logic: If BRISQUE model loading or computation fails (e.g., due to OpenCV errors on invalid images),
          or for skipped cases, computes Laplacian variance on grayscale (higher variance = sharper/better) and normalizes
          empirically: min(1.0, (variance / 100.0) / 100.0), suitable for typical image variances (e.g., ~0.05-0.5 for narrow PNGs).
        - Enhanced logging: Detailed warnings for fallbacks, including image shape, aspect ratio, and error traces.

        Args:
            None (uses bundled model or fallback).

        Attributes:
            brisque: The OpenCV QualityBRISQUE instance (or None if fallback).
            logger: Project logger.

        Example:
            evaluator = BRISQUEImageQualityEvaluator()
            score = evaluator.evaluate('/path/to/high_quality.jpg')  # e.g., 0.747 (BRISQUE normalized)
            score_narrow = evaluator.evaluate('/path/to/narrow_palette.png')  # e.g., 0.123 (Laplacian fallback for 1x400 PNG)
        """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

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
            self.logger.debug(
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

        Supports caching via FlatCacheManager: before computing the BRISQUE (or fallback Laplacian)
        score, checks the cache for an existing valid entry with a non-None 'brisque' value.
        The entry is validated against current file stats (size, mtime) by get_entry().
        If valid cached score exists, returns it immediately without recomputing.
        After successful computation, stores the normalized score in the 'brisque' field
        of the cache entry and persists it.

        Behavior:
        - If BRISQUE loaded successfully and image passes pre-checks:
          - Loads image robustly (cv2.imread with PIL fallback for palette PNGs/transparency issues).
          - Performs dimension pre-check: skips BRISQUE if width/height < 2 or aspect ratio > 100 (e.g., narrow 1x400 PNGs).
          - Pads small images (<8px min dimension) to avoid OpenCV resize assertions.
          - Computes raw BRISQUE score (0-100, lower = better), normalizes to [0, 1] higher-better: (100 - raw) / 100.
        - For invalid/narrow images or BRISQUE failures: falls back to Laplacian variance on grayscale
          (higher variance = sharper/better), normalized empirically: min(1.0, (var / 100.0) / 100.0).
          Example: Narrow palette PNGs (e.g., 1x400) typically yield ~0.05-0.5 via fallback.
        - The fallback score is also cached under 'brisque' as it represents this evaluator's output.
        - Enhanced logging for fallbacks, including shape, aspect, and errors.

        Args:
            path (str): Absolute or relative path to the image file.
            flat_cache_manager (Optional[FlatCacheManager]): Optional instance for caching.
                If provided, enables read/write of 'brisque' scores. Defaults to None (no caching).

        Returns:
            float: Normalized quality score in [0, 1], where higher values indicate better perceived quality.

        Raises:
            ImageQualityFileError: If the file does not exist, is not a valid file, or cannot be loaded as an image
                (even with PIL fallback).
            ImageQualityComputationError: If both BRISQUE and fallback computations fail (e.g., invalid image data).

        Examples:
            >>> evaluator = BRISQUEImageQualityEvaluator()
            >>> score = evaluator.evaluate('/path/to/high_quality.jpg')  # e.g., 0.853 (BRISQUE, cached on second call)
            >>> score_narrow = evaluator.evaluate('/path/to/1x400_palette.png')  # e.g., 0.123 (Laplacian fallback)
            >>> score_no_cache = evaluator.evaluate('/path/to/low_quality.jpg', flat_cache_manager=None)  # Computes fresh, no cache
        """
        # --- 1. Check Flat Cache First (Avoid Unnecessary Computation) ---
        # Retrieve and validate cache entry; if 'brisque' is set, it's considered valid for this evaluator
        # as get_entry() already ensures file stats match (freshness check).
        if flat_cache_manager:
            try:
                entry = flat_cache_manager.get_entry(path)
                if entry and entry.brisque is not None:
                    self.logger.debug(f"Cache hit: Returning stored BRISQUE score {entry.brisque:.2f} for {path}")
                    return entry.brisque
            except FlatCacheDBError as exc:
                self.logger.warning(f"Database error during cache lookup for {self.name} on {path}: {exc}")
            except Exception as exc:
                self.logger.warning(f"Unexpected error in cache lookup for {self.name} on {path}: {exc}")

            self.logger.debug(f"Cache miss for {self.name} on {path}; proceeding to compute")

        # File validation
        if not os.path.exists(path):
            raise ImageQualityFileError(f"File not found: {path}", path=path)
        if not os.path.isfile(path):
            raise ImageQualityFileError(f"Not a file: {path}", path=path)

        # Robust image loading: Try OpenCV first, fallback to PIL for problematic formats
        # (e.g., palette PNGs with transparency, GIF files, narrow images that fail cv2.imread)
        image = cv2.imread(path, cv2.IMREAD_COLOR)

        # Check if file extension indicates potentially problematic formats
        file_ext = Path(path).suffix.lower()
        problematic_formats = {'.gif', '.png', '.tiff', '.tif', '.bmp'}

        if (image is None or len(image.shape) != 3 or image.shape[0] <= 0 or image.shape[1] <= 0 or
            file_ext in problematic_formats):
            try:
                # Enhanced PIL fallback with format-specific handling
                pil_img = Image.open(path)

                # Handle GIF animations by taking first frame
                if file_ext == '.gif' and hasattr(pil_img, 'is_animated') and pil_img.is_animated:
                    pil_img.seek(0)  # Ensure we're on the first frame
                    self.logger.debug(f"Processing first frame of animated GIF: {path}")

                # Convert to RGB mode to ensure compatibility
                if pil_img.mode not in ('RGB', 'RGBA', 'L'):
                    pil_img = pil_img.convert('RGB')

                # Convert to numpy array and then to BGR for OpenCV
                image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                self.logger.debug(f"Loaded via PIL fallback for {path}, shape={image.shape}, original_mode={pil_img.mode}")
            except Exception as pil_exc:
                raise ImageQualityFileError(f"Failed to load image with OpenCV and PIL fallback: {path}", path=path) from pil_exc

        # Dimension pre-check: Skip BRISQUE for extreme cases to avoid OpenCV errors
        # (e.g., width/height < 2 or aspect > 100, common in narrow palette PNGs like 1x400)
        h, w = image.shape[:2]
        aspect_ratio = max(h / w if w > 0 else float('inf'), w / h if h > 0 else float('inf'))

        normalized_score = None
        if w < 2 or h < 2 or aspect_ratio > 100:
            self.logger.warning(
                f"Image too narrow or extreme aspect for BRISQUE: {path} (h={h}, w={w}, aspect={aspect_ratio:.1f}). "
                f"Using Laplacian fallback to avoid OpenCV resize assertions."
            )
            # Fallback: Laplacian variance (no BRISQUE computation)
            try:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                normalized_score = min(1.0, (lap_var / 100.0) / 100.0)  # Scale typical var to 0-1
                self.logger.debug(f"Laplacian fallback (extreme dims): var={lap_var:.2f}, normalized={normalized_score:.3f} for {path}")
            except Exception as e:
                raise ImageQualityComputationError(
                    f"Laplacian fallback failed for extreme image {path}: {str(e)}", path=path, original_error=e
                ) from e
        else:
            # Padding logic for very small images: Ensures min dimension >=8px for BRISQUE filters
            # (prevents assertion failures in OpenCV's internal resize for NSS extraction)
            if min(h, w) < 8:
                target_size = 8
                pad_h = max(0, target_size - h)
                pad_w = max(0, target_size - w)
                top = pad_h // 2
                bottom = pad_h - top
                left = pad_w // 2
                right = pad_w - left
                image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_REFLECT_101)
                self.logger.debug(
                    f"Padded small image for BRISQUE: {path} from ({h},{w}) to ({image.shape[0]},{image.shape[1]})"
                )

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
                    # Normalize BRISQUE: raw is 0-100 lower-better; convert to 0-1 higher-better
                    normalized_score = max(0.0, min(1.0, (100.0 - raw_score) / 100.0))
                    self.logger.debug(f"BRISQUE raw: {raw_score:.2f}, normalized: {normalized_score:.3f} for {path}")
                except Exception as e:
                    self.logger.warning(
                        f"BRISQUE compute failed for {path}: {e}. Image shape: {getattr(image, 'shape', 'None')}. "
                        f"Falling back to Laplacian variance.", exc_info=True
                    )
            
            # Fallback: Laplacian variance
            if normalized_score is None:
                try:
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                    normalized_score = min(1.0, (lap_var / 100.0) / 100.0)  # Scale typical var to 0-1
                    self.logger.debug(f"Laplacian fallback: var={lap_var:.2f}, normalized={normalized_score:.3f} for {path}")
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
                    size, mtime = flat_cache_manager._get_file_stats(path)
                    current_entry = FlatCacheEntry(
                        path=path, size=size, mtime=mtime
                    )
                
                current_entry.brisque = normalized_score
                flat_cache_manager.set_entry(current_entry)
                self.logger.debug(f"Flat cache updated for {self.name} on {path}")
            except Exception as e:
                self.logger.warning(f"Failed to update flat cache for {self.name} on {path}: {e}")

        return normalized_score