# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`slideslive-sessions` — a Python CLI tool for capturing ML conference session data (NeurIPS, ICLR, ICML, and others using SlidesLive): slides (JPEG), video (MP4), audio transcripts (Whisper), and AI-generated notes (Claude API).

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
slideslive-auth                     # opens browser, saves cookies.json
```

### Capture a session
```bash
slideslive-capture https://neurips.cc/virtual/2025/poster/12345
```

### Options
```bash
slideslive-capture --no-video <url>           # slides + notes only (no video/transcript)
slideslive-capture --no-notes <url>           # skip Claude notes generation
slideslive-capture --whisper-model base <url> # use faster/smaller Whisper model
slideslive-capture --cookies path/to/cookies.json <url>
slideslive-capture <url1> <url2> <url3>       # batch multiple sessions
```

### Run individual steps
```bash
slideslive-auth                              # login only
slideslive-transcribe output/session-X/      # re-transcribe with different model
slideslive-summarize output/session-X/       # re-generate notes
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API for notes generation |
| `WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
| `OUTPUT_DIR` | `./output` | Root output directory |

## Architecture

```
src/slideslive_sessions/capture.py      — main CLI orchestrator
src/slideslive_sessions/auth.py         — Playwright browser login + cookie management
src/slideslive_sessions/slides.py       — SlidesLive slide JPEG + sync XML download
src/slideslive_sessions/transcribe.py   — ffmpeg audio extraction + Whisper transcription
src/slideslive_sessions/summarize.py    — Claude API notes generation
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

## Debugging / Bug Fixes

After making bug fixes, re-read the surrounding logic to check for related issues (e.g., falsy value handling, off-by-one errors) before presenting the fix as complete.

## Key Technical Notes

- SlidesLive slides are individual JPEGs from CloudFront CDN (not PDFs)
- NeurIPS uses both SlidesLive and VideoKen players; yt-dlp handles both
- Re-running `slideslive-capture` on the same URL is idempotent (skips existing files)
- `cookies.json` and `.env` are gitignored — never commit credentials
