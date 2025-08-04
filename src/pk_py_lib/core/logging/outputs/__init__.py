"""
Log Output Handlers

Different output destinations for log messages including console,
file, GUI, and future database support.
"""

# Export LogOutput base class from logger for convenient imports like:
# from src.pk_py_lib.core.logging.outputs import LogOutput
from ..logger import LogOutput

from .console import SimpleConsoleOutput, RichConsoleOutput
from .file import FileOutput
# GUI output is optional; imported where needed to avoid PySide dependency at import time.

__all__ = [
    "LogOutput",
    "SimpleConsoleOutput",
    "RichConsoleOutput",
    "FileOutput"
]