# KDC Image Organizer - UI/UX Design Document

## 1. Design Principles

### 1.1 Core Principles
- **Clarity**: Every element should have a clear purpose
- **Efficiency**: Minimize clicks and navigation for common tasks
- **Consistency**: Uniform design patterns throughout the application
- **Feedback**: Immediate visual feedback for all user actions
- **Flexibility**: Support both novice and power users
- **Accessibility**: Full keyboard navigation and screen reader support

### 1.2 Visual Hierarchy
- Primary actions: Prominent buttons with accent colors
- Secondary actions: Standard buttons with neutral colors
- Destructive actions: Red coloring with confirmation dialogs
- Information density: Progressive disclosure for complex features

## 2. Application Layout

### 2.1 Main Window Structure
```
┌──────────────────────────────────────────────────────────────┐
│ KDC Image Organizer                                    [_][□][X]│
├──────────────────────────────────────────────────────────────┤
│ File  Edit  View  Tools  Help                               │
├──────────────────────────────────────────────────────────────┤
│ [New Scan] [Open] [Save] | [Basic ▼] | [Settings] [Help]    │
├────────────┬─────────────────────────────┬──────────────────┤
│            │                             │                  │
│  Files     │      Results Area           │    Preview       │
│  Panel     │                             │    Panel         │
│            │                             │                  │
│ ┌────────┐ │  ┌─────────────────────┐   │ ┌──────────────┐ │
│ │□ Folder│ │  │■ Group 1 (5 images) │   │ │              │ │
│ │  □ img1│ │  │  □ DSC001.jpg      │   │ │   [Image]    │ │
│ │  □ img2│ │  │  □ DSC002.jpg      │   │ │              │ │
│ └────────┘ │  └─────────────────────┘   │ └──────────────┘ │
│            │                             │                  │
├────────────┴─────────────────────────────┴──────────────────┤
│ Ready | Files: 1,234 | Groups: 23 | Selected: 5 | ████ 45% │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Panel Specifications

#### 2.2.1 File Browser Panel (Left)
**Purpose**: File and folder selection for scanning

**Components**:
- Tab bar: "Single Set" | "Reference/Target Sets"
- Tree view with checkboxes
- Quick action buttons:
  - Add Files [+]
  - Add Folder [📁]
  - Remove Selected [−]
  - Clear All [🗑]
- Statistics display:
  - Total files selected
  - Total size
  - File type breakdown

**Interactions**:
- Drag and drop files/folders
- Right-click context menu
- Multi-select with Ctrl/Shift
- Space to toggle selection

#### 2.2.2 Results Panel (Center)
**Purpose**: Display similarity detection results

**Components**:
- Toolbar:
  - View mode selector: [Tree] [Grid] [List]
  - Sort dropdown: "By Similarity ▼"
  - Filter button: [Filter ⚙]
  - Export button: [Export 📤]
- Results tree/list:
  - Group headers with statistics
  - Individual file entries
  - Selection checkboxes
  - Action buttons per item

**Group Header Display**:
```
▼ Group 1 - 95% Similar (5 images, 25.3 MB total)
  □ IMG_001.jpg - 5.2 MB - 3024×4032 - 95% match
  □ IMG_001_copy.jpg - 5.2 MB - 3024×4032 - 100% match
  □ IMG_001_edited.jpg - 4.8 MB - 3024×4032 - 92% match
```

#### 2.2.3 Preview Panel (Right)
**Purpose**: Visual preview and comparison

**View Modes**:
1. **Single Preview**:
   - Large image display
   - Zoom controls: [−][Fit][1:1][+]
   - Image info overlay
   
2. **Comparison View**:
   - Side-by-side images
   - Synchronized zoom/pan
   - Difference highlight toggle
   
3. **Grid View**:
   - Thumbnail grid of group
   - Adjustable thumbnail size

**Controls**:
- View mode selector
- Zoom slider
- Full screen button
- Quick actions (rotate, delete, open)

### 2.3 Dialogs and Modals

#### 2.3.1 New Scan Dialog
```
┌─────────────────────────────────────────┐
│     Start New Similarity Scan           │
├─────────────────────────────────────────┤
│                                         │
│ Scan Mode:                              │
│ ○ Single Set (find duplicates within)   │
│ ● Two Sets (find matches between)       │
│                                         │
│ Algorithms:                             │
│ ☑ Perceptual Hash (pHash)              │
│ ☑ Histogram Comparison                  │
│ ☐ Feature Matching (slower)            │
│                                         │
│ Similarity Threshold: [====|----] 85%   │
│                                         │
│ ☐ Advanced Options ▼                    │
│                                         │
│        [Cancel]  [Start Scan]           │
└─────────────────────────────────────────┘
```

#### 2.3.2 Progress Dialog
```
┌─────────────────────────────────────────┐
│         Scanning for Duplicates         │
├─────────────────────────────────────────┤
│                                         │
│ Processing: IMG_2834.jpg                │
│                                         │
│ ████████████████░░░░░░░░░ 68%          │
│                                         │
│ Files: 823 / 1,210                     │
│ Groups found: 15                        │
│ Time elapsed: 00:02:34                 │
│ Time remaining: ~ 00:01:15              │
│                                         │
│ ☐ Close when complete                  │
│                                         │
│     [Run in Background]  [Cancel]       │
└─────────────────────────────────────────┘
```

## 3. User Workflows

### 3.1 Basic Duplicate Scan Workflow
1. **Launch**: User opens application
2. **Select**: Drag folder to file panel or click "Add Folder"
3. **Configure**: Click "New Scan" (uses default settings in basic mode)
4. **Process**: Progress dialog shows scanning
5. **Review**: Results appear in center panel
6. **Preview**: Click group to see preview
7. **Select**: Check files to delete
8. **Action**: Click "Delete Selected" with confirmation
9. **Complete**: Success notification

### 3.2 Advanced Comparison Workflow
1. **Mode Switch**: Toggle to "Advanced" mode
2. **Setup Reference**: Add reference images to first set
3. **Setup Target**: Add target images to second set
4. **Configure**: 
   - Select specific algorithms
   - Adjust threshold
   - Set processing options
5. **Execute**: Start comparison
6. **Filter Results**: Apply filters to narrow results
7. **Batch Operations**: Select multiple results for operation
8. **Export**: Export results to CSV/JSON

## 4. Visual Design Specifications

### 4.1 Color Palette

#### Light Theme
```css
--primary: #0066CC;        /* Primary actions */
--primary-hover: #0052A3;  /* Hover state */
--secondary: #6C757D;      /* Secondary actions */
--success: #28A745;        /* Success states */
--warning: #FFC107;        /* Warnings */
--danger: #DC3545;         /* Destructive actions */
--background: #FFFFFF;     /* Main background */
--surface: #F8F9FA;        /* Panel background */
--border: #DEE2E6;         /* Borders */
--text-primary: #212529;   /* Primary text */
--text-secondary: #6C757D; /* Secondary text */
```

#### Dark Theme
```css
--primary: #4A9EFF;        /* Primary actions */
--primary-hover: #3A8EEF;  /* Hover state */
--secondary: #8B959E;      /* Secondary actions */
--success: #3FB950;        /* Success states */
--warning: #D29922;        /* Warnings */
--danger: #F85149;         /* Destructive actions */
--background: #0D1117;     /* Main background */
--surface: #161B22;        /* Panel background */
--border: #30363D;         /* Borders */
--text-primary: #F0F6FC;   /* Primary text */
--text-secondary: #8B949E; /* Secondary text */
```

### 4.2 Typography
```css
/* Font Stack */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", 
             Roboto, "Helvetica Neue", Arial, sans-serif;

/* Font Sizes */
--font-size-h1: 24px;
--font-size-h2: 20px;
--font-size-h3: 16px;
--font-size-body: 14px;
--font-size-small: 12px;

/* Font Weights */
--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-bold: 600;
```

### 4.3 Spacing System
```css
/* Spacing Scale (4px base) */
--space-xs: 4px;
--space-sm: 8px;
--space-md: 16px;
--space-lg: 24px;
--space-xl: 32px;
--space-xxl: 48px;
```

### 4.4 Component Styling

#### Buttons
```css
/* Primary Button */
.btn-primary {
    background: var(--primary);
    color: white;
    padding: 8px 16px;
    border-radius: 4px;
    border: none;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

/* Danger Button */
.btn-danger {
    background: var(--danger);
    /* Additional styling with confirmation */
}
```

## 5. Interaction Design

### 5.1 Mouse Interactions
- **Hover**: Visual feedback on all interactive elements
- **Click**: Immediate response with visual confirmation
- **Drag**: Ghost image for drag operations
- **Right-click**: Context menus for quick actions
- **Double-click**: Open/expand actions

### 5.2 Keyboard Shortcuts
```
Global:
Ctrl+N          - New scan
Ctrl+O          - Open results
Ctrl+S          - Save results
Ctrl+Q          - Quit application
F1              - Help
F11             - Full screen

Navigation:
Tab             - Next element
Shift+Tab       - Previous element
Arrow Keys      - Navigate lists/trees
Enter           - Activate/expand
Space           - Toggle selection

View:
Ctrl+1          - Tree view
Ctrl+2          - Grid view
Ctrl+3          - List view
Ctrl+Plus       - Zoom in
Ctrl+Minus      - Zoom out
Ctrl+0          - Reset zoom

Selection:
Ctrl+A          - Select all
Ctrl+Shift+A    - Deselect all
Ctrl+Click      - Toggle selection
Shift+Click     - Range selection

Actions:
Delete          - Delete selected
Ctrl+Z          - Undo
Ctrl+Y          - Redo
```

### 5.3 Touch Gestures (Future)
- **Pinch**: Zoom in/out on images
- **Swipe**: Navigate between images
- **Long press**: Context menu
- **Two-finger scroll**: Pan large images

## 6. Responsive Behavior

### 6.1 Window Resizing
- **Minimum size**: 1024×768 pixels
- **Panel behavior**:
  - Collapsible below 1280px width
  - Stack vertically below 768px height
- **Toolbar adaptation**:
  - Icon-only mode below 1440px
  - Overflow menu for hidden items

### 6.2 High DPI Support
- Vector icons for all UI elements
- Scalable fonts with proper hinting
- Resolution-independent rendering
- Per-monitor DPI awareness

## 7. Accessibility Features

### 7.1 Screen Reader Support
- Semantic HTML structure
- ARIA labels for all controls
- Meaningful alt text for images
- Keyboard navigation announcements

### 7.2 Visual Accessibility
- High contrast mode support
- Configurable font sizes
- Color blind friendly palettes
- Focus indicators for keyboard navigation

### 7.3 Motor Accessibility
- Large click targets (minimum 44×44px)
- Keyboard alternatives for all actions
- Configurable double-click speed
- Sticky keys support

## 8. Animation and Transitions

### 8.1 Animation Principles
- **Purpose**: Animations should guide, not distract
- **Duration**: 200-300ms for most transitions
- **Easing**: Use ease-out for entrances, ease-in for exits

### 8.2 Common Animations
```css
/* Panel slide */
@keyframes slideIn {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
}

/* Fade */
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Progress */
@keyframes progress {
    from { width: 0%; }
    to { width: var(--progress); }
}
```

## 9. Error States and Feedback

### 9.1 Error Display
- **Inline errors**: Red text below fields
- **Toast notifications**: Temporary alerts
- **Modal dialogs**: Critical errors
- **Status bar**: Persistent warnings

### 9.2 Loading States
- **Skeleton screens**: For initial loads
- **Progress bars**: For determinate operations
- **Spinners**: For indeterminate operations
- **Subtle animations**: Keep UI responsive

### 9.3 Empty States
- **Helpful messaging**: Guide user to action
- **Visual interest**: Icons or illustrations
- **Clear CTAs**: What to do next

## 10. Platform-Specific Considerations

### 10.1 Windows
- Native title bar with system controls
- Windows snap support
- Jump list integration
- Native file dialogs

### 10.2 macOS
- Native menu bar
- Dock integration
- Full screen mode support
- Native notifications

### 10.3 Linux
- GTK/Qt theme integration
- Desktop environment compliance
- Standard freedesktop.org compliance
- Package manager integration

## 11. Mockup Descriptions

### 11.1 Main Application State - Initial
```
The application opens with an empty state showing:
- Welcome message in center panel
- "Get Started" guide with numbered steps
- Prominent "Add Files" or "Add Folder" buttons
- Sample workflow animation
```

### 11.2 Main Application State - Processing
```
During scanning:
- File panel shows selected files/folders
- Center panel displays real-time results as found
- Progress bar in status bar
- Non-blocking UI allows result preview
- Cancel button always accessible
```

### 11.3 Main Application State - Results
```
After scanning:
- Groups displayed hierarchically
- Color coding for similarity levels
- Preview panel shows selected group
- Action toolbar becomes active
- Statistics summary in status bar
```

## 12. User Testing Scenarios

### 12.1 First-Time User
1. Can user find how to add files?
2. Is the scan process intuitive?
3. Are results understandable?
4. Can user safely delete duplicates?

### 12.2 Power User
1. Can shortcuts speed up workflow?
2. Are batch operations efficient?
3. Is configuration accessible?
4. Can complex filters be applied?

### 12.3 Accessibility User
1. Is keyboard navigation complete?
2. Are screen readers supported?
3. Is contrast sufficient?
4. Are targets large enough?