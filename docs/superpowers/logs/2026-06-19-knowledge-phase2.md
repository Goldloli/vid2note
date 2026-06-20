# Phase 2 — Vault And Media Evidence

## Result

Phase 2 completed. The Markdown Vault is now the durable knowledge-body source of truth, pipeline output is registered as timestamped source evidence, and frames/clips are generated only from controlled local source media.

## Delivered

- Idempotent Vault layout and templates for raw sources, source notes, Wiki pages, assets, private cache, staging, policy, index, and audit log.
- Path-confined Markdown reads, optimistic human edits, atomic replacement, content hashes, and append-only edit metadata without note contents.
- Stable source identities, URL normalization, SRT timeline segments, transcript Markdown, source metadata, duplicate reuse, and rollback-safe registration.
- Real Worker registration of completed pipeline notes and transcripts with `vid2note://source` time evidence.
- Typed Vault tree/page/search and Source ingest/read APIs with generated OpenAPI/TypeScript contracts.
- Controlled list-argument FFmpeg frame/clip generation, bounded ranges, buffered/clamped clips, content-addressed cache, atomic rendering, and promote-to-assets.
- Typed missing-media details pointing back to transcript and canonical URL.
- Debounced polling watcher with internal-operation suppression and external-edit audit entries.
- Restart coverage proving sources and Markdown remain readable after deleting the SQLite state database.

## Verification

- `uv run pytest -q`: 295 passed, 5 third-party deprecation warnings.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run mypy core/src server/src`: passed.
- `npm --prefix desktop run contracts:check`: passed.
- `npm --prefix desktop run test:unit`: 6 passed.
- `npm --prefix desktop run typecheck`: passed.
- `npm --prefix desktop run build`: passed.
- `npm --prefix desktop run test:e2e`: 12 passed.
- `npm --prefix desktop run electron:build`: DMG and ZIP produced successfully; local build remains unsigned.

## Review

CodeGraph was synced and the complete Phase 2 diff was independently reviewed for path escape, symlink escape, partial writes, concurrent render/cache behavior, source identity collisions, structured errors, media privacy, watcher feedback loops, state-database dependence, and generated contract drift. Blocking findings fixed:

- prevent progress regression between source registration and mind-map generation;
- return typed not-found responses for missing Vault pages;
- render media to temporary files before atomic cache promotion;
- reject source-id path traversal during asset promotion;
- suppress watcher feedback for human edits and source registration using operation identifiers.

No Critical, High, or blocking Medium findings remain.

## Checkpoint

- Commit: `55bf249` (`chore(phase2): checkpoint vault and media evidence`)
- Entry to Phase 3: all Phase 2 exit conditions and applicable project quality gates are green; the worktree is clean apart from this log entry.
