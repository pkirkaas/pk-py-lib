"""
Main window implementation for the KDC Image Organizer (img_app).

Provides a QMainWindow subclass with:
- Title: "KDC Image Organizer"
- Menu bar with File, View, Help (initially no-op actions)
- Profile management toolbar with combobox, create/copy/rename/delete buttons
- Structured settings editor for profile configuration
- Progress reporting during operations
- Results dialog for operation completion

This window integrates the full Settings Manager functionality directly
into the main application interface.

Syntax validation: This file has been reviewed for Python syntax correctness.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QWidget, QVBoxLayout, QMenuBar, QStatusBar,
    QComboBox, QPushButton, QHBoxLayout, QFrame, QProgressBar, QApplication,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QStackedWidget,
    QMessageBox, QToolBar, QMenu, QSizePolicy
)
from typing import Optional, Dict, Any, List, Tuple

# Import Settings Manager components
try:
    from src.pk_py_lib.gui.settings_manager.structured_editor import StructuredProfileEditorWidget
    from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
except ImportError:
    # Fallback imports if not available
    StructuredProfileEditorWidget = None
    SettingsManagerController = None


class _NamePromptDialog(QDialog):
    """
    Minimal reusable prompt dialog for entering a name (with live validation message).
    """

    def __init__(self, title: str, label: str, initial: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.inp = QLineEdit(initial)
        form.addRow(label, self.inp)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color:#c00; font-size:12px;")
        form.addRow("", self.lbl_error)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def text(self) -> str:
        return (self.inp.text() or "").strip()

    def set_error(self, msg: Optional[str]) -> None:
        self.lbl_error.setText(msg or "")


class CentralPlaceholder(QWidget):
    """
    Simple centered placeholder widget.

    Displays a centered label indicating where the application content will go.
    This class is placed here initially to keep scaffolding minimal; it can be
    moved to img_app/widgets/central_placeholder.py when expanded.

    Examples
    --------
    >>> w = CentralPlaceholder()
    >>> w.layout() is not None
    True
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        label = QLabel("The KDC Image Organizer will go here", self)
        # Use Qt.AlignmentFlag enums for correctness across PySide6 bindings
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """
    QMainWindow for the KDC Image Organizer.

    Responsibilities
    ----------------
    - Set up basic window chrome (title, menus, status bar)
    - Provide complete profile management UI (combobox, create/copy/rename/delete/set active buttons)
    - Integrated structured settings editor for profile configuration
    - Display progress reporting during operations
    - Show detailed results dialog after operation completion
    - Host future widgets and controllers derived from pk_py_lib

    Usage
    -----
    The window is constructed and shown by img_app.img_app.app:main()

    Examples
    --------
    >>> win = MainWindow()
    >>> isinstance(win.menuBar(), QMenuBar)
    True
    """

    # Signal emitted when the active profile changes
    profile_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None, active_profile: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize MainWindow.

        Parameters
        ----------
        parent : QWidget | None
            Optional parent widget.
        active_profile : Optional[Dict[str, Any]]
            Active settings profile to associate with this window; stored on self.active_profile
            for future use by UI components. Passing None keeps behavior identical to prior versions.
        """
        super().__init__(parent)
        # Store the active profile for future use in widgets/controllers
        self.active_profile: Optional[Dict[str, Any]] = active_profile
        self.profiles: List[Dict[str, Any]] = []
        self.controller = None  # Will be set when database manager is available
        self.structured_editor = None
        # Track whether we've connected structured_editor.dirtyChanged to avoid spurious disconnect warnings
        self._editor_dirty_connected: bool = False
         
        self._setup_window()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_profile_toolbar()
        self._setup_progress_section()
        self._setup_central_widget()
        
        # Initialize start time for progress simulation
        import time
        self.start_time = time.time()

    def _setup_profile_toolbar(self) -> None:
        """
        Create the profile management toolbar with combobox and buttons.
        """
        # Create a toolbar for profile management
        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        toolbar_layout.setSpacing(10)

        # Profile selection label
        profile_label = QLabel("Profile:", self)
        toolbar_layout.addWidget(profile_label)

        # Profile combobox
        self.profile_combo = QComboBox(self)
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        toolbar_layout.addWidget(self.profile_combo)

        # Create profile button
        self.create_btn = QPushButton("New", self)
        self.create_btn.setToolTip("Create a new profile")
        self.create_btn.clicked.connect(self._on_create_profile)
        toolbar_layout.addWidget(self.create_btn)

        # Copy profile button
        self.copy_btn = QPushButton("Copy", self)
        self.copy_btn.setToolTip("Copy the selected profile")
        self.copy_btn.clicked.connect(self._on_copy_profile)
        toolbar_layout.addWidget(self.copy_btn)

        # Rename profile button
        self.rename_btn = QPushButton("Rename", self)
        self.rename_btn.setToolTip("Rename the selected profile")
        self.rename_btn.clicked.connect(self._on_rename_profile)
        toolbar_layout.addWidget(self.rename_btn)

        # Delete profile button
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setToolTip("Delete the selected profile")
        self.delete_btn.clicked.connect(self._on_delete_profile)
        self.delete_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        toolbar_layout.addWidget(self.delete_btn)

        # Set active profile button
        self.set_active_btn = QPushButton("Set Active", self)
        self.set_active_btn.setToolTip("Set the selected profile as active")
        self.set_active_btn.clicked.connect(self._on_set_active_profile)
        self.set_active_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        toolbar_layout.addWidget(self.set_active_btn)

        # Save button (initially disabled)
        self.save_btn = QPushButton("Save", self)
        self.save_btn.setToolTip("Save changes to the current profile")
        self.save_btn.clicked.connect(self._on_save_profile)
        self.save_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; }")
        self.save_btn.setEnabled(False)
        toolbar_layout.addWidget(self.save_btn)

        # Cancel button (initially disabled)
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setToolTip("Discard changes to the current profile")
        self.cancel_btn.clicked.connect(self._on_cancel_changes)
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #9E9E9E; color: white; }")
        self.cancel_btn.setEnabled(False)
        toolbar_layout.addWidget(self.cancel_btn)

        # Start button
        self.start_btn = QPushButton("Start", self)
        self.start_btn.setToolTip("Start the operation with the selected profile")
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        toolbar_layout.addWidget(self.start_btn)

        # Add stretch to push buttons to the left
        toolbar_layout.addStretch(1)

        # Add the toolbar to the main window
        self.setMenuWidget(toolbar)

    def _setup_progress_section(self) -> None:
        """
        Create the progress reporting section with progress bar and status labels.
        """
        # Create a progress section widget (initially hidden)
        self.progress_section = QWidget(self)
        self.progress_section.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_section)
        progress_layout.setContentsMargins(10, 5, 10, 5)
        progress_layout.setSpacing(5)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Status labels in a horizontal layout
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Ready", self)
        status_layout.addWidget(self.status_label)
        
        self.file_count_label = QLabel("Files processed: 0", self)
        status_layout.addWidget(self.file_count_label)
        
        self.eta_label = QLabel("Estimated time: --", self)
        status_layout.addWidget(self.eta_label)
        
        status_layout.addStretch(1)
        progress_layout.addLayout(status_layout)

        # Add the progress section below the toolbar
        # We'll use a dock widget or place it in the central area temporarily
        # For now, we'll add it to the central widget's layout later

    def _setup_window(self) -> None:
        """Configure basic window properties."""
        self.setWindowTitle("KDC Image Organizer")
        self.resize(1024, 720)

    def _setup_menu_bar(self) -> None:
        """Create a standard application menu bar with File, View, Help."""
        menubar = self.menuBar() if self.menuBar() else QMenuBar(self)
        self.setMenuBar(menubar)

        # File menu
        file_menu = menubar.addMenu("&File")
        # Placeholder actions (no-op)
        file_menu.addAction(self._make_noop_action("Open..."))
        file_menu.addAction(self._make_noop_action("Save"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_noop_action("Exit"))

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._make_noop_action("Reset Layout"))

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._make_noop_action("About"))

    def _setup_status_bar(self) -> None:
        """Attach a status bar with selectable text for feedback."""
        status = self.statusBar() if self.statusBar() else QStatusBar(self)
        self.setStatusBar(status)
        
        # Create a label for selectable status messages
        self.status_label = QLabel("Ready")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status.addPermanentWidget(self.status_label)
        
        # Show active profile name if available
        try:
            if getattr(self, "active_profile", None):
                name = self.active_profile.get("name") or self.active_profile.get("id")
                if name:
                    self.status_label.setText(f"Ready — Profile: {name}")
        except Exception:
            # Fallback to default message if any unexpected structure
            pass

    def _setup_central_widget(self) -> None:
        """
        Create the central widget with progress section and main content.

        The central widget now includes:
        1. Progress section (initially hidden)
        2. Stacked widget for main content (file selector/placeholder and structured editor)
        """
        # Create a container widget for the central area
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Add progress section to the container
        container_layout.addWidget(self.progress_section)

        # Create stacked widget for main content
        self.stacked_widget = QStackedWidget(self)
        container_layout.addWidget(self.stacked_widget)

        # Page 0: File selector or placeholder
        try:
            # Import locally to avoid top-level dependency on pk-py-lib during module import
            from src.pk_py_lib.gui.file_selector.widgets import (
                MultiPathSelectorWidget,
                PathFilterSpec,
            )

            # Construct a sensible default filter spec (images & video)
            filter_spec = PathFilterSpec(include_categories={"images", "video"})
            selector = MultiPathSelectorWidget(
                parent=self,
                title="Paths",
                start_dir=None,
                filter_spec=filter_spec,
            )
            self.stacked_widget.addWidget(selector)
            self.stacked_widget.setCurrentIndex(0)
            # Update status with success (best-effort)
            try:
                self.statusBar().showMessage("MultiPathSelector loaded")
            except Exception:
                pass
        except Exception as exc:
            # Fallback to placeholder
            self.stacked_widget.addWidget(CentralPlaceholder(self))
            self.stacked_widget.setCurrentIndex(0)
            try:
                self.statusBar().showMessage(f"Using placeholder (MultiPathSelector unavailable): {exc}")
            except Exception:
                pass

        # Page 1: Structured editor (will be created when needed)
        # We'll add a placeholder for now
        self.structured_editor_placeholder = QLabel("Select a profile to view and edit details")
        self.structured_editor_placeholder.setAlignment(Qt.AlignCenter)
        self.stacked_widget.addWidget(self.structured_editor_placeholder)

        # Set the container as the central widget
        self.setCentralWidget(container)

    def _load_profiles(self) -> None:
        """
        Load available profiles from the database and populate the combobox.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            resp = self.controller.list_profiles()
            
            if resp.success:
                self.profiles = resp.data or []
                self.profile_combo.clear()
                
                if self.profiles:
                    # Populate combobox with profile names, marking active profile
                    for profile in self.profiles:
                        name = profile.get('name', 'Unnamed')
                        if profile.get('is_active'):
                            name += " ★"
                        self.profile_combo.addItem(name, profile.get('id'))
                    
                    # Select the active profile if available
                    active_profile = None
                    for profile in self.profiles:
                        if profile.get('is_active'):
                            active_profile = profile
                            break
                    
                    if active_profile:
                        self.active_profile = active_profile
                        index = self.profile_combo.findData(active_profile.get('id'))
                        if index >= 0:
                            self.profile_combo.setCurrentIndex(index)
                    elif self.profile_combo.count() > 0:
                        self.profile_combo.setCurrentIndex(0)
                    
                    self.status_label.setText(f"Loaded {len(self.profiles)} profiles")
                else:
                    self.status_label.setText("No profiles available. Create a new profile.")
            else:
                self.status_label.setText(f"Failed to load profiles: {resp.message}")
                
        except Exception as exc:
            self.status_label.setText(f"Error loading profiles: {exc}")
            # Log detailed error
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _load_profiles")

    def _on_profile_selected(self, index: int) -> None:
        """
        Handle profile selection change from combobox.
        """
        if index < 0:
            return
            
        profile_id = self.profile_combo.itemData(index)
        if not profile_id:
            return
            
        # Find the selected profile
        selected_profile = None
        for profile in self.profiles:
            if profile.get('id') == profile_id:
                selected_profile = profile
                break
                
        if selected_profile:
            self.active_profile = selected_profile
            self.profile_changed.emit(selected_profile)
            self.status_label.setText(f"Active profile: {selected_profile.get('name', 'Unnamed')}")
            
            # Update the active profile in the database
            try:
                if self.controller:
                    resp = self.controller.set_active(profile_id)
                    if not resp.success:
                        self.status_label.setText(f"Error setting active profile: {resp.message}")
            except Exception as exc:
                self.status_label.setText(f"Error setting active profile: {exc}")
            
            # Load the profile into the structured editor
            self._load_profile_into_editor(profile_id)

    def _on_create_profile(self) -> None:
        """
        Handle create new profile button click.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            from src.pk_py_lib.core.settings_schema import create_default_profile
            
            # Create a name prompt dialog
            dlg = _NamePromptDialog("Create Profile", "Name:", parent=self)
            # Suggest a unique name using controller
            sugg_resp = self.controller.suggest_unique_name("New Profile")
            if sugg_resp.success and sugg_resp.data:
                dlg.inp.setText(sugg_resp.data)
            else:
                dlg.inp.setText("New Profile")
            
            if dlg.exec() == QDialog.Accepted:
                name = dlg.text()
                if not name:
                    dlg.set_error("Name is required")
                    return
                
                # Validate the name using controller
                validate_resp = self.controller.validate_name(name)
                if not validate_resp.success:
                    dlg.set_error(validate_resp.message or "Invalid name")
                    return
                
                # Create the profile with default JSON data using controller
                json_data = create_default_profile(name, "")
                create_resp = self.controller.create_structured_profile(json_data, make_active=True)
                
                if create_resp.success:
                    self.status_label.setText(f"Profile '{name}' created")
                    self._load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to create profile: {create_resp.message}")
            else:
                self.status_label.setText("Create profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error creating profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_create_profile")

    def _on_copy_profile(self) -> None:
        """
        Handle copy profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to copy")
            return
            
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            current_name = self.active_profile.get('name', 'Unnamed')
            
            # Create a name prompt dialog
            dlg = _NamePromptDialog("Copy Profile", "New name:", parent=self)
            # Suggest a unique name based on current profile using controller
            sugg_resp = self.controller.suggest_unique_name(f"{current_name} (copy)")
            if sugg_resp.success and sugg_resp.data:
                dlg.inp.setText(sugg_resp.data)
            else:
                dlg.inp.setText(f"Copy of {current_name}")
            
            if dlg.exec() == QDialog.Accepted:
                new_name = dlg.text()
                if not new_name:
                    dlg.set_error("Name is required")
                    return
                
                # Validate the name
                validate_resp = self.controller.validate_name(new_name)
                if not validate_resp.success:
                    dlg.set_error(validate_resp.message or "Invalid name")
                    return
                
                # Copy the profile using controller
                copy_resp = self.controller.duplicate_structured_profile(
                    source_profile_id=self.active_profile['id'],
                    new_name=new_name,
                    description=f"Copy of {current_name}",
                    make_active=False
                )
                
                if copy_resp.success:
                    self.status_label.setText(f"Profile '{new_name}' created from copy")
                    self._load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to copy profile: {copy_resp.message}")
            else:
                self.status_label.setText("Copy profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error copying profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_copy_profile")

    def _on_start(self) -> None:
        """
        Handle start button click to begin the operation.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected")
            return
            
        # Show progress section
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting operation...")
        self.file_count_label.setText("Files processed: 0")
        self.eta_label.setText("Estimated time: --")
        
        # For now, simulate progress - will implement actual operation later
        self._simulate_operation()

    def _simulate_operation(self) -> None:
        """
        Simulate an operation with progress updates.
        """
        import time
        total_files = 100  # Simulate 100 files
        
        for i in range(total_files + 1):
            time.sleep(0.05)  # Simulate work
            progress = int((i / total_files) * 100)
            self.progress_bar.setValue(progress)
            self.file_count_label.setText(f"Files processed: {i}/{total_files}")
            
            # Simple ETA calculation
            if i > 0:
                elapsed = time.time() - self.start_time
                remaining = (elapsed / i) * (total_files - i)
                self.eta_label.setText(f"Estimated time: {remaining:.1f}s remaining")
            
            # Process events to update UI
            QApplication.processEvents()
            
        self.status_label.setText("Operation completed")
        # Show results dialog
        self._show_results_dialog()

    def _show_results_dialog(self) -> None:
        """
        Show the results dialog after operation completion.
        """
        # For now, show a message - will implement full results dialog later
        from src.pk_py_lib.gui.utils.messages import show_selectable_info
        show_selectable_info(
            self,
            "Operation Complete",
            "The operation has completed successfully.\n\n"
            f"Profile: {self.active_profile.get('name', 'Unnamed')}\n"
            "Files processed: 100\n"
            "Duplicates found: 5\n"
            "Time taken: 5.0 seconds"
        )

    def load_profiles(self) -> None:
        """
        Public method to load profiles after database manager is available.
        This should be called after the database manager is set on the window.
        """
        # Initialize the controller with the database manager
        if hasattr(self, 'database_manager') and self.database_manager is not None:
            try:
                from src.pk_py_lib.api.settings_profiles import SettingsProfilesAPI
                from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
                api = SettingsProfilesAPI(self.database_manager)
                self.controller = SettingsManagerController(api)
            except ImportError:
                self.status_label.setText("Settings Manager controller not available")
                return
        self._load_profiles()

    def _load_profile_into_editor(self, profile_id: str) -> None:
        """
        Load the selected profile into the structured editor.

        Parameters
        ----------
        profile_id : str
            The ID of the profile to load into the editor.
        """
        if self.controller is None:
            return

        # Create structured editor if it doesn't exist
        if self.structured_editor is None:
            try:
                from src.pk_py_lib.gui.settings_manager.structured_editor import StructuredProfileEditorWidget
                self.structured_editor = StructuredProfileEditorWidget(api=self.controller.api, parent=self)
                # Reset connection tracking when editor instance changes
                self._editor_dirty_connected = False
                # Replace the placeholder with the actual editor
                if self.stacked_widget.count() > 1:
                    self.stacked_widget.removeWidget(self.structured_editor_placeholder)
                    self.stacked_widget.addWidget(self.structured_editor)
                else:
                    self.stacked_widget.addWidget(self.structured_editor)
            except ImportError:
                self.status_label.setText("Structured editor not available")
                return

        # Load the profile data
        resp = self.controller.get_profile(profile_id)
        if resp.success and resp.data:
            # Extract Option A payload when profile is JSON-format; otherwise pass as-is
            payload = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data
            self.structured_editor.load_profile(payload)
            # Connect dirtyChanged signal to update save/cancel buttons (connect-once pattern)
            if hasattr(self.structured_editor, 'dirtyChanged') and self.structured_editor.dirtyChanged is not None:
                # Avoid calling disconnect() on an unconnected slot (PySide logs a RuntimeWarning)
                if not getattr(self, "_editor_dirty_connected", False):
                    self.structured_editor.dirtyChanged.connect(self._on_editor_dirty_changed)
                    self._editor_dirty_connected = True
            # Switch to the editor view
            self.stacked_widget.setCurrentIndex(1)
            # Initially disable save/cancel buttons
            self._update_save_cancel_buttons(False)
        else:
            self.status_label.setText(f"Failed to load profile: {resp.message}")

    def _on_rename_profile(self) -> None:
        """
        Handle rename profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to rename")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            current_name = self.active_profile.get('name', 'Unnamed')
            
            # Create a name prompt dialog
            dlg = _NamePromptDialog("Rename Profile", "New name:", current_name, self)
            
            if dlg.exec() == QDialog.Accepted:
                new_name = dlg.text()
                if not new_name:
                    dlg.set_error("Name is required")
                    return
                
                # Validate the name
                validate_resp = self.controller.validate_name(new_name)
                if not validate_resp.success:
                    dlg.set_error(validate_resp.message or "Invalid name")
                    return
                
                # Rename the profile
                rename_resp = self.controller.rename_profile(self.active_profile['id'], new_name)
                
                if rename_resp.success:
                    self.status_label.setText(f"Profile renamed to '{new_name}'")
                    self._load_profiles()  # Reload profiles to reflect the change
                else:
                    self.status_label.setText(f"Failed to rename profile: {rename_resp.message}")
            else:
                self.status_label.setText("Rename profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error renaming profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_rename_profile")

    def _on_delete_profile(self) -> None:
        """
        Handle delete profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to delete")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            profile_name = self.active_profile.get('name', 'Unnamed')
            
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete the profile '{profile_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                delete_resp = self.controller.delete_profile(self.active_profile['id'])
                
                if delete_resp.success:
                    self.status_label.setText(f"Profile '{profile_name}' deleted")
                    self._load_profiles()  # Reload profiles
                else:
                    self.status_label.setText(f"Failed to delete profile: {delete_resp.message}")
            else:
                self.status_label.setText("Delete profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error deleting profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_delete_profile")

    def _on_set_active_profile(self) -> None:
        """
        Handle set active profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No profile selected to set as active")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            set_active_resp = self.controller.set_active(self.active_profile['id'])
            
            if set_active_resp.success:
                self.status_label.setText(f"Profile '{self.active_profile.get('name', 'Unnamed')}' set as active")
                self._load_profiles()  # Reload to update active indicator
            else:
                self.status_label.setText(f"Failed to set active profile: {set_active_resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error setting active profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_set_active_profile")

    def _on_save_profile(self) -> None:
        """
        Handle save profile button click - save changes to the current profile.
        """
        if not self.active_profile or not self.structured_editor:
            self.status_label.setText("No profile selected or editor not available")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            # Validate the profile before saving
            is_valid, errors = self.structured_editor.get_validation_status()
            if not is_valid:
                error_msg = errors[0] if errors else "Profile validation failed"
                self.status_label.setText(f"Cannot save: {error_msg}")
                return

            # Gather changes from the editor
            profile_data = self.structured_editor.gather_changes()
            
            # Update the profile using the controller
            update_resp = self.controller.update_structured_profile(
                profile_id=self.active_profile['id'],
                profile_json=profile_data
            )
            
            if update_resp.success:
                self.status_label.setText(f"Profile '{profile_data.get('name', 'Unnamed')}' saved successfully")
                # Reset dirty state
                self.structured_editor.reset_dirty()
                self._update_save_cancel_buttons(False)
                # Reload profiles to reflect any name changes
                self._load_profiles()
                # Reload the current profile into the editor to ensure UI reflects saved state
                if self.active_profile:
                    self._load_profile_into_editor(self.active_profile['id'])
            else:
                self.status_label.setText(f"Failed to save profile: {update_resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error saving profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_save_profile")

    def _on_cancel_changes(self) -> None:
        """
        Handle cancel changes button click - discard unsaved changes.
        """
        if not self.active_profile or not self.structured_editor:
            self.status_label.setText("No profile selected or editor not available")
            return

        try:
            # Reload the original profile data to discard changes
            resp = self.controller.get_profile(self.active_profile['id'])
            if resp.success and resp.data:
                # For JSON-format profiles, reload editor with the embedded json_data payload
                payload = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data
                self.structured_editor.load_profile(payload)
                self.status_label.setText("Changes discarded")
                self._update_save_cancel_buttons(False)
            else:
                self.status_label.setText(f"Failed to reload profile: {resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error discarding changes: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_cancel_changes")

    def _on_editor_dirty_changed(self, dirty: bool) -> None:
        """
        Handle dirty state changes from the structured editor.
        
        Parameters
        ----------
        dirty : bool
            True if there are unsaved changes, False otherwise.
        """
        self._update_save_cancel_buttons(dirty)

    def _update_save_cancel_buttons(self, enabled: bool) -> None:
        """
        Update the enabled state of save and cancel buttons.
        
        Parameters
        ----------
        enabled : bool
            True to enable buttons, False to disable.
        """
        self.save_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)

    def _make_noop_action(self, text: str) -> QAction:
        """
        Create a no-op QAction placeholder.

        Parameters
        ----------
        text : str
            Display text for the action.

        Returns
        -------
        QAction
            Action connected to a lambda that performs no behavior.
        """
        action = QAction(text, self)
        action.triggered.connect(lambda: None)
        return action