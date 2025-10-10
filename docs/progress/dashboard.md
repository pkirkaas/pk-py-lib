# Progress Dashboard

Generated: 2025-08-14T17:43:52.453350Z

## Summary
- Planned: 9
- In_progress: 0
- Partial: 1
- Done: 0
- Blocked: 0
- Deferred: 0

## Items

| ID | Title | Status | Next step | Last updated | Specs | Code |
|---|---|---|---|---|---|---|
| `APP-001` | M0 app shell | in_progress | Start img_app with MultiPathSelector as central widget and run smoke test | 2025-08-15 | [`add-app-plan.md`](docs/add-app-plan.md) | [`app.py`](img_app/img_app/app.py), [`main_window.py`](img_app/img_app/main_window.py), [`widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py) |
| `PROC-001` | Canonical threshold normalization | planned | Add conversion helper in pk_py_lib and document UI conversion | 2025-08-14 | [`img-app-specification.md`](docs/roo/img-app-specification.md), [`pr-unified-diff.md`](docs/roo/pr-unified-diff.md) |  |
| `PROC-002` | Perceptual hash (pHash) algorithm implementation | planned | Implement pHash wrapper and add unit tests in src/pk_py_lib/core/image | 2025-08-14 | [`img-app-specification.md`](docs/roo/img-app-specification.md) | [`image`](src/pk_py_lib/core/image) |
| `DB-001` | Meta/schema_version table | planned | Implement meta table creation in DatabaseManager | 2025-08-14 | [`img-app-data-model.md`](docs/roo/img-app-data-model.md) |  |
| `API-001` | ApiResponse and ErrorCodes canonicalization | planned | Implement ApiResponse dataclass and ErrorCodes enum in pk_py_lib.api | 2025-08-14 | [`img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md) |  |
| `LOG-001` | Logging panel integration | planned | Design log viewer widget and use pk_py_lib.core.logging.panel | 2025-08-14 | [`gui-frame.md`](docs/gui-frame.md) | [`panel.py`](src/pk_py_lib/core/logging/panel.py) |
| `UI-001` | File selector widget demo | planned | Create showcase demo using FileSelector widget | 2025-08-14 | [`gui-file-selector.md`](docs/gui-file-selector.md) | [`widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py), [`file_selectors_demo.py`](showcase/gallery/file_selectors_demo.py) |
| `UI-002` | Results grouping & preview UI | planned | Prototype Results panel showing groups and previews in img_app main window | 2025-08-14 | [`img-app-specification.md`](docs/roo/img-app-specification.md), [`img-app-ui-design.md`](docs/roo/img-app-ui-design.md) | [`main_window.py`](img_app/img_app/main_window.py) |
| `CACHE-001` | Thumbnail & cache management | planned | Implement FlatCacheManager defaults and LRU eviction example in pk_py_lib.core.flat_cache | 2025-08-14 | [`img-app-data-model.md`](docs/roo/img-app-data-model.md), [`img-app-specification.md`](docs/roo/img-app-specification.md) |  |
| `FS-001` | Move/rename detection (inode/device + hashing) | planned | Add file identity strategy using file_hash with optional inode/device fallback | 2025-08-14 | [`suggested-changes.md`](docs/roo/suggested-changes.md), [`img-app-data-model.md`](docs/roo/img-app-data-model.md) | [`paths.py`](src/pk_py_lib/core/filesystem/paths.py), [`traversal.py`](src/pk_py_lib/core/filesystem/traversal.py) |
