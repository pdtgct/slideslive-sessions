# neurips-sessions

Capture slides, video, and AI-generated notes from NeurIPS conference sessions.

## How it works

For each session URL, the tool:
1. Downloads slide JPEGs from the SlidesLive CDN
2. Downloads the session video via yt-dlp
3. Extracts audio and transcribes it with Whisper
4. Generates structured Markdown notes via the Claude API

All steps are idempotent — re-running the same URL skips already-downloaded files.

## Prerequisites

**System dependencies (install before anything else):**

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

ffmpeg is required by yt-dlp to mux HLS video/audio streams, and by Whisper for audio extraction.

**Python 3.11+**

## Setup

```bash
# 1. Clone and create virtualenv
git clone https://github.com/pdtgct/neurips-sessions
cd neurips-sessions
python -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
pip install -e .

# 3. Install Playwright browser
playwright install chromium

# 4. Configure API key
cp .env.example .env
# Edit .env and set: ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Step 1: Log in to neurips.cc

```bash
python auth.py
```

Opens a browser window. Complete the SSO/Google login, then the window closes and
`cookies.json` is saved automatically.

### Step 2: Capture a session

```bash
python capture.py https://neurips.cc/virtual/2025/poster/12345
```

Output is written to `./output/{session-slug}/`.

### Common options

```bash
# Capture multiple sessions
python capture.py <url1> <url2> <url3>

# Skip video download (slides + notes only, no ffmpeg needed)
python capture.py --no-video <url>

# Skip Claude notes generation
python capture.py --no-notes <url>

# Use a faster/smaller Whisper model (tiny < base < small < medium < large)
python capture.py --whisper-model base <url>

# Custom output directory
python capture.py --output-dir ~/Downloads/neurips <url>

# If auto-detection of the SlidesLive ID fails
python capture.py --presentation-id 39055688 <url>
```

## Output structure

```
output/
  {session-slug}/
    metadata.json     # title, URL, presentation ID, slide count
    video.mp4
    audio.mp3
    slides/
      001.jpg, 002.jpg, ...
    sync.xml          # slide-to-timecode mapping (if available)
    transcript.txt    # Whisper transcription
    notes.md          # Claude-generated structured notes
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API for notes |
| `WHISPER_MODEL` | `small` | Whisper model size |
| `OUTPUT_DIR` | `./output` | Root output directory |

## Individual steps

```bash
python auth.py                         # login only
python transcribe.py output/session-X/ --model base
python summarize.py output/session-X/
```
