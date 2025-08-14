# PR: Minimal canonicalization and low-risk doc edits

This patch applies the approved canonical changes to the specification and example code. Changes are minimal and low-risk — documentation and example code only.

Summary of changes:
- Canonical internal similarity threshold: 0.0–1.0 (UI displays 0–100%)
- Update default thumbnail/cache size from 20GB -> 5GB
- Add DB meta/schema_version table and initial entry
- Annotate image metadata model with inode/device for rename detection
- Standardize ApiResponse to include machine-readable code field
- Add `ErrorCodes` enum to API specification
- Update small code examples (CacheManager, DEFAULT_SETTINGS) to use 5GB default

Files changed (high-level):
- [`docs/roo/img-app-specification.md:20`](docs/roo/img-app-specification.md:20) — Added 'Canonical Conventions' note describing internal vs UI units.
- [`docs/roo/img-app-api-specifications.md:18`](docs/roo/img-app-api-specifications.md:18) — Standard `ApiResponse` updated, `ErrorCodes` enum added.
- [`docs/roo/img-app-data-model.md:284`](docs/roo/img-app-data-model.md:284) — Added `meta` table and initial schema_version entry.
- [`docs/roo/img-app-data-model.md:40`](docs/roo/img-app-data-model.md:40) — Added `file_inode` and `file_device` fields and clarified `file_hash`.
- [`docs/roo/img-app-data-model.md:551`](docs/roo/img-app-data-model.md:551) — CachePolicy.MAX_CACHE_SIZE_GB changed to 5.0.
- [`docs/roo/img-app-implementation-guide.md:739`](docs/roo/img-app-implementation-guide.md:739) — DEFAULT_SETTINGS `cache.max_size_gb` set to 5.0.
- [`docs/roo/img-app-implementation-guide.md:833`](docs/roo/img-app-implementation-guide.md:833) — CacheManager example default set to 5.0 and minor robustness edits.
- [`docs/create-spec.md:55`](docs/create-spec.md:55) — Default cache mention updated to 5GB.
- [`docs/roo/img-app-technical-architecture.md:263`](docs/roo/img-app-technical-architecture.md:263) — CacheManager __init__ default changed to 5.0.

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

5) Cache defaults changed to 5GB in multiple places (excerpts):
- [`docs/roo/img-app-specification.md:318`](docs/roo/img-app-specification.md:318) — Thumbnail cache default changed to 5GB.
- [`docs/roo/img-app-data-model.md:551`](docs/roo/img-app-data-model.md:551) — CachePolicy.MAX_CACHE_SIZE_GB set to 5.0.
- [`docs/roo/img-app-implementation-guide.md:739`](docs/roo/img-app-implementation-guide.md:739) — DEFAULT_SETTINGS `cache.max_size_gb` = 5.0
- [`docs/roo/img-app-implementation-guide.md:833`](docs/roo/img-app-implementation-guide.md:833) — CacheManager.__init__ default = 5.0
- [`docs/create-spec.md:55`](docs/create-spec.md:55) — initial/default size updated to 5GB

6) [`docs/roo/img-app-technical-architecture.md:263`](docs/roo/img-app-technical-architecture.md:263)
---- before ----
```python
def __init__(self, cache_dir: Path, max_size_gb: float = 20.0):
```
---- after ----
```python
def __init__(self, cache_dir: Path, max_size_gb: float = 5.0):
```

Notes & rationale:
- All edits are documentation and example-code only; no production library code beyond example snippets was changed.
- These edits harmonize internal representations, reduce default disk footprint for casual users, and add basic DB versioning and machine-readable error codes to support automated tooling and testing.

Next steps (recommended):
1. Create a git branch `docs/canonical-edits` and commit the modified files.
2. Run a repo-wide search for remaining references to '20GB' and '20.0' in code examples and docs; update as needed.
3. Add a tiny integration test to verify DB migration/meta table creation.
4. Optionally, update the `img_app` example code under `img_app/` to use the new `ImageData` fields when populating the cache.

If this summary looks correct I will:
- Commit these documentation changes to a new branch and produce a `.patch` file or branch for review.

Approve to proceed with creating the branch and patch now.