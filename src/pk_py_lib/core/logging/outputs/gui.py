"""
GUI Log Output

Log output handler for displaying logs in a Qt GUI panel.
"""

from typing import Optional
from . import LogOutput
from ..logger import LogEntry


class GuiLogOutput(LogOutput):
    """
    Log output handler that sends log entries to a GUI panel.
    
    This output handler is designed to work with Qt-based GUI applications
    to display log messages in a dedicated log panel widget.
    """
    
    def __init__(self):
        """Initialize the GUI log output handler."""
        super().__init__()
        self.panel = None
    
    def register_panel(self, panel) -> None:
        """
        Register a GUI panel to receive log messages.
        
        Args:
            panel: GUI panel widget that has an add_log_entry method
        """
        self.panel = panel
    
    def write(self, entry: LogEntry) -> None:
        """
        Write a log entry to the GUI panel.
        
        Args:
            entry: LogEntry to display in the GUI
        """
        if self.panel is None:
            # Panel not registered, ignore log entries
            return
            
        try:
            # Send the log entry to the panel
            self.panel.add_log_entry(entry)
        except Exception as e:
            # Avoid infinite recursion if GUI logging fails
            print(f"Error writing to GUI log panel: {e}")
    
    def should_write(self, entry: LogEntry) -> bool:
        """
        Determine if this output should handle the given entry.
        
        Args:
            entry: LogEntry to evaluate
            
        Returns:
            True if the panel is registered and available, False otherwise
        """
        return self.panel is not None
    
    def close(self) -> None:
        """Close the output handler and clean up resources."""
        # Nothing to clean up for GUI output
        pass