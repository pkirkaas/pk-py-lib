"""
File Organization Module

Advanced file organization capabilities including automatic sorting,
duplicate handling, and intelligent file management.
"""

from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
import hashlib

from .operations import FileOperations, ConflictStrategy
from .traversal import DirectoryTraversal
from ..logging import get_logger

log = get_logger(__name__)


@dataclass
class OrganizationRule:
    """Rule for organizing files."""
    name: str
    condition: Callable[[Path], bool]  # Function to test if rule applies
    destination_func: Callable[[Path], Path]  # Function to determine destination
    priority: int = 0  # Higher priority rules are applied first


class FileOrganizer:
    """
    Advanced file organization with customizable rules and strategies.
    
    Provides flexible file organization based on various criteria including
    file type, date, size, content analysis, and custom rules.
    """
    
    def __init__(self, base_destination: Path):
        """
        Initialize file organizer.
        
        Args:
            base_destination: Base directory for organized files
        """
        self.base_destination = Path(base_destination)
        self.rules: List[OrganizationRule] = []
        self.default_strategy = "type"  # "type", "date", "size", "custom"
        
    def add_rule(self, rule: OrganizationRule) -> None:
        """
        Add organization rule.
        
        Args:
            rule: Organization rule to add
        """
        self.rules.append(rule)
        # Sort rules by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        log.debug(f"Added organization rule: {rule.name}")
    
    def organize_files(
        self,
        files: List[Path],
        dry_run: bool = False,
        conflict_strategy: ConflictStrategy = ConflictStrategy.RENAME
    ) -> Dict[str, Any]:
        """
        Organize files according to configured rules.
        
        Args:
            files: List of files to organize
            dry_run: If True, return plan without executing
            conflict_strategy: How to handle conflicts
            
        Returns:
            Dictionary with organization results
        """
        results = {
            "planned_moves": {},
            "completed_moves": {},
            "errors": [],
            "skipped": [],
            "summary": {
                "total_files": len(files),
                "organized": 0,
                "skipped": 0,
                "errors": 0
            }
        }
        
        log.info(f"Starting organization of {len(files)} files")
        
        for file_path in files:
            try:
                if not file_path.exists() or not file_path.is_file():
                    results["skipped"].append(str(file_path))
                    results["summary"]["skipped"] += 1
                    continue
                
                # Determine destination using rules
                destination = self._determine_destination(file_path)
                results["planned_moves"][str(file_path)] = str(destination)
                
                # Execute move if not dry run
                if not dry_run:
                    try:
                        final_dest = FileOperations.safe_move(
                            file_path,
                            destination,
                            on_conflict=conflict_strategy,
                            create_dirs=True
                        )
                        results["completed_moves"][str(file_path)] = str(final_dest)
                        results["summary"]["organized"] += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to move {file_path}: {e}"
                        results["errors"].append(error_msg)
                        results["summary"]["errors"] += 1
                        log.error(error_msg, exception=e)
                
            except Exception as e:
                error_msg = f"Error processing {file_path}: {e}"
                results["errors"].append(error_msg)
                results["summary"]["errors"] += 1
                log.error(error_msg, exception=e)
        
        log.info(f"Organization complete: {results['summary']}")
        return results
    
    def _determine_destination(self, file_path: Path) -> Path:
        """Determine destination for a file using organization rules."""
        # Try custom rules first (in priority order)
        for rule in self.rules:
            try:
                if rule.condition(file_path):
                    destination = rule.destination_func(file_path)
                    log.debug(f"Applied rule '{rule.name}' to {file_path} -> {destination}")
                    return self.base_destination / destination / file_path.name
            except Exception as e:
                log.warning(f"Rule '{rule.name}' failed for {file_path}: {e}")
                continue
        
        # Fall back to default strategy
        if self.default_strategy == "type":
            subdir = self._organize_by_type(file_path)
        elif self.default_strategy == "date":
            subdir = self._organize_by_date(file_path)
        elif self.default_strategy == "size":
            subdir = self._organize_by_size(file_path)
        else:
            subdir = Path("unsorted")
        
        return self.base_destination / subdir / file_path.name
    
    def _organize_by_type(self, file_path: Path) -> Path:
        """Organize by file type/extension."""
        extension = file_path.suffix.lower()
        
        # Define type categories
        type_mapping = {
            # Images
            '.jpg': 'images/photos', '.jpeg': 'images/photos', '.png': 'images/graphics',
            '.gif': 'images/graphics', '.bmp': 'images/graphics', '.tiff': 'images/photos',
            '.tif': 'images/photos', '.webp': 'images/graphics', '.svg': 'images/vector',
            '.raw': 'images/raw', '.cr2': 'images/raw', '.nef': 'images/raw',
            
            # Videos
            '.mp4': 'videos/mp4', '.avi': 'videos/avi', '.mkv': 'videos/mkv',
            '.mov': 'videos/quicktime', '.wmv': 'videos/windows', '.flv': 'videos/flash',
            '.webm': 'videos/web', '.m4v': 'videos/mp4',
            
            # Audio
            '.mp3': 'audio/mp3', '.wav': 'audio/wav', '.flac': 'audio/lossless',
            '.aac': 'audio/aac', '.ogg': 'audio/ogg', '.m4a': 'audio/aac',
            
            # Documents
            '.pdf': 'documents/pdf', '.doc': 'documents/word', '.docx': 'documents/word',
            '.xls': 'documents/excel', '.xlsx': 'documents/excel',
            '.ppt': 'documents/powerpoint', '.pptx': 'documents/powerpoint',
            '.txt': 'documents/text', '.rtf': 'documents/text',
            
            # Archives
            '.zip': 'archives/zip', '.rar': 'archives/rar', '.7z': 'archives/7zip',
            '.tar': 'archives/tar', '.gz': 'archives/gzip', '.bz2': 'archives/bzip2',
            
            # Code
            '.py': 'code/python', '.js': 'code/javascript', '.html': 'code/web',
            '.css': 'code/web', '.cpp': 'code/cpp', '.java': 'code/java',
        }
        
        return Path(type_mapping.get(extension, f'other/{extension[1:] if extension else "no_extension"}'))
    
    def _organize_by_date(self, file_path: Path) -> Path:
        """Organize by file modification date."""
        try:
            mtime = file_path.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)
            return Path(f"{dt.year:04d}/{dt.month:02d}")
        except OSError:
            return Path("unknown_date")
    
    def _organize_by_size(self, file_path: Path) -> Path:
        """Organize by file size."""
        try:
            size = file_path.stat().st_size
            size_mb = size / (1024 * 1024)
            
            if size_mb < 1:
                return Path("small")
            elif size_mb < 10:
                return Path("medium")
            elif size_mb < 100:
                return Path("large")
            else:
                return Path("huge")
        except OSError:
            return Path("unknown_size")
    
    def create_photo_organization_rules(self) -> None:
        """Create specialized rules for photo organization."""
        
        # Rule: RAW files go to raw folder
        self.add_rule(OrganizationRule(
            name="RAW Photos",
            condition=lambda p: p.suffix.lower() in ['.raw', '.cr2', '.nef', '.arw', '.dng'],
            destination_func=lambda p: Path("photos/raw"),
            priority=100
        ))
        
        # Rule: Screenshots to screenshots folder
        self.add_rule(OrganizationRule(
            name="Screenshots",
            condition=lambda p: 'screenshot' in p.name.lower() or 'screen shot' in p.name.lower(),
            destination_func=lambda p: Path("screenshots"),
            priority=90
        ))
        
        # Rule: Organize photos by EXIF date if available
        def get_photo_date_path(file_path: Path) -> Path:
            try:
                # Try to extract EXIF date (would need pillow/exifread)
                # For now, fall back to file date
                return self._organize_by_date(file_path)
            except:
                return Path("photos/unsorted")
        
        self.add_rule(OrganizationRule(
            name="Photos by Date",
            condition=lambda p: p.suffix.lower() in ['.jpg', '.jpeg', '.tiff', '.tif'],
            destination_func=lambda p: Path("photos") / get_photo_date_path(p),
            priority=50
        ))
    
    def create_duplicate_handling_rules(self) -> None:
        """Create rules for handling duplicate files."""
        
        def handle_duplicate(file_path: Path) -> Path:
            # Check if file already exists in organized structure
            potential_dest = self._determine_destination(file_path)
            if potential_dest.exists():
                # Compare file hashes to detect true duplicates
                if self._files_are_identical(file_path, potential_dest):
                    return Path("duplicates/identical")
                else:
                    return Path("duplicates/similar_names")
            return self._organize_by_type(file_path)
        
        self.add_rule(OrganizationRule(
            name="Duplicate Handler",
            condition=lambda p: True,  # Always check
            destination_func=handle_duplicate,
            priority=1  # Low priority, runs after other rules
        ))
    
    def _files_are_identical(self, file1: Path, file2: Path) -> bool:
        """Check if two files are identical by comparing hashes."""
        try:
            return self._calculate_file_hash(file1) == self._calculate_file_hash(file2)
        except:
            return False
    
    def _calculate_file_hash(self, file_path: Path, chunk_size: int = 8192) -> str:
        """Calculate SHA-256 hash of file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except:
            raise
    
    def analyze_organization_potential(self, directory: Path) -> Dict[str, Any]:
        """
        Analyze how files in a directory would be organized.
        
        Args:
            directory: Directory to analyze
            
        Returns:
            Analysis results showing organization potential
        """
        analysis = {
            "total_files": 0,
            "organization_preview": defaultdict(list),
            "size_by_category": defaultdict(int),
            "recommendations": []
        }
        
        try:
            files = list(DirectoryTraversal.walk_files(directory))
            analysis["total_files"] = len(files)
            
            for file_path in files:
                # Determine where this file would go
                destination = self._determine_destination(file_path)
                category = str(destination.parent.relative_to(self.base_destination))
                
                analysis["organization_preview"][category].append(str(file_path))
                
                # Track size by category
                try:
                    size = file_path.stat().st_size
                    analysis["size_by_category"][category] += size
                except OSError:
                    pass
            
            # Generate recommendations
            file_types = defaultdict(int)
            for file_path in files:
                file_types[file_path.suffix.lower()] += 1
            
            # Recommend photo organization if many images
            image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.raw', '.cr2'}
            image_count = sum(count for ext, count in file_types.items() if ext in image_extensions)
            if image_count > 50:
                analysis["recommendations"].append(
                    f"Consider using photo organization rules ({image_count} images found)"
                )
            
            # Recommend duplicate handling if many files
            if len(files) > 1000:
                analysis["recommendations"].append(
                    "Consider enabling duplicate detection for large file collection"
                )
        
        except Exception as e:
            analysis["error"] = str(e)
            log.error(f"Error analyzing organization potential for {directory}", exception=e)
        
        return analysis


class SmartOrganizer:
    """
    Intelligent file organizer with machine learning potential.
    
    This class provides advanced organization features that could
    be extended with ML capabilities in the future.
    """
    
    def __init__(self, base_destination: Path):
        self.organizer = FileOrganizer(base_destination)
        self.learning_data = []
        
    def learn_from_user_moves(self, source: Path, user_destination: Path) -> None:
        """
        Learn from user's manual file organization choices.
        
        Args:
            source: Original file location
            user_destination: Where user moved the file
        """
        # Store learning data for future ML implementation
        self.learning_data.append({
            "source": source,
            "destination": user_destination,
            "file_type": source.suffix.lower(),
            "file_size": source.stat().st_size if source.exists() else 0,
            "timestamp": datetime.now()
        })
        
        log.debug(f"Learned from user move: {source} -> {user_destination}")
    
    def suggest_organization(self, files: List[Path]) -> Dict[str, List[str]]:
        """
        Suggest organization based on learned patterns.
        
        Args:
            files: Files to suggest organization for
            
        Returns:
            Dictionary mapping suggested destinations to file lists
        """
        suggestions = defaultdict(list)
        
        for file_path in files:
            # For now, use standard organization
            # Future: Use ML model trained on learning_data
            destination = self.organizer._determine_destination(file_path)
            suggestions[str(destination.parent)].append(str(file_path))
        
        return dict(suggestions)