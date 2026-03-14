# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`neurips-sessions` — a Python CLI tool for capturing NeurIPS session data: slides (JPEG), video (MP4), audio transcripts (Whisper), and AI-generated notes (Claude API).

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Install Playwright browser
playwright install chromium

# Copy and fill in env vars
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# System requirement: ffmpeg must be installed
# macOS: brew install ffmpeg
```

## Run Commands

### First-time login
```bash
python auth.py                     # opens browser, saves cookies.json
```

### Capture a session
```bash
python capture.py https://neurips.cc/virtual/2025/poster/12345
```

### Options
```bash
python capture.py --no-video <url>           # slides + notes only (no video/transcript)
python capture.py --no-notes <url>           # skip Claude notes generation
python capture.py --whisper-model base <url> # use faster/smaller Whisper model
python capture.py --cookies path/to/cookies.json <url>
python capture.py <url1> <url2> <url3>       # batch multiple sessions
```

### Run individual steps
```bash
python auth.py                         # login only
python transcribe.py output/session-X/ # re-transcribe with different model
python summarize.py output/session-X/  # re-generate notes
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API for notes generation |
| `WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `OUTPUT_DIR` | `./output` | Root output directory |

## Architecture

```
capture.py      — main CLI orchestrator
auth.py         — Playwright browser login + cookie management
slides.py       — SlidesLive slide JPEG + sync XML download
transcribe.py   — ffmpeg audio extraction + Whisper transcription
summarize.py    — Claude API notes generation
```

### Output structure per session
```
output/{session-slug}/
  metadata.json       # title, URL, presentation ID, slide count
  video.mp4
  audio.mp3
  slides/
    001.jpg, 002.jpg, ...
  sync.xml            # slide-to-timecode mapping
  transcript.txt      # Whisper transcription
  notes.md            # Claude-generated structured notes
```

## Key Technical Notes

- SlidesLive slides are individual JPEGs from CloudFront CDN (not PDFs)
- NeurIPS uses both SlidesLive and VideoKen players; yt-dlp handles both
- Re-running `capture.py` on the same URL is idempotent (skips existing files)
- `cookies.json` and `.env` are gitignored — never commit credentials
