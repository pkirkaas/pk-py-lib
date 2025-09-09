# Image Organizer - GUI Design Specifications
> Updated for Structured Settings Profiles (Option A)

## Settings Dialog GUI Design

### Mermaid Diagram of Structured Settings Dialog

```mermaid
flowchart TD
    subgraph Dialog[Settings Manager Dialog]
        direction TB
        
        subgraph LeftPane[Left Pane - Profiles List]
            Search[Search Box]
            ProfilesList[Profiles List View]
            Toolbar[Toolbar: Create, Rename, Duplicate, Delete, Set Active]
        end

        subgraph RightPane[Right Pane - Structured Editor]
            direction TB
            
            subgraph Metadata[Profile Metadata]
                Name[Name Input]
                Description[Description Text Area]
            end

            subgraph Pools[Pools Configuration]
                direction TB
                
                subgraph PoolA[Pool A (Required)]
                    PoolAPath[Path Input + Browse Button]
                    PoolAOptions[Options: Recurse, Follow Symlinks, Include Hidden]
                end

                subgraph PoolB[Pool B (Optional)]
                    PoolBPath[Path Input + Browse Button]
                    PoolBOptions[Options: Recurse, Follow Symlinks, Include Hidden]
                end
            end

            subgraph ModeCriteria[Mode & Criteria]
                direction TB
                
                Mode[Mode Dropdown: duplicates/similarity]
                
                subgraph Criteria[Criteria]
                    Algorithm[Algorithm Dropdown: pHash/blake3]
                    Degree[Similarity Degree Slider 0-100%]
                end
            end

            subgraph Scope[Scope]
                direction TB
                ScopeKind[Kind Dropdown: single_pool/two_pool]
                Direction[Direction Dropdown: A_TO_B, B_TO_A, etc.]
            end

            subgraph Output[Output]
                OutputMode[Mode Dropdown: report_only]
            end

            Validation[Validation Status Label]
        end

        subgraph Footer[Footer Buttons]
            Buttons[OK, Apply, Cancel]
        end
    end

    LeftPane --> RightPane
    Metadata --> Pools
    Pools --> ModeCriteria
    ModeCriteria --> Scope
    Scope --> Output
    Output --> Validation
    RightPane --> Footer
```

### GUI Component Details

#### 1. Profile Metadata Section
- **Name Input**: Text field with validation (1-64 chars, alphanumeric + spaces/hyphens/underscores)
- **Description Text Area**: Multi-line optional description

#### 2. Pools Configuration
- **Pool A** (Required):
  - Multiple path input field with browse button (opens directory/file selector)
  - Paths can be directories or individual files
  - Checkboxes: Recurse subdirectories (default: checked), Follow symbolic links, Include hidden files
- **Pool B** (Optional, enabled for two-pool operations):
  - Same controls as Pool A
  - Enabled/disabled based on scope selection

#### 3. Mode & Criteria Section
- **Mode Dropdown**: "duplicates" or "similarity"
- **Criteria** (context-sensitive):
  - **Algorithm Dropdown**: "pHash" or "blake3" (auto-set to "blake3" for duplicates mode)
  - **Similarity Degree**: Slider (0-100%) with percentage display (disabled for duplicates mode)

#### 4. Scope Section
- **Kind Dropdown**: "single_pool" or "two_pool"
- **Direction Dropdown** (enabled only for two_pool):
  - "A_TO_B": Find items in B that match A
  - "B_TO_A": Find items in A that match B  
  - "A_WITHOUT_IN_B": Items in A with no match in B
  - "B_WITHOUT_IN_A": Items in B with no match in A

#### 5. Output Section
- **Mode Dropdown**: "report_only" (only option in v1)

#### 6. Validation & Feedback
- Real-time validation status display
- Color-coded messages (green for valid, red for errors)
- **All text elements must be selectable and copyable** (error messages, labels, etc.)
- Conditional enablement of controls based on selections

### UI Behavior Rules

#### Conditional Enablement
1. **Pool B Controls**: Enabled only when scope.kind = "two_pool"
2. **Direction Dropdown**: Enabled only when both Pool A and Pool B have valid paths
3. **Degree Slider**: Enabled only for similarity mode
4. **Algorithm Dropdown**: Locked to "blake3" for duplicates mode

#### Validation Rules
1. **Pool A Paths**: Must have at least one valid path specified
2. **Pool B Paths**: Required only for two-pool scope, must have valid paths if specified
3. **Name**: Must be unique and meet pattern requirements
4. **Mode-specific validation**:
   - Duplicates mode: No degree allowed
   - Similarity mode: Degree required (0-100)

#### Path Selection
- Browse buttons open directory/file selector dialog (supports multiple selection)
- Paths can be directories or individual files
- Paths are validated for existence and readability
- Recent paths may be suggested based on history

### Integration with Application

#### Settings Manager Dialog
- Left pane: Profiles list with search and management actions
- Right pane: Structured editor as described above
- Footer: OK (apply & close), Apply (apply without closing), Cancel

#### Data Flow
1. Profile loaded from database into editor
2. User makes changes in structured form
3. Real-time validation provides feedback
4. On apply/ok, data is validated and saved
5. Structured data is stored in JSON format in database

### GUI Text Selectability Requirement

**All text displayed in the GUI must be selectable and copyable by the user.** This includes:

- Error and warning messages
- Validation status text
- Path displays and labels
- Any informational text in dialogs
- Dropdown menu text items

Implementation guidelines:
- Use `QLabel` with `setTextInteractionFlags(Qt.TextSelectableByMouse)` for labels
- Ensure text in message boxes and dialogs is selectable
- Text fields should naturally support selection
- Avoid non-selectable text elements for user-facing information

### Migration from Key-Value to Structured

The new GUI replaces the key-value editor with a structured form that:
- Provides appropriate controls for each setting type (dropdowns, checkboxes, sliders)
- Ensures setting compatibility through UI constraints
- Offers better user experience with visual grouping and labels
- Maintains backward compatibility through data migration
- **Ensures all text content is selectable and copyable**

### Cross-References
- Data Model: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- API Specifications: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Technical Architecture: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)

## Main Window Menu Bar & Cache Management (implemented)

Status: Implemented

Overview
- The application provides a native menu bar with four top-level menus: File, Cache, View, Help.
- Cache management is accessible from the Cache menu and includes non-destructive metadata operations on cache.db and a destructive “clear” flow that recreates cache.db.
- The profile toolbar is attached as a true top toolbar, ensuring the menu bar remains visible and follows platform UX conventions.

Code references
- Menu bar creation: [MainWindow._setup_menu_bar()](img_app/img_app/main_window.py:283)
- Toolbar placement (fix): [MainWindow._setup_profile_toolbar()](img_app/img_app/main_window.py:157)
- Cache actions: [MainWindow._on_clear_cache()](img_app/img_app/main_window.py:971), [MainWindow._on_clean_cache()](img_app/img_app/main_window.py:1017)
- About dialog: [MainWindow._show_about()](img_app/img_app/main_window.py:940)
- Message utilities and error handling: [show_selectable_info()](src/pk_py_lib/gui/utils/messages.py:149), [show_selectable_error()](src/pk_py_lib/gui/utils/messages.py:131), [gui_error_handler()](src/pk_py_lib/gui/utils/messages.py:293)
- DB helpers and schema: [DatabaseManager.get_connection()](src/pk_py_lib/core/database.py:699), [CACHE_SCHEMA](src/pk_py_lib/core/database.py:149)

Menu bar structure and behavior
- File
  - Open... (placeholder)
  - Save (placeholder)
  - Exit (placeholder)
- Cache
  - Clear Cache
    - Behavior: Deletes cache.db (if present) and recreates an empty schema using [CACHE_SCHEMA](src/pk_py_lib/core/database.py:149).
    - UX: Confirmation dialog, then selectable success message; status bar feedback.
    - Notes: Only the database file is reset; file-backed thumbnails on disk remain. They are re-associated/replicated lazily during future operations.
    - Handler: [MainWindow._on_clear_cache()](img_app/img_app/main_window.py:971)
  - Clean Cache
    - Behavior: Validates image_metadata rows against the filesystem; removes rows for missing files and entries where file_size or mtime differ; runs VACUUM to compact the DB; cascades remove dependent rows (thumbnails metadata, hashes).
    - UX: Shows a selectable summary dialog with counts of checked/removed entries; status bar feedback.
    - Notes: This operation does not delete on-disk thumbnails; it maintains database integrity and size.
    - Handler: [MainWindow._on_clean_cache()](img_app/img_app/main_window.py:1017)
- View
  - Reset Layout (placeholder)
- Help
  - About...
    - Behavior: Shows application name and version with selectable text via [show_selectable_info()](src/pk_py_lib/gui/utils/messages.py:149); robust fallbacks to QMessageBox on rare failures.
    - References: [MainWindow._show_about()](img_app/img_app/main_window.py:940), version resolution [MainWindow._get_app_version()](img_app/img_app/main_window.py:917)

Placement and UX notes
- A real top toolbar is attached via addToolBar in [MainWindow._setup_profile_toolbar()](img_app/img_app/main_window.py:157). This resolves prior issues where pseudo-toolbar widgets inside the central layout could obscure or displace the native menu bar.
- All dialogs and message surfaces use selectable text to facilitate copy/paste for diagnostics, per project requirements.

Accessibility and error handling patterns
- All cache menu handlers are decorated with [gui_error_handler()](src/pk_py_lib/gui/utils/messages.py:293), which:
  - Presents user-friendly, selectable dialogs ([show_selectable_error()](src/pk_py_lib/gui/utils/messages.py:131))
  - Logs detailed diagnostics to STDERR with file path, line number, and stack trace
- Informational results use [show_selectable_info()](src/pk_py_lib/gui/utils/messages.py:149) to ensure copyable text.

Acceptance checklist (UI)
- Menu bar shows File, Cache, View, Help.
- Cache → Clear Cache and Cache → Clean Cache are present and functional as specified.
- About dialog shows app name and version with selectable text.
- Menu bar remains visible; toolbar is anchored in the top toolbar area (non-movable, non-floatable).

## Duplicate Manager Dialog

### Enhanced Flow for Single-Pool Mode

**New User Experience:**
- **Elimination of Modal Interruptions**: The previous "Processing Summary" and "Report" modal dialogs have been removed to improve workflow continuity.
- **Integrated Tabbed Interface**: Upon scan completion, the DuplicateManagerDialog opens directly with two dedicated tabs:
  - **Processing Summary Tab**: Displays real-time processing counters (files scanned, duplicates found, etc.) with selectable text for easy copying.
  - **Duplicate Report Tab**: Provides detailed duplicate detection results with cluster information, similarity scores, and file details, all with selectable text.
- **Direct Access**: Users can immediately interact with results without dismissing intermediate dialogs.

**Implementation Details:**
- **Code Changes**:
  - [`main_window.py`](img_app/img_app/main_window.py): Modified `_on_scan_finished` method to open enhanced DuplicateManagerDialog directly.
  - [`duplicate_manager.py`](img_app/img_app/widgets/duplicate_manager.py): Enhanced `__init__` to include tab widget with QTextEdit areas for summary and report.
- **Text Selectability**: All text in both tabs is selectable and copyable, adhering to project guidelines (`setTextInteractionFlags(Qt.TextSelectableByMouse)`).

**Benefits:**
- **Streamlined Workflow**: Users proceed directly from scan initiation to result interaction without modal interruptions.
- **Improved Usability**: Tabbed interface allows easy switching between summary statistics and detailed reports.
- **Enhanced Data Accessibility**: Selectable text facilitates copying of results for external use or documentation.
