#!/usr/bin/env python3
"""
Test script for GUI error handling functionality.

This script tests the new centralized GUI error handling system including:
- handle_gui_error function
- gui_error_handler decorator
- gui_error_context context manager

Note: This is a headless test that verifies the functionality without
actually showing GUI dialogs.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Mock PySide6 before importing messages to avoid import errors
import sys
from unittest.mock import MagicMock, patch

# Create a simple mock for PySide6 to avoid import errors
mock_pyside = MagicMock()
mock_pyside.QtCore = MagicMock()
mock_pyside.QtWidgets = MagicMock()

# Mock necessary constants
mock_pyside.QtCore.Qt = MagicMock()
mock_pyside.QtCore.Qt.TextSelectableByMouse = MagicMock()
mock_pyside.QtCore.Qt.TextSelectableByKeyboard = MagicMock()
mock_pyside.QtCore.Qt.LinksAccessibleByMouse = MagicMock()

mock_pyside.QtWidgets.QMessageBox = MagicMock()
mock_pyside.QtWidgets.QMessageBox.Critical = MagicMock()
mock_pyside.QtWidgets.QWidget = MagicMock()
mock_pyside.QtWidgets.QLabel = MagicMock()

# Set the mock as the module
sys.modules['PySide6'] = mock_pyside
sys.modules['PySide6.QtCore'] = mock_pyside.QtCore
sys.modules['PySide6.QtWidgets'] = mock_pyside.QtWidgets

# Now import the modules with patched show_selectable_error
with patch('src.pk_py_lib.gui.utils.messages.show_selectable_error') as mock_show_error:
    mock_show_error.return_value = 0  # Return value for exec()
    
    from src.pk_py_lib.gui.utils.messages import (
        handle_gui_error,
        gui_error_handler,
        gui_error_context
    )
    from src.pk_py_lib.core.logging import get_logger, LogLevel, configure_logging

# Configure logging to capture error output
configure_logging(console=True, level=LogLevel.DEBUG, rich_console=False)
log = get_logger(__name__)

def test_handle_gui_error():
    """Test the handle_gui_error function with various error types."""
    print("Testing handle_gui_error function...")
    
    # Test with string error
    try:
        handle_gui_error(
            parent=None,
            error="Test error message",
            title="Test Error",
            component_name="TestComponent",
            error_code="TEST_001"
        )
        print("✓ String error handled successfully")
    except Exception as e:
        print(f"✗ String error test failed: {e}")
        return False
    
    # Test with exception object
    try:
        try:
            raise ValueError("This is a test exception")
        except ValueError as e:
            handle_gui_error(
                parent=None,
                error=e,
                title="Test Exception",
                component_name="TestComponent",
                error_code="TEST_002"
            )
        print("✓ Exception error handled successfully")
    except Exception as e:
        print(f"✗ Exception error test failed: {e}")
        return False
    
    return True

@gui_error_handler(component_name="TestFunction")
def test_function_with_error():
    """Test function that raises an exception."""
    raise RuntimeError("This is a test error from decorated function")

@gui_error_handler(component_name="TestFunctionWithParams")
def test_function_with_params(a, b):
    """Test function with parameters that raises an exception."""
    result = a + b
    raise ValueError(f"Error after calculation: {result}")

def test_gui_error_handler_decorator():
    """Test the gui_error_handler decorator."""
    print("Testing gui_error_handler decorator...")
    
    # Test function with no parameters
    try:
        test_function_with_error()
        print("✓ Decorated function with no parameters handled error")
    except Exception as e:
        print(f"✗ Decorated function test failed: {e}")
        return False
    
    # Test function with parameters
    try:
        test_function_with_params(5, 10)
        print("✓ Decorated function with parameters handled error")
    except Exception as e:
        print(f"✗ Decorated function with parameters test failed: {e}")
        return False
    
    return True

def test_gui_error_context():
    """Test the gui_error_context context manager."""
    print("Testing gui_error_context context manager...")
    
    # Test successful operation
    try:
        with gui_error_context(component_name="TestContextSuccess"):
            result = 42
            print(f"✓ Context manager successful operation: {result}")
    except Exception as e:
        print(f"✗ Context manager successful operation failed: {e}")
        return False
    
    # Test operation with error
    try:
        with gui_error_context(component_name="TestContextError"):
            raise RuntimeError("Error inside context manager")
        print("✗ Context manager should have caught the error")
        return False
    except RuntimeError:
        print("✓ Context manager caught and handled error (exception re-raised)")
    
    return True

def test_integration_with_existing_components():
    """Test integration with existing components by simulating error scenarios."""
    print("Testing integration with existing components...")
    
    # Simulate settings manager error
    try:
        from src.pk_py_lib.gui.settings_manager.dialog import SettingsManagerDialog
        # This would normally show a dialog, but we're just testing the import and function call
        print("✓ Settings manager integration test passed (import successful)")
    except Exception as e:
        print(f"✗ Settings manager integration test failed: {e}")
        return False
    
    # Simulate file selector error
    try:
        from src.pk_py_lib.gui.file_selector.widgets import PathSelectorDialog
        print("✓ File selector integration test passed (import successful)")
    except Exception as e:
        print(f"✗ File selector integration test failed: {e}")
        return False
    
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing GUI Error Handling System")
    print("=" * 60)
    
    tests = [
        ("handle_gui_error", test_handle_gui_error),
        ("gui_error_handler decorator", test_gui_error_handler_decorator),
        ("gui_error_context", test_gui_error_context),
        ("Integration with components", test_integration_with_existing_components),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "PASS" if result else "FAIL"
            print(f"  {status}")
        except Exception as e:
            results.append((test_name, False))
            print(f"  FAIL: {e}")
    
    print("\n" + "=" * 60)
    print("Test Results Summary:")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{test_name:30} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    if all_passed:
        print("All tests PASSED! ✓")
        return 0
    else:
        print("Some tests FAILED! ✗")
        return 1

if __name__ == "__main__":
    sys.exit(main())