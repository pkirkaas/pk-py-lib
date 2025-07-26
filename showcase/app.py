"""
Main Component Showcase Application

Interactive showcase for all pk_py_lib components with live preview,
property inspection, and interactive testing capabilities.
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QSplitter, QVBoxLayout, QHBoxLayout,
        QWidget, QTreeWidget, QTreeWidgetItem, QTabWidget, QTextEdit,
        QScrollArea, QLabel, QFrame, QPushButton, QMenuBar, QStatusBar,
        QDockWidget, QMessageBox
    )
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import QFont, QIcon
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False
    print("Warning: PySide6 not available - GUI showcase disabled")

# Import our logging system
from src.pk_py_lib.core.logging import get_logger, LogPanel

log = get_logger(__name__)


@dataclass
class ComponentInfo:
    """Information about a component for the showcase."""
    name: str
    module: str
    class_name: str
    category: str
    description: str
    example_code: str
    properties: Dict[str, Any]
    preview_image: Optional[Path] = None


class ComponentShowcase(QMainWindow):
    """
    Interactive showcase for all pk_py_lib components.
    
    Features:
    - Component gallery with live preview
    - Property inspector for runtime configuration
    - Code examples with syntax highlighting
    - Interactive playground
    - Integrated logging panel
    - Performance monitoring
    """
    
    def __init__(self):
        """Initialize the showcase application."""
        super().__init__()
        
        if not PYSIDE_AVAILABLE:
            raise RuntimeError("PySide6 is required for the component showcase")
        
        self.logger = get_logger(__name__)
        self.current_component = None
        self.preview_widget = None
        
        self.setup_ui()
        self.setup_logging()
        self.load_components()
        
        self.logger.info("Component Showcase initialized")
    
    def setup_ui(self):
        """Create the showcase interface."""
        self.setWindowTitle("PK-Py-Lib Component Showcase")
        self.setGeometry(100, 100, 1400, 900)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main splitter (horizontal)
        main_splitter = QSplitter(Qt.Horizontal)
        central_widget.setLayout(QHBoxLayout())
        central_widget.layout().addWidget(main_splitter)
        
        # Left panel: Component browser
        self.component_browser = self.create_component_browser()
        main_splitter.addWidget(self.component_browser)
        
        # Center panel: Preview and code
        center_widget = self.create_center_panel()
        main_splitter.addWidget(center_widget)
        
        # Right panel: Property inspector
        self.property_inspector = self.create_property_inspector()
        main_splitter.addWidget(self.property_inspector)
        
        # Set splitter proportions
        main_splitter.setSizes([300, 700, 300])
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
    def create_component_browser(self) -> QWidget:
        """Create the component browser panel."""
        browser_widget = QWidget()
        layout = QVBoxLayout(browser_widget)
        
        # Title
        title = QLabel("Components")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Component tree
        self.component_tree = QTreeWidget()
        self.component_tree.setHeaderLabel("Available Components")
        self.component_tree.itemClicked.connect(self.on_component_selected)
        layout.addWidget(self.component_tree)
        
        # Search/filter controls would go here
        
        return browser_widget
    
    def create_center_panel(self) -> QWidget:
        """Create the center panel with preview and code tabs."""
        center_widget = QWidget()
        layout = QVBoxLayout(center_widget)
        
        # Tab widget for different views
        self.center_tabs = QTabWidget()
        
        # Preview tab
        self.preview_tab = self.create_preview_tab()
        self.center_tabs.addTab(self.preview_tab, "Live Preview")
        
        # Code tab
        self.code_tab = self.create_code_tab()
        self.center_tabs.addTab(self.code_tab, "Example Code")
        
        # Playground tab
        self.playground_tab = self.create_playground_tab()
        self.center_tabs.addTab(self.playground_tab, "Interactive Playground")
        
        layout.addWidget(self.center_tabs)
        return center_widget
    
    def create_preview_tab(self) -> QWidget:
        """Create the live preview tab."""
        preview_widget = QWidget()
        layout = QVBoxLayout(preview_widget)
        
        # Component info
        self.component_info_label = QLabel("Select a component to see preview")
        self.component_info_label.setStyleSheet("padding: 10px; background: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(self.component_info_label)
        
        # Preview area (scrollable)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMinimumHeight(400)
        
        # Default preview content
        default_preview = QLabel("Component preview will appear here")
        default_preview.setAlignment(Qt.AlignCenter)
        default_preview.setStyleSheet("color: #888; font-size: 14px;")
        self.preview_scroll.setWidget(default_preview)
        
        layout.addWidget(self.preview_scroll)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh Preview")
        self.refresh_btn.clicked.connect(self.refresh_preview)
        button_layout.addWidget(self.refresh_btn)
        
        self.reset_btn = QPushButton("Reset Properties")
        self.reset_btn.clicked.connect(self.reset_properties)
        button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return preview_widget
    
    def create_code_tab(self) -> QWidget:
        """Create the code example tab."""
        code_widget = QWidget()
        layout = QVBoxLayout(code_widget)
        
        # Code display (would use syntax highlighting in real implementation)
        self.code_display = QTextEdit()
        self.code_display.setReadOnly(True)
        self.code_display.setFont(QFont("Consolas", 10))
        self.code_display.setText("# Select a component to see example code")
        layout.addWidget(self.code_display)
        
        return code_widget
    
    def create_playground_tab(self) -> QWidget:
        """Create the interactive playground tab."""
        playground_widget = QWidget()
        layout = QVBoxLayout(playground_widget)
        
        # Description
        desc = QLabel("Interactive playground for testing components with custom code")
        layout.addWidget(desc)
        
        # Code editor (simplified)
        self.playground_editor = QTextEdit()
        self.playground_editor.setFont(QFont("Consolas", 10))
        self.playground_editor.setPlainText("""# Write custom code to test components
from src.pk_py_lib.gui.widgets import *

# Example:
# widget = SomeWidget()
# widget.show()
""")
        layout.addWidget(self.playground_editor)
        
        # Run button
        run_btn = QPushButton("Run Code")
        run_btn.clicked.connect(self.run_playground_code)
        layout.addWidget(run_btn)
        
        return playground_widget
    
    def create_property_inspector(self) -> QWidget:
        """Create the property inspector panel."""
        inspector_widget = QWidget()
        layout = QVBoxLayout(inspector_widget)
        
        # Title
        title = QLabel("Properties")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Property editor area (would be dynamically populated)
        self.property_area = QScrollArea()
        self.property_area.setWidgetResizable(True)
        
        default_props = QLabel("Select a component to edit properties")
        default_props.setAlignment(Qt.AlignCenter)
        self.property_area.setWidget(default_props)
        
        layout.addWidget(self.property_area)
        
        return inspector_widget
    
    def create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Component", self.new_component)
        file_menu.addAction("Import Component", self.import_component)
        file_menu.addSeparator()
        file_menu.addAction("Export Screenshot", self.export_screenshot)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        
        # View menu
        view_menu = menubar.addMenu("View")
        view_menu.addAction("Refresh Components", self.refresh_components)
        view_menu.addAction("Show Log Panel", self.show_log_panel)
        view_menu.addAction("Reset Layout", self.reset_layout)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self.show_about)
        help_menu.addAction("Component Documentation", self.show_docs)
    
    def setup_logging(self):
        """Setup integrated logging panel."""
        try:
            # Create log panel as dockable widget
            self.log_dock = QDockWidget("Logs", self)
            self.log_panel = LogPanel()
            self.log_dock.setWidget(self.log_panel)
            
            # Add to bottom of window
            self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
            
            # Configure logging to use our panel
            from src.pk_py_lib.core.logging.outputs.gui import GuiLogOutput
            gui_output = GuiLogOutput()
            gui_output.register_panel(self.log_panel)
            
            # Add to global logger configuration
            self.logger.add_output(gui_output)
            
        except Exception as e:
            print(f"Failed to setup logging panel: {e}")
    
    def load_components(self):
        """Load and display available components."""
        # For now, create some example entries
        # In real implementation, this would auto-discover components
        
        categories = {
            "Image Display": [
                ("ImageViewer", "Basic image viewing widget"),
                ("ThumbnailGrid", "Grid of image thumbnails"),
                ("ImageCarousel", "Carousel-style image browser")
            ],
            "File Management": [
                ("FileExplorer", "File system browser"),
                ("DuplicateFinder", "Duplicate file detection UI"),
                ("BatchProcessor", "Batch file operation interface")
            ],
            "Dialogs": [
                ("ProgressDialog", "Progress indication dialog"),
                ("SettingsDialog", "Application settings interface"),
                ("AboutDialog", "About application dialog")
            ]
        }
        
        for category, components in categories.items():
            category_item = QTreeWidgetItem([category])
            category_item.setFont(0, QFont("Arial", 10, QFont.Bold))
            self.component_tree.addTopLevelItem(category_item)
            
            for name, description in components:
                component_item = QTreeWidgetItem([name])
                component_item.setData(0, Qt.UserRole, {
                    'name': name,
                    'category': category,
                    'description': description
                })
                category_item.addChild(component_item)
        
        # Expand all categories
        self.component_tree.expandAll()
    
    def on_component_selected(self, item: QTreeWidgetItem):
        """Handle component selection in the tree."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        
        self.current_component = data
        
        # Update info display
        info_text = f"""
        <h3>{data['name']}</h3>
        <p><b>Category:</b> {data['category']}</p>
        <p><b>Description:</b> {data['description']}</p>
        """
        self.component_info_label.setText(info_text)
        
        # Update code display
        example_code = f"""# Example usage of {data['name']}
from src.pk_py_lib.gui.widgets import {data['name']}

# Create instance
widget = {data['name']}()

# Configure properties
# widget.set_property("value", "example")

# Show widget
widget.show()
"""
        self.code_display.setText(example_code)
        
        # Load preview (placeholder for now)
        preview_label = QLabel(f"Preview of {data['name']} component")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_label.setStyleSheet("background: white; border: 2px dashed #ccc; padding: 50px; margin: 20px;")
        preview_label.setMinimumSize(400, 300)
        self.preview_scroll.setWidget(preview_label)
        
        self.status_bar.showMessage(f"Selected: {data['name']}")
        self.logger.info(f"Selected component: {data['name']}")
    
    def refresh_preview(self):
        """Refresh the component preview."""
        if self.current_component:
            self.logger.info(f"Refreshing preview for {self.current_component['name']}")
    
    def reset_properties(self):
        """Reset component properties to defaults."""
        if self.current_component:
            self.logger.info(f"Resetting properties for {self.current_component['name']}")
    
    def run_playground_code(self):
        """Execute code in the playground."""
        code = self.playground_editor.toPlainText()
        self.logger.info("Executing playground code")
        
        try:
            # In a real implementation, this would safely execute the code
            # For now, just show a message
            QMessageBox.information(self, "Playground", "Code execution would happen here")
        except Exception as e:
            self.logger.error(f"Playground execution failed: {e}")
            QMessageBox.warning(self, "Error", f"Code execution failed: {e}")
    
    def new_component(self):
        """Create a new component template."""
        self.logger.info("Creating new component template")
    
    def import_component(self):
        """Import a component from file."""
        self.logger.info("Importing component")
    
    def export_screenshot(self):
        """Export current preview as screenshot."""
        self.logger.info("Exporting screenshot")
    
    def refresh_components(self):
        """Refresh the component list."""
        self.logger.info("Refreshing component list")
        self.load_components()
    
    def show_log_panel(self):
        """Show/hide the log panel."""
        if hasattr(self, 'log_dock'):
            self.log_dock.setVisible(not self.log_dock.isVisible())
    
    def reset_layout(self):
        """Reset the UI layout to defaults."""
        self.logger.info("Resetting layout")
    
    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About", 
                         "PK-Py-Lib Component Showcase\n\n"
                         "Interactive testing environment for GUI components.")
    
    def show_docs(self):
        """Show component documentation."""
        self.logger.info("Opening component documentation")


class LogPanel(QWidget):
    """
    Embeddable log display panel for GUI applications.
    
    Features:
    - Real-time log updates
    - Filtering by level/tag/source
    - Search functionality
    - Export capabilities
    """
    
    def __init__(self, parent=None):
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
        """Add a log entry to the display."""
        # Format and add log entry
        formatted = f"[{entry.timestamp}] {entry.level.name}: {entry.message}"
        self.log_display.append(formatted)


def run_showcase():
    """
    Run the component showcase application.
    
    This is the main entry point for launching the showcase.
    """
    if not PYSIDE_AVAILABLE:
        print("Error: PySide6 is required to run the component showcase")
        print("Install with: pip install PySide6")
        return 1
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("PK-Py-Lib Component Showcase")
    app.setOrganizationName("Paul Kirkaas")
    
    # Create and show main window
    try:
        showcase = ComponentShowcase()
        showcase.show()
        
        # Run event loop
        return app.exec()
        
    except Exception as e:
        print(f"Failed to start showcase: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_showcase())