# Project Progress — pk-py-lib / img_app

This file is the canonical progress ledger for the repo. The YAML ledger between the anchors <!-- progress-ledger:start --> and <!-- progress-ledger:end --> is the authoritative, machine-editable source of truth used by the Roo agent and other automation. Human-readable summary above is optional; if it drifts the YAML is authoritative.

Quick Status (auto-generated summary - recompute as needed)
- Planned: 4
- In Progress: 0
- Partial: 1
- Done: 0
- Blocked: 0
- Deferred: 0

Current Focus
- M0 app shell — see [`docs/add-app-plan.md`](docs/add-app-plan.md:67)

Recently completed
- None yet

Blockers
- None recorded

How Roo updates this file
- Edit only the YAML ledger section between the anchors. Do not edit anchors.
- Fields: id, title, status, next_step, spec_refs, code_refs, test_refs, acceptance, risk, last_updated, notes
- Status values: planned, in_progress, partial, done, blocked, deferred

<!-- progress-ledger:start -->
- id: APP-001
  title: M0 app shell
  status: partial
  next_step: Wire pdm run imgapp to app entry and run smoke test
  spec_refs:
    - docs/add-app-plan.md
  code_refs:
    - img_app/img_app/app.py
    - img_app/img_app/main_window.py
  test_refs:
    - img_app/tests/test_smoke.py
  acceptance:
    - Window titled KDC Image Organizer shows
    - Menus File, View, Help exist
    - Placeholder label visible
  risk: low
  last_updated: 2025-08-14
  notes: Scaffold exists under img_app/; smoke test pending

- id: PROC-001
  title: Canonical threshold normalization
  status: planned
  next_step: Add conversion helper in pk_py_lib and document UI conversion
  spec_refs:
    - docs/roo/img-app-specification.md
    - docs/roo/pr-unified-diff.md
  code_refs: []
  test_refs: []
  acceptance:
    - Docs state 0.0–1.0 internal and 0–100% UI
    - Helper function converts both ways and is used by UI
  risk: low
  last_updated: 2025-08-14
  notes: Waiting on final decision for UI components

- id: PROC-002
  title: Perceptual hash (pHash) algorithm implementation
  status: planned
  next_step: Implement pHash wrapper and add unit tests in src/pk_py_lib/core/image
  spec_refs:
    - docs/roo/img-app-specification.md
  code_refs:
    - src/pk_py_lib/core/image
  test_refs: []
  acceptance:
    - pHash computation available as a function
    - Unit tests validate identical and modified images
  risk: medium
  last_updated: 2025-08-14
  notes: Use imagehash or OpenCV implementation

- id: DB-001
  title: Meta/schema_version table
  status: planned
  next_step: Implement meta table creation in DatabaseManager
  spec_refs:
    - docs/roo/img-app-data-model.md
  code_refs: []
  test_refs: []
  acceptance:
    - meta table exists in settings.db with schema_version entry
  risk: low
  last_updated: 2025-08-14
  notes: Schema SQL block present in data model docs

- id: API-001
  title: ApiResponse and ErrorCodes canonicalization
  status: planned
  next_step: Implement ApiResponse dataclass and ErrorCodes enum in pk_py_lib.api
  spec_refs:
    - docs/roo/img-app-api-specifications.md
  code_refs: []
  test_refs: []
  acceptance:
    - ApiResponse structure available to code, used by core APIs
  risk: low
  last_updated: 2025-08-14
  notes: PR unified diff includes desired shape

- id: LOG-001
  title: Logging panel integration
  status: planned
  next_step: Design log viewer widget and use pk_py_lib.core.logging.panel
  spec_refs:
    - docs/gui-frame.md
  code_refs:
    - src/pk_py_lib/core/logging/panel.py
  test_refs: []
  acceptance:
    - In-app log viewer shows logs from pk_py_lib logging outputs
  risk: medium
  last_updated: 2025-08-14
  notes: panel exists in library; widget integration needed

- id: UI-001
  title: File selector widget demo
  status: planned
  next_step: Create showcase demo using FileSelector widget
  spec_refs:
    - docs/gui-file-selector.md
  code_refs:
    - src/pk_py_lib/gui/file_selector/widgets.py
    - showcase/gallery/file_selectors_demo.py
  test_refs: []
  acceptance:
    - Demo runs and shows file selection UI
  risk: low
  last_updated: 2025-08-14
  notes: Showcase exists; needs wiring

- id: UI-002
  title: Results grouping & preview UI
  status: planned
  next_step: Prototype Results panel showing groups and previews in img_app main window
  spec_refs:
    - docs/roo/img-app-specification.md
    - docs/roo/img-app-ui-design.md
  code_refs:
    - img_app/img_app/main_window.py
  test_refs: []
  acceptance:
    - Groups displayed hierarchically with preview panel and basic sorting
  risk: medium
  last_updated: 2025-08-14
  notes: Early prototype acceptable for M1

- id: CACHE-001
  title: Thumbnail & cache management
  status: planned
  next_step: Implement CacheManager defaults and LRU eviction example in pk_py_lib.core.cache
  spec_refs:
    - docs/roo/img-app-data-model.md
    - docs/roo/img-app-specification.md
  code_refs: []
  test_refs: []
  acceptance:
    - Thumbnail cache policy documented and a small example exists
  risk: medium
  last_updated: 2025-08-14
  notes: Default 5120 MB policy in docs (≈5 GB); implementation TBD

- id: FS-001
  title: Move/rename detection (inode/device + hashing)
  status: planned
  next_step: Add file identity strategy using file_hash with optional inode/device fallback
  spec_refs:
    - docs/roo/suggested-changes.md
    - docs/roo/img-app-data-model.md
  code_refs:
    - src/pk_py_lib/core/filesystem/paths.py
    - src/pk_py_lib/core/filesystem/traversal.py
  test_refs: []
  acceptance:
    - Renamed/moved files detected via hash and inode where available
  risk: medium
  last_updated: 2025-08-14
  notes: Trade-offs documented in suggested-changes
<!-- progress-ledger:end -->

Notes:
- The YAML ledger is authoritative. Minor human summaries may be updated but do not replace the ledger.
- To add new items, append a YAML object before the <!-- progress-ledger:end --> anchor.