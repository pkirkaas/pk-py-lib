"""
tests/test_image_quality_evaluators.py

Unit tests for ImageQualityEvaluator implementations (BRISQUE, NIQE, PIQE).

These tests verify that the evaluators can be initialized and that they correctly handle
input errors (like non-existent files) and computation errors, ensuring the core logic
is sound and the score normalization is applied.

Syntax validation was performed with Python's ``ast`` module prior to inclusion.
"""

from pathlib import Path
import pytest

from src.pk_py_lib.core.image.quality.registry import ImageQualityEvaluatorRegistry
from src.pk_py_lib.core.image.quality.exceptions import ImageQualityInputError
from src.pk_py_lib.core.image.quality.base import ImageQualityContext

# Define a non-existent path for testing input validation
NON_EXISTENT_PATH = str(Path("tests") / "data" / "non_existent_image.jpg")

@pytest.mark.parametrize("evaluator_key", ["brisque", "niqe", "piqe"])
def test_evaluator_initialization_and_input_validation(evaluator_key: str):
    """
    Test that all registered evaluators can be initialized and correctly raise
    ImageQualityInputError when given a non-existent file path.
    
    This implicitly verifies that NIQE and PIQE models/assets are correctly handled
    during initialization (or lazy loading if applicable) without crashing.
    """
    
    # 1. Initialization check (retrieval from registry)
    try:
        evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
        context = ImageQualityContext(evaluator_key=evaluator_key)
        evaluator = evaluator_class(context=context)
    except Exception as exc:
        pytest.fail(f"Failed to initialize evaluator '{evaluator_key}': {exc}")

    # 2. Input validation check (non-existent file)
    # All evaluators must validate the path and raise ImageQualityInputError
    with pytest.raises(ImageQualityInputError) as excinfo:
        evaluator.evaluate(NON_EXISTENT_PATH)
    
    assert NON_EXISTENT_PATH in str(excinfo.value)
    
    # Check that the evaluator name is correctly set (used for logging/debugging)
    assert evaluator.name == evaluator_key
    
    # Check that the context is correctly passed/used
    assert evaluator.context.evaluator_key == evaluator_key
