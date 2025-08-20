# PR: Minimal canonicalization and low-risk doc edits

This patch applies the approved canonical changes to the specification and example code. Changes are minimal and low-risk — documentation and example code only.

Summary of changes:
- Canonical internal similarity threshold: 0.0–1.0 (UI displays 0–100%)
- Normalize default cache size to 5120 MB (≈5 GB) and adopt app_settings.cache_size_mb naming in examples; remove legacy max_size_gb/MAX_CACHE_SIZE_GB references
- Add DB meta/schema_version table and initial entry
- Annotate image metadata model with inode/device for rename detection
- Standardize ApiResponse to include machine-readable code field
- Add `ErrorCodes` enum to API specification
- Update small code examples (CacheManager, DEFAULT_SETTINGS) to use 5120 MB (≈5 GB) default

Files changed (high-level):
- [docs/img-app-spec.md](docs/img-app-spec.md:1) — Added Canonical Conventions note describing internal vs UI units.
- [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:16) — Standard ApiResponse updated, ErrorCodes enum added.
- [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1) — Added meta table and initial schema_version entry; cache policy constants now use MB (MAX_CACHE_SIZE_MB=5120).
- [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) — Examples updated to use cache_size_mb and max_size_mb.
- [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:663) — CacheManager.__init__ uses max_size_mb and AppSettings.cache_size_mb.

Detailed diffs (excerpted, not a full patch):

1) [`docs/roo/img-app-specification.md:20`](docs/roo/img-app-specification.md:20)
---- before ----
(no canonical conventions section)
---- after ----
Inserted:
```text
## Canonical Conventions

- Internal representation: similarity thresholds and scores are stored as floating-point values in the range 0.0 — 1.0 (inclusive). All persistent storage (databases, caches) record similarity values using this canonical range.
- User interface representation: thresholds and similarity scores are presented to users as percentages (0 — 100%). UI components convert between the internal 0.0—1.0 representation and the user-facing 0—100% representation transparently.
- Documentation convention: where a feature or UI element is described, percentages (0—100%) are used for readability. Where storage, APIs, or database schemas are described, the canonical 0.0—1.0 representation is used.
```

2) [`docs/roo/img-app-api-specifications.md:18`](docs/roo/img-app-api-specifications.md:18)
---- before ----
```python
@dataclass
class ApiResponse[T]:
    success: bool
    data: Optional[T]
    error: Optional[str]
    metadata: Dict[str, Any]
```
---- after ----
Replaced with:
```python
@dataclass
class ApiResponse(Generic[T]):
    success: bool
    data: Optional[T]
    error: Optional[str]
    code: Optional[str]
    metadata: Dict[str, Any]
```
Also added machine-readable error codes:
```python
class ErrorCodes(Enum):
    LOCKED_DB = "LOCKED_DB"
    FILE_MISSING = "FILE_MISSING"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CORRUPTED_IMAGE = "CORRUPTED_IMAGE"
    INVALID_CONFIG = "INVALID_CONFIG"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
```

3) [`docs/roo/img-app-data-model.md:284`](docs/roo/img-app-data-model.md:284)
---- before ----
(no meta table in settings schema)
---- after ----
Inserted:
```sql
-- Meta table for schema versioning and global metadata
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR REPLACE INTO meta (key, value, notes) VALUES ('schema_version', '1.0.0', 'Initial schema');
```

4) [`docs/roo/img-app-data-model.md:40`](docs/roo/img-app-data-model.md:40)
---- before ----
`file_hash: str                   # SHA-256 hash of file`
---- after ----
`file_hash: str                   # SHA-256 hash of file (hex)`

Inserted fields:
```text
file_inode: Optional[int]        # OS inode (where available) to help detect renames/moves
file_device: Optional[int]       # Device identifier for the filesystem (where available)
```

5) Cache defaults normalized to MB (excerpts):
- [docs/img-app-spec.md](docs/img-app-spec.md:1) — Thumbnail/cache default documented as 5120 MB (≈5 GB).
- [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:913) — CachePolicy.MAX_CACHE_SIZE_MB set to 5120.
- [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) — Examples use cache_size_mb and max_size_mb.
- [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:663) — CacheManager.__init__ uses max_size_mb and AppSettings.cache_size_mb.

6) [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:663)
---- after ----
```python
def __init__(self, cache_dir: Path, max_size_mb: int = 5120):
    self.max_size_bytes = int(max_size_mb * 1024 * 1024)
```

Notes & rationale:
- All edits are documentation and example-code only; no production library code beyond example snippets was changed.
- These edits harmonize internal representations, reduce default disk footprint for casual users, and add basic DB versioning and machine-readable error codes to support automated tooling and testing.

Next steps (recommended):
1. Create a git branch `docs/canonical-edits` and commit the modified files.
2. Run a repo-wide search for remaining references to '5GB' and '20.0' in code examples and docs; update as needed.
3. Add a tiny integration test to verify DB migration/meta table creation.
4. Optionally, update the `img_app` example code under `img_app/` to use the new `ImageData` fields when populating the cache.

If this summary looks correct I will:
- Commit these documentation changes to a new branch and produce a `.patch` file or branch for review.

Approve to proceed with creating the branch and patch now.