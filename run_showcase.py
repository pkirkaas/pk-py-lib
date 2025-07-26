#!/usr/bin/env python3
"""
Direct launcher for the pk-py-lib component showcase.

Run this script from the project root to launch the GUI test framework
without needing to install the package first.

Usage:
    python run_showcase.py
"""

import sys
from pathlib import Path

# Add the project root to Python path so we can import our modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """Launch the component showcase."""
    try:
        from showcase.app import run_showcase
        print("🚀 Launching PK-Py-Lib Component Showcase...")
        return run_showcase()
        
    except ImportError as e:
        print(f"❌ Failed to import showcase: {e}")
        print("\nMake sure you have the required dependencies installed:")
        print("  pip install PySide6 rich")
        return 1
        
    except Exception as e:
        print(f"❌ Failed to launch showcase: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())