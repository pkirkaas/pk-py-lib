# Requirements Traceability Matrix (RTM) — pk-py-lib / img_app

Purpose
- Provide a concise mapping from requirements/spec items to implementation files and tests.
- Help the single developer (and Roo) quickly find where a requirement is specified and where it is implemented or tested.
- The canonical ledger is [`docs/progress.md`](docs/progress.md:27). The machine-readable registry is [`docs/progress/features.json`](docs/progress/features.json:1).

How to use
- Update the machine registry (`docs/progress/features.json`) for machine-driven workflows, then run the generator [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1) to refresh human dashboards.
- For quick edits or to record ad-hoc mapping, update this RTM directly. Keep both in sync where practical.

RTM Table

| Requirement ID | Requirement summary | Spec refs | Code refs | Test refs | Status | Notes |
|---|---|---|---|---|---|---|
| `APP-001` | M0 app shell — basic app window, menus, placeholder | [`docs/add-app-plan.md`](docs/add-app-plan.md:67) | `img_app/img_app/app.py`, `img_app/img_app/main_window.py`, `src/pk_py_lib/gui/file_selector/widgets.py` | `img_app/tests/test_smoke.py` | in_progress | Main window now attempts to load MultiPathSelector; smoke test pending |
| `PROC-001` | Canonical threshold normalization — internal 0.0–1.0, UI 0–100% | [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:20), [`docs/roo/pr-unified-diff.md`](docs/roo/pr-unified-diff.md:29) | `src/pk_py_lib/core/utils` |  | planned | Conversion helper needed |
| `PROC-002` | pHash algorithm implementation | [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:56) | `src/pk_py_lib/core/image` | `tests/test_phash.py` | planned | Use imagehash or OpenCV |
| `DB-001` | Meta/schema_version table | [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:284) | `src/pk_py_lib/core/database` |  | planned | Add creation in DatabaseManager |
| `API-001` | ApiResponse + ErrorCodes canonicalization | [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:16) | `src/pk_py_lib/api` |  | planned | Create dataclass and enum |
| `LOG-001` | Logging panel integration | [`docs/gui-frame.md`](docs/gui-frame.md:3) | `src/pk_py_lib/core/logging/panel.py` |  | planned | Wire to GUI log viewer |
| `UI-001` | File selector widget demo | [`docs/gui-file-selector.md`](docs/gui-file-selector.md:1) | `src/pk_py_lib/gui/file_selector/widgets.py`, `showcase/gallery/file_selectors_demo.py` |  | planned | Create demo entry |
| `UI-002` | Results grouping & preview UI | [`docs/roo/img-app-ui-design.md`](docs/roo/img-app-ui-design.md:141) | `img_app/img_app/main_window.py` |  | planned | Prototype for M1 |
| `CACHE-001` | Thumbnail & cache management | [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:316) | `src/pk_py_lib/core/flat_cache` |  | planned | Implement FlatCacheManager example |
| `FS-001` | Move/rename detection (inode/device + hashing) | [`docs/roo/suggested-changes.md`](docs/roo/suggested-changes.md:15) | `src/pk_py_lib/core/filesystem/paths.py`, `src/pk_py_lib/core/filesystem/traversal.py` |  | planned | Design hashed-based identity |

Notes and conventions
- Spec refs should point to the canonical spec file and, if possible, include a heading or line reference for fast lookup.
- Status values align with the ledger: planned / in_progress / partial / done / blocked / deferred.
- Prefer updating the machine registry (`docs/progress/features.json`) and re-running the generator (`scripts/progress/generate_dashboard.py`) for consistent dashboards.

Change log
- 2025-08-14: Initial RTM created.
