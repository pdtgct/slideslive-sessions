# slideslive-sessions

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A CLI tool for capturing ML conference session data — slides (JPEG), video (MP4), audio transcripts (Whisper), and AI-generated structured notes — into a local, searchable archive.

Built for ML researchers who want to review talks at their own pace without re-watching hours of video.

## Conference compatibility

Tested with **[NeurIPS](https://neurips.cc/Conferences/2025/Dates)**. The tool targets the SlidesLive player, so it may also work with other conferences that use SlidesLive for their virtual presentation platform — but these have **not been tested**:

- [ICLR](https://iclr.cc/templates/VirtualConferenceAuthorInstructions)
- [ICML](https://icml.cc/Conferences/2026/CallForWorkshops)

---

## Prerequisites

- **Python 3.11+**
- **ffmpeg** (required for audio extraction)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
- A **conference account** (for sessions behind login)
- An **API key** for your chosen LLM provider (e.g. `ANTHROPIC_API_KEY`)

---

## Setup

```bash
# Clone the repo
git clone https://github.com/pdtgct/slideslive-sessions.git
cd slideslive-sessions

# Install the package and dependencies (uv creates the venv automatically)
uv sync

# Install the Playwright Chromium browser
uv run playwright install chromium

# Configure environment variables
cp .env.example .env
# Edit .env and set NOTES_MODEL and the corresponding API key
```

> Don't have `uv`? Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` or see the [uv docs](https://docs.astral.sh/uv/getting-started/installation/). Alternatively, use `python -m venv .venv && source .venv/bin/activate && pip install -e .`

---

## Usage

### 1. Log in

```bash
uv run slideslive-auth
```

This opens a browser window. Log in manually; cookies are saved to `cookies.json`.

### 2. Capture a session

```bash
uv run slideslive-capture https://neurips.cc/virtual/2025/poster/12345
```

### All flags

| Flag | Description |
|---|---|
| `--no-video` | Skip video download; capture slides and notes only |
| `--no-notes` | Skip notes generation |
| `--recreate-notes` | Regenerate `notes.md` even if it already exists |
| `--clean-media` | Delete `video.mp4` and `audio.mp3` after capture to save disk space |
| `--whisper-model <size>` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` (default: `small`) |
| `--cookies <path>` | Path to cookies file (default: `cookies.json`) |
| `--output-dir <path>` | Root output directory (default: `$OUTPUT_DIR` or `./output`) |
| `--presentation-id <id>` | SlidesLive presentation ID, if auto-detection fails |

### Batch multiple sessions

```bash
uv run slideslive-capture <url1> <url2> <url3>
```

---

## Re-running individual steps

```bash
uv run slideslive-auth                                      # log in / refresh cookies
uv run slideslive-transcribe output/session-slug/           # re-transcribe with a different model
uv run slideslive-summarize output/session-slug/ --force    # regenerate notes
```

---

## Configuration

All settings can be placed in a `.env` file in the project root.

| Variable | Default | Purpose |
|---|---|---|
| `NOTES_MODEL` | `anthropic/claude-opus-4-6` | litellm model string for notes generation |
| `NOTES_API_BASE` | _(unset)_ | Custom API base URL (e.g. for Ollama or local endpoints) |
| `ANTHROPIC_API_KEY` | _(required for Anthropic)_ | Anthropic API key |
| `OPENAI_API_KEY` | _(required for OpenAI)_ | OpenAI API key |
| `WHISPER_MODEL` | `small` | Whisper model size |
| `OUTPUT_DIR` | `./output` | Root output directory |

---

## Supported LLM Providers

Notes generation uses [litellm](https://docs.litellm.ai/docs/providers), so any supported provider works.

**Anthropic (default)**
```env
NOTES_MODEL=anthropic/claude-opus-4-6
ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI**
```env
NOTES_MODEL=openai/gpt-4o
OPENAI_API_KEY=sk-...
```

**Ollama (local)**
```env
NOTES_MODEL=ollama/llama3
NOTES_API_BASE=http://localhost:11434
```

See the [litellm provider docs](https://docs.litellm.ai/docs/providers) for the full list.

---

## Output structure

Each session is saved under `output/{session-slug}/`:

```
output/{session-slug}/
  metadata.json       # title, URL, presentation ID, slide count
  page.md             # human-readable session summary page
  video.mp4           # downloaded video (omitted with --clean-media)
  audio.mp3           # extracted audio (omitted with --clean-media)
  slides/
    001.jpg, 002.jpg, ...
  sync.xml            # slide-to-timecode mapping
  transcript.txt      # Whisper transcription
  notes.md            # AI-generated structured notes
```

Re-running `slideslive-capture` on the same URL is **idempotent** — existing files are skipped unless `--recreate-notes` is passed.

---

## Troubleshooting

**`ffmpeg not found`** — Install ffmpeg (see Prerequisites). The tool requires it for audio extraction.

**`cookies.json` expired / login required** — Run `slideslive-auth` to refresh your session cookies.

**Whisper is too slow** — Use a smaller model: `--whisper-model base` or `--whisper-model tiny`.

**Notes generation returned empty output** — Check that your API key is set and the model string in `NOTES_MODEL` is valid for your provider.

**SlidesLive ID not detected** — Pass `--presentation-id <id>` manually. The ID appears in the SlidesLive embed URL on the session page.

---

## Limitations

- A **conference account** is required for sessions behind the virtual conference paywall.
- Slides depend on **SlidesLive** — sessions using other players may not have downloadable slide images.
- **Whisper accuracy** varies by audio quality, speaker accent, and model size. Technical terminology may require a larger model.

---

## Contributing

Contributions welcome. Open an issue to discuss a change before sending a PR. Please keep PRs focused — one concern per PR makes review easier.

---

## License

MIT
