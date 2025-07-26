"""
Console Output Handlers

Output handlers for writing log messages to the console/terminal
with optional rich formatting support.
"""

import sys
from datetime import datetime
from typing import Optional
from ..logger import LogOutput, LogEntry, LogLevel


class SimpleConsoleOutput(LogOutput):
    """
    Simple console output handler without rich formatting.
    
    This handler provides basic colored output that works in any terminal
    without additional dependencies.
    """
    
    # ANSI color codes
    COLORS = {
        LogLevel.TRACE: '\033[90m',     # Dark gray
        LogLevel.DEBUG: '\033[36m',     # Cyan
        LogLevel.INFO: '\033[37m',      # White
        LogLevel.WATCH: '\033[35m',     # Magenta
        LogLevel.SUCCESS: '\033[32m',   # Green
        LogLevel.WARNING: '\033[33m',   # Yellow
        LogLevel.ERROR: '\033[31m',     # Red
        LogLevel.CRITICAL: '\033[91m',  # Bright red
    }
    
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    def __init__(self, use_colors: bool = True, show_timestamps: bool = True):
        """
        Initialize console output.
        
        Args:
            use_colors: Whether to use ANSI color codes
            show_timestamps: Whether to show timestamps
        """
        self.use_colors = use_colors
        self.show_timestamps = show_timestamps
    
    def write(self, entry: LogEntry) -> None:
        """Write log entry to console."""
        # Format timestamp
        timestamp_str = ""
        if self.show_timestamps:
            dt = datetime.fromtimestamp(entry.timestamp)
            timestamp_str = f"[{dt.strftime('%H:%M:%S')}] "
        
        # Format level
        level_str = entry.level.name.ljust(8)
        if self.use_colors and entry.level in self.COLORS:
            level_str = f"{self.COLORS[entry.level]}{level_str}{self.RESET}"
        
        # Format source
        source_str = ""
        if entry.source:
            source_str = f" ({entry.source}:{entry.line_number})" if entry.line_number else f" ({entry.source})"
        
        # Main message
        message = f"{timestamp_str}{level_str} {entry.message}{source_str}"
        
        # Add variables if present
        if entry.variables:
            var_lines = []
            for name, value in entry.variables.items():
                var_lines.append(f"  {name} = {repr(value)}")
            if var_lines:
                message += "\n" + "\n".join(var_lines)
        
        # Add context if present
        if entry.context:
            context_items = [f"{k}={v}" for k, v in entry.context.items()]
            message += f" [Context: {', '.join(context_items)}]"
        
        # Add exception if present
        if entry.exception:
            message += f"\n  Exception: {type(entry.exception).__name__}: {entry.exception}"
        
        # Write to appropriate stream
        stream = sys.stderr if entry.level >= LogLevel.ERROR else sys.stdout
        print(message, file=stream)
        stream.flush()


class RichConsoleOutput(LogOutput):
    """
    Rich console output handler with advanced formatting.
    
    This handler uses the rich library for beautiful console output
    with syntax highlighting, tables, and more.
    """
    
    def __init__(self, width: Optional[int] = None):
        """
        Initialize rich console output.
        
        Args:
            width: Console width (None for auto-detect)
        """
        try:
            from rich.console import Console
            from rich.text import Text
            from rich.table import Table
            from rich import box
            
            self.rich_available = True
            self.console = Console(width=width, stderr=True)
            self.Text = Text
            self.Table = Table
            self.box = box
            
        except ImportError:
            # Fall back to simple output if rich is not available
            self.rich_available = False
            self.fallback = SimpleConsoleOutput()
    
    def write(self, entry: LogEntry) -> None:
        """Write log entry to console using rich formatting."""
        if not self.rich_available:
            return self.fallback.write(entry)
        
        # Color mapping for rich
        level_colors = {
            LogLevel.TRACE: "dim white",
            LogLevel.DEBUG: "cyan",
            LogLevel.INFO: "white", 
            LogLevel.WATCH: "magenta",
            LogLevel.SUCCESS: "green",
            LogLevel.WARNING: "yellow",
            LogLevel.ERROR: "red",
            LogLevel.CRITICAL: "bold red"
        }
        
        # Create timestamp
        dt = datetime.fromtimestamp(entry.timestamp)
        timestamp = dt.strftime('%H:%M:%S.%f')[:-3]  # Include milliseconds
        
        # Create main text
        color = level_colors.get(entry.level, "white")
        
        # Format the main message
        text = self.Text()
        text.append(f"[{timestamp}] ", style="dim")
        text.append(f"{entry.level.name:8} ", style=f"bold {color}")
        text.append(entry.message, style=color)
        
        # Add source info
        if entry.source:
            source_text = f" ({entry.source}"
            if entry.line_number:
                source_text += f":{entry.line_number}"
            source_text += ")"
            text.append(source_text, style="dim")
        
        # Print main message
        self.console.print(text)
        
        # Print variables in a table if present
        if entry.variables:
            table = self.Table(
                title="Variables",
                box=self.box.MINIMAL,
                show_header=True,
                header_style="bold blue"
            )
            table.add_column("Name", style="cyan")
            table.add_column("Value", style="white")
            table.add_column("Type", style="dim")
            
            for name, value in entry.variables.items():
                value_str = repr(value)
                if len(value_str) > 100:
                    value_str = value_str[:97] + "..."
                    
                table.add_row(
                    name,
                    value_str,
                    type(value).__name__
                )
            
            self.console.print(table)
        
        # Print context if present
        if entry.context:
            context_text = self.Text("Context: ", style="dim")
            context_items = []
            for k, v in entry.context.items():
                context_items.append(f"{k}={v}")
            context_text.append(", ".join(context_items), style="blue")
            self.console.print(context_text)
        
        # Print exception if present
        if entry.exception:
            self.console.print(f"[bold red]Exception:[/bold red] {type(entry.exception).__name__}: {entry.exception}")
            
            # If it's a critical error, show more details
            if entry.level == LogLevel.CRITICAL:
                import traceback
                self.console.print("[dim]" + "".join(traceback.format_exception(
                    type(entry.exception), entry.exception, entry.exception.__traceback__
                )) + "[/dim]")


def get_best_console_output(prefer_rich: bool = True) -> LogOutput:
    """
    Get the best available console output handler.
    
    Args:
        prefer_rich: Whether to prefer rich output if available
        
    Returns:
        Best available console output handler
    """
    if prefer_rich:
        try:
            return RichConsoleOutput()
        except ImportError:
            pass
    
    return SimpleConsoleOutput()