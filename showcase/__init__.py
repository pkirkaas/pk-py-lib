"""
PK-Py-Lib Component Showcase

Interactive showcase application for testing and demonstrating
all pk_py_lib GUI components with live preview and property inspection.
"""

from .app import ComponentShowcase, run_showcase
from .gallery.registry import ComponentRegistry, showcase_component

__all__ = [
    "ComponentShowcase",
    "run_showcase", 
    "ComponentRegistry",
    "showcase_component"
]

__version__ = "0.1.0"