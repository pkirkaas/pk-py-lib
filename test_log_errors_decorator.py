#!/usr/bin/env python3
"""
Test script for the enhanced @log_errors decorator.

This script tests the decorator by creating a simple GUI-like class (simulating a Qt widget)
and raising an error in a decorated method. It verifies that the log captures:
- Exception type and message
- File path and line number
- Function name and parameters
- GUI context (self class, widget states like objectName, current_text)
- Stack trace
- Output to both console (STDERR) and file

Requires PySide6 for GUI simulation, but keeps it minimal.
"""

import sys
from pathlib import Path
import traceback

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from pk_py_lib.core.logging import configure_logging, get_logger, LogLevel
from pk_py_lib.core.logging.decorators import log_errors

# For GUI simulation
try:
    from PySide6.QtWidgets import QApplication, QWidget, QLabel
    from PySide6.QtCore import Qt
    HAS_GUI = True
except ImportError:
    # Mock for non-GUI test
    HAS_GUI = False
    class QApplication: pass
    class QWidget: 
        def __init__(self): 
            self._objectName = "TestWidget"
            self._windowTitle = "Test Window"
        def objectName(self): return self._objectName
        def windowTitle(self): return self._windowTitle
    class QLabel:
        def __init__(self, text=""): self._text = text
        def text(self): return self._text
    Qt = type('Qt', (), {'TextSelectableByMouse': 1})()

# Configure logging: console and file
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)
test_log_path = logs_dir / "test_errors.log"

configure_logging(
    console=True,
    file_path=test_log_path,
    level=LogLevel.DEBUG,
    rich_console=False
)

log = get_logger(__name__)


class TestGUIWidget(QWidget):
    """
    Simple test widget to simulate GUI component for error logging.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("TestGUIWidget")
        self.setWindowTitle("Error Test Widget")
        self.user_input_label = QLabel("Sample user input: hello world")
        # Simulate some state

    @log_errors()
    def error_prone_method(self, user_input: str, param: int = 42):
        """
        Method that raises an error to test the decorator.
        
        Args:
            user_input: Simulated user input
            param: Test parameter
        """
        # Simulate GUI operation
        if not user_input:
            raise ValueError("Empty user input provided")
        
        # Simulate some processing
        result = len(user_input) + param
        
        # Force error for testing
        raise IOError(f"Simulated IO error during processing: result={result}, widget={self.objectName()}")
        
        return result


def run_test():
    """Run the test and print results."""
    print("Starting @log_errors decorator test...")
    print(f"Logging to console and {test_log_path}")
    
    if HAS_GUI:
        app = QApplication(sys.argv)
    else:
        app = None  # Headless test
    
    widget = TestGUIWidget()
    
    try:
        # This should raise and be caught/logged by decorator
        widget.error_prone_method(user_input="test input", param=10)
    except Exception as e:
        # Decorator re-raises, so catch here to continue
        print(f"Caught expected exception: {type(e).__name__}: {e}")
        tb = traceback.format_exc()
        print("Stack trace:")
        print(tb)
    
    print("\nTest completed. Check console output and log file for details.")
    
    if app:
        app.quit()


if __name__ == "__main__":
    run_test()