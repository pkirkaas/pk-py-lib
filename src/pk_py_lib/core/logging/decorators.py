"""
Logging Decorators

Decorators for automatic function call logging, performance tracking, and variable watching.
"""

import functools
import time
from typing import Any, Callable, Optional
from .logger import get_logger
import sys
import traceback
import inspect
import warnings

# Get module logger
logger = get_logger(__name__)


def log_calls(
    level: str = "INFO",
    include_args: bool = True,
    include_result: bool = True,
    logger_name: Optional[str] = None
):
    """
    Decorator to automatically log function calls.
    
    Args:
        level: Log level for the messages (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_args: Whether to include function arguments in the log
        include_result: Whether to include function result in the log
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        @log_calls()
        def example_function(x, y):
            return x + y
            
        @log_calls(level="DEBUG", include_args=False)
        def another_function(name):
            return f"Hello, {name}!"
    """
    def decorator(func: Callable) -> Callable:
        # Get logger for this function
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Log function entry
            if include_args and (args or kwargs):
                args_str = ", ".join([repr(arg) for arg in args])
                kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                all_args = ", ".join(filter(None, [args_str, kwargs_str]))
                func_logger.log(level, f"Calling {func.__name__}({all_args})")
            else:
                func_logger.log(level, f"Calling {func.__name__}()")
            
            # Execute function
            try:
                result = func(*args, **kwargs)
                
                # Log function exit with result
                if include_result:
                    func_logger.log(level, f"{func.__name__} returned: {repr(result)}")
                else:
                    func_logger.log(level, f"{func.__name__} completed successfully")
                
                return result
                
            except Exception as e:
                # Log exception
                func_logger.error(f"{func.__name__} raised {type(e).__name__}: {e}", exception=e)
                raise
        
        return wrapper
    return decorator


def log_performance(
    threshold: Optional[float] = None,
    level: str = "INFO",
    logger_name: Optional[str] = None
):
    """
    Decorator to log function execution time.
    
    Args:
        threshold: Optional time threshold in seconds - only log if execution time exceeds this
        level: Log level for the messages
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        @log_performance()
        def slow_function():
            time.sleep(1)
            return "done"
            
        @log_performance(threshold=0.5)
        def sometimes_slow_function():
            # Only logs if execution time > 0.5 seconds
            return "result"
    """
    def decorator(func: Callable) -> Callable:
        # Get logger for this function
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.perf_counter() - start_time
                
                # Log if no threshold or if execution time exceeds threshold
                if threshold is None or execution_time >= threshold:
                    func_logger.log(level, f"{func.__name__} executed in {execution_time:.4f}s")
                
                return result
                
            except Exception:
                execution_time = time.perf_counter() - start_time
                func_logger.error(f"{func.__name__} failed after {execution_time:.4f}s")
                raise
        
        return wrapper
    return decorator


def watch_variables(*var_names: str, level: str = "DEBUG", logger_name: Optional[str] = None):
    """
    Decorator to watch and log specific variable values during function execution.
    
    Note: This is a simplified implementation. A full implementation would require
    more complex introspection to access local variables by name.
    
    Args:
        var_names: Names of variables to watch
        level: Log level for the messages
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        @watch_variables('x', 'y')
        def calculate(x, y):
            z = x * y
            return z
    """
    def decorator(func: Callable) -> Callable:
        # Get logger for this function
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger.log(level, f"Watching variables: {', '.join(var_names)} in {func.__name__}")
            
            # In a real implementation, we would need to inspect the function's
            # local variables during execution, which is complex.
            # For now, we'll just log that we're watching.
            
            try:
                result = func(*args, **kwargs)
                func_logger.log(level, f"{func.__name__} completed")
                return result
            except Exception as e:
                func_logger.error(f"{func.__name__} failed: {e}")
                raise
        
        return wrapper
    return decorator


def log_errors(
    level: str = "ERROR",
    include_args: bool = True,
    include_traceback: bool = True,
    logger_name: Optional[str] = None
):
    """
    Decorator to catch and log exceptions with file path, line number, function name,
    parameters, locals context (especially for GUI: self class, widget states), and traceback.
    
    Enhanced for GUI components: captures locals at the exception site, including self.class.name
    and widget identifiers if available (e.g., objectName for Qt widgets). Filters safe variables
    and truncates large representations.
    
    Args:
        level: Log level for the error messages (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_args: Whether to include function arguments in the log
        include_traceback: Whether to include the full traceback (handled by logger now)
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        @log_errors()
        def risky_function(param):
            if param < 0:
                raise ValueError("Negative parameter")
            return param * 2
        
        class TestWidget:
            @log_errors()
            def gui_method(self, user_input):
                # Simulate GUI error
                if not user_input:
                    raise ValueError("Empty input")
    """
    def decorator(func: Callable) -> Callable:
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Get file and line from the exception frame
                exc_type, exc_value, exc_traceback = sys.exc_info()
                frame = exc_traceback.tb_frame if exc_traceback else None
                filename = frame.f_code.co_filename if frame else __file__
                lineno = exc_traceback.tb_lineno if exc_traceback else 0
                func_name = func.__name__
                
                # Format parameters
                if include_args and (args or kwargs):
                    args_str = ", ".join([repr(arg) for arg in args])
                    kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                    params_str = ", ".join(filter(None, [args_str, kwargs_str]))
                else:
                    params_str = ""
                
                error_msg = f"Error in {func_name} at {filename}:{lineno}: {exc_type.__name__}: {str(e)}"
                if params_str:
                    error_msg += f"\nParameters: {params_str}"
                
                # Capture relevant locals at error site for GUI context
                error_locals = {}
                if frame:
                    try:
                        locals_dict = frame.f_locals
                        for key, value in locals_dict.items():
                            if key == 'self' and hasattr(value, '__class__'):
                                error_locals['self_class'] = value.__class__.__name__
                                # Capture GUI-specific states if Qt-like widget
                                if hasattr(value, 'objectName'):
                                    error_locals['widget_objectName'] = value.objectName()
                                elif hasattr(value, 'windowTitle'):
                                    error_locals['window_title'] = value.windowTitle()
                                # Capture user inputs or common GUI vars
                                if hasattr(value, 'text') and callable(value.text):
                                    error_locals['current_text'] = value.text()[:50]  # Truncate
                            elif not key.startswith('_') and not callable(value) and not isinstance(value, type):
                                try:
                                    error_locals[key] = repr(value)[:100]  # Truncate large reps
                                except (Exception):
                                    error_locals[key] = '<unrepresentable>'
                    except Exception:
                        error_locals['capture_error'] = 'Failed to capture locals'
                
                # Log with full details: message, exception for traceback, variables for context
                try:
                    func_logger.error(
                        error_msg,
                        exception=e,
                        variables=error_locals
                    )
                except Exception as log_error:
                    # Fallback to stderr if logging fails
                    print(f"Failed to log error: {log_error}", file=sys.stderr)
                    print(error_msg, file=sys.stderr)
                    if error_locals:
                        print(f"Locals: {error_locals}", file=sys.stderr)
                    if include_traceback:
                        print(traceback.format_exc(), file=sys.stderr)
                
                raise
        
        return wrapper
    return decorator


def log_warnings(
    level: str = "WARNING",
    logger_name: Optional[str] = None
):
    """
    Decorator to catch and log warnings issued within the function using warnings.warn().
    
    Uses warnings.catch_warnings to record all warnings and logs them at the specified level.
    Does not suppress warnings; logs and allows them to propagate if desired.
    
    Args:
        level: Log level for the warning messages (default: "WARNING")
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        import warnings
        @log_warnings()
        def function_with_warning():
            warnings.warn("This is a test warning", UserWarning)
            return "done"
    """
    def decorator(func: Callable) -> Callable:
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with warnings.catch_warnings(record=True) as caught_warnings:
                # Ensure all warnings are recorded
                warnings.simplefilter("always")
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Log caught warnings
                for warning in caught_warnings:
                    warning_msg = f"Warning in {func.__name__}: {warning.message}"
                    if warning.filename and warning.lineno:
                        warning_msg += f" at {warning.filename}:{warning.lineno}"
                    if warning.category:
                        warning_msg += f" ({warning.category.__name__})"
                    
                    func_logger.log(level, warning_msg)
            
            return result
        
        return wrapper
    return decorator