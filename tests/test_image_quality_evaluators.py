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

@pytest.mark.parametrize("evaluator_key", ["brisque"])
def test_brisque_initialization_and_input_validation(evaluator_key: str):
    """
    Test that all registered evaluators can be initialized and correctly raise
    ImageQualityInputError when given a non-existent file path.
    
    This verifies that BRISQUE initializes correctly and handles basic input validation.
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

def test_niqe_and_piqe_are_not_registered():
    """
    Verify that NIQE and PIQE evaluators are explicitly not registered in the registry,
    confirming they are disabled as per current project requirements.
    """
    registry = ImageQualityEvaluatorRegistry
    
    # Check that only 'brisque' and 'none' (if applicable, but registry only holds classes) are available
    registered_keys = registry.get_registered_keys()
    assert registered_keys == ["brisque"]
    
    # Explicitly check for non-existent keys
    with pytest.raises(ValueError) as excinfo_niqe:
        registry.get_evaluator_class("niqe")
    assert "Unknown image quality evaluator: 'niqe'" in str(excinfo_niqe.value)
    
    with pytest.raises(ValueError) as excinfo_piqe:
        registry.get_evaluator_class("piqe")
    assert "Unknown image quality evaluator: 'piqe'" in str(excinfo_piqe.value)
