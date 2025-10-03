"""
Test script for verifying Unix line endings (LF) in log files under development mode.
"""

import sys
from datetime import datetime
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.configuration import ConfigurationManager
from src.pk_py_lib.core.logging.outputs.file import FileOutput
from src.pk_py_lib.core.logging.logger import LogEntry, LogLevel

# Initialize components
db_mgr = DatabaseManager()
config = ConfigurationManager(db_mgr)

# Set development mode to True
config.set_app_setting("development", True)
print("Development mode set to True")

# Create a simple log entry
timestamp = datetime.now().timestamp()
entry1 = LogEntry(
    timestamp=timestamp,
    level=LogLevel.INFO,
    message="This is the first test log line.",
    source="test_script.py",
    line_number=42,
    thread_id="MainThread"
)

entry2 = LogEntry(
    timestamp=timestamp + 1,
    level=LogLevel.INFO,
    message="This is the second test log line.",
    source="test_script.py",
    line_number=43,
    thread_id="MainThread"
)

# Create FileOutput with no rotation for simplicity
log_file = "test_log_dev.txt"
output = FileOutput(log_file, rotate_existing=False, json_format=False)

# Write entries
output.write(entry1)
output.write(entry2)

print(f"Log entries written to {log_file}")
print("To verify line endings, run: hexdump -C test_log_dev.txt")