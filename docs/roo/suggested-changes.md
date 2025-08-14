# Suggested Changes — KDC Image Organizer specification review

Overview:
This document records suggested corrections, clarifications, and enhancements after a full review of the conversation, the project, and the specification documents.

Reviewed sources:
- [`docs/create-spec.md`](docs/create-spec.md:1)
- [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:1)
- [`docs/roo/img-app-technical-architecture.md`](docs/roo/img-app-technical-architecture.md:1)
- [`docs/roo/img-app-ui-design.md`](docs/roo/img-app-ui-design.md:1)
- [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1)
- [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1)
- [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)
- [`docs/roo/img-app-error-handling-edge-cases.md`](docs/roo/img-app-error-handling-edge-cases.md:1)
- Key code references: [`pyproject.toml`](pyproject.toml:1), [`src/pk_py_lib/gui/file_selector/widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py:1), [`img_app/img_app/app.py`](img_app/img_app/app.py:1), [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py:1)

Scope and intent:
- Produce an actionable prioritized list of suggested edits and clarifications.
- Record cross-document inconsistencies and propose canonical decisions (to be applied if you approve).

High-priority issues (must-address before implementation):
1. Similarity threshold unit inconsistency: UI text uses 0–100% while APIs and some docs use 0.0–1.0. Pick canonical internal representation (recommend 0.0–1.0) and convert at UI boundaries.
2. Database schema versioning: schemas lack a guaranteed single-source schema_version table. Add `meta`/`schema_version` table and migration history.
3. File move/rename handling: docs treat moved/renamed files as new; suggest adding strategies to detect renames (inode/device where available, SHA-256 content hash, and path history) and document behavior.
4. Cache defaults and platform locations: 20GB default may be excessive on many laptops. Recommend lower default (5GB) with clear per-OS paths and fallback when lacking space.
5. Performance metrics are underspecified (e.g., "1,000 images/min"). Define benchmark harness, sample hardware profiles, and exact algorithm/thumbnail sizes used for measurement.

Issues and suggested edits by document
1) [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:1)
- Inconsistency: threshold units. Suggest add canonical note: "internal threshold: 0.0–1.0; UI shows 0–100%."
- Clarify overall_score composition when multiple algorithms are selected (weighted average? minimum? boolean composition?). Add explicit aggregation formula and default weights.
- Define behavior for images present in both reference and target sets (priority, dedupe rules).
- Add a sample JSON payload for a scan session and a scan result to support API consumers and tests.

2) [`docs/roo/img-app-technical-architecture.md`](docs/roo/img-app-technical-architecture.md:1)
- Threading clarity: map CPU-bound operations (e.g., SIFT/feature matching) to process pool vs I/O operations to thread pool. Recommend default process pool for heavy compute algorithms.
- Database access model: propose a dedicated DB worker with WAL; document short transaction practice and retry/backoff for locks.
- Add explicit memory budget parameters and automatic thread scaling when memory is constrained.

3) [`docs/roo/img-app-ui-design.md`](docs/roo/img-app-ui-design.md:1)
- Add wireframe assets and propose standard filenames for Qt Designer forms (e.g., `ui/main_window.ui`).
- Standardize keyboard shortcut list vs documented API keys; include a localization conflict resolution note.
- Clarify exact differences between "Basic" and "Advanced" modes, and list which UI elements/presets are toggled.

4) [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1)
- Add `meta` table for `schema_version` and migration history.
- Consider adding `device_id` and `inode` fields (where available) to `image_metadata` to help detect renames/moves; document Windows fallback strategy.
- Clarify thumbnail storage: compressed JPEG blobs vs store-as-files referenced by path (trade-offs: DB size vs filesystem maintenance).

5) [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1)
- Standardize `ApiResponse` shape and add `code` field for machine-readable errors.
- Explicitly provide async and sync variants in the API reference and document expected concurrency semantics.
- Define a canonical `ErrorCodes` enum for common failures (LOCKED_DB, FILE_MISSING, OOM, PERMISSION_DENIED, CORRUPTED_IMAGE).

6) [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)
- Update recommended default cache size to align with suggested change (5GB) and document per-OS default cache paths.
- Add reproducible benchmark scripts and instructions to run them; include sample expected results for CI regression tests.
- Add instructions for applying DB migrations and rolling back safely.

7) [`docs/roo/img-app-error-handling-edge-cases.md`](docs/roo/img-app-error-handling-edge-cases.md:1)
- Add automated backup policy for `settings.db` and `cache.db` and retention policy (e.g., weekly snapshots, retain 30 days).
- Add "safe mode" startup flag that disables cache writes and destructive operations for incident analysis.
- Ensure recovery flows include verification steps (after restore, run integrity checks and sample re-hashes).

Cross-document consistency items (canonical decisions I propose)
- Similarity thresholds: canonical internal range 0.0–1.0; UI slider 0–100%; APIs accept 0.0–1.0 (UI adapters convert).
- Similarity score storage: store floats 0.0–1.0 in DB; present percentages in UI.
- Default cache size: set to 5GB (configurable per profile); document recommendation to raise to 20GB for heavy users.
- Threading defaults: default thread pool = min(4, cpu_count() - 1); allow profile override.
- DB schema: add table `meta(schema_version TEXT, created_at TIMESTAMP, notes TEXT)` and include migration tooling.

Suggested implementation changes (small actionable edits)
- Add `meta` table creation to [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1) SQL blocks and to the `DatabaseManager.create_databases()` snippet in [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1).
- Update all docs that mention thresholds to state the canonical internal unit (0.0–1.0) and show UI conversion.
- Add explicit `ErrorCodes` enum to [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1).
- Add note in [`pyproject.toml`](pyproject.toml:1) that `pillow-heif` is optional and may require system-level dependencies; include install notes per OS.

Clarifying questions (please answer to finalize suggested changes)
1. Canonical threshold unit: confirm you approve internal 0.0–1.0 and UI 0–100% visual representation? (recommended)
2. Default cache size: prefer 5GB (safer) or keep 20GB as initial default?
3. File move/rename detection: do you want robust move detection (store content SHA-256 + optional device/inode tracking) or a simpler approach (treat as new)? Robust detection increases DB and compute cost.
4. Telemetry/analytics: should we include optional opt-in telemetry for crash reports (disabled by default)? Current security doc says no telemetry.
5. RAW support: you previously deferred RAW formats. Confirm RAW support remains Phase 2 and not required for initial release.

Prioritized next steps (recommended)
1. Accept canonical decisions in "Cross-document consistency".
2. Implement small edits: threshold normalization, add `meta` schema, add `ErrorCodes` enum, adjust default cache size.
3. Add benchmark scripts and update implementation guide.
4. Add UI mock files and `ui/` filenames for Qt Designer.
5. Run CI tests for SQL migrations and API contract tests.

Acceptance criteria before implementation start
- All docs in [`docs/`](docs/create-spec.md:1) and [`docs/roo/`](docs/roo/img-app-specification.md:1) reflect canonical threshold units and DB versioning.
- `pyproject.toml` contains clear optional dependency notes for native codecs.
- A short benchmark harness example (script) exists in repo and is referenced in the implementation guide.

If you confirm the clarifying questions, I will prepare a minimal PR-style patch that implements the low-risk edits (meta table SQL, threshold notes, `ErrorCodes` enum, and cache default change) and present the changes for approval.

End of suggested changes.