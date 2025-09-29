"""
PIQE Image Quality Evaluator (STUBBED).

This module contains a non-functional stub for the PIQEImageQualityEvaluator.
The implementation is disabled to prevent registration and usage due to external
library compatibility issues or project requirements. It is kept as a reference
for future implementation.

Attempting to instantiate this class will raise an ImageQualityComputationError.
"""

import os
from .base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.exceptions import ImageQualityComputationError
from pk_py_lib.core.logging import get_logger
from pk_py_lib.core.flat_cache import FlatCacheManager
from typing import Optional


class PIQEImageQualityEvaluator(ImageQualityEvaluator):
    """
    PIQE-based image quality evaluator (STUB).

    This class is a non-functional stub. It raises an error upon initialization
    to ensure it is not used in the application.
    """

    @property
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm."""
        return "PIQE"

    # Since this is a stub, we explicitly mark it as unavailable to prevent conditional registration
    # in the registry, even if the underlying OpenCV library might have the class.
    IS_AVAILABLE = False

    def __init__(self):
        """
        Initialize the PIQE evaluator.

        Raises
        ------
        ImageQualityComputationError
            Always raised to indicate that this evaluator is currently disabled.
        """
        self.logger = get_logger(__name__)
        error_msg = "PIQE evaluator is currently disabled and cannot be initialized."
        self.logger.error(error_msg)
        raise ImageQualityComputationError(
            error_msg, path="N/A", original_error=NotImplementedError(error_msg)
        )

    def evaluate(self, path: str, flat_cache_manager: Optional[FlatCacheManager] = None) -> float:
        """
        Evaluate the quality of the image at the given path using PIQE.

        Parameters
        ----------
        path : str
            The absolute or relative path to the image file to evaluate.
        flat_cache_manager : Optional[FlatCacheManager]
            Optional FlatCacheManager instance (ignored as this is a stub).

        Raises
        ------
        ImageQualityComputationError
            Always raised to indicate that this evaluator is currently disabled.
        """
        error_msg = "PIQE evaluator is currently disabled and cannot compute scores."
        # Note: flat_cache_manager is accepted for API compatibility but ignored.
        raise ImageQualityComputationError(
            error_msg, path=path, original_error=NotImplementedError(error_msg)
        )


__all__ = ["PIQEImageQualityEvaluator"]