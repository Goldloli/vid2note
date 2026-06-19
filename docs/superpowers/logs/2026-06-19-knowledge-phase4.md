# Phase 4 — Agent Runtime

## Result

Phase 4 completed. Built-in, Codex CLI, and Claude Code runtimes share one normalized event model; external processes run in isolated workspaces and can write back only by proposing a ChangeSet.

## Delivered

- Normalized AgentEvent sequencing and terminal-state enforcement.
- Runtime detection registry and capability reporting for Built-in, Codex, and Claude.
- Read-only Built-in tools for index-first Wiki lookup and source evidence.
- Per-run isolated workspaces with manifests, baseline hashes, symlink/path protection, and formal-Vault denial.
- Controlled subprocess execution with argv-only launch, bounded stderr, redaction, timeout, cancellation, and process-group termination.
- Codex JSONL and Claude stream-json adapters with fake executable integration fixtures.
- Durable Agent sessions, runs, events, cancellation, SSE streaming, and ChangeSet-only external write-back.
- Concurrent-human-edit preservation so stale external proposals fail normal ChangeSet validation instead of overwriting the Vault.

## Verification

- Phase checkpoint regression: 387 Python tests passed; Ruff, Ruff format, and mypy passed.
- Generated contracts, frontend unit tests, typecheck, and production build passed.
- The combined Phase 5 final gate later re-ran all Phase 4 paths through the complete Python, browser E2E, and Electron packaging suites.

## Review

The complete runtime boundary was reviewed for command injection, workspace escape, symlink traversal, live-Vault access, secret leakage, unbounded output, missing terminals, duplicate sequences, cancellation, timeout, stale bases, and silent runtime fallback. Blocking findings fixed:

- preserve baseline content and hashes when collecting external workspace diffs;
- package parser tests to avoid module-name collisions in the full suite;
- verify macOS sandbox profiles deny the live Vault while permitting the isolated workspace;
- persist every normalized event before broadcasting it.

No Critical, High, or blocking Medium findings remain.

## Checkpoint

- Commit: `f0c6d54` (`chore(phase4): checkpoint agent runtime`)
- Entry to Phase 5: runtime contracts, adapters, sandbox enforcement, session persistence, and abnormal-flow tests passed.
