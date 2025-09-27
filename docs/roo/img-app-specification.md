# KDC Image Organizer - Application Specification

<!-- Canonical decisions reference -->
Note: Canonical implementation decisions (thresholds, cache defaults, file identity strategy, API shapes, DB schema versioning, telemetry policy) are consolidated in [`docs/roo/canonical-decisions.md`](docs/roo/canonical-decisions.md:1). Implementations MUST follow that document.

## 1. Executive Summary

### 1.1 Project Overview
The KDC Image Organizer (img-app) is a cross-platform desktop GUI application designed to manage, organize, and process large collections of digital photographs (10,000+ images) stored on local file systems. Built using Python 3.13+ and PySide6, it leverages the pk-py-lib component library for reusable functionality.

### 1.2 Primary Objectives
- Detect and manage duplicate/similar images across large photo collections
- Provide advanced file organization and batch processing capabilities
- Offer professional-grade image management with consumer-friendly interface
- Ensure data safety through non-destructive operations and comprehensive undo

### 1.3 Target Users
- Photography enthusiasts with large personal photo collections
- Professional photographers needing duplicate management
- Digital archivists organizing historical image collections
- Anyone managing 10,000+ digital images requiring organization

## Canonical Conventions [ID: PROC-001]

- Internal representation: similarity thresholds and scores are stored as floating-point values in the range 0.0 — 1.0 (inclusive). All persistent storage (databases, caches) record similarity values using this canonical range.
- User interface representation: thresholds and similarity scores are presented to users as percentages (0 — 100%). UI components convert between the internal 0.0—1.0 representation and the user-facing 0—100% representation transparently.
- Documentation convention: where a feature or UI element is described, percentages (0—100%) are used for readability. Where storage, APIs, or database schemas are described, the canonical 0.0—1.0 representation is used.
## 2. Functional Requirements

### 2.0 Application Startup and Initialization

#### 2.0.1 Database Validation
**Startup Sequence:**
1. Check for existence of all required databases:
   - `settings.db` in user_data_dir
   - `sessions.db` in user_data_dir
   - `cache.db` in user_cache_dir
2. If any database doesn't exist, create it with initial schema
3. For each existing database:
   - Run `PRAGMA quick_check`
   - If quick_check fails, run `PRAGMA integrity_check`
   - If integrity_check fails, mark as corrupt and prompt user:
     - For settings.db: Offer to export/preserve settings before rebuild
     - For cache.db/sessions.db: Safe to rebuild from scratch

**Schema Migration:**
- Check `meta` table for `schema_version` in each database
- If version mismatch detected:
  1. Create timestamped backup in `backups/` subdirectory
  2. Run Alembic migrations to update schema
  3. Update schema_version in meta table
- Backup retention: Keep 10 most recent, purge older than 30 days

#### 2.0.2 Application Data Locations
**Directory Structure:**
- Vendor: "Pk"
- Application: "Img App"
- Use platformdirs library for cross-platform paths:
  ```
  user_data_dir/
    settings.db      # Application settings and profiles
    sessions.db      # Scan sessions and results
    backups/         # Database backups
  user_cache_dir/
    cache.db         # Image metadata and hashes
    thumbnails/      # Thumbnail images
      256x256/
      512x512/
  ```
- Environment override: `PK_IMG_APP_HOME` can override base directory

### 2.0.3 Command Line Interface (CLI) Options

The application supports the following command-line arguments for bootstrap and utility functions:

- `-l`, `--location`: List all local data paths used by the application (e.g., settings.db, cache.db, log directories).
- `-d`, `--default`: Automatically run/start the operation defined by the last active profile immediately upon GUI launch. This bypasses manual clicking of the "Start" button.

### 2.1 Core Features

#### 2.1.1 Image Format Support
**Supported Formats:**
- Standard: JPEG (.jpg, .jpeg), PNG (.png), GIF (.gif), BMP (.bmp), TIFF (.tif, .tiff)
- Modern: WebP (.webp), HEIF/HEIC (.heif, .heic)
- Future consideration: RAW formats (Phase 2)

**Format Handling:**
- Automatic format detection via file headers
- Graceful handling of corrupted/unsupported files
- Format conversion capabilities for batch operations

#### 2.1.2 File Selection System
**Selection Methods:**
- Individual file selection via file picker dialog
- Folder selection with recursive scanning
- Drag-and-drop support for files and folders
- Multiple selection modes (add, remove, clear)

**Dual Collection Support:**
- Single collection mode: One set of images for self-comparison
- Dual collection mode: Reference set vs target set comparison
- Visual distinction between reference and target collections
- Collection management (save, load, modify)

#### 2.1.3 Settings Profiles and Configuration

> **Note: Option A Settings Profiles Override**
> For Settings Profiles v1 (Option A), see canonical decision §18 in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).
> Option A uses a strongly-typed JSON profile schema with centralized validation, Balanced defaults, and specific algorithm choices that override some specifications below.

**Profile System:**
- Multiple named settings profiles for different workflows
- Each profile contains:
  - `id`: UUID primary key
  - `name`: Unique profile name (required)
  - `description`: Optional description text
  - `created_at`, `updated_at`: Timestamps
  - `profile_version`: Version string for format compatibility

**Pool Configuration:**
- **Single Pool Mode:**
  - Compare images within a single set of paths
  - Find all duplicates/similar images within the pool
  - Results show grouped duplicate clusters
  
- **Dual Pool Mode:**
  - Pool 1: Reference images (source of truth)
  - Pool 2: Target images to check against Pool 1
  - Default: Show Pool 2 files that match Pool 1
  - Inverse mode: Show Pool 1 files with NO matches in Pool 2

**Path Selection per Pool:**
- `include_dirs`: List of directories to scan
- `exclude_dirs`: List of directories to skip
- `include_globs`: File patterns to include (e.g., "*.jpg")
- `exclude_globs`: File patterns to exclude

**File Identity Detection:**
- **Identical File Detection:**
  - Algorithm: SHA-256 hashing (Note: Option A uses BLAKE3 for duplicates runs)
  - Staged hashing option (default enabled):
    - Stage 1: Group by file size
    - Stage 2: Partial hash (first/last 256KB) for files ≥512KB
    - Stage 3: Full SHA-256 for candidates (BLAKE3 in Option A duplicates mode)
  - Cache results with invalidation on size/mtime change

#### 2.1.4 Similarity Detection Engine

> **Note: Option A Algorithm Selection**
> For Settings Profiles v1 (Option A):
> - Duplicates mode: Uses BLAKE3 algorithm (fixed)
> - Similarity mode: Uses pHash algorithm with degree_ui 0-100 normalized to 0.0-1.0
> See canonical decision §18 and Package A specifications in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

**Algorithms:**
```
1. Perceptual Hash (pHash)
   - Default algorithm for general similarity
   - Robust to scaling, aspect ratio changes
   - Similarity range: 0-100% (internal: 0.0-1.0)

2. Difference Hash (dHash)
   - Fast algorithm for quick scanning
   - Good for detecting crops and edits
   - Similarity range: 0-100% (internal: 0.0-1.0)

3. Histogram Comparison
   - Color distribution analysis
   - Effective for color-shifted duplicates
   - Multiple comparison metrics (Chi-Square, Correlation, Intersection)

4. Feature Matching (Advanced)
   - SIFT/SURF/ORB keypoint detection
   - Robust to rotation and perspective changes
   - Higher computational cost

5. Identical File Detection
   - SHA-256 hash comparison
   - 100% exact byte-for-byte matches only
   - Fastest for finding exact duplicates
```

**Configuration:**
- Algorithm selection (single or multiple)
- Per-algorithm threshold settings (internal: 0.0-1.0)
- Preset configurations:
  - Exact Duplicates (100% match / 1.0 internal)
  - Near Duplicates (95-99% match / 0.95-0.99 internal)
  - Similar Images (85-94% match / 0.85-0.94 internal)
  - Loosely Related (70-84% match / 0.70-0.84 internal)
- Custom threshold definition

**Processing:**
- Multi-threaded parallel processing
- Configurable thread pool (auto-detect CPU cores)
- Progress tracking with ETA
- Pausable/resumable operations
- Batch size optimization for memory efficiency

### 2.2 Results Management

#### 2.2.1 Results Display
**Results Semantics by Mode:**

**Single Pool Results:**
- Display duplicate/similar groups (clusters)
- Each cluster contains all matching images
- Group header shows:
  - Number of images in cluster
  - Similarity score range (0-100% display)
  - Total size of all files in cluster
  - Potential space savings (size - smallest)
- All files in cluster are displayed
- User can select which files to keep/delete

**Dual Pool Results (Default):**
- Show only Pool 2 files that match Pool 1 files
- Group by Pool 1 reference image
- Each group shows:
  - Pool 1 reference image (header, not selectable)
  - All matching Pool 2 files (selectable)
- Only Pool 2 files appear in action lists
- Pool 1 files are read-only references

**Dual Pool Results (Inverse Mode):**
- Show only Pool 1 files with NO matches in Pool 2
- List shows unique Pool 1 files only
- No Pool 2 files displayed
- Useful for finding unique content in reference set

**Group Organization:**
- Hierarchical group display
- Expandable/collapsible groups
- Visual distinction between reference and target files

**Individual Image Information:**
- Full file path
- File size (human-readable)
- Image dimensions (width × height)
- File modification date
- Similarity score to group reference
- EXIF data summary

**Sorting Options:**
- By similarity score (ascending/descending)
- By file size (largest/smallest first)
- By date (newest/oldest first)
- By number of duplicates
- By potential space savings

**Filtering Options:**
- Minimum group size
- Date range filter
- File size range
- Path inclusion/exclusion patterns
- Similarity score threshold

#### 2.2.2 Image Preview System
**Preview Modes:**
- Single image preview with zoom/pan
- Side-by-side comparison view
- Grid view for group overview
- Slideshow mode for quick review

**Preview Features:**
- Synchronized zoom/pan in comparison mode
- Pixel-level difference highlighting
- EXIF data overlay
- Histogram display
- Quick actions toolbar (rotate, delete, open external)

### 2.3 File Operations

#### 2.3.1 Deletion Operations
**Safety Features:**
- Move to system recycle bin (default)
- Optional permanent deletion with confirmation
- Multi-step confirmation for batch operations
- Automatic backup before deletion (optional)

**Selection Methods:**
- Individual file checkbox selection
- Quick select patterns:
  - Keep largest/smallest
  - Keep newest/oldest
  - Keep best quality (by resolution)
  - Keep by path pattern
- Manual selection with keyboard shortcuts

#### 2.3.2 Organization Operations
**Move Operations:**
- Move to specified folder
- Create folder structure from EXIF data
- Organize by date taken (YYYY/MM/DD)
- Custom organization patterns

**Rename Operations:**
- Template-based batch renaming
- Variables: {date}, {time}, {camera}, {sequence}
- Preview before execution
- Collision handling

#### 2.3.3 Undo System
**Undo Stack:**
- Comprehensive operation history
- Multi-level undo/redo
- Persistent across sessions
- Visual history browser
- Selective undo capability

### 2.4 Batch Processing

#### 2.4.1 Image Operations
- Resize (maintain aspect ratio)
- Format conversion
- Quality adjustment
- Watermark application
- EXIF data modification/removal

#### 2.4.2 Processing Queue
- Add multiple operations
- Preview results
- Parallel processing
- Progress tracking
- Error handling with skip/retry options

## 3. User Interface Specifications

### 3.1 Application Window

#### 3.1.1 Layout Architecture
**Main Window Structure:**
```
┌─────────────────────────────────────────────────┐
│  Menu Bar (File, Edit, View, Tools, Help)       │
├─────────────────────────────────────────────────┤
│  Main Toolbar (Common Actions)                  │
├─────────────────────────────────────────────────┤
│ ┌──────────┬──────────────────┬──────────────┐ │
│ │          │                  │              │ │
│ │  File    │   Results/       │   Preview    │ │
│ │  Tree    │   Content        │   Panel      │ │
│ │  Panel   │   Area           │              │ │
│ │          │                  │              │ │
│ └──────────┴──────────────────┴──────────────┘ │
│  Status Bar (Progress, Statistics)              │
└─────────────────────────────────────────────────┘
```

#### 3.1.2 Dockable Panels
- File Browser Panel (left)
- Results Panel (center)
- Preview Panel (right)
- Properties Panel (bottom)
- Log Panel (bottom)
- All panels dockable, hideable, resizable

### 3.2 Progressive Disclosure

#### 3.2.1 Basic Mode
- Simplified interface
- One-click duplicate scan
- Automatic settings
- Essential operations only

#### 3.2.2 Advanced Mode
- Full algorithm configuration
- Detailed filtering options
- Batch operations
- Custom workflows

### 3.3 Visual Design

#### 3.3.1 Theme Support
- Light theme (default)
- Dark theme
- High contrast theme
- Custom theme creation

#### 3.3.2 Accessibility
- Keyboard navigation for all features
- Screen reader compatibility
- Adjustable font sizes
- UI scaling (100%, 125%, 150%, 200%)
- Tooltips and context help
- **Text selectability**: All text in GUI elements, dialogs, labels, and informational displays must be selectable and copyable by mouse to facilitate user interaction and data extraction

## 4. Technical Architecture

### 4.1 Application Structure

#### 4.1.1 Component Architecture
```
img_app/
├── core/                    # Core business logic
│   ├── algorithms/         # Similarity algorithms
│   ├── processors/         # Image processors
│   ├── operations/         # File operations
│   └── database/          # Database management
├── gui/                    # GUI components
│   ├── widgets/           # Custom widgets
│   ├── dialogs/           # Dialog windows
│   ├── panels/            # Dockable panels
│   └── models/            # Data models
├── utils/                  # Utility functions
└── config/                # Configuration management
```

#### 4.1.2 Threading Model
- Main GUI thread (PySide6 event loop)
- Worker thread pool for image processing
- Database thread for async operations
- File I/O thread for background loading

### 4.2 Performance Requirements

#### 4.2.1 Scalability
- Handle 100,000+ images
- Process 1,000 images/minute (similarity detection)
- Maximum 2048 MB RAM usage (≈2 GB) (configurable)
- Responsive UI during processing

#### 4.2.2 Optimization Strategies
- Lazy loading for large datasets
- Thumbnail caching system
- Incremental result updates
- Memory-mapped file access for large images

## 5. Data Management

### 5.1 Database Design

#### 5.1.1 Database Structure
**Primary Database (settings.db):**
- Application-scoped settings (AppSettings: UI preferences, performance tuning)
- Profile data (named profiles representing saved workflows and algorithm/file-handling defaults)
- Profile-scoped key/value settings and presets
- Operation history
- Schema metadata and migration history (meta table)

**Cache Database (cache.db):**
- Image metadata
- Thumbnail data
- Similarity results
- File hashes

### 5.2 Caching Strategy

#### 5.2.1 Thumbnail Cache
- Location: User app data folder
- Default size: 5120 MB (≈5 GB) (configurable via app_settings.cache_size_mb)
- Thumbnail sizes: 256x256, 512x512, 1024x1024
- LRU eviction policy
- Automatic cleanup options

#### 5.2.2 Results Cache
- Similarity computation results
- Valid for unchanged files
- Invalidation on file modification
- Export/import capability

## 6. Configuration Management

### 6.1 Profile System

#### 6.1.1 Profile Features
- Multiple named profiles representing saved workflows
- Settings profile management:
  - Create new profile with validation
  - Select/activate existing profile
  - Edit profile (name, description, settings)
  - Delete profile with confirmation
  - Copy/clone profile to new name
- Advanced features:
  - Set as default (auto-load on startup)
  - Validate paths on save
  - Preview effective include/exclude
  - Test hash settings on sample files
- Import/export profiles as JSON
- Profile templates for common scenarios
- Profiles store algorithm defaults, presets, paths, and settings

#### 6.1.2 Settings Categories
- Algorithm configurations (profile-scoped)
- Profile-scoped presets and key/value settings
- Application-scoped settings (AppSettings): UI preferences, performance tuning, global shortcuts
- File type associations
- Path preferences
- Operation history

### 6.2 Persistence

#### 6.2.1 Persistent Data
- Window layout and size
- Panel configurations
- Recent folders/files
- Search history
- Custom presets
- Operation history

## 7. Error Handling

### 7.1 Error Management
- Graceful degradation
- User-friendly error messages
- Detailed error logging
- Recovery suggestions
- Continue on error option

### 7.2 Logging System
- Multiple log levels (DEBUG, INFO, WARNING, ERROR)
- Rotating log files
- Maximum log size limits
- Log viewer in application
- Export logs for support

## 8. Security Considerations

### 8.1 Data Protection
- No network communications
- Local-only data storage
- Secure deletion options
- No telemetry or tracking

### 8.2 File System Safety
- Read-only by default
- Explicit user confirmation for modifications
- Safe path handling
- Permission checking

## 9. Development Phases

### Phase 1: Core Functionality (Weeks 1-4)
- Basic GUI framework
- File selection system
- Single similarity algorithm (pHash)
- Basic results display
- Simple deletion operations

### Phase 2: Advanced Features (Weeks 5-8)
- Multiple algorithms
- Advanced filtering/sorting
- Batch operations
- Profile system
- Undo/redo system

### Phase 3: Enhancement (Weeks 9-12)
- EXIF-based organization
- Batch processing
- Plugin architecture
- Performance optimization
- Polish and refinement

### Phase 4: Future Features (Post-release)
- AI-powered features
- Cloud storage integration
- RAW format support
- Face detection
- Advanced automation

## 10. Testing Requirements

### 10.1 Test Coverage
- Unit tests for all algorithms
- Integration tests for workflows
- GUI automation tests
- Performance benchmarks
- Stress testing with large datasets

### 10.2 Test Scenarios
- Empty folder handling
- Corrupted file handling
- Permission denied scenarios
- Large file handling (>100MB)
- Network drive disconnection
- Database corruption recovery

## 11. Dependencies

### 11.1 Required Libraries
- Python 3.13+
- PySide6 >= 6.6.0
- Pillow >= 10.0.0
- NumPy >= 1.24.0
- OpenCV-Python >= 4.8.0
- scikit-image >= 0.22.0
- imagehash >= 4.3.0
- SQLite3 (built-in)

### 11.2 Optional Libraries
- Pillow-HEIF >= 0.13.0 (HEIF support)
- ExifRead >= 3.0.0 (EXIF parsing)
- Send2Trash >= 1.8.0 (safe deletion)

## 12. Deployment

### 12.1 Distribution
- Standalone executable (PyInstaller)
- Python package (pip installable)
- Portable version (no installation)

### 12.2 System Requirements
- Windows 10/11, macOS 10.15+, Linux (Ubuntu 20.04+)
- Minimum 4096 MB RAM (≈4 GB); 8192 MB recommended (≈8 GB)
- 500MB disk space + cache
- OpenGL 2.1+ for hardware acceleration