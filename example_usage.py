#!/usr/bin/env python3
"""
Example usage of pk-py-lib core functionality.

This script demonstrates the key features implemented:
- Path operations with remove_contained_paths()
- Flexible logging system
- File system operations
- File monitoring capabilities
"""

from pathlib import Path
from src.pk_py_lib import get_logger, configure_logging
from src.pk_py_lib.core.filesystem import (
    PathOperations, FileOperations, DirectoryTraversal, 
    FileOrganizer, monitoring
)
from src.pk_py_lib.core.logging import LogLevel

# Configure logging with rich output
configure_logging(
    console=True,
    level=LogLevel.INFO,
    rich_console=True
)

log = get_logger(__name__)


def demo_path_operations():
    """Demonstrate path operations including remove_contained_paths."""
    log.info("=== Path Operations Demo ===")
    
    # Example paths with nested relationships
    test_paths = [
        Path("/photos"),
        Path("/photos/vacation"),
        Path("/photos/vacation/beach.jpg"),
        Path("/photos/work/project.jpg"),
        Path("/documents"),
        Path("/documents/reports/annual.pdf"),
        Path("/music")
    ]
    
    log.info("Original paths:")
    for path in test_paths:
        log.info(f"  {path}")
    
    # Remove contained paths - this is the key function you requested!
    minimal_paths = PathOperations.remove_contained_paths(test_paths)
    
    log.success("After removing contained paths:")
    for path in minimal_paths:
        log.info(f"  {path}")
    
    # Demonstrate other path operations
    common_ancestor = PathOperations.find_common_ancestor(test_paths)
    log.info(f"Common ancestor: {common_ancestor}")


def demo_logging_features():
    """Demonstrate advanced logging features."""
    log.info("=== Logging Features Demo ===")
    
    # Variable watching
    image_count = 150
    processing_time = 2.5
    threshold = 0.95
    
    log.watch(
        image_count=image_count,
        processing_time=processing_time,
        similarity_threshold=threshold
    )
    
    # Context logging
    with log.context(operation="duplicate_detection", user_id=123):
        log.info("Starting duplicate detection")
        log.debug("Analyzing image similarity")
        log.watch(threshold=threshold)
    
    # Performance timing
    with log.timer("example_operation"):
        import time
        time.sleep(0.1)  # Simulate work
    
    # Different log levels
    log.trace("Trace message")
    log.debug("Debug information")
    log.info("General information")
    log.success("Operation completed successfully")
    log.warning("This is a warning")


def demo_file_operations():
    """Demonstrate safe file operations."""
    log.info("=== File Operations Demo ===")
    
    # Example of safe file operations (dry run)
    try:
        # This would normally move files, but we're just demonstrating the API
        log.info("Safe file operations API available")
        log.info("- safe_move() with conflict resolution")
        log.info("- safe_copy() with metadata preservation")
        log.info("- Transaction support with rollback")
        log.info("- Batch organization capabilities")
        
    except Exception as e:
        log.error("File operations demo failed", exception=e)


def demo_directory_analysis():
    """Demonstrate directory analysis capabilities."""
    log.info("=== Directory Analysis Demo ===")
    
    # Analyze current directory
    current_dir = Path(".")
    
    try:
        # Get directory statistics
        stats = DirectoryTraversal.calculate_directory_stats(current_dir, include_subdirs=False)
        
        log.info(f"Directory: {stats['directory']}")
        log.info(f"Total files: {stats['file_count']}")
        log.info(f"Total size: {stats['total_size_mb']:.2f} MB")
        
        # Show file type distribution
        if stats['file_types']:
            log.info("File types found:")
            for ext, count in stats['file_types'].most_common(5):
                log.info(f"  {ext or 'no extension'}: {count} files")
                
    except Exception as e:
        log.error("Directory analysis failed", exception=e)


def demo_file_monitoring():
    """Demonstrate file monitoring capabilities."""
    log.info("=== File Monitoring Demo ===")
    
    try:
        # Check if monitoring is available
        from src.pk_py_lib.core.filesystem.monitoring import FileWatcher
        
        log.info("File monitoring capabilities:")
        log.info("- Real-time file watching with watchdog")
        log.info("- Pattern-based filtering")
        log.info("- Event debouncing and aggregation")
        log.info("- Batch operation detection")
        log.info("- Cross-platform support")
        
        # Note: We don't actually start watching to avoid hanging the demo
        
    except ImportError:
        log.warning("File monitoring requires 'watchdog' package")
    except Exception as e:
        log.error("File monitoring demo failed", exception=e)


def demo_showcase():
    """Demonstrate component showcase."""
    log.info("=== Component Showcase Demo ===")
    
    try:
        from showcase import run_showcase
        log.info("Component showcase available!")
        log.info("Run with: python -m showcase.app")
        log.info("Or use the console command: pk-showcase")
        
    except ImportError as e:
        log.warning(f"Showcase requires PySide6: {e}")
    except Exception as e:
        log.error("Showcase demo failed", exception=e)


def main():
    """Run all demonstrations."""
    log.info("🚀 Starting pk-py-lib demonstration")
    
    try:
        demo_path_operations()
        demo_logging_features()
        demo_file_operations()
        demo_directory_analysis()
        demo_file_monitoring()
        demo_showcase()
        
        log.success("✅ All demonstrations completed successfully!")
        
    except Exception as e:
        log.critical("Demo failed", exception=e)
        raise


if __name__ == "__main__":
    main()