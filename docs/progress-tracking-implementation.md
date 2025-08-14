# Progress Tracking Implementation Guide

Purpose

This document explains in detail the progress-tracking approach implemented in this repository. It is intended to be dropped into a new project so that Roo (an AI coding assistant) or a human developer can initialize, maintain, and operate the progress-tracking system with minimal ceremony.

Goals & Principles

- Simple, single-developer workflow.
- Machine-friendly and AI-maintainable.
- Minimal files to edit; deterministic anchors for safe programmatic updates.
- Traceability from spec → implementation → tests.

Core files created by this approach

- Canonical ledger (human + machine-editable): [`docs/progress.md`](docs/progress.md:1)
- Machine registry (optional / automation): [`docs/progress/features.json`](docs/progress/features.json:1)
- Dashboard generator script: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
- Generated dashboard (human-readable): [`docs/progress/dashboard.md`](docs/progress/dashboard.md:1)
- Roadmap: [`docs/progress/roadmap.md`](docs/progress/roadmap.md:1)
- Traceability matrix: [`docs/progress/traceability.md`](docs/progress/traceability.md:1)
- Feature template: [`docs/progress/templates/feature.md`](docs/progress/templates/feature.md:1)
- (Optional CI workflow): [`.github/workflows/progress.yml`](.github/workflows/progress.yml:1)

Design overview

The system uses a single source of truth for project progress: the YAML ledger embedded in [`docs/progress.md`](docs/progress.md:1) between the explicit anchors:

- `<!-- progress-ledger:start -->`
- `<!-- progress-ledger:end -->`

An AI agent (Roo) or a human edits only the YAML block between those anchors. This restriction prevents accidental edits to the surrounding prose and keeps diffs stable.

For machine automation, the project also includes a machine-readable registry at [`docs/progress/features.json`](docs/progress/features.json:1). The registry is a convenience for scripts and CI. The recommended maintenance pattern is ledger-first: update the YAML block in [`docs/progress.md`](docs/progress.md:1), then update the registry (either manually or via a small sync script), then run the dashboard generator.

Canonical ledger format (in [`docs/progress.md`](docs/progress.md:1))

- Top area: free-form human summary (counts by status, current focus, blockers).
- The YAML ledger between anchors is the authoritative structured data for features.

Ledger YAML schema (fields)

- id: string — stable identifier (prefix + 3-digit number, e.g. APP-001, DB-001)
- title: string — short title
- status: string — one of: planned, in_progress, partial, done, blocked, deferred
- next_step: string — concise next action
- spec_refs: array[string] — relative paths to specification docs
- code_refs: array[string] — relative paths to implementation files or directories
- test_refs: array[string] — relative paths to tests
- acceptance: array[string] — concrete acceptance criteria; all must be satisfied to mark done
- risk: string — low / medium / high
- last_updated: date string — YYYY-MM-DD
- notes: string (optional) — freeform notes, blockers, discussion points

Example YAML ledger entry (exact format)

```yaml
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
  risk: low
  last_updated: 2025-08-14
  notes: Scaffold exists under img_app/; smoke test pending
```

ID naming and prefixes

- Prefix convention (recommended):
  - APP — application / entry points
  - API — API / contract changes
  - DB — database / schema / migration items
  - PROC — processing / algorithms
  - UI — UI / widgets
  - FS — filesystem / traversal
  - CACHE — cache / storage
  - LOG — logging / diagnostics

- Numeric suffix: start at 001 and increment. Roo must check for existing IDs before creating a new one.

Machine registry (`docs/progress/features.json`)

- Purpose: a simple JSON file optimized for programmatic consumption and CI. Tools can read this file and generate human-readable artifacts.
- Recommended usage: treat the registry as a derived artifact or keep it in sync with the ledger. If you prefer machine-first workflows, you may elect to treat the registry as primary and generate the ledger from it; the implementation below assumes ledger-first for human clarity.
- Schema: JSON array of objects matching the ledger fields (id, title, status, ...).

Example registry fragment (JSON)

```json
{
  "id": "API-001",
  "title": "ApiResponse and ErrorCodes canonicalization",
  "status": "planned",
  "next_step": "Implement ApiResponse dataclass and ErrorCodes enum in pk_py_lib.api",
  "spec_refs": ["docs/roo/img-app-api-specifications.md"],
  "code_refs": [],
  "test_refs": [],
  "acceptance": ["ApiResponse structure available to code, used by core APIs"],
  "risk": "low",
  "last_updated": "2025-08-14",
  "notes": "PR unified diff includes desired shape"
}
```

Dashboard generator

- Script: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
- Purpose: read the machine registry (`docs/progress/features.json`) and produce a readable dashboard at [`docs/progress/dashboard.md`](docs/progress/dashboard.md:1).
- Invocation (local):

```bash
python scripts/progress/generate_dashboard.py -i docs/progress/features.json -o docs/progress/dashboard.md
```

- CI usage: run the generator as a CI step to ensure dashboards are always updated on main branch commits (see suggested workflow below).

Workflow options (recommended)

Option A — Ledger-first (recommended for single-developer, human-readable)

- Edit the YAML ledger in [`docs/progress.md`](docs/progress.md:1) between the anchors.
- Update `last_updated` to today's date.
- Optional: run a small sync script to export the YAML ledger to `docs/progress/features.json`. If no sync script is available, update `docs/progress/features.json` manually.
- Run generator: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
- Commit both files together.

Option B — Registry-first (machine-first)

- Edit [`docs/progress/features.json`](docs/progress/features.json:1) (JSON or YAML).
- Run generator to refresh [`docs/progress/dashboard.md`](docs/progress/dashboard.md:1).
- Regenerate or update the YAML ledger in [`docs/progress.md`](docs/progress.md:1) from the registry (requires a sync script).
- Commit the registry and generated artifacts; keep the ledger in sync.

Which to choose?

- Ledger-first is easier for humans and for Roo when initialising a repo.
- Registry-first is convenient when many automated changes are expected or when other tools will programmatically update feature records.

Step-by-step tasks for common operations

1) Add a new feature

- Decide prefix and next numeric id (e.g., PROC-003).
- Edit [`docs/progress.md`](docs/progress.md:1): insert a new YAML object inside the ledger anchors.
- Update `last_updated` to current date.
- Update related specs and add a short `spec_refs` to point to relevant docs.
- If using `docs/progress/features.json`, add the equivalent object to the JSON array or regenerate it from the ledger.
- Run the dashboard generator:
  - `python scripts/progress/generate_dashboard.py -i docs/progress/features.json -o docs/progress/dashboard.md`
- Commit changes together.

2) Mark a feature as partial or done

- Update `status` field to `partial` or `done` inside the ledger (`docs/progress.md`).
- Add a short note in `notes` describing what remains (for partial) or a brief summary of completion (for done).
- Update `last_updated`.
- If you maintain `docs/progress/features.json`, update it and regenerate dashboard.
- Commit changes.

3) Record a blocker

- Set `status: blocked` and add explanation to `notes`.
- Include a prospective owner or decision point and an expected review date.

AI / Roo-specific update rules (safety & determinism)

- Roo MUST only edit the YAML ledger between the anchors in [`docs/progress.md`](docs/progress.md:1). This is enforced to avoid accidental edits to descriptive prose.
- Anchors: always preserve `<!-- progress-ledger:start -->` and `<!-- progress-ledger:end -->` exactly.
- Roo must update `last_updated` whenever it changes `status` or `next_step`.
- Roo must ensure ID uniqueness before creating a new ID. Check existing ledger entries.
- Roo should avoid reformatting the rest of the file; edits must be minimal and localized to the YAML block.
- Roo should prefer to update `docs/progress/features.json` via a sync script that parses the ledger; if such a script is missing, Roo may update `features.json` directly, but must keep both in sync.
- Roo must not delete entries from the ledger without adding a `notes: "deprecated"` entry or marking them `deferred`/`done`.

Validation and CI (suggested)

- Add a small GitHub Actions workflow at [`.github/workflows/progress.yml`](.github/workflows/progress.yml:1) that:
  - Lints `docs/progress/features.json` (JSON validity).
  - Optionally runs a sync to ensure `docs/progress.md` ledger and `features.json` are consistent (if a sync tool exists).
  - Regenerates the dashboard: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
  - Fails if the generator crashes or if `features.json` is invalid.

Example CI workflow (GitHub Actions)

```yaml
name: Progress - Validate & Generate
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
jobs:
  progress:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Validate registry JSON
        run: python -c "import json,sys;json.load(open('docs/progress/features.json'));print('OK')"
      - name: Generate dashboard
        run: python scripts/progress/generate_dashboard.py -i docs/progress/features.json -o docs/progress/dashboard.md
      - name: Commit dashboard (optional)
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "actions@github.com"
          git add docs/progress/dashboard.md
          git commit -m "chore(progress): regenerate dashboard" || echo "nothing to commit"
```

Notes on commit policy

- Prefer to commit ledger edits together with related code changes when possible (e.g., when implementing a feature, update its status and code_refs in the same PR).
- For minor status-only edits (e.g., marking done), small commits are fine but keep them atomic and descriptive.

Troubleshooting

- If the generator fails with JSON errors:
  - Validate `docs/progress/features.json` with `python -c "import json;json.load(open('docs/progress/features.json'))"`.
  - Confirm `docs/progress.md` contains valid YAML inside the anchors if the registry is generated from it.
- If Roo's automated edit changes the file incorrectly:
  - Revert and inspect the diff to ensure the YAML structure is correct (lists must use `- ` prefixes).
- If IDs collide:
  - Choose the next numeric suffix or rename conservatively and add `notes` explaining the rename.

Bootstrapping a new project

To add this progress system to a new repository, perform the following steps:

1. Create the directory `docs/` and create [`docs/progress.md`](docs/progress.md:1) with the header and the two anchors. Include a brief human summary above the anchors.
2. Add the ledger YAML block with an initial feature or two (use the template from [`docs/progress/templates/feature.md`](docs/progress/templates/feature.md:1)).
3. Add the generator script: copy [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1) into `scripts/progress/`.
4. (Optional) Create a machine registry `docs/progress/features.json` or `docs/progress/features.yml`.
5. Add a CI workflow at [`.github/workflows/progress.yml`](.github/workflows/progress.yml:1) to validate and generate the dashboard on pushes.
6. Document the maintenance rules in the repo README with a pointer to [`docs/progress/templates/feature.md`](docs/progress/templates/feature.md:1).

Example minimal `docs/progress.md` bootstrap

```markdown
# Project Progress
<!-- progress-ledger:start -->
- id: APP-001
  title: Initial scaffold
  status: planned
  next_step: Create app skeleton
  spec_refs:
    - docs/spec.md
  code_refs: []
  test_refs: []
  acceptance:
    - App window shows
  risk: low
  last_updated: 2025-08-14
  notes: Bootstrapped
<!-- progress-ledger:end -->
```

Maintenance checklist (recommended)

- Weekly: review each `in_progress` and `partial` item and update status/next_step.
- On merge: update feature status and add `code_refs` and `test_refs`.
- On major spec decisions: add a `notes` comment and reference the spec document.

Closing notes

This progress system is intentionally low-friction. The most important operational rule is to keep edits targeted to the YAML ledger between the anchors (`docs/progress.md`) and to keep the machine registry (`docs/progress/features.json`) in sync when used for automation. Roo is explicitly instructed to operate only inside the ledger anchors to keep changes deterministic and safe.

Useful references (clickable)

- Canonical ledger: [`docs/progress.md`](docs/progress.md:1)
- Machine registry: [`docs/progress/features.json`](docs/progress/features.json:1)
- Generator script: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
- Dashboard: [`docs/progress/dashboard.md`](docs/progress/dashboard.md:1)
- Templates: [`docs/progress/templates/feature.md`](docs/progress/templates/feature.md:1)
- Roadmap: [`docs/progress/roadmap.md`](docs/progress/roadmap.md:1)
- Traceability matrix: [`docs/progress/traceability.md`](docs/progress/traceability.md:1)

Revision history

- 2025-08-14: Initial implementation and documentation.

End of document