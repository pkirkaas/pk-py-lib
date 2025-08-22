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
  - Path input field with browse button (opens directory selector)
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
1. **Pool A Path**: Must be specified and valid
2. **Pool B Path**: Required only for two-pool scope, must be valid if specified
3. **Name**: Must be unique and meet pattern requirements
4. **Mode-specific validation**: 
   - Duplicates mode: No degree allowed
   - Similarity mode: Degree required (0-100)

#### Path Selection
- Browse buttons open directory selector dialog
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
