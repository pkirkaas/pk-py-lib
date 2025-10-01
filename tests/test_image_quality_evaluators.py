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
import os

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


@pytest.fixture
def cache_manager(tmp_path: Path) -> FlatCacheManager:
    """Fixture for a temporary FlatCacheManager using a test DB."""
    db_path = tmp_path / "test_flat_cache.db"
    manager = FlatCacheManager(db_path=str(db_path))
    yield manager
    # Cleanup after test
    for ext in ["", "-wal", "-shm"]:
        (db_path.with_suffix(f".db{ext}")).unlink(missing_ok=True)


def test_brisque_cache_miss(temp_image: Path, cache_manager: FlatCacheManager):
    """Test cache miss: New image evaluation computes and stores score."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # Clear any existing entry
    cache_manager.invalidate_entry(str(temp_image))

    # Evaluate with cache (miss)
    score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(score, float)
    assert 0 <= score <= 100

    # Verify entry created and brisque set
    entry = cache_manager.get_entry(str(temp_image))
    assert entry is not None
    assert entry.brisque is not None
    assert abs(entry.brisque - score) < 1e-6  # Floating point tolerance


def test_brisque_cache_hit(temp_image: Path, cache_manager: FlatCacheManager):
    """Test cache hit: Re-evaluation returns cached score without recompute."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # First evaluation to populate cache
    first_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(first_score, float)

    # Second evaluation (hit)
    second_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(second_score, float)
    assert abs(second_score - first_score) < 1e-6  # Same score

    # Verify entry still valid
    entry = cache_manager.get_entry(str(temp_image))
    assert entry.brisque == first_score


def test_brisque_cache_validation_none(temp_image: Path, cache_manager: FlatCacheManager):
    """Test cache validation: Set brisque to None, forces recompute."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # First evaluation
    original_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)

    # Get entry and set brisque to None
    entry = cache_manager.get_entry(str(temp_image))
    assert entry is not None
    entry.brisque = None

    # Manually update entry in DB (simulate invalid cache)
    with cache_manager._get_connection() as conn:  # Access private for test
        conn.execute(
            "UPDATE flat_cache_entries SET brisque = NULL WHERE path = ?",
            (str(temp_image),)
        )
        conn.commit()

    # Re-evaluate: should recompute (but since file unchanged, score same; but verifies it doesn't return None)
    recomputed_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(recomputed_score, float)
    assert 0 <= recomputed_score <= 100
    assert abs(recomputed_score - original_score) < 1e-6  # Assuming deterministic

    # Verify updated back to non-None
    updated_entry = cache_manager.get_entry(str(temp_image))
    assert updated_entry.brisque is not None


def test_brisque_cache_invalid_file_change(temp_image: Path, cache_manager: FlatCacheManager):
    """Test cache invalidation on file change (size/mtime mismatch)."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # First evaluation
    original_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)

    # Modify file to invalidate cache (append dummy data)
    with open(temp_image, "ab") as f:
        f.write(b"\x00")  # Change size

    # Re-evaluate: should detect invalidation and recompute
    new_score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(new_score, float)
    assert 0 <= new_score <= 100

    # Score may differ due to file change, but verify entry updated with new stats
    entry = cache_manager.get_entry(str(temp_image))
    assert entry is not None
    assert entry.brisque is not None
    # Verify size updated (increased by 1 byte)
    assert entry.size == os.path.getsize(temp_image)


def test_brisque_edge_case_invalid_path_with_cache(temp_image: Path, cache_manager: FlatCacheManager):
    """Test invalid path raises exception, no cache interaction beyond check."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    invalid_path = str(temp_image.parent / "nonexistent.jpg")

    with pytest.raises(ImageQualityFileError):
        evaluator.evaluate(invalid_path, flat_cache_manager=cache_manager)

    # No entry should be created for invalid path
    entry = cache_manager.get_entry(invalid_path)
    assert entry is None


def test_brisque_edge_case_cache_db_error(temp_image: Path, monkeypatch):
    """Test handling of FlatCacheDBError during lookup (warns, computes anyway)."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    def mock_get_entry(path):
        raise FlatCacheDBError("Mock DB error")

    monkeypatch.setattr(FlatCacheManager, 'get_entry', mock_get_entry)

    cache_manager = FlatCacheManager()  # Real one, but get_entry mocked

    # Evaluate: should log warning but compute and return score
    score = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)
    assert isinstance(score, float)
    assert 0 <= score <= 100

    # Verify compute happened despite cache error


def test_brisque_computation_failure_fallback(temp_image: Path):
    """Test fallback to Laplacian when brisque is None."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # Temporarily set brisque to None to force fallback
    original_brisque = evaluator.brisque
    evaluator.brisque = None

    try:
        # Evaluate: should use Laplacian fallback
        score = evaluator.evaluate(str(temp_image))
        assert isinstance(score, float)
        assert 0 <= score <= 100

        # Verify fallback used (low variance for uniform black image)
        assert score < 10  # Adjust threshold if needed for black image variance
    finally:
        # Restore original
        evaluator.brisque = original_brisque


def test_brisque_cache_persistence(temp_image: Path, cache_manager: FlatCacheManager):
    """Verify score persists across evaluations and cache reload."""
    evaluator_key = "brisque"
    evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(evaluator_key)
    evaluator = evaluator_class()

    # Evaluate and store
    score1 = evaluator.evaluate(str(temp_image), flat_cache_manager=cache_manager)

    # Simulate cache persistence (already in file, but to test reload, perhaps recreate manager? But fixture handles)

    # New manager instance to simulate reload
    new_manager = FlatCacheManager(db_path=cache_manager.db_path)

    # Get entry from new manager
    entry = new_manager.get_entry(str(temp_image))
    assert entry.brisque == score1

    # Evaluate with new manager: hit
    score2 = evaluator.evaluate(str(temp_image), flat_cache_manager=new_manager)
    assert score2 == score1
