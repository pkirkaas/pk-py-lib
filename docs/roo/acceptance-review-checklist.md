# Settings Profiles v1 — Acceptance Review Checklist

Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A

Documents in scope

- [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)
- [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)
- [architecture-plan.md](architecture-plan.md)
- [docs/img-app-spec.md](docs/img-app-spec.md)

Global acceptance checklist

- [ ] JSON Schema present in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md) with defaults:
  - [ ] pools[*].include=["**/*"], exclude=[]
  - [ ] recurse=true, max_depth=0 (unlimited), include_hidden=false, follow_symlinks=false
  - [ ] filters.file_types default=[jpg, jpeg, png, webp, tiff, bmp, gif, heic, heif]
  - [ ] mode default="duplicates", duplicates.algorithm fixed "BLAKE3"
  - [ ] similarity.algorithm="pHash", similarity.degree=90
  - [ ] direction default="A_TO_B" (inactive until both pools valid)
  - [ ] single_pool_clustering=false
- [ ] Normalization rule documented: degree_ui 0–100 → degree_norm 0..1
- [ ] Package A documented: degree = round(100 * (1 - d/64)) and threshold rule degree ≥ threshold
- [ ] OS-aware behavior:
  - [ ] Path pattern case handling is OS-aware
  - [ ] File extension matching is case-insensitive
  - [ ] Hidden files excluded via file attribute (not just dot-prefix)
- [ ] Examples present:
  - [ ] Minimal single-pool duplicates
  - [ ] Minimal single-pool similarity
  - [ ] Two-pool duplicates
  - [ ] Two-pool similarity A→B
  - [ ] Two-pool "A without matches in B"
  - [ ] Fully explicit example
- [ ] Validation matrix present:
  - [ ] Duplicates vs similarity
  - [ ] One vs two pools
  - [ ] Direction gating requires both pools valid
  - [ ] Path validity checks
- [ ] UI design in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md):
  - [ ] Initial states per Set A
  - [ ] Progressive enable/disable logic
  - [ ] ASCII flow diagrams
  - [ ] Resolved configuration preview
- [ ] API specs in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md):
  - [ ] Profile endpoints with default-filling examples
  - [ ] Run outputs documented
  - [ ] Error conditions: invalid paths, degree out-of-range, invalid combinations, direction without both pools
- [ ] Technical architecture in [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md):
  - [ ] Centralized validator
  - [ ] Normalization utilities
  - [ ] Default resolution order
  - [ ] Capability flags
- [ ] Implementation guide in [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md):
  - [ ] Step-by-step plan
  - [ ] Tests list: degree rounding, OS case, extension case-insensitive, hidden attribute, direction gating, path gating
- [ ] Edge cases detailed in [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)
- [ ] Alignment docs updated with acceptance criteria: [architecture-plan.md](architecture-plan.md), [docs/img-app-spec.md](docs/img-app-spec.md)

Rubric — Data Model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Overview
  - [ ] JSON Schema
  - [ ] Defaults (including all required default values)
  - [ ] Normalization rule (degree_ui → degree_norm)
  - [ ] Examples (all required cases)
  - [ ] Validation matrix

Rubric — UI Design [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Initial states per Set A
  - [ ] Progressive enable/disable logic
  - [ ] ASCII flow diagrams
  - [ ] Resolved configuration preview

Rubric — API Specifications [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Profile endpoints with default-filling examples
  - [ ] Run outputs
  - [ ] Error conditions and responses
  - [ ] Request/response schemas

Rubric — Technical Architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Centralized validator
  - [ ] Normalization utilities
  - [ ] Default resolution order
  - [ ] Capability flags
  - [ ] Component interactions and data flow

Rubric — Implementation Guide [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Step-by-step plan
  - [ ] Tests list (degree rounding, OS case, extension case-insensitive, hidden attribute, direction gating, path gating)
  - [ ] Migration or integration notes (if applicable)

Rubric — Error Handling and Edge Cases [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Failure cases enumerated
  - [ ] Resolution guidance provided
  - [ ] Examples tied back to data model and API behavior

Rubric — Architecture Plan [architecture-plan.md](architecture-plan.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Updated alignment with acceptance criteria
  - [ ] Traceability to decisions and specifications

Rubric — Product Specification [docs/img-app-spec.md](docs/img-app-spec.md)

- [ ] Conformance to Option A
- [ ] Conformance to Balanced Defaults
- [ ] Conformance to Package A
- [ ] Conformance to Set A
- [ ] Terminology consistency (Pool A/B, Mode, Degree, Direction, single_pool_clustering)
- [ ] Clickable filename references used throughout
- [ ] Required sections present and complete:
  - [ ] Acceptance criteria reflected
  - [ ] Cross-references to all relevant design docs

Sign-off Record

| Document | Reviewer | Date (ISO 8601) | Result (Pass/Fail) | Notes |
|---|---|---|---|---|
| [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md) |  |  |  |  |
| [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md) |  |  |  |  |
| [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md) |  |  |  |  |
| [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md) |  |  |  |  |
| [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md) |  |  |  |  |
| [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md) |  |  |  |  |
| [architecture-plan.md](architecture-plan.md) |  |  |  |  |
| [docs/img-app-spec.md](docs/img-app-spec.md) |  |  |  |  |