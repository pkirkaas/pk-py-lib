"""
Log Panel

Embeddable log display panel for GUI applications.
"""

from typing import Any

# Try to import PySide6, but handle gracefully if not available
try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton
    from PySide6.QtGui import QFont
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False
    # Create placeholder classes to avoid import errors
    class QWidget:
        def __init__(self, *args, **kwargs):
            pass
    
    class QVBoxLayout:
        def __init__(self, *args, **kwargs):
            pass
    
    class QTextEdit:
        def __init__(self, *args, **kwargs):
            pass
    
    class QHBoxLayout:
        def __init__(self, *args, **kwargs):
            pass
    
    class QPushButton:
        def __init__(self, *args, **kwargs):
            pass
    
    class QFont:
        def __init__(self, *args, **kwargs):
            pass


class LogPanel(QWidget):
    """
    Embeddable log display panel for GUI applications.
    
    Features:
    - Real-time log updates
    - Filtering by level/tag/source
    - Search functionality
    - Export capabilities
    """
    
    def __init__(self, parent: Any = None):
        """
        Initialize the log panel.
        
        Args:
            parent: Parent widget
        """
        if not PYSIDE_AVAILABLE:
            raise RuntimeError("PySide6 is required for LogPanel but not available")
        
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the log panel UI."""
        layout = QVBoxLayout(self)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_display)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(clear_btn)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
    
    def clear_logs(self):
        """Clear the log display."""
        self.log_display.clear()
    
    def add_log_entry(self, entry):
        """
        Add a log entry to the display.
        
        Args:
            entry: Log entry to display
        """
        # Format and add log entry
        formatted = f"[{entry.timestamp}] {entry.level.name}: {entry.message}"
        self.log_display.append(formatted)