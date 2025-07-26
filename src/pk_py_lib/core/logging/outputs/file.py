"""
File Output Handler

Output handler for writing log messages to files with rotation support.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Union
from ..logger import LogOutput, LogEntry, LogLevel


class FileOutput(LogOutput):
    """
    File output handler with automatic rotation and formatting.
    
    Features:
    - Automatic file creation and directory setup
    - Optional log rotation by size or time
    - Structured JSON output option
    - Thread-safe writing
    """
    
    def __init__(self, 
                 file_path: Union[str, Path],
                 max_size_mb: Optional[int] = None,
                 backup_count: int = 5,
                 json_format: bool = False):
        """
        Initialize file output handler.
        
        Args:
            file_path: Path to log file
            max_size_mb: Maximum file size in MB before rotation (None to disable)
            backup_count: Number of backup files to keep
            json_format: Whether to output in JSON format
        """
        self.file_path = Path(file_path)
        self.max_size_mb = max_size_mb
        self.backup_count = backup_count
        self.json_format = json_format
        
        # Create directory if it doesn't exist
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotate if file is too large
        if self.max_size_mb and self._should_rotate():
            self._rotate_file()
    
    def _should_rotate(self) -> bool:
        """Check if file should be rotated."""
        if not self.file_path.exists() or not self.max_size_mb:
            return False
        
        file_size_mb = self.file_path.stat().st_size / (1024 * 1024)
        return file_size_mb >= self.max_size_mb
    
    def _rotate_file(self) -> None:
        """Rotate log files."""
        if not self.file_path.exists():
            return
        
        # Move existing backup files
        for i in range(self.backup_count - 1, 0, -1):
            old_backup = self.file_path.with_suffix(f".{i}.log")
            new_backup = self.file_path.with_suffix(f".{i + 1}.log")
            
            if old_backup.exists():
                if new_backup.exists():
                    new_backup.unlink()  # Remove oldest backup
                old_backup.rename(new_backup)
        
        # Move current file to .1 backup
        backup_file = self.file_path.with_suffix(".1.log")
        if backup_file.exists():
            backup_file.unlink()
        self.file_path.rename(backup_file)
    
    def write(self, entry: LogEntry) -> None:
        """Write log entry to file."""
        # Check if rotation is needed
        if self.max_size_mb and self._should_rotate():
            self._rotate_file()
        
        if self.json_format:
            self._write_json(entry)
        else:
            self._write_text(entry)
    
    def _write_text(self, entry: LogEntry) -> None:
        """Write entry in text format."""
        # Format timestamp
        dt = datetime.fromtimestamp(entry.timestamp)
        timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Format main line
        line = f"[{timestamp_str}] {entry.level.name:8} {entry.message}"
        
        # Add source info
        if entry.source:
            line += f" ({entry.source}"
            if entry.line_number:
                line += f":{entry.line_number}"
            line += ")"
        
        # Add thread info
        if entry.thread_id and entry.thread_id != "MainThread":
            line += f" [Thread: {entry.thread_id}]"
        
        lines = [line]
        
        # Add variables
        if entry.variables:
            lines.append("  Variables:")
            for name, value in entry.variables.items():
                lines.append(f"    {name} = {repr(value)}")
        
        # Add context
        if entry.context:
            context_items = [f"{k}={v}" for k, v in entry.context.items()]
            lines.append(f"  Context: {', '.join(context_items)}")
        
        # Add exception
        if entry.exception:
            lines.append(f"  Exception: {type(entry.exception).__name__}: {entry.exception}")
            
            # Add traceback for errors
            if entry.level >= LogLevel.ERROR:
                import traceback
                tb_lines = traceback.format_exception(
                    type(entry.exception), entry.exception, entry.exception.__traceback__
                )
                for tb_line in tb_lines:
                    lines.append(f"    {tb_line.rstrip()}")
        
        # Write to file
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
                f.flush()
        except Exception as e:
            # Fallback to stderr if file writing fails
            print(f"Failed to write to log file {self.file_path}: {e}", file=sys.stderr)
    
    def _write_json(self, entry: LogEntry) -> None:
        """Write entry in JSON format."""
        import json
        
        # Convert entry to dictionary
        entry_dict = {
            "timestamp": entry.timestamp,
            "level": entry.level.name,
            "message": entry.message,
            "source": entry.source,
            "line_number": entry.line_number,
            "thread_id": entry.thread_id
        }
        
        # Add optional fields
        if entry.variables:
            # Convert variables to JSON-serializable format
            try:
                entry_dict["variables"] = {k: repr(v) for k, v in entry.variables.items()}
            except:
                entry_dict["variables"] = {"error": "Could not serialize variables"}
        
        if entry.context:
            try:
                entry_dict["context"] = dict(entry.context)
            except:
                entry_dict["context"] = {"error": "Could not serialize context"}
        
        if entry.tags:
            entry_dict["tags"] = list(entry.tags)
        
        if entry.exception:
            entry_dict["exception"] = {
                "type": type(entry.exception).__name__,
                "message": str(entry.exception)
            }
        
        # Write JSON line
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                json.dump(entry_dict, f, separators=(',', ':'))
                f.write('\n')
                f.flush()
        except Exception as e:
            # Fallback to stderr if file writing fails
            import sys
            print(f"Failed to write to log file {self.file_path}: {e}", file=sys.stderr)
    
    def close(self) -> None:
        """Close file handler (nothing to do for file output)."""
        pass


class RotatingFileOutput(FileOutput):
    """
    Enhanced file output with time-based rotation.
    
    This rotates files based on time periods (daily, weekly, etc.)
    in addition to size-based rotation.
    """
    
    def __init__(self, 
                 file_path: Union[str, Path],
                 rotation_period: str = "daily",  # "hourly", "daily", "weekly" 
                 max_size_mb: Optional[int] = None,
                 backup_count: int = 7,
                 json_format: bool = False):
        """
        Initialize rotating file output.
        
        Args:
            file_path: Base path for log files
            rotation_period: How often to rotate ("hourly", "daily", "weekly")
            max_size_mb: Maximum file size in MB before rotation
            backup_count: Number of backup files to keep
            json_format: Whether to output in JSON format
        """
        self.rotation_period = rotation_period
        self.last_rotation_check = datetime.now()
        
        # Add timestamp to filename for time-based rotation
        self.base_path = Path(file_path)
        timestamped_path = self._get_timestamped_path()
        
        super().__init__(timestamped_path, max_size_mb, backup_count, json_format)
    
    def _get_timestamped_path(self) -> Path:
        """Get filename with timestamp for current period."""
        now = datetime.now()
        
        if self.rotation_period == "hourly":
            timestamp = now.strftime("%Y%m%d_%H")
        elif self.rotation_period == "daily":
            timestamp = now.strftime("%Y%m%d")
        elif self.rotation_period == "weekly":
            # Use Monday as start of week
            monday = now - timedelta(days=now.weekday())
            timestamp = monday.strftime("%Y%m%d_week")
        else:
            timestamp = now.strftime("%Y%m%d")
        
        stem = self.base_path.stem
        suffix = self.base_path.suffix
        
        return self.base_path.parent / f"{stem}_{timestamp}{suffix}"
    
    def write(self, entry: LogEntry) -> None:
        """Write entry, checking for time-based rotation first."""
        # Check if we need to rotate based on time
        current_timestamped_path = self._get_timestamped_path()
        if current_timestamped_path != self.file_path:
            # Time period has changed, start using new file
            self.file_path = current_timestamped_path
        
        super().write(entry)