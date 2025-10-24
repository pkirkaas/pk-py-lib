"""
GUI message utilities for pk-py-lib.

This module provides utilities for displaying messages, errors, and dialogs
in GUI applications with proper error handling and logging.
"""

from __future__ import annotations

from typing import Any, Optional
from PySide6.QtWidgets import QWidget, QMessageBox, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core.logging.logger import get_logger
from ...core.api.response import ErrorCodes


logger = get_logger(__name__)


def _enable_label_selection(label: QLabel) -> None:
    """
    Enable text selection on a QLabel.

    Args:
        label: QLabel to enable selection on
    """
    label.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    label.setCursor(Qt.IBeamCursor)


def show_selectable_error(
    parent: Optional[QWidget],
    title: str,
    message: str,
    details: Optional[str] = None
) -> None:
    """
    Show an error dialog with selectable text.

    Args:
        parent: Parent widget
        title: Dialog title
        message: Error message (will be selectable)
        details: Optional additional details
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setIcon(QMessageBox.Critical)

    # Main message
    main_label = QLabel(message)
    _enable_label_selection(main_label)

    # Additional details if provided
    if details:
        details_label = QLabel(f"\nDetails:\n{details}")
        details_label.setStyleSheet("QLabel { color: #666; }")
        _enable_label_selection(details_label)

        # Combine messages
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(main_label)
        layout.addWidget(details_label)

        msg_box.layout().addWidget(container)
    else:
        msg_box.setText(message)

    msg_box.exec()


def show_selectable_warning(
    parent: Optional[QWidget],
    title: str,
    message: str,
    details: Optional[str] = None
) -> None:
    """
    Show a warning dialog with selectable text.

    Args:
        parent: Parent widget
        title: Dialog title
        message: Warning message (will be selectable)
        details: Optional additional details
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setIcon(QMessageBox.Warning)

    # Main message
    main_label = QLabel(message)
    _enable_label_selection(main_label)

    # Additional details if provided
    if details:
        details_label = QLabel(f"\nDetails:\n{details}")
        details_label.setStyleSheet("QLabel { color: #666; }")
        _enable_label_selection(details_label)

        # Combine messages
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(main_label)
        layout.addWidget(details_label)

        msg_box.layout().addWidget(container)
    else:
        msg_box.setText(message)

    msg_box.exec()


def show_selectable_info(
    parent: Optional[QWidget],
    title: str,
    message: str,
    details: Optional[str] = None
) -> None:
    """
    Show an info dialog with selectable text.

    Args:
        parent: Parent widget
        title: Dialog title
        message: Info message (will be selectable)
        details: Optional additional details
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setIcon(QMessageBox.Information)

    # Main message
    main_label = QLabel(message)
    _enable_label_selection(main_label)

    # Additional details if provided
    if details:
        details_label = QLabel(f"\nDetails:\n{details}")
        details_label.setStyleSheet("QLabel { color: #666; }")
        _enable_label_selection(details_label)

        # Combine messages
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(main_label)
        layout.addWidget(details_label)

        msg_box.layout().addWidget(container)
    else:
        msg_box.setText(message)

    msg_box.exec()


def handle_gui_error(
    parent: Optional[QWidget],
    error: Exception,
    title: str,
    component_name: str = "Unknown",
    file_path: Optional[str] = None,
    operation_type: Optional[str] = None,
    error_code: Optional[str] = None
) -> None:
    """
    Handle a GUI error with both user dialog and detailed logging.

    This function provides the comprehensive error handling required by
    the project specifications, including selectable error dialogs and
    detailed STDERR logging with all relevant context.

    Args:
        parent: Parent widget for the dialog
        error: Exception or error message
        title: Dialog title
        component_name: Name of the component where error occurred
        file_path: File path involved in the error
        operation_type: Type of operation being performed
        error_code: Optional error code
    """
    # Determine error message
    if isinstance(error, Exception):
        error_message = str(error)
        # Get full traceback for logging
        import traceback
        full_traceback = traceback.format_exc()
    else:
        error_message = str(error)
        full_traceback = ""

    # Build context information
    context = {
        "component": component_name,
        "operation": operation_type,
        "file_path": file_path,
        "error_code": error_code
    }

    # Log detailed error information to STDERR
    _log_error_details(
        component_name=component_name,
        error_message=error_message,
        file_path=file_path,
        operation_type=operation_type,
        error_code=error_code,
        traceback=full_traceback,
        context=context
    )

    # Show user-friendly error dialog
    full_message = error_message
    if file_path:
        full_message += f"\n\nFile: {file_path}"
    if operation_type:
        full_message += f"\nOperation: {operation_type}"

    show_selectable_error(parent, title, full_message)


def _log_error_details(
    component_name: str,
    error_message: str,
    file_path: Optional[str] = None,
    operation_type: Optional[str] = None,
    error_code: Optional[str] = None,
    traceback: str = "",
    context: Optional[dict] = None
) -> None:
    """
    Log detailed error information to STDERR.

    This function ensures all required error details are logged as specified
    in the project requirements:
    - Full error text/description
    - Full file path of the component
    - Parameters/values that caused the error
    - Call stack that led to the error

    Args:
        component_name: Name of the component where error occurred
        error_message: The error message
        file_path: File path involved in the error
        operation_type: Type of operation being performed
        error_code: Optional error code
        traceback: Full traceback string
        context: Additional context information
    """
    try:
        # Try to get file path from traceback if not provided
        if not file_path and traceback:
            import traceback as tb
            # Extract file path from traceback
            lines = traceback.split('\n')
            for line in lines:
                if 'File "' in line:
                    # Extract file path from traceback line
                    file_part = line.split('File "')[1].split('"')[0]
                    file_path = file_part
                    break

        # Build detailed error message
        error_details = [
            "=" * 60,
            "GUI ERROR DETAILS",
            "=" * 60,
            f"Component: {component_name}",
            f"Error: {error_message}",
        ]

        if file_path:
            error_details.append(f"File Path: {file_path}")

        if operation_type:
            error_details.append(f"Operation: {operation_type}")

        if error_code:
            error_details.append(f"Error Code: {error_code}")

        if context:
            error_details.append("Context:")
            for key, value in context.items():
                if value is not None:
                    error_details.append(f"  {key}: {value}")

        if traceback:
            error_details.extend([
                "",
                "Traceback:",
                traceback.rstrip()
            ])

        error_details.extend([
            "=" * 60,
            ""
        ])

        # Log to STDERR
        full_error_text = '\n'.join(error_details)
        print(full_error_text, file=sys.stderr)

        # Also log to logger if available
        try:
            logger.error(
                f"GUI error in {component_name}",
                error_message=error_message,
                component=component_name,
                file_path=file_path,
                operation=operation_type,
                error_code=error_code,
                context=context,
                exc_info=traceback or None
            )
        except Exception:
            # If logger fails, at least we have stderr output
            pass

    except Exception as e:
        # Fallback if even error logging fails
        print(f"ERROR: Failed to log error details: {e}", file=sys.stderr)
        print(f"ERROR: Original error: {error_message}", file=sys.stderr)


class GUIErrorHandler:
    """
    Decorator class for automatic GUI error handling.

    This decorator can be applied to methods to automatically handle
    exceptions with the comprehensive error handling system.
    """

    def __init__(
        self,
        component_name: Optional[str] = None,
        operation: Optional[str] = None,
        title: Optional[str] = None
    ):
        """
        Initialize the error handler decorator.

        Args:
            component_name: Name of the component (auto-detected if None)
            operation: Operation type (auto-detected if None)
            title: Error dialog title (auto-generated if None)
        """
        self.component_name = component_name
        self.operation = operation
        self.title = title

    def __call__(self, func):
        """Apply the error handler decorator to a function."""
        return _GUIErrorHandlerDecorator(
            func,
            component_name=self.component_name,
            operation=self.operation,
            title=self.title
        )


class _GUIErrorHandlerDecorator:
    """Internal decorator implementation."""

    def __init__(
        self,
        func,
        component_name: Optional[str] = None,
        operation: Optional[str] = None,
        title: Optional[str] = None
    ):
        self.func = func
        self.component_name = component_name or func.__name__
        self.operation = operation or func.__name__
        self.title = title or f"Error in {self.component_name}"

    def __call__(self, *args, **kwargs):
        """Call the decorated function with error handling."""
        try:
            return self.func(*args, **kwargs)
        except Exception as e:
            # Determine parent widget from arguments
            parent = self._find_parent_widget(args)

            # Extract context from arguments
            context = self._extract_context(args, kwargs)

            handle_gui_error(
                parent=parent,
                error=e,
                title=self.title,
                component_name=self.component_name,
                operation_type=self.operation,
                **context
            )
            # Re-raise to allow calling code to handle cleanup
            raise

    def _find_parent_widget(self, args) -> Optional[QWidget]:
        """Find parent widget from function arguments."""
        # Check if first argument is a QWidget
        if args and hasattr(args[0], 'isWidget') and args[0].isWidget():
            return args[0]
        return None

    def _extract_context(self, args, kwargs) -> dict:
        """Extract context information from function arguments."""
        context = {}

        # Extract common parameter names
        if 'file_path' in kwargs:
            context['file_path'] = kwargs['file_path']
        elif len(args) > 1:
            context['file_path'] = str(args[1]) if len(args) > 1 else None

        return context


class GUIErrorContext:
    """
    Context manager for GUI error handling.

    This context manager can be used to handle errors within a specific
    operation or block of code.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        component_name: str,
        operation: str,
        title: Optional[str] = None
    ):
        """
        Initialize the error context manager.

        Args:
            parent: Parent widget
            component_name: Component name
            operation: Operation name
            title: Error dialog title
        """
        self.parent = parent
        self.component_name = component_name
        self.operation = operation
        self.title = title or f"Error in {component_name}"

    def __enter__(self):
        """Enter the error handling context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and handle any errors."""
        if exc_type is not None:
            handle_gui_error(
                parent=self.parent,
                error=exc_val,
                title=self.title,
                component_name=self.component_name,
                operation_type=self.operation
            )
            return False  # Re-raise the exception
        return True


# Convenience decorators
def gui_error_handler(
    component_name: Optional[str] = None,
    operation: Optional[str] = None,
    title: Optional[str] = None
):
    """
    Decorator for automatic GUI error handling.

    Args:
        component_name: Name of the component (auto-detected if None)
        operation: Operation type (auto-detected if None)
        title: Error dialog title (auto-generated if None)

    Returns:
        Decorated function
    """
    def decorator(func):
        return _GUIErrorHandlerDecorator(
            func,
            component_name=component_name,
            operation=operation,
            title=title
        )
    return decorator


def gui_error_context(
    parent: Optional[QWidget],
    component_name: str,
    operation: str,
    title: Optional[str] = None
):
    """
    Context manager for GUI error handling.

    Args:
        parent: Parent widget
        component_name: Component name
        operation: Operation name
        title: Error dialog title

    Returns:
        GUIErrorContext manager
    """
    return GUIErrorContext(parent, component_name, operation, title)


# Import sys for stderr logging
import sys
