#!/usr/bin/env python3
"""
Test script to verify progress dialog functionality for similarity operations.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt, QTimer

# Import the components we need to test
from src.pk_py_lib.gui.dialogs.progress_dialog import ProgressDialog
from src.pk_py_lib.core.image.similarity.phases import PhaseContext, execute_all_phases
from src.pk_py_lib.core.flat_cache import FlatCacheManager
from src.pk_py_lib.core.database import DatabaseManager


class ProgressDialogTester(QWidget):
    """Test widget to demonstrate progress dialog functionality."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Progress Dialog Test")
        self.setGeometry(100, 100, 400, 200)

        layout = QVBoxLayout(self)

        description = QLabel(
            "This test will demonstrate the progress dialog functionality.\n"
            "Click 'Test Progress Dialog' to start a similarity computation\n"
            "that will show a progress dialog with detailed status updates."
        )
        description.setWordWrap(True)
        description.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(description)

        self.test_button = QPushButton("Test Progress Dialog")
        self.test_button.clicked.connect(self.test_progress_dialog)
        layout.addWidget(self.test_button)

        self.status_label = QLabel("Ready for testing...")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        # Initialize managers
        self.db_manager = None
        self.flat_cache_manager = None
        self._initialize_managers()

    def _initialize_managers(self):
        """Initialize required managers for testing."""
        try:
            self.db_manager = DatabaseManager()
            self.db_manager.initialize()
            self.flat_cache_manager = FlatCacheManager()
            self.status_label.setText("Managers initialized successfully.")
        except Exception as e:
            self.status_label.setText(f"Manager initialization failed: {e}")
            print(f"ERROR: {e}")

    def test_progress_dialog(self):
        """Test the progress dialog with a similarity computation."""
        if not self.flat_cache_manager or not self.db_manager:
            self.status_label.setText("Cannot test: Managers not available")
            return

        self.status_label.setText("Starting similarity computation with progress dialog...")
        self.test_button.setEnabled(False)

        # Create progress dialog
        progress_dialog = ProgressDialog(
            parent=self,
            title="Computing Similarity Groups - Test"
        )

        # Create cancellation flag
        cancellation_flag = [False]

        def handle_cancellation():
            cancellation_flag[0] = True
            self.status_label.setText("Operation cancelled by user")

        progress_dialog.cancellation_requested.connect(handle_cancellation)

        def progress_callback(current: int, total: int, message: str):
            """Progress callback function."""
            if total > 0:
                percentage = min(100, max(0, int((current / total) * 100)))
            else:
                percentage = 0

            progress_dialog.set_progress(percentage, message)
            self.status_label.setText(f"Progress: {percentage}% - {message}")

            print(f"PROGRESS: {percentage}% - {message}")

        try:
            # Create a simple test - use minimal paths for testing
            test_paths = [
                str(project_root / "example-guis" / "clone-spy.jpg")
            ]

            # Only proceed if test file exists
            existing_paths = [p for p in test_paths if os.path.exists(p)]
            if not existing_paths:
                self.status_label.setText("Test file not found - cannot proceed with test")
                self.test_button.setEnabled(True)
                return

            progress_dialog.show()

            # Create PhaseContext for testing
            context = PhaseContext(
                image_paths=existing_paths,
                algorithm="phash",
                threshold=10,
                settings={},
                flat_cache_manager=self.flat_cache_manager,
                search_type='similarity',
                max_workers=2,
                progress_callback=progress_callback,
                cancellation_flag=cancellation_flag,
                total_files=len(existing_paths)
            )

            # Execute all phases (this will show progress)
            final_context = execute_all_phases(context)

            # Operation completed
            final_groups = final_context.stats.get('final_groups_count', 0)
            self.status_label.setText(f"Test completed successfully! Found {final_groups} groups.")

        except Exception as e:
            self.status_label.setText(f"Test failed: {e}")
            print(f"ERROR: {e}")
        finally:
            self.test_button.setEnabled(True)
            progress_dialog.accept()


def main():
    """Main function to run the progress dialog test."""
    app = QApplication(sys.argv)

    # Set up the application attributes for better GUI display
    app.setApplicationName("Progress Dialog Test")
    app.setApplicationVersion("1.0.0")
    app.setQuitOnLastWindowClosed(True)

    # Create and show the test widget
    tester = ProgressDialogTester()
    tester.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
