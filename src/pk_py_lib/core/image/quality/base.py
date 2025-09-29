"""
src/pk_py_lib/core/image/quality/base.py

Abstract base class for image quality evaluators in the pk_py_lib image subsystem.

This module defines the ImageQualityEvaluator ABC, providing a pluggable interface for
different quality assessment algorithms. Subclasses implement specific metrics (e.g., BRISQUE)
and must handle file validation, image loading with cv2.imread, error raising via the
ImageQualityError hierarchy, and logging with the project's logger.

The design ensures extensibility: new evaluators can be registered without modifying core code.
All evaluators operate on image file paths, returning a float score normalized such that higher values indicate higher image quality (implementation-specific scale, e.g., 0-100 where 100 is perfect quality). Subclasses must normalize their native scores accordingly. Edge cases like invalid paths, non-image files, empty images, or corrupted data must be handled by raising appropriate exceptions.
"""

from abc import ABC, abstractmethod
from typing import Any


class ImageQualityEvaluator(ABC):
    """Abstract base class for image quality evaluation.
    
    This interface defines the contract for pluggable image quality assessors. Subclasses must
    implement the evaluate method to compute a quality score for a given image file path.
    All subclasses must normalize their scores such that higher values indicate higher image quality
    for consistency across the pluggable system.
    
    Key responsibilities of implementations:
    - Validate the input path (exists, is file, readable).
    - Load the image using cv2.imread(path, cv2.IMREAD_COLOR) or equivalent.
    - Compute the quality metric, handling any library-specific errors.
    - Normalize the native score to higher-better scale (e.g., 0-100 where 100 is perfect).
    - Log evaluation events (success, warnings) using get_logger() from pk_py_lib.core.logging.
    - Raise ImageQualityError subclasses on failures, including path and original error details.
    
    Extensibility: Subclasses can support different scales/metrics but must normalize to higher-better
    (e.g., invert BRISQUE's lower-better 0-100). The registry system allows runtime selection via settings.
    
    Usage
    -----
    # Instantiate a concrete evaluator (e.g., via provider)
    evaluator = BRISQUEImageQualityEvaluator()
    
    # Evaluate an image
    try:
        score = evaluator.evaluate("/path/to/image.jpg")
        print(f"Quality score: {score}")  # e.g., 74.7 (higher is better)
    except ImageQualityError as e:
        print(f"Evaluation failed: {e}")
    
    Notes
    -----
    - Always handle edge cases: non-existent paths, non-image files (e.g., .txt), empty/corrupted images.
    - Use 4-space indentation, rich comments, and full PyDoc in subclasses.
    - No performance optimizations needed; prioritize correctness and logging.
    - Normalization ensures extensibility: future evaluators follow the higher-better convention.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm (e.g., 'BRISQUE').
        
        This property must be implemented by subclasses and should return a constant string.
        It is used for logging, UI display, and identifying the metric used in results.
        
        Returns
        -------
        str
            The name of the algorithm.
        """
        pass

    @abstractmethod
    def evaluate(self, path: str) -> float:
        """Evaluate the quality of the image at the given path.
        
        This method performs file validation, loads the image, computes the quality score,
        normalizes it such that higher values indicate higher quality, and logs the result.
        Implementations must ensure thread-safety if used concurrently.
        
        Parameters
        ----------
        path : str
            The absolute or relative path to the image file to evaluate.
            Supports common formats like JPG, PNG, etc., via cv2.imread.
        
        Returns
        -------
        float
            A normalized quality score such that higher values indicate higher image quality
            (implementation-specific scale, e.g., 0-100 where 100 is perfect quality).
            Subclasses must normalize their native scores accordingly.
            For example, BRISQUE native (lower-better) is inverted to higher-better.
        
        Raises
        ------
        ImageQualityFileError
            If the path is invalid, file not found, unreadable, or not an image (e.g., cv2.imread returns None).
        ImageQualityComputationError
            If image loading succeeds but quality computation fails (e.g., corrupted data, OpenCV error).
        ImageQualityError
            Base class for other quality-related failures.
        
        Examples
        --------
        # Successful evaluation
        score = evaluator.evaluate("/home/user/photo.jpg")  # Returns e.g., 84.3 (higher is better)
        
        # Handling file error
        try:
            score = evaluator.evaluate("/nonexistent.jpg")
        except ImageQualityFileError as e:
            # e.path == "/nonexistent.jpg", e.original_error may be FileNotFoundError
            logger.error(f"File evaluation failed: {e}")
        
        # Handling computation error (e.g., empty image)
        try:
            score = evaluator.evaluate("/corrupt.jpg")
        except ImageQualityComputationError as e:
            logger.warning(f"Computation failed for {e.path}: {e.original_error}")
        """
        # Abstract method: no implementation here
        # Subclasses must override with concrete logic
        # Inline comment: Ensure logging at DEBUG/INFO level for scores, ERROR for failures
        pass


__all__ = ["ImageQualityEvaluator"]