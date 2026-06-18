# Third-party ASR audit

Date: 2026-06-18
Owner: vid2note repository maintainer
Release status: **cleared after removal**

## Source and identity

`core/src/vid2note_core/asr/bk_asr/` is copied from
`WEIFENG2333/AsrTools` (`bk_asr/`). The local reference snapshot matches the
upstream tree at commit `572ac8fb5a4a489babbc1ac681555d002bd2ca1b` (2025-06-17).
All seven vendored Python files have the same SHA-256 hashes as
`/Users/gejiawei/Desktop/ai_code/项目参考/AsrTools-main/bk_asr/`.

The files entered this repository in commit
`d6eac5c31ad14c3ba617a5268a019b823441d838`. Despite that commit's formatting
message, the current files are byte-identical to the reference snapshot. The
vid2note-owned bridge `asr/cloud/bk_adapter.py` and its tests are separate new
files; no vendored file has a recorded local modification.

## License obligations

AsrTools is licensed under GPLv3. Conveying these sources or an application
that incorporates them requires, at minimum, preserving copyright and license
notices, providing the GPLv3 text and corresponding source, identifying
modifications, and licensing the covered combined work compatibly with GPLv3.
This is an engineering inventory, not legal advice.

Conclusion before remediation: the repository's root MIT license and package
did not satisfy those obligations. There was no vendored GPL license/notice,
source offer in the desktop package, or approved GPL-compatible release policy.

## Distribution check

`desktop/package.json` copies `../core/src/**/*` into `core-src` through
`extraResources`. Before remediation, `electron-builder` therefore included
`bk_asr` in DMG/ZIP output; this was distribution, not a development-only
dependency.

Conclusion: no DMG, ZIP, installer, wheel, or source archive containing that
directory may be published. The directory is now absent from the repository
and package input.

## Decision and remediation

The approved engineering direction was replacement, not continued extension:

1. The seven vendored files were removed from `core/src` on 2026-06-18.
2. `asrtools-b` was removed from `ASRFactory` and all runtime defaults.
3. FunASR is now the default provider and runs locally.
4. `BkAsrAdapter` remains only as an unregistered, backend-free compatibility
   boundary for migration tests; it imports and distributes no GPL code.

Package-content audit: Electron's `core-src` resource now contains no `bk_asr`
directory and no AsrTools source. The root MIT license therefore no longer
conflicts with this removed component. External distribution is cleared with
respect to AsrTools; other third-party dependencies remain subject to their
own normal notices.
