# img_app — Initial Implementation Plan

This document defines the first steps to introduce a new top-level img_app within this repository, consistent with docs/add-app.md. The app is a development-only, extractable PySide6 desktop application that consumes pk-py-lib functionality. The plan focuses on documentation and scaffolding decisions prior to code creation.

## Objectives

- Establish img_app purpose, boundaries, and structure aligned with future extraction to a separate repository.
- Define invocation via PDM script pdm run imgapp with a stable callable entry point.
- Specify the initial main window (title, menus, centered placeholder) to guide the first coding milestone.
- Identify integration points with pk-py-lib to ensure shared functionality remains in the library.

## Directory Structure

Top-level sibling of src and showcase:

```
img_app/
  img_app/                  # Python package (extractable as-is)
    __init__.py
    app.py                  # QApplication bootstrap, main()
    main_window.py          # QMainWindow subclass (KDC Image Organizer)
    widgets/
      __init__.py
      central_placeholder.py  # Centered label placeholder content
  assets/
    icons/
  docs/
    README.md
  tests/
    __init__.py
    test_smoke.py
  py.typed
  __main__.py               # Optional: python -m img_app
```

Principles:
- Keep all UI-specific code inside img_app; reusable logic stays in pk-py-lib.
- No imports from img_app into pk-py-lib (one-way dependency).
- Tests and docs colocated for easy extraction and independent CI.

## Invocation and Entry Point

Define a PDM script in pyproject.toml:

```toml
[tool.pdm.scripts]
imgapp = {call = "img_app.img_app.app:main"}
```

This launches the application via:

```bash
pdm run imgapp
```

Optional module execution support via __main__.py:

```bash
python -m img_app
```

Entry point contract for img_app.img_app.app:main:
- Synchronous function with no args returning int exit code.
- Creates a single QApplication if not present.
- Instantiates and shows main window; executes event loop.

## Initial Main Window Specification (Milestone M0)

- Framework: PySide6 (Qt 6)
- Window: QMainWindow subclass
- Title: KDC Image Organizer
- Menu Bar:
  - File (no-op actions initially)
  - View (no-op actions initially)
  - Help (no-op actions initially)
- Central Widget:
  - Simple centered label: The KDC Image Organizer will go here
  - Encapsulated in widgets/central_placeholder.py for clean separation

Accessibility and UX considerations (future):
- Keyboard shortcuts for basic actions (Ctrl+Q etc.)
- Basic status bar for feedback/logging
- High-DPI support via Qt attributes

## Integration Points with pk-py-lib (Initial)

- Logging: use pk_py_lib.core.logging.logger when available to route app logs consistently.
- File system: leverage pk_py_lib.core.filesystem traversal and operations for future features.
- Widgets: reuse/compose pk-py-lib GUI widgets as they mature.

Guideline: Any reusable logic identified while prototyping should be migrated into pk-py-lib, then consumed by img_app.

## Testing Strategy (seed)

- tests/test_smoke.py launches QApplication in offscreen mode (QT_QPA_PLATFORM=offscreen when needed) and constructs QMainWindow to ensure the app boots without errors.
- Keep tests minimal in M0; expand with UI behaviors later (pytest-qt).

## Step-by-Step Tasks

1) Update architecture plan
- Document img_app purpose, structure, invocation, and boundaries. STATUS: Completed.

2) Create this add-app-plan document
- Capture structure, invocation, spec, and steps. STATUS: Completed.

3) Adjust pyproject.toml (planning only in this step)
- Add PDM script imgapp pointing to img_app.img_app.app:main.
- No code added yet; change will be implemented with scaffolding.

4) Scaffold directories and files (to be implemented next)
- Create top-level img_app/ with subpackage img_app/.
- Add __init__.py, app.py, main_window.py, widgets/__init__.py, widgets/central_placeholder.py.
- Add docs/README.md and tests/test_smoke.py.
- Add py.typed and optional __main__.py.

5) Implement minimal functionality (M0)
- app.py: create QApplication, show main window, return app.exec().
- main_window.py: implement title, menus, central placeholder widget.
- widgets/central_placeholder.py: centered QLabel in a simple layout.

6) Wire invocation
- Update pyproject.toml with PDM script.
- Validate pdm run imgapp boots the empty shell.

7) Validate and iterate
- Run smoke test locally (optionally with pytest-qt).
- Identify next vertical slice leveraging pk-py-lib components.

## Risk and Constraints

- Platform differences: ensure the app starts without requiring platform plugins in CI by supporting offscreen mode for tests.
- Dependency boundaries: avoid accidental imports from img_app into pk-py-lib to maintain library purity.
- Extraction readiness: keep relative imports and internal paths clean so the app can be moved to its own repo with unchanged package layout.

## Acceptance Criteria for M0

- Repository contains the img_app directory structure as specified.
- Running pdm run imgapp launches a PySide6 window titled KDC Image Organizer with File, View, Help menus and a centered placeholder label.
- test_smoke.py passes locally verifying basic app startup.
