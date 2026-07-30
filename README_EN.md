<p align="center">
  <img src="frontend/public/icons/vid2note-icon-180.png" width="112" alt="vid2note icon">
</p>

# vid2note

Turn video URLs or local media into structured Markdown notes and mind maps.

[中文说明](README.md) · [MIT License](LICENSE) · [Contributing](CONTRIBUTING.md)

> vid2note is a local, single-user application without authentication. Docker
> Compose binds it to `127.0.0.1:8761` by default. Do not expose it to the
> public internet without authentication, TLS, and network access controls.

## Highlights

```text
download → extract audio → ASR → LLM notes → mind map → cleanup
```

- YouTube, Bilibili, generic HTTP(S), local video, and local audio input.
- Experimental `bcut` online ASR, local whisper.cpp/faster-whisper, or an external ASR endpoint.
- DeepSeek, Qwen, GLM, Moonshot, MiniMax, Doubao, Baidu, Ollama, and one custom OpenAI-compatible endpoint.
- Tabbed Settings and ASR diagnostics, including per-provider connectivity tests.
- Four note-detail levels: concise, balanced, detailed, and exhaustive.
- Optional PDF handout reference and video-frame embedding.
- Markdown, XMind, PNG, and Markdown-outline exports.
- Persistent SQLite tasks, SSE progress, node-level reruns, batch export, and retention rules.
- One same-origin Docker container for the Vue frontend and FastAPI backend.

## Quick start

```bash
git clone https://github.com/Goldloli/vid2note.git
cd vid2note
cp .env.example .env
docker compose up -d --build
```

Open <http://localhost:8761> and configure an LLM in Settings. You can also
provide the initial configuration through `.env`:

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=deepseek-v4-flash
```

Public settings stored in `data/config/settings.json` take precedence over
environment defaults.

## Ollama

Run Ollama on the host:

```bash
ollama pull qwen3.5
```

Then use:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3.5
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

Ollama does not need an API key. The Compose configuration provides the
`host.docker.internal` mapping on Linux.

## Local ASR

Models are never downloaded automatically. Mount a faster-whisper model
directory or whisper.cpp model into the container and set its in-container
path on the ASR page. See [configuration](docs/CONFIGURATION.md).

## Development

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend && .venv/bin/python -m pytest

# Node.js 22+
cd ../frontend
npm ci
npm run check
```

See [architecture](docs/ARCHITECTURE.md), [troubleshooting](docs/TROUBLESHOOTING.md),
the [roadmap](docs/ROADMAP.md), and the [security policy](SECURITY.md).

## Privacy and legal notice

Credentials stored through the UI are encrypted with Fernet in
`data/config/credentials.enc`; public settings live in `settings.json`.
Protect and back up `credentials.enc` and its master key together. For managed
deployments, mount the key through `VID2NOTE_MASTER_KEY_FILE`.

`bcut` is an experimental online compatibility feature that depends on an
external service and may stop working without notice. Video-platform
availability is likewise not guaranteed. Only process content you are
authorized to use and follow applicable platform terms and law.

vid2note evolved from `ai_srt2md`, an earlier project by the same author. See
[NOTICE](NOTICE). Licensed under the [MIT License](LICENSE).
