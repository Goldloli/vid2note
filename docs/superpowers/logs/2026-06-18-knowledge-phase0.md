# Phase 0 — trusted baseline

Status: complete
Checkpoint: `abb841e`

## Delivered

- One explicit `RuntimePaths` data root and lifespan-owned services.
- Structured failures, bounded Worker concurrency, retries, rerun/resume,
  streamed media imports, graceful shutdown, and dependency locking.
- Worker-driven SRT → source-note integration with deterministic time evidence,
  a two-case Golden Dataset, desktop import/export E2E, and package audit.
- Removed the GPLv3 AsrTools vendored implementation and its runtime provider;
  FunASR is the local default. See `docs/compliance/third-party-asr-audit.md`.

Task commits: `88e5804`, `75dfa5b`, `dcd2e5f`, `30c9bf0`, `1b0e81e`,
`ede3942`, `ded34e3`.

## Verification

- `uv run pytest -q`: 256 passed.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 112 files already formatted.
- `uv run mypy core/src server/src`: passed, 65 source files.
- `npm --prefix desktop run build`: passed.
- `npm --prefix desktop run test:main`: 2 passed.
- `npm --prefix desktop run test:e2e`: 9 passed.
- `npm --prefix desktop run electron:build`: DMG and ZIP built.
- Package inspection: no `bk_asr` source or Python bytecode in `core-src`.

## Review

CodeGraph was synchronized before and after implementation. The complete diff,
staging scope, path traversal boundaries, task terminal states, recovery,
concurrency, data-loss behavior, contracts, privacy, and licensing were
reviewed. Blocking findings fixed before checkpoint:

- SRT rerun from `organize` incorrectly restarted the missing download chain.
- Pipeline execution continued after a failed node.
- SSE used a duplicated `/api/v1` prefix in browser E2E.
- Electron resources copied vendored GPL code and stale `.pyc` files.
- Several old tests still constructed path-owning services implicitly.

No Critical, High, or blocking Medium findings remain. Phase 1 may start
because the legacy video/SRT path now runs through one tested control plane,
all Phase 0 gates pass, and release compliance is no longer blocked.
