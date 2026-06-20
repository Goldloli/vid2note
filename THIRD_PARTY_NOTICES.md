# Third-party notices

This file records the separately distributed tools used by vid2note. It is an
engineering inventory, not legal advice. Python and npm dependency versions
remain recorded in `uv.lock` and `desktop/package-lock.json`.

## FFmpeg

- Pinned macOS build: FFmpeg 8.1.2 from `https://evermeet.cx/ffmpeg/ffmpeg-8.1.2.zip`.
- Project and source: `https://ffmpeg.org/`.
- License: FFmpeg is LGPL-2.1-or-later by default; builds that enable GPL
  components are governed by the corresponding GPL terms. Before distributing
  a downloaded binary, the release process must retain its `ffmpeg -L` output,
  license text, build configuration, and the source offer required by that
  exact build.

## yt-dlp

- Pinned release: 2026.06.09.
- Project and source: `https://github.com/yt-dlp/yt-dlp`.
- License: The Unlicense. Downloaded macOS and Linux artifacts are verified
  against the SHA-256 digests published with the GitHub release.

## Local ASR

- FunASR is an optional local inference dependency; models are downloaded on
  demand and may carry their own model-card terms. They are not embedded in the
  Electron application bundle.
- The previously vendored GPLv3 AsrTools `bk_asr` source was removed. Its
  provenance, distribution impact, and remediation are recorded in
  `docs/compliance/third-party-asr-audit.md`.

## Other media downloaders

BBDown and you-get are optional download fallbacks. Their exact versions and
license texts must accompany any release that elects to bundle them; the
default `npm run electron:build` output does not bundle these tools.
