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

## Duplicate Manager Dialog (Exact Matches)

### Layout & Interaction Model
- **Tabs remain summary-focused**: The dialog still opens with the “Processing Summary” and “Duplicate Report” tabs (QTextEdit with selectable text) to surface scan metrics and the textual report.
- **Single-pane results view**: The middle splitter now contains only the left-hand QTreeWidget. The right-hand image preview pane has been removed because duplicate detection spans arbitrary file types.
- **Tree column roles**:
  - Column 1 (Name): File basename.
  - Column 2 (Directory): Parent directory.
  - Column 3 (Size): Human-readable file size.
  - Column 4 (File Type): Upper‑case extension (falls back to “—”).
  - Column 5 (Potential Savings): For groups, total reclaimable size if duplicates are deleted. For children, per-file delta relative to the smallest member; tooltip preserves the original last-modified timestamp.
  - Column 6 (Score): Hidden (duplicates are always 100 %).
- **Status line & footer**: Unchanged; continues to show total groups/files and selected items, with “Delete Selected” and the optional “Clear selections after delete” checkbox.

### UX Rationale
- Presents a compact, metadata-driven view suitable for non-image files (documents, archives, etc.).
- Eliminates empty/broken thumbnail previews while still allowing users to inspect directories, file types, and savings before deletion.
- Tooltips retain useful context (e.g., last-modified timestamp) without occupying column real estate.

### Implementation References
- [`duplicate_manager.py`](img_app/img_app/widgets/duplicate_manager.py): `_should_include_preview()` now returns `False`; `_populate_tree()` augments header/child rows with file-type and savings metadata; duplicate-specific header text updated.
- [`base_group_manager.py`](img_app/img_app/widgets/base_group_manager.py): Added `_should_include_preview()` and `_build_secondary_panel()` hooks so subclasses can opt out of the preview pane; preview-related slots are guarded when disabled.

## Similarity Manager Dialog (Perceptual Matches)

### Layout & Interaction Model
- Keeps the dual-pane experience: left tree + right preview table with thumbnails for perceptual comparison.
- Controls row includes algorithm combo, threshold spin box, and “Compute Groups”.
- Child rows retain preview, dimensions, similarity score columns in the preview table.

#### New "Exact" Column in SimilarityManager

- **Position**: Inserted after the "Quality" column in both the tree (left pane) and preview table (right pane).
- **Values**:
  - Blank (empty string) for unique files or files not part of an exact duplicate set.
  - Integer (e.g., "1", "2") representing the `exact_set_id` for files belonging to an exact duplicate set.
- **Purpose**: Provides visual indication of exact duplicate sets within perceptual similarity groups. Users can quickly identify and manage bitwise identical files as cohesive units (e.g., for bulk deletion), even when they form part of a larger similar group.
- **Behavior with Multiple Sets**: In a single perceptual group, multiple exact sets receive unique integers (assigned sequentially starting from 1 per scan). For example, a group might show Set 1 (two exact JPGs) and Set 2 (three exact PNG variants), all visually linked by their shared perceptual similarity to the group's reference.
- **Implementation Notes**: The column is populated from `FileItem.exact_set_id` during tree/table population. Tooltips explain: "Exact duplicate set ID (blank if unique)". Sorting by this column groups exact sets together for easier review.
- **UX Enhancement**: Supports set-level selections (e.g., check one file in a set to select all); integrates with existing checkbox tri-state logic for partial group selections.


### Implementation References
- [`similarity_manager.py`](img_app/img_app/widgets/similarity_manager.py): Inherits the base preview-enabled layout; no structural changes required beyond the existing similarity controls.
- [`base_group_manager.py`](img_app/img_app/widgets/base_group_manager.py): Preview helpers remain intact for similarity mode.

The two dialogs now share the summary/report scaffolding but diverge in the middle pane: duplicates deliver a metadata-only review surface, while similarity continues to prioritise visual inspection.

### User Interaction Flows in Results Dialogs (Duplicate/Similar Managers)

The Duplicate File Manager and Similar Image Manager dialogs support intuitive mouse interactions for file handling, enabling users to inspect and manage files directly from the results view without switching applications. These flows enhance usability by providing quick access to external tools (e.g., image editors, file explorers) while maintaining the dialog's focus on batch operations like deletions or selections.

#### Double-Click to Open File
- **Flow**: Users double-click a file item (child row in the tree) to launch it in the default OS-associated application. Group headers (parent rows) are ignored to avoid unintended actions.
- **Examples**:
  - In Duplicate Manager: Double-click a duplicate PDF to open it in Adobe Reader for content verification before deletion.
  - In Similar Image Manager: Double-click a similar JPG to view it full-size in Windows Photos (on Windows 11) or Preview (on macOS), allowing side-by-side comparison with the dialog's thumbnail preview.
- **Cross-Platform Behavior**: Uses Qt's `QDesktopServices.openUrl()` for seamless handling—e.g., opens images in the default viewer, documents in associated editors.
- **Usability Enhancement**: Provides instant file access for verification (e.g., checking if duplicates are truly identical or if similar images are variants), reducing workflow interruptions. Users stay in the dialog for selections while externally inspecting files, ideal for large scans where quick triage is key.

#### Right-Click Context Menu
- **Flow**: Right-click a file item to display a context menu with universal and OS-specific actions. Only file items trigger the menu; group headers show nothing.
- **Menu Actions** (Universal):
  - **Open File**: Mirrors double-click; launches in default app.
  - **Copy Path**: Copies the full absolute path to the clipboard for pasting into other tools (e.g., command line or email).
- **OS-Dependent Actions**:
  - **Windows-Specific**:
    - **Open Containing Folder**: Opens File Explorer with the file pre-selected (`explorer /select,"path"`), allowing easy navigation to related files.
    - **Properties**: Launches the native Properties dialog (`rundll32 shell32.dll`), showing details like size, attributes, and tabs for security/customization.
  - **Fallback for macOS/Linux**: **Open Folder** opens the parent directory in the default file manager (e.g., Finder or Nautilus) via `QDesktopServices`.
- **Examples**:
  - In Duplicate Manager: Right-click a selected duplicate → "Copy Path" to note it in a spreadsheet; "Open Containing Folder" to browse the directory for context.
  - In Similar Image Manager: Right-click a low-score similar image → "Open File" in an editor to crop/adjust; "Properties" (Windows) to check EXIF data for creation dates.
- **Usability Enhancement**: The menu offers power-user shortcuts for common tasks, streamlining file management. Windows actions leverage familiar shell integration (e.g., selected file in Explorer speeds up folder reviews), while fallbacks ensure accessibility on other OS. This empowers users to copy paths for reporting, inspect properties for forensics, or open folders for bulk actions—all without leaving the app, boosting efficiency in duplicate/similarity workflows.

#### Error Handling and Feedback
- Invalid paths (e.g., deleted files) trigger a selectable error dialog with details, allowing copy-paste for logging.
- All actions log success/failures with paths and context, ensuring traceability without disrupting the UI flow.

These interactions integrate with the existing selection system (checkboxes remain independent) and preview pane (Similarity Manager), preserving MVC separation while adding practical file-handling capabilities.

---
## Custom Painting Strategy for Group List Tables

### Overview
The group list tables in both Duplicate Manager and Similarity Manager dialogs now use a fully custom painting approach implemented by the [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159) class. This strategy replaces the previous Qt default rendering to ensure consistent visual appearance across different platforms and themes.

### Rationale for Custom Painting
- **Theme Independence**: Qt's default item rendering varies significantly across platforms and themes, leading to inconsistent visual experiences
- **Selection/Hover/Focus Visibility**: Custom painting ensures selection states are clearly visible regardless of system theme settings
- **Text Legibility**: Direct text drawing guarantees high contrast and readability in all conditions
- **Doubled-Text Resolution**: Eliminates the issue where Qt would draw text twice (once by default, once by custom code), causing blurry or misaligned text

### Delegate Implementation
The [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159) handles all visual aspects:

**Column 0 (Checkbox Column):**
- Custom checkbox painting with three states: Checked, Unchecked, PartiallyChecked
- Visual indicators: Blue filled square with white checkmark (Checked), Yellow filled square with black dash (PartiallyChecked), White square with gray border (Unchecked)
- Interactive handling via [`editorEvent()`](img_app/img_app/widgets/base_group_manager.py:385) for mouse and keyboard toggling

**Text Columns (1-6):**
- Background rendering using Qt style APIs for consistency
- Direct text drawing with explicit colors and font styling
- Proper text alignment and elision handling
- Focus indicator drawing with dotted border

### Visual States Handling
- **Group Headers**: Light gray background (#fafafa), bold dark text (#333333)
- **Child Items**: White background, dark text (#111111) for high contrast
- **Selection**: Blue background (#4a90e2), white text (bold for groups)
- **Focus**: Dotted border around selected item
- **Hover**: Uses Qt's native hover state rendering

### Key Helper Methods
The delegate coordinates painting through several specialized methods:
- [`_paint_text_cell()`](img_app/img_app/widgets/base_group_manager.py:351): Main painting coordinator for text columns
- [`_draw_cell_background()`](img_app/img_app/widgets/base_group_manager.py:238): Handles background rendering with proper visual states
- [`_draw_cell_text()`](img_app/img_app/widgets/base_group_manager.py:268): Manages text drawing with alignment and elision
- [`_draw_focus_indicator()`](img_app/img_app/widgets/base_group_manager.py:314): Draws focus rectangle when item has focus

### Benefits
- **Consistent Appearance**: Uniform look across Windows, macOS, and Linux
- **Enhanced Accessibility**: Clear visual feedback for all interaction states
- **Theme Resilience**: No dependency on system theme settings for core functionality
- **Performance**: Optimized painting without redundant text rendering

---
## UI Update — Similarity Manager Footer and Select Column (Minimal Fix)

Changes
- Footer: Added a QCheckBox labeled "Clear selections after delete" (default OFF)
  - Wiring in delete flow: [python.ImageSimilarityManagerDialog._on_delete_clicked()](img_app/img_app/widgets/duplicate_manager.py:869)
- Left pane "Select" column width enforced to avoid clipping of the custom indicator
  - Header min size + resize of column 0: [python.ImageSimilarityManagerDialog.__init__()](img_app/img_app/widgets/duplicate_manager.py:489)
- **Custom painting now handled by [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159)** instead of CheckboxDelegate
  - [`GroupTreeDelegate.paint()`](img_app/img_app/widgets/base_group_manager.py:180) handles all visual rendering
  - [`GroupTreeDelegate.editorEvent()`](img_app/img_app/widgets/base_group_manager.py:385) manages interaction
  - [`GroupTreeDelegate.sizeHint()`](img_app/img_app/widgets/base_group_manager.py:374) ensures proper sizing

UX Rationale
- Visibility: Prevents false perception that selections aren't applied
- Explicit clearing: Prevents surprising global clears; user opts in via checkbox
- Accessibility: Keyboard toggling via Space/Select
- **Consistent Rendering**: Custom painting ensures uniform appearance across themes

Acceptance
- The column remains wide enough for the indicator
- Toggling works on both mouse and keyboard, for group and child rows
- Delete behavior follows the footer option and preserves unrelated selections
- **Visual consistency maintained across different system themes**

Execution notes for this subtask
- Only append the sections above to the specified files
- Keep all filenames and language constructs as clickable references
- On completion, use attempt_completion to list the files updated and the titles of added sections; include a one-paragraph summary confirming that docs now reflect the minimal fix and forward plan
