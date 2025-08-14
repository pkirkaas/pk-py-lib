# Feature Template — Progress Ledger Item

This template documents the canonical fields and usage for a single feature record stored in the project ledger and registry.

Purpose
- Provide a stable schema that both humans and AI (Roo) can edit programmatically.

Source of truth
- The canonical human-editable ledger is: [`docs/progress.md`](docs/progress.md:1)
- The machine registry (JSON) is: [`docs/progress/features.json`](docs/progress/features.json:1)
- The dashboard generator script is: [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)

Canonical YAML example
```yaml
- id: APP-001
  title: M0 app shell
  status: partial
  next_step: Wire pdm run imgapp to app entry and run smoke test
  spec_refs:
    - docs/add-app-plan.md
  code_refs:
    - img_app/img_app/app.py
  test_refs:
    - img_app/tests/test_smoke.py
  acceptance:
    - Window titled KDC Image Organizer shows
    - Menus File, View, Help exist
  risk: low
  last_updated: 2025-08-14
  notes: Scaffold exists; smoke test pending
```

Field definitions
- id (string): Stable identifier. Prefixes: APP, DB, API, PROC, UI, FS, CACHE, LOG, TEST. Use 3-digit numeric suffix.
- title (string): Short human-friendly title.
- status (string): One of: planned, in_progress, partial, done, blocked, deferred.
- next_step (string): Concise next action to progress the item.
- spec_refs (list of strings): Paths to spec docs. Use relative repo paths.
- code_refs (list of strings): Paths to implementation files or folders.
- test_refs (list of strings): Paths to tests that exercise the item.
- acceptance (list of strings): Concrete acceptance criteria; all must be satisfied to mark done.
- risk (string): low / medium / high
- last_updated (date string): YYYY-MM-DD
- notes (string): Freeform notes and blockers.

Status guidance
- planned: Spec exists; no code
- in_progress: Active development
- partial: Partial implementation; list remaining acceptance items in notes
- done: All acceptance criteria satisfied with tests
- blocked: Waiting on an external decision/dependency; note blocker and owner
- deferred: Explicitly postponed; include review date

ID naming examples
- APP-001, DB-001, API-001, PROC-001, UI-001, FS-001, CACHE-001, LOG-001

AI (Roo) update rules
- Roo only edits the YAML ledger section inside [`docs/progress.md`](docs/progress.md:1) between the anchors:
  <!-- progress-ledger:start --> and <!-- progress-ledger:end -->
- For machine updates, prefer updating [`docs/progress/features.json`](docs/progress/features.json:1) and regenerating the dashboard with [`scripts/progress/generate_dashboard.py`](scripts/progress/generate_dashboard.py:1)
- When creating new items, append them to the ledger and the registry. Use the next available numeric suffix.
- When marking done, set status=done, update last_updated, and add brief summary in notes.

Best practices
- Keep titles short and actionable.
- Use spec_refs to point to the exact document and (optionally) the heading in the spec.
- Keep acceptance criteria minimal and testable.

Troubleshooting
- If the generator fails, inspect [`docs/progress/features.json`](docs/progress/features.json:1) for valid JSON.
- If the ledger drifts from the registry, prefer updating the registry and re-running the generator, then reconcile the ledger manually.

Contact and ownership
- Owner: repository author (single developer). Record any tradeoff notes in [`docs/roo/suggested-changes.md`](docs/roo/suggested-changes.md:1).

Revision history
- 2025-08-14: Initial template created