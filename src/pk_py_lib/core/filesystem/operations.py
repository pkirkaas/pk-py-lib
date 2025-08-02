"""
File Operations Module

Safe file and directory operations with conflict resolution,
batch processing, and transaction support with rollback capabilities.
"""

import shutil
import os
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple, Union
from datetime import datetime
from enum import Enum
import hashlib
import tempfile

from ..logging import get_logger

log = get_logger(__name__)


class ConflictStrategy(Enum):
    """Strategies for handling file conflicts."""
    RENAME = "rename"      # Auto-rename conflicting files
    SKIP = "skip"          # Skip conflicting files
    OVERWRITE = "overwrite"  # Overwrite existing files
    ERROR = "error"        # Raise error on conflict
    ASK = "ask"           # Ask user (for interactive use)


class FileOperations:
    """
    Safe file and directory operations with validation and conflict resolution.
    
    This class provides robust file operations that handle edge cases,
    provide detailed logging, and offer flexible conflict resolution.
    """
    
    @staticmethod
    def safe_move(
        source: Path, 
        destination: Path,
        on_conflict: Union[ConflictStrategy, str] = ConflictStrategy.RENAME,
        create_dirs: bool = True,
        verify_move: bool = True
    ) -> Path:
        """
        Safely move a file or directory with conflict resolution.
        
        Args:
            source: Source path to move
            destination: Destination path
            on_conflict: Strategy for handling conflicts
            create_dirs: Whether to create destination directories
            verify_move: Whether to verify the move succeeded
            
        Returns:
            Final destination path (may be renamed if conflict occurred)
            
        Raises:
            FileNotFoundError: If source doesn't exist
            PermissionError: If insufficient permissions
            ValueError: If invalid conflict strategy
            
        Example:
            >>> result = FileOperations.safe_move(
            ...     Path("/source/file.jpg"),
            ...     Path("/dest/file.jpg"),
            ...     on_conflict=ConflictStrategy.RENAME
            ... )
            >>> # If conflict, might return Path("/dest/file_1.jpg")
        """
        # Convert string strategy to enum
        if isinstance(on_conflict, str):
            try:
                on_conflict = ConflictStrategy(on_conflict)
            except ValueError:
                raise ValueError(f"Invalid conflict strategy: {on_conflict}")
        
        # Validate source
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        
        # Create destination directory if needed
        if create_dirs:
            destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle conflicts
        final_destination = destination
        if destination.exists():
            final_destination = FileOperations._handle_conflict(
                source, destination, on_conflict
            )
            
            # If conflict strategy returned None, skip the operation
            if final_destination is None:
                log.info(f"Skipped moving {source} due to conflict")
                return destination
        
        # Perform the move
        try:
            log.debug(f"Moving {source} -> {final_destination}")
            
            # Use shutil.move for cross-platform compatibility
            shutil.move(str(source), str(final_destination))
            
            # Verify the move if requested
            if verify_move and not final_destination.exists():
                raise RuntimeError(f"Move verification failed: {final_destination} does not exist")
            
            log.success(f"Successfully moved {source} -> {final_destination}")
            return final_destination
            
        except Exception as e:
            log.error(f"Failed to move {source} -> {final_destination}", exception=e)
            raise
    
    @staticmethod
    def safe_copy(
        source: Path,
        destination: Path,
        on_conflict: Union[ConflictStrategy, str] = ConflictStrategy.RENAME,
        create_dirs: bool = True,
        preserve_metadata: bool = True
    ) -> Path:
        """
        Safely copy a file or directory with conflict resolution.
        
        Args:
            source: Source path to copy
            destination: Destination path
            on_conflict: Strategy for handling conflicts
            create_dirs: Whether to create destination directories
            preserve_metadata: Whether to preserve file metadata
            
        Returns:
            Final destination path (may be renamed if conflict occurred)
        """
        # Convert string strategy to enum
        if isinstance(on_conflict, str):
            on_conflict = ConflictStrategy(on_conflict)
        
        # Validate source
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        
        # Create destination directory if needed
        if create_dirs:
            destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle conflicts
        final_destination = destination
        if destination.exists():
            final_destination = FileOperations._handle_conflict(
                source, destination, on_conflict
            )
            
            if final_destination is None:
                log.info(f"Skipped copying {source} due to conflict")
                return destination
        
        # Perform the copy
        try:
            log.debug(f"Copying {source} -> {final_destination}")
            
            if source.is_dir():
                shutil.copytree(str(source), str(final_destination))
            else:
                if preserve_metadata:
                    shutil.copy2(str(source), str(final_destination))
                else:
                    shutil.copy(str(source), str(final_destination))
            
            log.success(f"Successfully copied {source} -> {final_destination}")
            return final_destination
            
        except Exception as e:
            log.error(f"Failed to copy {source} -> {final_destination}", exception=e)
            raise
    
    @staticmethod
    def safe_delete(
        path: Path,
        to_trash: bool = False,
        confirm_large: bool = True,
        large_threshold_mb: int = 100
    ) -> bool:
        """
        Safely delete a file or directory with optional trash support.
        
        Args:
            path: Path to delete
            to_trash: Move to trash instead of permanent deletion
            confirm_large: Whether to require confirmation for large files
            large_threshold_mb: Size threshold for large file confirmation
            
        Returns:
            True if deletion succeeded, False if skipped
        """
        if not path.exists():
            log.warning(f"Cannot delete non-existent path: {path}")
            return False
        
        # Check size for large file confirmation
        if confirm_large and path.is_file():
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > large_threshold_mb:
                log.warning(f"Large file deletion requested: {path} ({size_mb:.1f} MB)")
                # In a real implementation, you might want to prompt the user
                # For now, we'll just log and continue
        
        try:
            if to_trash:
                # Try to use system trash if available
                try:
                    from send2trash import send2trash
                    send2trash(str(path))
                    log.info(f"Moved to trash: {path}")
                except ImportError:
                    log.warning("send2trash not available, using permanent deletion")
                    FileOperations._permanent_delete(path)
            else:
                FileOperations._permanent_delete(path)
            
            return True
            
        except Exception as e:
            log.error(f"Failed to delete {path}", exception=e)
            raise
    
    @staticmethod
    def _permanent_delete(path: Path) -> None:
        """Permanently delete a path."""
        if path.is_dir():
            shutil.rmtree(str(path))
            log.info(f"Permanently deleted directory: {path}")
        else:
            path.unlink()
            log.info(f"Permanently deleted file: {path}")
    
    @staticmethod
    def _handle_conflict(
        source: Path,
        destination: Path, 
        strategy: ConflictStrategy
    ) -> Optional[Path]:
        """
        Handle file conflicts based on strategy.
        
        Returns:
            Path to use for destination, or None to skip operation
        """
        if strategy == ConflictStrategy.SKIP:
            return None
        
        elif strategy == ConflictStrategy.OVERWRITE:
            return destination
        
        elif strategy == ConflictStrategy.ERROR:
            raise FileExistsError(f"Destination already exists: {destination}")
        
        elif strategy == ConflictStrategy.RENAME:
            return FileOperations._generate_unique_name(destination)
        
        elif strategy == ConflictStrategy.ASK:
            # In a real implementation, this would prompt the user
            # For now, default to rename
            log.info(f"Conflict detected, auto-renaming: {destination}")
            return FileOperations._generate_unique_name(destination)
        
        else:
            raise ValueError(f"Unknown conflict strategy: {strategy}")
    
    @staticmethod
    def _generate_unique_name(path: Path) -> Path:
        """Generate a unique filename by adding a number suffix."""
        if not path.exists():
            return path
        
        counter = 1
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1
            
            # Prevent infinite loops
            if counter > 9999:
                raise RuntimeError(f"Could not generate unique name for {path}")
    
    @staticmethod
    def batch_organize(
        files: List[Path],
        destination: Path,
        organize_by: str = "date",  # "date", "type", "size", "custom"
        custom_organizer: Optional[Callable[[Path], Path]] = None,
        dry_run: bool = False
    ) -> Dict[Path, Path]:
        """
        Organize files into subdirectories based on criteria.
        
        Args:
            files: List of files to organize
            organize_by: Organization strategy
            destination: Base destination directory
            custom_organizer: Custom function to determine subdirectory
            dry_run: If True, only return what would be done
            
        Returns:
            Dictionary mapping source paths to destination paths
            
        Example:
            >>> # Organize photos by year/month
            >>> result = FileOperations.batch_organize(
            ...     photo_files,
            ...     organize_by="date",
            ...     destination=Path("/organized_photos")
            ... )
        """
        operations = {}
        
        for file_path in files:
            if not file_path.exists() or not file_path.is_file():
                continue
            
            # Determine subdirectory
            if organize_by == "date":
                subdir = FileOperations._get_date_subdir(file_path)
            elif organize_by == "type":
                subdir = FileOperations._get_type_subdir(file_path)
            elif organize_by == "size":
                subdir = FileOperations._get_size_subdir(file_path)
            elif organize_by == "custom" and custom_organizer:
                subdir = custom_organizer(file_path)
            else:
                raise ValueError(f"Invalid organize_by: {organize_by}")
            
            # Calculate final destination
            final_dest = destination / subdir / file_path.name
            operations[file_path] = final_dest
            
            # Perform move if not dry run
            if not dry_run:
                try:
                    FileOperations.safe_move(
                        file_path, 
                        final_dest,
                        create_dirs=True
                    )
                except Exception as e:
                    log.error(f"Failed to organize {file_path}", exception=e)
        
        return operations
    
    @staticmethod
    def _get_date_subdir(file_path: Path) -> Path:
        """Get date-based subdirectory for file."""
        try:
            # Try to get creation time, fall back to modification time
            stat = file_path.stat()
            timestamp = getattr(stat, 'st_birthtime', stat.st_mtime)
            dt = datetime.fromtimestamp(timestamp)
            return Path(f"{dt.year:04d}/{dt.month:02d}")
        except:
            return Path("unknown_date")
    
    @staticmethod
    def _get_type_subdir(file_path: Path) -> Path:
        """Get file type-based subdirectory."""
        suffix = file_path.suffix.lower()
        
        # Define type mappings
        type_map = {
            '.jpg': 'images', '.jpeg': 'images', '.png': 'images', '.gif': 'images',
            '.bmp': 'images', '.tiff': 'images', '.webp': 'images',
            '.mp4': 'videos', '.avi': 'videos', '.mkv': 'videos', '.mov': 'videos',
            '.wmv': 'videos', '.flv': 'videos', '.webm': 'videos',
            '.mp3': 'audio', '.wav': 'audio', '.flac': 'audio', '.ogg': 'audio',
            '.txt': 'documents', '.doc': 'documents', '.docx': 'documents',
            '.pdf': 'documents', '.rtf': 'documents',
            '.zip': 'archives', '.rar': 'archives', '.7z': 'archives',
            '.tar': 'archives', '.gz': 'archives'
        }
        
        return Path(type_map.get(suffix, 'other'))
    
    @staticmethod
    def _get_size_subdir(file_path: Path) -> Path:
        """Get size-based subdirectory."""
        try:
            size_bytes = file_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            
            if size_mb < 1:
                return Path("small")
            elif size_mb < 10:
                return Path("medium")
            elif size_mb < 100:
                return Path("large")
            else:
                return Path("very_large")
        except:
            return Path("unknown_size")
    
    @staticmethod
    def safe_delete_empty_dirs(root: Path, protect_root: bool = True) -> List[Path]:
        """
        Recursively delete empty directories.
        
        Args:
            root: Root directory to start from
            protect_root: Whether to protect the root directory from deletion
            
        Returns:
            List of deleted directory paths
        """
        deleted = []
        
        if not root.exists() or not root.is_dir():
            return deleted
        
        try:
            # Walk bottom-up to ensure we check child directories first
            for current_dir in reversed(list(root.rglob('*'))):
                if current_dir.is_dir():
                    try:
                        # Check if directory is empty
                        if not any(current_dir.iterdir()):
                            # Don't delete the root directory if protected
                            if protect_root and current_dir == root:
                                continue
                            
                            current_dir.rmdir()
                            deleted.append(current_dir)
                            log.debug(f"Deleted empty directory: {current_dir}")
                    except OSError:
                        # Directory not empty or permission denied
                        continue
            
            return deleted
            
        except Exception as e:
            log.error(f"Error cleaning empty directories in {root}", exception=e)
            return deleted


class SafeFileOperations:
    """
    File operations with transaction support and rollback capability.
    
    This class allows you to perform multiple file operations as a transaction
    that can be rolled back if something goes wrong.
    """
    
    def __init__(self):
        """Initialize safe file operations with empty transaction log."""
        self.operations_log: List[Dict[str, Any]] = []
        self.in_transaction = False
        self.backup_dir: Optional[Path] = None
        
    def begin_transaction(self, backup_dir: Optional[Path] = None) -> None:
        """
        Start a new transaction for batch operations.
        
        Args:
            backup_dir: Directory to store backups (temp dir if None)
        """
        if self.in_transaction:
            raise RuntimeError("Transaction already in progress")
        
        self.in_transaction = True
        self.operations_log.clear()
        
        if backup_dir:
            self.backup_dir = backup_dir
            backup_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.backup_dir = Path(tempfile.mkdtemp(prefix="pk_py_lib_backup_"))
        
        log.info(f"Started transaction with backup dir: {self.backup_dir}")
    
    def move(self, source: Path, destination: Path) -> Path:
        """Move with ability to rollback."""
        if not self.in_transaction:
            raise RuntimeError("No transaction in progress")
        
        # Create backup of destination if it exists
        backup_path = None
        if destination.exists():
            backup_path = self._create_backup(destination)
        
        # Perform the move
        result = FileOperations.safe_move(source, destination)
        
        # Log the operation
        self.operations_log.append({
            'operation': 'move',
            'source': source,
            'destination': result,
            'backup_path': backup_path,
            'timestamp': datetime.now()
        })
        
        return result
    
    def copy(self, source: Path, destination: Path) -> Path:
        """Copy with ability to rollback."""
        if not self.in_transaction:
            raise RuntimeError("No transaction in progress")
        
        # Create backup of destination if it exists
        backup_path = None
        if destination.exists():
            backup_path = self._create_backup(destination)
        
        # Perform the copy
        result = FileOperations.safe_copy(source, destination)
        
        # Log the operation
        self.operations_log.append({
            'operation': 'copy',
            'source': source,
            'destination': result,
            'backup_path': backup_path,
            'timestamp': datetime.now()
        })
        
        return result
    
    def delete(self, path: Path) -> None:
        """Delete with ability to restore."""
        if not self.in_transaction:
            raise RuntimeError("No transaction in progress")
        
        if not path.exists():
            return
        
        # Create backup before deletion
        backup_path = self._create_backup(path)
        
        # Perform deletion
        FileOperations.safe_delete(path)
        
        # Log the operation
        self.operations_log.append({
            'operation': 'delete',
            'source': path,
            'backup_path': backup_path,
            'timestamp': datetime.now()
        })
    
    def _create_backup(self, path: Path) -> Path:
        """Create backup of a file or directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.name}_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        if path.is_dir():
            shutil.copytree(str(path), str(backup_path))
        else:
            shutil.copy2(str(path), str(backup_path))
        
        return backup_path
    
    def commit(self) -> None:
        """Commit all operations in transaction."""
        if not self.in_transaction:
            raise RuntimeError("No transaction in progress")
        
        log.info(f"Committed transaction with {len(self.operations_log)} operations")
        
        # Clean up backup directory
        if self.backup_dir and self.backup_dir.exists():
            shutil.rmtree(str(self.backup_dir))
        
        self._reset_transaction()
    
    def rollback(self) -> None:
        """Rollback all operations in current transaction."""
        if not self.in_transaction:
            raise RuntimeError("No transaction in progress")
        
        log.info(f"Rolling back transaction with {len(self.operations_log)} operations")
        
        # Process operations in reverse order
        for operation in reversed(self.operations_log):
            try:
                self._rollback_operation(operation)
            except Exception as e:
                log.error(f"Failed to rollback operation: {operation}", exception=e)
        
        self._reset_transaction()
    
    def _rollback_operation(self, operation: Dict[str, Any]) -> None:
        """Rollback a single operation."""
        op_type = operation['operation']
        
        if op_type == 'move':
            # Move the file back to original location
            if operation['destination'].exists():
                FileOperations.safe_move(
                    operation['destination'], 
                    operation['source'],
                    on_conflict=ConflictStrategy.OVERWRITE
                )
            
            # Restore backup if original destination existed
            if operation['backup_path'] and operation['backup_path'].exists():
                FileOperations.safe_move(
                    operation['backup_path'],
                    operation['destination'],
                    on_conflict=ConflictStrategy.OVERWRITE
                )
        
        elif op_type == 'copy':
            # Remove the copied file/directory
            if operation['destination'].exists():
                FileOperations.safe_delete(operation['destination'])
            
            # Restore backup if original destination existed
            if operation['backup_path'] and operation['backup_path'].exists():
                FileOperations.safe_move(
                    operation['backup_path'],
                    operation['destination'],
                    on_conflict=ConflictStrategy.OVERWRITE
                )
        
        elif op_type == 'delete':
            # Restore from backup
            if operation['backup_path'] and operation['backup_path'].exists():
                FileOperations.safe_move(
                    operation['backup_path'],
                    operation['source'],
                    on_conflict=ConflictStrategy.OVERWRITE
                )
    
    def _reset_transaction(self) -> None:
        """Reset transaction state."""
        self.in_transaction = False
        self.operations_log.clear()
        self.backup_dir = None
    
    def __enter__(self):
        """Context manager entry."""
        self.begin_transaction()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic rollback on exception."""
        if exc_type is not None:
            # Exception occurred, rollback
            self.rollback()
        else:
            # No exception, commit
            self.commit()