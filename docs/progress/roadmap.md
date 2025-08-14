# Progress Roadmap — pk-py-lib / img_app

This roadmap lists high-level milestones, acceptance criteria, and primary tasks.
The canonical ledger is maintained in [`docs/progress.md`](docs/progress.md:1).
The machine-readable registry is located at [`docs/progress/features.json`](docs/progress/features.json:1).

Current milestone — M0: App Shell
Acceptance criteria:
- Repository contains the img_app directory structure as specified in [`docs/add-app-plan.md`](docs/add-app-plan.md:67).
- Running pdm run imgapp launches a PySide6 window titled KDC Image Organizer with File, View, Help menus.
- test_smoke.py passes locally verifying basic app startup.

Tasks (M0):
- Wire PDM script and verify entry point in [`pyproject.toml`](pyproject.toml:1).
- Run smoke test (pytest) in offscreen mode (CI-friendly).
- Record acceptance in the canonical ledger [`docs/progress.md`](docs/progress.md:1) once tests pass.

Milestone M1 — Basic Duplicate Detection & UI
Goals:
- Implement pHash algorithm wrapper and basic similarity pipeline.
- Results grouping UI prototype (hierarchical groups + preview).
- Thumbnail cache and LRU eviction example.
Acceptance criteria:
- pHash function exposed under `src/pk_py_lib/core/image`.
- A simple Results panel in the app showing groups and previews.
- Thumbnail cache example and documentation.

Milestone M2 — Advanced Features
Goals:
- Multiple algorithms and algorithm presets.
- Batch processing, undo system, and profile management.
- Performance benchmarks and CI regression tests.

Future and Stretch Goals:
- RAW format support (Phase 2), plugin architecture, AI features.

How to use this roadmap
- Update the canonical ledger [`docs/progress.md`](docs/progress.md:1) for status changes; the YAML ledger is authoritative.
- Optionally keep the machine registry [`docs/progress/features.json`](docs/progress/features.json:1) in sync; run the generator at [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1) to produce a readable dashboard.
- Update cadence: weekly refresh recommended; add a short note to the ledger `notes` field with the date.

Contact and ownership
- Owner: single developer (repository author). For decisions that require tradeoffs, record notes in [`docs/roo/suggested-changes.md`](docs/roo/suggested-changes.md:1).