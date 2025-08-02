"""
Log Formatters

Formatting classes for converting LogEntry objects to various string representations.
"""

from typing import Any, Dict, Optional
from .logger import LogEntry, LogLevel


class LogFormatter:
    """Base class for log formatters."""
    
    def format(self, entry: LogEntry) -> str:
        """
        Format a log entry as a string.
        
        Args:
            entry: LogEntry to format
            
        Returns:
            Formatted string representation of the log entry
        """
        raise NotImplementedError


class SimpleFormatter(LogFormatter):
    """
    Simple log formatter that outputs basic information.
    
    Format: [LEVEL] timestamp - message
    """
    
    def format(self, entry: LogEntry) -> str:
        """
        Format a log entry as a simple string.
        
        Args:
            entry: LogEntry to format
            
        Returns:
            Formatted string like "[INFO] 2023-01-01 12:00:00 - Message"
        """
        # Convert timestamp to readable format
        from datetime import datetime
        timestamp = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        # Format basic message
        formatted = f"[{entry.level.name}] {timestamp} - {entry.message}"
        
        # Add context if available
        if entry.context:
            context_items = [f"{k}={v}" for k, v in entry.context.items()]
            formatted += f" [{', '.join(context_items)}]"
        
        # Add variables if available
        if entry.variables:
            var_items = [f"{k}={v}" for k, v in entry.variables.items()]
            formatted += f" Variables: {', '.join(var_items)}"
        
        return formatted


class DetailedFormatter(LogFormatter):
    """
    Detailed log formatter with comprehensive information.
    
    Format includes timestamp, level, source, line number, message, and metadata.
    """
    
    def format(self, entry: LogEntry) -> str:
        """
        Format a log entry with detailed information.
        
        Args:
            entry: LogEntry to format
            
        Returns:
            Formatted string with comprehensive log information
        """
        from datetime import datetime
        timestamp = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Start with basic information
        formatted = f"[{timestamp}] [{entry.level.name:>8}]"
        
        # Add source information if available
        if entry.source:
            source_info = entry.source
            if entry.line_number:
                source_info += f":{entry.line_number}"
            formatted += f" [{source_info}]"
        
        # Add thread information
        if entry.thread_id:
            formatted += f" [Thread:{entry.thread_id}]"
        
        # Add the main message
        formatted += f" {entry.message}"
        
        # Add context if available
        if entry.context:
            context_items = [f"{k}={v}" for k, v in entry.context.items()]
            formatted += f"\n    Context: {', '.join(context_items)}"
        
        # Add variables if available
        if entry.variables:
            var_items = [f"{k}={v}" for k, v in entry.variables.items()]
            formatted += f"\n    Variables: {', '.join(var_items)}"
        
        # Add exception if available
        if entry.exception:
            formatted += f"\n    Exception: {type(entry.exception).__name__}: {entry.exception}"
        
        return formatted


class JSONFormatter(LogFormatter):
    """
    JSON log formatter for structured logging.
    
    Outputs log entries as JSON objects for easy parsing and analysis.
    """
    
    def format(self, entry: LogEntry) -> str:
        """
        Format a log entry as a JSON string.
        
        Args:
            entry: LogEntry to format
            
        Returns:
            JSON-formatted string representation of the log entry
        """
        import json
        
        # Convert log entry to dictionary
        entry_dict = {
            "timestamp": entry.timestamp,
            "level": entry.level.name,
            "message": entry.message,
            "source": entry.source,
            "line_number": entry.line_number,
            "thread_id": entry.thread_id
        }
        
        # Add optional fields if they exist
        if entry.context:
            entry_dict["context"] = entry.context
        if entry.variables:
            entry_dict["variables"] = entry.variables
        if entry.tags:
            entry_dict["tags"] = entry.tags
        if entry.exception:
            entry_dict["exception"] = {
                "type": type(entry.exception).__name__,
                "message": str(entry.exception)
            }
        
        # Convert to JSON string
        return json.dumps(entry_dict, default=str)


# Predefined formatter instances for convenience
simple_formatter = SimpleFormatter()
detailed_formatter = DetailedFormatter()
json_formatter = JSONFormatter()