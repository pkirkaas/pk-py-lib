"""
File Output Handler

Output handler for writing log messages to files with rotation support.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Union
from ..logger import LogOutput, LogEntry, LogLevel
from pk_py_lib.core.utils import get_data_dir # Import unified data directory function
import sys # For invocation command

# Imports for development mode line ending configuration
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.configuration import ConfigurationManager


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
                 json_format: bool = False,
                 rotate_existing: bool = True):
        """
        Initialize file output handler.
        
        Args:
            file_path: Path to log file
            max_size_mb: Maximum file size in MB before rotation (None to disable)
            backup_count: Number of backup files to keep
            json_format: Whether to output in JSON format
            rotate_existing: Whether to rotate (rename) existing log file on init (default: True)
        
        Example:
            >>> # Standard usage with rotation
            >>> output = FileOutput("app.log")
            
            >>> # Skip rotation (e.g., for pre-rotated files like cache logs)
            >>> output = FileOutput("cache_process.log", rotate_existing=False)
        """
        self.file_path = Path(file_path)
        self.max_size_mb = max_size_mb
        self.backup_count = backup_count
        self.json_format = json_format
        self.rotate_existing = rotate_existing
        
        # Development mode check: Use Unix line endings (\n) for logs when development flag is True
        # This ensures consistent line endings for cross-platform analysis (git diffs, Linux tools)
        # even on Windows, without affecting other modes or platforms unnecessarily.
        # On non-Windows platforms, open() defaults to \n, so this primarily impacts Windows.
        db_mgr = DatabaseManager()
        config = ConfigurationManager(db_mgr)
        self.is_dev_mode = config.get_app_setting("development") or False
        
        # Create directory if it doesn't exist
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotate if file is too large
        if self.max_size_mb and self._should_rotate():
            self._rotate_file()
        
        # Apply project logging rules: rename existing log and write header
        self._prepare_log_file()
    
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
    
    def _prepare_log_file(self) -> None:
        """
        Implements project logging rules:
        1. Renames existing log file by adding a timestamp to the basename (if rotate_existing=True).
        2. Creates a new log file.
        3. Writes the full terminal invocation command as the first line.
        4. Writes a formatted date & time stamp as the second line, followed by a blank newline.
        
        For cache logs or pre-rotated files, set rotate_existing=False to skip renaming
        and only write the header to an existing empty file.
        """
        if self.rotate_existing and self.file_path.exists():
            # 1. Rename existing log file
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = self.file_path.stem
            suffix = self.file_path.suffix
            
            new_name = self.file_path.parent / f"{base_name}.{ts}{suffix}"
            
            try:
                self.file_path.rename(new_name)
                # Log this action to stderr/stdout since the file is being renamed
                print(f"Renamed existing log file to {new_name}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Could not rename existing log file {self.file_path}: {e}", file=sys.stderr)
                # If rename fails, we proceed to overwrite the existing file content below.
        
        # 2. A new logfile is implicitly created when we open in 'a' mode below,
        # but we ensure it's fresh by writing the header.
        
        # 3. Get full terminal invocation command
        invocation_command = " ".join(sys.argv)
        
        # 4. Get formatted date & time stamp
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        
        header = [
            f"Invocation Command: {invocation_command}",
            f"Start Time: {current_time_str}",
            "", # Blank newline after timestamp
            "--- Log Start ---"
        ]
        
        try:
            # Write header to the new file, overwriting if rename failed or file was missing
            # For non-rotated empty files (e.g., cache logs), this appends the header safely
            mode = 'w' if not self.file_path.exists() else 'a'
            newline_param = '\n' if self.is_dev_mode else None
            with open(self.file_path, mode, encoding='utf-8', newline=newline_param) as f:
                if mode == 'a' and f.tell() > 0:
                    f.write('\n')  # Ensure newline before header if file not empty
                f.write('\n'.join(header) + '\n')
                f.flush()
        except Exception as e:
            print(f"Critical: Failed to write log file header to {self.file_path}: {e}", file=sys.stderr)
            # If header write fails, subsequent writes will likely fail too, but we continue.

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
            newline_param = '\n' if self.is_dev_mode else None
            with open(self.file_path, 'a', encoding='utf-8', newline=newline_param) as f:
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
            newline_param = '\n' if self.is_dev_mode else None
            with open(self.file_path, 'a', encoding='utf-8', newline=newline_param) as f:
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