"""
NIQE Image Quality Evaluator (STUBBED).

This module contains a non-functional stub for the NIQEImageQualityEvaluator.
The implementation is disabled to prevent registration and usage due to external
library compatibility issues or project requirements. It is kept as a reference
for future implementation.

Attempting to instantiate this class will raise an ImageQualityComputationError.
"""

import os
from .base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.exceptions import ImageQualityComputationError
from pk_py_lib.core.logging import get_logger


class NIQEImageQualityEvaluator(ImageQualityEvaluator):
    """
    NIQE-based image quality evaluator (STUB).

    This class is a non-functional stub. It raises an error upon initialization
    to ensure it is not used in the application.
    """

    @property
    def name(self) -> str:
        """The human-readable name of the quality evaluation algorithm."""
        return "NIQE"

    def __init__(self):
        """
        Initialize the NIQE evaluator.

        Raises
        ------
        ImageQualityComputationError
            Always raised to indicate that this evaluator is currently disabled.
        """
        self.logger = get_logger(__name__)
        error_msg = "NIQE evaluator is currently disabled and cannot be initialized."
        self.logger.error(error_msg)
        raise ImageQualityComputationError(
            error_msg, path="N/A", original_error=NotImplementedError(error_msg)
        )

    def evaluate(self, path: str) -> float:
        """
        Evaluate the quality of the image at the given path using NIQE.

        Raises
        ------
        ImageQualityComputationError
            Always raised to indicate that this evaluator is currently disabled.
        """
        error_msg = "NIQE evaluator is currently disabled and cannot compute scores."
        raise ImageQualityComputationError(
            error_msg, path=path, original_error=NotImplementedError(error_msg)
        )


__all__ = ["NIQEImageQualityEvaluator"]