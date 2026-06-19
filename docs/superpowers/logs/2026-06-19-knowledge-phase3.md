# Phase 3 — Wiki Compiler

## Result

Phase 3 completed. New sources are retrieved index-first and compiled into durable, reviewable ChangeSets; formal Wiki pages change only through validation and atomic application, with approval as the default autonomy mode.

## Delivered

- Immutable ChangeSet, operation, citation, contradiction, validation, status, parent, and supersession contracts with append-safe persistence.
- Index-first retrieval across schema, index, related Wiki pages, source notes, and raw transcripts without a vector database.
- Strict structured Wiki compilation with one repair attempt, information classification, source-evidence requirements, and pipeline proposal generation.
- Validation for path confinement, page identity, stale bases, frontmatter, source identity, time ranges, wikilinks, duplicate paths, create/update, and atomic rename.
- Multi-file transactions for Wiki pages, `index.md`, and `log.md`, including crash recovery, exact-byte rollback, conflict proposals, and I/O-failure state reconciliation.
- A/B/C autonomy policy, approval/rejection/revision/partial approval/revert APIs, generated contracts, and one backend policy shown in both the title bar and Agent panel.
- Wiki lint for contradictions, stale claims, orphans, missing pages, broken links, missing citations, index drift, and research gaps.
- Six compiler fixtures plus real two-source compounding, contradiction preservation, stale-base rejection, Worker-to-approval, and restart-safe API scenarios.

## Verification

- `uv run pytest -q`: 353 passed, 5 third-party deprecation warnings.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run mypy core/src server/src`: passed.
- `npm --prefix desktop run contracts:check`: passed.
- `npm --prefix desktop run test:unit`: 7 passed.
- `npm --prefix desktop run typecheck`: passed.
- `npm --prefix desktop run build`: passed.
- `npm --prefix desktop run test:e2e`: 12 passed.
- `npm --prefix desktop run electron:build`: DMG and ZIP produced successfully; local build remains unsigned.

## Review

CodeGraph was synced and the complete Phase 3 diff was independently reviewed for path and symlink escape, stale writes, partial commits, crash recovery, rollback conflicts, source evidence, contract drift, autonomy defaults, duplicate accumulation, and formal-Wiki write authority. Blocking findings fixed:

- separate reverted ChangeSets from applied listings and expose the status in the API contract;
- align the Vault schema template with the Validator page contract;
- persist large ChangeSets without assuming a single complete `os.write`;
- load the title-bar and Agent-panel autonomy badge from the backend config endpoint;
- implement real atomic rename by immutable page id and exact rollback;
- reconcile live files with persisted status when apply or revert storage reports an ambiguous I/O failure.

No Critical, High, or blocking Medium findings remain.

## Checkpoint

- Commit: `c13f37a` (`chore(phase3): checkpoint wiki compiler`)
- Entry to Phase 4: all Phase 3 exit conditions and complete project quality gates are green; the worktree is clean apart from this log entry.
