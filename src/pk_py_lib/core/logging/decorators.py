"""
Logging Decorators

Decorators for automatic function call logging, performance tracking, and variable watching.
"""

import functools
import time
from typing import Any, Callable, Optional
from .logger import get_logger

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
                func_logger.error(f"{func.__name__} raised {type(e).__name__}: {e}")
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
    parameters, and traceback.
    
    Args:
        level: Log level for the error messages (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_args: Whether to include function arguments in the log
        include_traceback: Whether to include the full traceback in the log
        logger_name: Optional specific logger name to use instead of function's module
    
    Example:
        @log_errors()
        def risky_function(param):
            if param < 0:
                raise ValueError("Negative parameter")
            return param * 2
    """
    import sys
    import traceback
    
    def decorator(func: Callable) -> Callable:
        func_logger = get_logger(logger_name or func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Get file and line from the exception frame
                exc_type, exc_value, exc_traceback = sys.exc_info()
                frame = exc_traceback.tb_frame
                filename = frame.f_code.co_filename
                lineno = exc_traceback.tb_lineno
                func_name = func.__name__
                
                # Format parameters
                if include_args and (args or kwargs):
                    args_str = ", ".join([repr(arg) for arg in args])
                    kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                    params_str = ", ".join(filter(None, [args_str, kwargs_str]))
                else:
                    params_str = ""
                
                error_msg = f"Error in {func_name} at {filename}:{lineno}: {e}"
                if params_str:
                    error_msg += f"\nParameters: {params_str}"
                
                func_logger.error(error_msg)
                
                if include_traceback:
                    tb_str = traceback.format_exc()
                    func_logger.log(level, f"Traceback:\n{tb_str}")
                
                raise
        
        return wrapper
    return decorator