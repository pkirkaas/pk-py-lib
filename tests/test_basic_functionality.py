"""
Basic functionality tests for pk-py-lib and img_app.

This module contains basic tests to verify that the core functionality
is working correctly.
"""

from pathlib import Path

# Test core utilities
def test_path_normalization():
    """Test path normalization utility."""
    from pk_py_lib.core.utils.paths import normalize_path

    path = "/test/../test/file.jpg"
    normalized = normalize_path(path)
    assert "test/file.jpg" in normalized
    assert Path(normalized).is_absolute()


def test_validation_error():
    """Test validation error handling."""
    from pk_py_lib.core.utils.validation import ValidationError

    try:
        raise ValidationError("Test error", field="test_field", value="test_value")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass  # Expected


def test_api_response():
    """Test API response creation."""
    from pk_py_lib.core.api.response import create_success_response, create_error_response, ErrorCodes

    # Test success response
    success_resp = create_success_response("test_data")
    assert success_resp.success is True
    assert success_resp.data == "test_data"
    assert success_resp.error is None

    # Test error response
    error_resp = create_error_response("Test error", ErrorCodes.INVALID_CONFIG)
    assert error_resp.success is False
    assert error_resp.error == "Test error"
    assert error_resp.code == ErrorCodes.INVALID_CONFIG.value


def test_gui_models():
    """Test GUI data models."""
    from pk_py_lib.gui.models import FileItem, Group, GroupStats

    # Test FileItem creation
    file_item = FileItem(
        path="/test/file.jpg",
        size=1024,
        resolution="1920x1080",
        mod_date="2023-01-01"
    )
    assert file_item.basename == "file.jpg"
    assert file_item.directory == "/test"

    # Test GroupStats
    stats = GroupStats(
        total_size=2048,
        savings=1024,
        min_score=0.8,
        max_score=1.0,
        avg_score=0.9,
        file_count=2
    )
    assert stats.file_count == 2

    # Test Group
    group = Group(
        id=1,
        items=(file_item,),
        stats=stats,
        ref_path="/test/file.jpg"
    )
    assert group.item_count == 1


def test_selection_store():
    """Test selection store functionality."""
    from pk_py_lib.gui.models import SelectionStore

    store = SelectionStore()

    # Test adding selection
    assert store.add_selection("/test/file1.jpg") is True
    assert store.get_selection_count() == 1
    assert store.is_selected("/test/file1.jpg") is True

    # Test duplicate selection
    assert store.add_selection("/test/file1.jpg") is False
    assert store.get_selection_count() == 1

    # Test removing selection
    assert store.remove_selection("/test/file1.jpg") is True
    assert store.get_selection_count() == 0

    # Test clearing selection
    store.add_selection("/test/file1.jpg")
    store.add_selection("/test/file2.jpg")
    store.clear_selection()
    assert store.get_selection_count() == 0


def test_logger():
    """Test logging functionality."""
    from pk_py_lib.core.logging.logger import get_logger

    logger = get_logger("test_logger")
    assert logger is not None

    # Test basic logging
    logger.info("Test log message")
    logger.debug("Test debug message")
    logger.warning("Test warning message")


if __name__ == "__main__":
    # Run tests
    test_functions = [
        test_path_normalization,
        test_validation_error,
        test_api_response,
        test_gui_models,
        test_selection_store,
        test_logger,
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1

    print(f"\nTest Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All tests passed!")
        exit(0)
    else:
        print("💥 Some tests failed")
        exit(1)
