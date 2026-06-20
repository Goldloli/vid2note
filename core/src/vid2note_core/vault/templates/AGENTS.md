# vid2note Wiki Schema

This Vault is a human-readable, Obsidian-compatible knowledge workspace.

## Navigation

1. Read `index.md` before searching individual pages.
2. Use `wiki/concepts`, `wiki/people`, and `wiki/projects` for compiled pages.
3. Treat `raw` and `sources` as evidence, not as compiled Wiki pages.

## Page contract

Wiki frontmatter includes `id`, `title`, `page_type`, `status`, `sources`, `created_at`, and `updated_at`.
Allowed page types are `concept`, `entity`, `topic`, and `comparison`.
Time evidence uses `vid2note://source/<source_id>?start=<milliseconds>&end=<milliseconds>`.

## Write policy

Agents and the Wiki Compiler may change formal Wiki pages only through a validated ChangeSet.
Human editor changes are recorded separately. Never overwrite raw source material in place.
Do not create or depend on a vector index or vector database; navigate index-first and search plain text.
