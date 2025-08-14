# Canonical Decisions — KDC Image Organizer

Purpose

This document records the canonical decisions agreed for the KDC Image Organizer project to remove cross-document ambiguity and provide a single source of truth for implementation work by Roo and developers.

Scope

- Applies to threshold units, cache & thumbnail storage, file identity detection (move/rename), API shapes, DB schema versioning, telemetry policy, and benchmark harness.
- Update references: see implementation/action items below.

1) Similarity thresholds (canonical)

- Internal canonical representation: floating-point values in the inclusive range 0.0 — 1.0.
- User interface representation: percentages (0 — 100%). UI components MUST convert at the boundary.
- Conversion helpers (to implement): 
  - `ui_percent_to_internal(pct: float) -> float`
  - `internal_to_ui_percent(value: float) -> float`
- Reference: [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:20)
- Implementation target: [`src/pk_py_lib/core/utils/thresholds.py`](src/pk_py_lib/core/utils/thresholds.py:1)

2) Cache & Thumbnails (canonical)

- Default thumbnail/cache size: 5.0 GB (config key: `cache.max_size_gb`).
- Per-OS recommended default cache directories (implementation should derive via standard platform APIs):
  - Windows: Path.home() / "AppData" / "Local" / "KDC Image Organizer" / "cache"
  - macOS: Path.home() / "Library" / "Application Support" / "KDC Image Organizer" / "cache"
  - Linux: Path.home() / ".local" / "share" / "kdc-image-organizer" / "cache"
- Thumbnail storage policy (canonical decision): store thumbnails as files on disk (file-backed cache) under:
  `cache/thumbnails/{size}/{cache_key}.jpg` (example path). The database stores metadata and the relative path to the thumbnail.
- Default thumbnail encoding: JPEG, quality=85, configurable.
- Eviction policy: LRU with a cleanup trigger at 90% of max_size.
- Implementation target (example): [`src/pk_py_lib/core/cache.py`](src/pk_py_lib/core/cache.py:1) and examples in [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1).

3) File identity and move/rename detection (canonical)

- Default mode: "robust" (config key `filesystem.identity.mode = "robust"`).
- Robust algorithm (ordered checks):
  1. Where supported, capture (device, inode) pair at initial discovery and store in DB (`file_device`, `file_inode`).
  2. Compute and store SHA-256 content hash (hex string) for every indexed file.
  3. On file disappearance, search the cache DB for matching SHA-256; if found, treat as same file at new path (record path-history).
  4. If hash not found, but inode/device matches an existing entry on the same device, treat as move/rename.
  5. If none match, treat as new file.
- Configurable option "simple": do not compute persistent content hashes automatically; moved/renamed files are treated as new.
- Implementation target: [`src/pk_py_lib/core/filesystem/identity.py`](src/pk_py_lib/core/filesystem/identity.py:1) and integration points in [`src/pk_py_lib/core/filesystem/traversal.py`](src/pk_py_lib/core/filesystem/traversal.py:1).
- Reference: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:40)

4) API canonicalization: ApiResponse & ErrorCodes

- Canonical `ApiResponse` dataclass fields:
  - `success: bool`
  - `data: Optional[T]`
  - `error: Optional[str]` (human message)
  - `code: Optional[str]` (machine-readable error code)
  - `metadata: Dict[str, Any]`
- Canonical `ErrorCodes` enum values:
  - LOCKED_DB, FILE_MISSING, OUT_OF_MEMORY, PERMISSION_DENIED, CORRUPTED_IMAGE, INVALID_CONFIG, NETWORK_ERROR, TIMEOUT, UNKNOWN_ERROR
- Implementation target: [`src/pk_py_lib/api/__init__.py`](src/pk_py_lib/api/__init__.py:1)
- Reference: [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:18)

5) Threshold helper APIs (canonical)

- Public helper names and signatures:
  - `def ui_percent_to_internal(pct: float) -> float:`
  - `def internal_to_ui_percent(value: float) -> float:`
- Behavior: clamp and validate inputs; raise ValueError on invalid values.
- Implementation target: [`src/pk_py_lib/core/utils/thresholds.py`](src/pk_py_lib/core/utils/thresholds.py:1)

6) DB schema versioning and `meta` table

- The settings DB MUST contain a `meta` table with at least `schema_version` key on creation.
- On DatabaseManager initialization, create the `meta` table if missing and insert `schema_version = '1.0.0'`.
- Provide a `SchemaManager` helper to manage migrations; include `backup_before_migration()` and rollback guidance.
- Implementation touchpoints: DB create scripts and [`img_app/img_app/data/database.py`](img_app/img_app/data/database.py:1) or library DB helper.
- Reference: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:284)

7) Thumbnail format and quality

- Default thumbnail format: JPEG with quality 85 for performance/size trade-off.
- Allow override per user profile.

8) Telemetry and privacy

- No telemetry or crash-reporting in Phase 1. The application must operate fully offline by default.
- If telemetry/log upload is added later, it MUST be opt-in and documented; prefer plugin extension approach.

9) RAW format support

- RAW support is deferred to Phase 2 (not required in M0/M1).

10) Benchmarks and performance harness

- Provide a simple benchmark harness that measures images/sec for a given algorithm and thumbnail size.
- Implementation target: `tools/benchmarks/bench_images.py` and documented in [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)

11) Sample JSON payloads for API tests

- Create canonical sample payload files:
  - [`docs/roo/samples/scan_session.json`](docs/roo/samples/scan_session.json:1)
  - [`docs/roo/samples/scan_result.json`](docs/roo/samples/scan_result.json:1)
- These are required for contract tests and examples.

12) Developer action items (short list)

- Implement `ApiResponse` + `ErrorCodes` in [`src/pk_py_lib/api/__init__.py`](src/pk_py_lib/api/__init__.py:1)
- Add threshold helpers [`src/pk_py_lib/core/utils/thresholds.py`](src/pk_py_lib/core/utils/thresholds.py:1)
- Implement file-backed `CacheManager` [`src/pk_py_lib/core/cache.py`](src/pk_py_lib/core/cache.py:1)
- Implement file identity detection module [`src/pk_py_lib/core/filesystem/identity.py`](src/pk_py_lib/core/filesystem/identity.py:1)
- Ensure DB `meta` creation in DB init (integration test)
- Add sample payloads and benchmark harness; add unit/integration tests

13) Change control and acceptance

- Update the canonical decisions file and then propagate references into the spec docs and implementation guide. After code changes are implemented, update the progress ledger (`docs/progress.md` and `docs/progress/features.json`) and run `scripts/progress/generate_dashboard.py` to refresh the dashboard.

References (selected)

- Specification: [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:20)
- Data model: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1)
- API spec: [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1)
- Implementation guide: [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)

Author: Roo (AI coding assistant)
Date: 2025-08-14

End of canonical decisions.