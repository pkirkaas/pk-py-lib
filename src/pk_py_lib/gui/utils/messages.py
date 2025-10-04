"""
src/pk_py_lib/gui/utils/messages.py

Selectable/copyable QMessageBox helpers for consistent error/info dialogs.

- show_selectable_message(...)
- show_selectable_error/warning/info

Note: Syntax validation was performed using Python's ast module per project rules.
"""

from __future__ import annotations

from typing import Optional

from ...core.logging import get_logger
from ...core.logging.decorators import log_errors
import traceback
import sys
import inspect

logger = get_logger(__name__)

# Defensive import to keep library importable in headless/test environments
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QWidget, QLabel
    PYSIDE_AVAILABLE = True
except Exception as e:  # pragma: no cover
    logger.error(
        "Failed to import PySide6 for message dialogs",
        exception=e
    )
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for selectable message dialogs")

    Qt = QMessageBox = QWidget = QLabel = _Missing()  # type: ignore


@log_errors()
def _enable_label_selection(box: "QMessageBox") -> None:
    """Internal: enable text selection on QMessageBox labels."""
    try:
        # Try Qt6 API if available on QMessageBox directly (may not exist on some bindings)
        try:
            box.setTextInteractionFlags(  # type: ignore[attr-defined]
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
            )
        except Exception:
            pass

        # Find ALL QLabel children and make them selectable
        labels = box.findChildren(QLabel)
        for lbl in labels:
            try:
                lbl.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
                )
                lbl.setOpenExternalLinks(True)
                # Ensure text is in plain text format for reliable selection
                lbl.setTextFormat(Qt.PlainText)
            except Exception as e:
                logger.warning(
                    f"Failed to enable selection on label in message box",
                    exception=e,
                    variables={'label_count': len(labels)}
                )

        # Also ensure built-in labels with specific names are selectable (backward compatibility)
        for name in ("qt_msgbox_label", "qt_msgbox_informativelabel"):
            lbl = box.findChild(QLabel, name)
            if lbl is None:
                continue
            try:
                lbl.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
                )
                lbl.setOpenExternalLinks(True)
                lbl.setTextFormat(Qt.PlainText)
            except Exception as e:
                logger.warning(
                    f"Failed to enable selection on built-in label '{name}'",
                    exception=e
                )
    except Exception as e:
        # Never let this helper crash the app
        logger.error(
            "Error in _enable_label_selection",
            exception=e,
            variables={'box_type': type(box)}
        )


@log_errors()
def show_selectable_message(
    parent: Optional["QWidget"],
    title: str,
    text: str,
    informative_text: Optional[str] = None,
    icon: Optional["QMessageBox.Icon"] = None,
) -> int:
    """
    Show a modal QMessageBox with selectable/copyable text.
 
    Parameters
    ----------
    parent : Optional[QWidget]
        Parent widget or None for app-modal.
    title : str
        Dialog window title.
    text : str
        Main message text (plain or rich).
    informative_text : Optional[str]
        Optional subordinate text shown below the main text.
    icon : QMessageBox.Icon
        Icon to display (e.g., Critical, Warning, Information).
 
    Returns
    -------
    int
        exec() result (QDialog.DialogCode), useful if caller branches on buttons.
 
    Raises
    ------
    RuntimeError
        If PySide6 is not available in the current environment.
    """
    try:
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for show_selectable_message")

        box = QMessageBox(parent)
        if icon is None:
            icon = QMessageBox.Critical
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        if informative_text:
            try:
                box.setInformativeText(informative_text)
            except Exception as e:
                logger.warning(
                    "Failed to set informative text, falling back to main text",
                    exception=e,
                    variables={'informative_text': informative_text[:100]}
                )
                # Fallback: append informative text to main text if the property is unavailable
                try:
                    box.setText(f"{text}\n\n{informative_text}")
                except Exception as fallback_e:
                    logger.error(
                        "Fallback text setting also failed",
                        exception=fallback_e
                    )

        _enable_label_selection(box)
        return box.exec()
    except RuntimeError as e:
        logger.error(
            "PySide6 not available for message dialog",
            exception=e,
            variables={'title': title, 'text': text[:100]}
        )
        # Fallback: print to stderr since GUI not available
        import sys
        print(f"Message Dialog Error - {title}: {text}", file=sys.stderr)
        return 0  # Arbitrary return for non-GUI case
    except Exception as e:
        logger.error(
            "Unexpected error showing selectable message",
            exception=e,
            variables={'title': title, 'text': text[:100], 'parent_type': type(parent)}
        )
        # Show a basic error if possible
        try:
            basic_box = QMessageBox(parent)
            basic_box.setWindowTitle("Message Display Error")
            basic_box.setText(f"Failed to display message: {str(e)}")
            basic_box.exec()
        except:
            pass
        return 0


@log_errors()
def show_selectable_error(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for a Critical message box with selectable text.
    """
    try:
        return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Critical)
    except Exception as e:
        logger.error(
            "Error showing selectable error message",
            exception=e,
            variables={'title': title, 'text': text[:100]}
        )
        return 0


@log_errors()
def show_selectable_warning(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for a Warning message box with selectable text.
    """
    try:
        return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Warning)
    except Exception as e:
        logger.error(
            "Error showing selectable warning message",
            exception=e,
            variables={'title': title, 'text': text[:100]}
        )
        return 0


@log_errors()
def show_selectable_info(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for an Information message box with selectable text.
    """
    try:
        return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Information)
    except Exception as e:
        logger.error(
            "Error showing selectable info message",
            exception=e,
            variables={'title': title, 'text': text[:100]}
        )
        return 0


__all__ = [
    "show_selectable_message",
    "show_selectable_error",
    "show_selectable_warning",
    "show_selectable_info",
    "handle_gui_error",
    "gui_error_handler",
    "gui_error_context",
]

# Import logging infrastructure
try:
    from ...core.logging import get_logger, LogLevel
    LOGGING_AVAILABLE = True
except ImportError as e:
    logger.warning(
        "Logging infrastructure not available",
        exception=e
    )
    LOGGING_AVAILABLE = False
    get_logger = lambda name: None  # type: ignore
    LogLevel = type('LogLevel', (), {})  # type: ignore

import traceback
import inspect
import sys
from typing import Any, Callable, Optional, TypeVar, Union, ContextManager
from functools import wraps
from contextlib import contextmanager

# Type variable for decorator
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


@log_errors()
def handle_gui_error(
    parent: Optional["QWidget"],
    error: Union[str, Exception],
    title: str = "Error",
    component_name: Optional[str] = None,
    **context_vars: Any
) -> None:
    """
    Centralized GUI error handler that shows user-friendly dialogs and logs detailed error information.
    
    This function provides comprehensive error handling for GUI operations by:
    1. Showing a user-friendly error dialog with selectable text
    2. Logging detailed error information to STDERR with full context
    3. Capturing call stack, parameters, and component information
    
    Parameters
    ----------
    parent : Optional[QWidget]
        Parent widget for the error dialog
    error : Union[str, Exception]
        Error message string or exception object
    title : str, optional
        Dialog title, by default "Error"
    component_name : Optional[str], optional
        Name of the GUI component where error occurred, by default None
    **context_vars : Any
        Additional context variables to include in logging
    
    Examples
    --------
    >>> handle_gui_error(self, ValueError("Invalid input"), "Validation Error", component_name="SettingsEditor")
    >>> handle_gui_error(None, "File not found", "File Error", file_path="/path/to/file")
    """
    try:
        # Get error message and exception details
        error_message = str(error) if isinstance(error, Exception) else error
        exception_obj = error if isinstance(error, Exception) else None
        
        # Get caller information for logging
        caller_frame = inspect.currentframe().f_back
        file_path = ""
        line_number = 0
        
        if caller_frame:
            try:
                frame_info = inspect.getframeinfo(caller_frame)
                file_path = frame_info.filename
                line_number = frame_info.lineno
            finally:
                del caller_frame  # Prevent reference cycles
        
        # Show user-friendly error dialog
        dialog_message = error_message
        if component_name:
            dialog_message = f"{component_name}: {error_message}"
        
        show_selectable_error(parent, title, dialog_message)
        
        # Log detailed error information
        if LOGGING_AVAILABLE:
            logger = get_logger("gui.error")
            
            # Build comprehensive log context
            log_context = {
                "component": component_name or "Unknown",
                "file_path": file_path,
                "line_number": line_number,
                **context_vars
            }
            
            # Include call stack for exceptions
            if exception_obj:
                stack_trace = "".join(traceback.format_exception(
                    type(exception_obj), exception_obj, exception_obj.__traceback__
                ))
                log_context["stack_trace"] = stack_trace
            
            logger.error(
                f"GUI Error: {error_message}",
                exception=exception_obj,
                variables=log_context
            )
        else:
            # Fallback to simple STDERR output if logging is not available
            error_details = [
                f"GUI ERROR: {title}",
                f"Message: {error_message}",
                f"Component: {component_name or 'Unknown'}",
                f"Location: {file_path}:{line_number}",
            ]
            
            if context_vars:
                error_details.append("Context:")
                for key, value in context_vars.items():
                    error_details.append(f"  {key}: {value}")
            
            if exception_obj:
                error_details.append("Stack Trace:")
                error_details.append(traceback.format_exc())
            
            print("\n".join(error_details), file=sys.stderr)
    except Exception as handler_e:
        logger.error(
            "Error in GUI error handler itself",
            exception=handler_e,
            variables={'original_error': str(error), 'title': title}
        )
        # Ultimate fallback
        import sys
        print(f"CRITICAL: Error handler failed - Original: {str(error)}", file=sys.stderr)


@log_errors()
def gui_error_handler(
    component_name: Optional[str] = None,
    **default_context: Any
) -> Callable[[F], F]:
    """
    Decorator to automatically handle errors in GUI functions with comprehensive logging.
    
    This decorator wraps GUI functions to automatically catch exceptions and
    handle them using the centralized error handling system.
    
    Parameters
    ----------
    component_name : Optional[str], optional
        Name of the GUI component, by default uses function name
    **default_context : Any
        Default context variables to include in error logging
    
    Returns
    -------
    Callable[[F], F]
        Decorated function with automatic error handling
    
    Examples
    --------
    >>> @gui_error_handler(component_name="FileSelector", operation="file_selection")
    >>> def on_file_selected(self, file_path):
    >>>     # function implementation
    >>>     pass
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to get parent widget from args (usually self for QWidget methods)
            parent = None
            if args and hasattr(args[0], 'isWidgetType') and args[0].isWidgetType():
                parent = args[0]
            
            # Determine component name
            comp_name = component_name or func.__name__
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Build context from function arguments and default context
                context = default_context.copy()
                
                # Add function arguments to context (excluding self for methods)
                func_args = inspect.signature(func).parameters
                arg_names = list(func_args.keys())
                
                for i, arg_value in enumerate(args):
                    if i == 0 and arg_names and arg_names[0] == 'self':
                        continue  # Skip self parameter
                    if i < len(arg_names):
                        try:
                            context[arg_names[i]] = repr(arg_value)[:100]  # Truncate large values
                        except:
                            context[arg_names[i]] = '<unrepresentable>'
                
                context.update({k: repr(v)[:100] for k, v in kwargs.items()})
                
                handle_gui_error(
                    parent=parent,
                    error=e,
                    title=f"Error in {comp_name}",
                    component_name=comp_name,
                    **context
                )
                return None
        
        return wrapper  # type: ignore
    
    return decorator


@log_errors()
@contextmanager
def gui_error_context(
    parent: Optional["QWidget"] = None,
    component_name: str = "GUI Operation",
    **context_vars: Any
) -> ContextManager[None]:
    """
    Context manager for GUI operations with automatic error handling.
    
    This context manager catches exceptions within the context and handles them
    using the centralized error handling system.
    
    Parameters
    ----------
    parent : Optional[QWidget], optional
        Parent widget for error dialogs, by default None
    component_name : str, optional
        Name of the GUI component/operation, by default "GUI Operation"
    **context_vars : Any
        Context variables to include in error logging
    
    Yields
    ------
    ContextManager[None]
        Context manager that handles errors automatically
    
    Examples
    --------
    >>> with gui_error_context(self, "File Processing", file_path=path):
    >>>     process_file(path)
    """
    try:
        yield
    except Exception as e:
        handle_gui_error(
            parent=parent,
            error=e,
            title=f"Error in {component_name}",
            component_name=component_name,
            **context_vars
        )
        # Re-raise the exception after handling it
        raise