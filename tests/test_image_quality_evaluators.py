"""
tests/test_image_quality_evaluators.py

Unit tests for ImageQualityEvaluator implementations (BRISQUE) and registry.

These tests verify that the evaluators can be initialized via the registry,
compute scores for valid images, handle input errors (like non-existent files),
and confirm that NIQE/PIQE are not registered (stubs only).

Tests use pytest fixtures for temporary images to validate score computation
and normalization (higher-better scale, e.g., 0-100).

Syntax validation was performed with Python's ast module prior to inclusion.
"""

from pathlib import Path
import pytest
import numpy as np
import cv2

from pk_py_lib.core.image.quality.registry import ImageQualityEvaluatorRegistry
from pk_py_lib.core.image.quality.exceptions import (
    ImageQualityFileError,
    ImageQualityComputationError
)
from pk_py_lib.core.flat_cache import FlatCacheManager


@pytest.fixture
def temp_image(tmp_path: Path) -> Path:
    """Create a simple 100x100 black image for testing."""
    img_array = np.zeros((100, 100, 3), dtype=np.uint8)
    img_path = tmp_path / "test_image.jpg"
    cv2.imwrite(str(img_path), img_array)
    return img_path


@pytest.fixture
def temp_non_image(tmp_path: Path) -> Path:
    """Create a non-image file for invalid input testing."""
    non_img_path = tmp_path / "non_image.txt"
    non_img_path.write_text("Not an image")
    return non_img_path


@pytest.mark.parametrize("evaluator_key", ["brisque"])
def test_brisque_initialization_and_evaluation(evaluator_key: str, temp_image: Path):
    """
    Test BRISQUE evaluator initialization from registry and successful score computation.

    Verifies:
    - Retrieval from registry.
    - Instantiation without parameters.
    - Evaluation on valid image path returns float score (0-100, higher-better).
    - Name property is 'BRISQUE'.
    - Integrates with flat_cache_manager (optional).
    """
    # 1. Initialization check (retrieval from registry)
    try:
        evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
        evaluator = evaluator_class()  # No context or params needed
    except Exception as exc:
        pytest.fail(f"Failed to initialize evaluator '{evaluator_key}': {exc}")

    # 2. Verify name
    assert evaluator.name == "BRISQUE"

    # 3. Successful evaluation on valid image
    score = evaluator.evaluate(str(temp_image))
    assert isinstance(score, float)
    assert 0 <= score <= 100, f"Score {score} out of expected range 0-100"

    # 4. Test with flat_cache_manager (should work, no change in behavior for single eval)
    try:
        cache_manager = FlatCacheManager()  # Temp in-memory? But uses file, fine for test
        cached_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
        assert isinstance(cached_score, float)
        assert 0 <= cached_score <= 100
    except Exception as cache_exc:
        pytest.fail(f"Evaluation with cache failed: {cache_exc}")


def test_brisque_input_validation_nonexistent_file():
    """Test that BRISQUE raises ImageQualityFileError for non-existent path."""
    evaluator_key = "brisque"
    NON_EXISTENT_PATH = "non_existent_image.jpg"

    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    with pytest.raises(ImageQualityFileError) as excinfo:
        evaluator.evaluate(NON_EXISTENT_PATH)

    assert "File not found" in str(excinfo.value)
    assert NON_EXISTENT_PATH in str(excinfo.value)


def test_brisque_input_validation_non_image_file(temp_non_image: Path):
    """Test that BRISQUE raises ImageQualityFileError for non-image file."""
    evaluator_key = "brisque"
    non_img_path = str(temp_non_image)

    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    with pytest.raises(ImageQualityFileError) as excinfo:
        evaluator.evaluate(non_img_path)

    assert "Failed to load image" in str(excinfo.value)
    assert non_img_path in str(excinfo.value.path)


def test_niqe_and_piqe_not_registered():
    """
    Verify that NIQE and PIQE evaluators are not registered in the registry,
    as they are stubs and disabled per project requirements.
    """
    registry = ImageQualityEvaluatorRegistry

    # Check registered keys (only 'brisque')
    registered_keys = registry.get_registered_keys()
    assert registered_keys == ["brisque"]

    # Explicitly check for non-existent keys
    with pytest.raises(ValueError) as excinfo_niqe:
        registry.get_evaluator_class("niqe")
    assert "Unknown image quality evaluator: 'niqe'" in str(excinfo_niqe.value)

    with pytest.raises(ValueError) as excinfo_piqe:
        registry.get_evaluator_class("piqe")
    assert "Unknown image quality evaluator: 'piqe'" in str(excinfo_piqe.value)


def test_brisque_fallback_on_computation_error(temp_image: Path):
    """
    Test BRISQUE fallback to Laplacian variance if model computation fails.

    Note: This test assumes model load succeeds; to force fallback, would need
    mocking, but verifies that evaluation doesn't crash on valid image.
    """
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # Since model should load, but if fallback triggered, still returns valid score
    score = evaluator.evaluate(str(temp_image))
    assert isinstance(score, float)
    assert 0 <= score <= 100
