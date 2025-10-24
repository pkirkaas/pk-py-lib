"""
Central placeholder widget for img_app main window.

This widget provides a placeholder for the main content area
until full functionality is implemented.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class CentralPlaceholder(QWidget):
    """
    Placeholder widget for the main content area.

    This widget displays information about the application and provides
    quick access to common functions until the full interface is implemented.
    """

    def __init__(self, parent=None):
        """
        Initialize the placeholder widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.setup_ui()

    def setup_ui(self) -> None:
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(50, 50, 50, 50)

        # Main title
        title_label = QLabel("KDC Image Organizer")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = title_label.font()
        title_font.setPointSize(32)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Desktop application for managing large photo collections")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_font = subtitle_label.font()
        subtitle_font.setPointSize(14)
        subtitle_label.setFont(subtitle_font)
        layout.addWidget(subtitle_label)

        # Features section
        features_label = QLabel("Features:")
        features_label.setAlignment(Qt.AlignLeft)
        features_font = features_label.font()
        features_font.setPointSize(12)
        features_font.setBold(True)
        features_label.setFont(features_font)
        layout.addWidget(features_label)

        # Features list
        features_text = """
• Duplicate detection using perceptual hashing
• Image similarity analysis
• Batch file operations
• Comprehensive caching system
• Cross-platform support
• Professional image management
        """.strip()

        features_list = QLabel(features_text)
        features_list.setAlignment(Qt.AlignLeft)
        features_list.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 15px;
                font-family: monospace;
            }
        """)
        layout.addWidget(features_list)

        # Status section
        status_label = QLabel("Status: Development Preview")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-style: italic;
                padding: 10px;
            }
        """)
        layout.addWidget(status_label)

        # Spacer
        layout.addStretch()

        # Action buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)

        # This will be connected to actual functionality later
        demo_btn = QPushButton("Run Demo")
        demo_btn.setMinimumHeight(40)
        buttons_layout.addWidget(demo_btn)

        layout.addLayout(buttons_layout)
