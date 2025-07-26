"""
Log Output Handlers

Different output destinations for log messages including console,
file, GUI, and future database support.
"""

from .console import SimpleConsoleOutput, RichConsoleOutput
from .file import FileOutput
# GUI output will be imported conditionally when needed
# from .gui import GuiLogOutput

__all__ = [
    "SimpleConsoleOutput",
    "RichConsoleOutput", 
    "FileOutput"
]